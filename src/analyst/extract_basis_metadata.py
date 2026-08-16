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

The regex is the July bench's (`scripts/scratch/scratch_bench_unit_detection.py`): 22
front pages, untruncated text — the old 8-page window missed 15 Q4 filings whose
declaration lands p7–p17 behind the full annual opinion. It now lives in
`src.audit_reports.units` and is imported here, not duplicated.
"""
from __future__ import annotations

import sqlite3

from src.audit_reports import units

from .periods import quarter_num, sort_key

# Every stored period up to and including this one is sweep-established `bin`.
# Single definition in the audit lane; re-exported here for existing callers.
SWEEP_HORIZON = units.SWEEP_HORIZON
SWEEP_SOURCE = "sweep-2026-08-01"

# The detector lives in the AUDIT lane, because the reporting unit is a property
# of the filing and the analyst only consumes it. Imported, not copied: two
# copies of a regex that decides a 1000x scale factor is exactly the drift this
# repo has been bitten by before.
FRONT_PAGES = units.FRONT_PAGES
UNIT_RE = units.UNIT_RE
regex_unit = units.regex_unit
detect_unit_from_pdf = units.detect_unit_from_pdf


def _expected_assurance(period: str) -> str:
    return "audit" if quarter_num(period) == 4 else "review"


def build_rows(conn: sqlite3.Connection, bank: str | None = None) -> list[dict]:
    """One metadata row per extracted partition."""
    where, params = ("AND e.bank_ticker = ?", [bank]) if bank else ("", [])
    rows = conn.execute(
        "SELECT e.bank_ticker, e.period, e.kind, o.report_kind, "
        "       e.source_unit AS recorded_unit "
        "FROM bank_audit_extractions e "
        "LEFT JOIN bank_audit_opinion o ON o.bank_ticker = e.bank_ticker "
        f"  AND o.period = e.period AND o.kind = e.kind WHERE 1=1 {where}",
        params).fetchall()

    out: list[dict] = []
    for r in sorted(rows, key=lambda r: (r["bank_ticker"], sort_key(r["period"]), r["kind"])):
        within_sweep = sort_key(r["period"]) <= sort_key(SWEEP_HORIZON)
        recorded = (r["recorded_unit"] if "recorded_unit" in r.keys()
                    else None)
        out.append({
            "bank_ticker": r["bank_ticker"],
            "period": r["period"],
            "kind": r["kind"],
            # The unit READ from the filing at extraction wins: a Q2 partition
            # normalised on the way in must report `milyon` here even though its
            # stored amounts are canonical `bin`. Falling through to
            # `pending_regex` would say "nobody has looked at this filing" about
            # one we did look at.
            "reporting_unit": (
                recorded if recorded else ("bin" if within_sweep else None)),
            "unit_source": (
                "extraction" if recorded
                else (SWEEP_SOURCE if within_sweep else "pending_regex")),
            "assurance_level": r["report_kind"] or _expected_assurance(r["period"]),
            "assurance_source": "opinion" if r["report_kind"] else "expected_rhythm",
            "consolidation_basis": r["kind"],
        })
    return out
