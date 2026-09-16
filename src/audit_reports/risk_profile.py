"""Pillar 3 risk profile by sector — 17 exposure classes + TL/FC/Total.

Every BRSA audit report's Pillar 3 section includes a table titled along
the lines of "Sektöre Göre Risk Profili" / "Risk Profile by Sectors" that
carries the 17 standardised-approach credit-risk exposure classes as
columns, plus TL, FC and Total closing columns.

Sector rows use the same taxonomy as loans_by_sector (agriculture,
industry, construction, services, other, total).  The 20-column layout
is the distinguishing feature versus the Stage-2/3/ECL tables.
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
    _xy_lines,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

# The 17 standardised-approach exposure classes, in the regulator's order.
EXPOSURE_CLASSES: list[str] = [
    "class_1", "class_2", "class_3", "class_4", "class_5",
    "class_6", "class_7", "class_8", "class_9", "class_10",
    "class_11", "class_12", "class_13", "class_14", "class_15",
    "class_16", "class_17",
]

# Exposure class names for label-based detection (TR + EN).
_CLASS_NAMES: list[re.Pattern] = [
    re.compile(r"MERKEZI YONETIM|CENTRAL GOVERNMENT|SOVEREIGN"),
    re.compile(r"BOLGESEL|REGIONAL|LOCAL"),
    re.compile(r"IDARI BIRIM|ADMINISTRATIVE|NON.?COMMERCIAL"),
    re.compile(r"COK TARAFLI|MULTILATERAL"),
    re.compile(r"ULUSLARARASI TESKILAT|INTERNATIONAL ORGANI"),
    re.compile(r"BANKALAR VE ARACI|BANKS AND (BROKER|INTERMEDIAR|SECURITIES)|BANKS AND FINANCIAL"),
    re.compile(r"KURUMSAL|CORPORATE"),
    re.compile(r"PERAKENDE|RETAIL"),
    re.compile(r"IKAMET|RESIDENTIAL"),
    re.compile(r"TICARI AMACLI|COMMERCIAL (REAL|PROPERTY|MORTGAGE|IMMOVABLE)"),
    re.compile(r"TAHSILI GECIKMIS|PAST.?DUE|OVERDUE"),
    re.compile(r"RISKI YUKSEK|HIGH(ER)?.?RISK"),
    re.compile(r"TEMINATLI MENKUL|COVERED BOND|MORTGAGE.?BACKED"),
    re.compile(r"MENKUL KIYMETLES|SECURITI[SZ]ATION|KISA VADELI|SHORT.?TERM"),
    re.compile(r"KOLEKTIF|COLLECTIVE INVESTMENT|MUTUAL FUND"),
    re.compile(r"HISSE SENEDI|EQUITY|SHARE"),
    re.compile(r"DIGER ALACAK|OTHER (RECEIVABLE|ITEM|ASSET|EXPOSURE)|^DIGER$|^OTHER$"),
]

_HEADING_PATTERNS = [
    re.compile(r"SEKTORE.GORE.RISK.PROFILI|RISK.?PROFILE.+SECTOR", re.IGNORECASE),
    re.compile(r"SEKTÖRE.GÖRE.RISK.PROFİLİ", re.IGNORECASE),
]


@dataclass
class RiskProfileRow:
    sector: str
    class_1: float | None = None
    class_2: float | None = None
    class_3: float | None = None
    class_4: float | None = None
    class_5: float | None = None
    class_6: float | None = None
    class_7: float | None = None
    class_8: float | None = None
    class_9: float | None = None
    class_10: float | None = None
    class_11: float | None = None
    class_12: float | None = None
    class_13: float | None = None
    class_14: float | None = None
    class_15: float | None = None
    class_16: float | None = None
    class_17: float | None = None
    tl_amount: float | None = None
    fc_amount: float | None = None
    total: float | None = None
    period_type: str = "current"
    page: int = 0
    raw_label: str = ""

    def amount_for(self, col: str) -> float | None:
        return getattr(self, col, None)


@dataclass
class RiskProfileReport:
    pdf_path: str = ""
    rows: list[RiskProfileRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Column detection — 17 exposure classes + TL/FC/Total
# ---------------------------------------------------------------------------

def _page_has_risk_profile_heading(text: str) -> bool:
    return any(p.search(text) for p in _HEADING_PATTERNS)


def _detect_class_columns_xy(
    lines: list[list[tuple[float, float, str]]],
) -> list[tuple[str, float]] | None:
    """Detect the 20-column header (17 classes + TL + FC + Total) from
    x-position-aware line data. Returns [(column_name, x_right), ...]
    or None when the header can't be read."""
    # Strategy 1: numeric header row (1.0, 2.0, ..., 17.0, TP, YP, Toplam)
    for row in lines[:10]:
        cells_text = [t.strip() for _, _, t in row]
        nums = []
        for i, t in enumerate(cells_text):
            try:
                v = float(t.replace(",", "."))
                if v == int(v) and 1 <= int(v) <= 17:
                    nums.append((i, int(v)))
            except (ValueError, TypeError):
                pass
        if len(nums) >= 10:
            nums_sorted = sorted(nums, key=lambda x: x[1])
            if [n for _, n in nums_sorted] == list(range(1, len(nums_sorted) + 1)):
                out: dict[int, str] = {i: f"class_{n}" for i, n in nums_sorted}
                # Look for TP/YP/Toplam after the last numbered column
                last_idx = max(i for i, _ in nums_sorted)
                for i, t in enumerate(cells_text):
                    if i <= last_idx:
                        continue
                    tok = t.strip().upper()
                    if tok in ("TP", "TL", "TRL", "LC"):
                        out[i] = "tl"
                    elif tok in ("YP", "FC", "FX"):
                        out[i] = "fc"
                    elif tok in ("TOPLAM", "TOTAL"):
                        out[i] = "total"
                if len(out) >= 19:
                    # `out` is keyed by cell index; the caller aligns rows by
                    # printed x-position, so translate each index to that
                    # token's right edge.
                    return [(out[i], float(row[i][1]))
                            for i in sorted(out) if i < len(row)]

    # Strategy 2: named column labels
    header_text = " ".join(t for row in lines[:8] for _, _, t in row).upper()
    class_hits = sum(1 for pat in _CLASS_NAMES if pat.search(header_text))
    if class_hits >= 8:
        # Map columns left-to-right by label matching
        col_map: dict[int, str] = {}
        nxt = 0
        for row in lines[:8]:
            for x0, x1, t in row:
                tok = t.strip()
                if not tok:
                    continue
                tok_up = tok.upper()
                if re.search(r"^TP$|^TL$|^TRL$|^LC$", tok_up):
                    col_map.setdefault(round(x1), "tl")
                elif re.search(r"^YP$|^FC$|^FX$", tok_up):
                    col_map.setdefault(round(x1), "fc")
                elif re.search(r"TOPLAM|TOTAL", tok_up):
                    col_map.setdefault(round(x1), "total")
                else:
                    for k in range(nxt, len(_CLASS_NAMES)):
                        if _CLASS_NAMES[k].search(tok_up):
                            col_map.setdefault(round(x1), f"class_{k + 1}")
                            nxt = k + 1
                            break
        if sum(1 for v in col_map.values() if v.startswith("class_")) >= 8:
            return [(v, float(k)) for k, v in sorted(col_map.items())]

    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_risk_profile_xy(
    page_idx: int,
    lines: list[list[tuple[float, float, str]]],
) -> list[RiskProfileRow] | None:
    """Column-aware extraction: detect the 20-column header and align
    each sector row's numbers to the exposure class columns."""
    cols = _detect_class_columns_xy(lines)
    if not cols or len(cols) < 19:
        return None

    # Build x-position lookup
    col_by_x: dict[float, str] = {x: name for name, x in cols}
    sorted_xs = sorted(col_by_x.keys())

    # Find TL, FC, Total anchors
    tl_x = next((x for x in sorted_xs if col_by_x.get(x) == "tl"), None)
    fc_x = next((x for x in sorted_xs if col_by_x.get(x) == "fc"), None)
    total_x = next((x for x in sorted_xs if col_by_x.get(x) == "total"), None)
    if tl_x is None or fc_x is None or total_x is None:
        return None

    # Class column x positions
    class_xs = [(col_by_x[x], x) for x in sorted_xs if col_by_x.get(x, "").startswith("class_")]

    rows: list[RiskProfileRow] = []
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

        # Match sector
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

        def nearest(anchor: float, exclude: float | None = None) -> float | None:
            best, bestd = None, 1e9
            for v, x in nums:
                d = abs(x - anchor)
                if d < bestd:
                    if exclude is None or abs(x - exclude) > d:
                        best, bestd = v, d
            return best

        # Read class columns
        class_vals: dict[str, float | None] = {}
        for cls_name, cls_x in class_xs:
            class_vals[cls_name] = nearest(cls_x, tl_x)

        # Read TL/FC/Total
        tl_val = nearest(tl_x, fc_x)
        fc_val = nearest(fc_x, tl_x)
        total_val = nearest(total_x, fc_x)

        rows.append(RiskProfileRow(
            sector=sector_key,
            class_1=class_vals.get("class_1"),
            class_2=class_vals.get("class_2"),
            class_3=class_vals.get("class_3"),
            class_4=class_vals.get("class_4"),
            class_5=class_vals.get("class_5"),
            class_6=class_vals.get("class_6"),
            class_7=class_vals.get("class_7"),
            class_8=class_vals.get("class_8"),
            class_9=class_vals.get("class_9"),
            class_10=class_vals.get("class_10"),
            class_11=class_vals.get("class_11"),
            class_12=class_vals.get("class_12"),
            class_13=class_vals.get("class_13"),
            class_14=class_vals.get("class_14"),
            class_15=class_vals.get("class_15"),
            class_16=class_vals.get("class_16"),
            class_17=class_vals.get("class_17"),
            tl_amount=tl_val,
            fc_amount=fc_val,
            total=total_val,
            period_type=period_type,
            page=page_idx,
            raw_label=clean[:60],
        ))

    return rows or None


def _extract_risk_profile_text(
    page_idx: int,
    text: str,
) -> list[RiskProfileRow]:
    """Fallback text parser: pull sector rows from lines that have 20+
    trailing numbers (17 classes + TL + FC + Total)."""
    rows: list[RiskProfileRow] = []
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

        # Match trailing numbers — need 20 for the full template
        nums_all = re.findall(rf"(?:{_NUM_TOKEN})", ln_clean)
        if len(nums_all) < 19:
            continue

        label_part = ln_clean
        for m in re.finditer(_NUM_TOKEN, ln_clean):
            label_part = ln_clean[: m.start()].strip()
            break
        if not label_part:
            continue

        candidate = re.sub(r"\(\*+\)\s*$", "", label_part).strip()
        candidate = re.sub(r"\(\d+\)\s*$", "", candidate).strip()
        sector_key = None
        for lbl, key in _SECTOR_LABELS_SORTED:
            if candidate.lower().startswith(lbl):
                sector_key = key
                break
        if sector_key is None:
            sector_key = "unknown"

        vals = [parse_amount(v) for v in nums_all]
        vals = [v for v in vals if v is not None]
        if len(vals) < 19:
            continue

        # First 17 are class_1..class_17, then TL, FC, Total
        class_vals = {f"class_{i + 1}": vals[i] if i < len(vals) else None
                      for i in range(17)}
        tl_val = vals[17] if len(vals) > 17 else None
        fc_val = vals[18] if len(vals) > 18 else None
        total_val = vals[19] if len(vals) > 19 else None

        rows.append(RiskProfileRow(
            sector=sector_key,
            class_1=class_vals.get("class_1"),
            class_2=class_vals.get("class_2"),
            class_3=class_vals.get("class_3"),
            class_4=class_vals.get("class_4"),
            class_5=class_vals.get("class_5"),
            class_6=class_vals.get("class_6"),
            class_7=class_vals.get("class_7"),
            class_8=class_vals.get("class_8"),
            class_9=class_vals.get("class_9"),
            class_10=class_vals.get("class_10"),
            class_11=class_vals.get("class_11"),
            class_12=class_vals.get("class_12"),
            class_13=class_vals.get("class_13"),
            class_14=class_vals.get("class_14"),
            class_15=class_vals.get("class_15"),
            class_16=class_vals.get("class_16"),
            class_17=class_vals.get("class_17"),
            tl_amount=tl_val,
            fc_amount=fc_val,
            total=total_val,
            period_type=period_type,
            page=page_idx,
            raw_label=candidate[:60],
        ))

    return rows


def extract_from_pdf(
    pdf_path: str = "",
    skip_pages: int = 30,
) -> RiskProfileReport:
    """Scan the PDF for the Pillar 3 risk-profile-by-sector table."""
    rep = RiskProfileReport(pdf_path=pdf_path)
    if not (pdf_path and _HAS_FITZ):
        return rep
    n_pages = _fitz_page_count(pdf_path) or 0

    for i in range(skip_pages + 1, n_pages + 1):
        text = _fitz_page_text(pdf_path, i - 1)
        if not _page_has_risk_profile_heading(text):
            continue
        if _NONCASH_HINTS.search(text):
            continue

        lines = _xy_lines(pdf_path, i - 1)
        if lines:
            xy = _extract_risk_profile_xy(i, lines)
            if xy:
                rep.rows.extend(xy)
                continue

        txt = _extract_risk_profile_text(i, text)
        if txt:
            rep.rows.extend(txt)

    return rep


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------

_COLS = [
    "class_1", "class_2", "class_3", "class_4", "class_5",
    "class_6", "class_7", "class_8", "class_9", "class_10",
    "class_11", "class_12", "class_13", "class_14", "class_15",
    "class_16", "class_17", "tl_amount", "fc_amount", "total",
]


def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: RiskProfileReport,
    *,
    unit: UnitContext,
    commit: bool = True,
) -> int:
    """Idempotently store one bank's risk profile rows. Returns row count."""
    cur = conn.cursor()
    keys = {(r.sector, r.period_type) for r in rep.rows}
    if len(keys) != len(rep.rows):
        raise ValueError("duplicate sector/period rows in risk profile table")
    existing = set(cur.execute(
        "SELECT sector,period_type FROM bank_audit_risk_profile "
        "WHERE bank_ticker=? AND period=? AND kind=?", (bank_ticker, period, kind)))
    cur.executemany(
        "DELETE FROM bank_audit_risk_profile WHERE bank_ticker=? AND period=? "
        "AND kind=? AND sector=? AND period_type=?",
        [(bank_ticker, period, kind, *key) for key in existing - keys])
    insert_cols = ["bank_ticker", "period", "kind", "sector", "period_type",
                   "source_page", "raw_label"] + _COLS
    rows = [(
        bank_ticker, period, kind, r.sector, r.period_type,
        r.page, r.raw_label,
        r.class_1, r.class_2, r.class_3, r.class_4, r.class_5,
        r.class_6, r.class_7, r.class_8, r.class_9, r.class_10,
        r.class_11, r.class_12, r.class_13, r.class_14, r.class_15,
        r.class_16, r.class_17, r.tl_amount, r.fc_amount, r.total,
    ) for r in rep.rows]
    rows = unit.scale_rows(
        "bank_audit_risk_profile",
        insert_cols,
        rows,
    )
    if rows:
        facts = _COLS + ["source_page", "raw_label"]
        cur.executemany(
            "INSERT INTO bank_audit_risk_profile "
            "(" + ",".join(insert_cols) + ") "
            "VALUES (" + ",".join("?" for _ in insert_cols) + ") "
            "ON CONFLICT(bank_ticker,period,kind,sector,period_type) DO UPDATE SET "
            + ",".join(f"{col}=excluded.{col}" for col in facts)
            + ",extracted_at=CURRENT_TIMESTAMP WHERE "
            + " OR ".join(f"{col} IS NOT excluded.{col}" for col in facts),
            rows,
        )
    if commit:
        conn.commit()
    return len(rows)
