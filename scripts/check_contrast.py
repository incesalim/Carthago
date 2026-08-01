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
  3. No arbitrary hex is used AS text — `text-[#b07a18]` and friends.
  4. Text on a TINTED surface (`text-negative` over `bg-negative/12`) is checked
     against the actual composite, not against the untinted sheet.

  Rules 3 and 4 were added 2026-08-01 after a review found two holes that let
  live pages fail AA while this gate reported green:

  - Rule 1's regex is `\\btext-([a-z][a-z0-9-]*)\\b`, which requires a lowercase
    letter after the dash — so `text-[#b07a18]` is STRUCTURALLY invisible to it.
    That hex shipped as body and label text at 11 call sites on /products at
    3.72:1, and at 3.34:1 on its own /10 tint.
  - PAIRS only lists solid surfaces, so a chip putting `text-negative` on
    `bg-negative/12` was never evaluated against its own tint (4.34:1), nor
    `text-warning` on `bg-warning/15` (4.24:1).

  Note what this means about the paragraph below: it used to claim "if a chart
  colour is ever used AS text, rule 1 above will notice." Rule 1 IS the blind
  regex. The stated safety net did not exist; rule 3 is what makes it true.

WHAT IT DELIBERATELY DOES NOT CHECK

  Chart colours (`--chart-*`, `--data`, `--context` as a mark, heat scales).
  Those are marks, not text, and they answer to a different rule (WCAG 1.4.11,
  3:1, and only for meaningful graphics). `chart-theme.ts` owns them. If a chart
  colour is ever used AS text, rules 1 and 3 will notice.

  Font SIZE has no floor here. There are 175 sub-10px call sites; they pass on
  ratio and are a legibility question, not a WCAG one (no size minimum exists).

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


# Rule 3. `text-[#abc123]`, `dark:text-[#abc123]`, `hover:text-[#abc]` — any
# arbitrary hex in a text utility. These bypass the token system entirely: they
# cannot be retuned with the theme, cannot be checked by rule 1, and cannot
# follow a surface. The fix is always "use a token", never "pick a darker hex".
_ARBITRARY_TEXT_HEX = re.compile(r"\btext-\[(#[0-9A-Fa-f]{3,8})\]")

# Rule 4. A tinted surface: `bg-negative/12` is the token at 12% over whatever
# is behind it. Tailwind writes the alpha as a percentage.
_BG_TINT = re.compile(r"\bbg-([a-z][a-z0-9-]*)/(\d{1,3})\b")
_TEXT_CLASS = re.compile(r"\btext-([a-z][a-z0-9-]*)\b")

# Class lists live inside quoted strings; scanning per-string rather than
# per-line keeps a `text-` on one element from being paired with a `bg-` on the
# next one along.
_QUOTED = re.compile(r'"([^"\n]*)"|`([^`]*)`|\'([^\'\n]*)\'')

# The surfaces a tinted chip can sit on. `muted` is excluded: a tint over a
# subtotal row is rare and assuming it would produce false failures.
_TINT_BASES = ("card", "background")


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    s = h.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def composite(top: str, bottom: str, alpha: float) -> str:
    """`top` at `alpha` (0–1) painted over opaque `bottom` — plain source-over."""
    tr, tg, tb = _hex_to_rgb(top)
    br, bg_, bb = _hex_to_rgb(bottom)
    mix = lambda t, b: round(alpha * t + (1 - alpha) * b)  # noqa: E731
    return f"#{mix(tr, br):02x}{mix(tg, bg_):02x}{mix(tb, bb):02x}"


def check_arbitrary_text_hex() -> list[str]:
    out: list[str] = []
    for path in sorted(APP_DIR.rglob("*.ts*")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in _ARBITRARY_TEXT_HEX.finditer(line):
                out.append(
                    f"{rel}:{lineno}: text-[{m.group(1)}] — an arbitrary hex used as text. "
                    f"Use a token from globals.css so it is themed and checkable "
                    f"(rule 1 cannot see bracketed values)"
                )
    return out


def check_tinted_surfaces(themes: dict[str, dict[str, str]]) -> list[str]:
    """Text sitting on `bg-<token>/NN` must clear AA against the COMPOSITE."""
    seen: set[tuple[str, str, int]] = set()
    out: list[str] = []
    for path in sorted(APP_DIR.rglob("*.ts*")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for qm in _QUOTED.finditer(line):
                chunk = next((g for g in qm.groups() if g is not None), "")
                tints = _BG_TINT.findall(chunk)
                if not tints:
                    continue
                texts = [t for t in _TEXT_CLASS.findall(chunk) if not _NOT_A_COLOUR.match(t)]
                for tint_token, pct in tints:
                    for text_token in texts:
                        key = (text_token, tint_token, int(pct))
                        for theme, tokens in themes.items():
                            fg, tint = tokens.get(text_token), tokens.get(tint_token)
                            if fg is None or tint is None:
                                continue
                            for base in _TINT_BASES:
                                bg = tokens.get(base)
                                if bg is None:
                                    continue
                                surface = composite(tint, bg, int(pct) / 100)
                                ratio = contrast_ratio(fg, surface)
                                if ratio < MIN_RATIO and (key + (theme,)) not in seen:  # type: ignore[operator]
                                    seen.add(key + (theme,))  # type: ignore[arg-type]
                                    out.append(
                                        f"{rel}:{lineno}: [{theme}] text-{text_token} ({fg}) on "
                                        f"bg-{tint_token}/{pct} over {base} = {surface} -> "
                                        f"{ratio:.2f}:1, below the {MIN_RATIO}:1 AA floor"
                                    )
    return out


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

    # 3 — no arbitrary hex as text, and 4 — text on tinted surfaces.
    problems += check_arbitrary_text_hex()
    tinted = check_tinted_surfaces(themes)
    problems += tinted

    if problems:
        print("contrast check FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(
        f"contrast OK ({checked} token/surface pairs across 2 themes, >= {MIN_RATIO}:1; "
        f"no arbitrary text hexes; tinted surfaces composited)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
