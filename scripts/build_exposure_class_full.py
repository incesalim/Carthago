#!/usr/bin/env python
"""The exposure-class graduation: BRSA's numbered 1-18 standardised-approach
form (Pillar 3 CR4 — exposures and CRM effects by asset class), minted from
the document layer on the shared numbered-template machinery.

NO narrow lane holds any of this. The wide lane keeps, per asset class
(sovereigns, regional governments, administrative bodies, MDBs, banks,
corporates, retail, mortgage-secured, past-due, high-risk, … equity, total):
on- and off-balance-sheet exposure before and after CCF/CRM, the RWA, and
the RWA density — for the current period and the prior year-end instance.
This is where the credit-risk RWA of the OV1 form (row 1) decomposes.

Validators, dry-run (default): the template's own per-row identity,
density = RWA / (on + off after CRM) x 100, on rows 7, 8 and 18; and the
row-18 RWA against the OV1 form's credit-risk RWA for the same filing (a
wide-vs-wide anchor, reported within a 2% band — the forms' perimeters differ
slightly by filer).

`--write` stores into bank_audit_exposure_class_full in
data/bank_audit_tables.db (local only; never the audit snapshot, not D1).
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import numbered_template as NT  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"

_SIG = {
    1: re.compile(r"^MERKEZI YONETIM|^CENTRAL GOVERNMENT|^SOVEREIGN|^EXPOSURES TO CENTRAL"),
    7: re.compile(r"^KURUMSAL|^CORPORATE"),
    8: re.compile(r"^PERAKENDE|^RETAIL"),
    18: re.compile(r"^TOPLAM|^TOTAL"),
}
ROLE_BY_ROW = {
    1: "central_governments", 2: "regional_governments",
    3: "administrative_bodies", 4: "multilateral_development_banks",
    5: "international_organisations", 6: "banks_and_intermediaries",
    7: "corporates", 8: "retail", 9: "secured_by_real_estate",
    17: "equity_investments", 18: "total",
}
VALUES = ("on_bs_pre_crm", "off_bs_pre_crm", "on_bs_post_crm",
          "off_bs_post_crm", "rwa", "rwa_density")
_IDENTITY_ROWS = (7, 8, 18)

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_exposure_class_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    row_order    INTEGER NOT NULL,
    template_row INTEGER,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- the six printed columns; money in canonical thousand TL (scaled at
    -- mint), rwa_density a percent, never scaled. NULL = printed "-".
    on_bs_pre_crm   REAL,
    off_bs_pre_crm  REAL,
    on_bs_post_crm  REAL,
    off_bs_post_crm REAL,
    rwa             REAL,
    rwa_density     REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, row_order)
);
CREATE INDEX IF NOT EXISTS idx_exposure_class_full_row
  ON bank_audit_exposure_class_full(template_row);
"""


def _is_cr4(grid: list[dict]) -> bool:
    """Three forms number the same asset-class rows 1-18. CR5 spreads them over
    risk-weight buckets (ten-plus columns); the interim exposure-by-class table
    has six columns of AMOUNTS; CR4 has six columns whose LAST is the RWA
    density — a percentage, never above 100. Shape and content together."""
    return 5 <= NT.live_value_columns(grid, 18) <= 7


def _identity_holds(inst: list[dict]) -> bool:
    """The mint gate: an instance is stored only if its TOTAL row's density
    equals RWA / post-CRM exposure. That one equation proves the six columns
    landed in the right slots; an instance that fails it is a different
    per-class form (or a layout this builder does not read yet) and is
    counted, not stored."""
    x = {r["template_row"]: r for r in inst}.get(18, {})
    rwa, on, off, dens = (x.get("rwa"), x.get("on_bs_post_crm"),
                          x.get("off_bs_post_crm"), x.get("rwa_density"))
    expo = (on or 0.0) + (off or 0.0)
    return rwa is not None and dens is not None and bool(expo)         and abs(rwa / expo * 100 - dens) <= 0.15


# the same eighteen asset classes by label, for the filings that print the
# form without its row numbers (AKBNK, KUVEYT, ICBCT, ZIRAATK...). Order is
# match priority, not template order.
_R = re.compile
_BY_LABEL: list[tuple[int, re.Pattern]] = [
    (18, _R(r"^TOPLAM$|^TOTAL$|^GENEL TOPLAM|^TOTAL( CREDIT)? RISK")),
    (1, _R(r"^MERKEZI YONETIM|^CENTRAL GOVERNMENT|^SOVEREIGN|^EXPOSURES TO CENTRAL|^CONDITIONAL AND UNCONDITIONAL "
           r"(RECEIVABLES|EXPOSURES) (FROM|TO) (CENTRAL|SOVEREIGN)")),
    (2, _R(r"^BOLGESEL YONETIM|^REGIONAL GOVERNMENT|^EXPOSURES TO REGIONAL|^CONDITIONAL AND UNCONDITIONAL "
           r"(RECEIVABLES|EXPOSURES) (FROM|TO) (REGIONAL|LOCAL)")),
    (3, _R(r"^IDARI BIRIM|^ADMINISTRATIVE (BODIES|UNITS)|^PUBLIC SECTOR ENTIT|^EXPOSURES TO ADMINISTRATIVE|"
           r"^CONDITIONAL AND UNCONDITIONAL (RECEIVABLES|EXPOSURES) (FROM|TO) ADMINISTRATIVE")),
    (4, _R(r"^COK TARAFLI KALKINMA|^MULTILATERAL DEVELOPMENT")),
    (5, _R(r"^ULUSLARARASI TESKILAT|^INTERNATIONAL ORGANI[SZ]ATION")),
    (6, _R(r"^BANKALARDAN VE ARACI KURUM|^BANKS AND (BROKERAGE|INTERMEDIAR|CAPITAL MARKET)|^EXPOSURES TO (BANKS|"
           r"INSTITUTION)|^CONDITIONAL AND UNCONDITIONAL (RECEIVABLES|EXPOSURES) (FROM|TO) BANK")),
    (7, _R(r"^KURUMSAL ALACAK|^CORPORATE (RECEIVABLE|EXPOSURE|CLAIM)|^EXPOSURES TO CORPORATE|"
           r"^CONDITIONAL AND UNCONDITIONAL CORPORATE")),
    (8, _R(r"^PERAKENDE ALACAK|^RETAIL (RECEIVABLE|EXPOSURE|CLAIM)|^EXPOSURES TO RETAIL|"
           r"^CONDITIONAL AND UNCONDITIONAL RETAIL")),
    (9, _R(r"^IKAMET AMACLI GAYRIMENKUL|^(EXPOSURES )?SECURED BY (RESIDENTIAL|MORTGAGES ON RESIDENTIAL)|"
           r"^CONDITIONAL AND UNCONDITIONAL (RECEIVABLES|EXPOSURES) SECURED BY (RESIDENTIAL|MORTGAGE)")),
    (10, _R(r"^TICARI AMACLI GAYRIMENKUL|^(EXPOSURES )?SECURED BY (COMMERCIAL|MORTGAGES ON COMMERCIAL)")),
    (11, _R(r"^TAHSILI GECIKMIS|^PAST.?DUE (RECEIVABLE|EXPOSURE|ITEM|LOAN)|^EXPOSURES IN DEFAULT")),
    (12, _R(r"^KURULCA RISKI YUKSEK|^(ITEMS|RECEIVABLES|EXPOSURES) (IN|DEFINED IN) HIGH.?RISK|^HIGHER.?RISK")),
    (13, _R(r"^IPOTEK TEMINATLI MENKUL|^(SECURITIES|BONDS) (COLLATERALI[SZ]ED|SECURED) BY MORTGAGE|^COVERED BOND")),
    (14, _R(r"^MENKUL KIYMETLESTIRME|^SECURITI[SZ]ATION")),
    (15, _R(r"^BANKALAR VE ARACI KURUMLARDAN OLAN KISA|^SHORT.?TERM (RECEIVABLES|EXPOSURES|CLAIMS)")),
    (16, _R(r"^KOLEKTIF YATIRIM|^(INVESTMENTS? (SIMILAR TO |IN THE NATURE OF )?)?COLLECTIVE INVESTMENT|"
            r"^UNDERTAKINGS FOR COLLECTIVE")),
    (17, _R(r"^HISSE SENEDI YATIRIM|^EQUITY (INVESTMENT|SHARE|EXPOSURE)|^DIGER ALACAK|^OTHER (RECEIVABLE|ITEM|"
            r"ASSET|CLAIM|EXPOSURE)")),
]


def _label_gate(rows: list[dict]) -> bool:
    """The same density identity as the numbered path, on the total row."""
    return _identity_holds(rows)


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    got = NT.assemble(
        tab, key, sig=_SIG, max_row=18, bottom_row=17, n_values=6,
        percent_rows=set(), role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=VALUES, percent_cols=frozenset({5}), block_filter=_is_cr4)
    if got is not None:
        return got
    return NT.assemble_by_label(
        tab, key, labels=_BY_LABEL, n_values=6, percent_rows=set(), open_rows={1, 2, 3},
        close_row=18, min_rows=8, role_of=lambda n, _label: ROLE_BY_ROW.get(n),
        value_names=VALUES, gate=_label_gate)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
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

    def ov1_credit_rwa(key):
        try:
            return [v for (v,) in tab.execute(
                "SELECT rwa FROM bank_audit_rwa_full WHERE bank_ticker=? AND "
                "period=? AND kind=? AND period_label='current' AND template_row=1",
                key) if v is not None]
        except sqlite3.OperationalError:
            return []

    detected = written = 0
    gated: dict[str, int] = {}
    inst_count: Counter = Counter()
    ident = [0, 0]
    ov1 = [0, 0]
    mism = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        kept = {}
        for lab, inst in got["instances"].items():
            if _identity_holds(inst):
                kept[lab] = inst
            else:
                gated[lab] = gated.get(lab, 0) + 1
        got["instances"] = kept
        if not kept:
            continue
        inst_count[len(got["instances"])] += 1
        for lab, inst in got["instances"].items():
            by_row = {x["template_row"]: x for x in inst}
            for n in _IDENTITY_ROWS:
                x = by_row.get(n, {})
                rwa, on, off, dens = (x.get("rwa"), x.get("on_bs_post_crm"),
                                      x.get("off_bs_post_crm"), x.get("rwa_density"))
                expo = (on or 0.0) + (off or 0.0)
                if rwa is not None and dens is not None and expo:
                    ident[1] += 1
                    ident[0] += int(abs(rwa / expo * 100 - dens) <= 0.15)
        cur = {x["template_row"]: x for x in got["instances"].get("current", [])}
        total_rwa = cur.get(18, {}).get("rwa")
        have = ov1_credit_rwa(key)
        if total_rwa is not None and have:
            ov1[1] += 1
            ok = any(abs(total_rwa - v) <= 0.02 * v for v in have)
            ov1[0] += int(ok)
            if not ok and len(mism) < 8:
                mism.append((key, total_rwa, sorted(set(have))))
        if args.verbose:
            print(f"{' '.join(key)}: instances={list(got['instances'])} "
                  f"rows={[len(v) for v in got['instances'].values()]}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_exposure_class_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for lab, inst in got["instances"].items():
                out.executemany(
                    "INSERT INTO bank_audit_exposure_class_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, i, x["template_row"], x["label"], x["role"],
                      *(x[v] for v in VALUES), x["page"], x["block_id"],
                      got["unit"]) for i, x in enumerate(inst)])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"instances gated out by the mint identity: {sum(gated.values())}")
    if inst_count:
        print(f"instances per filing: {dict(sorted(inst_count.items()))}")
    print(f"  density = rwa / post-CRM exposure (rows 7/8/18): {ident[0]}/{ident[1]}"
          + (f"  {ident[0] / ident[1]:.1%}" if ident[1] else ""))
    print(f"  row 18 RWA vs OV1 credit-risk RWA (2% band):     {ov1[0]}/{ov1[1]}"
          + (f"  {ov1[0] / ov1[1]:.1%}" if ov1[1] else ""))
    for key, wide, vals in mism:
        print(f"    {' '.join(key):32} cr4={wide} ov1={vals}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_exposure_class_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
