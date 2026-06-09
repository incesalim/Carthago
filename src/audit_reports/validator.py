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


def rows_from_statement_rows(stmt_rows) -> list[dict]:
    """Adapt extractor.StatementRow objects to validator dicts."""
    return [{
        "hierarchy": r.hierarchy, "item_name": r.name,
        "amount_tl": r.cur_tl, "amount_fc": r.cur_fc, "amount_total": r.cur_total,
    } for r in stmt_rows]


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
    """Validate one extracted BankReport (assets, liabilities, cross)."""
    assets = rows_from_statement_rows(rep.bs_assets)
    liabilities = rows_from_statement_rows(rep.bs_liabilities)
    return {
        "assets": validate_statement(assets),
        "liabilities": validate_statement(liabilities),
        "cross": check_cross_statement(assets, liabilities),
    }
