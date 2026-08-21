"""Graduating a BRSA NUMBERED template from the document layer.

The LCR (rows 1-23), NSFR (1-34) and leverage (1-15) disclosures share one
structural gift: the regulator numbers the template's rows, and the capture
keeps that number as each row's first cell (or as the label's prefix). So
`template_row` is the cross-bank, cross-language join key, and the builders
for these lanes share everything except the template's own facts — its
signature rows, its row roles, its value-column names and which row is the
percent. This module is that shared everything; `scripts/build_lcr_full.py`,
`build_nsfr_full.py` and `build_leverage_full.py` are thin over it.

What a numbered template's assembly has in common:

  detect      a block is THE template when its numbered rows carry at least
              two of the template's signature rows — checked against the row's
              own printed number, so the LCR's row 23 and the NSFR's row 23
              can never be mistaken for each other, and a stray cross-
              reference quoting one row is not a table.
  columns     the grid's cells are already column-aligned by the document
              layer; what varies per filer is a leading row-number column and
              phantom all-None columns (GARAN a 7th, ALBRK up to 8). Decided
              per BLOCK by majority vote and liveness — never per row, which
              is what let a row with a missing number cell shift its values
              into the wrong slots — the value columns are the last `n_values`
              live columns after the row-number column.
  wraps       a filer whose row-1 label wraps prints the VALUES on an
              unnumbered line above and the number on the continuation below
              (GARAN's leverage table). A numbered row with no values adopts
              the immediately preceding unnumbered row's values.
  instances   the filing prints the current period and the prior YEAR-END as
              full tables; a row number <= the running maximum starts the next
              instance. First = current, second = prior, the printed order.
  percent     the ratio row is never unit-scaled, and a bare INTEGER >= 10000
              there is a three-decimal misparse repaired (ALBRK prints
              "186,610" meaning 186.610%); a genuinely enormous ratio carries
              its decimals and is left alone (ENPARA's LCR of 34,221.52%).
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Callable

from . import units as U

_TR_FOLD = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")
_ROW_IN_LABEL = re.compile(r"^(\d{1,2})\s+\S")
_LABEL_PREFIX = re.compile(r"^\d{1,2}\s+")


def fold(s: str | None) -> str:
    """Uppercase that survives the Turkish dotted/dotless i."""
    return (s or "").translate(_TR_FOLD).upper()


def rowno(r: dict, max_row: int) -> int | None:
    """The template row number: the row's first cell, or the label's prefix."""
    cells = r["cells"]
    if cells and isinstance(cells[0], (int, float)) and 1 <= cells[0] <= max_row \
            and float(cells[0]).is_integer():
        return int(cells[0])
    m = _ROW_IN_LABEL.match(r["label"] or "")
    if m and 1 <= int(m.group(1)) <= max_row:
        return int(m.group(1))
    return None


def num(cell) -> float | None:
    return float(cell) if isinstance(cell, (int, float)) else None


def prior_year_end(period: str) -> str:
    """The template's "Onceki Donem" re-prints December (the fx lane's
    documented BRSA convention): Q2/Q3/Q4 all anchor (year-1)Q4."""
    return f"{int(period[:4]) - 1}Q4"


def repair_percent(vals: list[float | None],
                   floor: float = 10000) -> list[float | None]:
    """A bare integer at or above `floor` on a percent row is a three-decimal
    misparse ("9,127" printed for 9.127%). The floor is the template's: no LCR
    or NSFR reaches 10,000% honestly but ENPARA's 34,221.52% (with decimals)
    does; no leverage ratio reaches 1,000%, so its floor sits there."""
    return [v / 1000 if v is not None and v >= floor and float(v).is_integer()
            else v for v in vals]


def block_columns(grid: list[dict], max_row: int, n_values: int) -> list[int]:
    """The value-column indices of one block: the last `n_values` LIVE columns
    after the row-number column (phantom all-None columns drop out)."""
    ncols = max((len(r["cells"]) for r in grid), default=0)
    if not ncols:
        return []
    numbered = [r for r in grid if rowno(r, max_row) is not None]
    with_rowno = sum(1 for r in numbered if r["cells"]
                     and isinstance(r["cells"][0], (int, float))
                     and r["cells"][0] == rowno(r, max_row))
    start = 1 if numbered and with_rowno * 2 >= len(numbered) else 0
    live = [c for c in range(start, ncols)
            if any(len(r["cells"]) > c and r["cells"][c] is not None
                   for r in grid)]
    return live[-n_values:]


def partition_blocks(tab: sqlite3.Connection, key: tuple) -> list[tuple]:
    return [(pg, bid, json.loads(g), unit) for pg, bid, g, unit in tab.execute(
        "SELECT page, block_id, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key)]


def detect(blocks: list[tuple], sig: dict[int, re.Pattern], max_row: int,
           min_sig: int = 2) -> list[tuple]:
    hits = []
    for pg, bid, grid, unit in blocks:
        # signatures see the label WITHOUT its number prefix ("1 KREDI RISKI"
        # -> "KREDI RISKI"), so a template may anchor its patterns at ^.
        s = sum(1 for r in grid
                if (n := rowno(r, max_row)) in sig
                and sig[n].search(fold(_LABEL_PREFIX.sub("", (r["label"] or "").strip()))))
        if s:
            hits.append((pg, bid, grid, unit, s))
    return hits if sum(h[4] for h in hits) >= min_sig else []


def assemble(tab: sqlite3.Connection, key: tuple, *, sig: dict[int, re.Pattern],
             max_row: int, bottom_row: int, n_values: int, percent_rows: set[int],
             role_of: Callable[[int, str], str | None],
             value_names: tuple[str, ...],
             percent_repair_floor: float = 10000) -> dict | None:
    """All instances of one numbered template in one partition, or None.

    Returns {"unit", "instances": {"current": [...], "prior": [...], ...}},
    each row a dict with template_row / label / role / page / block_id and
    one key per `value_names`, money already scaled to canonical bin.
    """
    hits = detect(partition_blocks(tab, key), sig, max_row)
    if not hits:
        return None
    unit = hits[0][3]
    factor = U.UNIT_SCALE.get(unit)
    instances: list[list[dict]] = [[]]
    last_no = 0
    for pg, bid, grid, _u, _s in hits:
        cols = block_columns(grid, max_row, n_values)
        prev_unnumbered: list[float | None] | None = None
        for r in grid:
            cells = r["cells"]
            vals = [num(cells[c]) if c < len(cells) else None for c in cols]
            vals = [None] * (n_values - len(vals)) + vals
            n = rowno(r, max_row)
            if n is None:
                prev_unnumbered = vals if any(v is not None for v in vals) else None
                continue
            label = _LABEL_PREFIX.sub("", (r["label"] or "").strip())
            if not label:
                continue
            if all(v is None for v in vals) and prev_unnumbered is not None:
                vals = prev_unnumbered          # the label wrapped; values above
            prev_unnumbered = None
            if n <= last_no and instances[-1]:
                instances.append([])
            last_no = n
            if n in percent_rows:
                vals = repair_percent(vals, percent_repair_floor)
            elif factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"template_row": n, "label": label, "role": role_of(n, label),
                   "page": pg, "block_id": bid}
            row.update(zip(value_names, vals))
            instances[-1].append(row)
    instances = [i for i in instances
                 if any(x["template_row"] >= bottom_row for x in i)]
    if not instances:
        return None
    labels = ("current", "prior", "extra2", "extra3")
    return {"unit": unit,
            "instances": {labels[i]: inst for i, inst in enumerate(instances[:4])}}
