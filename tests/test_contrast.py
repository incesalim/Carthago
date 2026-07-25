"""Text colours must stay legible, in both themes.

Thin pytest wrapper around scripts/check_contrast.py so a retuned token fails CI
as well as a standalone run. Sibling of tests/test_docs_sync.py.

The defect it exists for: `--faint` sat at 2.43:1 on the white sheet while
carrying 8–10px type across 210 call sites, and no test could see it because
contrast is arithmetic nobody re-runs after nudging a hex by eye.
"""

import re
from pathlib import Path

from check_contrast import (
    MIN_RATIO,
    PAIRS,
    check_chart_lockstep,
    contrast_ratio,
    parse_themes,
    text_tokens_in_use,
)

CSS = Path(__file__).resolve().parents[1] / "web" / "app" / "globals.css"


def _themes():
    return parse_themes(CSS.read_text(encoding="utf-8"))


def test_every_text_token_meets_aa_on_every_surface_it_sits_on():
    failures = []
    for theme, tokens in _themes().items():
        for token, surfaces in PAIRS.items():
            for surface in surfaces:
                ratio = contrast_ratio(tokens[token], tokens[surface])
                if ratio < MIN_RATIO:
                    failures.append(
                        f"[{theme}] text-{token} on {surface} = {ratio:.2f}:1"
                    )
    assert not failures, (
        f"text below the {MIN_RATIO}:1 AA floor: " + "; ".join(failures)
    )


def test_every_text_colour_in_the_app_has_a_declared_background():
    """A colour cannot be used as text without someone deciding what it sits on.

    The inventory half — the same reason check_docs_sync fails on an
    undocumented secret. It is how the chart palette leaking into label text
    (text-chart-4 on a chip, 3.27:1) became visible at all.
    """
    themes = _themes()
    undeclared = sorted(
        t for t in text_tokens_in_use() - set(PAIRS) if t in themes["light"]
    )
    assert not undeclared, (
        "text-<token> used in web/app with no PAIRS entry in "
        "scripts/check_contrast.py: " + ", ".join(undeclared)
    )


def test_chart_label_colours_track_the_text_tokens():
    """chart-theme.ts cannot read CSS variables, so its TEXT colours are copies.

    `axis` is the tick-label colour: text, rendered as an SVG fill. When --faint
    moved and the copy did not, chart labels kept the old 2.43:1.
    """
    problems = check_chart_lockstep(_themes())
    assert not problems, "; ".join(problems)


def test_the_quiet_ramp_stays_a_ramp():
    """Legibility must not flatten the hierarchy into one grey.

    Raising `faint` to AA squeezed it against `muted-foreground` (5.02:1), so
    `muted-foreground` moved too. Three tiers, each visibly quieter than the
    last, is the design contract The Desk is built on — assert the ORDER, so a
    future retune cannot quietly collapse two of them together.
    """
    for theme, tokens in _themes().items():
        sheet = tokens["card"]
        ink = contrast_ratio(tokens["foreground"], sheet)
        secondary = contrast_ratio(tokens["muted-foreground"], sheet)
        quiet = contrast_ratio(tokens["faint"], sheet)
        assert ink > secondary > quiet, (
            f"[{theme}] the three text tiers are out of order: "
            f"ink {ink:.2f} / secondary {secondary:.2f} / quiet {quiet:.2f}"
        )
        # …and far enough apart to read as different tiers, not as a rounding.
        assert secondary / quiet >= 1.25, (
            f"[{theme}] muted-foreground ({secondary:.2f}) and faint ({quiet:.2f}) "
            "have collapsed into the same tier"
        )


def test_there_is_something_to_check():
    """Guard against a passing run that checked nothing (glob/regex drift)."""
    themes = _themes()
    assert len(themes["light"]) > 20, "light tokens not parsed"
    assert len(themes["dark"]) > 20, "dark tokens not parsed"
    assert text_tokens_in_use(), "no text-* classes discovered — check the regex"


def test_the_css_has_no_stray_control_characters():
    """Same class of bug as tests/test_docs_sync.py::test_no_control_chars_in_source.

    A patch script wrote a literal 0x08 into this gate's own regex while it was
    being built, and the check silently matched nothing.
    """
    raw = CSS.read_bytes()
    assert not re.search(rb"[\x00\x08\x0b\x0c]", raw), "control characters in globals.css"
