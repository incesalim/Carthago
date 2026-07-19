#!/usr/bin/env python3
"""Print the newest local `regulation_briefings` row so two providers' output
can be read side by side in a CI log.

`summarize_regulations.py` prints bullet COUNTS, which is all the weekly cron
needs — but a count can't tell you whether a bullet is specific, current, or
correctly categorized, and those are exactly the axes the per-category
architecture exists to protect. So dump the text.

Scratch, paired with test-openrouter.yml (`task=regulation`). Reads the
runner's ephemeral SQLite only — never D1, never R2.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "bddk_data.db"


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "(unlabelled)"
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT generated_at, model, item_count, categories_json "
            "FROM regulation_briefings ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        print(f"[{label}] no briefing row found")
        return 1

    generated_at, model, item_count, categories_json = row
    payload = json.loads(categories_json)
    print(f"\n----- OUTPUT: {label} -----")
    print(f"  reported model: {model}   generated_at: {generated_at}   feed items: {item_count}")
    for cat in payload.get("categories", []):
        bullets = cat.get("bullets", [])
        # "specific" = contains a digit. The prompt's whole job is concrete
        # figures (a rate, a ratio, a date); a bullet without one is filler.
        n_spec = sum(1 for b in bullets if any(c.isdigit() for c in b.get("text", "")))
        print(f"\n  [{cat.get('name')}] {len(bullets)} bullets, {n_spec} with figures")
        for b in bullets:
            text = b.get("text", "")
            src = b.get("source") or b.get("url") or ""
            print(f"    - {text}")
            if src:
                print(f"      src: {src}")
    print("----- END -----\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
