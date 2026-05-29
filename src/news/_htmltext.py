"""Shared HTML → plain-text body extraction for the TCMB / BDDK scrapers.

Both regulators render their announcement bodies as a mix of <p> prose and
<table> blocks (e.g. TCMB macroprudential releases carry the actual
caps/ratios in a "Former / New" table). The original extractor pulled only
<p> text, silently dropping every table — so the substance of those
releases never reached the DB.

`extract_body` walks <p> and <table> blocks in document order, converting
each table to a GitHub-style Markdown pipe table so it round-trips as plain
text through SQLite/D1 and can be rendered as a real <table> in the web UI.
"""
from __future__ import annotations

import html as html_lib
import re

# A top-level <p>, <table> or <ul>/<ol> block. finditer is non-overlapping,
# so a matched container consumes any nested block (we don't want it twice).
_BLOCK_RE = re.compile(r"<(p|table|ul|ol)\b[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
# <script>/<style> bodies contain JS/CSS that mentions <li>, <ul>, etc. (BDDK
# pages build dropdowns in inline JS). Strip them before block extraction so
# that code never leaks into a body.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<(t[hd])\b[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.DOTALL | re.IGNORECASE)


_MOJIBAKE_MAP = {
    "Ã¼": "ü", "Ãœ": "Ü", "Ã§": "ç", "Ã‡": "Ç", "Ã¶": "ö", "Ã–": "Ö",
    "ÄŸ": "ğ", "Äž": "Ğ", "Ä±": "ı", "Ä°": "İ", "ÅŸ": "ş", "Åž": "Ş",
    "Ã¢": "â", "Ã‚": "Â", "Â±": "±", "â‚º": "₺", "â€™": "’", "â€œ": "“",
    "â€\x9d": "”", "â€“": "–", "â€”": "—", "Â ": " ",
}


def fix_mojibake(s: str) -> str:
    """Repair UTF-8-as-Latin-1 mojibake (e.g. 'TÃ¼rkiye' -> 'Türkiye').

    Applied iteratively (to clear double-encoding) until stable. Only triggers
    on the telltale sequences, so clean text passes through untouched. Used by
    the briefing summarizer and as a final gate in push_to_d1."""
    if not s:
        return s
    for _ in range(3):
        if not any(m in s for m in ("Ã", "Å", "Ä", "Â", "â€")):
            break
        prev = s
        for bad, good in _MOJIBAKE_MAP.items():
            s = s.replace(bad, good)
        if s == prev:
            break
    return s


def _clean_inline(fragment: str) -> str:
    """Strip inline tags, unescape entities, collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _table_to_markdown(table_html: str) -> str:
    """Convert one <table> to a Markdown pipe table. Returns "" if empty.

    The first row is treated as the header (TCMB/BDDK tables lead with a
    header row whether it uses <th> or <td>). Ragged rows are padded so the
    pipe count stays consistent.
    """
    grid: list[list[str]] = []
    for row_html in _ROW_RE.findall(table_html):
        cells = [_clean_inline(c) for _tag, c in _CELL_RE.findall(row_html)]
        if any(cells):
            grid.append(cells)
    if not grid:
        return ""
    ncol = max(len(r) for r in grid)
    grid = [r + [""] * (ncol - len(r)) for r in grid]
    # Escape pipes inside cells so they don't break the table.
    grid = [[c.replace("|", "\\|") for c in r] for r in grid]
    lines = ["| " + " | ".join(grid[0]) + " |",
             "| " + " | ".join(["---"] * ncol) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in grid[1:]]
    return "\n".join(lines)


def _list_to_markdown(list_html: str) -> str:
    """Convert one <ul>/<ol> to Markdown "- " bullets. Returns "" if empty.

    Some macroprudential releases put their rate changes in a bullet list
    rather than a table, so dropping lists would lose the numbers too.
    """
    items = [_clean_inline(li) for li in _LI_RE.findall(list_html)]
    items = [i for i in items if i]
    return "\n".join(f"- {i}" for i in items)


def extract_body(
    html_text: str,
    footer_markers: tuple[str, ...],
    max_chars: int,
    min_para_len: int = 30,
    include_lists: bool = False,
) -> str | None:
    """Extract a press-release / announcement body from a detail page.

    Collects <p> prose (>= `min_para_len` chars) and <table> blocks in
    document order, stopping at the first <p> that hits a footer/boilerplate
    marker. Tables are emitted as Markdown. Returns None if nothing usable.
    """
    html_text = _SCRIPT_STYLE_RE.sub(" ", html_text)
    blocks: list[str] = []
    for m in _BLOCK_RE.finditer(html_text):
        tag = m.group(1).lower()
        if tag == "p":
            text = _clean_inline(m.group(2))
            if len(text) < min_para_len:
                continue
            if any(marker in text for marker in footer_markers):
                break
            blocks.append(text)
        elif tag == "table":
            # Footer/boilerplate is often a contact-info <table> (phone,
            # address). Apply the same marker check to table text so we stop
            # at it instead of emitting it as a junk "data" table.
            if any(marker in _clean_inline(m.group(2)) for marker in footer_markers):
                break
            md = _table_to_markdown(m.group(2))
            if md:
                blocks.append(md)
        else:  # ul / ol
            # Off by default: some sites (BDDK) server-render their nav menu
            # as a long <ul>, which would pollute every body. Only enabled
            # for sources whose content uses lists (TCMB rate-change bullets).
            if not include_lists:
                continue
            inner = _clean_inline(m.group(2))
            if any(marker in inner for marker in footer_markers):
                break
            if len(inner) < min_para_len:
                continue
            md = _list_to_markdown(m.group(2))
            if md:
                blocks.append(md)
    body = "\n\n".join(blocks).strip()
    if not body:
        return None
    return body[:max_chars]
