#!/usr/bin/env python
"""The two-period notes graduation: the small NOTES-section tables printed
as items × (current period, prior period) with a total — minted from the
document layer under a family registry, each family anchored to a line of
the narrow off-balance-sheet statement:

  letters_of_guarantee   definite, temporary, advance, customs, other
                         letters of guarantee     → off-BS letters of guarantee
  non_cash_loans         letters of guarantee, letters of credit, bank
                         acceptances / avals, other guarantees and
                         sureties                 → off-BS guarantees head
  other_operating_expenses  personnel, termination reserve, social aid
                         fund, impairments and depreciation by asset class,
                         the "other operating expenses" head with its
                         lease / maintenance / advertising / other children,
                         loss on sale of assets, other
                                                  → P&L other operating expenses
  trading_income         gains and losses heads, each over capital-market,
                         derivative and FX children; net total
                                                  → P&L trading income (net)

Rows carry a registry role, the label kept. MINT GATE: total = Σ rows on
the current column (and on the prior where printed). Anchor, dry-run
(default): the current total vs the family's narrow off-balance line, same
filing.

`--write` stores into bank_audit_two_period_note_full in
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
from src.audit_reports.numbered_template import absorb_inline, fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

R = re.compile
# family -> (statement, narrow line regex, [(role, parent, label regex)])
FAMILIES: dict[str, tuple[str, re.Pattern, list[tuple[str, str | None, re.Pattern]]]] = {
    "letters_of_guarantee": ("off_balance", R(r"^TEMINAT MEKTUPLARI$|^LETTERS? OF GUARANTEES?$"), [
        ("definite", None, R(r"^KESIN|^DEFINITE|^LETTERS? OF CERTAIN|^CERTAIN|^FINAL")),
        ("temporary", None, R(r"^GECICI|^TEMPORARY|^LETTERS? OF TENTATIVE|^TENTATIVE|^BID|^PROVISIONAL")),
        ("advance", None, R(r"^AVANS|^ADVANCE|^LETTERS? OF ADVANCE")),
        ("customs", None, R(r"^GUMRUK|^CUSTOMS|^LETTERS? OF GUARANTEE GIVEN TO CUSTOMS|^GIVEN TO CUSTOMS")),
        ("other", None, R(r"^DIGER|^OTHER|^SURETY")),
    ]),
    # the narrow off-balance lane keeps the guarantees section head,
    # "Garanti ve Kefaletler" — the non-cash loans total
    "non_cash_loans": ("off_balance", R(r"^GAYRINAKDI KREDILER$|^NON.?CASH LOANS?$|^GARANTI VE KEFALETLER$|"
                                        r"^GUARANTEES AND (WARRANTIES|SURETIES|SURETYSHIPS)$|^GUARANTEES$"), [
        ("letters_of_guarantee", None, R(r"^TEMINAT MEKTUP|^LETTERS? OF GUARANTEE|^GUARANTEES?$|^GARANTI")),
        ("letters_of_credit", None, R(r"^AKREDITIF|^LETTERS? OF CREDIT")),
        ("bank_acceptances", None, R(r"^BANKA KREDI|^BANKA AVAL|^BANKA KABUL|^BANK LOAN|^BANK ACCEPTANCE|^BILLS? OF EXCHANGE|^ACCEPTANCE")),
        ("endorsements", None, R(r"^CIRO|^ENDORSEMENT")),
        ("other", None, R(r"^DIGER|^OTHER")),
    ]),
    "other_operating_expenses": ("pl", R(r"^DIGER FAALIYET GIDERLERI|^OTHER OPERATING EXPENSES?"), [
        ("personnel", None, R(r"^PERSONEL GIDER|^PERSONNEL (EXPENSE|COST)|^STAFF (EXPENSE|COST)")),
        ("termination_reserve", None, R(r"^KIDEM|^RESERVE FOR EMPLOYEE TERMINATION|^PROVISION FOR (RETIREMENT|EMPLOYEE TERMINATION|SEVERANCE)|"
                                        r"^EMPLOYEE TERMINATION|^SEVERANCE|^RETIREMENT PAY")),
        ("social_aid_fund", None, R(r"^BANKA SOSYAL YARDIM|^BANK SOCIAL AID|^(PROVISION FOR )?PENSION FUND|^SOCIAL AID")),
        ("tangible_impairment", None, R(r"^MADDI DURAN VARLIK DEGER DUSUS|^IMPAIRMENT (LOSSES? |EXPENSES? )?(ON|OF) (TANGIBLE|PROPERTY|FIXED)|^TANGIBLE ASSETS? IMPAIRMENT")),
        ("tangible_depreciation", None, R(r"^MADDI DURAN VARLIK AMORTISMAN|^DEPRECIATION (EXPENSES? |CHARGES? )?(ON|OF) (TANGIBLE|PROPERTY|FIXED)|^TANGIBLE ASSETS? DEPRECIATION")),
        ("intangible_impairment", None, R(r"^MADDI OLMAYAN DURAN VARLIK DEGER DUSUS|^IMPAIRMENT (LOSSES? |EXPENSES? )?(ON|OF) INTANGIBLE|^INTANGIBLE ASSETS? IMPAIRMENT")),
        ("goodwill_impairment", None, R(r"^SEREFIYE|^GOODWILL")),
        ("intangible_amortisation", None, R(r"^MADDI OLMAYAN DURAN VARLIK AMORTISMAN|^AMORTI[SZ]ATION (EXPENSES? |CHARGES? )?(ON|OF) INTANGIBLE|"
                                            r"^DEPRECIATION (EXPENSES? )?(ON|OF) INTANGIBLE|^INTANGIBLE ASSETS? (AMORTI[SZ]ATION|DEPRECIATION)")),
        ("equity_method_impairment", None, R(r"^OZKAYNAK YONTEMI|^OZKAYNAK YONETIMI|^EQUITY METHOD|^IMPAIRMENT .*EQUITY|^INVESTMENTS ACCOUNTED")),
        ("held_for_sale_impairment", None, R(r"^ELDEN CIKARILACAK (MENKUL )?KIYMETLER DEGER DUSUS|^SATIS AMACLI .*DEGER DUSUS|^IMPAIRMENT .*(HELD FOR SALE|DISPOSAL)|"
                                             r"^ASSETS HELD FOR (SALE|RESALE) .*IMPAIR|^(IMPAIRMENT|VALUE DECREASE).*ASSETS TO BE DISPOSED")),
        ("held_for_sale_depreciation", None, R(r"^ELDEN CIKARILACAK (MENKUL )?KIYMETLER AMORTISMAN|^ELDEN CIKARILACAK AMORTISMAN|^SATIS AMACLI .*AMORTISMAN|"
                                               r"^DEPRECIATION .*(HELD FOR SALE|DISPOSAL|DISPOSED)|^ASSETS HELD FOR (SALE|RESALE) .*DEPRECIATION")),
        ("other_operating", None, R(r"^DIGER ISLETME GIDERLERI|^OTHER OPERATING EXPENSES?$|^OTHER OPERATIONAL EXPENSES?$")),
        ("lease", "other_operating", R(r"^FAALIYET KIRALAMA|^KIRALAMA|^TFRS 16|^OPERATIONAL LEASE|^OPERATING LEASE|^RENT|^LEASE")),
        ("maintenance", "other_operating", R(r"^BAKIM VE ONARIM|^MAINTENANCE|^REPAIR")),
        ("advertising", "other_operating", R(r"^REKLAM|^ADVERTIS")),
        ("other_operating_other", "other_operating", R(r"^DIGER GIDERLER|^OTHER EXPENSES")),
        ("loss_on_sale_of_assets", None, R(r"^AKTIFLERIN SATISINDAN|^LOSS(ES)? (ON|FROM) (THE )?SALES? OF ASSETS")),
        ("other", None, R(r"^DIGER|^OTHER")),
    ]),
    # gains and losses print as two heads with the same three children;
    # the net total is gains minus losses (losses printed positive)
    "trading_income": ("pl", R(r"^TICARI KAR|^TRADING (INCOME|PROFIT|GAIN)|^NET TRADING"), [
        # children first: "Losses on Capital Market Transactions" is a child,
        # not the loss head
        ("capital_market", "*", R(r"^SERMAYE PIYASASI|^CAPITAL MARKET|^(GAINS?|LOSS(ES)?|PROFIT|INCOME) (ON|FROM) CAPITAL MARKET|"
                                  r"^SECURITIES TRADING|^TRADING ACCOUNT|^(GAINS?|LOSS(ES)?) ON SECURITIES")),
        ("derivative", "*", R(r"^TUREV|^DERIVATIVE|^(GAINS?|LOSS(ES)?|PROFIT|INCOME) (ON|FROM) DERIVATIVE|^FROM DERIVATIVE")),
        ("fx", "*", R(r"^KAMBIYO|^FOREIGN EXCHANGE|^FX|^(GAINS?|LOSS(ES)?|PROFIT|INCOME) (ON|FROM) FOREIGN EXCHANGE")),
        ("gain", None, R(r"^KAR$|^KAR \(|^PROFIT$|^TRADING (INCOME|GAINS?|PROFIT)$|^GAINS?$|^INCOME$|^GAINS? \(")),
        ("loss", None, R(r"^ZARAR|^LOSS(ES)?$|^LOSS(ES)? \(|^TRADING LOSS")),
    ]),
}
_DEDUCT = {"trading_income": ("loss",)}
_TOTAL = R(r"^TOPLAM|^TOTAL|^NET TICARI|^NET TRADING")
_FIRST = {"letters_of_guarantee": ("definite", "temporary"),
          "non_cash_loans": ("letters_of_guarantee", "letters_of_credit", "bank_acceptances"),
          "other_operating_expenses": ("personnel", "termination_reserve", None),
          "trading_income": ("gain",)}
_CTX = R(r"CARI|ONCEKI|CURRENT|PRIOR|PREVIOUS")


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
    """(role, parent) per row; a child role counts only under its head."""
    out: list[tuple[str | None, str | None]] = []
    head = None
    seen_total = False
    for lab in labels:
        f = fold(lab).strip()
        if seen_total:                            # memo rows after the total
            out.append((None, None))
            continue
        if _TOTAL.search(f):
            out.append(("total", None))
            seen_total = True
            continue
        hit = next(((role, parent) for role, parent, rx in FAMILIES[fam][2] if rx.search(f)), (None, None))
        role, parent = hit
        if parent == "*":                         # a child of whichever head is open
            role, parent = (f"{head}.{role}", head) if head else (None, None)
        elif parent is not None and head != parent:
            role, parent = None, None             # a child label outside its head
        elif role is not None and parent is None:
            head = role
        out.append((role, parent))
    return out


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_two_period_note_full (
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
    current      REAL,
    prior        REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, family, instance_no, row_order)
);
CREATE INDEX IF NOT EXISTS idx_two_period_note_full_role
  ON bank_audit_two_period_note_full(family, row_role);
"""


def family_of(grid: list[dict], col_labels: list, heading: str | None) -> str | None:
    if not 3 <= len(grid) <= 26 or len(grid[0]["cells"]) != 2:
        return None
    ctx = fold(" ".join(str(c or "") for c in col_labels) + " " + (heading or ""))
    if not _CTX.search(ctx):
        return None
    labels = [(r["label"] or "").strip() for r in grid]
    if not any(_TOTAL.search(fold(lab)) for lab in labels):
        return None
    best, best_n = None, 0
    for fam in FAMILIES:
        rs = roles_of(fam, labels)
        if rs[0][0] not in _FIRST[fam]:
            continue
        n = sum(1 for r, _p in rs if r and r != "total")
        need = 4 if fam == "other_operating_expenses" else 2
        if n >= need and n > best_n:
            best, best_n = fam, n
    return best


def _identity_holds(rows: list[dict], step: float, fam: str = "") -> bool:
    tot = next((x for x in rows if x["role"] == "total"), None)
    if tot is None:
        return False
    deduct = _DEDUCT.get(fam, ())
    ok = 0
    for col in ("current", "prior"):
        t = tot[col]
        if t is None:
            continue
        def head_value(x):
            # a head printed without a figure stands for the sum of its children
            if x[col] is None and x["role"]:
                kids = [y[col] for y in rows if y["parent"] == x["role"] and y[col] is not None]
                return sum(kids) if kids else 0.0
            return x[col] or 0.0

        s = sum((-head_value(x) if x["role"] in deduct and head_value(x) > 0 else head_value(x))
                for x in rows if x["role"] != "total" and x["parent"] is None)
        if abs(s - t) > max(2.0 * step, 1e-5 * abs(t)):
            return False
        for head in rows:
            if head["role"] and head["parent"] is None and head[col] is not None:
                kids = [x[col] for x in rows if x["parent"] == head["role"] and x[col] is not None]
                if len(kids) >= 2 and abs(sum(kids) - head[col]) > max(2.0 * step, 1e-5 * abs(head[col])):
                    return False
        ok += 1
    return ok >= 1


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, heading, col_labels_json, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = []
    for pg, bid, heading, cl, g, unit in blocks:
        grid = absorb_inline(json.loads(g), _any_role)
        fam = family_of(grid, json.loads(cl or "[]"), heading)
        if fam:
            found.append((fam, pg, bid, heading, grid, unit))
    if not found:
        return None
    unit = found[0][5]
    factor = U.UNIT_SCALE.get(unit)
    instances = []
    for fam, pg, bid, heading, grid, _u in found:
        labels = [(r["label"] or "").strip() for r in grid]
        rows = []
        for r, lab, (role, parent) in zip(grid, labels, roles_of(fam, labels)):
            if not lab:
                continue
            vals = [num(c) for c in r["cells"][-2:]]
            vals = [None] * (2 - len(vals)) + vals
            if factor is not None:
                vals = [U.scale_amount(v, factor) for v in vals]
            rows.append({"label": lab, "role": role, "parent": parent, "current": vals[0], "prior": vals[1],
                         "page": pg, "block_id": bid})
        instances.append({"family": fam, "rows": rows, "heading": heading})
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

    _FOOTNOTE = re.compile(r"(\s+[-–]?\s*[IVXA-Z0-9.(),]{1,8})+$")

    def narrow(key, fam) -> list[float]:
        statement, rx, _roles = FAMILIES[fam]
        try:
            if statement == "pl":
                rows = aud.execute("SELECT item_name, amount FROM bank_audit_profit_loss WHERE "
                                   "bank_ticker=? AND period=? AND kind=?", key)
            else:
                rows = aud.execute("SELECT item_name, amount_total FROM bank_audit_balance_sheet WHERE "
                                   "bank_ticker=? AND period=? AND kind=? AND statement=?", (*key, statement))
            return [v for name, v in rows
                    if v is not None and (rx.search(fold(name or "").strip())
                                          or rx.search(_FOOTNOTE.sub("", fold(name or "").strip())))]
        except sqlite3.OperationalError:
            return []

    def personnel_line(key) -> list[float]:
        try:
            return [v for name, v in aud.execute(
                "SELECT item_name, amount FROM bank_audit_profit_loss WHERE bank_ticker=? AND period=? AND kind=?", key)
                if v is not None and re.search(r"^PERSONEL GIDER|^PERSONNEL EXPENSE", fold(name or "").strip())]
        except sqlite3.OperationalError:
            return []

    detected = written = gated = 0
    fams: Counter = Counter()
    anchors = {f: [0, 0] for f in FAMILIES}
    role_cov = [0, 0]
    unrole: Counter = Counter()
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = []
        for inst in got["instances"]:
            if not _identity_holds(inst["rows"], got["step"], inst["family"]):
                gated += 1
                continue
            fam = inst["family"]
            fams[fam] += 1
            kept.append(inst)
            tot = next(x for x in inst["rows"] if x["role"] == "total")
            if tot["current"] is not None:
                ref = narrow(key, fam)
                if fam == "other_operating_expenses":
                    # since 2021 the P&L shows personnel expenses on their own
                    # line; a note that still carries the personnel row equals
                    # the two lines together
                    ref = ref + [v + pv for v in ref for pv in personnel_line(key)]
                if ref:
                    anchors[fam][1] += 1
                    anchors[fam][0] += int(any(abs(tot["current"] - v) <= max(2.0, 1e-3 * abs(v)) for v in ref))
            for x in inst["rows"]:
                if x["current"] is not None or x["prior"] is not None:
                    role_cov[1] += 1
                    role_cov[0] += int(x["role"] is not None)
                    if x["role"] is None:
                        unrole[(fam, fold(x["label"])[:40])] += 1
        if not kept:
            continue
        if out is not None:
            out.execute("DELETE FROM bank_audit_two_period_note_full WHERE bank_ticker=? AND period=? AND kind=?", key)
            n_by: Counter = Counter()
            for inst in kept:
                n = n_by[inst["family"]]
                n_by[inst["family"]] += 1
                out.executemany(
                    "INSERT INTO bank_audit_two_period_note_full VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, inst["family"], n, i, x["label"], x["role"], x["parent"], x["current"], x["prior"],
                      x["page"], x["block_id"], got["unit"]) for i, x in enumerate(inst["rows"])])
                written += len(inst["rows"])
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | instances refused by the total: {gated}")
    if fams:
        print(f"instances kept by family: {dict(fams.most_common())}")
    for fam, b in anchors.items():
        if b[1]:
            print(f"  {fam:26} current total vs narrow statement line  {b[0]:5}/{b[1]:5}  {b[0] / b[1]:6.1%}")
    if role_cov[1]:
        print(f"  value-bearing rows with a role: {role_cov[0]}/{role_cov[1]} ({role_cov[0] / role_cov[1]:.1%})")
    for (fam, lab), c in unrole.most_common(8):
        print(f"    unrecognised x{c} [{fam}]: {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_two_period_note_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
