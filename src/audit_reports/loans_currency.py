"""Sector-level loan exposure extractor — TL / FC currency split by sector.

Every BRSA audit report includes a table titled along the lines of
"Information by major sectors" that carries either Stage 2/3/ECL columns
or TL/FC (currency split) columns — sometimes both on the same page.

This module extracts the TL/FC columns:
  - TL amount  (local currency, thousands)
  - FC amount  (foreign currency, thousands)
  - TL %       (optional; not all banks disclose)
  - FC %       (optional; not all banks disclose)

Sector taxonomy is shared with loans_by_sector (BRSA-mandated, universal
across all 31 banks).  The same canonical keys are used.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .units import UnitContext
from .extractor import _HAS_FITZ, _fitz_page_count, _fitz_page_text, parse_amount
from .loans_by_sector import (
    _NONCASH_HINTS,
    _NUM_TOKEN,
    _SECTOR_LABELS_SORTED,
    _page_has_sector_heading,
    _xy_lines,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CurrencyRow:
    sector: str                       # canonical key (e.g. 'mfg_production') or 'unknown'
    tl_amount: float | None = None
    fc_amount: float | None = None
    tl_pct: float | None = None
    fc_pct: float | None = None
    period_type: str = "current"      # 'current' | 'prior'
    page: int = 0
    raw_label: str = ""               # original label as it appeared, for debug


@dataclass
class LoansCurrencyReport:
    pdf_path: str = ""
    rows: list[CurrencyRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Column detection — TL / FC headers
# ---------------------------------------------------------------------------
# Detect the TL/FC column headers on a page that already has a sector heading.
# Returns a list of (column_name, x_right) tuples when found, else None.
#
# The currency block is characterised by TP/YP/TL/FC/FX/TRL/LC tokens or
# percentage signs (%) in the header band, with 2, 4, or 8 live columns.
# Stage/ASAMA/ECL/PROVISION words disqualify a block — those belong to the
# narrow loans_by_sector lane.

_STAGE_DISQUALIFY = re.compile(
    r"stage|aşama|asama|karsilik|provision|ecl|expected|beklenen|tfrs\s*9|ifrs\s*9",
    re.IGNORECASE,
)
_CURRENCY_TOKENS = re.compile(
    r"\b(TP|YP|TL|FC|FX|TRL|LC)\b|\(%\)|%", re.IGNORECASE,
)


def _currency_col_x(
    lines: list[list[tuple[float, float, str]]],
) -> list[tuple[str, float]] | None:
    """Detect TL/FC column headers and return [(name, x_right), ...].

    Returns None when no currency column block is found or when the page
    carries stage/ECL headers instead (those belong to loans_by_sector).
    """
    # Scan header rows (first ~6 rows typically contain column headers).
    header_text = " ".join(
        t for row in lines[:8] for _x0, _x1, t in row
    ).lower()

    # Refuse when stage words dominate — this is the stage block, not currency.
    if _STAGE_DISQUALIFY.search(header_text) and not _CURRENCY_TOKENS.search(header_text):
        return None

    # Build a map of column positions from header rows.
    # We look for tokens that indicate currency columns.
    col_positions: dict[float, list[str]] = {}
    for row in lines[:8]:
        for x0, x1, t in row:
            tok = t.strip().lower()
            if tok in ("tp", "yp", "tl", "fc", "fx", "trl", "lc") or tok in ("(%)", "%"):
                col_positions.setdefault(x1, []).append(tok)

    if not col_positions:
        return None

    # Group adjacent header tokens into column bands.
    sorted_xs = sorted(col_positions.keys())
    bands: list[list[str]] = []
    current_band: list[str] = [col_positions[sorted_xs[0]][0]]
    for i in range(1, len(sorted_xs)):
        if sorted_xs[i] - sorted_xs[i - 1] < 30:
            current_band.extend(col_positions[sorted_xs[i]])
        else:
            bands.append(current_band)
            current_band = [col_positions[sorted_xs[i]][0]]
    bands.append(current_band)

    # Classify each band by its header tokens.
    col_names: list[tuple[str, float]] = []
    for band, x_right in zip(bands, sorted_xs):
        htext = " ".join(band)
        if re.search(r"%|\(%\)", htext):
            # Percentage column
            if re.search(r"tl|tp|yp(?!\s*%)", htext) and not re.search(r"fc|fx|lc", htext):
                col_names.append(("tl_pct", x_right))
            elif re.search(r"fc|fx|lc", htext):
                col_names.append(("fc_pct", x_right))
            else:
                col_names.append(("tl_pct", x_right))  # ambiguous, default
        elif re.search(r"tl|tp", htext, re.IGNORECASE):
            col_names.append(("tl", x_right))
        elif re.search(r"fc|fx|lc|yp", htext, re.IGNORECASE):
            col_names.append(("fc", x_right))
        elif re.search(r"onceki|prior|previous", htext, re.IGNORECASE):
            # Prior-period column — we name it with _prior suffix later
            col_names.append(("prior", x_right))

    n = len(col_names)
    if n not in (2, 4, 8):
        return None

    # Map to canonical names based on count.
    if n == 2:
        names = ["tl", "fc"]
    elif n == 4:
        # Check if there are % columns
        has_pct = any(c in ("tl_pct", "fc_pct") for c, _ in col_names)
        if has_pct:
            names = ["tl", "tl_pct", "fc", "fc_pct"]
        else:
            # Could be tl, fc, tl_prior, fc_prior
            has_prior = any(c == "prior" for c, _ in col_names)
            if has_prior:
                names = ["tl", "fc", "tl_prior", "fc_prior"]
            else:
                names = ["tl", "tl_pct", "fc", "fc_pct"]
    elif n == 8:
        names = ["tl", "tl_pct", "fc", "fc_pct",
                 "tl_prior", "tl_pct_prior", "fc_prior", "fc_pct_prior"]
    else:
        return None

    result = []
    for i, (col_name, x_right) in enumerate(col_names):
        if i < len(names):
            result.append((names[i], x_right))
    return result


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_currency_xy(
    page_idx: int,
    lines: list[list[tuple[float, float, str]]],
) -> list[CurrencyRow] | None:
    """Column-aware extraction: align each sector row's numbers to the
    TL/FC header columns by x-position. Returns None when currency
    headers can't be located."""
    cols = _currency_col_x(lines)
    if not cols or len(cols) < 2:
        return None

    # We need at least tl and fc columns.
    tl_x = next((x for name, x in cols if name == "tl"), None)
    fc_x = next((x for name, x in cols if name == "fc"), None)
    if tl_x is None or fc_x is None:
        return None

    # Build a lookup for optional columns.
    col_lookup = {name: x for name, x in cols}

    rows: list[CurrencyRow] = []
    period_type = "current"
    seen_current = False

    for row in lines:
        text = " ".join(t for _, _, t in row).strip()
        low = text.lower()

        # Period captions
        if re.search(r"\bcurrent\s+period\b|\bcari\s+dönem\b", low):
            period_type, seen_current = "current", True
            continue
        if re.search(r"\bprior\s+period\b|\bönceki\s+dönem\b", low):
            if seen_current:
                period_type = "prior"
            continue

        # Clean the label
        clean = re.sub(r"^(?:\(\w\)|[\w.]{1,5})[.\)]\s+", "", text)
        clean = re.sub(r"^\(\d+\)\s+", "", clean)
        clean = re.sub(r"^\d+(?:\.\d+)*\s+", "", clean)

        # Match sector label
        sector_key = None
        for lbl, key in _SECTOR_LABELS_SORTED:
            if clean.lower().startswith(lbl):
                sector_key = key
                break

        # Extract numbers with x-positions
        nums = [(parse_amount(t), x1) for _x0, x1, t in row
                if re.fullmatch(_NUM_TOKEN, t)]
        nums = [(v, x) for v, x in nums if v is not None]
        if not nums:
            continue
        if sector_key is None:
            sector_key = "unknown"

        def nearest(anchor: float, other: float):
            best, bestd = None, 1e9
            for v, x in nums:
                d = abs(x - anchor)
                if d < bestd and d <= abs(x - other):
                    best, bestd = v, d
            return best

        tl_val = nearest(tl_x, fc_x)
        fc_val = nearest(fc_x, tl_x)

        # Optional: tl_pct, fc_pct
        tl_pct_x = col_lookup.get("tl_pct")
        fc_pct_x = col_lookup.get("fc_pct")
        tl_pct_val = None
        fc_pct_val = None
        if tl_pct_x is not None and tl_pct_x != tl_x:
            tl_pct_val = nearest(tl_pct_x, fc_x)
        if fc_pct_x is not None and fc_pct_x != fc_x:
            fc_pct_val = nearest(fc_pct_x, tl_x)

        rows.append(CurrencyRow(
            sector=sector_key,
            tl_amount=tl_val,
            fc_amount=fc_val,
            tl_pct=tl_pct_val,
            fc_pct=fc_pct_val,
            period_type=period_type,
            page=page_idx,
            raw_label=clean[:60],
        ))

    return rows or None


def _extract_currency_text(
    page_idx: int,
    text: str,
) -> list[CurrencyRow]:
    """Fallback text parser: pull (sector, tl, fc) tuples from lines.

    Each sector heading line has the pattern:
        <known_sector_label> <tl> <fc>
    or with percentages:
        <known_sector_label> <tl> <tl_pct> <fc> <fc_pct>
    """
    rows: list[CurrencyRow] = []
    period_type = "current"
    seen_current_caption = False

    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        lower = ln.lower()

        if re.search(r"\bcurrent\s+period\b|\bcari\s+dönem\b", lower):
            period_type = "current"
            seen_current_caption = True
            continue
        if re.search(r"\bprior\s+period\b|\bönceki\s+dönem\b", lower):
            if seen_current_caption:
                period_type = "prior"
            continue

        # Clean label
        ln_clean = re.sub(r"^(?:\(\w\)|\w{1,3})[\.\)]\s+", "", ln)
        ln_clean = re.sub(r"^\(\d+\)\s+", "", ln_clean)
        ln_clean = re.sub(r"^\d+(?:\.\d+)*\s+", "", ln_clean)

        # Match trailing numbers (2, 4, or 8)
        nums_all = re.findall(rf"(?:{_NUM_TOKEN})", ln_clean)
        if len(nums_all) not in (2, 4, 8):
            continue

        label_part = ln_clean
        for m in re.finditer(_NUM_TOKEN, ln_clean):
            label_part = ln_clean[: m.start()].strip()
            break
        if not label_part:
            continue

        # Match sector
        candidate = re.sub(r"\(\*+\)\s*$", "", label_part).strip()
        candidate = re.sub(r"\(\d+\)\s*$", "", candidate).strip()
        sector_key = None
        for lbl, key in _SECTOR_LABELS_SORTED:
            if candidate.lower().startswith(lbl):
                sector_key = key
                break
        if sector_key is None:
            sector_key = "unknown"

        # Parse based on count
        vals = [parse_amount(v) for v in nums_all]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            continue

        tl_val = vals[0]
        fc_val = vals[1]
        tl_pct_val = vals[2] if len(vals) > 2 and len(nums_all) in (4, 8) else None
        fc_pct_val = vals[3] if len(vals) > 3 and len(nums_all) in (4, 8) else None

        rows.append(CurrencyRow(
            sector=sector_key,
            tl_amount=tl_val,
            fc_amount=fc_val,
            tl_pct=tl_pct_val,
            fc_pct=fc_pct_val,
            period_type=period_type,
            page=page_idx,
            raw_label=candidate[:60],
        ))

    return rows


def extract_from_pdf(
    pdf_path: str = "",
    skip_pages: int = 30,
) -> LoansCurrencyReport:
    """Scan the PDF for the sector-by-currency table.

    `skip_pages` skips the BS/PL statements — the currency-sector table is
    always in the credit-risk footnote section.
    """
    rep = LoansCurrencyReport(pdf_path=pdf_path)
    if not (pdf_path and _HAS_FITZ):
        return rep
    n_pages = _fitz_page_count(pdf_path) or 0

    for i in range(skip_pages + 1, n_pages + 1):
        text = _fitz_page_text(pdf_path, i - 1)
        if not _page_has_sector_heading(text):
            continue
        # Skip non-cash pages entirely — those are a different disclosure.
        if _NONCASH_HINTS.search(text):
            continue

        lines = _xy_lines(pdf_path, i - 1)
        if lines:
            xy = _extract_currency_xy(i, lines)
            if xy:
                rep.rows.extend(xy)
                continue

        # Fallback: text parser
        txt = _extract_currency_text(i, text)
        if txt:
            rep.rows.extend(txt)

    return rep


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------

def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: LoansCurrencyReport,
    *,
    unit: UnitContext,
    commit: bool = True,
) -> int:
    """Idempotently store one bank's currency rows. Returns row count."""
    cur = conn.cursor()
    keys = {(r.sector, r.period_type) for r in rep.rows}
    if len(keys) != len(rep.rows):
        raise ValueError("duplicate sector/period rows in currency table")
    existing = set(cur.execute(
        "SELECT sector,period_type FROM bank_audit_loans_currency "
        "WHERE bank_ticker=? AND period=? AND kind=?", (bank_ticker, period, kind)))
    cur.executemany(
        "DELETE FROM bank_audit_loans_currency WHERE bank_ticker=? AND period=? "
        "AND kind=? AND sector=? AND period_type=?",
        [(bank_ticker, period, kind, *key) for key in existing - keys])
    rows = [(
        bank_ticker, period, kind, r.sector, r.period_type,
        r.page, r.tl_amount, r.fc_amount, r.tl_pct, r.fc_pct,
        r.raw_label,
    ) for r in rep.rows]
    rows = unit.scale_rows(
        "bank_audit_loans_currency",
        ["bank_ticker", "period", "kind", "sector", "period_type",
         "source_page", "tl_amount", "fc_amount", "tl_pct", "fc_pct", "raw_label"],
        rows,
    )
    if rows:
        facts = ("source_page", "tl_amount", "fc_amount", "tl_pct", "fc_pct", "raw_label")
        cur.executemany(
            "INSERT INTO bank_audit_loans_currency "
            "(bank_ticker, period, kind, sector, period_type, source_page, "
            " tl_amount, fc_amount, tl_pct, fc_pct, raw_label) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(bank_ticker,period,kind,sector,period_type) DO UPDATE SET "
            + ",".join(f"{col}=excluded.{col}" for col in facts)
            + ",extracted_at=CURRENT_TIMESTAMP WHERE "
            + " OR ".join(f"{col} IS NOT excluded.{col}" for col in facts),
            rows,
        )
    if commit:
        conn.commit()
    return len(rows)
