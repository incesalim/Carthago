"""Per-category regulatory snapshot for the /regulation tab.

Architecture (why per-category):
  A single LLM call asked to compose all categories at once could not reliably
  satisfy completeness + specificity + currency + correct categorization — it
  traded them off run-to-run (dropping Credit Cards/CAR, filing RR rules under
  Deposit Share, citing year-old figures). So we make ONE focused call per
  category instead, each scoped to a single section with the baseline as the
  scaffold and the recent feed as updates. Focused calls are individually
  reliable, so the assembled snapshot is complete and consistent.

Grounding:
  Each call sees the TCMB annual "Monetary Policy for YYYY" baseline (the
  regime at year start — see scripts/ingest_policy_baseline.py) plus the
  recent TCMB/BDDK feed (updates since). The model starts from the baseline
  for that section and applies later-dated press releases on top.

Usage (local dev needs KIMI_API_KEY):
  python scripts/summarize_regulations.py
  python scripts/summarize_regulations.py --dry-run
  python scripts/summarize_regulations.py --only-category "Regulations on RRs"

The weekly workflow runs this, then push_to_d1.py syncs the new row to D1.
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

PROMPT_VERSION = "2026-05-29.v10-percat"

# Fixed sections, in display order, named to match BBVA Research's Turkish
# Banking Sector report. Each gets its own focused LLM call.
CATEGORY_SPECS: list[tuple[str, str]] = [
    ("Monetary Policy Stance",
     "the CURRENT policy rate (one-week repo auction rate), the interest-rate "
     "corridor (overnight lending and borrowing rates), the latest MPC decision "
     "and the easing/holding/tightening direction, and core funding & liquidity "
     "operations (repo auctions, FX swaps, liquidity bills). NOT capital ratios, "
     "NOT reserve requirements, NOT loan caps."),
    ("Regulations for TL Deposit Share",
     "ONLY the TRY deposit-share rules: real-person and legal-person deposit-"
     "share growth targets by bank ratio band, tolerance ranges, commission "
     "rates tied to the TL share, the calculation period, and the FX-rate basis "
     "used. NOT reserve requirements, NOT loan rules."),
    ("Loan Growth Caps",
     "TL and FC loan growth limits and their cadence (e.g. 8-week cycles): caps "
     "for SME vs non-SME commercial loans, general-purpose, auto, and overdraft "
     "loans; exemptions (export, investment, agriculture, tradesmen, KOSGEB, "
     "CGF/'breath' credits); SME size thresholds; housing loan-to-value rules."),
    ("Regulations on RRs",
     "Reserve Requirement Ratios (RRR / zorunlu karsilik): ratios by deposit "
     "type and maturity, FC deposits/liabilities, funds from repo transactions "
     "abroad, loans/deposits from banks abroad, indexed deposits; remuneration "
     "of required reserves; blocked-account maintenance ratios."),
    ("Regulations for CARs",
     "Capital Adequacy Ratio rules ONLY (about BANK CAPITAL): RWA risk weights, "
     "forbearances such as fixing the FX rate used in credit-risk calculations, "
     "treatment of HTC&S securities revaluation, capital floors/buffers. NOT the "
     "policy rate, NOT reserve requirements."),
    ("Regulations on Credit Cards",
     "credit-card rules: maximum monthly contractual and overdue interest rates "
     "by balance tier, minimum-payment ratios, cash-withdrawal/installment "
     "limits, total credit-card limit rules, and fee caps."),
    ("Other Regulatory Actions",
     "material rule changes that do NOT fit any section above — e.g. payment-"
     "system rules (FAST, open banking, digital lira), new operational "
     "frameworks, or structurally novel licenses. Use sparingly; do NOT repeat "
     "rules already covered by another section."),
]

PER_CATEGORY_SYSTEM = """You are compiling ONE section of a Turkish banking-sector
regulatory snapshot in the style of BBVA Research's Monthly Turkish Banking
Sector Report. The snapshot states the rules CURRENTLY IN FORCE.

THIS SECTION: "{name}"
Include ONLY rules that belong here: {desc}
Rules that belong to a different section must be left out entirely.

INPUT (in order):
  1. BASELINE — TCMB's annual "Monetary Policy for YYYY" document. Its annex
     tables are the AUTHORITATIVE regime as of the start of the policy year.
     Use it as the scaffold for this section.
  2. DATED PRESS RELEASES — TCMB/BDDK updates since. Each item has id, source,
     date (YYYY-MM-DD), title, body (may contain Markdown tables / bullet lists).

HOW TO COMPILE:
  - Start from the baseline for THIS section, then apply the dated press
    releases as updates.
  - CURRENCY: report the CURRENT value, and NEVER one older than the baseline.
    The baseline already supersedes prior years; only a press release dated
    AFTER the baseline overrides a baseline value (the latest date wins).
  - SPECIFICITY: every bullet MUST carry the concrete number(s) — rate, cap,
    ratio, threshold, limit — with units. Never write a vague bullet that names
    a rule without its figures. The numbers are in the baseline annex tables and
    the press-release bodies; extract them.
  - Lead with the rule (the number), not the regulator. Translate Turkish to
    clear English. Group tightly-coupled sub-rules into one BBVA-style bullet;
    otherwise give each distinct rule its own bullet.
  - Cite source ids verbatim in source_ids (e.g. "tcmb:ANO2026-21", "bddk:2286").
    The baseline itself needs no id.

EXCLUDE (never bullets): market observations / MPC commentary ("loan growth was
2.7%"), single-bank licensing, data-publication notices, internal HR notices.
Never output a placeholder bullet that says nothing was found.

OUTPUT: a single JSON object: {{"bullets": [{{"text": "...", "source_ids": ["..."]}}]}}
If this section genuinely has no qualifying rule even in the baseline, return
{{"bullets": []}}. Output VALID JSON only — no markdown fences."""


# --- text hygiene ----------------------------------------------------------

_MOJIBAKE_MAP = {
    "Ã¼": "ü", "Ãœ": "Ü", "Ã§": "ç", "Ã‡": "Ç", "Ã¶": "ö", "Ã–": "Ö",
    "ÄŸ": "ğ", "Äž": "Ğ", "Ä±": "ı", "Ä°": "İ", "ÅŸ": "ş", "Åž": "Ş",
    "Ã¢": "â", "Ã‚": "Â", "â‚º": "₺", "â€™": "’", "â€œ": "“", "â€\x9d": "”",
    "â€“": "–", "â€”": "—",
}


def _fix_mojibake(s: str) -> str:
    """Repair UTF-8-as-Latin-1 mojibake (e.g. 'TÃ¼rkiye' -> 'Türkiye').

    Kimi's response double-encodes Turkish characters. Replace the known
    digraphs directly so mixed strings (with a real ₺/İ) are still repaired."""
    if "Ã" in s or "Å" in s or "Ä" in s or "â€" in s:
        for bad, good in _MOJIBAKE_MAP.items():
            s = s.replace(bad, good)
    return s


_PLACEHOLDER_RE = re.compile(
    r"no specific|not mentioned|mentioned in the provided|"
    r"no (?:relevant|such|applicable) |none (?:were|was|found)|"
    r"no regulations? (?:regarding|on|were|was)",
    re.IGNORECASE,
)


def clean_bullets(raw) -> list[dict]:
    """Validate + sanitize a category's bullets: require text, repair mojibake,
    drop 'nothing found' placeholders, normalize source_ids."""
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for b in raw:
        if not (isinstance(b, dict) and b.get("text")):
            continue
        text = _fix_mojibake(str(b["text"]).strip())
        if not text or _PLACEHOLDER_RE.search(text):
            continue
        out.append({
            "text": text,
            "source_ids": [str(s) for s in (b.get("source_ids") or [])],
        })
    return out


# --- data ------------------------------------------------------------------

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


def build_context(items: list[dict], baseline: dict | None) -> str:
    """Shared user-message context (baseline + feed), reused for every section."""
    parts: list[str] = []
    if baseline:
        parts.append(
            f"==================== BASELINE ====================\n"
            f"{baseline['title']} — authoritative regime as of the start of the "
            f"policy year; annex tables list every rule in force. Use as scaffold.\n\n"
            f"{baseline['content']}"
        )
    parts.append(
        "==================== DATED PRESS RELEASES (updates since) ====================\n"
        f"Items ({len(items)}):\n{json.dumps(items, ensure_ascii=False)}"
    )
    return "\n\n".join(parts)


# --- generation ------------------------------------------------------------

def generate_category(name: str, desc: str, context: str, retries: int) -> tuple[list[dict], str]:
    """One focused call (with parse-retry) for a single section. Returns
    (bullets, model). Keeps the most specific parse seen across attempts."""
    sys_prompt = PER_CATEGORY_SYSTEM.format(name=name, desc=desc)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": context},
    ]
    best: list[dict] | None = None
    best_specific = -1
    model = ""
    for attempt in range(1, retries + 1):
        try:
            resp = kimi.chat_completion(messages, temperature=0.2, json_object=True)
            parsed = kimi.extract_json(resp)
        except Exception as e:  # noqa: BLE001 - network/JSON variance; retry
            print(f"  [{name}] attempt {attempt}/{retries} failed: {type(e).__name__}: {e}", flush=True)
            continue
        model = resp.get("model", "") or model
        bullets = clean_bullets(parsed.get("bullets") if isinstance(parsed, dict) else None)
        n_specific = sum(1 for b in bullets if re.search(r"\d", b["text"]))
        if n_specific > best_specific:
            best, best_specific = bullets, n_specific
        if bullets:  # got a usable answer — no need to spend another call
            break
    return (best or []), model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta-days", type=int, default=330,
                    help="Look-back for the UPDATE feed layered on the baseline "
                         "(default 330). The baseline carries the cumulative "
                         "year-start regime; this only needs recent revisions.")
    ap.add_argument("--body-cap", type=int, default=3000,
                    help="Max chars per item body (default 3000).")
    ap.add_argument("--cat-retries", type=int, default=2,
                    help="Parse/quality retries per section (default 2).")
    ap.add_argument("--only-category", default=None,
                    help="Generate just one section (exact name) for debugging.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build context + print stats but make no LLM calls.")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)
        items = fetch_input(conn, args.delta_days, args.body_cap)
        baseline = fetch_baseline(conn)

    print(f"[briefing] {len(items)} update items in last {args.delta_days}d", flush=True)
    if baseline:
        print(f"[briefing] baseline: {baseline['title']} ({len(baseline['content'])} chars)", flush=True)
    else:
        print("[briefing] WARNING: no baseline — run scripts/ingest_policy_baseline.py", flush=True)

    context = build_context(items, baseline)
    specs = [s for s in CATEGORY_SPECS if not args.only_category or s[0] == args.only_category]
    if not specs:
        print(f"[briefing] no category matches --only-category {args.only_category!r}")
        return 1

    approx = len(PER_CATEGORY_SYSTEM) + len(context)
    print(f"[briefing] per-section context ~{approx // 3:,} tokens x {len(specs)} sections", flush=True)
    if args.dry_run:
        print("[briefing] --dry-run; skipping LLM calls.")
        return 0

    t0 = time.time()
    categories: list[dict] = []
    models: set[str] = set()
    for name, desc in specs:
        bullets, model = generate_category(name, desc, context, args.cat_retries)
        if model:
            models.add(model)
        print(f"[briefing] {name}: {len(bullets)} bullets", flush=True)
        if bullets:
            categories.append({"name": name, "bullets": bullets})

    n_bullets = sum(len(c["bullets"]) for c in categories)
    print(f"[briefing] assembled {len(categories)} sections, {n_bullets} bullets "
          f"in {time.time() - t0:.1f}s", flush=True)
    if not categories:
        raise SystemExit("[briefing] no sections produced any bullets — aborting (kept previous row).")

    payload = {"categories": categories}
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)
        conn.execute(
            """INSERT OR REPLACE INTO regulation_briefings
               (generated_at, window_days, item_count, model, prompt_version,
                categories_json, raw_response)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                args.delta_days,
                len(items),
                ",".join(sorted(models)),
                PROMPT_VERSION,
                json.dumps(payload, ensure_ascii=False),
                None,
            ),
        )
        conn.commit()
    print("[briefing] stored in regulation_briefings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
