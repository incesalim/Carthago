"""Column model for a NOTES-section matrix whose columns are ordered bands —
maturity bands (deposits by maturity, the maturity-gap table), repricing
bands — read from the capture's header fragments.

A captured matrix rarely keeps its header in one piece: fragments park in
dead columns between the live ones, one cell names two bands ("3-6 Ay 6
Ay-1 Yıl"), a "1.0" in a header row is "1 month", and some banks print an
unlabelled prior-period total column on the right. `column_model` reads
what it can, completes the gaps from the band set's canonical order, and
lets the data decide which column is the total.

Shared by scripts/build_deposit_maturity_full.py and
scripts/build_maturity_gap_full.py; each brings its own `BandSet`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.audit_reports.numbered_template import fold, num

_PRIOR_COL = re.compile(r"ONCEKI|PRIOR|PREVIOUS")
_DEFAULT_HEADER_LABEL = re.compile(r"CARI DONEM|ONCEKI DONEM|CURRENT PERIOD|PRIOR PERIOD|PREVIOUS PERIOD")


@dataclass
class BandSet:
    """The bands one matrix family prints, in canonical left-to-right order,
    with the regex that recognises each in a header fragment; `total` is
    recognised separately. `optional` names the bands a bank may omit
    (the deposit matrix's 7-day notice column), tried when a gap is one
    short of the canonical run."""
    bands: list[tuple[str, re.Pattern]]
    total: re.Pattern = field(default_factory=lambda: re.compile(r"TOPLAM|TOTAL"))
    optional: tuple[str, ...] = ()
    header_label: re.Pattern = _DEFAULT_HEADER_LABEL

    @property
    def order(self) -> list[str]:
        return [b for b, _rx in self.bands]

    def bands_in(self, text: str) -> list[str]:
        """Every band a header fragment names, in order of appearance."""
        f = fold(text)
        hits = []
        for band, rx in self.bands:
            m = rx.search(f)
            if m:
                hits.append((m.start(), band))
        m = self.total.search(f)
        if m:
            hits.append((m.start(), "total"))
        return [b for _pos, b in sorted(hits)]


def is_header_row(r: dict, header_label: re.Pattern = _DEFAULT_HEADER_LABEL) -> bool:
    cells = [c for c in r["cells"] if c is not None]
    if not cells:
        return bool(header_label.search(fold(r["label"] or "")))
    return all(isinstance(c, str) and c.strip() != "-" for c in cells)


def _fmt(cell) -> str | None:
    if cell is None:
        return None
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell).strip() or None


def adds_up(data: list[dict], cols, step: float = 1.0) -> float:
    """Share of value-bearing rows on which total = Σ bands under `cols`."""
    checked = ok = 0
    for r in data:
        cells = r["cells"]
        vals = {b: num(cells[i]) if i < len(cells) else None for i, b in cols if b}
        tot = vals.get("total")
        parts = [v for b, v in vals.items() if b not in ("total", "total_prior") and v is not None]
        if tot is None or not parts:
            continue
        checked += 1
        ok += int(abs(sum(parts) - tot) <= max(2.0 * step, 1e-5 * abs(tot)))
    return ok / checked if checked else 0.0


def column_model(grid: list[dict], col_labels: list, bs: BandSet,
                 min_named: int = 4) -> list[tuple[int, str | None]] | None:
    """[(cell index, band)] for the matrix's value columns, the total last
    (a trailing prior-period total column, where a bank prints one, as
    'total_prior'), or None.

    A value column is one live in at least a quarter of the data rows (a
    "7" split off a "7 Days Notice" label lives in one). Its header text is
    every fragment at its index AND at the dead columns just before it —
    the capture often parks a wrapped header in a column of its own. One
    fragment may name two bands: the earlier ones go backwards to the
    unnamed columns before. Readings must follow the canonical order; the
    gaps are completed from it.
    """
    order = bs.order
    data = [r for r in grid if not is_header_row(r, bs.header_label)]
    headers = [r for r in grid if is_header_row(r, bs.header_label)]
    if not data:
        return None
    ncol = max(len(r["cells"]) for r in data)
    live_counts = [sum(1 for r in data if i < len(r["cells"]) and r["cells"][i] is not None)
                   for i in range(ncol)]
    live = [i for i in range(ncol) if live_counts[i] >= max(2, len(data) / 4)]
    if len(live) < 4:
        return None
    frags: dict[int, list[str]] = {}
    prev = -1
    for i in live:
        toks = []
        for j in range(prev + 1, i + 1):
            toks += [t for r in headers if j < len(r["cells"]) and (t := _fmt(r["cells"][j]))]
            if j < len(col_labels) and col_labels[j]:
                toks.append(str(col_labels[j]))
        frags[i] = toks
        prev = i
    text = {i: " ".join(frags[i]) for i in live}
    # a trailing prior-period total column
    total_prior_idx = None
    if len(live) >= 6 and _PRIOR_COL.search(fold(text[live[-1]])) \
            and not [b for b in bs.bands_in(text[live[-1]]) if b != "total"]:
        total_prior_idx = live[-1]
        live = live[:-1]
    total_idx = live[-1]
    if [b for b in bs.bands_in(text[total_idx]) if b != "total"]:
        return None
    value_idx = live[:-1]
    bands: list[str | None] = [None] * len(value_idx)
    for k, i in enumerate(value_idx):
        found = [b for b in bs.bands_in(text[i]) if b != "total"]
        if not found:
            continue
        bands[k] = found[-1]
        back = k - 1
        for b in reversed(found[:-1]):
            if back >= 0 and bands[back] is None:
                bands[back] = b
                back -= 1
    # canonical order: a reading out of order is a misread, dropped
    last = -1
    for k, b in enumerate(bands):
        if b is None:
            continue
        pos = order.index(b)
        if pos <= last:
            bands[k] = None
        else:
            last = pos
    # complete the gaps from the canonical order between named neighbours
    k = 0
    while k < len(bands):
        if bands[k] is not None:
            k += 1
            continue
        j = k
        while j < len(bands) and bands[j] is None:
            j += 1
        lo = order.index(bands[k - 1]) + 1 if k > 0 else 0
        hi = order.index(bands[j]) if j < len(bands) else len(order)
        gap, avail = j - k, order[lo:hi]
        if len(avail) == gap:
            bands[k:j] = avail
        elif len(avail) == gap + 1:
            omit = [b for b in bs.optional if b in avail]
            if len(omit) == 1:
                bands[k:j] = [b for b in avail if b != omit[0]]
            elif j == len(bands):
                bands[k:j] = avail[:-1]           # the last band is the one missing
        k = j
    if sum(1 for b in bands if b is not None) < min_named:
        return None
    cols = [(i, b) for i, b in zip(value_idx, bands)] + [(total_idx, "total")]
    if total_prior_idx is not None:
        cols.append((total_prior_idx, "total_prior"))
    # the data has the last word on which column is the total: a bank that
    # prints an unlabelled prior-period total column to the right adds up
    # one column earlier
    if total_prior_idx is None and len(value_idx) >= 5:
        base = adds_up(data, cols)
        if base < 0.9:
            alt = [(i, b) for i, b in zip(value_idx[:-1], bands[1:] if bands[0] is None else bands[:-1])]
            alt = alt + [(value_idx[-1], "total"), (total_idx, "total_prior")]
            if adds_up(data, alt) >= 0.9 and adds_up(data, alt) > base:
                return alt
    return cols
