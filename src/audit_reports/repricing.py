"""Interest-rate repricing-gap extractor — BRSA §4 "Interest-rate risk" footnote.

Most BRSA audit reports (~81% of the corpus; participation banks word it as
profit-share-rate risk and often omit it) carry an interest-rate sensitivity
table laying assets/liabilities out by repricing bucket:

    Cari Dönem   1 Aya Kadar  1-3 Ay  3-12 Ay  1-5 Yıl  5 Yıl ve Üzeri  Faizsiz  Toplam
    Toplam Varlıklar   890,697,566  268,437,220  467,986,977  331,343,904  133,594,673  423,536,314  2,515,596,654
    Toplam Yükümlülükler ...
    Toplam Pozisyon   (118,680,506) (57,142,966) 177,037,251 291,530,881 64,907,609 (331,627,652) 26,024,617

A "Prior Period" block (usually the next page) repeats the table. English and
Turkish; the standard template has 5 maturity buckets + a non-interest-bearing
("Faizsiz" / "Non-Interest Bearing") column + Total = 7 columns.

We keep only the three summary rows — total assets (rate-sensitive assets),
total liabilities (rate-sensitive liabilities), and total position (the gap,
which nets on- and off-balance positions) — read as the trailing N values in
bucket order. The 1-year cumulative gap is derived. Banks whose table isn't the
standard 7-column shape (some participation banks, image-only quarters) are left
to the validated N/A tail. Footing identities are checked in validator.py.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .extractor import _HAS_FITZ, parse_num

# fitz-only: the §4 interest-rate-risk table is a single narrow footnote — fitz
# word clustering reads it faithfully and is far cheaper than pdfplumber per page,
# which adds no accuracy here (per the project's per-statement engine strategy).

_NUM_TOKEN = re.compile(r"^%?\(?-?\d[\d.,]*%?\)?$")
_NIL = {"-", "—", "–", "--", "---"}

# Standard 7-column bucket order (5 maturity + non-interest + total). Buckets
# ≤1y are the first three (used for the 1y cumulative gap).
_BUCKETS_7 = ["lt_1m", "1_3m", "3_12m", "1_5y", "gt_5y", "non_sensitive", "total"]
_LE_1Y = {"lt_1m", "1_3m", "3_12m"}

_ROWS: list[tuple[str, list[str]]] = [
    ("rate_sensitive_assets", [r"^Total\s+assets\b", r"^Toplam\s+Varlıklar\b", r"^Toplam\s+Aktifler\b"]),
    ("rate_sensitive_liab", [r"^Total\s+liabilities\b", r"^Toplam\s+Yükümlülükler\b"]),
    # The reported total repricing gap row (on + off balance).
    ("gap", [r"^Total\s+position\b", r"^Toplam\s+Pozisyon\b", r"^Net\s+position\b"]),
]
_ROW_RX = [(f, [re.compile(p, re.I) for p in pats]) for f, pats in _ROWS]

_PRIOR_RX = re.compile(r"\b(Prior\s+Period|Önceki\s+Dönem|Geçmiş\s+Dönem)\b", re.I)
# Bucket-header signal: a non-interest / non-rate-sensitive column ("Faizsiz" /
# "Non-interest bearing") next to a Total — distinguishes the repricing table
# from the FX one. English convenience translations vary the word order
# ("Non-bearing interest" — Halkbank — vs "Non-interest bearing") and Turkish
# filings vary the phrase ("Faizsiz" / "Faiz Getirmeyen"), so match the whole
# family rather than one fixed order (a fixed "Non-Interest" missed HALKB
# entirely — all 17 quarters — because "bearing" sits between the two words).
_NONINT_RX = re.compile(
    r"(Faizsiz"
    r"|Faiz\s*(?:Getirmeyen|İçermeyen|Taşımayan)"
    r"|Non[\s-]*(?:Interest|Bearing)"
    r"|Interest[\s-]*Free)",
    re.I,
)
_SKIP_PAGES = 20
_MAX_SECTION_PAGES = 6


@dataclass
class RepricingRow:
    period_type: str   # 'current' | 'prior'
    bucket: str        # lt_1m | 1_3m | 3_12m | 1_5y | gt_5y | non_sensitive | total
    rate_sensitive_assets: float | None = None
    rate_sensitive_liab: float | None = None
    gap: float | None = None
    cumulative_gap: float | None = None


@dataclass
class RepricingReport:
    pdf_path: str = ""
    source_page: int | None = None
    rows: list[RepricingRow] = field(default_factory=list)


def _fitz_word_lines(pdf_path: str):
    import fitz
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(len(doc)):
        words = doc[i].get_text("words")
        rows = []
        for w in sorted(words, key=lambda w: (w[1], w[0])):
            if rows and w[1] - rows[-1][0] <= 3.0:
                rows[-1][1].append((w[0], w[4]))
            else:
                rows.append((w[1], [(w[0], w[4])]))
        pages.append([sorted(toks) for _, toks in rows])
    return pages, doc


def _label(tokens) -> str:
    return " ".join(t for _, t in tokens).strip()


def _value_tokens(tokens) -> list[str]:
    return [t for _, t in tokens if t in _NIL or _NUM_TOKEN.match(t)]


def extract_from_pdf(pdf: object = None, pdf_path: str = "") -> RepricingReport:
    # `pdf` (a pdfplumber handle) is accepted for signature parity with the audit
    # lane but unused — parsing is fitz-only via pdf_path.
    rep = RepricingReport(pdf_path=pdf_path)
    if not pdf_path or not _HAS_FITZ:
        return rep
    pages, doc = _fitz_word_lines(pdf_path)
    try:
        n = len(pages)
        _gap_rx = _ROW_RX[2][1]
        _assets_rx = _ROW_RX[0][1]
        # Locate the IR table: a page with the gap row AND a non-interest bucket
        # header (the gap row alone could be a different table; the Faizsiz/
        # Non-Interest header pins it to the repricing schedule).
        start = None
        for i in range(min(_SKIP_PAGES, n), n):
            lns = pages[i]
            has_gap = any(any(rx.match(_label(t)) for rx in _gap_rx) for t in lns)
            has_nonint = any(_NONINT_RX.search(_label(t)) for t in lns)
            if has_gap and has_nonint:
                start = i
                break
        if start is None:
            return rep
        rep.source_page = start + 1

        ncols: int | None = None     # number of bucket columns incl. total
        data: dict[tuple[str, str], dict[str, float | None]] = {}
        period = "current"
        for i in range(start, min(n, start + _MAX_SECTION_PAGES)):
            for tokens in pages[i]:
                lab = _label(tokens)
                if not lab:
                    continue
                if _PRIOR_RX.search(lab):
                    period = "prior"
                for fld, rxs in _ROW_RX:
                    if not any(rx.match(lab) for rx in rxs):
                        continue
                    vals = _value_tokens(tokens)
                    # Lock the column count off the first assets row we see.
                    if ncols is None and fld == "rate_sensitive_assets":
                        ncols = len(vals)
                    if ncols is None or len(vals) != ncols:
                        break
                    # Second assets block w/o a marker ⇒ prior comparative.
                    if fld == "rate_sensitive_assets" and period == "current" \
                            and ("current", "total") in data \
                            and data[("current", "total")].get("rate_sensitive_assets") is not None:
                        period = "prior"
                    buckets = _BUCKETS_7 if ncols == 7 else \
                        [f"b{k+1}" for k in range(ncols - 1)] + ["total"]
                    for bk, tok in zip(buckets, vals):
                        data.setdefault((period, bk), {})[fld] = parse_num(tok)
                    break
    finally:
        doc.close()

    # Build rows + the running cumulative gap (over dated buckets, in order).
    for ptype in ("current", "prior"):
        buckets = _BUCKETS_7 if ncols == 7 else \
            [f"b{k+1}" for k in range((ncols or 1) - 1)] + ["total"]
        run = 0.0
        for bk in buckets:
            fields = data.get((ptype, bk))
            if fields is None:
                continue
            row = RepricingRow(period_type=ptype, bucket=bk, **fields)
            if bk != "total" and row.gap is not None:
                run += row.gap
                row.cumulative_gap = run
            rep.rows.append(row)
    return rep


def extract(pdf_path: str | Path) -> RepricingReport:
    return extract_from_pdf(None, str(pdf_path))


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
_VALUE_COLS = ["rate_sensitive_assets", "rate_sensitive_liab", "gap", "cumulative_gap"]


def upsert(conn: sqlite3.Connection, bank_ticker: str, period: str, kind: str,
           rep: RepricingReport) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_repricing WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    cols = ["bank_ticker", "period", "kind", "period_type", "bucket",
            *_VALUE_COLS, "source_page"]
    ph = ", ".join("?" for _ in cols)
    rows = [(
        bank_ticker, period, kind, r.period_type, r.bucket,
        *[getattr(r, c) for c in _VALUE_COLS], rep.source_page,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            f"INSERT INTO bank_audit_repricing ({', '.join(cols)}) VALUES ({ph})", rows
        )
    conn.commit()
    return len(rows)


def summarize(rep: RepricingReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no interest-rate-risk table found)"
    lines = [f"{Path(rep.pdf_path).name}  (page {rep.source_page})"]
    for r in rep.rows:
        def f(v):
            return f"{v:,.0f}" if v is not None else "-"
        lines.append(
            f"  {r.period_type:<7} {r.bucket:<14} RSA={f(r.rate_sensitive_assets):>16} "
            f"RSL={f(r.rate_sensitive_liab):>16} gap={f(r.gap):>15} cum={f(r.cumulative_gap):>15}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/eye/AKBNK_2024Q4_unconsolidated.pdf"
    print(summarize(extract(path)))
