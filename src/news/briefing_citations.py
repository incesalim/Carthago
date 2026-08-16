"""Verify that a briefing bullet's citations actually support it.

The page's contract is "every claim carries its source", and it means it:
`buildChangelog` in web/app/lib/regulation.ts drops any bullet whose ids
resolve to nothing — an unsourced sentence from a model is not something a
reader can check. What nothing verified until 2026-08-16 is whether the CITED
release is the one that STATES the figure: the live briefing attributed the
policy-rate corridor (37% / 40% / 35.5%) to the same-day "Türkiye and Syria
sign a deposit-account agreement" release, whose body contains no percentage
at all, while ANO2026-28 — the actual Press Release on Interest Rates — sat
one id away. The reader got the right number, the wrong instrument, and the
wrong date chip.

The check is deterministic and precision-first, in this lane's tradition:

- Only PERCENTAGES are checked (`37%` / `37 percent`), matched numerically.
  They are the regulatory payload, and they dodge false hits on years,
  version numbers and "USD 50 billion". Production bodies carry them in both
  forms — tables print "| 4% | 3% |", prose prints "at 37 percent"
  (calibrated against D1 on 2026-08-16: ANO2026-21, ANO2026-06, ANO2026-28).
- A bullet's own transition values ("…, down from 2%") are excluded first —
  the source that states the NEW cap need not restate the old one.
- A citation SUPPORTS a bullet when its body carries every remaining
  percentage. A bullet with no percentages is only checked for the id
  existing in the feed (there is no number to anchor on, and subject
  matching against an 8,000-char body is the documented false-positive
  machine this lane already rejected twice).

Repair is strip-then-ask, never auto-repoint: picking "the newest release
whose body contains 40%" re-derives supersession by content — the exact
mechanism behind the reverted supersession note. Unsupported ids are
stripped; a figure-bearing bullet left with no citation gets one pointed
retry telling the model to re-cite; if that fails the bullet is dropped,
because the page would refuse to render it anyway and a figure nobody can
check must not ship.
"""

from __future__ import annotations

import sqlite3

from .briefing_validate import _PCT_RE, _transition_stale_values


def _norm(tok: str) -> str:
    return f"{float(tok):g}"


def bullet_current_pcts(text: str) -> set[str]:
    """The percentages a bullet asserts as CURRENT — its own "down from X"
    values excluded, so a citation need only state the value now in force."""
    pcts = {_norm(m.group(1)) for m in _PCT_RE.finditer(text)}
    return pcts - _transition_stale_values(text)


def body_pcts(text: str) -> set[str]:
    return {_norm(m.group(1)) for m in _PCT_RE.finditer(text or "")}


def supports(bullet_text: str, source_body: str) -> bool:
    """True when the source states every current percentage the bullet does.
    A bullet without percentages is vacuously supported — existence of the id
    is the only thing checkable for prose claims."""
    need = bullet_current_pcts(bullet_text)
    return need <= body_pcts(source_body) if need else True


def audit_citations(bullets: list[dict], items_by_id: dict[str, dict]) -> list[dict]:
    """Per-bullet citation audit. Each finding:
    {index, text, unknown (ids not in the feed), unsupported (ids whose body
    lacks the bullet's figures), supported (ids that carry them)}."""
    out: list[dict] = []
    for i, b in enumerate(bullets):
        text = b.get("text", "")
        unknown: list[str] = []
        unsupported: list[str] = []
        supported_ids: list[str] = []
        for sid in b.get("source_ids") or []:
            item = items_by_id.get(sid)
            if item is None:
                unknown.append(sid)
            elif supports(text, f"{item.get('title') or ''}\n{item.get('body') or ''}"):
                supported_ids.append(sid)
            else:
                unsupported.append(sid)
        out.append({"index": i, "text": text, "unknown": unknown,
                    "unsupported": unsupported, "supported": supported_ids})
    return out


def strip_unsupported(bullets: list[dict], items_by_id: dict[str, dict],
                      ) -> tuple[list[dict], list[dict], list[dict]]:
    """Remove unknown/unsupported ids from each bullet. Returns
    (bullets, stripped_findings, dead) where `dead` lists the figure-bearing
    bullets that LOST every citation — the ones the page would not render and
    the pointed retry should re-cite."""
    findings = audit_citations(bullets, items_by_id)
    stripped: list[dict] = []
    dead: list[dict] = []
    out: list[dict] = []
    for b, f in zip(bullets, findings):
        bad = f["unknown"] + f["unsupported"]
        if not bad:
            out.append(b)
            continue
        stripped.append(f)
        kept_ids = f["supported"]
        nb = {**b, "source_ids": kept_ids}
        out.append(nb)
        if not kept_ids and bullet_current_pcts(f["text"]) and (b.get("source_ids") or []):
            dead.append(f)
    return out, stripped, dead


def drop_uncited_figures(bullets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Final pass: a figure-bearing bullet with no citation left cannot be
    checked by a reader and is not rendered by the page — drop it rather than
    store it. Prose bullets (no percentages) pass through untouched."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for b in bullets:
        if not (b.get("source_ids") or []) and bullet_current_pcts(b.get("text", "")):
            dropped.append(b)
        else:
            kept.append(b)
    return kept, dropped


def citation_addendum(dead: list[dict]) -> str:
    """The repair message for a re-citation retry. Names the defective bullets
    and the RULE for citing; never suggests which id to use — that choice must
    come from the model reading the feed, or the check stops measuring it."""
    lines = [
        "REVISION — some bullets of your draft cite releases that do not state",
        "their figures (a same-day release on another topic is not a source).",
        "For each bullet below, re-cite from the DATED PRESS RELEASES provided:",
        "a cited id's own body must state the bullet's percentage(s). If no",
        "provided release states a figure, take the figure's bullet out rather",
        "than citing something adjacent. Keep every other bullet unchanged.",
        "",
    ]
    for f in dead:
        lines.append(f"  - {f['text'][:160]}")
    return "\n".join(lines)


def fetch_feed_items(conn: sqlite3.Connection, window_days: int, body_cap: int) -> list[dict]:
    """The briefing's update feed — one query, one shape, shared by the
    generator (context building + citation gate) and the after-the-fact
    checker (scripts/check_briefing_facts.py), so the two can never audit
    against different feeds. Moved verbatim from summarize_regulations."""
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
