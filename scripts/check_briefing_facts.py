#!/usr/bin/env python3
"""Score a regulation briefing against figures we KNOW were published.

Bullet counts are not a quality measure — a briefing can grow by padding and
shrink by tightening. What matters is whether the rules actually in force appear.
So this asserts *facts*, each traced to the TCMB press release that published it,
and reports which are present, which are stale (the superseded value appears
instead), and which are simply absent.

The checklist exists because those figures were provably missing from the feed:
TCMB bodies scraped before 2026-05-29 lost their tables, and the tables are where
the caps and ratios live (docs/knowledge/regulation-consistency-plan-2026-07-20.md).
This is the instrument that says whether fixing that actually fixed the briefing.

The checklist itself (FACTS) and the scorer live in `src/news/briefing_facts.py`
since 2026-08-16, because the GENERATOR now gates on the same instrument this
CLI scores with — a briefing failing its facts is repaired or held back before
the store, instead of shipping at 69% with a Telegram alert as the only trace.
This script remains the independent, after-the-fact reading of what shipped.

Usage:
  python scripts/check_briefing_facts.py                  # newest local briefing
  python scripts/check_briefing_facts.py --d1             # newest briefing in D1
  python scripts/check_briefing_facts.py --json out.json  # machine-readable
  python scripts/check_briefing_facts.py --fail-under 0.8 # non-zero exit if worse

A fact is matched on its NUMBER plus a context keyword, not on phrasing: the LLM
is free to word a bullet any way it likes, and this must not become a style test.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.news.briefing_facts import FACTS, score  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"


def load_local() -> dict:
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT categories_json, generated_at, model FROM regulation_briefings "
            "ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("no briefing in the local DB")
    print(f"[facts] local briefing {row[1]} ({row[2]})")
    return json.loads(row[0])


def load_d1() -> dict:
    out = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "bddk-data", "--remote", "--json",
         "--command", "SELECT categories_json, generated_at, model FROM "
                      "regulation_briefings ORDER BY generated_at DESC LIMIT 1"],
        cwd=REPO_ROOT / "web", capture_output=True, text=True, shell=True,
    )
    m = re.search(r"\[\s*\{.*\}\s*\]", out.stdout, re.S)
    if not m:
        raise SystemExit(f"could not read D1: {out.stdout[-400:]}{out.stderr[-400:]}")
    data = json.loads(m.group(0))
    rows = data[0]["results"] if isinstance(data[0], dict) and "results" in data[0] else data
    print(f"[facts] D1 briefing {rows[0]['generated_at']} ({rows[0]['model']})")
    return json.loads(rows[0]["categories_json"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--d1", action="store_true", help="Score the briefing in D1, not the local DB")
    ap.add_argument("--json", dest="json_out", help="Write the full result to this path")
    ap.add_argument("--fail-under", type=float, default=None,
                    help="Exit non-zero if the score is below this (0-1)")
    ap.add_argument("--alert", action="store_true",
                    help="Telegram on any CONTRADICTED/STALE/MISSING fact or missing "
                         "section. Alerting only — combine with --fail-under to "
                         "also turn the run red.")
    args = ap.parse_args()

    payload = load_d1() if args.d1 else load_local()
    res = score(payload)

    print(f"\n{'verdict':<10}{'fact':<16}{'want':<7}{'section'}")
    for r in res["results"]:
        icon = {"PASS": "OK  ", "MISFILED": "~   ", "CONTRADICTED": "CONFLICT",
                "STALE": "OLD ", "MISSING": "MISS"}[r["verdict"]]
        print(f"{icon:<10}{r['id']:<16}{str(r['value'] or '-'):<7}{r['section']}")
    c = res["counts"]
    print(f"\nsections: {res['sections']}")
    print(f"PASS {c['PASS']}  MISFILED {c['MISFILED']}  CONTRADICTED {c['CONTRADICTED']}  "
          f"STALE {c['STALE']}  MISSING {c['MISSING']}"
          f"   ->  score {res['score']:.0%} ({c['PASS'] + c['MISFILED']}/{len(FACTS)})")
    for r in res["results"]:
        if r["verdict"] in ("MISSING", "STALE", "CONTRADICTED"):
            extra = f"  (superseded {r['stale']} also printed)" if r["verdict"] == "CONTRADICTED" else ""
            print(f"  {r['verdict']:<13}{r['id']:<16}{r['source']}{extra}")

    if args.alert:
        bad = [r for r in res["results"] if r["verdict"] in ("CONTRADICTED", "STALE", "MISSING")]
        if bad or res["missing_sections"]:
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            from notify import notify
            lines = [f"⚠️ Regulation briefing scored {res['score']:.0%} "
                     f"({len(bad)} fact issue(s))"]
            if res["missing_sections"]:
                lines.append("EMPTY SECTIONS: " + ", ".join(res["missing_sections"]))
            for r in bad[:8]:
                lines.append(f"• {r['verdict']}: {r['id']} — want {r['value']} "
                             f"[{r['section']}]")
            notify("\n".join(lines))
            print("[facts] alert sent")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")
    if res["missing_sections"]:
        print(f"\nFAIL: {len(res['missing_sections'])} expected section(s) produced "
              f"nothing: {', '.join(res['missing_sections'])}", file=sys.stderr)
        return 1
    if args.fail_under is not None and res["score"] < args.fail_under:
        print(f"\nFAIL: {res['score']:.0%} < {args.fail_under:.0%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
