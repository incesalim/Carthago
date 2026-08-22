#!/usr/bin/env python
"""The narrow lanes audited by the wide ones: every narrow row the graduated
lanes contradict, named.

The narrow lanes (bank_audit_capital, _liquidity, _npl_movement,
_loans_by_sector, _repricing, _fx_position in data/bank_audit.db) were
extracted one figure at a time with no identity of their own. The wide
lanes in data/bank_audit_tables.db are minted only when the regulator's
template arithmetic holds, and they carry the same figures. Where the two
disagree, the wide figure has an identity behind it and the narrow one
does not — so the disagreement is the narrow lane's repair list.

Reads both databases, prints a per-lane summary and writes the full list
to docs/knowledge/<date>-narrow-vs-wide-repair-list.md (gitignored, internal).
Read-only on both databases.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.numbered_template import fold  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"
KNOWLEDGE = REPO / "docs" / "knowledge"


def close(a, b, rel=1e-3, absolute=2.0) -> bool:
    return abs(a - b) <= max(absolute, rel * abs(b))


def audit(tab: sqlite3.Connection, aud: sqlite3.Connection) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = defaultdict(list)

    # --- capital: narrow total_capital / tier1 / cet1 vs the wide capital lane
    wide = {}
    for bank, per, kind, role, val in tab.execute(
            "SELECT bank_ticker, period, kind, row_role, amount FROM bank_audit_capital_full "
            "WHERE row_role IN ('cet1_total','tier1_total','total_own_funds') AND amount IS NOT NULL"):
        wide.setdefault((bank, per, kind, role), val)
    for bank, per, kind, cet1, t1, tot in aud.execute(
            "SELECT bank_ticker, period, kind, cet1_capital, tier1_capital, total_capital "
            "FROM bank_audit_capital WHERE period_type='current'"):
        for role, narrow in (("cet1_total", cet1), ("tier1_total", t1), ("total_own_funds", tot)):
            w = wide.get((bank, per, kind, role))
            if narrow is not None and w is not None and not close(narrow, w):
                out["bank_audit_capital"].append((bank, per, kind, role, narrow, w))

    # --- liquidity: narrow lcr_total / nsfr vs the wide LCR row 23 / NSFR row 34
    lcr = {(b, p, k): v for b, p, k, v in tab.execute(
        "SELECT bank_ticker, period, kind, weighted_total FROM bank_audit_lcr_full "
        "WHERE period_label='current' AND template_row=23 AND weighted_total IS NOT NULL")}
    nsfr = {(b, p, k): v for b, p, k, v in tab.execute(
        "SELECT bank_ticker, period, kind, weighted_total FROM bank_audit_nsfr_full "
        "WHERE period_label='current' AND template_row=34 AND weighted_total IS NOT NULL")}
    for bank, per, kind, n_lcr, n_nsfr in aud.execute(
            "SELECT bank_ticker, period, kind, lcr_total, nsfr FROM bank_audit_liquidity "
            "WHERE period_type='current'"):
        w = lcr.get((bank, per, kind))
        if n_lcr is not None and w is not None and not close(n_lcr, w, rel=5e-3, absolute=0.05):
            out["bank_audit_liquidity.lcr_total"].append((bank, per, kind, "lcr_total", n_lcr, w))
        w = nsfr.get((bank, per, kind))
        if n_nsfr is not None and w is not None and not close(n_nsfr, w, rel=5e-3, absolute=0.05):
            out["bank_audit_liquidity.nsfr"].append((bank, per, kind, "nsfr", n_nsfr, w))

    # --- npl_movement: narrow closing sum (III+IV+V) vs CR1 defaulted loans
    cr1 = {(b, p, k): v for b, p, k, v in tab.execute(
        "SELECT bank_ticker, period, kind, defaulted_gross FROM bank_audit_credit_quality_full "
        "WHERE period_label='current' AND template_row=1 AND defaulted_gross IS NOT NULL")}
    sums: dict[tuple, float] = defaultdict(float)
    for b, p, k, v in aud.execute(
            "SELECT bank_ticker, period, kind, closing_balance FROM bank_audit_npl_movement "
            "WHERE period_type='current' AND closing_balance IS NOT NULL"):
        sums[(b, p, k)] += v
    for key, narrow in sums.items():
        w = cr1.get(key)
        if w is not None and not close(narrow, w):
            out["bank_audit_npl_movement.closing_sum"].append((*key, "closing III+IV+V", narrow, w))

    # --- loans_by_sector: every stage/ECL cell vs the gated wide sector lane
    wide_cells = {}
    for b, p, k, sector, col, v in tab.execute(
            "SELECT bank_ticker, period, kind, sector, column, amount FROM bank_audit_sector_full "
            "WHERE family='stage_ecl' AND period_label='current' AND instance_no=0 "
            "AND column IN ('stage2','stage3','ecl') AND sector IS NOT NULL AND amount IS NOT NULL "
            "ORDER BY page, block_id, row_order, col_order"):
        # the note prints the loan table and then the non-cash one in the same
        # instance, so a sector appears twice; the narrow lane holds the first
        wide_cells.setdefault((b, p, k, sector, col), v)
    # a filing that prints the sector table in SEVERAL blocks (the loan one,
    # the non-cash one, last year's copy) cannot be aligned with a narrow lane
    # that keeps one row per sector, and a comparison that cannot be aligned
    # is not evidence: those filings are skipped rather than indicted
    many = {key for key, n in tab.execute(
        "SELECT bank_ticker || '|' || period || '|' || kind, COUNT(DISTINCT page || ':' || block_id) "
        "FROM bank_audit_sector_full WHERE family='stage_ecl' AND period_label='current' "
        "GROUP BY 1 HAVING COUNT(DISTINCT page || ':' || block_id) > 1")}
    wide_cells = {kk: v for kk, v in wide_cells.items()
                  if f"{kk[0]}|{kk[1]}|{kk[2]}" not in many}
    for b, p, k, sector, s2, s3, e in aud.execute(
            "SELECT bank_ticker, period, kind, sector, stage2_amount, stage3_amount, ecl_amount "
            "FROM bank_audit_loans_by_sector WHERE period_type='current'"):
        for col, narrow in (("stage2", s2), ("stage3", s3), ("ecl", e)):
            w = wide_cells.get((b, p, k, sector, col))
            if narrow is not None and w is not None and not close(narrow, w):
                out["bank_audit_loans_by_sector"].append((b, p, k, f"{sector}.{col}", narrow, w))

    # --- repricing: narrow rate-sensitive assets per bucket vs the wide total-assets row
    bucket_of = {"m1": ("1 AY", "1 MONTH", "UP TO 1"), "m1_3": ("1-3",), "m3_12": ("3-12",),
                 "y1_5": ("1-5",), "y5_plus": ("5 Y", "OVER 5"), "non_interest": ("FAIZSIZ", "NON", "INTEREST")}
    wide_rp = {}
    for b, p, k, band, v in tab.execute(
            "SELECT bank_ticker, period, kind, band, amount FROM bank_audit_section4_matrix_full "
            "WHERE family='repricing' AND period_label='current' AND instance_no=0 "
            "AND row_role='total_assets' AND amount IS NOT NULL"):
        wide_rp[(b, p, k, band)] = v
    for b, p, k, bucket, ta in aud.execute(
            "SELECT bank_ticker, period, kind, bucket, rate_sensitive_assets FROM bank_audit_repricing "
            "WHERE period_type='current' AND rate_sensitive_assets IS NOT NULL"):
        fb = fold(bucket or "")
        band = next((bd for bd, needles in bucket_of.items() if any(n in fb for n in needles)), None)
        w = wide_rp.get((b, p, k, band)) if band else None
        if w is not None and not close(ta, w):
            out["bank_audit_repricing.rate_sensitive_assets"].append((b, p, k, bucket, ta, w))

    # --- fx_position: narrow on-balance assets per currency vs the wide total-assets row
    wide_fx = {}
    for b, p, k, band, v in tab.execute(
            "SELECT bank_ticker, period, kind, band, amount FROM bank_audit_section4_matrix_full "
            "WHERE family='fx_position' AND period_label='current' AND instance_no=0 "
            "AND row_role='total_assets' AND amount IS NOT NULL"):
        wide_fx[(b, p, k, band)] = v
    for b, p, k, cur, ta in aud.execute(
            "SELECT bank_ticker, period, kind, currency, on_bs_assets FROM bank_audit_fx_position "
            "WHERE period_type='current' AND on_bs_assets IS NOT NULL"):
        c = fold(cur or "")
        band = ("eur" if "EUR" in c or "AVRO" in c else "usd" if "USD" in c or "DOLAR" in c
                else "other_fc" if "DIGER" in c or "OTHER" in c else "total" if "TOPLAM" in c or "TOTAL" in c
                else None)
        w = wide_fx.get((b, p, k, band)) if band else None
        if w is not None and not close(ta, w):
            out["bank_audit_fx_position.on_bs_assets"].append((b, p, k, cur, ta, w))

    # --- npl_movement, every cell: the wide movement table per group
    gmap = {"III": "group_iii", "IV": "group_iv", "V": "group_v"}
    wide_npl = {}
    for b, p, k, role, g, v in tab.execute(
            "SELECT bank_ticker, period, kind, row_role, npl_group, amount FROM bank_audit_npl_movement_full "
            "WHERE period_label='current' AND instance_no=0 AND amount IS NOT NULL "
            "AND row_role IN ('opening','additions','transfers_in','transfers_out','collections',"
            "'write_offs','sold','closing','provision','net')"):
        wide_npl.setdefault((b, p, k, role, g), v)
    cols = {"opening": "opening_balance", "additions": "additions", "transfers_in": "transfers_in",
            "transfers_out": "transfers_out", "collections": "collections", "write_offs": "write_offs",
            "sold": "sold", "closing": "closing_balance", "provision": "provision", "net": "net_balance"}
    sel = ", ".join(cols.values())
    for row in aud.execute(
            f"SELECT bank_ticker, period, kind, group_code, {sel} FROM bank_audit_npl_movement "
            "WHERE period_type='current'"):
        b, p, k, gc, *vals = row
        g = gmap.get((gc or "").strip().upper())
        if not g:
            continue
        for role, narrow in zip(cols, vals):
            w = wide_npl.get((b, p, k, role, g))
            if narrow is not None and w is not None and not close(narrow, w):
                out["bank_audit_npl_movement"].append((b, p, k, f"{g}.{role}", narrow, w))

    # --- the statement lines behind the breakdown notes: a gated note total
    # the TFRS 9 stage balances: the narrow lane keeps three numbers per
    # filing, the wide movement table derives the same three from a
    # roll-forward that had to close. The gross-loan instances only —
    # the ECL ones are provisions, not balances.
    wide_stage: dict[tuple, dict[str, float]] = defaultdict(dict)
    for b, p_, k, band, v in tab.execute(
            "SELECT bank_ticker, period, kind, band, amount FROM bank_audit_stage_movement_full "
            "WHERE row_role='closing' AND measure='gross_loans' AND subject='loans' AND instance_no=0 "
            "AND band IN ('stage1','stage2','stage3') AND amount IS NOT NULL"):
        wide_stage[(b, p_, k)].setdefault(band, v)
    for b, p_, k, s1, s2, s3 in aud.execute(
            "SELECT bank_ticker, period, kind, stage1_amount, stage2_amount, stage3_amount "
            "FROM bank_audit_stages WHERE period_type='current'"):
        w = wide_stage.get((b, p_, k))
        if not w:
            continue
        for band, narrow in (("stage1", s1), ("stage2", s2), ("stage3", s3)):
            wv = w.get(band)
            if narrow is None or wv is None or close(narrow, wv):
                continue
            out["bank_audit_stages"].append((b, p_, k, band, narrow, wv))

    #     that meets no narrow line is a narrow line wrong or missing
    statements = {
        ("bank_audit_tl_fc_note_full", "interest_on_loans"): ("pl", r"^KREDILERDEN ALINAN FAIZ|^INTEREST (INCOME )?(ON|FROM) LOANS"),
        ("bank_audit_tl_fc_note_full", "interest_from_banks"): ("pl", r"^BANKALARDAN ALINAN FAIZ|^INTEREST (INCOME )?(ON|FROM) BANKS|^INTEREST RECEIVED FROM BANKS"),
        ("bank_audit_tl_fc_note_full", "interest_on_securities"): ("pl", r"^MENKUL DEGERLERDEN ALINAN FAIZ|^INTEREST (INCOME )?(ON|FROM) (MARKETABLE )?SECURITIES"),
        ("bank_audit_tl_fc_note_full", "interest_on_borrowings"): ("pl", r"^KULLANILAN KREDILERE VERILEN FAIZ|^INTEREST (EXPENSE )?ON (FUNDS )?BORROW|^INTEREST (PAID )?ON LOANS"),
        ("bank_audit_tl_fc_note_full", "funds_borrowed"): ("bs", r"^ALINAN KREDILER|^FUNDS BORROWED|^BORROWINGS"),
        ("bank_audit_tl_fc_note_full", "cash_and_cbrt"): ("bs", r"^NAKIT DEGERLER VE MERKEZ|^CASH AND (BALANCES WITH|CASH EQUIVALENTS AND)? ?(THE )?CENTRAL|^CASH AND BALANCES"),
        ("bank_audit_tl_fc_note_full", "securities_issued"): ("bs", r"^IHRAC EDILEN MENKUL|^(MARKETABLE |DEBT )?SECURITIES ISSUED|^ISSUED (MARKETABLE |DEBT )?SECURITIES|^BONDS ISSUED"),
        ("bank_audit_two_period_note_full", "letters_of_guarantee"): ("off_balance", r"^TEMINAT MEKTUPLARI$|^LETTERS? OF GUARANTEES?$"),
        ("bank_audit_two_period_note_full", "trading_income"): ("pl", r"^TICARI KAR|^TRADING (INCOME|PROFIT|GAIN)|^NET TRADING"),
    }
    # the derivatives note's own total against the balance sheet's derivative
    # line — two independent captures of the same figure
    deriv = {
        "assets": r"^ALIM SATIM AMACLI TUREV ?FINANSAL (ARACLAR|VARLIK)|"
                  r"^DERIVATIVE FINANCIAL ASSETS( (HELD FOR TRADING|AT FAIR VALUE THROUGH PROFIT))?$",
        "liabilities": r"^ALIM SATIM AMACLI TUREV FINANSAL (BORCLAR|YUKUMLULUK)|"
                       r"^DERIVATIVE FINANCIAL LIABILITIES( HELD FOR TRADING)?$",
    }
    pl_rows: dict[tuple, list] = defaultdict(list)
    for b, p, k, name, v in aud.execute("SELECT bank_ticker, period, kind, item_name, amount FROM bank_audit_profit_loss"):
        if v is not None:
            pl_rows[(b, p, k)].append((fold(name or "").strip(), v))
    bs_rows: dict[tuple, list] = defaultdict(list)
    for b, p, k, st, name, v in aud.execute(
            "SELECT bank_ticker, period, kind, statement, item_name, amount_total FROM bank_audit_balance_sheet"):
        if v is not None:
            bs_rows[(b, p, k, st)].append((fold(name or "").strip(), v))
    import re as _re
    foot = _re.compile(r"(\s+[-–]?\s*[IVXA-Z0-9.(),]{1,8})+$")
    for (table, fam), (st, rx) in statements.items():
        rx_c = _re.compile(rx)
        if table == "bank_audit_tl_fc_note_full":
            q = ("SELECT bank_ticker, period, kind, COALESCE(tl_current,0)+COALESCE(fc_current,0) FROM "
                 f"{table} WHERE family=? AND row_role='total' AND instance_no=0 "
                 "AND (tl_current IS NOT NULL OR fc_current IS NOT NULL)")
        else:
            q = (f"SELECT bank_ticker, period, kind, current FROM {table} WHERE family=? AND row_role='total' "
                 "AND instance_no=0 AND current IS NOT NULL")
        for b, p, k, wv in tab.execute(q, (fam,)):
            rows = pl_rows.get((b, p, k), []) if st == "pl" else bs_rows.get((b, p, k, st if st != "bs" else "liabilities"), []) + \
                (bs_rows.get((b, p, k, "assets"), []) if st == "bs" else [])
            cands = [v for name, v in rows if rx_c.search(name) or rx_c.search(foot.sub("", name))]
            if not cands:
                continue                           # no narrow line at all: a gap, not a contradiction
            if not any(close(wv, v) for v in cands):
                out[f"{fam} (narrow statement line)"].append((b, p, k, f"{fam}.total", cands[0], wv))

    # the securities note's total per measurement portfolio against the
    # balance sheet's line for that portfolio. "Türev" first: the derivative
    # lines carry the same words and are a different asset
    import re as _re2
    _NOT_SEC = _re2.compile(r"^TUREV|^DERIVATIVE")
    portfolios = {
        "fvtpl": r"^(FINANSAL VARLIKLAR )?GERCEGE UYGUN DEGER FARKI KAR ?[/ ]?ZARARA YANSITILAN|"
                 r"^FINANCIAL ASSETS (AT|MEASURED AT) FAIR VALUE THROUGH PROFIT",
        "fvoci": r"^(FINANSAL VARLIKLAR )?GERCEGE UYGUN DEGER FARKI DIGER KAPSAMLI GELIRE YANSITILAN|"
                 r"^FINANCIAL ASSETS (AT|MEASURED AT) FAIR VALUE THROUGH OTHER COMPREHENSIVE",
        "amortised_cost": r"^ITFA EDILMIS MALIYETI ILE OLCULEN FINANSAL VARLIKLAR|"
                          r"^FINANCIAL ASSETS MEASURED AT AMORTI[SZ]ED COST",
    }
    for portfolio, rx in portfolios.items():
        rx_c = _re2.compile(rx)
        for b, p, k, wv in tab.execute(
                "SELECT bank_ticker, period, kind, current FROM bank_audit_securities_full "
                "WHERE portfolio=? AND item_role='total' AND instance_no=0 AND current IS NOT NULL",
                (portfolio,)):
            rows = bs_rows.get((b, p, k, "assets"), [])
            cands = [v for name, v in rows
                     if not _NOT_SEC.search(name)
                     and (rx_c.search(name) or rx_c.search(foot.sub("", name)))]
            if not cands or any(close(wv, v) for v in cands):
                continue
            out[f"securities.{portfolio} (narrow balance-sheet line)"].append(
                (b, p, k, f"securities.{portfolio}", cands[0], wv))

    # the deposit-maturity matrix's grand total against the balance sheet's
    # deposits line — the same figure captured from two pages
    _DEPOSITS_BS = _re2.compile(r"^MEVDUAT$|^MEVDUAT \(|^DEPOSITS?$|^DEPOSITS? \(|^TOPLANAN FONLAR")
    # the matrix prints a total row per section (savings, commercial, banks…)
    # and one for the whole table; the grand total is the largest of them
    dep_total: dict[tuple, float] = {}
    for b, p, k, v in tab.execute(
            "SELECT bank_ticker, period, kind, MAX(amount) FROM bank_audit_deposit_maturity_full "
            "WHERE row_role='total' AND band='total' AND period_label='current' AND measure='balance' "
            "AND amount IS NOT NULL GROUP BY bank_ticker, period, kind"):
        dep_total[(b, p, k)] = v
    for (b, p, k), wv in dep_total.items():
        rows = bs_rows.get((b, p, k, "liabilities"), [])
        cands = [v for name, v in rows if _DEPOSITS_BS.search(name) or _DEPOSITS_BS.search(foot.sub("", name))]
        if not cands or any(close(wv, v) for v in cands):
            continue
        out["deposit_maturity (narrow balance-sheet line)"].append(
            (b, p, k, "deposits.total", cands[0], wv))

    # two WIDE lanes on the same number: the own-funds note's total RWA and
    # the OV1 form's. Both are gated, and they are captured from different
    # pages of the same filing
    ov1: dict[tuple, float] = {}
    for b, p, k, v in tab.execute(
            "SELECT bank_ticker, period, kind, rwa FROM bank_audit_rwa_full "
            "WHERE row_role='total_rwa' AND period_label='current' AND rwa IS NOT NULL"):
        ov1.setdefault((b, p, k), v)
    for b, p, k, wv in tab.execute(
            "SELECT bank_ticker, period, kind, amount FROM bank_audit_capital_full "
            "WHERE row_role='total_rwa' AND amount IS NOT NULL"):
        other = ov1.get((b, p, k))
        if other is None or close(wv, other):
            continue
        out["capital.total_rwa vs the OV1 form (wide vs wide)"].append(
            (b, p, k, "total_rwa", other, wv))

    for ctx, rx in deriv.items():
        rx_c = _re2.compile(rx)
        st = "assets" if ctx == "assets" else "liabilities"
        for b, p, k, tl, fc in tab.execute(
                "SELECT bank_ticker, period, kind, current_tl, current_fc FROM bank_audit_derivative_full "
                "WHERE context=? AND row_role='total' AND instance_no=0", (ctx,)):
            if tl is None and fc is None:
                continue
            wv = (tl or 0.0) + (fc or 0.0)
            rows = bs_rows.get((b, p, k, st), [])
            cands = [v for name, v in rows if rx_c.search(name) or rx_c.search(foot.sub("", name))]
            if not cands or any(close(wv, v) for v in cands):
                continue
            out[f"derivative.{ctx} (narrow balance-sheet line)"].append(
                (b, p, k, f"derivative.{ctx}", cands[0], wv))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--no-write", action="store_true", help="print only; no knowledge file")
    args = ap.parse_args()
    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    aud = sqlite3.connect(f"file:{args.audit_db}?mode=ro", uri=True)
    found = audit(tab, aud)

    lines = [f"# Narrow lanes audited by the wide lanes — {date.today().isoformat()}", "",
             "Status: repair list (open). Generated by `scripts/audit_narrow_vs_wide.py`;",
             "read-only on both databases. Each row: a narrow figure a gated wide lane",
             "contradicts. The wide figure has the template's identity behind it; the",
             "narrow one has none. Tolerance 0.1% (ratios 0.5%).", ""]
    total = 0
    for lane in sorted(found):
        rows = found[lane]
        total += len(rows)
        print(f"{lane:48} {len(rows):5} rows indicted")
        lines += [f"## {lane} — {len(rows)} rows", "", "| bank | period | kind | what | narrow | wide |",
                  "|---|---|---|---|---:|---:|"]
        for b, p, k, what, n, w in sorted(rows):
            lines.append(f"| {b} | {p} | {k} | {what} | {n:,.2f} | {w:,.2f} |")
        lines.append("")
    print(f"{'total':48} {total:5}")
    if not args.no_write:
        KNOWLEDGE.mkdir(exist_ok=True)
        path = KNOWLEDGE / f"{date.today().isoformat()}-narrow-vs-wide-repair-list.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
