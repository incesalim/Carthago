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
    if abs(a - li) / abs(a) <= 0.005:
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

    def _letter_amt(letter: str) -> float | None:
        for r in rows:
            if ((r.get("hierarchy") or "").strip().rstrip(".").upper() == letter
                    and r.get("amount_total") is not None):
                return r["amount_total"]
        return None

    a, b, tot = _letter_amt("A"), _letter_amt("B"), None
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
    EXIM/VAKBN source mislabel head-on) and V6 (labelled "(A+B)" grand total = A
    + B — a top-of-tree reconciliation that DOES catch a wholly dropped custody
    block, which V2's parent-sums cannot). Both are corpus-calibrated to zero
    false positives.
    """
    res = ValidationResult()
    res.merge(check_row_triplets(rows))
    res.merge(check_hierarchy_sums(rows))
    res.merge(check_no_duplicate_hierarchy(rows))
    res.merge(check_grand_total_ab(rows))
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
    if 25 in spine:
        cands.append(spine[25])
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

def check_oci(oci_rows: list[dict], pl_rows: list[dict] | None = None) -> ValidationResult:
    """OCI: numeric hierarchy sums (2.1/2.2 trees) + roman chain III=I+II +
    cross-check OCI.I == P&L net (row XXV)."""
    res = ValidationResult()
    if not oci_rows:
        res.add_skip()
        return res
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
    """
    res = ValidationResult()
    if not cf_rows:
        res.add_skip()
        return res
    amt = _pl_spine(cf_rows)  # roman spine I..VII (longest strictly-increasing run)
    for target, sources in _CF_CHAIN:
        if target not in amt or any(s not in amt for s in sources):
            res.add_skip()
            continue
        expected = sum(amt[s] for s in sources)
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
