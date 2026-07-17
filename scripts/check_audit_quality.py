"""Post-extraction data-quality checks for the bank-audit tables.

Catches the kind of silent extraction error the Eximbank 3-period / 4-column
layout produced (the prior period stored as the current one), so a format change
on a bank's report pings us the same week instead of being found by hand months
later. Runs against the standalone audit SQLite after extraction.

Checks (each yields offending (bank, period, kind)):
  1. stale_period — a quarter whose balance-sheet line items are almost all
                    IDENTICAL to the immediately prior quarter. A real quarter
                    moves nearly every number; ~100% identical means the prior
                    period was stored as current (the exact Eximbank fingerprint).
                    Total-row-independent, so it's robust even for banks whose
                    grand-total row isn't cleanly captured.
  2. balance     — where both labelled grand totals are present: total assets
                    must equal total liabilities; >0.5% off is a column grab.
                    Skipped (not failed) when a total row isn't identifiable.
  3. coverage    — an extracted (bank, period, kind) missing assets /
                    liabilities / P&L rows (or far below a sane minimum).
  4. npl_drop    — a quarter whose Stage-3 NPL ratio crashes from a real level
                    (>=1%) to ~0 (<0.1%). Fingerprint of the Stage-3 extractor
                    grabbing an FC-only / fragment sub-table instead of the
                    total III/IV/V NPL classification (the DENIZ/FIBA 2026Q1 bug).
  5. capital     — bank_audit_capital arithmetic: CET1<=Tier1<=Total Capital and
                    reported CAR must reconcile to Total Capital / RWA. A failure
                    is a parse error (missing label variant / wrong total row).
  6. liquidity   — bank_audit_liquidity plausibility bands (leverage <30%,
                    LCR/NSFR sane; a sub-50% LCR is a mis-grabbed value).
  7. structure   — bank_audit_validation partitions with failed internal-sum
                    identities (TL+FC=Total per row, parent=Σchildren,
                    TOTAL=Σromans, assets=liabilities+equity). Written at
                    extraction time by src/audit_reports/validator.py.
  8. ecl         — Expected Credit Losses balance-sheet rows: a truncated label
                    ("…Losses(") or a tiny |amount| on a large bank are
                    fingerprints of the dipnot-ref "(6)" being read as the value
                    (the ALBRK -6 bug); a quarter that LOSES its ECL rows while
                    the prior quarter had them is the row-drop variant.
  9. pl_sign     — P&L deduction romans (II, IX–XII) whose stored sign flips
                    within a bank/kind series. The chain check accepts either
                    storage convention by design, so flips are invisible to it;
                    they break YTD de-cumulation downstream unless abs()'d.
 10. freeprov    — bank_audit_free_provision (serbest karşılık stock): a plausibility
                    band, a longitudinal cross-check (stated prior == prior-year-end
                    current), and a two-sided reconciliation against the audit
                    opinion — qualified-over-free-provision ⇒ a value must exist
                    (recall), a value under a clean opinion ⇒ verify it isn't a
                    cancelled amount read as the stock (precision).

Alert-only / non-blocking: prints a report and (with --alert) sends one
Telegram/Discord summary via scripts/notify.py, then always exits 0 so it never
stops the pipeline. --strict exits non-zero on anomalies (handy locally / tests).

  python scripts/check_audit_quality.py --db data/bank_audit.db
  python scripts/check_audit_quality.py --db data/bank_audit.db --alert
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

# Reuse the validator's canonical grand-total / Σ-romans logic so the off-balance
# vertical check can't drift from the BS one.
from src.audit_reports.validator import _statement_total  # noqa: E402

BALANCE_TOL = 0.005       # 0.5%
DUP_FRACTION = 0.95       # >=95% of line items identical to prior quarter
DUP_MIN_ROWS = 15         # need enough comparable rows to trust the fraction
MIN_ASSET_ROWS = 15
MIN_PL_ROWS = 15
# NPL-collapse check: a Stage-3 gross that falls from a real level to ~zero
# between consecutive quarters is the fingerprint of the extractor grabbing an
# FC-only / fragment sub-table instead of the total NPL classification (the
# DENIZ/FIBA 2026Q1 bug: ~5% NPL read as ~0%). Require the PRIOR quarter to be a
# genuine NPL so we never flag banks that are simply low-NPL every quarter
# (ATBANK/ICBCT sit at ~0% legitimately).
NPL_COLLAPSE_PRIOR_MIN = 0.01   # prior-quarter NPL ratio >= 1%
NPL_COLLAPSE_CUR_MAX = 0.001    # current-quarter NPL ratio < 0.1%
# Off-balance vertical consistency: total/Σromans. The per-partition validator
# deliberately skips TOTAL=Σromans for off-balance (some banks carry a STABLE
# structural gap — derivative notionals outside the I/II/III romans — so a flat
# tolerance false-positives). Flag only when a partition's ratio jumps off the
# SAME bank's median ratio: a stable gap stays clean, a dropped roman section
# spikes the ratio (e.g. ATBANK 2025Q4 total 8x Σromans).
OFFBAL_MIN_POINTS = 5
OFFBAL_RATIO_DEV = 0.5

_TOT_ASSETS = re.compile(r"(TOPLAM\s+AKT[İI]F|AKT[İI]F\s+TOPLAM|VARLIKLAR\s+TOPLAM|TOPLAM\s+VARLIK|TOTAL\s+ASSETS)", re.I)
_TOT_LIAB = re.compile(r"(TOPLAM\s+PAS[İI]F|PAS[İI]F\s+TOPLAM|TOPLAM\s+KAYNAK|TOPLAM\s+Y[ÜU]K[ÜU]ML[ÜU]L[ÜU]K|TOTAL\s+LIABILITIES|TOTAL\s+EQUITY\s+AND\s+LIABILITIES|TOTAL\s+SHAREHOLDERS)", re.I)


def _stale_periods(conn: sqlite3.Connection) -> list[str]:
    out = []
    pairs = conn.execute(
        "SELECT DISTINCT bank_ticker, kind FROM bank_audit_balance_sheet").fetchall()
    for bank, kind in pairs:
        periods = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM bank_audit_balance_sheet "
            "WHERE bank_ticker=? AND kind=? ORDER BY period", (bank, kind))]
        for p0, p1 in zip(periods, periods[1:]):
            prev = {(s, o): a for s, o, a in conn.execute(
                "SELECT statement, item_order, amount_total FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND kind=? AND period=?", (bank, kind, p0))}
            cur = {(s, o): a for s, o, a in conn.execute(
                "SELECT statement, item_order, amount_total FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND kind=? AND period=?", (bank, kind, p1))}
            comparable = matches = 0
            for k, pv in prev.items():
                if pv in (None, 0) or k not in cur or cur[k] is None:
                    continue
                comparable += 1
                if cur[k] == pv:
                    matches += 1
            if comparable >= DUP_MIN_ROWS and matches / comparable >= DUP_FRACTION:
                out.append(f"stale     {bank} {p1} {kind}: {matches}/{comparable} line items "
                           f"identical to {p0} — prior period likely stored as current")
    return out


def _grand_total(conn, bank, period, kind, statement, pat) -> float | None:
    """The statement's grand total — the LARGEST amount_total, but only when that
    max row carries a total label. This avoids two failure modes: a stray row
    whose label merely contains "total" (tiny value), and banks whose real total
    row isn't captured at all (then the max is a sub-line, not a total → skip)."""
    rows = [(n, a) for n, a in conn.execute(
        "SELECT item_name, amount_total FROM bank_audit_balance_sheet "
        "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
        (bank, period, kind, statement)) if a is not None]
    if not rows:
        return None
    name, mx = max(rows, key=lambda x: x[1])
    return mx if pat.search(name or "") else None


def _balance(conn) -> list[str]:
    out = []
    keys = conn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet").fetchall()
    for bank, period, kind in keys:
        a = _grand_total(conn, bank, period, kind, "assets", _TOT_ASSETS)
        liab = _grand_total(conn, bank, period, kind, "liabilities", _TOT_LIAB)
        if a and liab and a > 0 and abs(a - liab) / a > BALANCE_TOL:
            out.append(f"balance   {bank} {period} {kind}: assets {a:,.0f} != "
                       f"liabilities {liab:,.0f} ({abs(a-liab)/a*100:.1f}% off)")
    return out


def _coverage(conn) -> list[str]:
    out = []
    for bank, period, kind in conn.execute(
            "SELECT bank_ticker, period, kind FROM bank_audit_extractions WHERE success=1"):
        na = conn.execute("SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                          "AND period=? AND kind=? AND statement='assets'",
                          (bank, period, kind)).fetchone()[0]
        nl = conn.execute("SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                          "AND period=? AND kind=? AND statement='liabilities'",
                          (bank, period, kind)).fetchone()[0]
        npl = conn.execute("SELECT COUNT(*) FROM bank_audit_profit_loss WHERE bank_ticker=? "
                           "AND period=? AND kind=?", (bank, period, kind)).fetchone()[0]
        if na < MIN_ASSET_ROWS or nl < MIN_ASSET_ROWS or npl < MIN_PL_ROWS:
            out.append(f"coverage  {bank} {period} {kind}: rows assets={na} liab={nl} pl={npl}")
    return out


def _npl_collapse(conn: sqlite3.Connection) -> list[str]:
    """Flag a quarter whose Stage-3 NPL ratio crashes from a real level to ~0 —
    the signature of the Stage-3 extractor latching onto an FC-only / fragment
    sub-table instead of the total III/IV/V classification."""
    # bank_audit_stages may not exist on a freshly-seeded DB; degrade gracefully.
    have = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_audit_stages'"
    ).fetchone()
    if not have:
        return []
    out = []
    banks = [r[0] for r in conn.execute(
        "SELECT DISTINCT bank_ticker FROM bank_audit_stages "
        "WHERE kind='unconsolidated' AND period_type='current'")]
    for bank in banks:
        rows = conn.execute(
            "SELECT period, CASE WHEN total_amount > 0 "
            "       THEN stage3_amount * 1.0 / total_amount END AS npl "
            "FROM bank_audit_stages "
            "WHERE bank_ticker=? AND kind='unconsolidated' AND period_type='current' "
            "ORDER BY period", (bank,)).fetchall()
        for (p0, n0), (p1, n1) in zip(rows, rows[1:]):
            if (n0 is not None and n1 is not None
                    and n0 >= NPL_COLLAPSE_PRIOR_MIN and n1 < NPL_COLLAPSE_CUR_MAX):
                out.append(
                    f"npl_drop  {bank} {p1} unconsolidated: NPL {n1*100:.3f}% "
                    f"collapsed from {n0*100:.2f}% at {p0} — Stage-3 likely an "
                    f"FC-only/fragment table, not the total NPL classification")
    return out


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


# Capital tolerance: 2% absorbs rounding and any sub-line the extractor missed.
CAP_REL_TOL = 0.02


def _capital_consistency(conn: sqlite3.Connection) -> list[str]:
    """Arithmetic sanity on bank_audit_capital (current period): the tier
    ordering must hold and the reported CAR must reconcile to capital / RWA.
    A failure is almost always a parse error — a missing label variant or the
    wrong 'Total Capital' line picked up — i.e. exactly what to fix next."""
    if not _has_table(conn, "bank_audit_capital"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, cet1_capital, tier1_capital, "
        "       total_capital, total_rwa, capital_adequacy_ratio, "
        "       cet1_ratio, tier1_ratio "
        "FROM bank_audit_capital WHERE period_type='current'").fetchall()
    for bank, period, kind, cet1, t1, tc, rwa, car, cet1r, t1r in rows:
        tag = f"capital   {bank} {period} {kind}:"
        if cet1 and t1 and cet1 > t1 * (1 + CAP_REL_TOL):
            out.append(f"{tag} CET1 {cet1:,.0f} > Tier1 {t1:,.0f}")
        if t1 and tc and t1 > tc * (1 + CAP_REL_TOL):
            out.append(f"{tag} Tier1 {t1:,.0f} > Total capital {tc:,.0f}")
        # Reconcile the bank's OWN reported ratios to EACH OTHER, not the reported
        # CAR to printed capital/RWA. Many banks publish a BDDK forbearance-adjusted
        # regulatory ratio (the "Geçici madde" transitional measures — fixed-FX RWA
        # etc.), so printed total_capital / total_rwa legitimately does NOT divide to
        # the printed CAR (ATBANK runs a ~1.5pp gap every quarter — a true false
        # positive under the old check). The RWA each reported ratio implies
        # (capital_i / ratio_i) must agree, though; a real column-slip (wrong RWA or
        # a mis-parsed capital component) breaks that mutual consistency, a
        # forbearance gap does not. Real RWA/total drops are caught upstream by the
        # extraction-time validator (cap_composition / cap_rwa_missing).
        # 8% band: a real column-slip (wrong RWA/component) throws an implied RWA
        # off by tens of % (EMLAK 2025Q1's slipped total_capital → ~4×). A bank
        # that publishes a forbearance-adjusted CAR but raw CET1/Tier1 ratios
        # (ICBCT/ANADOLU) sits at ~3–5% — real reporting basis, not a parse error —
        # so the band stays above it to avoid re-introducing that false positive.
        implied = [c / r * 100 for c, r in ((tc, car), (t1, t1r), (cet1, cet1r)) if c and r]
        if len(implied) >= 2 and (hi := max(implied)) > 0 and (hi - min(implied)) / hi > 0.08:
            out.append(f"{tag} reported ratios imply inconsistent RWA "
                       f"({min(implied):,.0f}–{hi:,.0f}) — a capital component or ratio mis-parsed")
        if car is not None and not (5 <= car <= 80):
            out.append(f"{tag} CAR {car} out of plausible band")
    return out


def _liquidity_bands(conn: sqlite3.Connection) -> list[str]:
    """Plausibility bands on bank_audit_liquidity (current period). Ratios are
    percentages; banks must run LCR/NSFR >= 100% in steady state, so a very low
    LCR is the fingerprint of a mis-grabbed value."""
    if not _has_table(conn, "bank_audit_liquidity"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, leverage_ratio, lcr_total, nsfr "
        "FROM bank_audit_liquidity WHERE period_type='current'").fetchall()
    for bank, period, kind, lev, lcr, nsfr in rows:
        tag = f"liquidity {bank} {period} {kind}:"
        if lev is not None and not (0 < lev < 30):
            out.append(f"{tag} leverage {lev} out of band")
        for nm, v in (("LCR", lcr), ("NSFR", nsfr)):
            if v is not None and not (0 < v < 2000):
                out.append(f"{tag} {nm} {v} out of band")
        if lcr is not None and lcr < 50:
            out.append(f"{tag} LCR {lcr}% implausibly low — likely a mis-grabbed value")
    return out


# A liquidity ratio is reconciliation-free (the table stores no components), so
# the only structural check is consistency with the SAME bank's other periods:
# a decimal/wrong-cell slip throws a value off by an order of magnitude (e.g.
# FIBA lcr_fc read 1.08 when the bank runs ~430). 8x is well above genuine
# ratio volatility (an FX-heavy bank like EXIM swings ~5x and is real) so this
# stays high-precision. Critically it also covers lcr_fc, which the band check
# and the per-partition validator never read.
LIQ_OUTLIER_FACTOR = 8.0
LIQ_MIN_POINTS = 5  # need a stable within-bank baseline


def _liquidity_outliers(conn: sqlite3.Connection) -> list[str]:
    if not _has_table(conn, "bank_audit_liquidity"):
        return []
    import statistics as _st
    out = []
    metrics = ("leverage_ratio", "lcr_total", "lcr_fc", "nsfr")
    series: dict[tuple, list] = {}
    rows = conn.execute(
        f"SELECT bank_ticker, period, kind, {','.join(metrics)} "
        "FROM bank_audit_liquidity WHERE period_type='current'").fetchall()
    for bank, period, kind, *vals in rows:
        for m, v in zip(metrics, vals):
            if v is not None:
                series.setdefault((bank, kind, m), []).append((period, v))
    for (bank, kind, m), pts in series.items():
        if len(pts) < LIQ_MIN_POINTS:
            continue
        med = _st.median([v for _, v in pts])
        if med <= 0:
            continue
        for period, v in pts:
            r = v / med
            if r > LIQ_OUTLIER_FACTOR or r < 1 / LIQ_OUTLIER_FACTOR:
                out.append(f"liquidity {bank} {period} {kind}: {m} {v:g} is "
                           f"{r:.2g}x the bank's median {med:g} — likely a mis-grabbed value")
    return out


# ECL sanity: corrupted parses show up as values like -6 / 63 / 89 (the dipnot
# ref "(6)" read as a value). Real ECL on a bank with a >10bn-TL balance sheet
# is never under 100 thousand TL.
ECL_TINY_MAX = 100            # thousand TL
ECL_MIN_BANK_TOTAL = 10_000_000  # only apply the tiny test to large banks


def _ecl_sanity(conn: sqlite3.Connection) -> list[str]:
    """Fingerprints of the ECL parse bug (ALBRK -6 / row-drop class):
       a) truncated label '…Losses(' — the label boundary landed inside '(-)';
       b) ALL of a large bank's ECL rows implausibly tiny — dipnot ref read as
          value (covers -6). Per-row tiny is normal: the cash-section 1.1.4 ECL
          is legitimately ~tens of TL-thousands (BURGAN prints "77") — only a
          partition whose LARGEST |ECL| is tiny is corrupt. Sign is never
          flagged: some banks print the value itself in parens, so a large
          negative ECL is the faithful reading (ING/KLNMA/PASHA/TFKB);
       c) a quarter whose ECL rows vanish while the prior quarter had them —
          the silent row-drop variant."""
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, item_name, amount_total "
        "FROM bank_audit_balance_sheet WHERE statement='assets' AND ("
        "  replace(upper(item_name),' ','') LIKE '%EXPECTEDCREDITLOSS%'"
        "  OR replace(upper(item_name),' ','') LIKE '%BEKLENENZARAR%')"
    ).fetchall()
    totals: dict[tuple, float] = {}

    def bank_total(bank: str, period: str, kind: str) -> float:
        key = (bank, period, kind)
        if key not in totals:
            v = conn.execute(
                "SELECT MAX(amount_total) FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND period=? AND kind=? AND statement='assets'",
                key).fetchone()[0]
            totals[key] = v or 0
        return totals[key]

    ecl_periods: dict[tuple, set] = {}
    partition_max: dict[tuple, float] = {}
    for bank, period, kind, name, amt in rows:
        ecl_periods.setdefault((bank, kind), set()).add(period)
        tag = f"ecl       {bank} {period} {kind}:"
        if (name or "").rstrip().endswith("("):
            out.append(f"{tag} truncated label {name!r} (amount {amt}) — parse error")
            continue
        if amt is None:
            continue
        key = (bank, period, kind)
        partition_max[key] = max(partition_max.get(key, 0.0), abs(amt))
    for (bank, period, kind), mx in partition_max.items():
        if 0 < mx < ECL_TINY_MAX and bank_total(bank, period, kind) > ECL_MIN_BANK_TOTAL:
            out.append(f"ecl       {bank} {period} {kind}: largest ECL only "
                       f"{mx:,.0f} — dipnot ref likely read as the value")
    # c) ECL rows vanished vs the prior quarter (needs enough asset rows that
    #    the quarter isn't just a failed extraction — coverage flags those).
    for (bank, kind), have in ecl_periods.items():
        periods = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM bank_audit_balance_sheet "
            "WHERE bank_ticker=? AND kind=? AND statement='assets' ORDER BY period",
            (bank, kind))]
        for p0, p1 in zip(periods, periods[1:]):
            if p0 in have and p1 not in have:
                n = conn.execute(
                    "SELECT COUNT(*) FROM bank_audit_balance_sheet WHERE bank_ticker=? "
                    "AND period=? AND kind=? AND statement='assets'",
                    (bank, p1, kind)).fetchone()[0]
                if n >= MIN_ASSET_ROWS:
                    out.append(f"ecl       {bank} {p1} {kind}: ECL rows present at {p0} "
                               f"but missing here — row likely dropped by the parser")
    return out


def _off_balance_consistency(conn: sqlite3.Connection) -> list[str]:
    """Off-balance grand total vs Σ roman sections, validated within-bank. The
    TOTAL=Σromans identity isn't a per-partition off-balance check (stable
    structural gaps would false-fail), so flag a partition only when its
    total/Σromans ratio deviates from the bank's own median by >OFFBAL_RATIO_DEV —
    a sudden jump = a dropped roman section / wrong total; a stable offset = the
    bank's structure, left alone."""
    if not _has_table(conn, "bank_audit_balance_sheet"):
        return []
    import statistics as _st
    from collections import defaultdict
    series: dict[tuple, list] = defaultdict(list)
    keys = conn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_balance_sheet "
        "WHERE statement='off_balance'").fetchall()
    for bank, period, kind in keys:
        rows = [
            {"hierarchy": h, "item_name": n, "amount_total": a}
            for h, n, a in conn.execute(
                "SELECT hierarchy, item_name, amount_total FROM bank_audit_balance_sheet "
                "WHERE bank_ticker=? AND period=? AND kind=? AND statement='off_balance' "
                "ORDER BY item_order", (bank, period, kind))
        ]
        total, romans = _statement_total(rows)
        if total and romans and romans != 0:
            series[(bank, kind)].append((period, total / romans))
    out = []
    for (bank, kind), pts in series.items():
        if len(pts) < OFFBAL_MIN_POINTS:
            continue
        med = _st.median([r for _, r in pts])
        for period, r in pts:
            if abs(r - med) > OFFBAL_RATIO_DEV:
                out.append(f"offbal    {bank} {period} {kind}: TOTAL/Σromans={r:.2f} "
                           f"vs bank median {med:.2f} — a roman section likely dropped")
    return out


def _pl_sign_convention(conn: sqlite3.Connection) -> list[str]:
    """P&L deduction romans (II, IX–XII) whose stored SIGN flips within one
    bank/kind series. The per-partition chain check deliberately accepts either
    storage convention (positive magnitude vs parenthesised negative), so a
    convention flip — a layout change, an extraction inconsistency, or a genuine
    provision recovery — is invisible to it, yet corrupts any consumer that
    de-cumulates YTD romans across the flip quarter without abs()-normalising.
    Heuristic + alert-only: the standing flips live in the R2 anomaly baseline;
    only a NEW flip pings."""
    if not _has_table(conn, "bank_audit_profit_loss"):
        return []
    from collections import defaultdict
    from src.audit_reports.validator import _pl_spine
    series: dict[tuple, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    keys = conn.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_profit_loss").fetchall()
    for bank, period, kind in sorted(keys):
        rows = [{"hierarchy": h, "item_name": n, "amount": a} for h, n, a in conn.execute(
            "SELECT hierarchy, item_name, amount FROM bank_audit_profit_loss "
            "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY item_order",
            (bank, period, kind))]
        spine = _pl_spine(rows)
        for o in (2, 9, 10, 11, 12):
            if spine.get(o):  # zeros carry no sign information
                series[(bank, kind)][o].append((period, spine[o]))
    out = []
    for (bank, kind), ords in sorted(series.items()):
        for o, vals in sorted(ords.items()):
            pos = [p for p, v in vals if v > 0]
            neg = [p for p, v in vals if v < 0]
            if pos and neg:
                minority = pos if len(pos) <= len(neg) else neg
                out.append(f"pl_sign   {bank} {kind}: roman {o} stored sign flips "
                           f"({len(pos)}+/{len(neg)}−; minority e.g. {', '.join(minority[:3])}) "
                           f"— de-cumulating consumers must abs()-normalise")
    return out


# Free provisions are stored in thousand-TL. The largest real one in the corpus
# is ~15bn TL (VAKBN = 15,000,000); a value above this generous ceiling or below
# zero is a mis-parse (a total grabbed as the reserve). The prior figure a report
# states IS the prior year-end (Dec 31) stock, so it must equal that bank's Q4
# free_provision for the prior year — an exact, independent cross-check that
# catches a wrong current OR a wrong prior on either side.
FREEPROV_MAX = 100_000_000        # thousand TL (= 100bn TL) — generous ceiling
FREEPROV_PRIOR_TOL = 0.01         # stated prior vs prior-year-end current: 1%

# How an auditor NAMES the reserve when qualifying over it. The recall check
# below is only as wide as this list, and it was too narrow: BURGAN's 2023Q2–
# 2024Q1 basis paragraphs say "general reserve" / "general provision" where its
# 2024Q2 paragraph — same boilerplate, same Note 2.h.2.ii, same purpose clause —
# says "free provision". The auditor merely translated it differently. Result:
# 8 cells read "not applicable" while carrying a qualification over a reserve of
# up to ₺1.87bn, and the value is sitting in bank_audit_opinion.basis_text, a
# neighbouring column of this same database.
#
# Surgical by measurement, not by hope: these two phrases appear in BURGAN (9)
# and SKBNK (8, which already have rows) and nowhere else.
#
# 'genel karşılık' is deliberately ABSENT despite the symmetry — it matches 0
# rows today AND it is the standard BRSA term for the regulatory general
# loan-loss provision, an entirely different thing. Adding it would only ever
# manufacture false positives.
#
# NOTE — this widens DETECTION, not capture. src/audit_reports/free_provision.py
# has the same blind spot (_SUBJ_EN = r"free\s+provision", _SUBJ_TR =
# r"serbest\s+kar[şs][ıi]l[ıi]k"), so SKBNK 2022Q1–Q3 have rows only because
# their text literally says "free provision". These alarms are correct and the
# data fix needs the extractor widened too.
_FREEPROV_SUBJECTS = ("%free provision%", "%serbest kar%",
                      "%general reserve%", "%general provision%")


def _free_provision(conn: sqlite3.Connection) -> list[str]:
    """Data-quality checks for bank_audit_free_provision (the serbest karşılık
    stock). There is no intra-row arithmetic to reconcile, so the checks are
    cross-lane and longitudinal — reconciliation against independent signals,
    which is what actually catches a regression:

      a) band        — 0 <= free_provision <= a sane ceiling; a huge value is a
                        total mis-read as the reserve.
      b) prior_chain — the prior figure a report states is the prior YEAR-END
                        stock, so it must equal that bank's Q4 free_provision for
                        the prior year. A break means the current or the prior was
                        mis-extracted on one side.
      c) recall      — the auditor qualified over a free provision (opinion
                        is_modified + basis names it) yet no value was captured =
                        a missed disclosure (the BURGAN-2022 gap fingerprint).
      d) precision   — a value under a CLEAN opinion. Holding a free provision
                        usually triggers a qualification, so this wants a look —
                        it is exactly how the AKBNK/ZIRAATK cancelled-amount false
                        positives surfaced (a reversal read as the stock)."""
    if not _has_table(conn, "bank_audit_free_provision"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, free_provision, free_provision_prior "
        "FROM bank_audit_free_provision").fetchall()
    cur = {(b, p, k): v for b, p, k, v, _ in rows}
    for bank, period, kind, fp, prior in rows:
        tag = f"freeprov  {bank} {period} {kind}:"
        if fp is not None and (fp < 0 or fp > FREEPROV_MAX):
            out.append(f"{tag} free provision {fp:,.0f} out of plausible band")
        # prior_chain: stated prior == that bank's prior-year-end (Q4) current.
        if prior is not None and prior >= 0 and re.fullmatch(r"\d{4}Q\d", period):
            q4_prev = cur.get((bank, f"{int(period[:4]) - 1}Q4", kind))
            if q4_prev is not None:
                denom = max(abs(prior), abs(q4_prev), 1)
                if abs(prior - q4_prev) / denom > FREEPROV_PRIOR_TOL:
                    out.append(f"{tag} stated prior {prior:,.0f} != prior-year-end current "
                               f"{q4_prev:,.0f} ({int(period[:4]) - 1}Q4) — one side mis-extracted")
    if _has_table(conn, "bank_audit_opinion"):
        _subj_sql = " OR ".join(["lower(o.basis_text) LIKE ?"] * len(_FREEPROV_SUBJECTS))
        for bank, period, kind in conn.execute(
                "SELECT o.bank_ticker, o.period, o.kind FROM bank_audit_opinion o "
                f"WHERE o.is_modified=1 AND ({_subj_sql}) "
                "AND NOT EXISTS (SELECT 1 FROM bank_audit_free_provision f "
                "  WHERE f.bank_ticker=o.bank_ticker AND f.period=o.period "
                "    AND f.kind=o.kind)", _FREEPROV_SUBJECTS):
            # No row at all — not merely a captured 0 (a bank that reversed to
            # zero and disclosed "none" is covered, not a gap).
            out.append(f"freeprov  {bank} {period} {kind}: auditor qualified over a free "
                       f"provision but none was extracted — likely a missed disclosure")
        for bank, period, kind, fp in conn.execute(
                "SELECT f.bank_ticker, f.period, f.kind, f.free_provision "
                "FROM bank_audit_free_provision f JOIN bank_audit_opinion o "
                "  ON o.bank_ticker=f.bank_ticker AND o.period=f.period AND o.kind=f.kind "
                # source_page=-1 is a hand-transcribed override — already human
                # verified, so it needs no "verify this holding" warning. The check
                # targets UNVERIFIED extractor values (the cancelled-amount trap).
                "WHERE f.free_provision>0 AND o.is_modified=0 "
                "  AND (f.source_page IS NULL OR f.source_page >= 0)"):
            out.append(f"freeprov  {bank} {period} {kind}: free provision {fp:,.0f} under a "
                       f"CLEAN opinion — verify a real holding, not a cancelled amount")
    return out


def _structure(conn: sqlite3.Connection) -> list[str]:
    """Partitions whose extraction-time identity validation failed (see
    src/audit_reports/validator.py). Summarized per partition — the per-check
    detail lives in bank_audit_validation.failed_detail."""
    if not _has_table(conn, "bank_audit_validation"):
        return []
    out = []
    rows = conn.execute(
        "SELECT bank_ticker, period, kind, statement, checks_passed, checks_failed "
        "FROM bank_audit_validation WHERE checks_failed > 0 "
        "ORDER BY bank_ticker, period, kind, statement").fetchall()
    for bank, period, kind, stmt, ok, bad in rows:
        out.append(f"structure {bank} {period} {kind}: {stmt} — {bad} identity "
                   f"check(s) failed ({ok} passed)")
    return out


def check(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return (_stale_periods(conn) + _balance(conn) + _coverage(conn)
                + _npl_collapse(conn) + _capital_consistency(conn)
                + _liquidity_bands(conn) + _liquidity_outliers(conn)
                + _off_balance_consistency(conn)
                + _structure(conn) + _ecl_sanity(conn)
                + _pl_sign_convention(conn) + _free_provision(conn))
    finally:
        conn.close()


# --- Delta alerting -------------------------------------------------------
# The full anomaly list is a large, slow-moving backlog of known issues, so
# alerting it on every run (incl. every per-cell re-extract) is pure noise. We
# alert only on what CHANGED vs a baseline persisted in R2.

BASELINE_KEY = "state/audit_anomaly_baseline.json"
_FP_NUM = re.compile(r"[-+]?\d[\d.,]*%?")


def _fingerprint(anomaly: str) -> str:
    """Stable identity for an anomaly line, ignoring volatile numbers in the detail.
    The head ('<category> <bank> <period> <kind>') is kept verbatim — periods like
    2022Q4 live there — and only the detail after the first ':' is number-stripped,
    so a value nudge (e.g. CAR 18.92% → 18.90%) is NOT a new anomaly while a
    different partition / statement / check still is."""
    head, sep, detail = anomaly.partition(":")
    key = " ".join(head.split())
    if sep:
        key += " :: " + " ".join(_FP_NUM.sub("#", detail).split())
    return key


def _load_baseline() -> set[str] | None:
    """Baseline fingerprints from R2 — empty set if the file doesn't exist yet
    (first run), or None if R2 is unavailable/errored (caller falls back to a full
    alert so a real regression is never silently dropped)."""
    try:
        from src.audit_reports import r2_storage
        if not r2_storage.exists(BASELINE_KEY):
            return set()
        data = json.loads(r2_storage.download_bytes(BASELINE_KEY).decode("utf-8"))
        return set(data.get("fingerprints", []))
    except Exception as e:  # noqa: BLE001
        print(f"[quality] baseline load failed ({e}); falling back to full alert",
              file=sys.stderr)
        return None


def _save_baseline(fingerprints: set[str]) -> None:
    try:
        from datetime import datetime, timezone
        from src.audit_reports import r2_storage
        body = json.dumps(
            {"fingerprints": sorted(fingerprints),
             "updated_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False).encode("utf-8")
        r2_storage.upload_bytes(body, BASELINE_KEY, content_type="application/json")
    except Exception as e:  # noqa: BLE001
        print(f"[quality] baseline save failed ({e})", file=sys.stderr)


def _notify(msg: str) -> None:
    try:
        subprocess.run([sys.executable, str(REPO / "scripts" / "notify.py"), msg], check=False)
    except Exception as e:  # noqa: BLE001
        print(f"[quality] notify failed: {e}", file=sys.stderr)


def _legacy_alert(anomalies: list[str]) -> None:
    head = anomalies[:20]
    more = f"\n…and {len(anomalies) - 20} more" if len(anomalies) > 20 else ""
    _notify(f"⚠️ Audit data-quality: {len(anomalies)} anomaly(ies)\n" + "\n".join(head) + more)


def alert_delta(anomalies: list[str]) -> None:
    """Alert only on anomalies NEW or RESOLVED vs the R2 baseline; quiet otherwise.
    First run seeds the baseline silently (so the standing backlog isn't re-blasted)."""
    cur = {_fingerprint(a): a for a in anomalies}
    baseline = _load_baseline()
    if baseline is None:  # R2 unavailable — don't go silent on a real backlog
        _legacy_alert(anomalies)
        return
    new = [cur[fp] for fp in cur if fp not in baseline]
    resolved = baseline - set(cur)
    if not baseline:
        print(f"[quality] seeded baseline with {len(cur)} anomaly(ies); not alerting", flush=True)
    elif new:
        head = new[:15]
        more = f"\n…and {len(new) - 15} more new" if len(new) > 15 else ""
        res = f", {len(resolved)} resolved" if resolved else ""
        _notify(f"🟡 Audit data-quality changed: {len(new)} new ({len(cur)} total){res}\n"
                + "\n".join(head) + more)
    elif resolved:
        _notify(f"✅ {len(resolved)} audit anomaly(ies) resolved; {len(cur)} remain")
    else:
        print(f"[quality] no change vs baseline ({len(cur)} anomalies); not alerting", flush=True)
    _save_baseline(set(cur))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--alert", action="store_true", help="send a Telegram/Discord summary on anomalies")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on anomalies")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[quality] no DB at {db}; skipping")
        return 0
    anomalies = check(db)
    if not anomalies:
        print("[quality] OK — no audit data-quality anomalies")
        return 0

    print(f"[quality] {len(anomalies)} anomaly(ies):")
    for a in anomalies:
        print("  -", a)
    if args.alert:
        alert_delta(anomalies)
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
