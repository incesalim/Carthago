"""Tests for scripts/verify_chart_spec.py — the chart-spec verification harness.

Covers the transform engine (scale/sum_series/ratio/growth), the derive AST
walker (incl. rejecting unknown refs, bad arity, forward refs/cycles), tolerance
math (abs/pp/pct), spec validation, the SQL param-inliner, and the monthly-vs-
weekly bank-type namespaces (the code collision this whole design defends).

Stdlib only + an in-memory FakeRunner — no DB or network. scripts/ is on the
pytest pythonpath (pyproject) so the modules import directly.
"""
import pytest

import verify_chart_spec as v
import _bank_types as bt


# ---------------------------------------------------------------------------
# Fake DB runner — keyed by EVDS code; handles the COUNT(*) registry probe too.
# ---------------------------------------------------------------------------

class FakeRunner:
    label = "fake"

    def __init__(self, evds: dict[str, list[tuple[str, float]]]):
        self.evds = evds

    def query(self, sql: str, params: list) -> list[dict]:
        if "COUNT(*)" in sql:
            return [{"n": len(self.evds.get(params[0], []))}]
        if "evds_series" in sql:
            return [{"d": d, "v": val} for d, val in self.evds.get(params[0], [])]
        return []


# ---------------------------------------------------------------------------
# derive AST walker
# ---------------------------------------------------------------------------

def test_eval_formula_const_and_ref():
    resolved = {"a": {"2026-01": 10.0}}
    assert v.eval_formula({"const": 3}, resolved) == 3.0
    assert v.eval_formula({"ref": "a"}, resolved) == {"2026-01": 10.0}


def test_eval_formula_arithmetic_aligns_by_date():
    resolved = {
        "a": {"2026-01": 10.0, "2026-02": 20.0},
        "b": {"2026-01": 2.0, "2026-02": 5.0, "2026-03": 9.0},
    }
    # (a - b) / 2  → only dates present in both a and b
    node = {"op": "div", "args": [
        {"op": "sub", "args": [{"ref": "a"}, {"ref": "b"}]},
        {"const": 2},
    ]}
    out = v.eval_formula(node, resolved)
    assert out == {"2026-01": 4.0, "2026-02": 7.5}


def test_eval_formula_div_by_zero_drops_date():
    resolved = {"a": {"x": 10.0, "y": 10.0}, "b": {"x": 0.0, "y": 5.0}}
    out = v.eval_formula({"op": "div", "args": [{"ref": "a"}, {"ref": "b"}]}, resolved)
    assert out == {"y": 2.0}  # x dropped (div by zero)


def test_eval_formula_unknown_ref_raises():
    with pytest.raises(ValueError, match="unresolved/unknown series 'ghost'"):
        v.eval_formula({"ref": "ghost"}, {})


def test_eval_formula_bad_op_and_arity_raise():
    with pytest.raises(ValueError, match="unknown formula op"):
        v.eval_formula({"op": "pow", "args": [{"const": 2}, {"const": 3}]}, {})
    with pytest.raises(ValueError, match="exactly 2 args"):
        v.eval_formula({"op": "add", "args": [{"const": 1}]}, {})


# ---------------------------------------------------------------------------
# transform ops
# ---------------------------------------------------------------------------

def test_scale():
    out = v.apply_op({"op": "scale", "factor": 0.001}, {"a": 2000.0, "b": 5000.0}, {})
    assert out == {"a": 2.0, "b": 5.0}


def test_sum_series_by_date():
    resolved = {"x": {"d1": 1.0, "d2": 2.0}, "y": {"d1": 10.0, "d3": 3.0}}
    out = v.apply_op({"op": "sum_series", "keys": ["x", "y"]}, {}, resolved)
    assert out == {"d1": 11.0, "d2": 2.0, "d3": 3.0}


def test_ratio_percent_and_zero_denominator():
    resolved = {"n": {"d1": 50.0, "d2": 10.0}, "den": {"d1": 200.0, "d2": 0.0}}
    out = v.apply_op({"op": "ratio", "numerator": "n", "denominator": "den"}, {}, resolved)
    assert out == {"d1": 25.0}  # d2 dropped (den = 0)


def test_ratio_custom_scale():
    resolved = {"n": {"d1": 1.0}, "den": {"d1": 4.0}}
    out = v.apply_op({"op": "ratio", "numerator": "n", "denominator": "den", "scale": 1}, {}, resolved)
    assert out == {"d1": 0.25}


def test_growth_yoy_and_annualized():
    series = {"w1": 100.0, "w2": 110.0, "w3": 121.0}
    yoy = v.apply_op({"op": "growth", "window": 1, "mode": "yoy"}, series, {})
    assert yoy["w2"] == pytest.approx(10.0)
    assert yoy["w3"] == pytest.approx(10.0)
    # annualized with window=13 uses exponent 52/13 = 4
    ann = v._growth({"a": 100.0, "b": 110.0}, 1, "annualized")  # exponent 52
    assert ann["b"] == pytest.approx((1.1 ** 52 - 1) * 100)


def test_rolling_sum_window_and_scale():
    series = {"m1": 1.0, "m2": 2.0, "m3": 3.0, "m4": 4.0}
    out = v.apply_op({"op": "rolling_sum", "window": 3, "scale": 0.001}, series, {})
    # first complete window ends at m3; earlier dates dropped
    assert out == {"m3": pytest.approx(0.006), "m4": pytest.approx(0.009)}


def test_apply_op_unresolved_ref_raises():
    with pytest.raises(ValueError, match="ratio references unresolved series"):
        v.apply_op({"op": "ratio", "numerator": "a", "denominator": "b"}, {}, {"a": {}})


# ---------------------------------------------------------------------------
# full spec resolution
# ---------------------------------------------------------------------------

def _ratio_spec():
    return {
        "id": "t.share", "title": "t", "format": "pct",
        "series": [
            {"key": "fa", "label": "fa", "source": "evds", "locator": {"code": "FA"}},
            {"key": "ta", "label": "ta", "source": "evds", "locator": {"code": "TA"}},
            {"key": "share", "label": "share", "source": "derived",
             "transform": [{"op": "ratio", "numerator": "fa", "denominator": "ta"}]},
        ],
        "verify": [{"series": "share", "date": "2026-03", "value": 50.0, "tolerance": 0.5, "tolerance_unit": "pp"}],
    }


def test_resolve_spec_ratio_pipeline():
    runner = FakeRunner({"FA": [("2026-03", 50.0)], "TA": [("2026-03", 100.0)]})
    resolved = v.resolve_spec(_ratio_spec(), runner)
    assert resolved["share"] == {"2026-03": 50.0}


def test_resolve_spec_forward_ref_raises():
    # 'first' references 'second' which is declared later → not yet resolved.
    spec = {
        "id": "t.fwd", "title": "t", "format": "raw",
        "series": [
            {"key": "first", "label": "f", "source": "derived",
             "transform": [{"op": "sum_series", "keys": ["second"]}]},
            {"key": "second", "label": "s", "source": "evds", "locator": {"code": "S"}},
        ],
        "verify": [{"series": "first", "date": "2026-01", "value": 1.0}],
    }
    with pytest.raises(ValueError, match="unresolved series 'second'"):
        v.resolve_spec(spec, FakeRunner({"S": [("2026-01", 1.0)]}))


def test_check_spec_pass_and_blank_and_missing():
    spec = _ratio_spec()
    spec["registry_additions"] = [{"code": "FA", "label": "x"}, {"code": "GONE", "label": "y"}]
    # FA/TA present → share passes; GONE absent → WARN.
    runner = FakeRunner({"FA": [("2026-03", 50.0)], "TA": [("2026-03", 100.0)]})
    rows = v.check_spec(spec, runner)
    statuses = {(s, lbl.split("@")[0]) for s, lbl, _ in rows}
    assert ("PASS", "t.share/share") in statuses
    assert any(s == "WARN" and "GONE" in lbl for s, lbl, _ in rows)

    # Now TA missing → ratio resolves to {} → BLANK fail.
    runner2 = FakeRunner({"FA": [("2026-03", 50.0)]})
    rows2 = v.check_spec(spec, runner2)
    assert any(s == "FAIL" and "BLANK" in det for s, _, det in rows2)


# ---------------------------------------------------------------------------
# tolerance + point selection
# ---------------------------------------------------------------------------

def test_within_tolerance_abs_pp_pct():
    assert v.within_tolerance(100.4, 100.0, 0.5, "abs")
    assert not v.within_tolerance(101.0, 100.0, 0.5, "abs")
    assert v.within_tolerance(4.1, 4.0, 0.2, "pp")
    assert v.within_tolerance(105.0, 100.0, 5.0, "pct")     # 5 <= 100*5/100
    assert not v.within_tolerance(105.0, 100.0, 4.0, "pct")


def test_default_tol_unit():
    assert v.default_tol_unit({"format": "pct"}, {}) == "pp"
    assert v.default_tol_unit({"format": "bn"}, {}) == "abs"
    assert v.default_tol_unit({"format": "pct"}, {"tolerance_unit": "pct"}) == "pct"


def test_pick_point_prefix_and_last_and_none():
    series = {"2026-03-01": 1.0, "2026-03-31": 2.0, "2026-04-15": 3.0}
    assert v.pick_point(series, "2026-03") == ("2026-03-31", 2.0)  # last in March
    assert v.pick_point(series, "2026-04-15") == ("2026-04-15", 3.0)
    assert v.pick_point(series, "2025") is None


# ---------------------------------------------------------------------------
# validation + inliner + bank-type namespaces
# ---------------------------------------------------------------------------

def test_validate_spec_catches_bad_refs_and_missing_locator():
    spec = {
        "id": "t.bad", "title": "t",
        "series": [
            {"key": "a", "label": "a", "source": "evds"},  # missing locator
            {"key": "b", "label": "b", "source": "derived",
             "transform": [{"op": "ratio", "numerator": "a", "denominator": "ghost"}]},
        ],
        "verify": [{"series": "nope", "date": "x", "value": 1}],
    }
    errs = " ".join(v.validate_spec(spec))
    assert "needs a locator" in errs
    assert "references unknown series 'ghost'" in errs
    assert "verify point references unknown series 'nope'" in errs


def test_inline_quotes_and_numbers():
    assert v._inline("code = ? AND y >= ?", ["TP.X", 8]) == "code = 'TP.X' AND y >= 8"
    assert v._inline("n = ?", ["O'Brien"]) == "n = 'O''Brien'"
    with pytest.raises(ValueError, match="placeholder/param mismatch"):
        v._inline("a = ?", [])


def test_bank_type_namespaces_match_metrics_ts():
    # The collision this whole design defends: same numbers, different groups.
    assert bt.MONTHLY["PRIVATE"] == "10005"
    assert bt.MONTHLY["STATE"] == "10006"
    assert bt.MONTHLY["PARTICIPATION"] == "10003"
    assert bt.WEEKLY["PRIVATE"] == "10003"
    assert bt.WEEKLY["STATE"] == "10004"
    assert bt.WEEKLY["PARTICIPATION"] == "10006"
    # 10004 means Dev&Inv monthly but State weekly — must never be confused.
    assert bt.MONTHLY["DEV_INV"] == "10004" and bt.WEEKLY["STATE"] == "10004"


def test_resolve_codes_namespacing_and_errors():
    assert v.resolve_codes("bddk_monthly", ["STATE"]) == ["10006"]
    assert v.resolve_codes("bddk_weekly", ["STATE"]) == ["10004"]
    with pytest.raises(ValueError, match="unknown bank type"):
        v.resolve_codes("bddk_monthly", ["NOPE"])
    with pytest.raises(ValueError, match="no bank-type namespace"):
        v.resolve_codes("evds", ["SECTOR"])
