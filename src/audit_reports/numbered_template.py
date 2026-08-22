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

# the Turkish letters, plus the circumflexed vowels older filings still
# print ("Kâr", "Resmî", "Mahkûm") — one registry pattern must match both
_TR_FOLD = str.maketrans("İıŞşĞğÜüÖöÇçÂâÎîÛû", "IiSsGgUuOoCcAaIiUu")
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


def live_value_columns(grid: list[dict], max_row: int) -> int:
    """How many live value columns a block has after its row-number column —
    the shape that tells CR4 (six) from CR5 (ten-plus) when both number the
    same asset-class rows 1-18."""
    return len(block_columns(grid, max_row, 99))


def detect(blocks: list[tuple], sig: dict[int, re.Pattern], max_row: int,
           min_sig: int = 2,
           block_filter: Callable[[list[dict]], bool] | None = None) -> list[tuple]:
    hits = []
    for pg, bid, grid, unit in blocks:
        if block_filter is not None and not block_filter(grid):
            continue
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
             percent_repair_floor: float = 10000,
             percent_cols: frozenset[int] = frozenset(),
             block_filter: Callable[[list[dict]], bool] | None = None,
             row_live_cells: bool = False) -> dict | None:
    """All instances of one numbered template in one partition, or None.

    `row_live_cells`: a row holding exactly `n_values` non-empty cells after
    its number uses THOSE, whatever the block-level column model says. For
    when the capture merged two side-by-side templates into one block (CR1
    prior + CR2 share a six-column grid at AKTIF) and the block's last-N live
    columns stagger one of them. Opt-in: the lanes minted before it are
    untouched.

    Returns {"unit", "instances": {"current": [...], "prior": [...], ...}},
    each row a dict with template_row / label / role / page / block_id and
    one key per `value_names`, money already scaled to canonical bin.
    """
    hits = detect(partition_blocks(tab, key), sig, max_row, block_filter=block_filter)
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
            live = [c for c in cells[1:] if c is not None] if row_live_cells else []
            if len(live) == n_values:
                vals = [num(c) for c in live]
            else:
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
                # percent COLUMNS (CR4's RWA density) stay unscaled on money rows
                vals = [v if i in percent_cols else U.scale_amount(v, factor)
                        for i, v in enumerate(vals)]
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


def assemble_by_label(tab: sqlite3.Connection, key: tuple, *,
                      labels: list[tuple[int, re.Pattern]], n_values: int,
                      percent_rows: set[int], open_rows: set[int], close_row: int,
                      min_rows: int, role_of: Callable[[int, str], str | None],
                      value_names: tuple[str, ...], gate: Callable[[list[dict]], bool],
                      percent_repair_floor: float = 10000,
                      period_hint: Callable[[str | None, list[dict]], str | None] | None = None,
                      tail_of: Callable[[int, int], list[tuple[int, str, list]] | None] | None = None,
                      ) -> dict | None:
    """The same numbered template read WITHOUT its numbers: a chain of rows
    matched by label (`labels`: (template_row, regex) in match-priority
    order, tried on the folded label with any leading number stripped; a
    template_row may be a tuple of alternatives — the NSFR's twin "%35 or
    lower risk weight" rows 21 and 23 — the first one after the chain's
    last row taken), kept in template order, continued over adjacent
    blocks, opened only on
    `open_rows`, closed on `close_row` or on the first block that does not
    continue it, and kept only when `gate(rows)` — the template's own
    arithmetic — holds. Sub-headers print no cells and take no row; a
    matched row with no cells adopts the cells of the unmatched row below
    (a label that wrapped). Values are the last `n_values` live columns.

    Instances are labelled current / prior / extra... in print order, or by
    `period_hint(heading, grid)` where it says.

    `tail_of(page, block_id)` supplies rows the capture kept as prose rather
    than grid rows — the NSFR's total-RSF and ratio lines, which print as
    "Gerekli İstikrarlı Fon 364,384" with the figure inside the text. It is
    called with the chain's last block and returns [(template_row, label,
    cells)] appended before the gate, so the gate still decides.
    """
    from . import band_matrix as BM

    def template_row(label: str, after: int = 0) -> int | None:
        f = re.sub(r"^\d{1,2}[.)]?\s*", "", fold(label).strip())
        for n, rx in labels:
            if rx.search(f):
                if isinstance(n, tuple):
                    return next((c for c in n if c > after), None)
                return n
        return None

    blocks = [(pg, bid, h, json.loads(g), unit) for pg, bid, h, g, unit in tab.execute(
        "SELECT page, block_id, heading, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key)]
    # one sequence over the partition, so a label that wraps across a block
    # boundary (TEB's NSFR row 20: the label closes one block, its values
    # open the next) still adopts its values
    seq: list[tuple[int, int, str | None, str | None, dict]] = [
        (pg, bid, h, unit, r) for pg, bid, h, grid, unit in blocks for r in grid]
    tagged_seq: list[tuple[int, int, str | None, str | None, dict, int | None]] = []
    for i, (pg, bid, h, unit, r) in enumerate(seq):
        has_cells = any(c is not None for c in r["cells"])
        n = template_row(r["label"] or "") if (r["label"] or "").strip() else None
        if n is not None and not has_cells and i + 1 < len(seq):
            nxt = seq[i + 1][4]
            if template_row(nxt["label"] or "") is None and any(c is not None for c in nxt["cells"]):
                r = {**r, "cells": nxt["cells"]}            # the label wrapped; values below
                has_cells = True
        tagged_seq.append((pg, bid, h, unit, r, n if has_cells else None))
    by_block: dict[tuple[int, int], list] = {}
    meta: dict[tuple[int, int], tuple] = {}
    for pg, bid, h, unit, r, n in tagged_seq:
        by_block.setdefault((pg, bid), []).append((r, n))
        meta[(pg, bid)] = (h, unit)

    chain: list[tuple] = []
    unit = None
    hint = None
    last = (-1, -1)
    found: list[tuple[list, str | None, str | None]] = []

    def close():
        """End the chain: where it stops short of `close_row`, `tail_of` may
        still supply the rows the capture kept as prose."""
        nonlocal chain, hint
        if chain and tail_of is not None and chain[-1][3] < close_row:
            extra = tail_of(chain[-1][0], chain[-1][1])
            if extra:
                width = max(len(r["cells"]) for _p, _b, r, _n in chain)
                for n, label, cells in extra:
                    if n > chain[-1][3]:
                        # the callback puts each figure in its LAST cell; pad
                        # left so the row lines up with the block's columns
                        cells = [None] * (width - len(cells)) + list(cells)
                        chain.append((chain[-1][0], chain[-1][1], {"label": label, "cells": cells}, n))
        if chain and any(n in open_rows for *_x, n in chain) and len(chain) >= min_rows:
            found.append((chain, unit, hint))
        chain, hint = [], None

    for (pg, bid), tagged in by_block.items():
        heading, u = meta[(pg, bid)]
        grid = [r for r, _n in tagged]
        nums = [n for _r, n in tagged if n]
        adjacent = (pg == last[0] and bid == last[1] + 1) or (pg == last[0] + 1 and bid == 1)
        if not nums:
            if chain and not adjacent:
                close()
            continue
        # a block continues the chain only when its FIRST template row does:
        # a block that opens on row 1 is the next table (ING's prior NSFR)
        first_n = next((template_row(r["label"] or "", chain[-1][3]) for r, n in tagged if n), None) if chain else None
        continues = bool(chain) and adjacent and first_n is not None and first_n > chain[-1][3]
        if not continues:
            close()
            unit = u
            hint = period_hint(heading, grid) if period_hint else None
        for r, n in tagged:
            if n and chain:
                n = template_row(r["label"] or "", chain[-1][3])   # the alternatives, after the chain's last row
            if n and (not chain or n > chain[-1][3]):
                if not chain and n not in open_rows:
                    continue
                chain.append((pg, bid, r, n))
        last = (pg, bid)
        if chain and chain[-1][3] == close_row:
            close()
    close()
    # instances are labelled in CHAIN order — a refused first table still
    # makes the surviving second one the prior — unless the heading says
    order = ("current", "prior", "extra2", "extra3")
    out: dict[str, list[dict]] = {}
    unit_out = found[0][1] if found else None
    for idx, (chain, u, h) in enumerate(found[:4]):
        factor = U.UNIT_SCALE.get(u)
        # the value columns are a BLOCK's, not the chain's: a chain that
        # spans blocks of different widths (TEB's NSFR: six cells on one
        # page, seven on the next) would misread every row otherwise
        cols_by_block: dict[tuple[int, int], list[int]] = {}
        for pg, bid, r, _n in chain:
            cols_by_block.setdefault((pg, bid), []).append(r)
        for pgbid, block_rows in list(cols_by_block.items()):
            live = BM.live_value_columns(block_rows)
            ncol = max(len(r["cells"]) for r in block_rows)
            cols_by_block[pgbid] = (live[-n_values:] if len(live) >= n_values
                                    else list(range(ncol - n_values, ncol)))
        rows = []
        for pg, bid, r, n in chain:
            cells = r["cells"]
            cols = cols_by_block[(pg, bid)]
            vals = [num(cells[c]) if 0 <= c < len(cells) else None for c in cols]
            vals = [None] * (n_values - len(vals)) + vals
            if n in percent_rows:
                vals = repair_percent(vals, percent_repair_floor)
            elif factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"template_row": n, "label": (r["label"] or "").strip(), "role": role_of(n, r["label"] or ""),
                   "page": pg, "block_id": bid}
            row.update(zip(value_names, vals))
            rows.append(row)
        if not gate(rows):
            continue
        label = h if h in ("current", "prior") and h not in out else order[idx]
        if label in out:
            label = next(o for o in order if o not in out)
        out[label] = rows
    if not out:
        return None
    return {"unit": unit_out, "instances": out}


def absorb_inline(grid: list[dict], role_of, keep=None) -> list[dict]:
    """Fold the document layer's `inline` rows (label-only lines printed
    inside a block: a wrapped row head, or a sub-header) into a grid a
    registry lane can read. A head is prepended to the row below when the
    row's bare label has no role (or a placeholder one, "_...") and the
    joined label has one; anything else is dropped — except an inline row
    `keep(label)` claims (a period head such as "Önceki Dönem (Net)"),
    which stays as a valueless row of its own. Rows without the flag pass
    through untouched."""
    out: list[dict] = []
    pending = ""
    for r in grid:
        if r.get("inline"):
            label = (r["label"] or "").strip()
            if keep is not None and label and keep(label):
                pending = ""
                out.append({k: v for k, v in r.items() if k != "inline"})
                continue
            pending = (pending + " " + label).strip()
            continue
        if pending:
            label = (r["label"] or "").strip()
            bare = role_of(label) if label else None
            joined = role_of(pending + " " + label) if label else None
            if (bare is None or str(bare).startswith("_")) and joined is not None:
                r = {**r, "label": pending + " " + label}
            pending = ""
        out.append(r)
    return out
