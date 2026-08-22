#!/usr/bin/env python
"""The TL/FC notes graduation: the small NOTES-section tables printed as
items × (TL, FC) × (current, prior), each a breakdown of one statement
line — minted from the document layer under a family registry:

  interest_on_loans        short-term, medium/long-term, NPL interest, fund
                           premiums        → P&L interest on loans
  interest_from_banks      CBRT, domestic banks, foreign banks, branches
                           abroad          → P&L interest from banks
  interest_on_securities   FVTPL, FVOCI, amortised cost
                                           → P&L interest on securities
  interest_on_borrowings   banks (CBRT, domestic, foreign, branches abroad),
                           other institutions
                                           → P&L interest on funds borrowed
  funds_borrowed           CBRT loans, domestic banks and institutions,
                           foreign banks, funds
                                           → BS funds borrowed
  funds_borrowed_maturity  short-term, medium/long-term
                                           → BS funds borrowed
  cash_and_cbrt            cash, CBRT, other
                                           → BS cash and balances with CBRT
  cbrt_accounts            unrestricted demand / time, restricted time,
                           reserve requirement
                                           → the cash note's CBRT row (wide vs wide)
  securities_issued        bills, asset-backed securities, bonds
                                           → BS securities issued
  subordinated_debt        AT1-eligible (loans, instruments), Tier 2-eligible
                           (loans, instruments)
                                           → BS subordinated debt

Families tried and dropped for want of an anchor: the balance-sheet banks
note, FVTPL securities by type, hedging derivatives by hedge type — their
first rows admit other tables and the statement lines did not confirm them.

The balance-sheet "banks" note prints the interest-from-banks rows under
the assets section; it anchors to nothing the narrow lanes hold and is
left unminted (the contents item the block sits under tells them apart).

Rows carry a registry role (with a parent where the note nests: the
borrowings note's "to banks" heads four sub-rows); the label is kept.
MINT GATE: total = Σ top-level rows and head = Σ its children, on the
current TL and FC columns. Anchor, dry-run (default): current TL + FC of
the total vs the family's narrow statement line (bank_audit_profit_loss /
bank_audit_balance_sheet, same filing).

`--write` stores into bank_audit_tl_fc_note_full in
data/bank_audit_tables.db (local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402
from src.audit_reports import numbered_template as NT  # noqa: E402
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

R = re.compile
# family -> (statement, narrow item regex, [(role, parent, label regex)])
FAMILIES: dict[str, tuple[str, re.Pattern, list[tuple[str, str | None, re.Pattern]]]] = {
    "interest_on_loans": ("pl", R(r"^KREDILERDEN ALINAN FAIZ|^INTEREST (INCOME )?(ON|FROM) LOANS"), [
        ("short_term", None, R(r"^KISA VADELI|^SHORT.?TERM")),
        ("medium_long_term", None, R(r"^ORTA VE UZUN|^MEDIUM|^LONG.?TERM")),
        ("npl_interest", None, R(r"^TAKIPTEKI|^INTEREST ON (NON.?PERFORMING|NPL|LOANS UNDER FOLLOW)")),
        ("fund_premiums", None, R(r"^KAYNAK KUL|^PREMIUMS? (RECEIVED )?FROM|^RESOURCE UTILI")),
    ]),
    "interest_from_banks": ("pl", R(r"^BANKALARDAN ALINAN FAIZ|^INTEREST (INCOME )?(ON|FROM) BANKS|^INTEREST RECEIVED FROM BANKS"), [
        ("cbrt", None, R(r"^T\.?C\.? ?MERKEZ BANKASINDAN|^TCMB|^CBRT|^(FROM )?(THE )?CENTRAL BANK")),
        ("domestic_banks", None, R(r"^YURT ?ICI BANKALAR|^DOMESTIC BANK")),
        ("foreign_banks", None, R(r"^YURT ?DISI BANKALAR|^FOREIGN BANK")),
        ("branches_abroad", None, R(r"^YURT ?DISI MERKEZ|^(FOREIGN |ABROAD )?(HEAD.?OFFICE|BRANCHES)")),
    ]),
    "interest_on_securities": ("pl", R(r"^MENKUL DEGERLERDEN ALINAN FAIZ|^INTEREST (INCOME )?(ON|FROM) (MARKETABLE )?SECURITIES"), [
        ("fvtpl", None, R(r"^GERCEGE UYGUN DEGER FARKI KAR|^FINANCIAL ASSETS AT FAIR VALUE THROUGH PROFIT|^ALIM SATIM|^TRADING|^FVTPL")),
        ("fvoci", None, R(r"^GERCEGE UYGUN DEGER FARKI DIGER|^FINANCIAL ASSETS AT FAIR VALUE THROUGH OTHER|^SATILMAYA HAZIR|^AVAILABLE|^FVOCI")),
        ("amortised_cost", None, R(r"^ITFA EDILMIS|^AMORTI[SZ]ED|^FINANCIAL ASSETS (MEASURED )?AT AMORTI|^VADEYE KADAR|^HELD.?TO")),
    ]),
    "interest_on_borrowings": ("pl", R(r"^KULLANILAN KREDILERE VERILEN FAIZ|^INTEREST (EXPENSE )?ON (FUNDS )?BORROW|^INTEREST (PAID )?ON LOANS"), [
        ("banks", None, R(r"^BANKALARA$|^BANKS$|^TO BANKS|^BANKALARA\b")),
        ("cbrt", "banks", R(r"^T\.?C\.? ?MERKEZ BANKASINA|^TCMB|^CBRT|^(TO )?(THE )?CENTRAL BANK")),
        ("domestic_banks", "banks", R(r"^YURT ?ICI BANKALARA|^DOMESTIC BANK")),
        ("foreign_banks", "banks", R(r"^YURT ?DISI BANKALARA|^FOREIGN BANK")),
        ("branches_abroad", "banks", R(r"^YURT ?DISI MERKEZ|^(FOREIGN |ABROAD )?(HEAD.?OFFICE|BRANCHES)")),
        ("other_institutions", None, R(r"^DIGER KURULUS|^OTHER (FINANCIAL )?INSTITUTION|^OTHER$")),
    ]),
    "funds_borrowed": ("bs", R(r"^ALINAN KREDILER|^FUNDS BORROWED|^BORROWINGS"), [
        ("cbrt_loans", None, R(r"^T\.?C\.? ?MERKEZ BANKASI KREDI|^(FROM )?(THE )?CENTRAL BANK|^CBRT|^TCMB")),
        ("domestic", None, R(r"^YURT ?ICI BANKA|^(FROM )?DOMESTIC (BANKS|INSTITUTIONS)")),
        ("foreign", None, R(r"^YURT ?DISI BANKA|^(FROM )?FOREIGN (BANKS|INSTITUTIONS)")),
        ("funds", None, R(r"^FONLAR|^FUNDS$|^FROM FUNDS")),
    ]),
    "funds_borrowed_maturity": ("bs", R(r"^ALINAN KREDILER|^FUNDS BORROWED|^BORROWINGS"), [
        ("short_term", None, R(r"^KISA VADELI|^SHORT.?TERM")),
        ("medium_long_term", None, R(r"^ORTA VE UZUN|^MEDIUM|^LONG.?TERM")),
    ]),
    "cash_and_cbrt": ("bs", R(r"^NAKIT DEGERLER VE MERKEZ|^CASH AND (BALANCES WITH|CASH EQUIVALENTS AND)? ?(THE )?CENTRAL|^CASH AND BALANCES"), [
        ("cash", None, R(r"^KASA|^CASH(?! AND)|^CASH IN|^CASH ON HAND")),
        ("cbrt", None, R(r"^T\.?C\.? ?MERKEZ|^TCMB|^CBRT|^CENTRAL BANK|^BALANCES WITH")),
        ("other", None, R(r"^DIGER|^OTHER")),
    ]),
    # anchored wide-vs-wide: the cash note's CBRT row, same filing
    "cbrt_accounts": ("wide:cash_and_cbrt.cbrt", R(r"."), [
        ("unrestricted_demand", None, R(r"^VADESIZ SERBEST|^UNRESTRICTED DEMAND|^DEMAND (UNRESTRICTED|FREE)|^FREE DEMAND|^DEMAND DEPOSIT")),
        ("unrestricted_time", None, R(r"^VADELI SERBEST HESAP|^UNRESTRICTED TIME|^TIME (UNRESTRICTED|FREE)|^FREE TIME|^TIME DEPOSIT")),
        ("restricted_time", None, R(r"^VADELI SERBEST OLMAYAN|^RESTRICTED TIME|^TIME RESTRICTED|^BLOCKED|^RESTRICTED")),
        ("reserve_requirement", None, R(r"^ZORUNLU KARSILIK|^RESERVE REQUIREMENT|^REQUIRED RESERVE|^COMPULSORY RESERVE|^RESERVE DEPOSIT")),
    ]),
    "securities_issued": ("bs", R(r"^IHRAC EDILEN MENKUL|^(MARKETABLE |DEBT )?SECURITIES ISSUED|^ISSUED (MARKETABLE |DEBT )?SECURITIES|^BONDS ISSUED"), [
        ("bills", None, R(r"^BONOLAR|^BILLS|^BONO")),
        ("asset_backed", None, R(r"^VARLIGA DAYALI|^ASSET.?BACKED")),
        ("bonds", None, R(r"^TAHVILLER|^BONDS|^TAHVIL")),
    ]),
    "subordinated_debt": ("bs", R(r"^SERMAYE BENZERI|^SUBORDINATED"), [
        ("at1_included", None, R(r"^ILAVE ANA SERMAYE|^(DEBT INSTRUMENTS )?(TO BE )?INCLUDED IN (THE )?(CALCULATION OF )?ADDITIONAL TIER")),
        ("loans", "*", R(r"^SERMAYE BENZERI KREDILER$|^SUBORDINATED LOANS$")),
        ("instruments", "*", R(r"^SERMAYE BENZERI BORCLANMA ARACLARI$|^SUBORDINATED (DEBT )?INSTRUMENTS$")),
        ("tier2_included", None, R(r"^KATKI SERMAYE|^(DEBT INSTRUMENTS )?(TO BE )?INCLUDED IN (THE )?(CALCULATION OF )?TIER ?2|^INCLUDED IN SUPPLEMENTARY")),
    ]),
}
_TOTAL = R(r"^TOPLAM|^TOTAL")
VALUES = ("tl_current", "fc_current", "tl_prior", "fc_prior")
# the roles a family's first row may carry (None: an unregistered head such
# as a bare "Bankalar" above its items)
_FIRST_ROLE: dict[str, tuple] = {
    "interest_on_loans": ("short_term",), "interest_from_banks": ("cbrt",),
    "interest_on_securities": ("fvtpl",), "interest_on_borrowings": ("banks",),
    "funds_borrowed": ("cbrt_loans",), "funds_borrowed_maturity": ("short_term",),
    "cash_and_cbrt": ("cash", None), "cbrt_accounts": ("unrestricted_demand", "unrestricted_time"),
    "securities_issued": ("bills", "bonds"), "subordinated_debt": ("at1_included", "tier2_included"),
}
_ANY = R(r".")
_CTX = {  # words in the block heading / labels that confirm a family when first rows tie
    "interest_on_loans": R(r"FAIZ|INTEREST"), "interest_from_banks": R(r"FAIZ|INTEREST"),
    "interest_on_securities": R(r"FAIZ|INTEREST"), "interest_on_borrowings": R(r"FAIZ|INTEREST"),
    "funds_borrowed": R(r"KREDI|BORROW|FUND"), "funds_borrowed_maturity": R(r"KREDI|BORROW|FUND"),
    "cash_and_cbrt": _ANY, "cbrt_accounts": _ANY, "securities_issued": R(r"IHRAC|ISSUED|MENKUL|SECURIT"),
    "subordinated_debt": R(r"SERMAYE BENZERI|SUBORDINATED"),
}
# A liability family never comes from a note about securities the bank HOLDS
# and has pledged. ZIRAAT's "Teminata Verilen/Bloke Itfa Edilmis Maliyeti
# Uzerinden Degerlenen Finansal Varliklar" lists "Bono / Tahvil ve Benzeri
# Menkul Degerler / Diger / Toplam" -- the issued-securities note's rows word
# for word -- and "MENKUL" among those labels confirmed the family, so an
# asset note was stored as a liability. Both its consolidated and its
# unconsolidated filing then carried the same 220,122,149.
#
# Only the collateral wording is used. Widening this to the asset-notes
# CONTENTS ITEM ("Bilanconun aktif hesaplarina iliskin dipnotlar") also cost
# ten funds-borrowed instances that agreed with the narrow lane, so it is
# left out: the two halves were measured apart.
_LIABILITY_FAMILIES = frozenset({"securities_issued", "subordinated_debt", "funds_borrowed",
                                 "funds_borrowed_maturity"})
_PLEDGED_NOTE = R(r"TEMINATA VERILEN|BLOKE EDILEN|PLEDGED|GIVEN AS COLLATERAL")

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_tl_fc_note_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    family       TEXT NOT NULL,
    instance_no  INTEGER NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    parent_role  TEXT,
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    tl_current   REAL,
    fc_current   REAL,
    tl_prior     REAL,
    fc_prior     REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, family, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_tl_fc_note_full_role
  ON bank_audit_tl_fc_note_full(family, row_role);
"""


def _any_role(label: str) -> str | None:
    f = fold(label).strip()
    if _TOTAL.search(f):
        return "total"
    for fam in FAMILIES:
        for role, _parent, rx in FAMILIES[fam][2]:
            if rx.search(f):
                return role
    return None


def roles_of(fam: str, labels: list[str]) -> list[tuple[str | None, str | None]]:
    """(role, parent) per row. A child registered with parent "*" belongs to
    the latest head above it — the subordinated note repeats "loans" and
    "instruments" under its AT1 and Tier 2 heads."""
    out = []
    head = None
    for lab in labels:
        f = fold(lab).strip()
        hit: tuple[str | None, str | None] = (None, None)
        if _TOTAL.search(f):
            hit = ("total", None)
        else:
            for role, parent, rx in FAMILIES[fam][2]:
                if rx.search(f):
                    if parent == "*":
                        hit = (f"{head}.{role}" if head else role, head)
                    else:
                        hit = (role, parent)
                        if parent is None:
                            head = role
                    break
        out.append(hit)
    return out


def family_of(grid: list[dict], heading: str | None, item_title: str | None = None) -> str | None:
    if not 3 <= len(grid) <= 10 or len(grid[0]["cells"]) != 4:
        return None
    labels = [(r["label"] or "").strip() for r in grid]
    if not any(_TOTAL.search(fold(lab)) for lab in labels):
        return None
    best, best_n = None, 0
    for fam in FAMILIES:
        rs = roles_of(fam, labels)
        if rs[0][0] not in _FIRST_ROLE[fam]:
            continue
        n = sum(1 for role, _p in rs if role and role != "total")
        # the confirming word is often only in the contents item the block
        # sits under ("Faiz gelirlerine ilişkin bilgiler"), never in the
        # heading the capture kept ("Cari Dönem Önceki Dönem")
        ctx = fold(heading or "") + " " + fold(item_title or "") + " " + fold(" ".join(labels))
        if fam in _LIABILITY_FAMILIES and _PLEDGED_NOTE.search(fold(heading or "")
                                                               + " " + fold(item_title or "")):
            continue
        if n >= 2 and n > best_n and _CTX[fam].search(ctx):
            best, best_n = fam, n
    return best


def heading_confirms(fam: str, heading: str | None, item_title: str | None) -> bool:
    """True when the block's OWN heading names the family, rather than the
    family being inferred from the row labels.

    BURGAN prints three tables with the issued note's rows. Only one carries
    the title — "d. İhraç edilen menkul kıymetlere ait bilgiler" — and only
    that one totals 1,623,857, the balance sheet's figure; the other two sit
    under the loan notes with an empty heading and were confirmed by the word
    "Menkul" among their labels alone. Both readings stay, but the titled one
    is instance 0, which is the instance every consumer takes."""
    ctx = fold(heading or "")
    if _CTX[fam] is _ANY:
        return bool(ctx.strip())
    if not _CTX[fam].search(ctx):
        return False
    # the generic contents line is not a title: it names the section, not
    # this table ("Faaliyet bolumlerine iliskin aciklamalar...")
    return ctx.strip() != fold(item_title or "").strip()


def _identity_holds(rows: list[dict], step: float) -> bool:
    def close(a, b):
        return abs(a - b) <= max(2.0 * step, 1e-5 * abs(b))
    tot = next((x for x in rows if x["role"] == "total"), None)
    if tot is None:
        return False
    ok = 0
    for col in ("tl_current", "fc_current"):
        t = tot[col]
        top = [x[col] for x in rows if x["role"] not in ("total", None) and x["parent"] is None]
        if t is None:
            continue
        if not close(sum(v for v in top if v is not None), t):
            return False
        for head in rows:
            if head["role"] and head["parent"] is None and head[col] is not None:
                kids = [x[col] for x in rows if x["parent"] == head["role"] and x[col] is not None]
                if len(kids) >= 2 and not close(sum(kids), head[col]):
                    return False
        ok += 1
    return ok >= 1


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, item_title, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    item_title_of: dict[tuple, str | None] = {}
    for pg, bid, heading, item_title, g, unit in blocks:
        grid = NT.strip_date_lines(absorb_inline(json.loads(g), _any_role))
        fam = family_of(grid, heading, item_title)
        if fam in ("interest_from_banks", "interest_on_securities"):
            # the balance-sheet "banks" and "securities by measurement" notes
            # print the same rows under the assets section and anchor to
            # nothing the narrow lanes hold; the contents item the block sits
            # under tells them apart
            ctx = fold(item_title or "")
            if re.search(r"BILANCO|BALANCE SHEET|AKTIF|ASSETS|VARLIK", ctx) and not re.search(
                    r"GELIR TABLOSU|PROFIT OR LOSS|INCOME STATEMENT|KAR VEYA ZARAR", ctx):
                fam = None
        if fam:
            found.append((fam, pg, bid, heading, grid, unit))
            item_title_of[(pg, bid)] = item_title
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for fam, pg, bid, heading, grid, _u in found:
        # each note has ONE total; anything after it is the next note the
        # capture glued on (AKTIF prints "1.4. İştirak ve bağlı ortaklıklardan
        # alınan faizler" under the securities table, and its 7,919 was stored
        # as the securities total)
        first_total = next((i for i, r in enumerate(grid)
                            if _TOTAL.search(fold(r["label"] or "").strip())), None)
        if first_total is not None:
            grid = grid[:first_total + 1]
        labels = [(r["label"] or "").strip() for r in grid]
        rs = roles_of(fam, labels)
        rows = []
        for r, lab, (role, parent) in zip(grid, labels, rs):
            if not lab:
                continue
            vals = [num(c) for c in r["cells"][-4:]]
            vals = [None] * (4 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            row = {"label": lab, "role": role, "parent": parent, "page": pg, "block_id": bid}
            row.update(zip(VALUES, vals))
            rows.append(row)
        instances.append({"family": fam, "rows": rows, "heading": heading,
                          "strong": heading_confirms(fam, heading, item_title_of[(pg, bid)])})
    return {"unit": unit, "step": float(factor or 1.0), "instances": instances}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    aud = sqlite3.connect(f"file:{args.audit_db}?mode=ro", uri=True)
    out = None
    if args.write:
        out = sqlite3.connect(args.tables_db)
        out.executescript(DDL)

    where, params = [], []
    for col, val in (("bank_ticker", args.bank), ("period", args.period),
                     ("kind", args.kind)):
        if val:
            where.append(f"{col}=?")
            params.append(val.upper() if col != "kind" else val)
    keys = [tuple(r) for r in tab.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_document_tables"
        + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY 1,2,3",
        params)]

    def narrow(key, fam) -> list[float]:
        statement, rx, _roles = FAMILIES[fam]
        if statement.startswith("wide:"):
            # another family's row in this very lane (wide-vs-wide)
            ofam, orole = statement[5:].split(".")
            return [(tl or 0.0) + (fc or 0.0) for tl, fc in tab.execute(
                "SELECT tl_current, fc_current FROM bank_audit_tl_fc_note_full WHERE bank_ticker=? "
                "AND period=? AND kind=? AND family=? AND row_role=? AND (tl_current IS NOT NULL OR fc_current IS NOT NULL)",
                (*key, ofam, orole))]
        try:
            if statement == "pl":
                rows = aud.execute("SELECT item_name, amount FROM bank_audit_profit_loss WHERE "
                                   "bank_ticker=? AND period=? AND kind=?", key)
            else:
                rows = aud.execute("SELECT item_name, amount_total FROM bank_audit_balance_sheet WHERE "
                                   "bank_ticker=? AND period=? AND kind=?", key)
            return [v for name, v in rows if v is not None and rx.search(fold(name or "").strip())]
        except sqlite3.OperationalError:
            return []

    detected = written = gated = 0
    fams: Counter = Counter()
    anchors: dict[str, list[int]] = {f: [0, 0] for f in FAMILIES}
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for inst in got["instances"]:
            if not _identity_holds(inst["rows"], got["step"]):
                gated += 1
                continue
            fam = inst["family"]
            tot = next(x for x in inst["rows"] if x["role"] == "total")
            grand = None
            if tot["tl_current"] is not None or tot["fc_current"] is not None:
                grand = (tot["tl_current"] or 0.0) + (tot["fc_current"] or 0.0)
            fams[fam] += 1
            kept.append(inst)
            if grand is not None:
                ref = narrow(key, fam)
                if ref:
                    anchors[fam][1] += 1
                    anchors[fam][0] += int(any(abs(grand - v) <= max(2.0, 1e-3 * abs(v)) for v in ref))
            for x in inst["rows"]:
                if any(x[v] is not None for v in VALUES):
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[(fam, fold(x["label"])[:40])] += 1
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_tl_fc_note_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            n_by: Counter = Counter()
            # a block whose own heading names the family is instance 0 of
            # that family; page order breaks the tie, as before
            for inst in sorted(kept, key=lambda i: not i.get("strong")):
                n = n_by[inst["family"]]
                n_by[inst["family"]] += 1
                out.executemany(
                    "INSERT INTO bank_audit_tl_fc_note_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["family"], n, i, x["label"], x["role"], x["parent"],
                      *(x[v] for v in VALUES), x["page"], x["block_id"], got["unit"])
                     for i, x in enumerate(inst["rows"])])
                written += len(inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused by the identities: {gated}")
    if fams:
        print(f"instances kept by family: {dict(fams.most_common())}")
    for fam, b in anchors.items():
        if b[1]:
            print(f"  {fam:26} total TL+FC vs narrow statement line  {b[0]:5}/{b[1]:5}  {b[0] / b[1]:6.1%}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for (fam, lab), c in unrole.most_common(10):
        print(f"    unrecognised x{c} [{fam}]: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_tl_fc_note_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
