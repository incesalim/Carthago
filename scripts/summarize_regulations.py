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

PROMPT_VERSION = "2026-05-12.v1"

# Fixed 6-category schema — keeps the briefing comparable week-over-week.
# Kimi must categorize each policy change into ONE of these.
CATEGORIES = [
    "TL Deposit Share Regulations",
    "Loan Growth & Limits",
    "Reserve Requirements",
    "Capital Adequacy",
    "Credit Cards & Consumer Credit",
    "Other Regulatory Actions",
]

SYSTEM_PROMPT = """You are summarizing Turkish banking-sector regulations for an analyst dashboard.
You receive a JSON list of regulatory press releases and announcements from
TCMB (Türkiye Cumhuriyet Merkez Bankası, central bank) and BDDK (Bankacılık
Düzenleme ve Denetleme Kurumu, banking regulator). Each item has:
  - id        (use this verbatim when citing sources)
  - source    ("tcmb" or "bddk")
  - date      (YYYY-MM-DD)
  - title     (Turkish or English)
  - body      (Turkish or English, may be truncated)

YOUR TASK: produce a thematic briefing in the BBVA Research Monthly
Turkish Banking Report style — short bullets emphasising *what changed*
and *by how much* (specific percentages, ratios, dates, thresholds).

OUTPUT: a single JSON object with this exact structure:
{
  "categories": [
    {
      "name": "<one of the fixed category names>",
      "bullets": [
        {
          "text": "<one or two sentences with specific numbers>",
          "source_ids": ["<id1>", "<id2>"]
        }
      ]
    }
  ]
}

RULES:
1. Use EXACTLY these category names (omit categories with no relevant
   items entirely):
     "TL Deposit Share Regulations"
     "Loan Growth & Limits"
     "Reserve Requirements"
     "Capital Adequacy"
     "Credit Cards & Consumer Credit"
     "Other Regulatory Actions"
2. Each bullet must describe a CONCRETE policy change with numbers
   where available (e.g. "Reserve requirement ratio for TL deposits raised
   from 17% to 20% effective [date]"). Skip items that are merely
   administrative (single-bank licensing, hiring notices, data-portal
   publication notices) — those go to "Other Regulatory Actions" only if
   genuinely material, else skip entirely.
3. Group related changes into one bullet and cite all relevant source ids.
4. Write bullets in clear English suitable for international analysts.
   The source text may be Turkish — translate as needed.
5. Be specific. "Various changes were made" is unacceptable; quote the
   actual numbers and dates from the body.
6. Output VALID JSON only. No markdown fences, no commentary outside the
   JSON object.
7. Categories list order should follow the fixed order above; do not invent
   new categories."""


def fetch_input(conn: sqlite3.Connection, window_days: int) -> list[dict]:
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
            "body": body[:2500],   # cap per-item body for token budget
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
    if not cleaned:
        raise ValueError("Kimi returned 0 valid category entries")
    return {"categories": cleaned}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=90,
                    help="Look-back window for input items (default 90).")
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
        items = fetch_input(conn, args.window_days)

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
