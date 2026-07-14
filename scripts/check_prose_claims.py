#!/usr/bin/env python3
"""Guard: a sentence that asserts a fact about the data must be computed from it.

Sibling of `check_docs_sync.py` and `check_pipeline_graph_sync.py`, applying the
same idea to the site's prose. Those guard inventories; this guards claims.

A 2026-07 audit found 41 hand-typed sentences on the dashboard asserting a
direction, a level or a ranking with nothing checking them. They do not merely go
stale — several assert the OPPOSITE of the chart directly beneath them the moment
the data turns:

  * "Every ownership group fell together"  — off a step detector that picks by |Δ|
  * "Real appreciation of −4.3"            — the noun typed, the sign computed
  * "+₺-42bn"                              — a hardcoded + in front of a signed value
  * "32 banks' audited BRSA financials"    — the universe has been 38 since TAKAS

The fix is `web/app/lib/prose.ts` (`direction()` / `claim()` / `signed()`), which
fails closed: a claim the data won't support returns null and the caller prints
the topic instead. This script stops the pattern coming back.

Three rules, all narrow enough to leave the ~300 legitimately static strings
(axis descriptions, methodology, definitions) alone:

  R1  a hardcoded `+` in front of a formatter — `+{fmtBn(x)}`. The sign belongs to
      the value, not the template. Use `signed()`.
  R2  a `title=` string literal (NO `${…}`) whose text asserts a direction, a level
      or a ranking. If the operands are on the page, compute it; the chart's own
      `data` prop is usually enough. Use `claim()` / `firstClaim()` / `seriesFinding()`.
  R3  a hardcoded bank-universe count (`32 banks`) in RENDERED text. The universe
      grows; derive it from BANK_NAMES / bankSummaries().

Deliberately NOT checked: whether a computed sentence is *well-written*; whether a
static description is *accurate* (unlintable — that is what the regime-flip suite
in web/app/lib/prose-regression.test.ts is for); and counts inside code comments,
which mislead the next reader but tell the user nothing. A title of three words or
fewer is a topic label, not a claim ("Largest funds" names a table; "The margin
rebuilt as deposits repriced down" asserts one). This guards the shape, not the
sentiment.

Escape hatch: `// prose-ok: <reason>` (or `{/* prose-ok: <reason> */}`) on the
offending line or the one above it. Every active suppression is printed on every
run, so they cannot accumulate quietly.

Run standalone (`python scripts/check_prose_claims.py`), `--warn` to report
without failing, or via pytest (tests/test_prose_claims.py). Stdlib only: the CI
python job installs ruff/pytest/lxml/requests and nothing else.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "web" / "app"

# Route folders that render no prose to a reader.
_SKIP_DIRS = ("api", "admin", "_franchise")
_SKIP_SUFFIXES = (".test.ts", ".test.tsx")
# lib/prose.ts documents the bug shapes it exists to fix, so it trips its own rules.
_SKIP_FILES = ("lib/prose.ts",)

# ── R1 ── `+{fmtBn(x)}` / `+{rollNow.net}` — a sign typed in front of a value.
# Only in a JSX expression slot, so `a + {…}` in plain TS can't trip it.
_R1 = re.compile(r">\s*\+\{|\+\{(?=[\w$][\w$.]*\s*[({])|(?<![\w$)])\+\{[\w$][\w$.]*\}")

# ── R2 ── a title= literal, no interpolation, asserting something about the data.
_TITLE_LITERAL = re.compile(r'title=(?:"([^"]{12,})"|\{\s*"([^"]{12,})"\s*\}|\{`([^`${]{12,})`\})')

# The closed vocabulary of assertion. Narrow on purpose: these words state a
# direction, a ranking or a universal — none of them belongs in an axis label.
_ASSERTS = re.compile(
    r"\b("
    # direction
    r"ris(?:e|es|ing|en)|fall(?:s|ing)?|fell|climb(?:s|ed|ing)?|rose|grew|grow(?:s|ing)|"
    r"shr(?:ank|inking|unk)|compress(?:ed|ing)|rebuil[td]|widen(?:ed|ing)|narrow(?:ed|ing)|"
    r"slid(?:ing)?|eas(?:ed|ing)|edged|jumped|dropped|stopped|reversed|deepen(?:ed|ing)|"
    r"accelerat\w+|cool(?:ed|ing)|keeps?|"
    # ranking / superlative
    r"hardest|biggest|largest|smallest|strongest|weakest|lead(?:s|ing)?|dominat\w+|"
    r"outpaces?|drove|lagged|"
    # universal / level
    r"every|all|none|exceeds?|breach(?:es|ed)?|barely|nearly|"
    r"more than|less than|far below|far above|below the|above the"
    r")\b",
    re.IGNORECASE,
)

# A claim is a sentence; a topic is a label. Under four words it names a chart.
_MIN_CLAIM_WORDS = 4

# ── R3 ── a hardcoded universe count, in text a reader actually sees.
_R3 = re.compile(r"\b(\d{2})\s+banks\b", re.IGNORECASE)
# The two places allowed to state it, because they derive it.
_R3_ALLOW = ("lib/bank_names.ts", "banks/page.tsx")
# A count in a comment is stale documentation, not a lie to the user.
_COMMENT = re.compile(r"^\s*(//|/\*|\*)")

_SUPPRESS = re.compile(r"prose-ok:\s*(.+?)\s*(?:\*/\}?)?$")

RULES = {
    "R1": "hardcoded sign before a formatter — the sign belongs to the value: use signed() from lib/prose",
    "R2": "a title that asserts a direction, a level or a ranking must be computed: use claim()/firstClaim()/seriesFinding()",
    "R3": "hardcoded bank-universe count — derive it from BANK_NAMES / bankSummaries()",
}


@dataclass(frozen=True)
class Hit:
    rule: str
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class Suppression:
    path: str
    line: int
    reason: str


def _files() -> list[Path]:
    out: list[Path] = []
    for p in sorted(APP_DIR.rglob("*")):
        if p.suffix not in (".ts", ".tsx") or not p.is_file():
            continue
        if p.name.endswith(_SKIP_SUFFIXES):
            continue
        rel = p.relative_to(APP_DIR)
        if rel.parts and rel.parts[0] in _SKIP_DIRS:
            continue
        if rel.as_posix().endswith(_SKIP_FILES):
            continue
        out.append(p)
    return out


def _rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def scan_text(rel: str, text: str) -> tuple[list[Hit], list[Suppression]]:
    """The rules, applied to one file's text. Pure — the unit under test."""
    hits: list[Hit] = []
    sups: list[Suppression] = []
    lines = text.splitlines()

    # A suppression covers its own line and the line below it, so it can sit
    # above a multi-line JSX prop.
    covered: dict[int, str] = {}
    for i, line in enumerate(lines, start=1):
        m = _SUPPRESS.search(line)
        if m:
            sups.append(Suppression(rel, i, m.group(1)))
            covered[i] = m.group(1)
            covered[i + 1] = m.group(1)

    for i, line in enumerate(lines, start=1):
        if i in covered:
            continue
        found: list[str] = []

        if _R1.search(line):
            found.append("R1")

        m = _TITLE_LITERAL.search(line)
        if m:
            title = next(g for g in m.groups() if g is not None)
            if len(title.split()) >= _MIN_CLAIM_WORDS and _ASSERTS.search(title):
                found.append("R2")

        if _R3.search(line) and not rel.endswith(_R3_ALLOW) and not _COMMENT.match(line):
            found.append("R3")

        for rule in found:
            hits.append(Hit(rule, rel, i, line.strip()[:120]))

    return hits, sups


def scan() -> tuple[list[Hit], list[Suppression]]:
    hits: list[Hit] = []
    sups: list[Suppression] = []
    for path in _files():
        h, s = scan_text(_rel(path), path.read_text(encoding="utf-8"))
        hits.extend(h)
        sups.extend(s)
    return hits, sups


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--warn", action="store_true", help="report without failing")
    args = ap.parse_args()

    # The offending lines are full of ₺ and −; a cp1252 console must not be the
    # thing that fails this check.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    hits, sups = scan()

    if sups:
        print(f"prose-ok suppressions in force ({len(sups)}):")
        for s in sups:
            print(f"  {s.path}:{s.line} — {s.reason}")
        print()

    if not hits:
        print(f"prose claims: clean ({len(_files())} files scanned).")
        return 0

    by_rule: dict[str, list[Hit]] = {}
    for h in hits:
        by_rule.setdefault(h.rule, []).append(h)

    stream = sys.stdout if args.warn else sys.stderr
    for rule in sorted(by_rule):
        print(f"\n{rule} — {RULES[rule]}", file=stream)
        for h in by_rule[rule]:
            print(f"  {h.path}:{h.line}", file=stream)
            print(f"      {h.text}", file=stream)

    total = len(hits)
    summary = f"\n{total} unguarded claim{'s' if total != 1 else ''} across {len(by_rule)} rule(s)."
    if args.warn:
        print(summary + " (--warn: not failing)", file=stream)
        return 0
    print(summary + " Compute it, or add `prose-ok: <reason>`.", file=stream)
    return 1


if __name__ == "__main__":
    sys.exit(main())
