#!/usr/bin/env python3
"""Guard: the hand-typed forward dates must not quietly run out.

Sibling of `check_docs_sync.py` and `check_prose_claims.py`.

Five pages used to carry a hand-typed release schedule — "JUL 23 — TCMB MPC",
"AUG ~12 — BDDK monthly bulletin". They were correct when written and silently
wrong a fortnight later. Those rows are now DERIVED (web/app/lib/ahead.ts) from
the record periods in D1 plus the observed KAP filing lag, with one exception:
TCMB publishes its MPC calendar a year or two ahead and nothing scrapes it, so
`MPC_DATES` is transcribed by hand.

That list is therefore the one place the old failure could come back — it would
simply run out, the row would vanish, and nobody would notice. So:

  1. MPC_DATES is well-formed and sorted
  2. its last date is at least MIN_RUNWAY_DAYS away  ← the real check
  3. web/app/lib/economy.ts's BBVA_BASELINE.asOf is not older than
     MAX_BASELINE_AGE_MONTHS — a stale third-party "outlook" carried as a chart
     subtitle is a lie of omission

Stdlib only (the CI python job installs no TS tooling): the TypeScript is regexed
as text, exactly as check_docs_sync.py regexes the workflow YAML.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AHEAD_TS = REPO_ROOT / "web" / "app" / "lib" / "ahead.ts"
ECONOMY_TS = REPO_ROOT / "web" / "app" / "lib" / "economy.ts"

# Refresh the calendar before it gets this close to the end. TCMB publishes the
# next year's dates well inside this window, so it is always actionable.
MIN_RUNWAY_DAYS = 90
# A "Türkiye Outlook 1Q26" still being quoted in 2028 is not context, it is decor.
MAX_BASELINE_AGE_MONTHS = 18

_MPC_BLOCK = re.compile(r"MPC_DATES[^=]*=\s*\[(.*?)\]", re.S)
_DATE = re.compile(r'"(\d{4}-\d{2}-\d{2})"')
_AS_OF = re.compile(r'asOf:\s*"([^"]+)"')

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}


def mpc_dates() -> list[str]:
    m = _MPC_BLOCK.search(AHEAD_TS.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"MPC_DATES not found in {AHEAD_TS} — did the export get renamed?")
    return _DATE.findall(m.group(1))


def baseline_as_of() -> str | None:
    m = _AS_OF.search(ECONOMY_TS.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _parse_as_of(s: str) -> date | None:
    """'March 2026' → 2026-03-01."""
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", s.strip())
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    return date(int(m.group(2)), month, 1) if month else None


def check(today: date | None = None) -> list[str]:
    """Every problem found, as printable lines. Empty means green."""
    today = today or datetime.now(timezone.utc).date()
    problems: list[str] = []

    dates = mpc_dates()
    if not dates:
        problems.append("MPC_DATES is empty — the /Ahead MPC row will never render.")
        return problems

    if dates != sorted(dates):
        problems.append("MPC_DATES is not in ascending order — nextMpc() picks the first match.")

    last = date.fromisoformat(dates[-1])
    runway = (last - today).days
    if runway < MIN_RUNWAY_DAYS:
        problems.append(
            f"MPC_DATES runs out in {runway}d (last: {last.isoformat()}), under the "
            f"{MIN_RUNWAY_DAYS}d minimum.\n"
            f"  Transcribe the next year from TCMB's published calendar into "
            f"web/app/lib/ahead.ts:\n"
            f"  https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Calendar"
        )

    as_of = baseline_as_of()
    if as_of:
        d = _parse_as_of(as_of)
        if d is None:
            problems.append(f"BBVA_BASELINE.asOf ({as_of!r}) is not a parseable 'Month YYYY'.")
        else:
            months = (today.year - d.year) * 12 + (today.month - d.month)
            if months > MAX_BASELINE_AGE_MONTHS:
                problems.append(
                    f"BBVA_BASELINE.asOf is {as_of} — {months} months old, over the "
                    f"{MAX_BASELINE_AGE_MONTHS}-month limit.\n"
                    f"  /economy carries it as a forecast scenario; refresh it from the "
                    f"latest outlook or drop the table."
                )

    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    problems = check()
    if not problems:
        dates = mpc_dates()
        runway = (date.fromisoformat(dates[-1]) - datetime.now(timezone.utc).date()).days
        print(f"calendar fresh ({len(dates)} MPC dates, {runway}d of runway).")
        return 0

    print("Hand-typed forward dates need attention:\n", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
