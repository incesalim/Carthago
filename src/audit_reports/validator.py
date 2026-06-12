"""Structural validation of extracted BRSA balance-sheet rows.

BRSA statements are self-validating: every 6-column row carries TL + FC =
Total, every hierarchy parent equals the sum of its direct children (rows
labelled "(-)" are contra lines and subtract), the grand-total row equals the
sum of the roman sections, and total assets equal total liabilities + equity.
The 2026-06 ECL incident (see docs/AUDIT_REWORK_PLAN.md) corrupted 17 banks
for four years of quarters while violating *all* of these identities — this
module makes them a permanent extraction-time gate instead of post-incident
fingerprint checks.

Pure stdlib on purpose: importable (and testable) under CI's minimal
dependency set — no pdfplumber here. Operates on plain row dicts:

    {"hierarchy": "1.1.4.", "item_name": "Expected Credit Losses (-)",
     "amount_tl": 55886.0, "amount_fc": 127366.0, "amount_total": 183252.0}

which is both the loader's StatementRow shape and a bank_audit_balance_sheet
SELECT — so the same checks run at extraction time and over any DB snapshot.

Sign convention: "(-)"-labelled contra rows contribute -|amount| to their
parent. That covers both storage conventions in the corpus: most banks store
the positive magnitude (label carries the minus), while ING/KLNMA/PASHA/TFKB
print the value itself in parentheses and therefore store a negative.

Tolerances absorb the report's thousands-rounding: each child contributes up
to ±1 of rounding, so identity tolerances scale mildly with the magnitude.
Calibrated against the 2026-06 fleet dry-run (Phase 2 of the rework plan).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# Contra lines: "Expected Credit Losses (-)", "Beklenen Zarar Karşılıkları ( - )"
_CONTRA_RX = re.compile(r"\(\s*-\s*\)")
_ROMAN_RX = re.compile(r"^([IVX]+)\.?$")
_NUMERIC_RX = re.compile(r"^(\d+(?:\.\d+)*)\.?$")
_TOTAL_RX = re.compile(r"(?:TOTAL|TOPLAM)", re.I)

_ROMAN_VAL = {"I": 1, "V": 5, "X": 10}


def _roman_to_int(s: str) -> int | None:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = _ROMAN_VAL.get(ch)
        if v is None:
            return None
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total or None


def _path(hierarchy: str | None) -> tuple[int, ...] | None:
    """Normalize a hierarchy token to a numeric path.

    'III.' → (3,)   '2.4' / '2.4.' → (2, 4)   '1.1.4.' → (1, 1, 4)
    Roman sections and their numeric children share one tree: section III.'s
    direct children are the 3.x rows.
    """
    h = (hierarchy or "").strip()
    if not h:
        return None
    m = _ROMAN_RX.match(h)
    if m:
        v = _roman_to_int(m.group(1))
        return (v,) if v else None
    m = _NUMERIC_RX.match(h)
    if m:
        try:
            return tuple(int(p) for p in m.group(1).split("."))
        except ValueError:
            return None
    return None


def _contribution(row: dict) -> float | None:
    amt = row.get("amount_total")
    if amt is None:
        return None
    if _CONTRA_RX.search(row.get("item_name") or ""):
        return -abs(amt)
    return amt


@dataclass
class ValidationResult:
    checked: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[dict] = field(default_factory=list)

    def add_pass(self) -> None:
        self.checked += 1
        self.passed += 1

    def add_skip(self) -> None:
        self.skipped += 1

    def add_fail(self, check: str, node: str, expected: float, actual: float) -> None:
        self.checked += 1
        self.failed += 1
        self.failures.append({
            "check": check, "node": node,
            "expected": round(expected, 2), "actual": round(actual, 2),
            "diff": round(actual - expected, 2),
        })

    def merge(self, other: "ValidationResult") -> None:
        self.checked += other.checked
        self.passed += other.passed
        self.failed += other.failed
        self.skipped += other.skipped
        self.failures.extend(other.failures)

    def detail_json(self, cap: int = 25) -> str | None:
        if not self.failures:
            return None
        head = self.failures[:cap]
        if len(self.failures) > cap:
            head.append({"check": "…", "node": f"+{len(self.failures) - cap} more",
                         "expected": 0, "actual": 0, "diff": 0})
        return json.dumps(head, ensure_ascii=False)


def _tol(expected: float, base: float, rel: float) -> float:
    return max(base, abs(expected) * rel)


def check_row_triplets(rows: list[dict]) -> ValidationResult:
    """V1 — every row: amount_tl + amount_fc = amount_total (±rounding)."""
    res = ValidationResult()
    for r in rows:
        tl, fc, tot = r.get("amount_tl"), r.get("amount_fc"), r.get("amount_total")
        if tl is None or fc is None or tot is None:
            res.add_skip()
            continue
        if abs((tl + fc) - tot) <= _tol(tot, base=3.0, rel=1e-5):
            res.add_pass()
        else:
            res.add_fail("row_triplet", f"{r.get('hierarchy', '')} {r.get('item_name', '')}".strip(),
                         expected=tot, actual=tl + fc)
    return res


def check_hierarchy_sums(rows: list[dict]) -> ValidationResult:
    """V2 — each parent row equals the sum of its DIRECT children's
    contributions ("(-)" rows subtract). A parent with no captured children is
    skipped, not failed — banks legitimately omit all-zero sub-rows; a DROPPED
    child shows up as a failing parent, which is exactly the point."""
    res = ValidationResult()
    by_path: dict[tuple[int, ...], list[dict]] = {}
    for r in rows:
        p = _path(r.get("hierarchy"))
        if p is not None:
            by_path.setdefault(p, []).append(r)
    children: dict[tuple[int, ...], list[dict]] = {}
    for p, rs in by_path.items():
        if len(p) < 2:
            continue
        for r in rs:
            children.setdefault(p[:-1], []).append(r)
    for parent_path, kids in children.items():
        parents = by_path.get(parent_path)
        if not parents:
            res.add_skip()
            continue
        parent = parents[0]
        p_total = parent.get("amount_total")
        if p_total is None:
            res.add_skip()
            continue
        contribs = [_contribution(k) for k in kids]
        if any(c is None for c in contribs):
            res.add_skip()
            continue
        # A contra parent ("ECL (-)" with sub-rows) compares on magnitudes —
        # its children are stated as magnitudes under the same convention.
        if _CONTRA_RX.search(parent.get("item_name") or ""):
            expected = abs(p_total)
            actual = sum(abs(c) for c in contribs)
        else:
            expected = p_total
            actual = sum(contribs)
        if abs(actual - expected) <= _tol(expected, base=3.0 + len(kids), rel=5e-5):
            res.add_pass()
        else:
            node = f"{parent.get('hierarchy', '')} {parent.get('item_name', '')}".strip()
            res.add_fail("hierarchy_sum", node, expected=expected, actual=actual)
    return res


def _statement_total(rows: list[dict]) -> tuple[float | None, float | None]:
    """(labelled grand-total amount or None, sum of roman sections or None)."""
    total_row = None
    for r in rows:
        name = r.get("item_name") or ""
        if _TOTAL_RX.search(name) and _path(r.get("hierarchy")) is None and r.get("amount_total") is not None:
            if total_row is None or abs(r["amount_total"]) > abs(total_row):
                total_row = r["amount_total"]
    romans = [r for r in rows if (p := _path(r.get("hierarchy"))) is not None and len(p) == 1]
    # one row per roman ordinal (duplicates would double-count)
    seen: dict[int, float] = {}
    for r in romans:
        amt = _contribution(r)
        if amt is None:
            continue
        seen.setdefault(_path(r["hierarchy"])[0], amt)
    roman_sum = sum(seen.values()) if seen else None
    return total_row, roman_sum


def check_statement_total(rows: list[dict]) -> ValidationResult:
    """V3 — labelled TOTAL row = Σ roman sections (when both exist)."""
    res = ValidationResult()
    total_row, roman_sum = _statement_total(rows)
    if total_row is None or roman_sum is None:
        res.add_skip()
        return res
    if abs(total_row - roman_sum) <= _tol(total_row, base=10.0, rel=5e-5):
        res.add_pass()
    else:
        res.add_fail("statement_total", "TOTAL vs Σ romans",
                     expected=total_row, actual=roman_sum)
    return res


def check_cross_statement(assets: list[dict], liabilities: list[dict]) -> ValidationResult:
    """V4 — total assets = total liabilities + equity (0.5%, matches the
    long-standing balance check in check_audit_quality)."""
    res = ValidationResult()
    a_total, a_romans = _statement_total(assets)
    l_total, l_romans = _statement_total(liabilities)
    a = a_total if a_total is not None else a_romans
    li = l_total if l_total is not None else l_romans
    if a is None or li is None or a == 0:
        res.add_skip()
        return res
    if abs(a - li) / abs(a) <= 0.005:
        res.add_pass()
    else:
        res.add_fail("cross_statement", "assets vs liabilities+equity",
                     expected=a, actual=li)
    return res


def validate_statement(rows: list[dict]) -> ValidationResult:
    """All single-statement checks (V1–V3) for one BS statement's rows."""
    res = ValidationResult()
    res.merge(check_row_triplets(rows))
    res.merge(check_hierarchy_sums(rows))
    res.merge(check_statement_total(rows))
    return res


def validate_off_balance(rows: list[dict]) -> ValidationResult:
    """Off-balance row triplets only.

    Off-balance sheets use I./II./III. roman top-level rows with sub-items
    numbered 1.x / 1.x.y that skip intermediate aggregation levels (e.g.
    there is no '1.1' row bridging 'I.' and '1.1.1'). This makes the generic
    parent=Σchildren check fire spuriously.  Only TL+FC=Total is reliable.
    """
    return check_row_triplets(rows)


def rows_from_statement_rows(stmt_rows) -> list[dict]:
    """Adapt extractor.StatementRow objects to validator dicts."""
    return [{
        "hierarchy": r.hierarchy, "item_name": r.name,
        "amount_tl": r.cur_tl, "amount_fc": r.cur_fc, "amount_total": r.cur_total,
    } for r in stmt_rows]


def rows_from_pl_statement_rows(stmt_rows) -> list[dict]:
    """Adapt extractor.StatementRow P&L objects to validator dicts ({hierarchy,
    item_name, amount}) — the single-column income-statement shape, matching a
    bank_audit_profit_loss SELECT."""
    return [{"hierarchy": r.hierarchy, "item_name": r.name, "amount": r.cur_amount}
            for r in stmt_rows]


# --- P&L (income statement) validation ------------------------------------
# The BDDK income statement is a fixed roman chain — each subtotal row literally
# prints its own formula. Roles are fixed by TEMPLATE POSITION: romans II and
# IX–XII are deductions; everything else adds with its stored sign. Two corpus
# realities make a naive ±1 chain false-fail, so the check is built around them:
#
#  1. Storage convention is NOT uniform — even within one statement. Most banks
#     store a deduction as a positive magnitude (the line prints "(-)"); the
#     participation/parenthesised-negative banks (ING, KLNMA, TFKB) store it as a
#     negative; and a genuine ECL *recovery* is a negative that must ADD back.
#     TFKB even mixes the two (II positive, IX–XII negative) in one statement.
#     So a deduction identity passes if EITHER reading foots — subtract the
#     magnitude (−|x|) OR subtract the stored value (−x). Same idea as the tax ±.
#  2. Stray roman rows — a title line ("III. STATEMENT OF PROFIT OR LOSS") above
#     the body, or a footnote roman below it — would shadow a real subtotal. We
#     take the subtotal amounts from the longest contiguous strictly-increasing
#     run of roman rows (the statement body) and ignore out-of-sequence strays.
#   (target roman ordinal, [source roman ordinals])
_PL_DEDUCTIONS = frozenset({2, 9, 10, 11, 12})
_PL_CHAIN = [
    (3,  [1, 2]),               # III  = I − II
    (8,  [3, 4, 5, 6, 7]),      # VIII = III+IV+V+VI+VII
    (13, [8, 9, 10, 11, 12]),   # XIII = VIII−IX−X−XI−XII
    (17, [13, 14, 15, 16]),     # XVII = XIII+XIV+XV+XVI
    (25, [19, 24]),             # XXV  = XIX+XXIV
]
# XIX = XVII ± XVIII handled apart: the tax provision XVIII prints "(±)" and is
# genuinely signed (usually expense, occasionally benefit), so XIX may land on
# either side of the pre-tax figure by XVIII's magnitude.
_PL_NET_RX = re.compile(
    r"DÖNEM NET KAR|DÖNEM NET KÂR|NET PERIOD PROFIT|DÖNEM KÂRI|Grubun|Group", re.I)


def _pl_spine(pl_rows: list[dict]) -> dict[int, float]:
    """Roman subtotals as {ordinal: amount}, taken from the longest contiguous
    strictly-increasing-ordinal run of roman-form rows — the statement body.
    Discards out-of-sequence strays (title/footnote rows, captured "1 OCAK…"
    header fragments) that would otherwise shadow a real subtotal."""
    seq: list[tuple[int, float]] = []
    for r in pl_rows:
        h = (r.get("hierarchy") or "").strip()
        if not _ROMAN_RX.match(h):     # roman-form only; a numeric "1" never a subtotal
            continue
        a = r.get("amount")
        o = _roman_to_int(h.rstrip("."))
        if o is not None and a is not None:
            seq.append((o, a))
    best: list[tuple[int, float]] = []
    cur: list[tuple[int, float]] = []
    for o, a in seq:
        if cur and o <= cur[-1][0]:
            if len(cur) > len(best):
                best = cur
            cur = []
        cur.append((o, a))
    if len(cur) > len(best):
        best = cur
    return {o: a for o, a in best}


def check_pl_chain(pl_rows: list[dict]) -> ValidationResult:
    """The income-statement roman identities (III=I−II … XXV=XIX+XXIV). An
    identity runs only when its target and ALL its source romans are present, so
    a P&L missing optional rows skips rather than false-fails. Deduction
    identities accept either storage convention (see module note)."""
    res = ValidationResult()
    amt = _pl_spine(pl_rows)
    for target, sources in _PL_CHAIN:
        if target not in amt or any(s not in amt for s in sources):
            res.add_skip()
            continue
        base = sum(amt[s] for s in sources if s not in _PL_DEDUCTIONS)
        ded = [amt[s] for s in sources if s in _PL_DEDUCTIONS]
        tol = _tol(amt[target], base=3.0, rel=5e-5)
        if not ded:
            actual = base
            ok = abs(actual - amt[target]) <= tol
        else:
            actual = base + sum(-abs(v) for v in ded)            # magnitude reading
            actual_signed = base + sum(-v for v in ded)          # stored-sign reading
            ok = min(abs(actual - amt[target]), abs(actual_signed - amt[target])) <= tol
        if ok:
            res.add_pass()
        else:
            res.add_fail("pl_chain", f"roman {target} identity",
                         expected=amt[target], actual=actual)
    # XIX = XVII ± XVIII (tax line genuinely signed → accept either direction)
    if 19 in amt and 17 in amt:
        tax = abs(amt.get(18, 0.0))
        tol = _tol(amt[19], base=3.0, rel=5e-5)
        if min(abs(amt[19] - (amt[17] - tax)), abs(amt[19] - (amt[17] + tax))) <= tol:
            res.add_pass()
        else:
            res.add_fail("pl_chain", "roman 19 identity",
                         expected=amt[19], actual=amt[17] - tax)
    else:
        res.add_skip()
    return res


def check_pl_bottomline(pl_rows: list[dict], liabilities: list[dict]) -> ValidationResult:
    """The income statement's net profit (XXV, or the group share 25.1 for a
    consolidated report) must equal the balance-sheet equity row 16.6.2 — or
    14.6.2 for participation banks (equity at XIV.)."""
    res = ValidationResult()
    cands = [r["amount"] for r in pl_rows
             if r.get("amount") is not None and _PL_NET_RX.search(r.get("item_name") or "")]
    bs_net = next((r.get("amount_total") for r in liabilities
                   if _path(r.get("hierarchy")) in ((16, 6, 2), (14, 6, 2))
                   and r.get("amount_total") is not None), None)
    if not cands or bs_net is None:
        res.add_skip()
        return res
    if any(abs(c - bs_net) <= _tol(bs_net, base=3.0, rel=1e-5) for c in cands):
        res.add_pass()
    else:
        res.add_fail("pl_bottomline", "P&L net vs BS equity (16.6.2/14.6.2)",
                     expected=bs_net, actual=cands[0])
    return res


def check_profit_loss(pl_rows: list[dict], liabilities: list[dict] | None = None) -> ValidationResult:
    """P&L structural checks: the roman identity chain, plus (when the BS
    liabilities rows are supplied) net profit = balance-sheet equity. The BS
    parent=Σchildren machinery is deliberately NOT used — P&L deduction lines
    carry "(-)" labels but additive signs, which would false-fail it."""
    res = ValidationResult()
    res.merge(check_pl_chain(pl_rows))
    if liabilities is not None:
        res.merge(check_pl_bottomline(pl_rows, liabilities))
    return res


def upsert_validation(conn, bank: str, period: str, kind: str,
                      results: dict[str, ValidationResult]) -> None:
    """Persist per-statement results; replaces the partition idempotently."""
    conn.execute(
        "DELETE FROM bank_audit_validation WHERE bank_ticker=? AND period=? AND kind=?",
        (bank, period, kind))
    conn.executemany(
        "INSERT INTO bank_audit_validation (bank_ticker, period, kind, statement, "
        " checks_passed, checks_failed, checks_skipped, failed_detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(bank, period, kind, stmt, r.passed, r.failed, r.skipped, r.detail_json())
         for stmt, r in results.items()])


def validate_report(rep) -> dict[str, ValidationResult]:
    """Validate one extracted BankReport (assets, liabilities, cross, P&L, off-balance, OCI)."""
    assets = rows_from_statement_rows(rep.bs_assets)
    liabilities = rows_from_statement_rows(rep.bs_liabilities)
    off_balance = rows_from_statement_rows(rep.off_balance)
    pl = rows_from_pl_statement_rows(rep.profit_loss)
    oci = rows_from_pl_statement_rows(getattr(rep, "other_comprehensive_income", []))
    return {
        "assets": validate_statement(assets),
        "liabilities": validate_statement(liabilities),
        "cross": check_cross_statement(assets, liabilities),
        "profit_loss": check_profit_loss(pl, liabilities),
        "off_balance": validate_off_balance(off_balance),
        "oci": check_oci(oci, pl),
    }


# ===========================================================================
# OCI (Other Comprehensive Income) validation
# ===========================================================================

def check_oci(oci_rows: list[dict], pl_rows: list[dict] | None = None) -> ValidationResult:
    """OCI: numeric hierarchy sums (2.1/2.2 trees) + roman chain III=I+II +
    cross-check OCI.I == P&L net (row XXV)."""
    res = ValidationResult()
    if not oci_rows:
        res.add_skip()
        return res
    # check_hierarchy_sums expects "amount_total" — adapt the single-column OCI rows
    oci_adapted = [{"hierarchy": r.get("hierarchy"), "item_name": r.get("item_name"),
                    "amount_total": r.get("amount")} for r in oci_rows]
    res.merge(check_hierarchy_sums(oci_adapted))
    # Roman chain III = I + II  (the TOPLAM KAPSAMLI GELİR row)
    roman_amt: dict[int, float] = {}
    for r in oci_rows:
        h = (r.get("hierarchy") or "").strip()
        if not _ROMAN_RX.match(h):
            continue
        a = r.get("amount")
        o = _roman_to_int(h.rstrip("."))
        if o is not None and a is not None:
            roman_amt.setdefault(o, a)
    if 1 in roman_amt and 2 in roman_amt and 3 in roman_amt:
        expected = roman_amt[1] + roman_amt[2]
        tol = _tol(roman_amt[3], base=3.0, rel=5e-5)
        if abs(roman_amt[3] - expected) <= tol:
            res.add_pass()
        else:
            res.add_fail("oci_chain", "OCI III = I + II",
                         expected=expected, actual=roman_amt[3])
    else:
        res.add_skip()
    # Cross-check: OCI.I must equal P&L net (XXV / row 25)
    if pl_rows is not None:
        oci_i = roman_amt.get(1)
        pl_net = _pl_spine(pl_rows).get(25)
        if oci_i is not None and pl_net is not None:
            tol = _tol(pl_net, base=3.0, rel=1e-5)
            if abs(oci_i - pl_net) <= tol:
                res.add_pass()
            else:
                res.add_fail("oci_cross", "OCI.I == P&L XXV (net profit)",
                             expected=pl_net, actual=oci_i)
        else:
            res.add_skip()
    return res


# ===========================================================================
# §4 capital adequacy validation
# ===========================================================================

_CAP_TOL = 0.02  # relative tolerance for CET1≤Tier1≤Total ordering checks
_CAP_CAR_TOL = 2.0  # ±2 percentage-point tolerance for CAR reconciliation;
                     # BRSA floor overrides cause reported CAR to differ from
                     # Total_Capital/RWA*100 by up to ~2pp across many banks


def check_capital(rows: list[dict]) -> ValidationResult:
    """Capital adequacy: CET1 ≤ Tier1 ≤ Total Capital, and CAR = Total/RWA*100."""
    res = ValidationResult()
    cur = next((r for r in rows if r.get("period_type") == "current"), None)
    if cur is None:
        res.add_skip()
        return res
    cet1 = cur.get("cet1_capital")
    t1   = cur.get("tier1_capital")
    tc   = cur.get("total_capital")
    rwa  = cur.get("total_rwa")
    car  = cur.get("capital_adequacy_ratio")
    # CET1 ≤ Tier1
    if cet1 is not None and t1 is not None:
        if cet1 <= t1 * (1 + _CAP_TOL):
            res.add_pass()
        else:
            res.add_fail("cap_tier_order", "CET1 ≤ Tier1", expected=t1, actual=cet1)
    else:
        res.add_skip()
    # Tier1 ≤ Total Capital
    if t1 is not None and tc is not None:
        if t1 <= tc * (1 + _CAP_TOL):
            res.add_pass()
        else:
            res.add_fail("cap_tier_order", "Tier1 ≤ Total Capital", expected=tc, actual=t1)
    else:
        res.add_skip()
    # CAR = Total Capital / RWA * 100 (±2pp absolute tolerance for BRSA floors)
    if tc is not None and rwa is not None and car is not None and rwa > 0:
        implied = tc / rwa * 100
        tol = _CAP_CAR_TOL
        if abs(implied - car) <= tol:
            res.add_pass()
        else:
            res.add_fail("cap_car_reconcile", "CAR = Total Capital / RWA * 100",
                         expected=implied, actual=car)
    else:
        res.add_skip()
    # CAR within plausible band [5, 80]
    if car is not None:
        if 5 <= car <= 80:
            res.add_pass()
        else:
            res.add_fail("cap_car_band", "CAR plausible band [5, 80]%",
                         expected=12.0, actual=car)
    else:
        res.add_skip()
    return res


# ===========================================================================
# §4 liquidity validation
# ===========================================================================

def check_liquidity(rows: list[dict]) -> ValidationResult:
    """Liquidity ratios: leverage < 30%, LCR/NSFR within plausible bands."""
    res = ValidationResult()
    cur = next((r for r in rows if r.get("period_type") == "current"), None)
    if cur is None:
        res.add_skip()
        return res
    lev  = cur.get("leverage_ratio")
    lcr  = cur.get("lcr_total")
    nsfr = cur.get("nsfr")
    if lev is not None:
        if 0 < lev < 30:
            res.add_pass()
        else:
            res.add_fail("liq_leverage_band", "leverage ∈ (0, 30)%",
                         expected=5.0, actual=lev)
    else:
        res.add_skip()
    for name, val in (("LCR", lcr), ("NSFR", nsfr)):
        if val is None:
            res.add_skip()
            continue
        if not (0 < val < 2000):
            res.add_fail("liq_ratio_band", f"{name} ∈ (0, 2000)%",
                         expected=100.0, actual=val)
        elif val < 50:
            # sub-50% LCR is the fingerprint of a mis-grabbed value
            res.add_fail("liq_ratio_low", f"{name} {val:.1f}% implausibly low",
                         expected=100.0, actual=val)
        else:
            res.add_pass()
    return res


# ===========================================================================
# IFRS-9 credit-quality validation
# ===========================================================================

def _nonnull_sum(*vals: float | None) -> float | None:
    """Sum of values; returns None if ALL are None, else treats None as 0."""
    non_none = [v for v in vals if v is not None]
    return sum(non_none) if non_none else None


def check_credit_quality(rows: list[dict]) -> ValidationResult:
    """Credit quality: per section total=S1+S2+S3.
    Cross-section: loans_amounts.total ≈ loans_by_stage(S1+S2)+npl_brsa_gross(S3).
    Note: npl_brsa gross−provision=net is NOT checked — BRSA provision rows include
    general/collective reserves and collateral adjustments that make the identity
    unreliable across bank presentation formats (~30% of partitions fail it)."""
    res = ValidationResult()
    by_sect: dict[str, dict] = {}
    for r in rows:
        if r.get("period_type") == "current":
            by_sect[r.get("section") or ""] = r
    if not by_sect:
        res.add_skip()
        return res
    # Per section: total = S1 + S2 + S3 (when all four are non-null)
    for sect, r in by_sect.items():
        s1  = r.get("stage1_amount")
        s2  = r.get("stage2_amount")
        s3  = r.get("stage3_amount")
        tot = r.get("total_amount")
        if s1 is None or s2 is None or s3 is None or tot is None:
            res.add_skip()
            continue
        expected = s1 + s2 + s3
        tol = _tol(tot, base=3.0, rel=5e-5)
        if abs(expected - tot) <= tol:
            res.add_pass()
        else:
            res.add_fail("cq_section_total", f"{sect}: total = S1+S2+S3",
                         expected=tot, actual=expected)
    # Cross-section: loans_amounts.total ≈ loans_by_stage(S1+S2) + npl_brsa_gross(S3)
    la   = by_sect.get("loans_amounts")
    lbs  = by_sect.get("loans_by_stage")
    nplg = by_sect.get("npl_brsa_gross")
    if la and lbs and nplg:
        la_tot  = la.get("total_amount")
        lbs_s12 = _nonnull_sum(lbs.get("stage1_amount"), lbs.get("stage2_amount"))
        nplg_tot = nplg.get("total_amount")
        if la_tot and lbs_s12 is not None and nplg_tot is not None:
            expected = lbs_s12 + nplg_tot
            tol = _tol(la_tot, base=1000.0, rel=0.005)
            if abs(la_tot - expected) <= tol:
                res.add_pass()
            else:
                res.add_fail("cq_cross_amounts",
                             "loans_amounts ≈ loans_by_stage(S1+S2) + npl_brsa_gross(S3)",
                             expected=expected, actual=la_tot)
        else:
            res.add_skip()
    else:
        res.add_skip()
    return res


# ===========================================================================
# IFRS-9 stages (derived table) validation
# ===========================================================================

def check_stages(rows: list[dict]) -> ValidationResult:
    """Stages: total sums (amounts + ECL), coverage ∈ [0,1], no NPL=100% fingerprint."""
    res = ValidationResult()
    cur = [r for r in rows if r.get("period_type") == "current"]
    if not cur:
        res.add_skip()
        return res
    for r in cur:
        s1   = r.get("stage1_amount")
        s2   = r.get("stage2_amount")
        s3   = r.get("stage3_amount")
        tot  = r.get("total_amount")
        e1   = r.get("stage1_ecl")
        e2   = r.get("stage2_ecl")
        e3   = r.get("stage3_ecl")
        etot = r.get("total_ecl")
        # total_amount = S1 + S2 + S3
        if s1 is not None and s2 is not None and s3 is not None and tot is not None:
            expected = s1 + s2 + s3
            tol = _tol(tot, base=3.0, rel=5e-5)
            if abs(expected - tot) <= tol:
                res.add_pass()
            else:
                res.add_fail("stages_total_amount", "total_amount = S1+S2+S3",
                             expected=tot, actual=expected)
        else:
            res.add_skip()
        # total_ecl = E1 + E2 + E3
        if e1 is not None and e2 is not None and e3 is not None and etot is not None:
            expected = e1 + e2 + e3
            tol = _tol(abs(etot), base=3.0, rel=5e-5)
            if abs(expected - etot) <= tol:
                res.add_pass()
            else:
                res.add_fail("stages_total_ecl", "total_ecl = E1+E2+E3",
                             expected=etot, actual=expected)
        else:
            res.add_skip()
        # Coverage ∈ [0, 1] per stage
        for label, cov in (("s1", r.get("stage1_coverage")),
                            ("s2", r.get("stage2_coverage")),
                            ("s3", r.get("stage3_coverage"))):
            if cov is None:
                res.add_skip()
            elif -1e-6 <= cov <= 1.0:  # -1e-6 floor absorbs floating-point -0.0
                res.add_pass()
            else:
                res.add_fail("stages_coverage", f"stage {label} coverage ∈ [0, 1]",
                             expected=0.5, actual=cov)
        # NPL=100% fingerprint: stage3 ≈ total while S1+S2 ≈ 0 → broken extraction
        if (s1 is not None and s2 is not None and s3 is not None
                and tot is not None and abs(tot) > 0):
            if abs(s3) >= abs(tot) * 0.999 and abs(s1 + s2) < abs(tot) * 0.001:
                res.add_fail("stages_npl100",
                             "stage3 == total (S1+S2 ≈ 0): broken extraction fingerprint",
                             expected=abs(tot) * 0.5, actual=s3)
            else:
                res.add_pass()
        else:
            res.add_skip()
    return res


# ===========================================================================
# NPL movement validation
# ===========================================================================

def check_npl_movement(rows: list[dict]) -> ValidationResult:
    """NPL movement: opening + flows = closing, per BRSA group (III/IV/V).

    Skip a group row when write_offs, sold, or transfers_out is NULL: those
    columns are often not extracted (extractor gap) and treating them as 0
    causes false failures when they are genuinely non-zero in the report.
    fx_diff is treated as 0 when NULL — it's absent in most BRSA formats.
    """
    res = ValidationResult()
    cur = [r for r in rows if r.get("period_type") == "current"]
    if not cur:
        res.add_skip()
        return res
    for r in cur:
        op = r.get("opening_balance")
        cl = r.get("closing_balance")
        if op is None or cl is None:
            res.add_skip()
            continue
        # Can't verify the equation when key flow columns are missing
        if r.get("write_offs") is None or r.get("sold") is None or r.get("transfers_out") is None:
            res.add_skip()
            continue
        additions   = r.get("additions")    or 0.0
        t_in        = r.get("transfers_in") or 0.0
        t_out       = r["transfers_out"]
        collections = r.get("collections")  or 0.0
        writeoffs   = r["write_offs"]
        sold        = r["sold"]
        fx          = r.get("fx_diff")      or 0.0
        implied = op + additions + t_in - t_out - collections - writeoffs - sold + fx
        tol = _tol(abs(cl), base=100.0, rel=0.002)
        if abs(implied - cl) <= tol:
            res.add_pass()
        else:
            grp = r.get("group_code") or ""
            res.add_fail("npl_movement", f"group {grp}: opening + flows = closing",
                         expected=cl, actual=implied)
    return res


# ===========================================================================
# Loans by sector validation
# ===========================================================================

# Each sector group has a preferred aggregate key and a set of sub-keys.
# If the aggregate is absent but sub-keys are present, sum the sub-keys instead
# (some banks skip the sub-total row and only print the detail lines).
_SECTOR_GROUPS: list[tuple[str, frozenset]] = [
    ("agri_total",  frozenset({"agri_farming", "agri_fishery", "agri_forestry", "agri_other"})),
    ("mfg_total",   frozenset({"mfg_mining", "mfg_production", "mfg_utilities", "mfg_other"})),
    ("svc_total",   frozenset({"svc_trade", "svc_hospitality", "svc_transport", "svc_financial",
                               "svc_realestate", "svc_professional", "svc_health",
                               "svc_education", "svc_other"})),
]
_SECTOR_STANDALONE = frozenset({"construction", "other"})


def _resolved_top_level(cur_rows: list[dict]) -> list[dict]:
    """Return sector rows that together cover the non-total, non-overlapping sectors.

    For each group (agri/mfg/svc): use the group-total row if present, otherwise
    use the individual sub-sector rows.  Standalone sectors (construction, other)
    are always included if present.
    """
    by_sector = {r["sector"]: r for r in cur_rows if r.get("sector")}
    result = []
    for total_key, subs in _SECTOR_GROUPS:
        if total_key in by_sector:
            result.append(by_sector[total_key])
        else:
            result.extend(by_sector[k] for k in subs if k in by_sector)
    for key in _SECTOR_STANDALONE:
        if key in by_sector:
            result.append(by_sector[key])
    return result


def check_loans_by_sector(rows: list[dict]) -> ValidationResult:
    """Loans by sector: sum of top-level sectors ≈ total row, per amount column.

    Falls back to sub-sector rows when a group aggregate (agri_total, mfg_total,
    svc_total) is absent — some banks omit the sub-total line but print the detail.
    """
    res = ValidationResult()
    cur = [r for r in rows if r.get("period_type") == "current"]
    if not cur:
        res.add_skip()
        return res
    total_row = next((r for r in cur if r.get("sector") == "total"), None)
    if total_row is None:
        res.add_skip()
        return res
    top_rows = _resolved_top_level(cur)
    if not top_rows:
        res.add_skip()
        return res
    any_check = False
    for col in ("stage2_amount", "stage3_amount"):  # ecl_amount excluded: collective provisioning ≠ sector-exact
        tot_val = total_row.get(col)
        if tot_val is None:
            res.add_skip()
            continue
        col_vals = [r.get(col) for r in top_rows if r.get(col) is not None]
        if not col_vals:
            res.add_skip()
            continue
        sector_sum = sum(col_vals)
        tol = _tol(abs(tot_val), base=1000.0, rel=0.005)
        if abs(sector_sum - tot_val) <= tol:
            res.add_pass()
        else:
            res.add_fail("loans_sector_total", f"{col}: Σ top-level sectors ≠ total",
                         expected=tot_val, actual=sector_sum)
        any_check = True
    if not any_check:
        res.add_skip()
    return res
