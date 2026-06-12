"""Verify reproduced charts against live data — the regression check that turns
"eyeball once" into "alerts forever".

For every spec in the chart-spec catalog (web/app/lib/chart-specs.catalog.json):
  1. resolve each series from the DB (remote D1 by default, or a local SQLite
     snapshot with --db),
  2. apply the spec's declarative transforms (scale / sum_series / ratio /
     growth / derive-AST),
  3. assert each verify[] point matches the stored value within tolerance.

It flags three failure classes loudly:
  • BLANK   — a series resolved to 0 rows (the silent-blank bug that wiped the
              /credit charts and the monthly EVDS series),
  • MISMATCH — a verify point drifted beyond tolerance (prints actual vs expected),
  • MISSING — a registry_additions EVDS code is absent from evds_series.

Conventions mirror scripts/check_audit_quality.py: prints a PASS/FAIL table,
alerts via scripts/notify.py with --alert, and exits 0 (alert IS the signal)
unless --strict is passed.

Usage:
    python scripts/verify_chart_spec.py                 # remote D1 (default)
    python scripts/verify_chart_spec.py --db data/bddk_data.db   # local snapshot
    python scripts/verify_chart_spec.py --alert         # cron: notify on failure
    python scripts/verify_chart_spec.py --strict        # exit nonzero on failure
    python scripts/verify_chart_spec.py --only liquidity.net_cbrt_funding

Env (remote mode): CLOUDFLARE_API_TOKEN (wrangler picks it up automatically).
Stdlib only — safe to import under the minimal-deps CI (ruff/pytest/lxml/requests).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DEFAULT_CATALOG = WEB / "app" / "lib" / "chart-specs.catalog.json"
DEFAULT_DB = ROOT / "data" / "bddk_data.db"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bank_types import resolve_codes  # noqa: E402

try:  # notify is optional — a no-op printer if the module/secrets are absent
    from notify import notify
except Exception:  # pragma: no cover
    def notify(text: str) -> bool:
        print(f"[notify] {text}", file=sys.stderr)
        return False

# Column allow-lists per monthly table — column names can't be bound as SQL
# params, so they must be validated against a fixed set (injection guard).
MONTHLY_COLUMNS: dict[str, set[str]] = {
    "balance_sheet": {"amount_total", "amount_tl", "amount_fx"},
    "loans": {"total_amount", "total_tl", "total_fx", "npl_amount"},
    "deposits": {
        "total_amount", "demand", "maturity_1m", "maturity_1_3m",
        "maturity_3_6m", "maturity_6_12m", "maturity_over_12m",
    },
    "financial_ratios": {"ratio_value"},
    "income_statement": {"amount_total", "amount_tl", "amount_fx"},
}

_AST_OPS = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div": lambda a, b: (a / b) if b not in (0, 0.0) else None,
}


# ---------------------------------------------------------------------------
# DB runners — same SQL (with ? placeholders), two backends.
# ---------------------------------------------------------------------------

class LocalRunner:
    """Query a local SQLite snapshot (e.g. data/bddk_data.db)."""

    def __init__(self, db_path: Path):
        import sqlite3
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.label = f"local:{db_path.name}"

    def query(self, sql: str, params: list) -> list[dict]:
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


class RemoteRunner:
    """Query remote Cloudflare D1 via wrangler (mirrors healthcheck.query_d1)."""

    label = "remote:D1"

    def query(self, sql: str, params: list) -> list[dict]:
        inlined = _inline(sql, params)
        cmd = [
            "npx", "--yes", "wrangler", "d1", "execute", "bddk-data",
            "--remote", "--json", "--command", inlined,
        ]
        res = subprocess.run(
            cmd, cwd=str(WEB), capture_output=True, text=True,
            shell=os.name == "nt",
        )
        if res.returncode != 0:
            raise RuntimeError(f"wrangler exit {res.returncode}: {res.stderr[-400:]}")
        data = json.loads(res.stdout)
        return (data[0] if isinstance(data, list) else data)["results"]


def _inline(sql: str, params: list) -> str:
    """Substitute ? placeholders with quoted literals (for wrangler --command,
    which has no parameter binding). Numbers inline raw; strings are single-
    quoted with '' escaping."""
    parts = sql.split("?")
    if len(parts) - 1 != len(params):
        raise ValueError(f"placeholder/param mismatch: {len(parts)-1} vs {len(params)}")
    out = [parts[0]]
    for part, v in zip(parts[1:], params):
        if isinstance(v, bool):
            out.append("1" if v else "0")
        elif isinstance(v, (int, float)):
            out.append(repr(v))
        else:
            out.append("'" + str(v).replace("'", "''") + "'")
        out.append(part)
    return "".join(out)


# ---------------------------------------------------------------------------
# Series resolution — each returns {date: value} for ONE series.
# ---------------------------------------------------------------------------

def _bank_code(source: str, loc: dict) -> str:
    """Resolve a single bank-type code from a locator, preferring the safe
    bank_types_named form. A spec series must resolve to one value per date."""
    if loc.get("bank_types_named"):
        codes = resolve_codes(source, loc["bank_types_named"])
    elif loc.get("bank_types_raw"):
        codes = list(loc["bank_types_raw"])
    else:
        raise ValueError(f"{source} locator needs bank_types_named (or bank_types_raw)")
    if len(codes) != 1:
        raise ValueError(
            f"{source} spec series must select exactly one bank type, got {codes}"
        )
    return codes[0]


def resolve_evds(loc: dict, runner) -> dict[str, float]:
    rows = runner.query(
        "SELECT period_date AS d, value AS v FROM evds_series "
        "WHERE code = ? AND value IS NOT NULL "
        "AND period_date >= date('now', '-' || ? || ' years') "
        "ORDER BY period_date",
        [loc["code"], int(loc.get("years_back", 8))],
    )
    return {r["d"]: r["v"] for r in rows if r["v"] is not None}


def resolve_monthly(loc: dict, runner) -> dict[str, float]:
    table = loc["table"]
    column = loc["column"]
    if table not in MONTHLY_COLUMNS or column not in MONTHLY_COLUMNS[table]:
        raise ValueError(f"unsupported table/column: {table}.{column}")
    code = _bank_code("bddk_monthly", loc)

    if table == "financial_ratios":
        value_expr = "ratio_value * 12.0 / month" if loc.get("annualize") else "ratio_value"
        rows = runner.query(
            f"SELECT year || '-' || PRINTF('%02d', month) AS d, {value_expr} AS v "
            "FROM financial_ratios "
            "WHERE table_number = ? AND item_name = ? AND bank_type_code = ? "
            "ORDER BY year, month",
            [int(loc.get("table_number", 15)), loc["item_name"], code],
        )
    elif "item_orders" in loc:
        # Positional selection, SUMMED per period — for tables whose row labels
        # are unstable but whose item_order positions are fixed (e.g. the
        # income_statement interest buckets). Orders can't be bound one-by-one
        # into IN(...) portably with the wrangler inliner, so validate them as
        # ints and inline (injection guard).
        orders = loc["item_orders"]
        if not orders or not all(isinstance(o, int) and not isinstance(o, bool) for o in orders):
            raise ValueError(f"item_orders must be a non-empty list of ints, got {orders!r}")
        in_list = ",".join(str(o) for o in orders)
        rows = runner.query(
            f"SELECT year || '-' || PRINTF('%02d', month) AS d, SUM({column}) AS v "
            f"FROM {table} "
            f"WHERE item_order IN ({in_list}) AND currency = ? AND bank_type_code = ? "
            "GROUP BY year, month ORDER BY year, month",
            [loc.get("currency", "TL"), code],
        )
    else:
        rows = runner.query(
            f"SELECT year || '-' || PRINTF('%02d', month) AS d, {column} AS v "
            f"FROM {table} "
            "WHERE item_name = ? AND currency = ? AND bank_type_code = ? "
            "ORDER BY year, month",
            [loc["item_name"], loc.get("currency", "TL"), code],
        )
    return {r["d"]: r["v"] for r in rows if r["v"] is not None}


def resolve_weekly(loc: dict, runner) -> dict[str, float]:
    code = _bank_code("bddk_weekly", loc)
    rows = runner.query(
        "SELECT period_date AS d, value AS v FROM weekly_series "
        "WHERE category = ? AND item_id = ? AND currency = ? AND bank_type_code = ? "
        "ORDER BY period_date",
        [loc["category"], loc["item_id"], loc.get("currency", "TOTAL"), code],
    )
    return {r["d"]: r["v"] for r in rows if r["v"] is not None}


_RESOLVERS = {
    "evds": resolve_evds,
    "bddk_monthly": resolve_monthly,
    "bddk_weekly": resolve_weekly,
}


# ---------------------------------------------------------------------------
# Transform engine (mirror of the TS engine; kept honest by verify[] points).
# ---------------------------------------------------------------------------

def eval_formula(node: dict, resolved: dict[str, dict]):
    """Walk a derive AST. Returns a {date: value} dict or a scalar (const).
    Refs may only name an already-resolved sibling series — forward refs,
    self-refs and cycles raise. No eval/Function: data, not code."""
    if not isinstance(node, dict):
        raise ValueError(f"formula node must be an object, got {node!r}")
    if "ref" in node:
        key = node["ref"]
        if key not in resolved:
            raise ValueError(f"derive references unresolved/unknown series {key!r}")
        return resolved[key]
    if "const" in node:
        return float(node["const"])
    if "op" in node:
        if node["op"] not in _AST_OPS:
            raise ValueError(f"unknown formula op {node['op']!r}")
        args = node.get("args")
        if not isinstance(args, list) or len(args) != 2:
            raise ValueError("formula op needs exactly 2 args")
        return _binop(node["op"], eval_formula(args[0], resolved), eval_formula(args[1], resolved))
    raise ValueError(f"invalid formula node {node!r}")


def _binop(op: str, a, b) -> dict | float:
    fn = _AST_OPS[op]
    a_series, b_series = isinstance(a, dict), isinstance(b, dict)
    if not a_series and not b_series:
        return fn(a, b)
    if a_series and b_series:
        out = {}
        for d in a.keys() & b.keys():
            r = fn(a[d], b[d])
            if r is not None:
                out[d] = r
        return out
    if a_series:
        return {d: r for d in a if (r := fn(a[d], b)) is not None}
    return {d: r for d in b if (r := fn(a, b[d])) is not None}


def apply_op(op: dict, cur: dict[str, float], resolved: dict[str, dict]) -> dict[str, float]:
    """Apply one transform op to the current series, with sibling refs resolving
    to already-finalized series."""
    kind = op["op"]
    if kind == "scale":
        f = op["factor"]
        return {d: v * f for d, v in cur.items()}
    if kind == "sum_series":
        out: dict[str, float] = {}
        for key in op["keys"]:
            if key not in resolved:
                raise ValueError(f"sum_series references unresolved series {key!r}")
            for d, v in resolved[key].items():
                out[d] = out.get(d, 0.0) + v
        return out
    if kind == "ratio":
        num, den = op["numerator"], op["denominator"]
        for k in (num, den):
            if k not in resolved:
                raise ValueError(f"ratio references unresolved series {k!r}")
        scale = op.get("scale", 100)
        n, d_ = resolved[num], resolved[den]
        return {
            dt: n[dt] / d_[dt] * scale
            for dt in n.keys() & d_.keys()
            if d_[dt] not in (0, 0.0)
        }
    if kind == "growth":
        return _growth(cur, int(op["window"]), op["mode"])
    if kind == "rolling_sum":
        # Trailing sum over `window` observations (e.g. 12m rolling current
        # account), optionally scaled — mirrors economy.ts rollingSum().
        window = int(op["window"])
        scale = op.get("scale", 1)
        dates = sorted(cur)
        out: dict[str, float] = {}
        for i in range(window - 1, len(dates)):
            out[dates[i]] = sum(cur[d] for d in dates[i - window + 1 : i + 1]) * scale
        return out
    if kind == "derive":
        result = eval_formula(op["formula"], resolved)
        if not isinstance(result, dict):
            raise ValueError("derive formula produced a scalar (needs at least one ref)")
        return result
    raise ValueError(f"unknown transform op {kind!r}")


def _growth(series: dict[str, float], window: int, mode: str) -> dict[str, float]:
    """Rolling growth over `window` positions. 'yoy' = simple (v/prev-1); the
    metrics.ts weeklyGrowth annualization uses exponent 52/window."""
    dates = sorted(series)
    exponent = 1.0 if mode == "yoy" else 52.0 / window
    out: dict[str, float] = {}
    for i in range(window, len(dates)):
        prev = series[dates[i - window]]
        cur = series[dates[i]]
        if prev and prev > 0:
            out[dates[i]] = ((cur / prev) ** exponent - 1) * 100
    return out


def resolve_spec(spec: dict, runner) -> dict[str, dict[str, float]]:
    """Resolve every series in a spec to {date: value}. Non-derived series are
    fetched then transformed in listed order; refs resolve to already-finalized
    siblings (so order matters and cycles are impossible)."""
    resolved: dict[str, dict[str, float]] = {}
    for s in spec["series"]:
        if s["source"] == "derived":
            cur: dict[str, float] = {}
        else:
            resolver = _RESOLVERS.get(s["source"])
            if resolver is None:
                raise ValueError(f"unknown series source {s['source']!r}")
            cur = resolver(s["locator"], runner)
        for op in s.get("transform", []):
            cur = apply_op(op, cur, resolved)
        resolved[s["key"]] = cur
    return resolved


# ---------------------------------------------------------------------------
# Verify points
# ---------------------------------------------------------------------------

def pick_point(series: dict[str, float], date_prefix: str):
    """Last point whose date starts with the prefix; None if no match."""
    matches = sorted(d for d in series if d.startswith(date_prefix))
    return (matches[-1], series[matches[-1]]) if matches else None


def within_tolerance(actual: float, expected: float, tol: float, unit: str) -> bool:
    if unit == "pct":
        return abs(actual - expected) <= abs(expected) * tol / 100.0
    return abs(actual - expected) <= tol  # abs / pp are both absolute deltas


def default_tol_unit(spec: dict, point: dict) -> str:
    if point.get("tolerance_unit"):
        return point["tolerance_unit"]
    return "pp" if spec.get("format") == "pct" else "abs"


# ---------------------------------------------------------------------------
# Structural validation (stdlib — no jsonschema dependency)
# ---------------------------------------------------------------------------

def validate_spec(spec: dict) -> list[str]:
    """Return a list of structural errors (empty = ok). Catches the mistakes the
    JSON-Schema describes but that we can't rely on jsonschema to enforce here."""
    errs: list[str] = []
    for field in ("id", "title", "series", "verify"):
        if field not in spec:
            errs.append(f"missing required field {field!r}")
    keys = {s.get("key") for s in spec.get("series", [])}
    for s in spec.get("series", []):
        if s.get("source") != "derived" and "locator" not in s:
            errs.append(f"series {s.get('key')!r} needs a locator")
        for op in s.get("transform", []):
            for ref in _op_refs(op):
                if ref not in keys:
                    errs.append(f"transform in {s.get('key')!r} references unknown series {ref!r}")
    for v in spec.get("verify", []):
        if v.get("series") not in keys:
            errs.append(f"verify point references unknown series {v.get('series')!r}")
    return errs


def _op_refs(op: dict) -> list[str]:
    kind = op.get("op")
    if kind == "sum_series":
        return list(op.get("keys", []))
    if kind == "ratio":
        return [op.get("numerator"), op.get("denominator")]
    if kind == "derive":
        return _formula_refs(op.get("formula", {}))
    return []


def _formula_refs(node: dict) -> list[str]:
    if not isinstance(node, dict):
        return []
    if "ref" in node:
        return [node["ref"]]
    if "op" in node:
        out: list[str] = []
        for a in node.get("args", []):
            out.extend(_formula_refs(a))
        return out
    return []


# ---------------------------------------------------------------------------
# Runner over the whole catalog
# ---------------------------------------------------------------------------

def check_spec(spec: dict, runner) -> list[tuple[str, str, str]]:
    """Return rows of (status, label, detail). status in PASS/FAIL/WARN."""
    rows: list[tuple[str, str, str]] = []
    errs = validate_spec(spec)
    if errs:
        for e in errs:
            rows.append(("FAIL", spec.get("id", "?"), f"invalid spec: {e}"))
        return rows

    sid = spec["id"]
    try:
        resolved = resolve_spec(spec, runner)
    except Exception as e:
        rows.append(("FAIL", sid, f"resolve error: {type(e).__name__}: {e}"))
        return rows

    for v in spec["verify"]:
        series = resolved.get(v["series"], {})
        label = f"{sid}/{v['series']}@{v['date']}"
        if not series:
            rows.append(("FAIL", label, "BLANK: 0 rows resolved"))
            continue
        hit = pick_point(series, v["date"])
        if hit is None:
            rows.append(("FAIL", label, f"no point matching date {v['date']!r}"))
            continue
        matched_date, actual = hit
        unit = default_tol_unit(spec, v)
        tol = v.get("tolerance", 0.5)
        ok = within_tolerance(actual, v["value"], tol, unit)
        detail = f"actual={actual:.4g} expected={v['value']:.4g} (±{tol}{unit}, @{matched_date})"
        rows.append(("PASS" if ok else "FAIL", label, ("" if ok else "MISMATCH ") + detail))

    # Soft check: referenced EVDS registry codes present in the DB.
    for add in spec.get("registry_additions", []):
        code = add["code"]
        try:
            n = runner.query(
                "SELECT COUNT(*) AS n FROM evds_series WHERE code = ?", [code]
            )[0]["n"]
        except Exception:
            n = 0
        if not n:
            rows.append(("WARN", f"{sid}:{code}", "MISSING from evds_series (add to evds_scraper.py SERIES)"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=str, default=None,
                    help="Query a local SQLite snapshot instead of remote D1.")
    ap.add_argument("--catalog", type=str, default=str(DEFAULT_CATALOG))
    ap.add_argument("--only", type=str, default=None, help="Only this spec id.")
    ap.add_argument("--alert", action="store_true", help="Notify on FAIL via notify.py.")
    ap.add_argument("--strict", action="store_true", help="Exit nonzero on any FAIL.")
    args = ap.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        print(f"ERROR: catalog {catalog_path} not found", file=sys.stderr)
        return 2
    specs = json.loads(catalog_path.read_text(encoding="utf-8"))
    if args.only:
        specs = [s for s in specs if s.get("id") == args.only]
        if not specs:
            print(f"ERROR: no spec with id {args.only!r}", file=sys.stderr)
            return 2

    if args.db:
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"ERROR: db {db_path} not found", file=sys.stderr)
            return 2
        runner = LocalRunner(db_path)
    else:
        runner = RemoteRunner()

    print(f"verifying {len(specs)} chart spec(s) against {runner.label}\n")
    all_rows: list[tuple[str, str, str]] = []
    for spec in specs:
        all_rows.extend(check_spec(spec, runner))

    width = max((len(r[1]) for r in all_rows), default=10)
    for status, label, detail in all_rows:
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "!"}[status]
        print(f"  {icon} {status:4} {label:{width}}  {detail}")

    fails = [r for r in all_rows if r[0] == "FAIL"]
    warns = [r for r in all_rows if r[0] == "WARN"]
    passes = [r for r in all_rows if r[0] == "PASS"]
    print(f"\n{len(passes)} pass · {len(fails)} fail · {len(warns)} warn")

    if fails and args.alert:
        lines = [f"⚠️ chart-spec verify: {len(fails)} failing point(s) on {runner.label}"]
        lines += [f"  ✗ {lbl}: {det}" for _, lbl, det in fails[:15]]
        notify("\n".join(lines))

    return 1 if (fails and args.strict) else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
