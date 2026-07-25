#!/usr/bin/env python3
"""Guard: every colour used as TEXT stays legible, in both themes.

Sibling of `check_prose_claims.py`, applying the same idea to colour: a claim
must be computed, and a text colour must be readable. The 2026-07-12 site
evaluation scored accessibility 6.5/10 and named the cause — `text-faint` at
**2.43:1** on the white sheet, used for 8–10px type across 210 call sites. WCAG
AA asks 4.5:1 for normal text; 2.43 is roughly "visible if you already know what
it says".

Why a gate and not just a fix: the value that regressed was a design token, and
tokens get retuned by eye. A ratio nobody recomputes drifts back. This makes the
floor executable — stdlib only (the CI python job installs no colour library),
no network, ~10ms.

WHAT IT CHECKS

  1. Every `text-<token>` class actually used in `web/app` appears in PAIRS
     below, so a new text colour cannot enter the codebase without someone
     deciding which surfaces it sits on. (The inventory half — same reason
     check_docs_sync fails on an undocumented secret.)
  2. For each (token, surface) pair, in BOTH themes, contrast >= 4.5:1.

WHAT IT DELIBERATELY DOES NOT CHECK

  Chart colours (`--chart-*`, `--data`, `--context` as a mark, heat scales).
  Those are marks, not text, and they answer to a different rule (WCAG 1.4.11,
  3:1, and only for meaningful graphics). `chart-theme.ts` owns them. If a chart
  colour is ever used AS text, rule 1 above will notice.

Run standalone (`python scripts/check_contrast.py`) or via pytest
(`tests/test_contrast.py`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CSS = REPO_ROOT / "web" / "app" / "globals.css"
APP_DIR = REPO_ROOT / "web" / "app"

# WCAG 2.1 AA, normal text. The faint tier is 8–10px here, so the large-text
# allowance (3:1) never applies to it.
MIN_RATIO = 4.5

# Which surfaces each text token is allowed to sit on. A token is checked
# against EVERY surface listed for it, so the weakest pairing is the one that
# has to pass.
#
# `muted` is included wherever body text can land on a subtotal row — it is the
# darkest surface in the light theme, and the pairing that fails first.
PAIRS: dict[str, tuple[str, ...]] = {
    "foreground": ("card", "background", "muted"),
    "muted-foreground": ("card", "background", "muted"),
    "faint": ("card", "background", "muted"),
    "primary": ("card", "background", "muted"),
    "positive": ("card", "background", "muted"),
    "negative": ("card", "background", "muted"),
    "warning": ("card", "background", "muted"),
    "info": ("card", "background", "muted"),
    "data": ("card", "background", "muted"),
    "card-foreground": ("card",),
    "popover-foreground": ("popover",),
    "accent-foreground": ("accent",),
    "secondary-foreground": ("secondary",),
    # Inverted chips: the text sits ON a solid fill, not on a sheet.
    "primary-foreground": ("primary",),
    "background": ("foreground",),
}

# Tailwind text utilities that are not colour tokens (size, weight, alignment,
# decoration, transform). `text-[10px]` and `text-[#abc]` are arbitrary values.
_NOT_A_COLOUR = re.compile(
    r"^(?:xs|sm|base|lg|xl|\d?xl|left|right|center|justify|start|end|top|bottom|middle|"
    r"wrap|nowrap|balance|pretty|ellipsis|clip|opacity|shadow|"
    r"transparent|current|inherit|white|black)$"
)


def _srgb_to_linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


_TOKEN = re.compile(r"^\s*--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8}|var\(--[a-z0-9-]+\))\s*;", re.MULTILINE)
_VAR = re.compile(r"^var\(--([a-z0-9-]+)\)$")


def _resolve(tokens: dict[str, str]) -> dict[str, str]:
    """Follow `--a: var(--b)` aliases to the hex they end at (e.g. card-foreground)."""
    out: dict[str, str] = {}
    for name in tokens:
        seen, value = set(), tokens[name]
        while (m := _VAR.match(value)) and m.group(1) not in seen:
            seen.add(m.group(1))
            value = tokens.get(m.group(1), value)
            if value == m.group(0):
                break
        if value.startswith("#"):
            out[name] = value
    return out


def parse_themes(css: str) -> dict[str, dict[str, str]]:
    """{'light': {token: hex}, 'dark': {...}} from :root and .dark blocks."""

    def block(start_pat: str) -> str:
        m = re.search(start_pat, css)
        if not m:
            raise SystemExit(f"check_contrast: no {start_pat!r} block in globals.css")
        depth, i = 0, m.end() - 1
        for j in range(i, len(css)):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    return css[i : j + 1]
        raise SystemExit("check_contrast: unbalanced braces in globals.css")

    light_raw = dict(_TOKEN.findall(block(r":root\s*\{")))
    dark_raw = dict(_TOKEN.findall(block(r"\.dark\s*\{")))
    # The dark block overrides a subset; anything it omits keeps the light value.
    return {"light": _resolve(light_raw), "dark": _resolve({**light_raw, **dark_raw})}


def text_tokens_in_use() -> set[str]:
    """Every `text-<token>` class written in web/app, minus non-colour utilities."""
    found: set[str] = set()
    for path in APP_DIR.rglob("*.ts*"):
        for m in re.finditer(r"\btext-([a-z][a-z0-9-]*)\b", path.read_text(encoding="utf-8")):
            name = m.group(1)
            if not _NOT_A_COLOUR.match(name):
                found.add(name)
    return found


# chart-theme.ts holds its own hexes (Recharts bakes colours into SVG attributes,
# so it cannot read CSS variables). Two of them render TEXT — `axis` is the tick
# LABEL colour and `inkMuted` labels series — so they must equal the text tokens,
# not merely look similar. The rest of that file is marks, which answer to 3:1.
CHART_TEXT_LOCKSTEP = {
    "LIGHT": {"axis": "faint", "inkMuted": "muted-foreground"},
    "DARK": {"axis": "faint", "inkMuted": "muted-foreground"},
}
CHART_THEME = REPO_ROOT / "web" / "app" / "lib" / "chart-theme.ts"


def check_chart_lockstep(themes: dict[str, dict[str, str]]) -> list[str]:
    src = CHART_THEME.read_text(encoding="utf-8")
    out: list[str] = []
    for block_name, fields in CHART_TEXT_LOCKSTEP.items():
        m = re.search(rf"export const {block_name}: ChartTheme = \{{(.*?)^\}};", src, re.S | re.M)
        if not m:
            out.append(f"chart-theme.ts: no `export const {block_name}` block")
            continue
        body = m.group(1)
        theme = themes["light" if block_name == "LIGHT" else "dark"]
        for field, token in fields.items():
            fm = re.search(rf'\b{field}:\s*"(#[0-9A-Fa-f]{{6}})"', body)
            if not fm:
                out.append(f"chart-theme.ts {block_name}.{field} is missing")
                continue
            if fm.group(1).upper() != theme[token].upper():
                out.append(
                    f"chart-theme.ts {block_name}.{field} = {fm.group(1)} but --{token} = "
                    f"{theme[token]} — these render text and must stay in lockstep"
                )
    return out


def main() -> int:
    css = CSS.read_text(encoding="utf-8")
    themes = parse_themes(css)
    problems: list[str] = []
    problems += check_chart_lockstep(themes)

    # 1 — inventory: no text colour without a declared background.
    used = text_tokens_in_use()
    known = set(PAIRS)
    for token in sorted(used - known):
        if token in themes["light"]:
            problems.append(
                f"text-{token} is used in web/app but has no entry in PAIRS — "
                f"add it to scripts/check_contrast.py with the surfaces it sits on"
            )
    # An entry for a token nobody uses is dead weight; say so rather than rot.
    for token in sorted(known - used):
        problems.append(f"PAIRS lists '{token}' but no text-{token} appears in web/app")

    # 2 — the ratios themselves.
    checked = 0
    for theme, tokens in themes.items():
        for token, surfaces in PAIRS.items():
            fg = tokens.get(token)
            if fg is None:
                problems.append(f"[{theme}] --{token} is not defined")
                continue
            for surface in surfaces:
                bg = tokens.get(surface)
                if bg is None:
                    problems.append(f"[{theme}] --{surface} is not defined")
                    continue
                ratio = contrast_ratio(fg, bg)
                checked += 1
                if ratio < MIN_RATIO:
                    problems.append(
                        f"[{theme}] text-{token} ({fg}) on {surface} ({bg}) = "
                        f"{ratio:.2f}:1 — below the {MIN_RATIO}:1 AA floor for normal text"
                    )

    if problems:
        print("contrast check FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"contrast OK ({checked} token/surface pairs across 2 themes, >= {MIN_RATIO}:1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
