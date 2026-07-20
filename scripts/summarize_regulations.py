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
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from notify import notify  # noqa: E402  (scripts/ is sys.path[0] under `python scripts/…`)
from src.news import kimi  # noqa: E402
from src.news._htmltext import fix_mojibake  # noqa: E402
from src.news.briefing_validate import describe, find_contradictions  # noqa: E402
from src.news.schema import init_schema  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"

# Feeds input_hash, so a bump forces one regeneration — which is what you want
# after a context change.
PROMPT_VERSION = "2026-07-20.v23-no-supersession-note"

# Fixed seed + temperature 0: this is an extraction task, so sampling buys
# nothing and costs run-to-run stability. Measured spread before this change:
# the fact-checklist score swung 46-77% across runs on identical input.
BRIEFING_SEED = 20260720

# Sections whose source data is NOT in our scraped feeds — the rules live in
# BDDK Resmî Gazete / Tebliğ, which we don't ingest yet. Generating them makes
# the model leak adjacent rules (CARs) or fabricate tier tables (Credit Cards),
# so they are skipped until a BDDK Tebliğ source is added (then drop them from
# this set / pass --include-unsourced).
UNSOURCED_CATEGORIES = {"Regulations for CARs", "Regulations on Credit Cards"}

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
  1. BASELINE: CURRENT FRAMEWORK — TCMB's annual "Monetary Policy for YYYY"
     document, minus its decision log. The standing framework at year start.
     Use it as the scaffold for this section.
  2. BASELINE: DATED DECISION LOG — a chronology (Annex 1) in which THE SAME
     RULE APPEARS SEVERAL TIMES as it was revised. Only the LATEST entry per
     rule is in force; earlier ones are superseded. Where nothing below revises
     a rule, this log's latest entry IS its current value.
  3. DATED PRESS RELEASES — TCMB/BDDK updates since. Each item has id, source,
     date (YYYY-MM-DD), title, body (may contain Markdown tables / bullet lists).

HOW TO COMPILE:
  - Start from the CURRENT FRAMEWORK for THIS section, then layer the DECISION
    LOG's latest entry per rule, then the dated press releases on top. Later
    always wins.
  - CURRENCY: report the CURRENT value only. For any rule, the LATEST-DATED
    statement wins — a press release overrides the framework, and a later
    release overrides an earlier one.
  - ONE VALUE PER RULE. Never print two figures for the same cap, ratio or rate
    as if both applied. If a limit changed, state only the value now in force
    (you may write "reduced from X to Y", but never a bare bullet asserting the
    old X somewhere else in the section).
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

DISCIPLINE — a short, correct section is the goal. It is BETTER to return 1-2
bullets, or even an empty list, than to pad. NEVER:
  - borrow a rule that belongs to a DIFFERENT section. Reserve-requirement /
    KKM (FX-protected deposit) rules belong ONLY to "Regulations on RRs";
    loan-growth limits ONLY to "Loan Growth Caps". Do not use them to fill
    "{name}".
  - include observed market data (growth rates, balances, averages — e.g.
    "the average four-week growth rate was 2.7%"). Those are not rules.
  - include narrative intent with no number ("will maintain a tight stance").
If "{name}" genuinely has few or no qualifying rules, return few or none.

OUTPUT: a single JSON object: {{"bullets": [{{"text": "...", "source_ids": ["..."]}}]}}
If this section genuinely has no qualifying rule even in the baseline, return
{{"bullets": []}}. Output VALID JSON only — no markdown fences."""


# --- text hygiene ----------------------------------------------------------

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
        text = fix_mojibake(str(b["text"]).strip())
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


def compute_input_hash(items: list[dict], baseline: dict | None) -> str:
    """Stable fingerprint of everything that determines the briefing: the feed
    items (ids/dates/bodies), the baseline content, and the prompt version.
    Used to skip regeneration when nothing changed."""
    blob = json.dumps(items, ensure_ascii=False, sort_keys=True)
    base = baseline["content"] if baseline else ""
    return hashlib.sha256(
        (PROMPT_VERSION + "\n" + base + "\n" + blob).encode("utf-8")
    ).hexdigest()


def fetch_baseline(conn: sqlite3.Connection) -> dict | None:
    """Latest annual policy baseline (the grounding scaffold), or None."""
    row = conn.execute(
        "SELECT year, title, content FROM regulation_baseline ORDER BY year DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"year": row[0], "title": row[1], "content": row[2]}


# "Annex 1: Monetary Policy Decisions Made in YYYY" is a DATED CHANGELOG, not a
# statement of the regime — its own Table 5 lists the SME growth limit at 2.5%
# (January 2025) and the FX limit falling 1.5% → 1% → 0.5% across three entries.
# The context previously introduced the whole document as "annex tables list every
# rule in force", so the model transcribed superseded entries as current: the
# 2026-07-19 briefing printed "2.5% monthly growth limit for SME loans" verbatim
# from that table alongside the actual 4.5% cap. Split it out and label it for
# what it is. Annex 2 is the MPC meeting calendar — no rules at all.
_ANNEX1_RE = re.compile(r"^\s*Annex 1[:.]", re.M)
_ANNEX2_RE = re.compile(r"^\s*Annex 2[:.]", re.M)


def split_baseline(content: str) -> tuple[str, str]:
    """Return (current_framework, decision_history). History is Annex 1 only;
    everything before it and from Annex 2 on describes the standing framework."""
    m1 = _ANNEX1_RE.search(content)
    if not m1:
        return content, ""
    m2 = _ANNEX2_RE.search(content, m1.end())
    end = m2.start() if m2 else len(content)
    history = content[m1.start():end].strip()
    framework = (content[:m1.start()] + "\n" + content[end:]).strip()
    return framework, history


def build_context(items: list[dict], baseline: dict | None) -> str:
    """Shared user-message context (baseline + feed), reused for every section."""
    parts: list[str] = []
    if baseline:
        framework, history = split_baseline(baseline["content"])
        parts.append(
            f"==================== BASELINE: CURRENT FRAMEWORK ====================\n"
            f"{baseline['title']} — the standing framework as of the start of the "
            f"policy year. Use as scaffold.\n\n"
            f"{framework}"
        )
        if history:
            parts.append(
                "============ BASELINE: DATED DECISION LOG (latest entry wins) ============\n"
                "A CHRONOLOGY of decisions, oldest to newest, in which THE SAME RULE "
                "APPEARS SEVERAL TIMES as it was revised. For any given rule only the "
                "LATEST-DATED entry is in force; every earlier entry for that rule is "
                "superseded and must NEVER be printed. A dated press release below "
                "overrides even the latest entry here.\n"
                "Read it as a log, not a list: if this log is the newest source for a "
                "rule (nothing below revises it), its latest entry IS the current "
                "value and you should report it.\n\n"
                f"{history}"
            )
    # NO supersession note. It was added to stop the model mixing an old FX
    # ratio table with the current one — a problem that turned out to be this
    # repo's own false positives, not the model. It never demonstrably helped,
    # and it demonstrably HURT: subject matching on an 8,000-char MPC summary
    # fires on incidental mentions, so the note named ANO2026-24 (which does not
    # discuss FX loans at all) as CURRENT for the FX loan cap and marked
    # ANO2026-06 — the release that actually sets it at 0.5% — as SUPERSEDED.
    # It told the model to ignore the only correct source. Machinery that is
    # unproven and has caused a wrong value does not stay.
    parts.append(
        "==================== DATED PRESS RELEASES (updates since) ====================\n"
        f"Items ({len(items)}):\n{json.dumps(items, ensure_ascii=False)}"
    )
    return "\n\n".join(parts)


# --- generation ------------------------------------------------------------

# Deterministic guards: a section that has no genuine source in our feeds
# (CARs / credit-card content lives in BDDK Resmî Gazete, which we don't scrape)
# tends to get filled with leaked rules from adjacent sections. Drop the leaks;
# if nothing genuine remains, the section is omitted rather than faked.
_CAR_OK = re.compile(r"capital|risk[- ]?weight|\brwa\b|forbearance|htc|own funds|buffer|leverage", re.I)
_CAR_LEAK = re.compile(r"reserve requirement|zorunlu|\bkkm\b|fx-protected|loan growth|deposit share|credit card", re.I)


def enforce_category(name: str, bullets: list[dict]) -> list[dict]:
    if name == "Regulations for CARs":
        return [b for b in bullets
                if _CAR_OK.search(b["text"]) and not _CAR_LEAK.search(b["text"])]
    return bullets


def generate_category(name: str, desc: str, context: str,
                      retries: int) -> tuple[list[dict], str, str]:
    """One focused call (with parse-retry) for a single section. Returns
    (bullets, model, provider). Keeps the most specific parse seen across attempts.

    `provider` is OpenRouter's upstream for this call (empty on a direct API).
    Worth recording: the same model id behaves very differently by upstream, so
    "which model" alone does not identify what produced a briefing."""
    sys_prompt = PER_CATEGORY_SYSTEM.format(name=name, desc=desc)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": context},
    ]
    best: list[dict] | None = None
    best_specific = -1
    model = ""
    provider = ""
    for attempt in range(1, retries + 1):
        try:
            resp = kimi.chat_completion(messages, temperature=0.0, json_object=True,
                                        seed=BRIEFING_SEED)
            parsed = kimi.extract_json(resp)
        except Exception as e:  # noqa: BLE001 - network/JSON variance; retry
            print(f"  [{name}] attempt {attempt}/{retries} failed: {type(e).__name__}: {e}", flush=True)
            continue
        model = resp.get("model", "") or model
        provider = resp.get("provider", "") or provider
        bullets = clean_bullets(parsed.get("bullets") if isinstance(parsed, dict) else None)
        n_specific = sum(1 for b in bullets if re.search(r"\d", b["text"]))
        if n_specific > best_specific:
            best, best_specific = bullets, n_specific
        if bullets:  # got a usable answer — no need to spend another call
            break
    return (best or []), model, provider


# Telegram hard-caps a message at 4096 chars and notify() trims at 4000; a full
# briefing runs longer than that, so split at SECTION boundaries rather than
# mid-bullet. Budget leaves room for the continuation header.
_TG_BUDGET = 3600


def notify_briefing(categories: list[dict], models: set[str], item_count: int,
                    baseline: dict | None, providers: set[str] | None = None,
                    stale: list[str] | None = None) -> None:
    """Post the briefing that just shipped. Never raises — a failed alert must
    not fail a good run (notify() already swallows network errors and no-ops
    when no channel is configured, which is what keeps the scratch bench quiet).
    """
    try:
        n_bullets = sum(len(c["bullets"]) for c in categories)
        # A bench run posts the same shape as the live weekly briefing, so it must
        # say so at the top: BRIEFING_LABEL is how test-openrouter.yml marks its
        # output as NOT the page you are reading. Unset in production.
        label = os.environ.get("BRIEFING_LABEL", "").strip()
        head = (
            (f"{label}\n" if label else "")
            + f"🏛 Regulation briefing — {len(categories)} sections, {n_bullets} bullets\n"
            f"model: {','.join(sorted(models)) or '?'}"
            # Name the upstream: the same model id behaves very differently across
            # OpenRouter providers, so the model alone doesn't identify the run.
            + (f" @ {','.join(sorted(providers))}" if providers else "")
            + f" · {item_count} feed items · "
            f"baseline: {baseline['title'] if baseline else 'NONE'}"
            # A section held back from last week must be visible, or the gate
            # trades a loud wrong answer for a quiet stale one.
            + ("\n⚠️ HELD BACK (kept last week's, would not validate): "
               + ", ".join(stale) if stale else "")
        )
        # Pack per BULLET, not per section: a section that alone exceeds the
        # budget would otherwise be handed to notify() and silently trimmed —
        # the same warn-and-carry-on failure that hid the missing baseline for
        # seven weeks. Spilled sections repeat their header marked "(cont.)".
        chunks: list[str] = []
        cur = head
        for cat in categories:
            hdr = f"▸ {cat['name']} ({len(cat['bullets'])})"
            if len(cur) + len(hdr) + 2 > _TG_BUDGET:
                chunks.append(cur)
                cur = ""
            cur = f"{cur}\n\n{hdr}" if cur else hdr
            for b in cat["bullets"]:
                line = f"• {b['text']}"
                if len(cur) + len(line) + 1 > _TG_BUDGET:
                    chunks.append(cur)
                    cur = f"{hdr} (cont.)"
                cur = f"{cur}\n{line}"
        if cur.strip():
            chunks.append(cur)

        # Log the outcome rather than relying on notify()'s silence-means-success:
        # it only speaks up on failure, so a working send and a run where nobody
        # was watching look identical in the log.
        ok = 0
        for i, chunk in enumerate(chunks, 1):
            prefix = f"({i}/{len(chunks)})\n" if len(chunks) > 1 else ""
            ok += bool(notify(prefix + chunk))
        print(f"[briefing] telegram: {ok}/{len(chunks)} message(s) sent "
              f"({n_bullets} bullets)", flush=True)
    except Exception as e:  # noqa: BLE001 — alerting is never worth a failed run
        print(f"[briefing] notify failed: {type(e).__name__}: {e}", flush=True)


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
    ap.add_argument("--include-unsourced", action="store_true",
                    help="Also generate sections in UNSOURCED_CATEGORIES (CARs, "
                         "Credit Cards). Off by default — enable once a BDDK "
                         "Tebliğ source backs them.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build context + print stats but make no LLM calls.")
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if inputs are unchanged since last run.")
    ap.add_argument("--require-baseline", action="store_true",
                    help="Fail instead of generating an ungrounded briefing when "
                         "no baseline is stored. The weekly workflow passes this: "
                         "a warning alone went unnoticed for seven weeks (see "
                         "docs/regulation_followups.md).")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)
        items = fetch_input(conn, args.delta_days, args.body_cap)
        baseline = fetch_baseline(conn)
        prev = conn.execute(
            "SELECT input_hash FROM briefing_input_state WHERE id = 1"
        ).fetchone()

    # NO pre-baseline cutoff. It was tried (v15) on the reasoning that a release
    # older than the baseline is already incorporated into it, and it did remove
    # real contradictions — but it silently deleted the whole "Regulations for TL
    # Deposit Share" section across three runs. The baseline does NOT carry those
    # rules: Annex 1's "Table 3. Decisions Regarding Deposits" extracts as a bare
    # header, so that section has always been fed by 2025 releases and nothing
    # else. Superseded duplicates are handled by the ONE VALUE PER RULE prompt
    # rule instead, which costs no coverage.
    print(f"[briefing] {len(items)} update items in last {args.delta_days}d", flush=True)
    if baseline:
        print(f"[briefing] baseline: {baseline['title']} ({len(baseline['content'])} chars)", flush=True)
    elif args.require_baseline:
        # Without the baseline every section is reconstructed from the press-release
        # feed alone, so any rule in force but not re-announced inside the window is
        # simply invisible — and the output still reads plausibly, which is why this
        # went unnoticed from 2026-05-29 to 2026-07-19. Refuse rather than ship a
        # briefing that looks complete and isn't.
        raise SystemExit(
            "[briefing] FATAL: no baseline stored, and --require-baseline is set.\n"
            "  The snapshot's regulation_baseline table is empty, so the briefing "
            "would be built from the feed alone.\n"
            "  Fix: dispatch summarize-regulations.yml with baseline_url set to the "
            "TCMB 'Monetary Policy for YYYY' PDF\n"
            "  (see docs/regulation_followups.md)."
        )
    else:
        print("[briefing] WARNING: no baseline — run scripts/ingest_policy_baseline.py", flush=True)

    # No-op when nothing changed: feed + baseline + prompt all identical to the
    # last run. Keeps the weekly cron from regenerating identical output (and
    # spending LLM calls) in quiet weeks.
    input_hash = compute_input_hash(items, baseline)
    if prev and prev[0] == input_hash and not args.force and not args.dry_run:
        print("[briefing] inputs unchanged since last run — skipping regeneration. "
              "(use --force to override)", flush=True)
        return 0

    context = build_context(items, baseline)
    specs = [
        s for s in CATEGORY_SPECS
        if (args.only_category and s[0] == args.only_category)
        or (not args.only_category
            and (args.include_unsourced or s[0] not in UNSOURCED_CATEGORIES))
    ]
    if not specs:
        print(f"[briefing] no category matches --only-category {args.only_category!r}")
        return 1

    approx = len(PER_CATEGORY_SYSTEM) + len(context)
    print(f"[briefing] per-section context ~{approx // 3:,} tokens x {len(specs)} sections", flush=True)
    if args.dry_run:
        print("[briefing] --dry-run; skipping LLM calls.")
        return 0

    # Previous briefing, loaded once: it is both the fallback for a section that
    # will not validate and the reference for the section-regression check below.
    prev_sections: dict[str, list[dict]] = {}
    with sqlite3.connect(str(DB_PATH)) as conn:
        prev_row = conn.execute(
            "SELECT categories_json FROM regulation_briefings "
            "ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    if prev_row:
        try:
            prev_sections = {c["name"]: c.get("bullets", [])
                             for c in json.loads(prev_row[0]).get("categories", [])}
        except (ValueError, TypeError, KeyError):
            prev_sections = {}

    t0 = time.time()
    categories: list[dict] = []
    models: set[str] = set()
    providers: set[str] = set()
    stale_sections: list[str] = []
    for name, desc in specs:
        bullets, model, provider = generate_category(name, desc, context, args.cat_retries)
        if model:
            models.add(model)
        if provider:
            providers.add(provider)
        kept = enforce_category(name, bullets)

        # Gate: a section must not state two values for one rule. This is the
        # lane's defining failure and the model cannot be instructed out of it
        # (v18 tried), so it is caught here instead. One regeneration, then the
        # previous week's verified text — on a regulatory reference, stale and
        # right beats fresh and self-contradicting.
        conflicts = find_contradictions([b["text"] for b in kept])
        if conflicts:
            print(f"[briefing] {name}: CONTRADICTION — regenerating\n"
                  + describe(conflicts, limit=2), flush=True)
            retry_bullets, r_model, r_provider = generate_category(
                name, desc, context, args.cat_retries)
            retry_kept = enforce_category(name, retry_bullets)
            retry_conflicts = find_contradictions([b["text"] for b in retry_kept])
            if retry_kept and not retry_conflicts:
                kept, conflicts = retry_kept, []
                models.add(r_model) if r_model else None
                providers.add(r_provider) if r_provider else None
                print(f"[briefing] {name}: clean on retry", flush=True)
            elif prev_sections.get(name):
                kept, conflicts = prev_sections[name], []
                stale_sections.append(name)
                print(f"[briefing] {name}: still contradicting — KEEPING LAST "
                      f"WEEK'S {len(kept)} bullets", flush=True)
            else:
                kept = []
                print(f"[briefing] {name}: still contradicting and no previous "
                      f"version — DROPPING the section", flush=True)

        dropped = len(bullets) - len(kept)
        print(f"[briefing] {name}: {len(kept)} bullets"
              + (f" via {provider}" if provider else "")
              + (f" ({dropped} leaked dropped)" if dropped else ""), flush=True)
        if kept:
            categories.append({"name": name, "bullets": kept})

    n_bullets = sum(len(c["bullets"]) for c in categories)
    print(f"[briefing] assembled {len(categories)} sections, {n_bullets} bullets "
          f"in {time.time() - t0:.1f}s", flush=True)
    if not categories:
        raise SystemExit("[briefing] no sections produced any bullets — aborting (kept previous row).")

    # A section that yields nothing is dropped from the payload with no error, and
    # the abort above only fires when EVERY section is empty — so a partial
    # provider failure ships a quietly shorter briefing that still reads fine.
    # (Observed: deepseek-v4-flash returned {"bullets":[]} for Other Regulatory
    # Actions and the section simply vanished.) Compare against the previous
    # briefing and speak up when a section that had content now has none.
    produced = {c["name"] for c in categories}
    if prev_sections:
        regressed = sorted(n for n, b in prev_sections.items()
                           if b and n not in produced)
        if regressed:
            msg = ("⚠️ Regulation briefing LOST a section that had content last run: "
                   + ", ".join(regressed))
            print(f"[briefing] {msg}", flush=True)
            try:
                notify(msg)
            except Exception as e:  # noqa: BLE001 — alerting must not fail the run
                print(f"[briefing] regression notify failed: {type(e).__name__}: {e}", flush=True)

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
        conn.execute(
            "INSERT OR REPLACE INTO briefing_input_state (id, input_hash, updated_at) "
            "VALUES (1, ?, ?)",
            (input_hash, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
    print("[briefing] stored in regulation_briefings.")
    # Only reached when the LLM actually ran: the unchanged-inputs and --dry-run
    # paths return earlier, so quiet weeks stay quiet.
    notify_briefing(categories, models, len(items), baseline, providers,
                    stale_sections)
    return 0


if __name__ == "__main__":
    sys.exit(main())
