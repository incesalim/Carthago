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
    # --- reserve requirements ---
    ("rr:fx-short",         r"demand deposits|maturities up to 1 month|up to one month"),
    ("rr:fx-long",          r"longer maturit"),
    ("rr:precious-metal",   r"precious metal"),
    ("rr:banks-abroad",     r"banks abroad|head office abroad"),
    ("rr:repo-abroad",      r"repo transactions abroad"),
    ("rr:additional-tl",    r"additional Turkish lira"),
    # --- deposit share ---
    ("dep:tl-share-target", r"deposit share target|TL deposit share|Turkish lira deposit share"),
]

_COMPILED = [(name, re.compile(pat, re.I)) for name, pat in RULE_SUBJECTS]

# How near a percentage must be to the subject mention to be read as ITS value.
# A bullet often lists several rules ("3% for general-purpose and vehicle, 1% for
# overdraft"), so the association has to be positional rather than per-bullet.
_NEAR_CHARS = 90

# A subject named only to be EXCLUDED is not the bullet's subject. Without this,
# "commercial loans (excluding overdraft) adjusted to 4.5%" reads as an overdraft
# rule at 4.5% and collides with the real overdraft bullet — a false positive
# that would have withheld a perfectly good 2026-07-12 briefing.
_EXCLUSION_RE = re.compile(
    r"(?:exclud\w*|except\w*|other than|apart from|save for|but not)\s*$", re.I
)
_EXCLUSION_LOOKBACK = 30


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
            lead = text[max(0, m.start() - _EXCLUSION_LOOKBACK):m.start()]
            if _EXCLUSION_RE.search(lead.rstrip(" ([,")):
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
