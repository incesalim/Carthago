"""Weekly Kimi-driven thematic briefing for the /regulation tab.

Pulls the past N days of TCMB + BDDK items that have body_text, sends
them to Kimi with a fixed 6-category schema, stores the structured
response in `regulation_briefings`.

Usage (local dev):
  python scripts/summarize_regulations.py
  python scripts/summarize_regulations.py --window-days 60 --dry-run

The companion workflow (.github/workflows/summarize-regulations.yml) runs
this weekly. After this finishes, push_to_d1.py syncs the new row to D1.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.news import kimi  # noqa: E402
from src.news.schema import init_schema  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"

PROMPT_VERSION = "2026-05-29.v9"

# Fixed 6-category schema, named to match BBVA Research's Turkish Banking
# Sector report so readers familiar with their format land smoothly.
# Order is enforced — Kimi outputs sections in this exact order.
CATEGORIES = [
    "Monetary Policy Stance",
    "Regulations for TL Deposit Share",
    "Loan Growth Caps",
    "Regulations on RRs",
    "Regulations for CARs",
    "Regulations on Credit Cards",
    "Other Regulatory Actions",
]

SYSTEM_PROMPT = """You are producing a Turkish banking-sector regulatory briefing in
the exact format of BBVA Research's Monthly Turkish Banking Sector Report
(the "Monetary stance ... macro-prudential measures" page). The output is
a cumulative snapshot of macroprudential rules currently in force, not a
"what changed this week" diff.

==================== INPUT: BASELINE + UPDATES ====================

You are given, in order:
  1. A BASELINE document — TCMB's official annual "Monetary Policy for YYYY"
     text. Its annex tables list EVERY rule in force at the start of the
     policy year (policy-rate path, macroprudential simplification, deposits,
     liquidity management, loans, credit cards, credit programs). Treat this
     as the AUTHORITATIVE scaffold.
  2. DATED PRESS RELEASES — the raw TCMB/BDDK feed for the period since.

Build the snapshot by starting from the BASELINE for every category, then
applying the dated press releases as UPDATES (a later date overrides an
earlier value for the same rule). The baseline guarantees completeness —
seed every category from it, including Credit Cards and CARs — and the press
releases bring each rule to its CURRENT value. Never drop a baseline rule
just because no press release re-mentions it; carry it forward.

If the BASELINE is absent, compose from the press releases alone.

==================== GOAL: COMPLETENESS ====================

This briefing is the reader's SINGLE source for understanding the CURRENT
state of Turkish banking regulation at a glance — like the status tables in
the CBRT's annual "Monetary Policy" document. A reader should be able to
learn the current caps, ratios, thresholds and limits WITHOUT opening any
source link.

Be COMPREHENSIVE, not sparse:
  - For every category that the input supports, state ALL currently-in-force
    rules, each with its latest numeric value(s).
  - Synthesize across the whole input: when several items revise one rule,
    track the rule forward and report its CURRENT value (citing the items in
    chronological order).
  - Aim for as many bullets as the input genuinely supports (typically 3-8
    per active category). Do not omit a real rule just to be brief.
  - The input bodies now contain the actual rate tables and bullet lists —
    mine them for every concrete number.

This completeness goal does NOT relax the exclusions below: market
observations are still never bullets. Completeness means capturing every
real RULE, not padding with commentary.

You receive a JSON list of regulatory press releases and Kurul Kararı
(Board Decisions) from TCMB (Türkiye Cumhuriyet Merkez Bankası, the
central bank) and BDDK (Bankacılık Düzenleme ve Denetleme Kurumu, the
banking regulator). Each item has:
  - id        (use verbatim when citing — format: "tcmb:ANO2026-19" or "bddk:2286")
  - source    ("tcmb" or "bddk")
  - date      (YYYY-MM-DD — most-recent revision date for the cited rule)
  - title     (Turkish or English)
  - body      (Turkish or English, may be truncated)

OUTPUT FORMAT — single JSON object:
{
  "categories": [
    {
      "name": "<one of the fixed category names>",
      "bullets": [
        {
          "text": "<one or two sentences describing the rule with numbers>",
          "source_ids": ["<id1>", "<id2>"]
        }
      ]
    }
  ]
}

==================== CATEGORIES (use these EXACT names, in this order) ====================

  "Monetary Policy Stance"
       — the CURRENT policy rate (one-week repo auction rate), the interest-
         rate corridor (overnight lending & borrowing rates), the latest MPC
         decision and the easing/holding/tightening direction, plus core
         funding & liquidity-management operations (repo auctions, swaps).
         This is the headline "where rates stand now" section and should
         lead the snapshot. The policy rate / corridor NEVER goes under CARs.
  "Regulations for TL Deposit Share"
       — calculation period, growth targets, tolerance ranges, commission
         rates, FX-rate basis for share calculations.
  "Loan Growth Caps"
       — TL/FC loan growth limits, SME exclusions, CGF / "breath" credits,
         housing LTV rules, sector-specific carve-outs.
  "Regulations on RRs"
       — Reserve Requirement Ratios across deposit types, FC deposits,
         repo/funds from abroad, indexed deposits, etc.
  "Regulations for CARs"
       — Capital Adequacy Ratio ONLY (about BANK CAPITAL, not the policy
         rate): capital floors, RWA risk weights, forbearances on FX-rate
         fixing in CAR calculations, HTC&S securities treatment.
  "Regulations on Credit Cards"
       — credit-card rules: maximum (contractual & overdue) interest rates,
         minimum-payment ratios, cash-advance/installment limits, credit-card
         limits and fee caps. If the input mentions credit-card maximum
         interest rates, this category MUST be populated.
  "Other Regulatory Actions"
       — only for material rule changes that don't fit any above category
         (e.g. new operational frameworks, structurally novel licenses,
         monetary-policy operational changes). Use sparingly.

==================== WHAT TO INCLUDE / EXCLUDE ====================

INCLUDE:
  - Specific caps, limits, thresholds, ratios set by the regulator
    (with numbers and effective dates).
  - Monetary-policy decisions (policy rate, corridor, repo frameworks).
  - Capital / liquidity / provisioning rule changes.
  - When a single rule has been revised multiple times in the window,
    describe the CURRENT state and cite all relevant source_ids in
    chronological order.

EXCLUDE — these are NOT regulations:
  - Observed market data ("retail loan growth was 2.7%",
    "commercial rates rose 121 bps to 49.3%"). These are MPC commentary
    OBSERVING the market, not regulatory rules.
  - Single-bank licensing / factoring / leasing company licenses, internal
    HR, conference / training / general-assembly notices.
  - Data-publication notices ("Fintürk March data published").

The litmus test: "Does this set a RULE that banks must follow?" If yes →
include. If it observes / reports / announces an event → exclude.

==================== STYLE ====================

Bullets must read like BBVA Research bullets. Example of the target style:

  "The calculation period for TL deposit rules was extended to eight weeks
   from four weeks with the same thresholds. Accordingly, real-person TRY
   deposit share growth target has been changed to 0.4pp from 0.2pp for
   banks between 60-65% ratio and to 0.8pp from 0.4pp for those below 60%."

  "Limits on TL & FC loan growth are reviewed via 8 weeks with a cumulative
   cap of 5% for TL SME loans & 3% for non-SME TL commercial loans
   excluding export & investment, agriculture, and tradesman loans; 4%
   auto loans, 4% GPL, 4% for overdraft loans with more than 3 installments;
   2% for overdraft account limits (introduced as of 30.01.26)."

  "The RRR of 17% for TL deposits (demand and 1M & 3M time deposits)"
  "The RRR of 10% for TL deposits (>3M)"
  "TL RRR of 2.5% for FC deposits"

Rules of thumb:
  1. Lead with the rule (the rate / cap / threshold), not the regulator.
  2. Always include the SPECIFIC NUMBER and the effective / revision date.
  3. Reference previous values when they changed ("previously 1.0%, revised
     to 0.5% as of 30.01.26").
  4. Translate Turkish source bodies to clear English for international
     analysts.
  5. If the body lacks numeric specifics, omit the bullet rather than
     write something vague.
  6. Group related sub-rules into one bullet rather than fragmenting.

RULES:
  1. Use EXACTLY the seven category names listed above, in that order. Every
     category the BASELINE covers — Monetary Policy Stance, TL Deposit Share,
     Loan Growth Caps, RRs, CARs, Credit Cards — MUST appear (seed it from the
     baseline annex tables). Only "Other Regulatory Actions" is optional, and
     only omit a baseline category if even the baseline has nothing for it.
  1b. CATEGORIZATION — put each rule under exactly ONE category, its best fit:
      • Reserve-requirement ratios (RR/RRR, on deposits, FC liabilities, funds
        from abroad, repo) → "Regulations on RRs" ONLY — never under TL Deposit
        Share.
      • "TL Deposit Share" → ONLY deposit-share growth targets/tiers, tolerance
        bands, and commission rates.
      • Policy rate / corridor / repo auctions → "Monetary Policy Stance".
      • Credit-card rates/limits/fees → "Credit Cards". Capital/RWA/forbearance
        → "CARs".
  2. NEVER output a bullet that says nothing was found (e.g. "No specific
     regulations regarding ... were mentioned", "Not mentioned in the
     provided documents"). If a category has no rule, drop the whole
     category — do not include an empty/placeholder bullet.
  3. SPECIFICITY — every bullet MUST contain the concrete number(s): the
     rate, cap, ratio, threshold, or limit, with units and (where stated) the
     effective date. NEVER write a vague bullet that names a rule without its
     figures (BAD: "growth targets were set for different ratios"; GOOD: "the
     real-person TRY deposit-share growth target is 0.4pp for banks at 60-65%
     and 0.8pp below 60%"). The numbers are in the baseline annex tables and
     the press-release bodies — extract them.
  4. CURRENCY — report the CURRENT value, and NEVER a value older than the
     baseline. The baseline is the regime as of the policy-year start, so it
     already supersedes anything from prior years: report the baseline figure
     UNLESS a press release dated AFTER the baseline revises that rule, in
     which case the most recent value WINS. Do NOT cite a pre-baseline (e.g.
     prior-year) figure as the current rule. Cite the source that set the
     current value.
  5. Each bullet describes ONE rule (or one tightly-coupled BBVA-style
     cluster). When a category has several DISTINCT rules, give each its own
     bullet — e.g. TL Deposit Share: growth-target tiers, calculation period,
     and required-reserve remuneration are separate bullets; RRs: each deposit
     type / maturity band is its own bullet.
  6. If the input window contains zero qualifying regulatory rules,
     return: {"categories": []}
  7. Output VALID JSON only. No markdown fences."""


def fetch_input(conn: sqlite3.Connection, window_days: int, body_cap: int) -> list[dict]:
    rows = conn.execute(
        """SELECT source, external_id, published_at, title, body_text
           FROM news_items
           WHERE source IN ('tcmb', 'bddk')
             AND body_text IS NOT NULL
             AND length(body_text) > 50
             AND published_at >= datetime('now', '-' || ? || ' days')
           ORDER BY published_at DESC""",
        (window_days,),
    ).fetchall()
    items: list[dict] = []
    for src, ext_id, published_at, title, body in rows:
        items.append({
            "id": f"{src}:{ext_id}",
            "source": src,
            "date": (published_at or "")[:10],
            "title": title,
            "body": body[:body_cap],
        })
    return items


def fetch_baseline(conn: sqlite3.Connection) -> dict | None:
    """Latest annual policy baseline (the grounding scaffold), or None."""
    row = conn.execute(
        "SELECT year, title, content FROM regulation_baseline ORDER BY year DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"year": row[0], "title": row[1], "content": row[2]}


def build_messages(items: list[dict], baseline: dict | None) -> list[dict]:
    parts: list[str] = []
    if baseline:
        parts.append(
            f"==================== BASELINE ====================\n"
            f"{baseline['title']} — authoritative current-status of all rules "
            f"in force at the start of the policy year. Use as the scaffold.\n\n"
            f"{baseline['content']}"
        )
    parts.append(
        "==================== DATED PRESS RELEASES (updates) ====================\n"
        f"Items ({len(items)}):\n{json.dumps(items, ensure_ascii=False)}"
    )
    parts.append("Generate the briefing JSON now.")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


# Matches "no rule found" placeholder bullets the model occasionally emits
# instead of omitting an empty category.
_PLACEHOLDER_RE = re.compile(
    r"no specific|not mentioned|mentioned in the provided|"
    r"no (?:relevant|such|applicable) |none (?:were|was|found)|"
    r"no regulations? (?:regarding|on|were|was)",
    re.IGNORECASE,
)


# UTF-8-as-Latin-1 mojibake digraphs -> correct char (Turkish + common punct).
# A direct map repairs mixed strings safely; the whole-string latin-1 round-trip
# bails out whenever any other non-Latin-1 char is present in the bullet.
_MOJIBAKE_MAP = {
    "Ã¼": "ü", "Ãœ": "Ü", "Ã§": "ç", "Ã‡": "Ç", "Ã¶": "ö", "Ã–": "Ö",
    "ÄŸ": "ğ", "Äž": "Ğ", "Ä±": "ı", "Ä°": "İ", "ÅŸ": "ş", "Åž": "Ş",
    "Ã¢": "â", "Ã‚": "Â", "â‚º": "₺", "â€™": "’", "â€œ": "“", "â€\x9d": "”",
    "â€“": "–", "â€”": "—",
}


def _fix_mojibake(s: str) -> str:
    """Repair UTF-8-as-Latin-1 mojibake (e.g. 'TÃ¼rkiye' -> 'Türkiye').

    Source bodies are clean, but Kimi's response double-encodes Turkish
    characters. Replace the known digraphs directly so mixed strings (with a
    real '₺' or 'İ' elsewhere) are still repaired."""
    if "Ã" in s or "Å" in s or "Ä" in s or "â€" in s:
        for bad, good in _MOJIBAKE_MAP.items():
            s = s.replace(bad, good)
    return s


def validate_response(data) -> dict:
    """Sanity-check the Kimi response shape; raise on garbage."""
    if not isinstance(data, dict) or "categories" not in data:
        raise ValueError(f"Response missing 'categories' key: {str(data)[:200]}")
    if not isinstance(data["categories"], list):
        raise ValueError("'categories' is not a list")
    allowed = set(CATEGORIES)
    cleaned: list[dict] = []
    for cat in data["categories"]:
        if not isinstance(cat, dict):
            continue
        name = cat.get("name")
        bullets = cat.get("bullets") or []
        if name not in allowed or not isinstance(bullets, list):
            continue
        good_bullets = []
        for b in bullets:
            if not (isinstance(b, dict) and b.get("text")):
                continue
            text = _fix_mojibake(str(b["text"]).strip())
            # Drop "nothing found" placeholder bullets the model sometimes
            # emits instead of omitting an empty category.
            if _PLACEHOLDER_RE.search(text):
                continue
            good_bullets.append({
                "text": text,
                "source_ids": [str(s) for s in (b.get("source_ids") or [])],
            })
        if good_bullets:
            cleaned.append({"name": name, "bullets": good_bullets})
    # Empty result is legitimate when no rule changes occurred in the window —
    # the prompt instructs Kimi to prefer empty over misclassifying market
    # commentary as a regulation. Just log it and return the empty shape so
    # the dashboard can render an "no rule changes this period" note.
    if not cleaned:
        print("[briefing] note: Kimi returned 0 qualifying regulatory actions", flush=True)
    return {"categories": cleaned}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=730,
                    help="Look-back window for input items (default 730 = 2y). "
                         "The briefing is a cumulative snapshot of currently-"
                         "active rules; 1y misses rules set earlier but still "
                         "in force. ~175 items / ~66k tokens at 2y, comfortably "
                         "within moonshot-v1-128k. 3y (~1095) gets close to the "
                         "context limit — raise the model/trim body-cap first.")
    ap.add_argument("--body-cap", type=int, default=3000,
                    help="Max chars per item body (default 3000). Large enough "
                         "that a release's full rate table + bullet list fits "
                         "without truncation.")
    ap.add_argument("--samples", type=int, default=4,
                    help="Generate N candidate briefings and keep the best by "
                         "(category coverage, numeric bullets, total bullets). "
                         "Counters Kimi's run-to-run variance. Default 4.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the prompt + print stats but skip the LLM call.")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        # init_schema covers news_items, regulation_briefings, regulation_baseline.
        init_schema(conn)
        items = fetch_input(conn, args.window_days, args.body_cap)
        baseline = fetch_baseline(conn)

    print(f"[briefing] {len(items)} TCMB+BDDK items with body in last {args.window_days}d", flush=True)
    if baseline:
        print(f"[briefing] grounding on baseline: {baseline['title']} "
              f"({len(baseline['content'])} chars)", flush=True)
    else:
        print("[briefing] no baseline found — composing from feed alone "
              "(run scripts/ingest_policy_baseline.py to add one)", flush=True)
    if not items:
        print("[briefing] nothing to summarize; exiting.")
        return

    messages = build_messages(items, baseline)
    approx_input_chars = sum(len(m["content"]) for m in messages)
    print(f"[briefing] prompt approx {approx_input_chars:,} chars "
          f"(~{approx_input_chars // 3:,} tokens)", flush=True)

    if args.dry_run:
        print("[briefing] --dry-run; skipping LLM call.")
        return

    # Kimi output varies run-to-run (one sample gives 11 rich bullets, the
    # next 5 thin ones) and occasionally returns malformed JSON. Generate a
    # few candidates and keep the most COMPLETE one — most total bullets, then
    # most categories. This both counters the completeness variance and
    # absorbs one-off parse failures.
    t0 = time.time()
    candidates: list[tuple[int, int, dict, dict]] = []
    for attempt in range(1, args.samples + 1):
        response = kimi.chat_completion(messages, temperature=0.3, json_object=True)
        try:
            parsed = kimi.extract_json(response)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[briefing] sample {attempt}/{args.samples}: bad JSON ({e})", flush=True)
            continue
        v = validate_response(parsed)
        all_bullets = [b for c in v["categories"] for b in c["bullets"]]
        n_specific = sum(1 for b in all_bullets if re.search(r"\d", b["text"]))
        # Rank: category coverage first (completeness), then bullets carrying a
        # concrete number (specificity), then total bullets. This stops the
        # picker from rewarding a verbose-but-vague or category-dropping sample.
        score = (len(v["categories"]), n_specific, len(all_bullets))
        candidates.append((score, v, response))
        print(f"[briefing] sample {attempt}/{args.samples}: "
              f"{len(v['categories'])} categories, {n_specific}/{len(all_bullets)} "
              f"bullets with numbers", flush=True)
    if not candidates:
        raise SystemExit("[briefing] no parseable Kimi response across all samples")
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, validated, response = candidates[0]
    elapsed = time.time() - t0
    model_used = response.get("model", "")
    print(f"[briefing] picked best of {len(candidates)}: "
          f"{len(validated['categories'])} categories, "
          f"{sum(len(c['bullets']) for c in validated['categories'])} bullets "
          f"(in {elapsed:.1f}s)", flush=True)

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO regulation_briefings
               (generated_at, window_days, item_count, model, prompt_version,
                categories_json, raw_response)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                args.window_days,
                len(items),
                model_used,
                PROMPT_VERSION,
                json.dumps(validated, ensure_ascii=False),
                json.dumps(response, ensure_ascii=False)[:50_000],
            ),
        )
        conn.commit()
    print("[briefing] stored in regulation_briefings.")


if __name__ == "__main__":
    main()
