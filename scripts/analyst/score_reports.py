"""Report-quality scorer — the calibration criteria generalized into numbers.

Reads memo artifacts (`data/analyst_memo_*.json`) and scores each on the
properties the calibration process enforced by hand: guard verdict, structure,
length, LEAD-adherence (does the headline state the first live gate?) and
live-story coverage (does every live story appear in the body?). Informational
by design — the guard already gates publishing; this exists so a prompt or
model change gets a regression NUMBER across many banks instead of a
judgment call over one.

    python scripts/analyst/score_reports.py data/analyst_memo_*.json
"""
from __future__ import annotations

import glob
import json
import re
import sys

REQUIRED_SECTIONS = [
    "## First-read scorecard",
    "## What changed",
    "## Asset quality",
    "## Capital",
    "## What the auditor said",
    "## What to watch",
    "## Bottom line",
]

# story key → what its presence looks like in prose. Deliberately loose:
# the scorer measures coverage, it does not police wording.
STORY_MARKS: dict[str, re.Pattern] = {
    "real_terms": re.compile(r"real[- ]terms|real ROE|purchasing.power|inflation.adjust", re.I),
    "capital_composition": re.compile(r"non.?core|CAR.CET1|composition|Tier.?2", re.I),
    "npl_coverage_divergence": re.compile(r"coverage", re.I),
    "free_provision": re.compile(r"free.?provision|discretionary", re.I),
    "peer_deviation": re.compile(r"median|peer", re.I),
    "comparability_events": re.compile(
        r"perimeter|restat|reporting unit|discontinued|comparab", re.I),
}

WORD_RANGE = (1800, 4600)


def score(path: str) -> dict:
    m = json.load(open(path, encoding="utf-8"))
    body: str = m.get("body", "")
    title: str = m.get("title", "")
    words = len(body.split())
    gates = m.get("gates", [])
    live = [g for g in gates if g.get("live")]
    lead = live[0]["story"] if live else None
    lead_ok = bool(lead and STORY_MARKS[lead].search(title)) if lead in STORY_MARKS else None
    covered = [g["story"] for g in live
               if g["story"] in STORY_MARKS and STORY_MARKS[g["story"]].search(body)]
    missing_sections = [h for h in REQUIRED_SECTIONS if h not in body]
    return {
        "bank": m.get("bank_ticker"),
        "period": m.get("period"),
        "kind": m.get("kind"),
        "model": m.get("model"),
        "passed": bool(m.get("fact_check_passed")),
        "dropped": m.get("dropped_paragraphs", 0),
        "words": words,
        "length_ok": WORD_RANGE[0] <= words <= WORD_RANGE[1],
        "sections_ok": not missing_sections,
        "missing_sections": missing_sections,
        "lead": lead,
        "lead_ok": lead_ok,
        "live_stories": [g["story"] for g in live],
        "covered": covered,
        "coverage_ok": len(covered) == len([g for g in live if g["story"] in STORY_MARKS]),
    }


def main(argv: list[str]) -> int:
    paths: list[str] = []
    for a in argv or ["data/analyst_memo_*.json"]:
        paths.extend(glob.glob(a))
    if not paths:
        print("no memo artifacts found")
        return 0
    rows = [score(p) for p in sorted(paths)]
    for r in rows:
        flags = [
            "PASS" if r["passed"] else f"FAIL({r['dropped']}¶)",
            "len" if r["length_ok"] else f"len!{r['words']}",
            "struct" if r["sections_ok"] else "struct!" + ",".join(r["missing_sections"]),
            ("lead" if r["lead_ok"] else f"lead!{r['lead']}") if r["lead_ok"] is not None else "lead:n/a",
            "cover" if r["coverage_ok"] else "cover!" + ",".join(
                s for s in r["live_stories"] if s not in r["covered"]),
        ]
        print(f"{r['bank']} {r['period']} {r['kind']}: {' | '.join(flags)}  [{r['model']}]")
    ok = sum(1 for r in rows
             if r["passed"] and r["length_ok"] and r["sections_ok"]
             and r["lead_ok"] is not False and r["coverage_ok"])
    print(f"\n{ok}/{len(rows)} reports fully clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
