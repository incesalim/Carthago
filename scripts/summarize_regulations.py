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

PROMPT_VERSION = "2026-05-12.v3"

# Fixed 6-category schema, named to match BBVA Research's Turkish Banking
# Sector report so readers familiar with their format land smoothly.
# Order is enforced — Kimi outputs sections in this exact order.
CATEGORIES = [
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
       — Capital Adequacy Ratio: floors, RWA weights, forbearances on FX
         rate fixing in CAR calculations, HTC&S securities treatment.
  "Regulations on Credit Cards"
       — credit-card limits (overdraft, total), restructuring rules,
         interest-rate caps by balance tier, fee limits.
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
  1. Use EXACTLY the six category names listed above, in that order.
     Omit any category with zero qualifying bullets.
  2. Each bullet describes ONE rule (or one coherent rule cluster).
  3. If the input window contains zero qualifying regulatory rules,
     return: {"categories": []}
  4. Output VALID JSON only. No markdown fences."""


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


def build_messages(items: list[dict]) -> list[dict]:
    user = (
        f"Items ({len(items)}):\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        f"Generate the briefing JSON now."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


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
            if isinstance(b, dict) and b.get("text"):
                good_bullets.append({
                    "text": str(b["text"]).strip(),
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
    ap.add_argument("--window-days", type=int, default=365,
                    help="Look-back window for input items (default 365 — "
                         "BBVA-style briefing is a cumulative snapshot of "
                         "currently-active rules, not just recent changes).")
    ap.add_argument("--body-cap", type=int, default=1500,
                    help="Max chars per item body. Keeps prompt within "
                         "the 32k-context window for ~100 items. Raise + "
                         "switch KIMI_MODEL to moonshot-v1-128k for richer input.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the prompt + print stats but skip the LLM call.")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)
        # Ensure the briefings table exists locally too (CREATE TABLE IF NOT EXISTS).
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS regulation_briefings (
                generated_at TEXT NOT NULL PRIMARY KEY,
                window_days INTEGER NOT NULL,
                item_count INTEGER NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                categories_json TEXT NOT NULL,
                raw_response TEXT,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        items = fetch_input(conn, args.window_days, args.body_cap)

    print(f"[briefing] {len(items)} TCMB+BDDK items with body in last {args.window_days}d", flush=True)
    if not items:
        print("[briefing] nothing to summarize; exiting.")
        return

    messages = build_messages(items)
    approx_input_chars = sum(len(m["content"]) for m in messages)
    print(f"[briefing] prompt approx {approx_input_chars:,} chars "
          f"(~{approx_input_chars // 3:,} tokens)", flush=True)

    if args.dry_run:
        print("[briefing] --dry-run; skipping LLM call.")
        return

    t0 = time.time()
    response = kimi.chat_completion(
        messages,
        temperature=0.2,
        json_object=True,
    )
    parsed = kimi.extract_json(response)
    validated = validate_response(parsed)
    elapsed = time.time() - t0
    model_used = response.get("model", "")
    print(f"[briefing] Kimi responded in {elapsed:.1f}s "
          f"({len(validated['categories'])} categories, "
          f"{sum(len(c['bullets']) for c in validated['categories'])} bullets)",
          flush=True)

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
