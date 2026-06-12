"""Diagnostic: dump a (bank, period, kind) statement with the raw PDF lines that
produced each row, and show where the identity checks break. Read-only.

  python scripts/diag_partition.py BANK PERIOD KIND [assets|liabilities] [--pdf]
"""
import sys, os, tempfile
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
from src.audit_reports import r2_storage
from src.audit_reports.extractor import extract, _locate_pages, extract_page_text_repaired, _fitz_merge_rows
import pdfplumber

bank, period, kind = sys.argv[1], sys.argv[2], sys.argv[3]
want_stmt = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("-") else None
show_pdf = "--pdf" in sys.argv

conn = sqlite3.connect("data/bank_audit.db")
print(f"== DB rows for {bank} {period} {kind} ==")
for stmt in (["assets", "liabilities"] if not want_stmt else [want_stmt]):
    rows = conn.execute(
        "SELECT item_order, hierarchy, item_name, amount_tl, amount_fc, amount_total "
        "FROM bank_audit_balance_sheet WHERE bank_ticker=? AND period=? AND kind=? "
        "AND statement=? ORDER BY item_order", (bank, period, kind, stmt)).fetchall()
    print(f"\n--- {stmt} ({len(rows)} rows) ---")
    romansum = 0.0
    for o, h, nm, tl, fc, tot in rows:
        is_roman = h and all(ch in "IVX." for ch in h)
        flag = ""
        if tl is not None and fc is not None and tot is not None and abs((tl+fc)-tot) > max(3, abs(tot)*1e-5):
            flag = " <<TL+FC≠TOT"
        if is_roman and tot is not None:
            romansum += tot
        print(f"  {o:3} {h:8} {(nm or '')[:46]:46} {str(tl):>14} {str(fc):>14} {str(tot):>14}{flag}")
    print(f"  Σromans={romansum:,.0f}")

if show_pdf:
    key = f"{bank.lower()}/{bank}_{period}_{kind}.pdf"
    dest = os.path.join(tempfile.gettempdir(), f"diag_{bank}_{period}_{kind}.pdf")
    if not os.path.exists(dest):
        r2_storage.download_to(key, dest)
    with pdfplumber.open(dest) as pdf:
        loc = _locate_pages(pdf)
        print(f"\n== PDF pages: {loc} ==")
        for st, pkey in (("assets", "bs_assets"), ("liabilities", "bs_liab")):
            if want_stmt and st != want_stmt:
                continue
            if pkey not in loc:
                continue
            text = extract_page_text_repaired(pdf.pages[loc[pkey]-1])
            print(f"\n--- raw {st} page lines ---")
            for ln in _fitz_merge_rows(text, 6).split("\n"):
                if ln.strip():
                    print("  ", repr(ln[:120]))
