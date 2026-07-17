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
    # one row per roman ordinal (duplicates would double-count). On a collision
    # keep the LARGER-magnitude contribution: a stray page-header / bank-name row
    # captured with a numeric hierarchy ("5", amount 0) must not displace the real
    # section it shares an ordinal with — the ISCTR 2025Q4 off_balance case, where
    # a header read as hierarchy "5" hid section V (5.97bn) from the roman sum.
    seen: dict[int, float] = {}
    for r in romans:
        amt = _contribution(r)
        if amt is None:
            continue
        ordn = _path(r["hierarchy"])[0]
        if ordn not in seen or abs(amt) > abs(seen[ordn]):
            seen[ordn] = amt
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
    # ±10 thousand TL flat, NOT the old 0.5%. A balance sheet balances by
    # construction, and the corpus says so with no hedging: the maximum
    # |assets − liabilities| across all 1,050 partitions is EXACTLY 0.000000 —
    # not "within tolerance", zero, including the 16 that fall back to the roman
    # sum. The 0.5% band was therefore pure slack, tolerating a median ₺1.11bn
    # and up to ₺48.2bn (ZIRAAT 2026Q1) of undetected error on data whose real
    # dispersion is nil. base=10 matches the module's other two top-of-tree total
    # checks (check_statement_total, check_b_block), costs nothing today (exact
    # equality also flags 0/1050) and leaves room for a future filer's print
    # rounding. At ZIRAAT scale this is ~4.8 million times tighter.
    if abs(a - li) <= _tol(a, base=10.0, rel=0.0):
        res.add_pass()
    else:
        res.add_fail("cross_statement", "assets vs liabilities+equity",
                     expected=a, actual=li)
    return res


def check_no_duplicate_hierarchy(rows: list[dict]) -> ValidationResult:
    """V5 — no two DISTINCT line items share one numeric hierarchy key.

    A source mislabel or an extractor misfile lands two different rows on the
    same key; the parent=Σchildren check can miss it when the misfiled row's
    TRUE parent has no other captured children (so nothing contradicts). The
    EXIM/VAKBN off-balance case is exactly this: the Forward-FX Sell leg is
    stamped 3.2.2.2 in the filing, colliding with the real Swap-Sell at 3.2.2.2.
    Corpus-calibrated to zero false positives: fires only when the rows on one
    key carry DIFFERENT names AND at least two of them a non-zero total — an
    all-zero template row legitimately repeats, and a trailing-dot spelling of
    the same label ("2.1" / "2.1.") is the same item, not a collision.
    """
    res = ValidationResult()
    by_key: dict[tuple[int, ...], list[dict]] = {}
    for r in rows:
        p = _path(r.get("hierarchy"))
        if p is not None and len(p) >= 2:  # skip len-1: roman/numeric top-levels alias
            by_key.setdefault(p, []).append(r)
    for key, rs in by_key.items():
        names = {(r.get("item_name") or "").strip().casefold() for r in rs}
        nonzero = sum(1 for r in rs if (r.get("amount_total") or 0) != 0)
        if len(names) > 1 and nonzero >= 2:
            hstr = ".".join(str(x) for x in key)
            res.add_fail("dup_hierarchy",
                         f"{hstr}: {len(rs)} distinct rows on one key",
                         expected=1, actual=len(names))
        else:
            res.add_pass()
    return res


def _letter_amt(rows: list[dict], letter: str) -> float | None:
    """The amount of a letter-block row ("A." / "B.")."""
    for r in rows:
        if ((r.get("hierarchy") or "").strip().rstrip(".").upper() == letter
                and r.get("amount_total") is not None):
            return r["amount_total"]
    return None


def _roman_amt(rows: list[dict], ordinal: int) -> float | None:
    """One roman section's contribution, or None if absent. Largest magnitude on
    an ordinal collision — mirrors _statement_total, where a stray header row
    captured with a real section's ordinal must not displace it (ISCTR 2025Q4)."""
    best = None
    for r in rows:
        if _path(r.get("hierarchy")) == (ordinal,):
            a = _contribution(r)
            if a is not None and (best is None or abs(a) > abs(best)):
                best = a
    return best


def check_b_block(rows: list[dict]) -> ValidationResult:
    """V7 (off-balance) — the B. custody/pledged block = Σ its roman sections
    (IV+V+VI).

    This is the check V6 was supposed to be. V6 reconciles the "(A+B)" grand
    total against A + B and claims in its own docstring to catch a wholly dropped
    custody block — but it cannot: removing B deletes V6's own operand, so it
    flips from RUN to SKIP on 887/887 partitions and reports green. Measured
    0/259 detection. A check cannot detect the loss of its own input.

    V7 works because B is the operand it checks AGAINST, not one it needs
    present: it sums whichever of IV/V/VI survive and compares to the printed B.
    A section that is legitimately absent contributes 0 and B foots anyway; a
    section that was DROPPED leaves the sum short and it fails. That also puts a
    guard on the largest unconstrained number in the corpus — VAKBN 2026Q1 unco's
    roman VI "KABUL EDİLEN AVALLER VE KEFALETLER", ₺92.7trn, which no identity
    reads today (V2 skips it for want of captured children; V3 never runs here).

    A = I+II+III is deliberately NOT checked: it holds on only 920/977 (94.2%),
    the 57 exceptions being the stable TEB-consolidated ~76% structural offset
    that validate_off_balance's docstring already documents. B holds 1,046/1,046
    (100.0%), and the report itself prints the formula in the label on 1,003.
    """
    res = ValidationResult()
    b = _letter_amt(rows, "B")
    parts = [a for a in (_roman_amt(rows, o) for o in (4, 5, 6)) if a is not None]
    if b is None or not parts:
        res.add_skip()
        return res
    total = sum(parts)
    if abs(total - b) <= _tol(b, base=10.0, rel=5e-5):
        res.add_pass()
    else:
        res.add_fail("off_balance_b_block", "B. block vs Σ romans IV+V+VI",
                     expected=b, actual=total)
    return res


def check_grand_total_ab(rows: list[dict]) -> ValidationResult:
    """V6 (off-balance) — labelled grand total "(A+B)" = letter-block A + B.

    A robust top-of-tree reconciliation that the roman-section total check (V3)
    can't do on an off-balance sheet: the grand total sums an A. commitments
    block and a B. custody/pledged block, and dropping the WHOLE B block (silent
    section loss — the failure mode V2 can't see, since every surviving row's
    parent-sum still foots) shows up only as A+B ≠ total. Uses the letter
    aggregates the report itself prints, so it sidesteps the structural offset
    that made V3 unusable here. Corpus: 889 statements reconcile exactly, 0
    mismatch; skips (never fails) the 160 whose A/B/total labels differ.
    """
    res = ValidationResult()
    a, b, tot = _letter_amt(rows, "A"), _letter_amt(rows, "B"), None
    for r in rows:
        name = (r.get("item_name") or "").upper().replace(" ", "")
        if "(A+B)" in name and r.get("amount_total") is not None:
            if tot is None or abs(r["amount_total"]) > abs(tot):
                tot = r["amount_total"]
    if a is None or b is None or tot is None:
        res.add_skip()
        return res
    if abs((a + b) - tot) <= _tol(tot, base=10.0, rel=5e-5):
        res.add_pass()
    else:
        res.add_fail("grand_total_ab", "(A+B) grand total vs A + B",
                     expected=tot, actual=a + b)
    return res


def validate_statement(rows: list[dict]) -> ValidationResult:
    """All single-statement checks for one BS statement's rows (V1–V3, V5)."""
    res = ValidationResult()
    res.merge(check_row_triplets(rows))
    res.merge(check_hierarchy_sums(rows))
    res.merge(check_statement_total(rows))
    res.merge(check_no_duplicate_hierarchy(rows))
    return res


def validate_off_balance(rows: list[dict]) -> ValidationResult:
    """Off-balance sheet: row triplets (V1) + hierarchy sums (V2).

    V2 is safe here despite the skip-level numbering (a '1.1' bridging '1.' and
    '1.1.1' is sometimes absent): check_hierarchy_sums SKIPS a parent with no
    captured children rather than failing it, so the gaps never false-fail. What
    it does catch is the dropped-child class this module exists for — verified
    against the corpus, every off-balance V2 failure is a real defect:
      * a "Forward FX Buy/Sell" line whose Sell leg (x.x.2) was not extracted
        foots to ~half its parent (EXIM, VAKBN 2022);
      * a dropped commitment / derivative sub-item (TSKB, EMLAK, FIBA, ALNTF);
      * a page-header or column-header line captured with a spurious numeric
        hierarchy (ISCTR 2025Q4 "5"; HAYATK "TL FC Total…" title rows) whose
        real siblings then overrun the phantom parent.

    V3 (labelled TOTAL = Σ top-level sections) is deliberately NOT run. The
    off-balance grand total sums an A. commitments / B. custody-and-pledged
    split whose custody side is not reported as plain numeric top-level rows,
    so V3 mismatches by a STABLE per-bank offset every quarter (TEB ~35%,
    DENIZ/YKBNK ~6-8%) — structural, not a bug. That drift is monitored instead
    by check_audit_quality._off_balance_consistency, which flags a sudden JUMP
    in the offset (a genuinely dropped section) but leaves a stable one alone.

    On top of V1/V2 this also runs V5 (no duplicate hierarchy key — catches the
    EXIM/VAKBN source mislabel head-on), V6 (labelled "(A+B)" grand total = A + B)
    and V7 (B. block = Σ romans IV+V+VI). All are corpus-calibrated to zero false
    positives.

    V7 exists because V6 does NOT do what its docstring claims. V6 says it catches
    a wholly dropped custody block; measured, it catches 0/259, because dropping B
    deletes V6's own operand and the check silently stops running. V7 is the one
    that actually sees a dropped section — see check_b_block.
    """
    res = ValidationResult()
    res.merge(check_row_triplets(rows))
    res.merge(check_hierarchy_sums(rows))
    res.merge(check_no_duplicate_hierarchy(rows))
    res.merge(check_grand_total_ab(rows))
    res.merge(check_b_block(rows))
    return res


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
# prints its own formula. But the ORDINALS are NOT fixed across the corpus. The
# standard template runs gross VIII / net-operating XIII / pre-tax XVII / tax
# XVIII / continuing-net XIX / discontinued-net XXIV / period-net XXV, while the
# compressed variant some participation banks file drops a row and prints
# net-operating XII / pre-tax XVI / tax XVII — then continuing-net XVIII and
# period-net XXIV (DUNYAK), or continuing-net XIX with no XVIII at all (TOMK).
# Each report states its own numbering in the formula it prints ("XVI. …VERGİ
# ÖNCESİ K/Z (XII+...+XV)"), and foots perfectly under it. Hardcoding 17/18/19/25
# therefore compared those banks' TAX row against the pre-tax sum — 9 permanent
# false failures on correct data, and no real check of their chain at all
# (2026-07-16).
#
# So the chain is assembled per-partition from ANCHOR rows located by label, and
# the deduction band falls out of the anchors — everything between gross and
# net-operating — instead of a hardcoded {9,10,11,12}. Safety: every anchor falls
# back to its standard ordinal when its label is unreadable (HAYATK 2024Q2's
# wrapped labels leave XIX as "OPERATIONS (XV±XVI)"), and the template reverts to
# standard wholesale unless the anchors come out strictly increasing. A partition
# whose labels we can't read behaves exactly as it did before.
#
# Two corpus realities make a naive ±1 chain false-fail, so the check keeps both:
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
_PL_STD = {"gross": 8, "net_op": 13, "pretax": 17,
           "tax": 18, "cont_net": 19, "period_net": 25}
# XIX = XVII ± XVIII is handled apart from the additive chain: the tax provision
# prints "(±)" and is genuinely signed (usually expense, occasionally benefit),
# so continuing-net may land on either side of pre-tax by the tax magnitude.
_PL_NET_RX = re.compile(
    r"DÖNEM NET KAR|DÖNEM NET KÂR|NET PERIOD PROFIT|DÖNEM KÂRI|Grubun|Group", re.I)

# Anchor matching runs on a folded label: Turkish glyphs mapped to ASCII, upper-
# cased, ALL whitespace stripped — the extractor emits both "DÖNEM NET KARI" and
# the space-collapsed "DÖNEMNETKARI/ZARARI" (TOMK), which a spaced pattern misses.
_PL_FOLD = str.maketrans("ıİğĞüÜşŞöÖçÇâÂîÎûÛ", "iIgGuUsSoOcCaAiIuU")
# (role, any-of these substrings, none-of these). Order matters only in that each
# roman takes the FIRST role it matches. The none-of lists do the real work: the
# discontinued block mirrors the continuing block almost word for word, and every
# subtotal from XIX down carries some form of "DÖNEM NET"/"NET PROFIT".
_PL_ROLES = (
    ("pretax",     ("VERGIONCESI", "BEFORETAX"),
                   ("DURDURULAN", "DISCONTINUED")),
    ("tax",        ("VERGIKARSILIGI", "PROVISIONFORTAX", "TAXPROVISION",
                    "PROVISIONFROMTAXES", "TAXESONINCOME"),
                   ("DURDURULAN", "DISCONTINUED")),
    ("cont_net",   ("SURDURULENFAALIYETLERDONEMNET", "FROMCONTINUEDOPERATIONS",
                    "FROMCONTINUINGOPERATIONS"),
                   ("DURDURULAN", "DISCONTINUED", "BEFORE", "VERGI", "TAX", "PROVISION")),
    ("gross",      ("FAALIYETBRUT", "GROSSOPERATINGPROFIT", "GROSSPROFIT"), ()),
    ("net_op",     ("NETFAALIYET", "NETOPERATING"), ()),
    ("period_net", ("DONEMNETKAR", "NETPROFIT", "NETINCOME"),
                   ("SURDURULEN", "DURDURULAN", "CONTINUED", "DISCONTINUED",
                    "OPERATIONS", "VERGI", "TAX")),
)


def _pl_fold(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or "").translate(_PL_FOLD)).upper()


def _pl_template(pl_rows: list[dict], amt: dict[int, float]) -> dict[str, int]:
    """The partition's OWN ordinal for each anchor role, read off the labels of
    the rows already in the spine. Roles it can't find keep their standard
    ordinal; if what comes out isn't strictly increasing the labels are lying
    (or mis-parsed) and we fall back to the standard template wholesale."""
    t = dict(_PL_STD)
    seen: set[str] = set()
    for r in pl_rows:
        h = (r.get("hierarchy") or "").strip()
        if not _ROMAN_RX.match(h):
            continue
        o = _roman_to_int(h.rstrip("."))
        if o is None or o not in amt:      # spine rows only — strays can't anchor
            continue
        lbl = _pl_fold(r.get("item_name"))
        for role, want, avoid in _PL_ROLES:
            if role in seen or any(x in lbl for x in avoid):
                continue
            if any(x in lbl for x in want):
                t[role], _ = o, seen.add(role)
                break
    # discontinued-net is the roman immediately above the bottom line in every
    # template variant filed, and its label mirrors the XX/XXI income+expense
    # rows too closely to anchor on safely.
    t["disc_net"] = t["period_net"] - 1
    order = (3, t["gross"], t["net_op"], t["pretax"], t["tax"],
             t["cont_net"], t["disc_net"], t["period_net"])
    if any(a >= b for a, b in zip(order, order[1:])):
        t = dict(_PL_STD)
        t["disc_net"] = 24
    return t


def _pl_chain(t: dict[str, int]) -> tuple[list[tuple[int, list[int]]], frozenset[int]]:
    """(additive chain, deduction ordinals) for one template. The bands between
    anchors are what the report itself sums: gross = III..gross-1, the opex
    deductions are everything from gross+1 to net_op-1, and net_op+1..pretax-1
    are the add-backs (merger income, equity-method, net monetary position)."""
    g, n, p = t["gross"], t["net_op"], t["pretax"]
    chain = [
        (3, [1, 2]),                                  # III = I − II
        (g, list(range(3, g))),                       # gross    = III+…
        (n, [g] + list(range(g + 1, n))),             # net_op   = gross − opex…
        (p, [n] + list(range(n + 1, p))),             # pre-tax  = net_op + …
        (t["period_net"], [t["cont_net"], t["disc_net"]]),
    ]
    return chain, frozenset({2} | set(range(g + 1, n)))


def _pl_spine(pl_rows: list[dict]) -> dict[int, float]:
    """Roman subtotals as {ordinal: amount}, taken from the longest strictly-
    increasing-ordinal SUBSEQUENCE of roman-form rows — the statement body.
    Discards out-of-sequence strays (title/footnote rows, captured "1 OCAK…"
    header fragments) that would otherwise shadow a real subtotal. A subsequence
    (not a contiguous run) so a single misparsed roman mid-statement — HSBC's
    "XIV." read as hierarchy "X" — drops out alone instead of severing the
    valid XV–XXV tail from the spine."""
    seq: list[tuple[int, float]] = []
    for r in pl_rows:
        h = (r.get("hierarchy") or "").strip()
        if not _ROMAN_RX.match(h):     # roman-form only; a numeric "1" never a subtotal
            continue
        a = r.get("amount")
        o = _roman_to_int(h.rstrip("."))
        if o is not None and a is not None:
            seq.append((o, a))
    if not seq:
        return {}
    # Longest strictly-increasing subsequence (O(n²) — a P&L has ~25 romans).
    # dp[j]+1 > dp[i] (strict) keeps the earliest predecessor achieving the
    # length, so the contiguous body always beats an equal-length path through
    # a stray title row.
    dp = [1] * len(seq)
    prev = [-1] * len(seq)
    for i in range(len(seq)):
        for j in range(i):
            if seq[j][0] < seq[i][0] and dp[j] + 1 > dp[i]:
                dp[i], prev[i] = dp[j] + 1, j
    end = max(range(len(seq)), key=dp.__getitem__)
    chosen: list[tuple[int, float]] = []
    while end != -1:
        chosen.append(seq[end])
        end = prev[end]
    return {o: a for o, a in reversed(chosen)}


# Dashboard-facing role map. The anchors above say WHERE each subtotal sits for a
# given filer; this turns that into a per-ROW semantic tag the Worker can read, so
# a SQL consumer never has to hardcode an ordinal. heatmap.ts did, and it cost us:
# `COALESCE(XXV., XIX.)` read DUNYAK's net profit as 0 (its period-net is XXIV, so
# the COALESCE fell through to XIX = discontinued-ops INCOME = 0) and `XI. + XII.`
# summed other-opex + net-operating-PROFIT as "opex" (2026-07-17 investigation).
#
# Emitted to bank_audit_pl_roles by scripts/revalidate_audit_db.py. Keep the
# resolution HERE — one place decides what a row means, in the language that has
# the Turkish fold. Re-deriving it in SQL means UPPER() (ASCII-only, so "Dönem net
# karı" never folds) plus hand-cut wildcards, and a second copy to drift.
_PL_OPEX_ROLES = (
    # (role, folded label fragments). Matched INSIDE the deduction band only, so a
    # like-named row elsewhere in the statement cannot claim the tag.
    ("opex_personnel", ("PERSONEL", "PERSONNEL")),
    ("opex_other", ("FAALIYETGIDERLER", "OPERATINGEXPENSE")),
)
_PL_ANCHOR_ROLES = ("gross", "net_op", "pretax", "tax", "cont_net", "disc_net", "period_net")


def pl_roles(pl_rows: list[dict]) -> dict[str, str]:
    """{hierarchy: role} for one partition — the chain anchors plus the two opex
    lines, each tagged on the row that actually carries it under THIS filer's
    numbering. Empty when there's no spine to anchor against."""
    amt = _pl_spine(pl_rows)
    if not amt:
        return {}
    t = _pl_template(pl_rows, amt)
    by_ord: dict[int, str] = {}
    for r in pl_rows:
        h = (r.get("hierarchy") or "").strip()
        if not _ROMAN_RX.match(h):
            continue
        o = _roman_to_int(h.rstrip("."))
        if o is not None and o in amt:
            by_ord.setdefault(o, h)          # spine rows only; first wins
    out: dict[str, str] = {}
    for role in _PL_ANCHOR_ROLES:
        h = by_ord.get(t[role])
        if h:
            out[h] = role
    band = [o for o in range(t["gross"] + 1, t["net_op"]) if o in by_ord]
    tagged: dict[int, str] = {}
    for o in band:
        lbl = next((_pl_fold(r.get("item_name")) for r in pl_rows
                    if (r.get("hierarchy") or "").strip() == by_ord[o]), "")
        for role, want in _PL_OPEX_ROLES:
            if any(x in lbl for x in want):
                tagged[o] = role
                break
    if len(set(tagged.values())) < 2 and len(band) >= 2:
        # Label match needs a label: AKBNK 2022Q4/2026Q1 print the whole P&L with
        # EMPTY item_names. Positional fallback — personnel and other-opex are the
        # last two rows of the deduction band in every template variant filed
        # (standard band IX–XII ends XI,XII; compressed IX–XI ends X,XI), which is
        # what the old ordinal read got right for these four partitions. Asserted
        # against the label match on the 1,046 partitions that HAVE labels
        # (test_pl_roles_positional_fallback_matches_labels).
        tagged = {band[-2]: "opex_personnel", band[-1]: "opex_other"}
    for o, role in tagged.items():
        out[by_ord[o]] = role
    return out


def check_pl_deduction_convention(pl_rows: list[dict]) -> ValidationResult:
    """Each deduction block carries ONE storage convention, and the chain says
    which: the signed sum of the block must equal +(base − target) or
    −(base − target). Nothing in between is possible.

    This is the check that pins the sign, and the reason it is separate from
    check_pl_chain is that the chain CANNOT do it. The chain accepts a deduction
    identity if EITHER `Σ|v| == D` (subtract the magnitudes) or `Σv == D`
    (subtract the stored values) foots. The first reading is **sign-blind by
    construction** — flipping a line's sign leaves its magnitude untouched, so
    the identity sails through. Measured: flipping one deduction's stored sign is
    caught 29/300 (10%) by the chain and 299/300 (100%) here.

    The sign is not decoration. pl-sankey.ts deliberately does NOT abs() the
    deduction stack (lib/pl-sankey.ts:150-168): a genuine ECL RELEASE (BURGAN) or
    provision write-back (DENIZ) is stored with the opposite sign and must be
    ADDED back, and abs()-ing it double-counted the swing until the VIII→XIII
    identity failed by ~190%. So a wrong stored sign renders a wrong chart.

    Why ±D and not a fixed convention: the corpus genuinely uses both. Most banks
    print the magnitude and carry the "(-)" in the label; ING/KLNMA/PASHA and the
    participation banks parenthesise the value itself and therefore store a
    negative. TFKB mixes the two WITHIN one statement (II positive, IX–XII
    negative), which is why this is applied per identity-block rather than per
    statement. What is NOT allowed is a block that matches neither — that is a
    line whose sign contradicts its own block.

    A genuine reversal is still fine, and this is the subtle part: a released
    provision inside a positive-convention block stores negative and REDUCES Σv
    by exactly the amount the block's net deduction D falls, so Σv == D still
    holds. The check constrains the block's total against the chain, not each
    line's sign against a rule — so it accepts every faithful reversal and
    rejects a flip.

    Corpus: 1048/1048 pass, 0 flags. Independently corroborated — the convention
    this derives agrees with pl-sankey.ts's own anchor heuristic (personnel XI.,
    else II., else XII.) on 1048/1048, so the UI has been guessing right; this
    makes the guess checkable instead of assumed.

    NOT covered, stated so it isn't assumed: only the block's SUM is constrained,
    so moving value between two lines of one block is invisible (the same-band
    swap, 0/299). And the TAX sign stays free — the chain pins |tax| via
    cont_net = pretax ± tax but genuinely cannot pick the side, since tax is an
    expense in most quarters and a benefit in some. That one is inert rather than
    unfixable: pl-sankey.ts:220 does `Math.abs(ix.get("XVIII.") ?? 0)`, the only
    consumer that reads it.
    """
    res = ValidationResult()
    amt = _pl_spine(pl_rows)
    if not amt:
        res.add_skip()
        return res
    tpl = _pl_template(pl_rows, amt)
    chain, deductions = _pl_chain(tpl)
    for target, sources in chain:
        ded_ords = [s for s in sources if s in deductions]
        if not ded_ords:
            continue        # gross / pre-tax / period-net are pure sums — N/A here
        ded = [amt[s] for s in ded_ords if s in amt]
        base_ords = [s for s in sources if s not in deductions]
        if (target not in amt or not ded
                or any(o not in amt for o in base_ords)):
            res.add_skip()
            continue
        d = sum(amt[o] for o in base_ords) - amt[target]   # the net deduction
        s = sum(ded)                                       # as stored, signed
        tol = _tol(d, base=3.0, rel=5e-5)
        if abs(s - d) <= tol or abs(s + d) <= tol:
            res.add_pass()
        else:
            res.add_fail("pl_deduction_convention",
                         f"roman {target}: signed Σ(deductions) must be ±(base − target)",
                         expected=d, actual=s)
    return res


def check_pl_chain(pl_rows: list[dict]) -> ValidationResult:
    """The income-statement roman identities (III=I−II … period-net=cont+disc),
    each read against the partition's OWN numbering (see module note). An
    identity runs only when its target and ALL its source romans are present, so
    a P&L missing optional rows skips rather than false-fails. Deduction
    identities accept either storage convention (see module note)."""
    res = ValidationResult()
    amt = _pl_spine(pl_rows)
    tpl = _pl_template(pl_rows, amt)
    chain, deductions = _pl_chain(tpl)
    # A missing subtotal must fail, not vanish. Every identity below skips when a
    # source is absent, so a dropped roman erased its own constraint — drop
    # detection was 10/300 (3%). These anchors resolve AND are present in
    # 1050/1050 partitions (checked against each filer's OWN numbering, so the
    # compressed template is not penalised), which makes their absence never
    # faithful. Corpus: 2 flags, both real and both already known — ODEA 2023Q3
    # unco and TSKB 2025Q2 unco lose net-operating to a wrapped label.
    #
    # disc_net is deliberately NOT required: 11 partitions genuinely omit it
    # (ANADOLU ×6, HSBC ×2, HAYATK, QNBFB, ZIRAATK) because a bank with no
    # discontinued operations does not print the row.
    for role in ("gross", "net_op", "pretax", "tax", "cont_net", "period_net"):
        if tpl[role] not in amt:
            res.add_fail("pl_roman_missing",
                         f"P&L {role} (roman {tpl[role]}) absent from the spine",
                         expected=0.0, actual=0.0)
    for target, sources in chain:
        if target not in amt or any(s not in amt for s in sources):
            res.add_skip()
            continue
        base = sum(amt[s] for s in sources if s not in deductions)
        ded = [amt[s] for s in sources if s in deductions]
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
    # continuing-net = pre-tax ± tax (tax genuinely signed → accept either way)
    cont, pre = tpl["cont_net"], tpl["pretax"]
    if cont in amt and pre in amt:
        tax = abs(amt.get(tpl["tax"], 0.0))
        tol = _tol(amt[cont], base=3.0, rel=5e-5)
        if min(abs(amt[cont] - (amt[pre] - tax)), abs(amt[cont] - (amt[pre] + tax))) <= tol:
            res.add_pass()
        else:
            res.add_fail("pl_chain", f"roman {cont} identity",
                         expected=amt[cont], actual=amt[pre] - tax)
    else:
        res.add_skip()
    return res


def check_pl_bottomline(pl_rows: list[dict], liabilities: list[dict]) -> ValidationResult:
    """The income statement's net profit (XXV, or the group share 25.1 for a
    consolidated report) must equal the balance-sheet equity row 16.6.2 — or
    14.6.2 for participation banks (equity at XIV.).

    Candidates come from the label regex AND from hierarchy (spine roman XXV +
    row 25.1): the English template prints "NET PROFIT/LOSS", participation
    banks "NET DÖNEM KARI/ZARARI", and some partitions lose labels entirely —
    all invisible to a label regex, which silently skipped this check for 21%
    of the corpus (2026-07 audit)."""
    res = ValidationResult()
    cands = [r["amount"] for r in pl_rows
             if r.get("amount") is not None and _PL_NET_RX.search(r.get("item_name") or "")]
    spine = _pl_spine(pl_rows)
    # The filer's OWN period-net ordinal, not a hardcoded 25 (see check_oci).
    # Harmless today — the compressed-template partitions still supply a label
    # candidate via _PL_NET_RX, so this check runs and passes for them either way
    # — but it should not depend on that luck.
    _pn = _pl_template(pl_rows, spine)["period_net"] if spine else None
    if _pn in spine:
        cands.append(spine[_pn])
    cands += [r["amount"] for r in pl_rows
              if r.get("amount") is not None and _path(r.get("hierarchy")) == (25, 1)]
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
    res.merge(check_pl_deduction_convention(pl_rows))
    if liabilities is not None:
        res.merge(check_pl_bottomline(pl_rows, liabilities))
    return res


def upsert_pl_roles(conn, bank: str, period: str, kind: str,
                    pl_rows: list[dict]) -> int:
    """Persist the derived P&L role map for one partition; replaces it
    idempotently. Rebuilt from stored rows wherever validation is (the two are
    derived from the same rows and must never disagree about a partition), so a
    consumer joining bank_audit_pl_roles always sees the current resolution."""
    conn.execute(
        "DELETE FROM bank_audit_pl_roles WHERE bank_ticker=? AND period=? AND kind=?",
        (bank, period, kind))
    roles = pl_roles(pl_rows)
    conn.executemany(
        "INSERT INTO bank_audit_pl_roles (bank_ticker, period, kind, hierarchy, role, derived_at) "
        "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        [(bank, period, kind, h, role) for h, role in roles.items()])
    return len(roles)


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


def statement_passes(conn, bank: str, period: str, kind: str, statement: str) -> bool:
    """True iff the stored validation for this (partition, statement) is clean —
    at least one check passed and none failed. This is the "is this data already
    correct?" signal used to protect validated rows from being overwritten by a
    re-extract (a partition with no validation row, or one that only skipped, is
    NOT considered passing — re-extraction proceeds normally)."""
    row = conn.execute(
        "SELECT checks_passed, checks_failed FROM bank_audit_validation "
        "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
        (bank, period, kind, statement)).fetchone()
    return bool(row and row[1] == 0 and row[0] > 0)


def _prior_rows(stmt_rows) -> list[dict]:
    """The PRIOR-period column of a 6-column statement as validator dicts. The
    report prints prior TL/FC/Total independently of the current column, so its
    own triplets and parent-sums are a second, free identity set — a value error
    the current column happens to foot through still has to survive the prior
    column too."""
    return [{"hierarchy": r.hierarchy, "item_name": r.name,
             "amount_tl": r.pri_tl, "amount_fc": r.pri_fc, "amount_total": r.pri_total}
            for r in stmt_rows]


def validate_report(rep, period: str | None = None) -> dict[str, ValidationResult]:
    """Validate one extracted BankReport (all statement types)."""
    assets = rows_from_statement_rows(rep.bs_assets)
    liabilities = rows_from_statement_rows(rep.bs_liabilities)
    off_balance = rows_from_statement_rows(rep.off_balance)
    pl = rows_from_pl_statement_rows(rep.profit_loss)
    oci = rows_from_pl_statement_rows(getattr(rep, "other_comprehensive_income", []))
    cf = rows_from_pl_statement_rows(getattr(rep, "cash_flow", []))
    eq_rep = getattr(rep, "equity_change", None)
    eq_rows = rows_from_equity_rows(eq_rep) if eq_rep else []
    results = {
        "assets": validate_statement(assets),
        "liabilities": validate_statement(liabilities),
        "cross": check_cross_statement(assets, liabilities),
        "profit_loss": check_profit_loss(pl, liabilities),
        "off_balance": validate_off_balance(off_balance),
        "oci": check_oci(oci, pl),
        "cash_flow": check_cash_flow(cf),
        "equity_change": check_equity_change(eq_rows, oci_rows=oci,
                                              liabilities=liabilities, period=period),
    }
    # Prior-period column: an independently-printed number set validated nowhere
    # else (the DB stores only the current column). Merge its row triplets and
    # parent-sums into the owning 6-column statement's result — only when the
    # column is actually populated (some banks file a single-period statement).
    for key, stmt_rows in (("assets", rep.bs_assets),
                           ("liabilities", rep.bs_liabilities),
                           ("off_balance", rep.off_balance)):
        prior = _prior_rows(stmt_rows)
        if any(r["amount_total"] is not None for r in prior):
            results[key].merge(check_row_triplets(prior))
            results[key].merge(check_hierarchy_sums(prior))
    return results


# ===========================================================================
# OCI (Other Comprehensive Income) validation
# ===========================================================================

# The OCI statement's entire template: romans I/II/III + the 2.x sub-tree. Kept
# in step with oci._OCI_TEMPLATE (the extractor-side guard); this is the
# detection half of the same fact.
_OCI_TEMPLATE_RX = re.compile(r"^(?:I{1,3}\.?|2(?:\.\d+){1,2}\.?)$")


def check_oci(oci_rows: list[dict], pl_rows: list[dict] | None = None) -> ValidationResult:
    """OCI: numeric hierarchy sums (2.1/2.2 trees) + roman chain III=I+II +
    cross-check OCI.I == P&L net (row XXV)."""
    res = ValidationResult()
    if not oci_rows:
        res.add_skip()
        return res
    # Every row must be ON the OCI template (romans I/II/III + the 2.x sub-tree).
    # A row outside it is a page artefact the parser swallowed — the date header
    # ("31 MART 2024 TARİHİNDE…" → hierarchy '31', name 'MART', amount 202) or the
    # statement title (→ the section's own roman 'IV.'/'V.'). 577 such rows sat in
    # 574 of 1050 partitions (55% of the corpus) and EVERY ONE read green: a stray
    # takes no part in III = I + II, so no identity ever touched it. Junk in the
    # table rather than a wrong headline — but invisible, which is the point.
    # Zero real rows fall outside the template (16,709 conform, 0 don't), so this
    # cannot fire on faithful data.
    for r in oci_rows:
        if not _OCI_TEMPLATE_RX.fullmatch((r.get("hierarchy") or "").strip()):
            res.add_fail("oci_offtemplate_row",
                         f"{r.get('hierarchy')!r} / {(r.get('item_name') or '')[:30]!r} "
                         "is not an OCI template row (page header or title)",
                         expected=0.0, actual=r.get("amount") or 0.0)
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
    # III = Σ surviving(I, II), and I/II/III are each required. Same shape and
    # same reason as check_cash_flow: the old `if 1 and 2 and 3 in roman_amt`
    # SKIPPED whenever a roman was dropped, so the loss erased its own check —
    # measured 0/296 detection. All three are present in ~1049/1049, so an
    # absence is never faithful. Corpus: 5 flags, all real — ICBCT 2023Q3 lost
    # roman I (₺1.43bn) to a stray "30 | EYLÜL" date fragment parsed as hierarchy
    # 30; ISCTR 2025Q4 cons lost a ~₺90bn roman I; EXIM 2023Q1 and HAYATK 2023Q2
    # retain only III where every sibling quarter has three rows.
    for o in (1, 2, 3):
        if o not in roman_amt:
            res.add_fail("oci_roman_missing",
                         f"OCI roman {o} absent (present in ~1049/1049)",
                         expected=0.0, actual=0.0)
    present = [roman_amt[o] for o in (1, 2) if o in roman_amt]
    if 3 in roman_amt and present:
        expected = sum(present)
        tol = _tol(roman_amt[3], base=3.0, rel=5e-5)
        if abs(roman_amt[3] - expected) <= tol:
            res.add_pass()
        else:
            res.add_fail("oci_chain", "OCI III = I + II",
                         expected=expected, actual=roman_amt[3])
    else:
        res.add_skip()
    # Section sums (the RELIABLE mid level): I = Σ(1.x), II = Σ(2.x). The DEEP
    # level (2.1 = Σ(2.1.x)) is intentionally NOT checked: OCI sub-rows carry
    # net-of-tax rounding and the extractor drops immaterial zero/near-zero lines,
    # so that sum is noisy and false-fails on faithful data (the cash_flow lesson).
    # The roman chain above + these section sums verify every material OCI figure.
    num: dict[str, float] = {}
    for r in oci_rows:
        h = (r.get("hierarchy") or "").strip().rstrip(".")
        a = r.get("amount")
        if re.fullmatch(r"\d+\.\d+", h) and a is not None:
            num.setdefault(h, a)
    for sec in (1, 2):
        parent = roman_amt.get(sec)
        kids = [v for h, v in num.items() if h.startswith(f"{sec}.")]
        if parent is not None and kids:
            if abs(parent - sum(kids)) <= _tol(parent, base=3.0, rel=1e-4):
                res.add_pass()
            else:
                res.add_fail("oci_section", f"{sec}. = sum of {sec}.x sections",
                             expected=parent, actual=sum(kids))
    # Cross-check: OCI.I must equal the P&L's period-net — at whatever roman THIS
    # filer numbers it, not a hardcoded XXV. The compressed template runs
    # period-net at XXIV, so `.get(25)` returned None and this check — the only
    # cross-statement check OCI has — silently SKIPPED on 6 DUNYAK partitions
    # (2024Q3/2024Q4 unco, 2025Q1/2025Q2 cons+unco), leaving them green with
    # nothing but internal footing verified. Latent rather than live (OCI.I ties
    # exactly on all 6), but not hypothetical: the same bank's OCI lane breaks
    # catastrophically from 2025Q3 (the extractor grabs the income statement, 61
    # rows, roman I = "KÂR PAYI GELİRLERİ") and oci_cross is precisely what caught
    # it. Same class as the hardcoded-ordinal heatmap.ts bug fixed in e72823f —
    # _pl_template exists to answer this question; ask it. (TOMK's compressed
    # variant still ends at XXV and was never affected.)
    if pl_rows is not None:
        oci_i = roman_amt.get(1)
        pl_spine = _pl_spine(pl_rows)
        pl_net = (pl_spine.get(_pl_template(pl_rows, pl_spine)["period_net"])
                  if pl_spine else None)
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
    """Capital adequacy — RECONCILE the table (not just orderings):
      composition: Tier1 = CET1 + AT1 ; Total Capital = Tier1 + Tier2
      sub-ratios:  cet1_ratio = CET1/RWA ; tier1_ratio = Tier1/RWA ; CAR = Total/RWA
      plus a CAR plausibility band [5, 80]%.
    An optional component (AT1 / Tier2) is treated as 0 when NULL, but the
    composition PASSES only when the identity then ties — a genuinely-missed
    NON-zero component won't tie → SKIP, never a false pass/fail."""
    res = ValidationResult()
    cur = next((r for r in rows if r.get("period_type") == "current"), None)
    if cur is None:
        res.add_skip()
        return res
    cet1 = cur.get("cet1_capital")
    at1  = cur.get("additional_tier1_capital")
    t1   = cur.get("tier1_capital")
    t2   = cur.get("tier2_capital")
    tc   = cur.get("total_capital")
    rwa  = cur.get("total_rwa")
    cet1r = cur.get("cet1_ratio")
    t1r   = cur.get("tier1_ratio")
    car   = cur.get("capital_adequacy_ratio")

    def _composition(parent, base, opt, label):
        # parent = base + opt (opt None → 0, but PASS only when it ties)
        if base is None or parent is None:
            res.add_skip()
            return
        tol = _tol(abs(parent), base=1000.0, rel=1e-3)
        implied = base + (opt or 0.0)
        if abs(implied - parent) <= tol:
            res.add_pass()
        elif base > parent + tol:
            # base ALONE exceeds the parent — a non-negative optional component
            # can't fix that, so it's a real fail even if opt is unknown.
            res.add_fail("cap_composition", label, expected=parent, actual=base)
        elif opt is None:
            res.add_skip()   # missed optional component — can't fail confidently
        else:
            res.add_fail("cap_composition", label, expected=parent, actual=implied)

    _composition(t1, cet1, at1, "Tier1 = CET1 + AT1")
    _composition(tc, t1, t2, "Total Capital = Tier1 + Tier2")

    def _ratio(reported, num, label):
        # reported sub-ratio must equal num / RWA * 100 (±2pp, as for CAR)
        if reported is None or num is None or rwa is None or rwa <= 0:
            res.add_skip()
            return
        implied = num / rwa * 100
        if abs(implied - reported) <= _CAP_CAR_TOL:
            res.add_pass()
        else:
            res.add_fail("cap_ratio_reconcile", label, expected=implied, actual=reported)

    _ratio(cet1r, cet1, "CET1 ratio = CET1 / RWA * 100")
    _ratio(t1r, t1, "Tier1 ratio = Tier1 / RWA * 100")
    _ratio(car, tc, "CAR = Total Capital / RWA * 100")

    # CAR within plausible band [5, 80]%
    if car is not None:
        if 5 <= car <= 80:
            res.add_pass()
        else:
            res.add_fail("cap_car_band", "CAR plausible band [5, 80]%",
                         expected=12.0, actual=car)
    elif tc is None or rwa is None:
        # CAR null is a dropped column UNLESS it's derivable from total_capital +
        # RWA (both present → the cell is complete and CAR = TC/RWA*100 is
        # computable). Fail only when it can't be derived; otherwise the band just
        # can't run, but the cell is whole. (RWA-None also trips cap_rwa_missing.)
        res.add_fail("cap_car_missing",
                     "CAR dropped and not derivable (total_capital/RWA also NULL)",
                     expected=0.0, actual=0.0)
    else:
        res.add_skip()  # CAR not stored but derivable from total_capital + RWA → complete
    # Total RWA is the mandatory, non-derivable denominator of every §4 table; NULL
    # = a dropped column (every cet1/tier1/CAR reconcile skips without it).
    if rwa is None:
        res.add_fail("cap_rwa_missing", "total_rwa dropped (mandatory on §4 table)",
                     expected=0.0, actual=0.0)
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


def _bs_loans_total(bs_rows: list[dict] | None) -> float | None:
    """The balance sheet's gross loans (assets row 2.1), or None.

    Resolved by PATH, not by label or string equality. `_path` is dot-agnostic
    both ways ("2.1" / "2.1."), which the two existing consumers are not —
    compute_bank_metrics.ASSET_GROSS_LOANS and heatmap.ts both do `== '2.1'` and
    would silently drop a trailing-dot row (the defect loader._canon_hier exists
    to prevent). Labels are the WORSE anchor here: 21 spellings across TR/EN with
    footnote suffixes ("Krediler (6)", "Loans I-e-f", "Krediler (5.1.5.)").
    Unlike the P&L, the ordinal is genuinely universal — 1050/1050 partitions
    carry exactly one 2.1 row and none is null — and the participation-bank
    XIV/XVI divergence is a LIABILITIES-side phenomenon that does not reach here.
    """
    if not bs_rows:
        return None
    return next((r.get("amount_total") for r in bs_rows
                 if _path(r.get("hierarchy")) == (2, 1)
                 and r.get("amount_total") is not None), None)


# stages.total_amount / BS loans 2.1. The IFRS-9 stage table and the balance
# sheet describe the SAME loan book, so this ties at 1.0 for a clean extraction:
# median 1.0000, p05 1.0000, p95 1.0465 over 1,033 partitions.
#
# The band is wide on purpose, and the width is where the calibration lives.
# 1.05–1.20 is NOT noise — it is persistent per-bank structural offset present in
# EVERY quarter of the affected banks (BURGAN cons 1.11–1.17, TOMK unco
# 1.08–1.20, YKBNK cons 1.05–1.06, DENIZ cons 1.05), i.e. leasing/factoring
# receivables inside the consolidated IFRS-9 table but outside BS 2.1. Tightening
# to [0.95, 1.10] would flag all of them: 30 partitions, ~21 of them faithful.
# There is a real GAP to sit in: the highest structural offset is 1.1974 (TOMK
# 2025Q2) and the nearest true defect above is 1.5641 (FIBA 2022Q4); below, the
# whole [0.8, 0.95) bucket is EMPTY (p01 is already 1.0000) and the nearest true
# defect is 0.6531 (EMLAK 2022Q3 cons).
#
# Corpus: 9/1033 flagged (0.87%), and all 9 are real — each of those banks reads
# 1.0000 in its other quarters, so the deviation is per-quarter, not structural:
#   SKBNK 2025Q4 unco 0.0326 / cons 0.0373 (S1 == S3, a duplicated column)
#   SKBNK 2024Q4 cons 0.0454 · SKBNK 2022Q4 unco 0.1489 / cons 0.1575
#   FIBA  2025Q2 cons 0.0543 · FIBA 2022Q4 cons+unco 1.5641 (byte-identical
#         stage values across kinds — a cross-kind copy)
#   EMLAK 2022Q3 cons 0.6531 (its unconsolidated reads 1.0000 in all 17 quarters)
# SIX of the nine pass every other stages check — this is the only thing that
# sees them. SKBNK 2025Q4 publishes a 39.51% NPL against a truth of ~1.33%.
_STAGES_BS_BAND = (0.8, 1.3)


def check_fx_position(rows: list[dict]) -> ValidationResult:
    """Currency-risk (§4) footing — current period only:
      column: Σ per-currency rows = TOTAL (assets, liab, net BS, net off, net pos)
      row:    net balance position = assets − liab ; net position = net BS + net off
    All values from the one printed table, so footing is exact; tolerant only of
    rounding. Skips (never false-fails) when a field is absent."""
    res = ValidationResult()
    cur = {r.get("currency"): r for r in rows if r.get("period_type") == "current"}
    if not cur or "TOTAL" not in cur:
        res.add_skip()
        return res
    parts = [c for c in cur if c != "TOTAL"]
    tot = cur["TOTAL"]
    for fld in ("on_bs_assets", "on_bs_liab", "net_on_balance",
                "net_off_balance", "net_position"):
        tv = tot.get(fld)
        if tv is None or not parts or any(cur[c].get(fld) is None for c in parts):
            res.add_skip()
            continue
        s = sum(cur[c][fld] for c in parts)
        if abs(s - tv) <= _tol(abs(tv), base=2.0, rel=5e-3):
            res.add_pass()
        else:
            res.add_fail("fx_footing", f"Σ currencies = TOTAL ({fld})", expected=tv, actual=s)
    for code, r in cur.items():
        a, l, non = r.get("on_bs_assets"), r.get("on_bs_liab"), r.get("net_on_balance")
        if a is not None and l is not None and non is not None:
            if abs((a - l) - non) <= _tol(abs(non), base=2.0, rel=5e-3):
                res.add_pass()
            else:
                res.add_fail("fx_net_bs", f"{code}: assets−liab = net BS", expected=non, actual=a - l)
        noff, npos = r.get("net_off_balance"), r.get("net_position")
        if non is not None and noff is not None and npos is not None:
            if abs((non + noff) - npos) <= _tol(abs(npos), base=2.0, rel=5e-3):
                res.add_pass()
            else:
                res.add_fail("fx_net_pos", f"{code}: net BS + net off = net pos", expected=npos, actual=non + noff)
    return res


def check_repricing(rows: list[dict]) -> ValidationResult:
    """Interest-rate repricing (§4) footing — current period only:
      column:  Σ per-bucket rows = total (RSA, RSL, gap)
      balance: total RSA = total RSL (the schedule foots to the balance sheet)
    Skips when absent (participation banks that don't disclose the table)."""
    res = ValidationResult()
    cur = {r.get("bucket"): r for r in rows if r.get("period_type") == "current"}
    if not cur or "total" not in cur:
        res.add_skip()
        return res
    parts = [b for b in cur if b != "total"]
    tot = cur["total"]
    for fld in ("rate_sensitive_assets", "rate_sensitive_liab", "gap"):
        tv = tot.get(fld)
        if tv is None or not parts or any(cur[b].get(fld) is None for b in parts):
            res.add_skip()
            continue
        s = sum(cur[b][fld] for b in parts)
        if abs(s - tv) <= _tol(abs(tv), base=2.0, rel=5e-3):
            res.add_pass()
        else:
            res.add_fail("rp_footing", f"Σ buckets = total ({fld})", expected=tv, actual=s)
    rsa, rsl = tot.get("rate_sensitive_assets"), tot.get("rate_sensitive_liab")
    if rsa is not None and rsl is not None:
        if abs(rsa - rsl) <= _tol(abs(rsa), base=2.0, rel=5e-3):
            res.add_pass()
        else:
            res.add_fail("rp_balance", "total RSA = total RSL", expected=rsa, actual=rsl)
    return res


def check_credit_quality(rows: list[dict],
                         npl_movement_rows: list[dict] | None = None) -> ValidationResult:
    """Credit quality: per section total=S1+S2+S3.
    Cross-section: loans_amounts.total ≈ loans_by_stage(S1+S2)+npl_brsa_gross(S3).
    Cross-table: npl_brsa_gross vs the NPL movement table's closing balance —
    the mirror of check_npl_movement's own comparison, raised here too because
    the evidence says THIS is usually the defective side (ICBCT's gross freezes
    for quarters at a time while the movement closing tracks; see the note above
    check_npl_vs_gross). Flagging only the movement lane would leave the wrong
    number protected from re-extraction by statement_passes().
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
    # Per section: total = S1 + S2 + S3.
    #
    # An ABSENT stage counts as 0, and the identity passes only if it then TIES —
    # this module's standing convention for an optional component
    # (check_capital._composition, check_npl_movement's flow columns). Demanding
    # all four non-null was far stricter than the data warrants and cost real
    # coverage: the BRSA sections legitimately omit stages (loans_by_stage never
    # carries a stage 3 at all — the BRSA stage-3 balance lives in
    # npl_brsa_gross, so it is NULL in 1,036/1,036 rows; a bank with no watchlist
    # prints "-" for stage 2; an early-stage bank has neither). Measured over the
    # corpus: 2,818 skips -> 857, i.e. +1,961 checks that now RUN, and +0
    # failures. Nothing that was passing changed.
    #
    # Safe because the filing's own total is the judge: a genuinely DROPPED
    # non-zero stage cannot tie (the printed total would exceed the stages we
    # have), so it stays a SKIP — never a false pass. That is why the `elif`
    # below only forgives a NULL, never a present-but-wrong stage.
    for sect, r in by_sect.items():
        s1  = r.get("stage1_amount")
        s2  = r.get("stage2_amount")
        s3  = r.get("stage3_amount")
        tot = r.get("total_amount")
        if s1 is None or tot is None:
            res.add_skip()
            continue
        expected = s1 + (s2 or 0.0) + (s3 or 0.0)
        tol = _tol(tot, base=3.0, rel=5e-5)
        if abs(expected - tot) <= tol:
            res.add_pass()
        elif s2 is None or s3 is None:
            res.add_skip()   # a missed NON-zero stage — can't fail confidently
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
            # 0.5% band. IFRS stage-3 loans and BRSA NPL gross (Σ groups III/IV/V)
            # are the same closing balance and DO match this tightly for clean
            # extractions — a larger gap means a mis-extracted npl_brsa_gross (e.g.
            # grabbing the "Dönem İçinde İntikal" inflow row of the NPL *movement*
            # table instead of "Dönem Sonu Bakiyesi"), which must stay flagged, not
            # be tolerated away.
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
    # Cross-table mirror: npl_brsa_gross vs the movement table's closing, per
    # group. Same numbers, same tolerance, opposite lane — see check_npl_vs_gross.
    if npl_movement_rows:
        gross = by_sect.get("npl_brsa_gross")
        if gross is not None:
            _gbg = {"III": gross.get("stage1_amount"),
                    "IV": gross.get("stage2_amount"),
                    "V": gross.get("stage3_amount")}
            res.merge(check_npl_vs_gross(npl_movement_rows, _gbg,
                                         check_name="cq_gross_vs_movement"))
        else:
            res.add_skip()
    # NOTE: a `gross = provision + net` check was considered to catch the NPL
    # gross mis-grab corpus-wide, but REJECTED — the identity is genuinely noisy
    # (BRSA provision/net rows fold in general/collective reserves and collateral,
    # so e.g. AKBNK 2024Q4 has a CORRECT gross yet sits 4% above prov+net). It
    # would have flagged ~200 partitions, many correct. The mis-grab is instead
    # prevented at extraction time (credit_quality picks the gross row that foots
    # gross=provision+net within 1%) and cross-checked, where loans_amounts exists,
    # by cq_cross_amounts above. There is no reliable corpus-wide NPL-gross check.
    return res


# ===========================================================================
# IFRS-9 stages (derived table) validation
# ===========================================================================

def check_stages(rows: list[dict], bs_loans: list[dict] | None = None) -> ValidationResult:
    """Stages: total sums (amounts + ECL), coverage ∈ [0,1], no NPL=100%
    fingerprint, and — when the BS assets rows are supplied — the loan book
    reconciled against balance-sheet row 2.1.

    That last one is the only check here that is not internal. It matters because
    `total = S1+S2+S3` is ONE equation in FOUR unknowns: it cannot see any error
    that preserves the sum. Scaling the whole row (a fragment sub-table read as
    the loan book) or swapping S1/S2 leaves every internal identity footing —
    measured 0/1000 and 0/993 detection. Every one of the nine defects this lane
    is known to carry is of exactly that consistency-preserving shape, so only a
    cross-source anchor sees them. See _STAGES_BS_BAND for the calibration.
    """
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
        # NPL=100% fingerprint: stage3 ≈ total while S1+S2 ≈ 0 → broken extraction.
        # NULL stage1/stage2 count as 0 HERE: the real broken shape is a derived
        # row built from only the NPL line (loans_by_stage missing), so the
        # stage-1/2 cells are absent, not zero — requiring them non-null let every
        # such partition skip the very check meant to catch it. A real bank never
        # has ~100% of loans in stage 3, so firing on (s3≈total, s1+s2≈0) is safe.
        # We only PASS when s1/s2 are actually present (genuinely not-broken); a
        # partial row that isn't the broken shape still SKIPS.
        if s3 is not None and tot is not None and abs(tot) > 0:
            s12 = (s1 or 0.0) + (s2 or 0.0)
            if abs(s3) >= abs(tot) * 0.999 and abs(s12) < abs(tot) * 0.001:
                res.add_fail("stages_npl100",
                             "stage3 == total (S1+S2 ≈ 0): broken extraction fingerprint",
                             expected=abs(tot) * 0.5, actual=s3)
            elif s1 is not None and s2 is not None:
                res.add_pass()
            else:
                res.add_skip()
        else:
            res.add_skip()
        # Dropped Stage-3 (NPL) column: S1/S2 captured but S3 is NULL — the
        # NPL/Stage-3 line was never read. A genuine zero-NPL bank stores S3 = 0,
        # not NULL, and `total` then equals S1+S2 with no Stage-3 contribution, so
        # a NULL S3 beside present S1/S2 is a silently-dropped column, not an empty
        # bucket. FAIL (not skip) so the gap surfaces in the coverage matrix as
        # 'error' instead of passing 'ok' on the checks that don't need S3 — the
        # blind spot that hid EMLAK's missing NPL for 10 quarters while the cell
        # read green. Distinct from npl100, which fires when S3 is PRESENT but ≈ total.
        if s3 is None and s1 is not None and s2 is not None and tot is not None:
            res.add_fail("stages_stage3_missing",
                         "S3 (NPL) null while S1/S2 captured — dropped Stage-3 column",
                         expected=tot, actual=s1 + s2)
        # Cross-table: the IFRS-9 loan book IS the balance sheet's loan book.
        # Skips (never false-fails) when either side is absent or the BS loans row
        # is zero — 6 partitions carry a genuine 0 there (ENPARA 2024Q4, HAYATK
        # 2023Q1/Q2, TOMK 2023Q3/Q4, DUNYAK 2023Q4: banks whose loan book had not
        # yet started) and 2 have a null stages total (HAYATK 2023Q3, ZIRAATD
        # 2026Q1). Neither is a defect; a ratio is simply undefined.
        if bs_loans is not None:
            bs = _bs_loans_total(bs_loans)
            if tot is None or bs is None or bs == 0:
                res.add_skip()
            else:
                lo, hi = _STAGES_BS_BAND
                if lo <= tot / bs <= hi:
                    res.add_pass()
                else:
                    res.add_fail("stages_bs_loans",
                                 "stages total_amount vs BS loans (2.1)",
                                 expected=bs, actual=tot)
    return res


# ===========================================================================
# Bank profile (branches / personnel)
# ===========================================================================

def check_profile(rows: list[dict], counterpart: list[dict] | None = None,
                  kind: str | None = None) -> ValidationResult:
    """Bank profile — the lane's FIRST validator. Until now `profile` carried
    has_validator=False, so its 980 green cells asserted only "a row exists" and
    said nothing about the values. İşbank has been rendering **1 branch** on
    /banks for four straight Q4s underneath that green.

    There is no arithmetic to reconcile here (the table stores counts, not a
    footing), so the checks are cross-kind and cross-field — the same
    "reconciliation beats bands" move used everywhere else in this module. The
    strongest is cons >= unco: a consolidated group CONTAINS the parent, so it
    cannot have fewer branches or staff. That is not a heuristic, it is
    arithmetic, and it holds on 385/393 — the 8 exceptions being the defects.

    Corpus, all measured, all 0 FP:
      profile_empty           0/980 — every row carries branches or personnel.
                              Kept as the lane's ALWAYS-EVALUABLE check: without
                              one, a partition with no counterpart would pass
                              nothing, and _cell_status turns zero-pass into
                              `error` — 60 cells would redden spuriously.
      profile_cons_lt_unco    8 — ISCTR 2022–2025Q4 cons (personnel 187/163/147/
                              170 vs 22,971/20,809/20,175/20,246) and TSKB
                              2022–2025Q4 cons (159/192/196/206 vs 438/452/456/
                              483). TSKB is a NEW find, same Q4-consolidated
                              fingerprint as ISCTR.
      profile_branches_split  2 — ZIRAAT 2025Q4 cons+unco read 1753+28 vs total
                              1769, byte-identical to 2024Q4's split: a
                              prior-year comparative-column bleed.
      profile_personnel_count 2 — DENIZ 2024Q1/Q2 unco store personnel ==
                              branches_total EXACTLY (643=643, 644=644), a column
                              slip; the real figure is ~12,694.
      profile_branches_missing 7 — AKBNK 2022Q1/Q2/Q3 unco (its own consolidated
                              reports 711/711/713) + TSKB 2022–2025Q4 cons.

    Measured and rejected: `personnel >= branches_total` — 0 flags in 811, and it
    PASSES DENIZ at exactly 1.00, the very defect it was proposed for. The strict
    `>` is the shippable form. A longitudinal >3x jump guard — its only net-new
    flags are DUNYAK's real 1→8 branch rollout and ENPARA's real 85→1,402 staff
    transfer. A bare `branches_total IS NOT NULL` — 48% FP: 36 of the 75 nulls
    are branchless digital banks (HAYATK, TOMK, ENPARA, COLENDI, ZIRAATD) that
    are null in EVERY quarter. profile_branches_missing is the airtight subset:
    it fires only when the bank's own counterpart filing reports a branch count.
    """
    res = ValidationResult()
    cur = rows[0] if rows else None
    if cur is None:
        res.add_skip()
        return res
    br, pers = cur.get("branches_total"), cur.get("personnel")
    dom, frn = cur.get("branches_domestic"), cur.get("branches_foreign")

    if br is not None or pers is not None:
        res.add_pass()
    else:
        res.add_fail("profile_empty",
                     "profile row carries neither branches nor personnel",
                     expected=1.0, actual=0.0)
    # Staffing: a branch needs more than one person. Guarded on br > 0 so a
    # branchless bank (PASHA/KLNMA run 1; digital banks 0) isn't compared.
    if br is not None and pers is not None and br > 0:
        if pers > br:
            res.add_pass()
        else:
            res.add_fail("profile_personnel_count",
                         f"personnel ({pers:,.0f}) <= branches ({br:,.0f}) — column slip",
                         expected=br, actual=pers)
    # ±1 of headroom: ZIRAAT 2026Q1 is off by exactly one and I cannot prove from
    # the data whether that is our misread or the bank's own table, so it is left
    # alone. The +12 break is unambiguous.
    if dom is not None and frn is not None and br is not None:
        if abs((dom + frn) - br) <= 1:
            res.add_pass()
        else:
            res.add_fail("profile_branches_split",
                         "domestic + foreign != total branches",
                         expected=br, actual=dom + frn)

    cp = counterpart[0] if counterpart else None
    if cp is None:
        res.add_skip()
        return res
    cp_br, cp_pers = cp.get("branches_total"), cp.get("personnel")
    if br is None and cp_br is not None:
        res.add_fail("profile_branches_missing",
                     "branches_total dropped (the bank's counterpart filing "
                     f"reports {cp_br:,.0f})", expected=cp_br, actual=0.0)
    # A consolidated group contains the parent, so it cannot report FEWER
    # branches or staff than the unconsolidated bank. Raised on the consolidated
    # cell only: that is the impossible side, and the one carrying the defect in
    # all 8 cases.
    if kind == "consolidated":
        if pers is not None and cp_pers is not None:
            if pers >= cp_pers:
                res.add_pass()
            else:
                res.add_fail("profile_cons_lt_unco",
                             f"consolidated personnel ({pers:,.0f}) < unconsolidated "
                             f"({cp_pers:,.0f}) — impossible",
                             expected=cp_pers, actual=pers)
        if br is not None and cp_br is not None:
            # −1 of headroom: BURGAN 2022Q3 reads cons 23 vs unco 32 while its
            # own series reads 32 either side, so a small genuine timing
            # difference is plausible; a wholesale collapse is not.
            if br >= cp_br - 1:
                res.add_pass()
            else:
                res.add_fail("profile_cons_lt_unco",
                             f"consolidated branches ({br:,.0f}) < unconsolidated "
                             f"({cp_br:,.0f}) — impossible",
                             expected=cp_br, actual=br)
    return res


# ===========================================================================
# Audit opinion
# ===========================================================================

def check_audit_opinion(rows: list[dict]) -> ValidationResult:
    """Audit opinion — the lane's FIRST validator (has_validator was False, so
    976 green cells asserted only "a row exists").

    Both checks are definitional rather than arithmetic, which is the most this
    lane admits: every BRSA audit report is signed, and ISA 705 requires a "Basis
    for Qualified Opinion" paragraph whenever the opinion is modified. A blank in
    either is a parse failure, not a filing choice.

    Corpus, 0 FP:
      opinion_auditor_missing  45/976 — every one a Q4 report_kind='audit'
                               (19.2% of the 234 annual reports; 0/742 reviews).
                               The Q4 annual layout is a systematic blind spot.
                               Kept as the ALWAYS-EVALUABLE check: the basis rule
                               below only evaluates for modified opinions, so on
                               its own it would leave all 424 clean rows with
                               zero passes — which _cell_status now turns red.
      opinion_basis_missing    7/552 — ALNTF 2023Q1/Q2/Q3 (both kinds) and TFKB
                               2024Q4 cons: qualified with no stated basis.

    Measured and rejected: `opinion_type ∈ {clean, qualified}` — the corpus holds
    exactly those two values, so a closed 2-value enum cannot be violated;
    vacuous. `basis_text present ⇒ is_modified=1` — 0/545 violations AND circular:
    is_modified is perfectly collinear with opinion_type (552/552, 424/424), so
    it tests one derived binary against itself.
    """
    res = ValidationResult()
    cur = rows[0] if rows else None
    if cur is None:
        res.add_skip()
        return res
    if (cur.get("auditor") or "").strip():
        res.add_pass()
    else:
        res.add_fail("opinion_auditor_missing",
                     "auditor not captured (every BRSA audit report is signed)",
                     expected=1.0, actual=0.0)
    if cur.get("is_modified"):
        if (cur.get("basis_text") or "").strip():
            res.add_pass()
        else:
            res.add_fail("opinion_basis_missing",
                         "opinion is modified but no basis captured (ISA 705 "
                         "requires the paragraph)", expected=1.0, actual=0.0)
    return res


# ===========================================================================
# NPL movement validation
# ===========================================================================

def check_npl_movement(
    rows: list[dict], gross_by_group: dict | None = None,
) -> ValidationResult:
    """NPL movement: opening + flows = closing, per BRSA group (III/IV/V).

    write_offs / sold / transfers_out are sometimes ABSENT from a bank's table
    (it simply omits a genuinely-zero row — e.g. a bank with no write-offs) and
    sometimes just unextracted. A NULL alone can't tell the two apart, so we treat
    NULL flow-columns as 0 and PASS only when the roll-forward then TIES: a
    genuinely-missed NON-zero column wouldn't tie, so it stays a SKIP — never a
    false pass, never a false fail. fx_diff is 0 when NULL (absent in most BRSA
    formats).

    When all flow columns ARE present and it STILL doesn't tie, the flow
    roll-forward is unreliable for this bank — many tables carry an unmodeled
    "Diğer" (other-movements) flow or a sub-breakdown that doesn't foot to its
    own total (TEB), or mis-scaled flows from a stacked sub-table (PASHA). So we
    cross-check the CLOSING balance against the authoritative npl_brsa_gross
    (`gross_by_group`, the same period-end NPL from the credit-quality table):
    if the closing MATCHES the gross, the movement table's bottom line is correct
    and the residual is an unmodeled flow → SKIP (don't fail faithful data). Only
    when the closing ALSO disagrees with the gross is it a genuine extraction
    error (HALKB reads a loans-by-borrower sub-category, not the total) → FAIL.
    Mirrors the cash_flow lesson: validate the reliable bottom line, not a
    flow-model the source doesn't follow.
    """
    res = ValidationResult()
    cur = [r for r in rows if r.get("period_type") == "current"]
    if not cur:
        res.add_skip()
        return res
    for r in cur:
        op = r.get("opening_balance")
        cl = r.get("closing_balance")
        # Dropped opening/closing balance: this group IS reported (it has a row in
        # `cur`) and carries movement flows, but its opening and/or closing balance
        # is NULL — the balance column was dropped in extraction, not a genuinely
        # omitted (zero) group, which has no row at all. The roll-forward can't run,
        # so the old code SKIPPED and the cell passed green 'ok'. Fail so it surfaces.
        if (op is None or cl is None) and any(
                r.get(k) is not None for k in
                ("additions", "transfers_in", "transfers_out",
                 "collections", "write_offs", "sold")):
            res.add_fail("npl_movement_balance_missing",
                         f"group {r.get('group_code') or ''}: opening/closing dropped "
                         "(movement flows present, balance NULL)",
                         expected=(cl if cl is not None else (op or 0.0)), actual=0.0)
            continue
        if op is None or cl is None:
            res.add_skip()
            continue
        additions   = r.get("additions")     or 0.0
        t_in        = r.get("transfers_in")  or 0.0
        t_out       = r.get("transfers_out") or 0.0
        collections = r.get("collections")   or 0.0
        writeoffs   = r.get("write_offs")    or 0.0
        sold        = r.get("sold")          or 0.0
        fx          = r.get("fx_diff")       or 0.0
        # The always-outflow columns are magnitudes the roll-forward SUBTRACTS.
        # Most banks print them positive ("Tahsilat (-) 829.970"); some print the
        # value itself in parentheses ("Tahsilat (-) (8.115)") which the extractor
        # stores as a negative — and `- (-8.115)` would then ADD it (PASHA's
        # roll-forward wouldn't tie). Take the magnitude so both conventions
        # subtract correctly; positive values are unchanged, so banks that already
        # tie are unaffected.
        t_out, collections, writeoffs, sold = (
            abs(t_out), abs(collections), abs(writeoffs), abs(sold))
        implied = op + additions + t_in - t_out - collections - writeoffs - sold + fx
        tol = _tol(abs(cl), base=100.0, rel=0.002)
        if abs(implied - cl) <= tol:
            res.add_pass()
        elif (r.get("write_offs") is None or r.get("sold") is None
              or r.get("transfers_out") is None):
            # Doesn't tie, but a NULL flow column could be a genuinely non-zero
            # value the extractor missed — can't fail confidently, so skip.
            res.add_skip()
        else:
            grp = r.get("group_code") or ""
            g = (gross_by_group or {}).get(grp)
            if g is not None and abs(cl - g) <= _tol(abs(g), base=100.0, rel=0.005):
                # Closing matches the authoritative npl_brsa_gross → the table's
                # bottom line is correct; the roll-forward residual is an
                # unmodeled flow. Flows unverifiable but not wrong → SKIP.
                res.add_skip()
            else:
                res.add_fail("npl_movement", f"group {grp}: opening + flows = closing",
                             expected=cl, actual=implied)
    res.merge(check_npl_vs_gross(rows, gross_by_group,
                                 check_name="npl_closing_vs_gross"))
    # closing − |provision| = net_balance, the table's own second identity.
    # Holds 2,097/2,097 across the corpus and needs nothing external, so it costs
    # nothing and covers 100 of the 147 partitions that otherwise pass NOTHING
    # (the roll-forward above skips them all). Provision is a magnitude under
    # either storage convention, hence abs().
    for r in cur:
        cl, prov, net = (r.get("closing_balance"), r.get("provision"),
                         r.get("net_balance"))
        if cl is None or prov is None or net is None:
            res.add_skip()
            continue
        if abs((cl - abs(prov)) - net) <= _tol(abs(net), base=100.0, rel=0.002):
            res.add_pass()
        else:
            res.add_fail("npl_provision_net",
                         f"group {r.get('group_code') or ''}: closing − |provision| = net",
                         expected=net, actual=cl - abs(prov))
    return res


# The BRSA NPL closing balance is reported TWICE — as the movement table's
# closing row and as the credit-quality footnote's npl_brsa_gross. They are the
# same period-end figure and tie EXACTLY: 2,873 of 2,958 group-rows deviate by
# 0.000000. There is no middle ground (median/p75/p90/p95 are all exactly 0),
# which is why the tolerance barely matters — 0.5% flags 34 partitions, 20%
# flags 29. We keep 0.5% to match the roll-forward's rescue branch.
#
# THIS CHECK DOES NOT SAY WHICH SIDE IS WRONG, and must never be read that way.
# It is a DISAGREEMENT detector; adjudication needs the PDF. Do not assume the
# movement table is the outlier just because credit_quality and stages agree —
# bank_audit_stages is DERIVED from bank_audit_credit_quality by
# build_bank_audit_stages.py, so they are one source, not two. On the evidence the
# defective side is usually credit_quality:
#   ICBCT unco — gross FROZEN at 127,385 through 2024Q1/Q2 (a stale repeat of
#     2023Q4) while closing moves 29,172 → 29,304; again frozen at 28,118 across
#     2025Q2/Q3/Q4 while closing moves 26,966 → 27,297 → 27,465. The movement
#     table is the credible one here.
#   PASHA unco — gross reads 0 for 2024Q1–2025Q4 while closing carries 19,067 →
#     3,135 and stages S3 is stale at 35,268.
# So it is raised on BOTH lanes (see check_credit_quality), which is honest — the
# partition's NPL is unreliable until a human adjudicates — and avoids leaving the
# wrong side protected from re-extraction by statement_passes().
#
# Corpus: 34 partitions — ICBCT 17, PASHA 10, DUNYAK 2, AKTIF/FIBA/ISCTR/QNBFB/
# TOMK 1 each. Worst: FIBA 2025Q4 cons (closing 1,586,729 vs gross 1,773 — 894×),
# ISCTR 2025Q2 unco (21,209,420 vs 2,869,855), QNBFB 2025Q3 unco.
_NPL_GROSS_TOL = 0.005


def check_npl_vs_gross(rows: list[dict], gross_by_group: dict | None,
                       check_name: str) -> ValidationResult:
    """NPL closing balance vs the independently-reported npl_brsa_gross, per BRSA
    group. Runs UNCONDITIONALLY wherever both numbers exist (998/999 partitions).

    The comparison already existed inside check_npl_movement but only as a
    last-resort RESCUE — reachable solely after the roll-forward had already
    failed AND every flow column was present. In that position it fired 138 times
    to EXCUSE a failure and 0 times to report one; its `else: add_fail` was dead
    code, and the roll-forward it guards has never failed once in the corpus.
    Hoisting it to an unconditional check is what turns the lane's authoritative
    number from an alibi into a test.
    """
    res = ValidationResult()
    for r in rows:
        if r.get("period_type") != "current":
            continue
        cl = r.get("closing_balance")
        g = (gross_by_group or {}).get(r.get("group_code") or "")
        if cl is None or g is None:
            res.add_skip()
            continue
        if abs(cl - g) <= _tol(abs(g), base=100.0, rel=_NPL_GROSS_TOL):
            res.add_pass()
        else:
            res.add_fail(check_name,
                         f"group {r.get('group_code') or ''}: movement closing vs "
                         "npl_brsa_gross (disagreement — adjudicate vs the PDF)",
                         expected=g, actual=cl)
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


def _check_sector_year_swap(cur: list[dict], prior_year_total: dict | None,
                            res: ValidationResult) -> None:
    """This year's sector TOTAL must not be byte-identical to last year's.

    The footing check (Σ top-level == total) is structurally blind to the worst
    failure this lane has: a WHOLESALE YEAR SWAP foots perfectly, because last
    year's table foots against last year's total. Only a cross-period identity
    can see it.

    ICBCT is the live case and the calibration set. Its annual report stacks two
    tables on one page captioned `31 Aralık 2023` / `31 Aralık 2022` — never
    "Cari Dönem"/"Önceki Dönem" — so the period never flips, both tables are
    tagged `current`, and `_dedupe`'s first-wins backfills any dropped current
    row from LAST YEAR's table. 2023Q4 unconsolidated lost so many rows that the
    partition became almost entirely the 2022 table: it stored
    stage2 1,749,577 / stage3 41,860, byte-identical to its own 2022Q4, understated
    Stage 3 by 3.1x against the printed 127,422 — and read a flawless `ok`, with
    0 failures, for as long as this lane has existed.

    CALIBRATION (2026-07-17, whole corpus): 2 flags / 167 adjacent annual pairs
    (1.2%), BOTH true positives, both ICBCT (cons + unco 2022Q4 == 2023Q4).
    Zero false positives.

    Why a hard fail is safe: these are lira-precise aggregates over a live loan
    book. Two consecutive year-ends agreeing to the lira on BOTH stage columns
    does not happen to a real bank. The one legitimate way to tie is nil-on-nil
    (a bank with no Stage-2/Stage-3 both years), so a zero total is excluded — it
    is the only value that repeats honestly.
    """
    if not prior_year_total:
        res.add_skip()
        return
    total_row = next((r for r in cur if r.get("sector") == "total"), None)
    if total_row is None:
        res.add_skip()
        return
    same = []
    for col in ("stage2_amount", "stage3_amount"):
        now, was = total_row.get(col), prior_year_total.get(col)
        if now is None or was is None:
            return  # can't judge on a partial pair — the footing check still runs
        if abs(now) < 1.0:
            return  # nil-on-nil is the honest repeat; never flag it
        same.append(abs(now - was) < 1.0)
    if same and all(same):
        res.add_fail("loans_sector_year_swap",
                     "sector total identical to the PRIOR ANNUAL report "
                     "(stage2+stage3 both tie to the lira) — the comparative "
                     "column was almost certainly stored as current",
                     expected=float(prior_year_total.get("stage2_amount") or 0.0),
                     actual=float(total_row.get("stage2_amount") or 0.0))
    else:
        res.add_pass()


def _check_sector_child_le_parent(cur: list[dict], res: ValidationResult) -> None:
    """A group total is the sum of its non-negative children, so NO CHILD can
    exceed its parent. A child > parent is a merged-label corruption the footing
    check is blind to: the extractor fused two adjacent rows ("Balıkçılık - - -
    Sanayi") and gave one sector's key another's numbers, or backfilled a child
    from the wrong year — and because _resolved_top_level prefers the (correct)
    PARENT over the (corrupt) child, the footing still ties and the cell reads
    'ok'.

    ICBCT is the live case: 2022Q4 `agri_fishery` stored 635,214 (the prior-year
    Sanayi Stage-2, backfilled onto nil Balıkçılık) against `agri_total` 0;
    2025Q4 `svc_education` stored 1,448,401 (belongs to Sağlık) against a services
    parent that doesn't contain it. Both read a flawless green for as long as the
    lane has existed.

    Zero false positives BY CONSTRUCTION — this is arithmetic, not a tolerance:
    child > parent cannot happen in a faithfully-read table (a small epsilon
    absorbs rounding). When it does, either the child or the parent is wrong;
    either way the partition is defective. ecl_amount is included here (unlike the
    footing check) because the hierarchy holds for provisions too, and a corrupt
    child inflates a real column regardless of collective-provisioning nuance.
    """
    by = {r["sector"]: r for r in cur if r.get("sector")}
    eps = 1.0
    for parent, subs in _SECTOR_GROUPS:
        prow = by.get(parent)
        if prow is None:
            continue
        for col in ("stage2_amount", "stage3_amount", "ecl_amount"):
            pv = prow.get(col)
            if pv is None:
                continue
            for kid in subs:
                krow = by.get(kid)
                kv = krow.get(col) if krow else None
                if kv is not None and kv > pv + eps:
                    res.add_fail(
                        "loans_sector_child_exceeds_parent",
                        f"{col}: {kid} ({kv:,.0f}) > {parent} ({pv:,.0f}) — a "
                        "child sector cannot exceed its group total (merged-label "
                        "or wrong-year corruption)",
                        expected=pv, actual=kv)
                    return  # one flag per partition is enough to fail it


def check_loans_by_sector(rows: list[dict],
                          prior_year_total: dict | None = None) -> ValidationResult:
    """Loans by sector: sum of top-level sectors ≈ total row, per amount column.

    Falls back to sub-sector rows when a group aggregate (agri_total, mfg_total,
    svc_total) is absent — some banks omit the sub-total line but print the detail.

    `prior_year_total` is the PREVIOUS annual report's own `total` row for this
    (bank, kind) — see `loans_sector_year_swap` below for why the footing check
    alone cannot be trusted here.
    """
    res = ValidationResult()
    cur = [r for r in rows if r.get("period_type") == "current"]
    if not cur:
        res.add_skip()
        return res
    _check_sector_year_swap(cur, prior_year_total, res)
    total_row = next((r for r in cur if r.get("sector") == "total"), None)
    sectors = [r for r in cur if r.get("sector") and r.get("sector") != "total"]
    if total_row is None:
        # Sector detail present but no TOTAL row → the total was dropped (the BRSA
        # sector table always carries a Toplam); the footing can't run. Fail so the
        # unverifiable cell doesn't read 'ok'; skip only when there's no sector data.
        if sectors:
            res.add_fail("loans_sector_total_missing",
                         "TOTAL row dropped (sector rows present)", expected=0.0, actual=0.0)
        else:
            res.add_skip()
        return res
    top_rows = _resolved_top_level(cur)
    if not top_rows:
        res.add_fail("loans_sector_detail_missing",
                     "sector detail dropped (total present, no sector rows)",
                     expected=0.0, actual=0.0)
        return res
    _check_sector_child_le_parent(cur, res)
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
        # Total + sector rows both present, but every amount column is NULL on one
        # side → the columns were dropped; the footing never ran. Fail, don't skip.
        res.add_fail("loans_sector_columns_missing",
                     "no checkable amount column (total or sector cols all NULL)",
                     expected=0.0, actual=0.0)
    return res


# ===========================================================================
# Cash flow statement validation
# ===========================================================================

# Cash flow identity chain (roman ordinals → sources).
# V = I+II+III+IV  and  VII = V+VI.
_CF_CHAIN = [
    (5, [1, 2, 3, 4]),   # V  = I+II+III+IV  (net cash before FX/opening)
    (7, [5, 6]),          # VII = V+VI         (closing = net + opening)
]
# Romans present in 1050/1050 partitions — a bank that files a cash-flow
# statement at all files these. III and IV are NOT here: III is absent once
# (DUNYAK 2024Q1 unco) and IV nine times, and some of those absences are
# faithful (see check_cash_flow).
_CF_REQUIRED = frozenset({1, 2, 5, 6, 7})


def check_cash_flow(cf_rows: list[dict]) -> ValidationResult:
    """Cash flow: the roman bottom-line identities  V = I+II+III+IV  and  VII = V+VI.

    Only the roman chain is checked — it is sign-agnostic (the section subtotals
    I–VII are stored signed) and reliable across every bank. The previous generic
    parent=Σchildren ("hierarchy_sum") check on the 1./2./3. sub-trees was dropped:
    it produced ~146 false positives because cash-flow layout is irregular —
    the period-header line ("1 OCAK – 31 MART") is captured as a stray hierarchy
    "1" colliding with roman "I." at path (1,); banks variously omit or relabel the
    "1.1"/"1.2" subtotal rows (some print 1.1 on the "A." section header); and the
    sign convention is not label-derivable (DenizBank stores "Ödenen Faizler (-)"
    as a positive magnitude but "Personele … Yapılan Nakit" — also a payment — as a
    positive with no "(-)", so neither raw nor contra summing foots the section).
    A wrong *section total* still surfaces here, because it breaks V = I+II+III+IV.

    A DROPPED section used to be invisible — measured 0/300. The chain skipped
    whenever a source roman was absent, so deleting a section deleted its own
    constraint and the partition stayed green: KUVEYT 2024Q4 unco lost roman IV
    (₺36.5bn of FX-effect-on-cash) while reading 1 passed / 0 failed. Now the
    identity sums whichever sources SURVIVE, which is check_b_block's shape and
    works for the same reason — it never asks for the input whose loss it is
    trying to see. A legitimately-nil section contributes nothing and V foots
    anyway; a dropped one leaves the sum short and it fails.

    That distinction is why this is NOT "require every roman". Requiring all
    seven flags 10 partitions, and 2 of them are FAITHFUL: ZIRAATD 2025Q3 and
    DUNYAK 2024Q1 foot to gap = 0 without the absent roman (ZIRAATD prints IV = 0
    in every other quarter). The sum-surviving shape flags neither, and reads the
    absent slot's VALUE rather than its presence — the only way to tell nil from
    dropped. Corpus: 8 flags, all real, drop-detection 0% → 99.9% (7317/7326).
    ALNTF 2024Q3's own label prints the formula "(I+II+III+IV)"; KUVEYT 2024Q2's
    sibling consolidated IV equals the unconsolidated gap to the lira.

    _CF_REQUIRED still fails on an absent I/II/V/VI/VII — those are present in
    1050/1050, so their absence is never faithful, and without the target roman
    the identity has nothing to check.
    """
    res = ValidationResult()
    if not cf_rows:
        res.add_skip()
        return res
    amt = _pl_spine(cf_rows)  # roman spine I..VII (longest strictly-increasing run)
    for o in sorted(_CF_REQUIRED):
        if o not in amt:
            res.add_fail("cf_roman_missing",
                         f"CF roman {o} absent from the spine (present in 1050/1050)",
                         expected=0.0, actual=0.0)
    for target, sources in _CF_CHAIN:
        present = [amt[s] for s in sources if s in amt]
        if target not in amt or not present:
            res.add_skip()
            continue
        expected = sum(present)
        if abs(amt[target] - expected) <= _tol(amt[target], base=3.0, rel=5e-5):
            res.add_pass()
        else:
            res.add_fail("cf_chain", f"CF roman {target} identity",
                         expected=expected, actual=amt[target])
    return res


# ===========================================================================
# Statement of changes in equity validation
# ===========================================================================

_EQ_CLOSING_RX = re.compile(r'BAK[Iİ]YE|BALANCE', re.I)
_EQ_EQUITY_RX  = re.compile(r'(?:ÖZKAYNAK|OZKAYNAK|SHAREHOLDER|EQUITY)', re.I)


def rows_from_equity_rows(report) -> list[dict]:
    """Adapt EquityChangeReport rows to flat dicts for the validator."""
    if report is None:
        return []
    return [{"hierarchy": r.hierarchy, "item_name": r.name,
             "period_type": r.period_type, "source_page": r.source_page,
             "paid_in_capital": r.paid_in_capital,
             "share_premium": r.share_premium,
             "share_cancellation_profits": r.share_cancellation_profits,
             "other_capital_reserves": r.other_capital_reserves,
             "oci_not_reclassified_1": r.oci_not_reclassified_1,
             "oci_not_reclassified_2": r.oci_not_reclassified_2,
             "oci_not_reclassified_3": r.oci_not_reclassified_3,
             "oci_reclassified_1": r.oci_reclassified_1,
             "oci_reclassified_2": r.oci_reclassified_2,
             "oci_reclassified_3": r.oci_reclassified_3,
             "profit_reserves": r.profit_reserves,
             "prior_period_profit_loss": r.prior_period_profit_loss,
             "period_net_profit_loss": r.period_net_profit_loss,
             "total_equity": r.total_equity,
             "minority_interest": r.minority_interest,
             "total_equity_incl_minority": r.total_equity_incl_minority}
            for r in report.rows]


def _eq_closing(rows: list[dict]) -> dict | None:
    """Return the closing-balance row (hierarchy=='' and BAKIYE/BALANCE name), or last row."""
    for r in reversed(rows):
        if not r.get("hierarchy") and _EQ_CLOSING_RX.search(r.get("item_name") or ""):
            return r
    if rows:
        return rows[-1]
    return None


def _eq_roman(rows: list[dict], ordinal: int) -> dict | None:
    """Return the first row whose hierarchy is the given roman ordinal."""
    for r in rows:
        h = (r.get("hierarchy") or "").strip()
        m = re.match(r'^([IVX]+)\.?$', h)
        if m and _roman_to_int(m.group(1)) == ordinal:
            return r
    return None


def _bs_equity_section(liabilities: list[dict]) -> int | None:
    """The roman ordinal of the balance sheet's EQUITY section — XVI for most
    filers, XIV for participation banks. RESOLVED, never assumed.

    Resolving matters more here than anywhere else in this module, because the
    tempting shortcut is actively wrong. check_pl_bottomline can get away with
    `_path(...) in ((16,6,2), (14,6,2))` — a tuple set — because at DEPTH 3 the
    two spellings don't collide. At depth 2 they do: for the 801 partitions whose
    equity sits at XVI, row `14.1` is **Krediler / Loans / Borrowings** (500 /
    207 / 51). An anchor of `(16,1) or (14,1)` would therefore compare a bank's
    paid-in capital against its BORROWINGS line and call the difference a defect.

    Corpus: XVI 801, XIV 247, unresolvable 2 (AKBNK 2026Q1 cons+unco, whose
    labels are empty — already `error`, and this check skips them).
    """
    for r in liabilities:
        p = _path(r.get("hierarchy"))
        if (p is not None and len(p) == 1
                and _EQ_EQUITY_RX.search(r.get("item_name") or "")):
            return p[0]
    return None


def _eq_grand(r: dict | None) -> float | None:
    """The equity total to compare against statement-level TOTALS (BS equity, OCI
    total comprehensive income). For consolidated those totals INCLUDE minority, so
    use the grand total (total_equity_incl_minority); for unconsolidated that column
    is NULL and total_equity is already the total. (The internal column chain still
    uses parent total_equity — it's a within-column identity.)"""
    if r is None:
        return None
    g = r.get("total_equity_incl_minority")
    return g if g is not None else r.get("total_equity")


def check_eq_paid_in_capital(cur_rows: list[dict],
                             liabilities: list[dict]) -> ValidationResult:
    """The equity statement's closing PAID-IN CAPITAL vs the balance sheet's own
    (row S.1, S being the resolved equity section).

    Why a component and not just the total: check_equity_change reads only
    `total_equity` and the SUM of the 13 component columns, so any error that
    preserves the sum is invisible to it — measured 0/296 detection. A column
    SHIFT preserves the sum exactly. The equity extractor fits columns
    positionally (`paid_in_capital = cols[0]`, equity_change.py:543), so a
    one-column displacement is precisely its failure mode, and the balance sheet
    — parsed separately, from a different page, reading nothing from the equity
    statement — cannot inherit it. Two independent parses; not circular.

    Only paid-in capital is checked, and that is a measured choice, not caution:
      * paid_in_capital — 950/1,002 tie at EXACTLY 0.0000 difference; the largest
        tie is 0 and the smallest non-tie is ₺600,000, so the tolerance has no
        knob to get wrong (0.5 through 599,999 all flag the same 52).
      * share_premium — also ties cleanly, but adds 0 flags over paid-in. Risk
        without value.
      * other_capital_reserves — REJECTED: smallest non-tie is ₺92 and the
        non-ties are a continuum, not a gap. They are faithful: EMLAK 2025Q1 unco
        ties on total_equity, paid-in AND premium, so its ₺98,418 of OCR simply
        sits in a different column of the other statement — a classification
        difference between two disclosures, not a defect. It would redden 4 good
        cells.
      * the paid-in COLUMN CHAIN (closing = Σ III..XI, mirroring total_equity's)
        — REJECTED: 34 heterogeneous flags. EMLAK 2026Q1's real ₺1.03bn→₺5.0bn
        capital increase and HAYATK's ₺1.5bn→₺2.5bn raise book the increase
        outside the summed band and would fail.

    Corpus: 52 flags / 1,002 runs, false-positive rate 0/52. All 52 store a
    closing paid_in_capital of EXACTLY 0 while 52/52 carry the bank's real
    paid-in under `share_premium` — the shift signature, corroborating itself.
    No bank has zero paid-in capital: the corpus minimum is ₺99,337 and 0/1,002
    partitions have BS paid-in <= 0, so pic == 0 is wrong unconditionally.
    32 of the 52 are cells currently reading green: TFKB ×29 (2022Q3 unco, and
    2022Q4→2026Q1 cons+unco), EXIM 2024Q2 unco (₺35.7bn), HAYATK 2023Q4 unco,
    TOMK 2023Q3 unco.

    Known false negatives, stated so nobody assumes otherwise: this reads the
    CLOSING row only, so a shift confined to the opening/prior page is invisible
    (ZIRAAT 2024Q4 cons's opening is shifted while its closing is correct; ~29
    partitions carry the shape on the prior page alone). A prior-period column
    has no same-period BS to reconcile against.
    """
    res = ValidationResult()
    sect = _bs_equity_section(liabilities)
    closing = _eq_closing(cur_rows)
    pic = closing.get("paid_in_capital") if closing else None
    bs_pic = next((r.get("amount_total") for r in liabilities
                   if _path(r.get("hierarchy")) == (sect, 1)
                   and r.get("amount_total") is not None), None) if sect else None
    if pic is None or bs_pic is None:
        res.add_skip()
        return res
    if abs(pic - bs_pic) <= _tol(abs(bs_pic), base=3.0, rel=5e-5):
        res.add_pass()
    else:
        res.add_fail("eq_paid_in_capital",
                     f"equity closing paid-in capital vs BS {sect}.1",
                     expected=bs_pic, actual=pic)
    return res


def check_equity_change(eq_rows: list[dict],
                        oci_rows: list[dict] | None = None,
                        liabilities: list[dict] | None = None,
                        period: str | None = None) -> ValidationResult:
    """Statement of changes in equity structural checks.

    Per page (current + prior):
      - row-sum re-verification: total_equity ≈ Σ(first 13 components)
      - total_equity column chain: III = I + II; closing = III + IV + … + XI
    Cross-checks (skip when anchor missing):
      - row IV total_equity == OCI III amount (total comprehensive income)
      - closing total_equity == BS liabilities equity (matched by label)
      - opening == prior-closing, only for Q4 partitions
    """
    res = ValidationResult()
    if not eq_rows:
        res.add_skip()
        return res

    cur_rows  = [r for r in eq_rows if r.get("period_type") == "current"]
    pri_rows  = [r for r in eq_rows if r.get("period_type") == "prior"]

    _COL_FIELDS = [
        "paid_in_capital", "share_premium", "share_cancellation_profits",
        "other_capital_reserves",
        "oci_not_reclassified_1", "oci_not_reclassified_2", "oci_not_reclassified_3",
        "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
        "profit_reserves", "prior_period_profit_loss", "period_net_profit_loss",
    ]

    def _check_page(rows: list[dict], ptype: str) -> None:
        if not rows:
            res.add_skip()
            return
        # Row-sum re-verification
        for r in rows:
            total = r.get("total_equity")
            if total is None:
                res.add_skip()
                continue
            comp = [r.get(f) for f in _COL_FIELDS if r.get(f) is not None]
            if not comp:
                res.add_skip()
                continue
            tol = max(len(comp) * 3.0, abs(total) * 5e-5)
            if abs(sum(comp) - total) <= tol:
                res.add_pass()
            else:
                name = r.get("item_name", "")[:50]
                res.add_fail("eq_row_sum", f"{ptype} row '{name}': total ≠ Σ components",
                             expected=total, actual=sum(comp))
        # Column chain on total_equity: III = I + II
        r1 = _eq_roman(rows, 1)
        r2 = _eq_roman(rows, 2)
        r3 = _eq_roman(rows, 3)
        if r1 and r2 and r3:
            t1 = r1.get("total_equity")
            t2 = r2.get("total_equity")
            t3 = r3.get("total_equity")
            if t1 is not None and t2 is not None and t3 is not None:
                tol = _tol(t3, base=3.0, rel=5e-5)
                if abs((t1 + t2) - t3) <= tol:
                    res.add_pass()
                else:
                    res.add_fail("eq_col_chain", f"{ptype}: III = I + II (total_equity col)",
                                 expected=t3, actual=t1 + t2)
            else:
                res.add_skip()
        else:
            res.add_skip()
        # Closing chain: closing ≈ III + IV + … + XI (sum of romans 3..11)
        closing = _eq_closing(rows)
        if closing:
            cl_total = closing.get("total_equity")
            roman_sum = 0.0
            found_any = False
            for ord_n in range(3, 12):
                rx = _eq_roman(rows, ord_n)
                if rx and rx.get("total_equity") is not None:
                    roman_sum += rx["total_equity"]
                    found_any = True
            if cl_total is not None and found_any:
                tol = _tol(abs(cl_total), base=10.0, rel=5e-5)
                if abs(roman_sum - cl_total) <= tol:
                    res.add_pass()
                else:
                    res.add_fail("eq_col_chain",
                                 f"{ptype}: closing = III+IV+…+XI (total_equity col)",
                                 expected=cl_total, actual=roman_sum)
            else:
                res.add_skip()
        else:
            res.add_skip()

    _check_page(cur_rows, "current")
    _check_page(pri_rows, "prior")

    # Cross-check: row IV total_equity == OCI III amount
    if oci_rows:
        r4 = _eq_roman(cur_rows, 4)
        oci_roman: dict[int, float] = {}
        for r in oci_rows:
            h = (r.get("hierarchy") or "").strip()
            m = re.match(r'^([IVX]+)\.?$', h)
            if m:
                o = _roman_to_int(m.group(1))
                a = r.get("amount")
                if o is not None and a is not None:
                    oci_roman.setdefault(o, a)
        oci_iii = oci_roman.get(3)
        r4_total = _eq_grand(r4)
        if r4_total is not None and oci_iii is not None:
            tol = _tol(abs(oci_iii), base=3.0, rel=1e-4)
            if abs(r4_total - oci_iii) <= tol:
                res.add_pass()
            else:
                res.add_fail("eq_oci_cross",
                             "equity row IV total == OCI III (total comprehensive income)",
                             expected=oci_iii, actual=r4_total)
        else:
            res.add_skip()
    else:
        res.add_skip()

    # Cross-check: closing total_equity ≈ BS equity (matched by label)
    if liabilities:
        closing = _eq_closing(cur_rows)
        cl_total = _eq_grand(closing)
        bs_eq = next(
            (r.get("amount_total") for r in liabilities
             if r.get("amount_total") is not None
             and _EQ_EQUITY_RX.search(r.get("item_name") or "")
             and (p := _path(r.get("hierarchy"))) is not None
             and len(p) == 1),
            None,
        )
        if cl_total is not None and bs_eq is not None:
            tol = _tol(abs(bs_eq), base=100.0, rel=0.005)
            if abs(cl_total - bs_eq) <= tol:
                res.add_pass()
            else:
                res.add_fail("eq_bs_cross",
                             "equity closing total == BS equity (0.5% tolerance)",
                             expected=bs_eq, actual=cl_total)
        else:
            res.add_skip()
        res.merge(check_eq_paid_in_capital(cur_rows, liabilities))
    else:
        res.add_skip()

    # Cross-check: current opening == prior closing (Q4 partitions only)
    is_q4 = period is not None and period.endswith("Q4")
    if is_q4 and cur_rows and pri_rows:
        # Row I of current = opening balance
        r1_cur = _eq_roman(cur_rows, 1)
        cl_pri = _eq_closing(pri_rows)
        if r1_cur and cl_pri:
            op = r1_cur.get("total_equity")
            cl = cl_pri.get("total_equity")
            if op is not None and cl is not None:
                tol = _tol(abs(cl), base=100.0, rel=1e-4)
                if abs(op - cl) <= tol:
                    res.add_pass()
                else:
                    res.add_fail("eq_open_close",
                                 "current opening (row I) == prior closing (Q4)",
                                 expected=cl, actual=op)
            else:
                res.add_skip()
        else:
            res.add_skip()
    else:
        res.add_skip()

    return res
