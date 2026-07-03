"""Tag press/google_news items with the bank(s) they mention.

Yahoo-Finance-style per-ticker news, done deterministically: a hand-curated
alias map (data/news/bank_aliases.json) is compiled into per-bank regexes and
matched against each item's title + summary (all we store for those sources).
Matches land in the `news_item_banks` junction table — one row per
article × bank, so a story naming several banks surfaces on each bank's
/banks/[ticker] page. `news_items.ticker` keeps its KAP semantics untouched.

Matching reuses press.py's Turkish machinery: `_normalize_tr` lowercasing and
LEFT-word-boundary regexes so agglutinative suffixes still match ("akbank"
catches "Akbank'ın"/"AKBANKTAN") while "garantili" can't hit "garanti".
Aliases that are (or end in) a common Turkish word additionally get a RIGHT
boundary ("word" mode): "teb" must not match "tebliğ", "ing" must not match
"İngiltere", "yapı kredi" must not match "yapı kredisi". `\\b` still matches
before an apostrophe, so suffixed proper nouns ("TEB'den") work.

`retag_all` is a pure-local post-step of scripts/sync_news.py (no network):
it recomputes tags for ALL stored press/google rows every run, so alias-map
edits apply retroactively and the first run doubles as the backfill. Only
changed rows are written (fresh `fetched_at` → picked up by push_to_d1's
incremental sync); rows a match no longer supports are deleted locally AND
queued in the `d1_pending_deletes` outbox, since the D1 push is otherwise
INSERT OR REPLACE-only and would leave orphan tags remotely.

Stdlib-only (plus press._normalize_tr) so tests run under CI's minimal deps.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from src.news.sources.press import _normalize_tr

REPO_ROOT = Path(__file__).resolve().parents[2]
ALIASES_FILE = REPO_ROOT / "data" / "news" / "bank_aliases.json"


def _fold(s: str | None) -> str:
    """Turkish-normalize, then fold dotless ı → i for matching only.

    _normalize_tr maps uppercase ASCII 'I' to 'ı' (correct Turkish), which
    mangles acronyms/brands in caps: "ING" → "ıng", "ICBC" → "ıcbc",
    "GARANTI" (sloppy ASCII caps) → "garantı" — none of which would hit an
    alias spelled with 'i'. Folding both the aliases and the text to 'i'
    makes matching dot-insensitive; no two aliases are distinguished only
    by ı-vs-i, and boundary rules are unaffected ("ingiltere" still can't
    match word-mode "ing")."""
    return _normalize_tr(s).replace("ı", "i")

# Only journalism sources get tagged; kap rows already carry their bank in
# news_items.ticker, and tcmb/bddk are regulator-wide.
TAGGED_SOURCES = ("press", "google_news")

# Hard-coded fallback so the pipeline still works if bank_aliases.json is
# missing/corrupt. Kept in sync with the JSON by hand (press.py convention).
DEFAULT_ALIASES: dict[str, dict[str, list[str]]] = {
    "AKBNK": {"prefix": ["akbank"]},
    "AKTIF": {"prefix": ["aktifbank", "aktif yatırım bankas"], "word": ["aktif bank"]},
    "ALBRK": {"prefix": ["albaraka"]},
    "ALNTF": {"prefix": ["alternatifbank"], "word": ["alternatif bank"]},
    "ANADOLU": {"prefix": ["anadolubank"]},
    "ATBANK": {"prefix": ["arap türk bankas", "a&t bank"]},
    "BURGAN": {"prefix": ["burgan"]},
    "DENIZ": {"prefix": ["denizbank"]},
    "EMLAK": {"word": ["emlak katılım"]},
    "EXIM": {"prefix": ["eximbank", "ihracat kredi bankas"]},
    "FIBA": {"prefix": ["fibabanka"]},
    "GARAN": {"prefix": ["garanti bbva", "garanti bankas"]},
    "HALKB": {"prefix": ["halkbank", "halk bankas"]},
    "HSBC": {"prefix": ["hsbc"]},
    "ICBCT": {"prefix": ["icbc"]},
    "ING": {"word": ["ing"]},
    "ISCTR": {"prefix": ["iş bankas", "is bankas", "işbank", "isbank"]},
    "KLNMA": {"prefix": ["kalkınma ve yatırım bankas"], "word": ["tkyb"]},
    "KUVEYT": {"prefix": ["kuveyt türk"]},
    "ODEA": {"prefix": ["odeabank", "odea bank"]},
    "PASHA": {"prefix": ["pashabank", "pasha bank", "pasha yatırım"]},
    "QNBFB": {"prefix": ["finansbank"], "word": ["qnb"]},
    "SKBNK": {"prefix": ["şekerbank", "sekerbank"]},
    "TEB": {"prefix": ["türk ekonomi bankas"], "word": ["teb"]},
    "TFKB": {"word": ["türkiye finans"]},
    "TSKB": {"prefix": ["sınai kalkınma"], "word": ["tskb"]},
    "VAKBN": {"prefix": ["vakıfbank", "vakıflar bankas"]},
    "VAKIFK": {"word": ["vakıf katılım"]},
    "YKBNK": {"prefix": ["yapıkredi"], "word": ["yapı kredi", "yapı ve kredi"]},
    "ZIRAAT": {"prefix": ["ziraat bankas"]},
    "ZIRAATK": {"word": ["ziraat katılım"]},
}


def load_aliases(path: Path = ALIASES_FILE) -> dict[str, dict[str, list[str]]]:
    """Read the alias map from bank_aliases.json, falling back to
    DEFAULT_ALIASES (mirrors press._load_feeds)."""
    if not Path(path).exists():
        return DEFAULT_ALIASES
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        banks = data.get("banks") or {}
        return banks or DEFAULT_ALIASES
    except (json.JSONDecodeError, OSError):
        return DEFAULT_ALIASES


def compile_matchers(
    aliases: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, re.Pattern[str]]:
    """One compiled alternation per ticker. Every branch is anchored at a
    LEFT word boundary; "word"-mode branches get a RIGHT boundary too."""
    out: dict[str, re.Pattern[str]] = {}
    for ticker, spec in (aliases or load_aliases()).items():
        branches = [re.escape(_fold(a)) for a in spec.get("prefix", [])]
        branches += [re.escape(_fold(a)) + r"\b" for a in spec.get("word", [])]
        if branches:
            out[ticker] = re.compile(r"\b(?:" + "|".join(branches) + r")", re.UNICODE)
    return out


_MATCHERS: dict[str, re.Pattern[str]] | None = None


def _matchers() -> dict[str, re.Pattern[str]]:
    global _MATCHERS
    if _MATCHERS is None:
        _MATCHERS = compile_matchers()
    return _MATCHERS


def match_banks(title: str | None, summary: str | None = None) -> dict[str, str]:
    """Ticker → 'title' | 'summary' for every bank the item mentions.
    A title hit outranks (and hides) a summary hit for the same bank."""
    t = _fold(title)
    s = _fold(summary)
    out: dict[str, str] = {}
    for ticker, rx in _matchers().items():
        if t and rx.search(t):
            out[ticker] = "title"
        elif s and rx.search(s):
            out[ticker] = "summary"
    return out


def retag_all(conn: sqlite3.Connection) -> dict[str, int]:
    """Recompute news_item_banks from scratch against current aliases.

    Full pass over all press/google rows (~1k rows of regex — cheap), then a
    diff against the stored tags: only new/changed rows are written (fresh
    fetched_at so the incremental D1 push ships them); stale rows — an alias
    edit untagged the item, or the item itself was purged from news_items —
    are deleted locally and queued in the d1_pending_deletes outbox.
    """
    placeholders = ",".join("?" * len(TAGGED_SOURCES))
    items = conn.execute(
        f"SELECT source, external_id, title, summary FROM news_items "
        f"WHERE source IN ({placeholders})",
        TAGGED_SOURCES,
    ).fetchall()

    desired: dict[tuple[str, str, str], str] = {}
    for source, ext_id, title, summary in items:
        for ticker, matched_in in match_banks(title, summary).items():
            desired[(source, ext_id, ticker)] = matched_in

    existing: dict[tuple[str, str, str], str] = {
        (source, ext_id, ticker): matched_in
        for source, ext_id, ticker, matched_in in conn.execute(
            "SELECT source, external_id, ticker, matched_in FROM news_item_banks"
        )
    }

    added = {k: v for k, v in desired.items() if existing.get(k) != v}
    stale = [k for k in existing if k not in desired]

    if added:
        conn.executemany(
            "INSERT OR REPLACE INTO news_item_banks"
            " (source, external_id, ticker, matched_in, fetched_at)"
            " VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [(s, e, t, w) for (s, e, t), w in added.items()],
        )
    if stale:
        conn.executemany(
            "DELETE FROM news_item_banks"
            " WHERE source = ? AND external_id = ? AND ticker = ?",
            stale,
        )
        # Values are internal identifiers (fixed source strings, hex ids, our
        # tickers) — no quoting hazards; same literal-SQL outbox as tefas/kap.
        conn.executemany(
            "INSERT INTO d1_pending_deletes (sql) VALUES (?)",
            [
                (
                    f"DELETE FROM news_item_banks WHERE source='{s}'"
                    f" AND external_id='{e}' AND ticker='{t}';",
                )
                for s, e, t in stale
            ],
        )
    conn.commit()
    return {
        "items": len(items),
        "tagged_items": len({(s, e) for s, e, _ in desired}),
        "tags": len(desired),
        "added": len(added),
        "removed": len(stale),
    }
