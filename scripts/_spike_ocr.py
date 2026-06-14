"""SPIKE (throwaway): does re-OCR'ing a failing equity page recover enough that
the chain validates? Render the located page to an image, OCR it (PaddleOCR,
bypassing the corrupted text layer), feed the OCR'd lines through the PRODUCTION
parser (by monkeypatching the page readers), and validate exactly like production.

Go/no-go: how many of the sample NEWLY pass where the text-layer reader failed.

  python scripts/_spike_ocr.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

import fitz  # noqa: E402
from src.audit_reports import r2_storage  # noqa: E402
from src.audit_reports import extractor as ex  # noqa: E402
from src.audit_reports import equity_change as ec  # noqa: E402
from src.audit_reports import validator as v  # noqa: E402
import pdfplumber  # noqa: E402

DB = REPO / "data" / "bank_audit.db"

# (bank, period, kind, target, failure_type) — target 'equity' or 'oci'
SAMPLE = [
    ("ISCTR", "2025Q2", "consolidated",   "equity", "letter-spacing"),
    ("HSBC",  "2025Q1", "consolidated",   "equity", "missing-col"),
    ("HSBC",  "2025Q1", "unconsolidated", "equity", "missing-col"),
    ("ANADOLU", "2025Q1", "unconsolidated", "equity", "chain"),
    ("ING",   "2026Q1", "consolidated",   "equity", "chain"),
    ("ICBCT", "2025Q1", "consolidated",   "equity", "over"),
    ("ALNTF", "2025Q1", "consolidated",   "equity", "content"),
    ("TSKB",  "2025Q2", "consolidated",   "equity", "partial"),
    ("TEB",   "2025Q1", "unconsolidated", "oci",    "oci-lane"),
    ("YKBNK", "2025Q1", "consolidated",   "oci",    "oci-lane"),
]

# Partitions whose full OCR line reconstruction is dumped for diagnosis.
DUMP = {("ISCTR", "2025Q2", "consolidated"), ("HSBC", "2025Q1", "consolidated")}

# --- OCR (RapidOCR = PP-OCR models on onnxruntime; no paddle/torch) ---------
_OCR = None


def _ocr_engine():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def _ocr_raw(img_path: str):
    """Return list of (x0, y0, text) for every detected text box."""
    eng = _ocr_engine()
    res, _elapse = eng(img_path)
    boxes = []
    for item in (res or []):
        box, text = item[0], item[1]
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        boxes.append((float(min(xs)), float(min(ys)), text))
    return boxes


def _lines_from_boxes(boxes, y_tol=8):
    """Y-bucket boxes into visual rows (same idea as fitz y-bucketing)."""
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    rows = defaultdict(list)
    last_y = None
    key = None
    for x0, y0, text in boxes:
        if last_y is None or abs(y0 - last_y) > y_tol:
            key = y0
            last_y = y0
        rows[key].append((x0, text))
    out = []
    for y in sorted(rows):
        cells = sorted(rows[y], key=lambda t: t[0])
        out.append(" ".join(t for _x, t in cells))
    return out


def ocr_page_lines(pdf_path: str, page_idx_0: int, dpi=250) -> list[str]:
    doc = fitz.open(pdf_path)
    pix = doc[page_idx_0].get_pixmap(dpi=dpi)
    doc.close()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "page.png"
        pix.save(str(p))
        boxes = _ocr_raw(str(p))
    return _lines_from_boxes(boxes)


# --- validation helpers (mirror revalidate_partition) ----------------------
_EQ_COLS = ("hierarchy", "item_name", "period_type", "paid_in_capital", "share_premium",
            "share_cancellation_profits", "other_capital_reserves",
            "oci_not_reclassified_1", "oci_not_reclassified_2", "oci_not_reclassified_3",
            "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
            "profit_reserves", "prior_period_profit_loss", "period_net_profit_loss",
            "total_equity", "minority_interest", "total_equity_incl_minority")


def _rows_to_dicts(rows):
    out = []
    for r in rows:
        out.append({
            "hierarchy": r.hierarchy, "item_name": r.name, "period_type": r.period_type,
            "paid_in_capital": r.paid_in_capital, "share_premium": r.share_premium,
            "share_cancellation_profits": r.share_cancellation_profits,
            "other_capital_reserves": r.other_capital_reserves,
            "oci_not_reclassified_1": r.oci_not_reclassified_1,
            "oci_not_reclassified_2": r.oci_not_reclassified_2,
            "oci_not_reclassified_3": r.oci_not_reclassified_3,
            "oci_reclassified_1": r.oci_reclassified_1,
            "oci_reclassified_2": r.oci_reclassified_2,
            "oci_reclassified_3": r.oci_reclassified_3,
            "profit_reserves": r.profit_reserves,
            "prior_period_profit_loss": r.prior_period_profit_loss,
            "period_net_profit_loss": r.period_net_profit_loss,
            "total_equity": r.total_equity, "minority_interest": r.minority_interest,
            "total_equity_incl_minority": r.total_equity_incl_minority,
        })
    return out


def _db_rows(conn, b, p, k, table, cols):
    return [dict(zip(cols, r)) for r in conn.execute(
        f"SELECT {','.join(cols)} FROM {table} WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY item_order", (b, p, k))]


def run_one(conn, b, p, k, target, ftype):
    key = r2_storage.make_key(b, p, k)
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "x.pdf"
        r2_storage.download_to(key, dest)
        P = str(dest)
        pdf = pdfplumber.open(P)
        loc = ex._locate_pages(pdf)
        pl = loc.get("pl")
        oci_pg = ex._locate_oci_page(pdf, pl)
        eqp = ec._locate_equity_pages(pdf, P, oci_pg or pl)
        try:
            pdf.stream.close()
        except Exception:
            pass

        if target == "oci":
            # lighter check: OCR the OCI page, print roman III value
            if not oci_pg:
                return (b, p, k, ftype, "no-oci-page", "")
            lines = ocr_page_lines(P, oci_pg - 1)
            samp = " | ".join(ln for ln in lines if any(c.isdigit() for c in ln))[:160]
            return (b, p, k, ftype, "OCI-OCR (eyeball)", samp)

        if not eqp:
            return (b, p, k, ftype, "no-eq-page", "")

        # OCR each equity page, monkeypatch readers to feed OCR into the parser
        ocr_by_page = {pg: ocr_page_lines(P, pg - 1) for pg, _pt in eqp}
        if (b, p, k) in DUMP:
            pg0 = eqp[0][0]
            print(f"\n--- OCR lines for {b} {p} {k} page {pg0} ({len(ocr_by_page[pg0])} lines) ---", flush=True)
            for ln in ocr_by_page[pg0]:
                print("   |", ln[:115], flush=True)
            print("--- end OCR lines ---\n", flush=True)
        real_srt, real_fpt, real_fpl = ec._safe_repaired_text, ec._fitz_page_text, ec._fitz_page_lines

        def patched_srt(path, idx1, timeout=35.0):
            return "\n".join(ocr_by_page[idx1]) if idx1 in ocr_by_page else real_srt(path, idx1, timeout)

        def patched_fpt(path, idx0):
            return "\n".join(ocr_by_page[idx0 + 1]) if (idx0 + 1) in ocr_by_page else real_fpt(path, idx0)

        def patched_fpl(path, idx0):
            return list(ocr_by_page[idx0 + 1]) if (idx0 + 1) in ocr_by_page else real_fpl(path, idx0)

        rows = []
        try:
            ec._safe_repaired_text = patched_srt
            ec._fitz_page_text = patched_fpt
            ec._fitz_page_lines = patched_fpl
            first_lines = ocr_by_page[eqp[0][0]]
            n_cols = ec._modal_ncols(first_lines)
            for pg, pt in eqp:
                rows.extend(ec._parse_equity_page(P, pg, pt, n_cols))
        finally:
            ec._safe_repaired_text, ec._fitz_page_text, ec._fitz_page_lines = real_srt, real_fpt, real_fpl

    eq = _rows_to_dicts(rows)
    liab = _db_rows(conn, b, p, k, "bank_audit_balance_sheet", None) if False else [
        dict(zip(("hierarchy", "item_name", "amount_tl", "amount_fc", "amount_total"), r))
        for r in conn.execute("SELECT hierarchy,item_name,amount_tl,amount_fc,amount_total "
                              "FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? AND kind=? "
                              "AND statement='liabilities' ORDER BY item_order", (b, p, k))]
    oci = [dict(zip(("hierarchy", "item_name", "amount"), r)) for r in conn.execute(
        "SELECT hierarchy,item_name,amount FROM bank_audit_oci WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY item_order", (b, p, k))]
    res = v.check_equity_change(eq, oci_rows=oci, liabilities=liab, period=p)
    # A REAL pass = the chain checks actually ran AND passed (not skipped because
    # OCR produced no rows). 0-row results are NO-ROWS, never PASS.
    if len(rows) < 4:
        status = "NO-ROWS"
    elif res.failed == 0 and res.passed > 0:
        status = "PASS"
    else:
        status = "FAIL:" + (res.failures[0].get("check", "?") if res.failures else "skip")
    ol = ocr_by_page[eqp[0][0]]
    nwide = sum(1 for ln in ol if ec._count_value_tokens(ln) >= 8)
    samp = next((ln for ln in ol if ec._count_value_tokens(ln) >= 8), "")
    detail = (f"rows={len(rows)} ocrlines={len(ol)} wide={nwide} "
              f"P{res.passed}/F{res.failed} | {samp[:72]}")
    return (b, p, k, ftype, status, detail)


def main():
    if not DB.exists():  # on CI the audit DB lives in R2, not the repo
        from scripts.audit_d1 import pull_snapshot
        pull_snapshot(guard=False)
    conn = sqlite3.connect(str(DB))
    print(f"{'bank':8} {'period':7} {'kind':5} {'failtype':14} {'OCR-result':18} detail")
    print("-" * 100)
    npass = 0
    for b, p, k, target, ftype in SAMPLE:
        try:
            b_, p_, k_, ft, status, detail = run_one(conn, b, p, k, target, ftype)
        except Exception as e:  # noqa: BLE001
            status, detail = f"ERR:{type(e).__name__}", str(e)[:80]
        if status == "PASS":
            npass += 1
        print(f"{b:8} {p:7} {k[:5]:5} {ftype:14} {status:18} {detail}", flush=True)
    eq_total = sum(1 for *_, t, _ in SAMPLE if t == "equity")
    print("-" * 100)
    print(f"equity cases newly PASS via OCR: {npass}/{eq_total}")


if __name__ == "__main__":
    main()
