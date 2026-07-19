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

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"

# Each fact: (id, section it belongs to, the number that must appear, keywords
# that must co-occur, the source that published it, and — where the rule was
# revised — the superseded value, so a STALE answer is distinguishable from a
# missing one. Distinguishing those two matters: stale means the model read an
# old release, absent means it never had the number at all.
FACTS: list[dict] = [
    # --- 2026-05-23 loan growth limits (the table that was missing entirely) ---
    dict(id="loan_general", section="Loan Growth Caps", value="3",
         keywords=[r"general[- ]purpose|general purpose"], stale="4",
         source="tcmb:ANO2026-21 (2026-05-23)"),
    dict(id="loan_vehicle", section="Loan Growth Caps", value="3",
         keywords=[r"vehicle|auto"], stale="4",
         source="tcmb:ANO2026-21 (2026-05-23)"),
    dict(id="loan_overdraft", section="Loan Growth Caps", value="1",
         keywords=[r"overdraft"], stale="2",
         source="tcmb:ANO2026-21 (2026-05-23)"),
    dict(id="loan_sme", section="Loan Growth Caps", value="4.5",
         keywords=[r"\bSME\b"], stale="5",
         source="tcmb:ANO2026-21 (2026-05-23)"),
    dict(id="loan_nonsme", section="Loan Growth Caps", value="2",
         keywords=[r"non-?SME"], stale="3",
         source="tcmb:ANO2026-21 (2026-05-23)"),
    # --- 2026-01-31 FX loan + overdraft ---
    dict(id="loan_fx", section="Loan Growth Caps", value="0.5",
         keywords=[r"foreign currency|FX|FC"], stale="1",
         source="tcmb:ANO2026-06 (2026-01-31)"),
    # --- 2026-07-01 FX reserve requirements (post-fix release, table present) ---
    dict(id="rr_fx_short", section="Regulations on RRs", value="32",
         keywords=[r"demand|1 month|one month|short"], stale="30",
         source="tcmb (2026-07-01)"),
    dict(id="rr_fx_long", section="Regulations on RRs", value="28",
         keywords=[r"longer matur|longer than|long"], stale="26",
         source="tcmb (2026-07-01)"),
    dict(id="rr_addl_tl", section="Regulations on RRs", value="2.5",
         keywords=[r"additional|terminated|abolish"], stale=None,
         source="tcmb (2026-07-01) — the 2.5% additional TL RR was TERMINATED"),
    # --- policy rates (prose releases; unaffected by the table bug — the control) ---
    dict(id="policy_rate", section="Monetary Policy Stance", value="37",
         keywords=[r"policy rate|one-week repo|week repo"], stale="38",
         source="tcmb:ANO2026-24 (2026-06-11)"),
    dict(id="on_lending", section="Monetary Policy Stance", value="40",
         keywords=[r"lending"], stale="41",
         source="tcmb:ANO2026-24 (2026-06-11)"),
    dict(id="on_borrowing", section="Monetary Policy Stance", value="35.5",
         keywords=[r"borrowing"], stale="36.5",
         source="tcmb:ANO2026-24 (2026-06-11)"),
    # --- 2026-03-01 repo auction suspension (a fact with no number) ---
    dict(id="repo_suspended", section="Monetary Policy Stance", value=None,
         keywords=[r"suspend"], stale=None,
         source="tcmb:ANO2026-11 (2026-03-01) — one-week repo auctions suspended"),
]


# The sections a healthy briefing produces. UNSOURCED_CATEGORIES (CARs, Credit
# Cards) are deliberately skipped upstream and are not expected here.
EXPECTED_SECTIONS = [
    "Monetary Policy Stance",
    "Regulations for TL Deposit Share",
    "Loan Growth Caps",
    "Regulations on RRs",
    "Other Regulatory Actions",
]


# Tokenise numbers and compare NUMERICALLY. The first version matched the value
# as text with a lookahead, so "37.0%" did not satisfy "37" — the model writing a
# trailing zero scored the fact MISSING while the briefing was correct. Textual
# matching also cannot see that 4.50 and 4.5 are one value.
_NUM_TOKEN_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)")


def _num_present(text: str, value: str) -> bool:
    """True if `value` appears as a standalone number, compared by magnitude.
    Still anchored on token boundaries so 3 does not match inside 37 or 0.35."""
    want = float(value)
    return any(abs(float(tok) - want) < 1e-9 for tok in _NUM_TOKEN_RE.findall(text))


def score(payload: dict) -> dict:
    cats = {c.get("name", ""): c for c in payload.get("categories", [])}
    all_bullets = [b.get("text", "")
                   for c in payload.get("categories", []) for b in c.get("bullets", [])]
    all_text = "\n".join(all_bullets)
    results = []
    for f in FACTS:
        # Prefer the fact's own section, but fall back to the whole briefing:
        # a correct figure filed under a neighbouring heading is a categorisation
        # problem, not a missing fact, and the two deserve different verdicts.
        sect = cats.get(f["section"])
        sect_text = "\n".join(b.get("text", "") for b in sect.get("bullets", [])) if sect else ""
        kw_re = re.compile("|".join(f["keywords"]), re.I)

        def hit(text: str, val: str | None) -> bool:
            if not text:
                return False
            lines = [ln for ln in text.splitlines() if kw_re.search(ln)]
            if not lines:
                return False
            return True if val is None else any(_num_present(ln, val) for ln in lines)

        current = hit(sect_text, f["value"]) or hit(all_text, f["value"])
        # The defect this lane exhibits is not omission — it is the SUPERSEDED
        # value printed as if still in force. But judge that PER BULLET: a bullet
        # saying "reduced FROM 4% TO 3%" is correct reporting and necessarily
        # contains both numbers, whereas a separate bullet asserting a bare "4%"
        # is the defect. Requiring the stale value to appear in a bullet that
        # does NOT also carry the current one separates the two without having
        # to pattern-match English.
        superseded = False
        if f["stale"]:
            for b in all_bullets:
                if not kw_re.search(b):
                    continue
                if _num_present(b, f["stale"]) and not _num_present(b, f["value"] or "\0"):
                    superseded = True
                    break

        if current and superseded:
            verdict = "CONTRADICTED"
        elif hit(sect_text, f["value"]):
            verdict = "PASS"
        elif current:
            verdict = "MISFILED"
        elif superseded:
            verdict = "STALE"
        else:
            verdict = "MISSING"
        results.append({**{k: f[k] for k in ("id", "section", "value", "stale", "source")},
                        "verdict": verdict})
    # Section coverage is scored separately from facts, because the two failures
    # are independent and the checklist is blind to one of them: a change can
    # raise the fact score while deleting an entire section whose rules the
    # checklist happens not to assert. That is exactly what the pre-baseline
    # feed cutoff did — 100% on facts, "Regulations for TL Deposit Share" gone.
    missing_sections = [s for s in EXPECTED_SECTIONS if not cats.get(s, {}).get("bullets")]

    order = ("PASS", "MISFILED", "CONTRADICTED", "STALE", "MISSING")
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in order}
    # Only PASS/MISFILED are correct: the figure reached the page and nothing
    # contradicts it. CONTRADICTED is scored as wrong — a reader cannot tell
    # which of two printed caps applies, which is worse than a missing bullet.
    good = counts["PASS"] + counts["MISFILED"]
    return {"results": results, "counts": counts,
            "score": good / len(FACTS) if FACTS else 0.0,
            "missing_sections": missing_sections,
            "sections": {n: len(c.get("bullets", [])) for n, c in cats.items()}}


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
                         "section. Alert-only: never blocks the briefing.")
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
