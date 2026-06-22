"""OCR a rendered statement page into {row-label-prefix -> column values}.

The image-only (scanned) BRSA statement pages have no text layer; the user
sanctioned OCR for transcribing them. easyocr (CPU) reads the digits; the caller
maps rows to the known BRSA hierarchy and verifies the statement identities — so
an OCR digit slip is caught, never silently stored.

  rows = ocr_rows("page.png")            # [(y, [(x, text), ...]), ...]
  cols = row_numbers(line)               # [int|None, ...] left→right number cols
Numbers are normalised to ints (thousands separators dropped, "(...)" → negative).
"""
from __future__ import annotations

import re
import sys

_reader = None


def reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def parse_num(t: str) -> int | None:
    t = t.strip().replace(" ", "")
    if not re.search(r"\d", t):
        return None
    neg = t.startswith("(") or t.startswith("-")
    digits = re.sub(r"\D", "", t)
    if not digits:
        return None
    return -int(digits) if neg else int(digits)


def _is_num_token(t: str) -> bool:
    # a value cell: digits + separators/parens, NO letters (footnotes like
    # "(5.IV.2)" carry letters and are skipped).
    return bool(re.fullmatch(r"[(\-]?[\d.,]+\)?\|?", t.strip())) and bool(re.search(r"\d", t))


def ocr_rows(png: str, ytol: float = 22.0):
    res = reader().readtext(png, detail=1, paragraph=False)
    items = []
    for box, txt, _conf in res:
        y = sum(p[1] for p in box) / 4
        x = sum(p[0] for p in box) / 4
        items.append((y, x, txt))
    items.sort()
    rows, cur, base = [], [], None
    for y, x, txt in items:
        if base is None or y - base <= ytol:
            cur.append((x, txt))
            base = y if base is None else base
        else:
            rows.append((base, sorted(cur)))
            cur, base = [(x, txt)], y
    if cur:
        rows.append((base, sorted(cur)))
    return rows


def row_numbers(line) -> list[int | None]:
    """Left→right numeric column values for one OCR row (footnote tokens skipped)."""
    return [parse_num(t) for _x, t in line if _is_num_token(t)]


def _value_columns(rows, n_cols: int, xtol: float = 130.0) -> list[float]:
    """Detect the x-centres of the n_cols rightmost number columns (the value
    columns — the leftmost cluster is the row-number prefix '1.2', excluded)."""
    xs = sorted(x for _y, line in rows for x, t in line if _is_num_token(t))
    clusters: list[list[float]] = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= xtol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    centres = [sum(c) / len(c) for c in clusters]
    return centres[-n_cols:] if len(centres) >= n_cols else centres


def col_rows(png: str, n_cols: int):
    """Yield (label, [col0..col_{n_cols-1}]) per row, numbers aligned to the
    detected value columns by x-position. col0 is the leftmost value column
    (current-period cumulative for the P&L / current for OCI / current-TL for BS)."""
    rows = ocr_rows(png)
    cols = _value_columns(rows, n_cols)
    out = []
    for _y, line in rows:
        vals: list[int | None] = [None] * len(cols)
        label_toks = []
        for x, t in line:
            if _is_num_token(t):
                ci = min(range(len(cols)), key=lambda i: abs(cols[i] - x))
                if abs(cols[ci] - x) <= 160:
                    vals[ci] = parse_num(t)
            else:
                label_toks.append(t)
        out.append((" ".join(label_toks), vals))
    return out


if __name__ == "__main__":
    for y, line in ocr_rows(sys.argv[1]):
        label = " ".join(t for _x, t in line if not _is_num_token(t))
        nums = row_numbers(line)
        if nums:
            print(f"{label[:34]:34} | {nums}")
