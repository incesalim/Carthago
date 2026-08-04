"""Task 1.5 — basis metadata: the three facts behind the comparability badge.

For every stored partition: `reporting_unit`, `assurance_level`,
`consolidation_basis`. Two of the three are joins (`report_kind` from the
opinion lane; the `kind` column itself). `reporting_unit` is the only fact
nothing stores today:

- For 2022Q1–2026Q1 it is `bin` fleet-wide — the July sweep (550 sampled
  filings, two random draws over all 1,061 R2 PDFs) found no pre-2026Q2 filing
  that ever used millions. Those rows carry `unit_source = 'sweep-2026-08-01'`.
- From 2026Q2 on, the unit must be READ per filing (the sector switched to
  Milyon). Filings are R2-only, so `detect_unit_from_pdf` runs in CI; a
  partition past the sweep horizon with no regex result gets
  `reporting_unit = NULL` + `unit_source = 'pending_regex'` — never a silent
  `bin`. UNKNOWN means "look at this filing", not "assume thousands".

The regex is the July bench's (`scripts/scratch_bench_unit_detection.py`),
promoted here verbatim: 22 front pages, untruncated text — the old 8-page
window missed 15 Q4 filings whose declaration lands p7–p17 behind the full
annual opinion.
"""
from __future__ import annotations

import re
import sqlite3

from .periods import quarter_num, sort_key

# Every stored period up to and including this one is sweep-established `bin`.
SWEEP_HORIZON = "2026Q1"
SWEEP_SOURCE = "sweep-2026-08-01"

FRONT_PAGES = 22

UNIT_RE = re.compile(
    r"(bin|milyon|milyar|thousand|million|billion)s?\s+(?:of\s+)?"
    r"(?:t[uü]rk\s+liras[iı]|turkish\s+lira)", re.I)
_NORM = {
    "bin": "bin", "thousand": "bin",
    "milyon": "milyon", "million": "milyon",
    "milyar": "milyar", "billion": "milyar",
}


def regex_unit(pages: list[str]) -> str | None:
    """First unit declaration in the front pages, normalized; None = UNKNOWN."""
    for text in pages[:FRONT_PAGES]:
        m = UNIT_RE.search(text)
        if m:
            return _NORM[m.group(1).lower()]
    return None


def detect_unit_from_pdf(pdf_path: str) -> str | None:
    """CI path — reads the first FRONT_PAGES pages with fitz. Import is local
    so the snapshot-only paths never need PyMuPDF loaded."""
    import fitz  # PyMuPDF — the repo's only sanctioned PDF engine

    with fitz.open(pdf_path) as doc:
        pages = [page.get_text() for page in doc.pages(0, min(FRONT_PAGES, doc.page_count))]
    return regex_unit(pages)


def _expected_assurance(period: str) -> str:
    return "audit" if quarter_num(period) == 4 else "review"


def build_rows(conn: sqlite3.Connection, bank: str | None = None) -> list[dict]:
    """One metadata row per extracted partition."""
    where, params = ("AND e.bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT e.bank_ticker, e.period, e.kind, o.report_kind "
        "FROM bank_audit_extractions e "
        "LEFT JOIN bank_audit_opinion o ON o.bank_ticker = e.bank_ticker "
        f"  AND o.period = e.period AND o.kind = e.kind WHERE 1=1 {where}",
        params).fetchall()

    out: list[dict] = []
    for r in sorted(rows, key=lambda r: (r["bank_ticker"], sort_key(r["period"]), r["kind"])):
        within_sweep = sort_key(r["period"]) <= sort_key(SWEEP_HORIZON)
        out.append({
            "bank_ticker": r["bank_ticker"],
            "period": r["period"],
            "kind": r["kind"],
            "reporting_unit": "bin" if within_sweep else None,
            "unit_source": SWEEP_SOURCE if within_sweep else "pending_regex",
            "assurance_level": r["report_kind"] or _expected_assurance(r["period"]),
            "assurance_source": "opinion" if r["report_kind"] else "expected_rhythm",
            "consolidation_basis": r["kind"],
        })
    return out
