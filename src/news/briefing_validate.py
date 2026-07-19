"""Reject a regulation section that states two values for the same rule.

The lane's characteristic failure is not a missing bullet — it is two bullets
giving different values for the SAME rule, both as if in force. The 2026-07-19
briefing printed the SME loan cap at 2.5%, at 5% and at 4.5% in one section.
Every figure was real; two were superseded. A reader cannot tell which applies,
which is worse than saying nothing.

Resolving that is an LLM job that instruction does not make reliable — the model
must track supersession across a 34k-token context, and asking more firmly
measured no better (PROMPT_VERSION v18, reverted). So catch it downstream and
refuse to publish, the way `web/app/lib/prose.ts` refuses to print an uncomputed
claim.

WHY A CURATED SUBJECT LIST, not a generic structural check. The obvious
approach — two bullets sharing vocabulary but disagreeing on a percentage —
was built first and was unusable: in this domain almost every bullet shares
"reserve/requirement/funds/deposits/week", so it flagged "general-purpose 3%"
against "overdraft 1%" and "banks abroad 14%" against "FX deposits 32%". Those
are different rules with correctly different values. Since this GATES
publication, a false positive withholds a good briefing, so precision matters
more than coverage. What distinguishes rules here is their SUBJECT, and the
subjects are a short, stable list worth naming explicitly.

Adding a rule is one line in RULE_SUBJECTS.
"""

from __future__ import annotations

import re

_PCT_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:percent\b|%)")

# The subject of each rule the briefing states as a percentage. Order matters:
# the first match wins for a given span, so narrower patterns come first
# (non-SME before SME, which is a substring of it).
RULE_SUBJECTS: list[tuple[str, str]] = [
    # --- loan growth caps ---
    ("loan:non-sme",        r"non-?SME"),
    ("loan:sme",            r"\bSMEs?\b"),
    ("loan:general",        r"general[- ]purpose"),
    ("loan:vehicle",        r"\bvehicle\b|\bauto\b"),
    ("loan:overdraft",      r"overdraft"),
    ("loan:fx",             r"(?:foreign[- ]currency|\bFX\b|\bFC\b)[^.;]{0,40}?loans?"),
    # --- reserve requirements: NOT GATED (measured only) ---
    # Three attempts, three distinct false-positive classes, each of which held
    # a CORRECT section back on every run:
    #   1. maturity as the subject → "FX deposits up to 1 month 32%" collided
    #      with "funds from repo abroad up to 1 month 14%"
    #   2. a 30-char exclusion lookback missed "other FX liabilities (excluding
    #      deposits/participation funds and precious metal accounts)"
    #   3. liability type as the subject → "ADDITIONAL Turkish lira RR for FX
    #      deposits/participation funds, 2.5%" collided with the FX-deposit
    #      ratio itself at 32%/28% — a surcharge rule and a base rule sharing
    #      their entire vocabulary
    # RR rules overlap too much for a flat regex list, and this GATES
    # publication, so a false positive is expensive and a miss is not. Real RR
    # contradictions are still caught for OBSERVABILITY by the hand-verified
    # facts in scripts/check_briefing_facts.py, which alerts rather than blocks.
    # --- deposit share ---
    ("dep:tl-share-target", r"deposit share target|TL deposit share|Turkish lira deposit share"),
]

_COMPILED = [(name, re.compile(pat, re.I)) for name, pat in RULE_SUBJECTS]

# Human-readable names, used when telling the model which source is newest for a
# rule. Keys must match RULE_SUBJECTS.
SUBJECT_LABELS: dict[str, str] = {
    "loan:non-sme": "loan growth cap — non-SME commercial",
    "loan:sme": "loan growth cap — SME",
    "loan:general": "loan growth cap — general-purpose consumer",
    "loan:vehicle": "loan growth cap — vehicle",
    "loan:overdraft": "loan growth cap — consumer overdraft",
    "loan:fx": "loan growth cap — FX loans",
    "dep:tl-share-target": "TL deposit share target / commission",
}


def sources_per_subject(items: list[dict]) -> dict[str, list[dict]]:
    """Every dated item that substantively states each rule, newest first."""
    found: dict[str, list[dict]] = {}
    for it in items:
        date = it.get("date") or ""
        if not date:
            continue
        body = f"{it.get('title') or ''}\n{it.get('body') or ''}"
        for subject in _subject_values(body):
            found.setdefault(subject, []).append(
                {"date": date, "id": it.get("id", "?")})
    for subject in found:
        found[subject].sort(key=lambda s: s["date"], reverse=True)
    return found


def latest_source_per_subject(items: list[dict]) -> dict[str, dict]:
    """For each rule subject, the NEWEST dated item that substantively states it.

    Precedence only — deliberately NOT the value. Extracting the current value
    from a source body was tried and does not work: the proximity window that
    behaves on a short generated bullet picks up market statistics from an
    8,000-char MPC summary (it returned vehicle-loan "caps" of 39.3/45.9/64.1).
    Which source is newest is robust; what it says is the model's job.

    `items` are the briefing feed dicts: {"id", "date", "title", "body"}.
    """
    latest: dict[str, dict] = {}
    for it in items:
        date = (it.get("date") or "")
        if not date:
            continue
        body = f"{it.get('title') or ''}\n{it.get('body') or ''}"
        for subject in _subject_values(body):
            prev = latest.get(subject)
            if prev is None or date > prev["date"]:
                latest[subject] = {"date": date, "id": it.get("id", "?"),
                                   "title": (it.get("title") or "")[:70]}
    return latest


def supersession_note(items: list[dict]) -> str:
    """A deterministic precedence block for the prompt, or "" if nothing to say.

    Names the sources to IGNORE, not merely the one to prefer. Naming only the
    newest was tried and did not work: the model went on printing the December
    FX ratio table beside the July one, because a complete-looking markdown
    table is more persuasive than a line saying another source is newer. An
    instruction to discard a specific id is something it can act on.
    """
    per_subject = sources_per_subject(items)
    contested = {s: srcs for s, srcs in per_subject.items() if len(srcs) > 1}
    if not contested:
        return ""
    lines = [
        "======= SUPERSESSION (computed from the feed — obey it over your reading) =======",
        "These rules are stated by MORE THAN ONE source in this context. For each, the",
        "CURRENT source is named and the SUPERSEDED ones are listed by id.",
        "",
        "  ⛔ DO NOT take a value for these rules from a superseded id — not even from a",
        "     table that looks complete and authoritative. Those tables are republished",
        "     in full whenever one row changes, so an old one still looks current.",
        "     Read the value ONLY from the current id.",
        "",
    ]
    for subject, srcs in sorted(contested.items(),
                                key=lambda kv: SUBJECT_LABELS.get(kv[0], kv[0])):
        label = SUBJECT_LABELS.get(subject, subject)
        cur = srcs[0]
        old = ", ".join(f"{s['id']} ({s['date']})" for s in srcs[1:5])
        lines.append(f"  {label}")
        lines.append(f"      CURRENT:    {cur['id']} ({cur['date']})")
        lines.append(f"      SUPERSEDED: {old}")
    return "\n".join(lines)

# How near a percentage must be to the subject mention to be read as ITS value.
# A bullet often lists several rules ("3% for general-purpose and vehicle, 1% for
# overdraft"), so the association has to be positional rather than per-bullet.
_NEAR_CHARS = 90

# A subject named only to be EXCLUDED is not the bullet's subject. Without this,
# "commercial loans (excluding overdraft) adjusted to 4.5%" reads as an overdraft
# rule at 4.5% and collides with the real overdraft bullet — a false positive
# that would have withheld a perfectly good 2026-07-12 briefing.
_EXCLUSION_RE = re.compile(
    r"(?:exclud\w*|except\w*|other than|apart from|save for|but not)\b", re.I
)
# Generous, because the excluded list can be long: "other foreign currency
# liabilities (excluding deposits/participation funds and precious metal
# accounts)" puts 45 chars between the "excluding" and "precious metal". A
# 30-char window missed it and the subject read as the bullet's own — a false
# positive that helped freeze a correct section.
_EXCLUSION_LOOKBACK = 140


def _subject_values(text: str) -> dict[str, set[str]]:
    """Map each rule subject mentioned in `text` to the percentages stated near it."""
    pcts = [(m.start(), f"{float(m.group(1)):g}") for m in _PCT_RE.finditer(text)]
    if not pcts:
        return {}
    found: dict[str, set[str]] = {}
    claimed: set[int] = set()
    for name, rx in _COMPILED:
        for m in rx.finditer(text):
            # Do not let a broad subject re-match a span a narrower one took
            # (SME inside non-SME).
            if any(m.start() <= c < m.end() for c in claimed):
                continue
            # Look back only within the current clause: a full stop or semicolon
            # ends the exclusion's reach, so "…excluding X. Y is capped at 3%"
            # still treats Y as a real subject.
            lead = text[max(0, m.start() - _EXCLUSION_LOOKBACK):m.start()]
            lead = re.split(r"[.;]", lead)[-1]
            if _EXCLUSION_RE.search(lead):
                continue  # named only to be excluded — not this bullet's subject
            claimed.update(range(m.start(), m.end()))
            near = {v for pos, v in pcts if abs(pos - m.start()) <= _NEAR_CHARS}
            if near:
                found.setdefault(name, set()).update(near)
    return found


def find_contradictions(bullets: list[str]) -> list[dict]:
    """Rule subjects given more than one value across a section's bullets.

    A single bullet carrying two values for one subject is fine — that is
    transition phrasing ("reduced from 4% to 3%") and self-documenting. The
    defect is two SEPARATE bullets each asserting a different value.
    """
    per_bullet = [(b, _subject_values(b)) for b in bullets]
    by_subject: dict[str, list[tuple[str, set[str]]]] = {}
    for text, subjects in per_bullet:
        for name, vals in subjects.items():
            by_subject.setdefault(name, []).append((text, vals))

    out: list[dict] = []
    for name, entries in by_subject.items():
        if len(entries) < 2:
            continue
        for i, (a_text, a_vals) in enumerate(entries):
            for b_text, b_vals in entries[i + 1:]:
                if a_vals & b_vals:
                    continue  # agree on at least one value → not a conflict
                out.append({
                    "subject": name,
                    "a": a_text, "b": b_text,
                    "a_pcts": sorted(a_vals), "b_pcts": sorted(b_vals),
                })
    return out


def describe(conflicts: list[dict], limit: int = 4) -> str:
    lines = []
    for c in conflicts[:limit]:
        lines.append(
            f"    {c['subject']}: {','.join(c['a_pcts'])}% vs {','.join(c['b_pcts'])}%\n"
            f"      A: {c['a'][:110]}\n"
            f"      B: {c['b'][:110]}"
        )
    if len(conflicts) > limit:
        lines.append(f"    … and {len(conflicts) - limit} more")
    return "\n".join(lines)
