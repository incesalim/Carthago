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
