"""Tests for the §4 market-risk lane (FX net open position + interest-rate
repricing gap).

The validator tests are pure (stdlib only) and run everywhere, including CI
(which installs only ruff/pytest/lxml/requests). The extractor tests need
fitz (PyMuPDF) and the local diagnostic PDFs under data/eye/, so they
`importorskip` and skip when it is absent.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.audit_reports.repricing import _NONINT_RX  # noqa: E402
from src.audit_reports.validator import check_fx_position, check_repricing  # noqa: E402


# ---------------------------------------------------------------------------
# Repricing table locator — the non-interest-bearing column header (pure regex,
# runs in CI). This header is what pins the interest-rate repricing schedule
# apart from the FX table; if it doesn't match, the table is never located and
# the bank drops to a false N/A.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("header", [
    "Faizsiz",                 # standard Turkish
    "Faiz Getirmeyen",         # Turkish variant
    "Non-Interest Bearing",    # standard English
    "Non-Interest",            # English, header split
    "Non-bearing interest",    # Halkbank English (reversed word order) — regressed all 17 quarters to N/A
    " Non-bearing",            # as fitz clusters Halkbank's header line
    "Interest-Free",           # English variant
])
def test_nonint_header_matches_known_phrasings(header):
    assert _NONINT_RX.search(header), header


@pytest.mark.parametrize("not_header", [
    "Interest bearing assets",  # the OPPOSITE column — must NOT match
    "Total interest income",
    "Faiz oranı riski",         # prose section heading
])
def test_nonint_header_rejects_non_matches(not_header):
    assert not _NONINT_RX.search(not_header), not_header


# ---------------------------------------------------------------------------
# Validator footing logic (pure — runs in CI)
# ---------------------------------------------------------------------------
def _fx_rows(net_off_total=2000.0):
    """A well-formed currency-risk set: EUR + USD + OTHER = TOTAL on every field,
    net_on = assets − liab, net_position = net_on + net_off."""
    base = [
        ("EUR", 300.0, 200.0, -50.0),
        ("USD", 500.0, 700.0, 1000.0),
        ("OTHER", 200.0, 100.0, 1050.0),
    ]
    rows = []
    tot_a = tot_l = tot_non = tot_noff = 0.0
    for ccy, a, l, noff in base:
        non = a - l
        rows.append(dict(period_type="current", currency=ccy, on_bs_assets=a,
                         on_bs_liab=l, net_on_balance=non, net_off_balance=noff,
                         net_position=non + noff))
        tot_a += a; tot_l += l; tot_non += non; tot_noff += noff
    rows.append(dict(period_type="current", currency="TOTAL", on_bs_assets=tot_a,
                     on_bs_liab=tot_l, net_on_balance=tot_non,
                     net_off_balance=tot_noff, net_position=tot_non + tot_noff))
    return rows


def test_fx_validator_passes_on_wellformed():
    res = check_fx_position(_fx_rows())
    assert res.failed == 0 and res.passed > 0


def test_fx_validator_flags_broken_footing():
    rows = _fx_rows()
    # Corrupt a currency's assets so Σ != TOTAL.
    rows[0]["on_bs_assets"] += 9999.0
    res = check_fx_position(rows)
    assert res.failed > 0


def test_fx_validator_flags_broken_net_identity():
    rows = _fx_rows()
    rows[1]["net_on_balance"] += 9999.0  # net_on no longer = assets − liab
    res = check_fx_position(rows)
    assert res.failed > 0


def test_fx_validator_skips_without_total():
    rows = [r for r in _fx_rows() if r["currency"] != "TOTAL"]
    res = check_fx_position(rows)
    assert res.checked == 0 and res.skipped >= 1


def _rp_rows():
    """Well-formed repricing set: Σ buckets = total (RSA, RSL, gap); RSA=RSL total."""
    buckets = [
        ("lt_1m", 100.0, 150.0, -50.0),
        ("1_3m", 200.0, 120.0, 80.0),
        ("3_12m", 300.0, 100.0, 200.0),
        ("1_5y", 250.0, 80.0, 170.0),
        ("gt_5y", 90.0, 40.0, 50.0),
        ("non_sensitive", 60.0, 510.0, -450.0),
    ]
    rows, ta, tl, tg = [], 0.0, 0.0, 0.0
    for bk, a, l, g in buckets:
        rows.append(dict(period_type="current", bucket=bk, rate_sensitive_assets=a,
                         rate_sensitive_liab=l, gap=g, cumulative_gap=None))
        ta += a; tl += l; tg += g
    rows.append(dict(period_type="current", bucket="total", rate_sensitive_assets=ta,
                     rate_sensitive_liab=tl, gap=tg, cumulative_gap=None))
    return rows


def test_repricing_validator_passes_on_wellformed():
    res = check_repricing(_rp_rows())
    assert res.failed == 0 and res.passed > 0


def test_repricing_validator_flags_broken_footing():
    rows = _rp_rows()
    rows[2]["gap"] += 9999.0
    res = check_repricing(rows)
    assert res.failed > 0


def test_repricing_validator_skips_without_total():
    rows = [r for r in _rp_rows() if r["bucket"] != "total"]
    res = check_repricing(rows)
    assert res.checked == 0 and res.skipped >= 1


# ---------------------------------------------------------------------------
# Extractor tests (need fitz (PyMuPDF) + local sample PDFs — skip otherwise)
# ---------------------------------------------------------------------------
_SAMPLE = REPO / "data" / "eye" / "AKBNK_2024Q4_unconsolidated.pdf"


def _need_extractor():
    pytest.importorskip("fitz")
    if not _SAMPLE.exists():
        pytest.skip("sample PDF not present (local-only diagnostic fixture)")


def test_fx_extractor_on_sample():
    _need_extractor()
    from src.audit_reports.fx_position import extract
    rep = extract(_SAMPLE)
    cur = {r.currency: r for r in rep.rows if r.period_type == "current"}
    assert "TOTAL" in cur
    tot = cur["TOTAL"]
    # net position identity holds, and per-currency assets foot to TOTAL.
    assert abs((tot.net_on_balance + tot.net_off_balance) - tot.net_position) < 2.0
    s = sum(cur[c].on_bs_assets for c in cur if c != "TOTAL")
    assert abs(s - tot.on_bs_assets) < max(2.0, 0.005 * abs(tot.on_bs_assets))


def test_repricing_extractor_on_sample():
    _need_extractor()
    from src.audit_reports.repricing import extract
    rep = extract(_SAMPLE)
    cur = {r.bucket: r for r in rep.rows if r.period_type == "current"}
    assert "total" in cur and "lt_1m" in cur
    tot = cur["total"]
    sg = sum(cur[b].gap for b in cur if b != "total")
    assert abs(sg - tot.gap) < max(2.0, 0.01 * abs(tot.gap))
    # the schedule foots to the balance sheet (total RSA == total RSL).
    assert abs(tot.rate_sensitive_assets - tot.rate_sensitive_liab) < 2.0


# --- fx currency-header parsing: the TSKB "US Dollar" + YKBNK wrapped "FC" fixes ---
from src.audit_reports.fx_position import _parse_header_columns  # noqa: E402


def _hdr(*words):
    """Build a header line as (x, token) pairs, left-to-right."""
    return [(float(i), w) for i, w in enumerate(words)]


def test_fx_header_english_us_dollar():
    # TSKB files "... Euro US Dollar Other FC Total" — fitz splits "US Dollar" into
    # US + Dollar, so the parser keys on "US". Must still resolve 4 columns.
    cols = _parse_header_columns(
        _hdr("Current", "Period", "Euro", "US", "Dollar", "Other", "FC", "Total"))
    assert cols == ["EUR", "USD", "OTHER", "TOTAL"], cols


def test_fx_header_wrapped_other_fc():
    # YKBNK-unconsolidated wraps "Other" onto the line above, leaving "FC(4)" on the
    # header baseline — "FC" must resolve to OTHER.
    cols = _parse_header_columns(
        _hdr("Current", "Period", "EUR", "USD", "FC(4)", "Total"))
    assert cols == ["EUR", "USD", "OTHER", "TOTAL"], cols


def test_fx_header_turkish_unchanged():
    # The Turkish header must be unaffected by the new alternates.
    cols = _parse_header_columns(_hdr("EURO", "USD", "Diğer", "YP", "Toplam"))
    assert cols == ["EUR", "USD", "OTHER", "TOTAL"], cols


def test_fx_header_non_currency_rejected():
    # A Total-only header (no hard currency) must not false-match.
    assert _parse_header_columns(_hdr("Amount", "Total")) is None


# --- fx period-tag guard: a dual-period sensitivity header must NOT flip to prior ---
from src.audit_reports.fx_position import _PRIOR_RX, _CURRENT_RX  # noqa: E402


def test_fx_period_flip_only_on_standalone_prior():
    # A standalone prior-block caption flips; a dual-period sensitivity header
    # (names Current too) must be guarded so it does NOT flip.
    standalone = "Prior Period"
    dual = "exchange rate Current Period Prior Period Current Period Prior Period"
    assert _PRIOR_RX.search(standalone) and not _CURRENT_RX.search(standalone)
    assert _PRIOR_RX.search(dual) and _CURRENT_RX.search(dual)  # guarded → no flip


def test_fx_period_flip_turkish():
    assert _PRIOR_RX.search("Önceki Dönem") and not _CURRENT_RX.search("Önceki Dönem")
    assert _CURRENT_RX.search("Cari Dönem EURO USD Toplam")


# --- fx completeness: partial-extraction green cells must now fail ---
def _fxrow(currency, period_type="current", **kw):
    d = {"currency": currency, "period_type": period_type,
         "on_bs_assets": None, "on_bs_liab": None, "net_on_balance": None,
         "net_off_balance": None, "net_position": None}
    d.update(kw)
    return d


def test_fx_net_position_missing_fails():
    # GARAN pattern: only gross Assets/Liab captured, no net position → not verified.
    rows = [
        _fxrow("EUR", on_bs_assets=100, on_bs_liab=60),
        _fxrow("TOTAL", on_bs_assets=100, on_bs_liab=60),
    ]
    res = check_fx_position(rows)
    assert any(f["check"] == "fx_net_position_missing" for f in res.failures), res.failures


def test_fx_current_incomplete_dropped_off_balance_fails():
    # DENIZ pattern: current drops Net Off-Balance that the prior column carries.
    rows = [
        _fxrow("TOTAL", on_bs_assets=100, on_bs_liab=160, net_on_balance=-60,
               net_off_balance=None, net_position=-60),
        _fxrow("TOTAL", "prior", on_bs_assets=100, on_bs_liab=160, net_on_balance=-60,
               net_off_balance=62, net_position=2),
    ]
    res = check_fx_position(rows)
    assert any(f["check"] == "fx_current_incomplete" for f in res.failures), res.failures


def test_fx_genuine_no_off_balance_passes():
    # A bank with NO off-balance FX in BOTH columns is not incomplete — must not flag.
    rows = [
        _fxrow("EUR", on_bs_assets=100, on_bs_liab=60, net_on_balance=40,
               net_off_balance=None, net_position=40),
        _fxrow("TOTAL", on_bs_assets=100, on_bs_liab=60, net_on_balance=40,
               net_off_balance=None, net_position=40),
        _fxrow("EUR", "prior", on_bs_assets=90, on_bs_liab=55, net_on_balance=35,
               net_off_balance=None, net_position=35),
        _fxrow("TOTAL", "prior", on_bs_assets=90, on_bs_liab=55, net_on_balance=35,
               net_off_balance=None, net_position=35),
    ]
    res = check_fx_position(rows)
    assert not any(f["check"] in ("fx_net_position_missing", "fx_current_incomplete")
                   for f in res.failures), res.failures


def test_fx_current_missing_zero_prior_not_flagged():
    # ATBANK/DUNYAK pattern: prior net_off is 0 (genuinely no off-balance FX), so a
    # NULL current net_off is not a "dropped" value — must NOT flag.
    rows = [
        _fxrow("TOTAL", on_bs_assets=100, on_bs_liab=90, net_on_balance=10,
               net_off_balance=None, net_position=10),
        _fxrow("TOTAL", "prior", on_bs_assets=95, on_bs_liab=88, net_on_balance=7,
               net_off_balance=0.0, net_position=7),
    ]
    res = check_fx_position(rows)
    assert not any(f["check"] == "fx_current_incomplete" for f in res.failures), res.failures


def test_fx_prior_incomplete_dropped_off_balance_fails():
    # TSKB pattern: the PRIOR column drops Net Off-Balance that the current column
    # carries → prior net_position collapses to net_on only (sign-flipped), which
    # every within-column identity still accepts. The symmetric check catches it.
    rows = [
        _fxrow("TOTAL", on_bs_assets=140, on_bs_liab=151, net_on_balance=-11,
               net_off_balance=12, net_position=1),
        _fxrow("TOTAL", "prior", on_bs_assets=91, on_bs_liab=100, net_on_balance=-9,
               net_off_balance=None, net_position=-9),
    ]
    res = check_fx_position(rows)
    assert any(f["check"] == "fx_prior_incomplete" for f in res.failures), res.failures
    # …and it is NOT mislabelled as a current-column drop.
    assert not any(f["check"] == "fx_current_incomplete" for f in res.failures), res.failures


def test_fx_cross_period_divergence_fails():
    # The prior column re-prints the prior year-end; disagreeing with that year-end's
    # independently-extracted current TOTAL is the external anchor (both columns here
    # are complete, so this is a genuine value divergence, not a drop).
    rows = [
        _fxrow("TOTAL", on_bs_assets=100, on_bs_liab=60, net_on_balance=40,
               net_off_balance=5, net_position=45),
        _fxrow("TOTAL", "prior", on_bs_assets=90, on_bs_liab=55, net_on_balance=35,
               net_off_balance=6, net_position=41),
    ]
    res = check_fx_position(rows, prior_ye_totals={"net_position": 25.0})
    assert any(f["check"] == "fx_cross_period" for f in res.failures), res.failures


def test_fx_cross_period_matching_year_end_passes():
    # Prior column == prior year-end current → the anchor is satisfied, no flag.
    rows = [
        _fxrow("TOTAL", on_bs_assets=100, on_bs_liab=60, net_on_balance=40,
               net_off_balance=5, net_position=45),
        _fxrow("TOTAL", "prior", on_bs_assets=90, on_bs_liab=55, net_on_balance=35,
               net_off_balance=6, net_position=41),
    ]
    res = check_fx_position(rows, prior_ye_totals={"net_position": 41.0})
    assert not any(f["check"] == "fx_cross_period" for f in res.failures), res.failures


def test_fx_cross_period_skips_when_prior_incomplete():
    # When the prior column dropped net_off, its net_position is unreliable — the
    # cross-period anchor must NOT double-flag (fx_prior_incomplete owns it).
    rows = [
        _fxrow("TOTAL", on_bs_assets=140, on_bs_liab=151, net_on_balance=-11,
               net_off_balance=12, net_position=1),
        _fxrow("TOTAL", "prior", on_bs_assets=91, on_bs_liab=100, net_on_balance=-9,
               net_off_balance=None, net_position=-9),
    ]
    res = check_fx_position(rows, prior_ye_totals={"net_position": 1.0})
    assert not any(f["check"] == "fx_cross_period" for f in res.failures), res.failures


def test_fx_cross_period_no_anchor_no_flag():
    # First-year partition (no prior year-end supplied) → the anchor simply doesn't run.
    res = check_fx_position(_fx_rows(), prior_ye_totals=None)
    assert not any(f["check"] == "fx_cross_period" for f in res.failures), res.failures


def test_fx_cross_period_catches_symmetric_net_off_drop():
    # BURGAN pattern: the net_off row is dropped from BOTH columns, so the
    # symmetric completeness check sees no asymmetry — only the cross-period read
    # against the year-end (which DID carry a net_off) exposes the collapsed
    # net_position. The anchor must not be gated on prior net_off being present.
    rows = [
        _fxrow("TOTAL", on_bs_assets=91, on_bs_liab=117, net_on_balance=-25,
               net_off_balance=None, net_position=-25),
        _fxrow("TOTAL", "prior", on_bs_assets=76, on_bs_liab=103, net_on_balance=-27,
               net_off_balance=None, net_position=-27),
    ]
    # prior year-end carried a real net_off → its net position was ~-1.75.
    res = check_fx_position(rows, prior_ye_totals={"net_position": -1.75})
    assert any(f["check"] == "fx_cross_period" for f in res.failures), res.failures
    # completeness (symmetric) correctly stays silent — nothing to compare within.
    assert not any(f["check"] in ("fx_current_incomplete", "fx_prior_incomplete")
                   for f in res.failures), res.failures
