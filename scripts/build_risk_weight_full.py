#!/usr/bin/env python
"""The risk-weight graduation: BRSA's Pillar 3 CR5 matrix — standardised
approach exposures by asset class (numbered rows 1-17, total 18) × risk
weight (0%, 10%, 20%, 35%, 50%, 75%, 100%, 150%, 200%, 250%, "others" ...,
plus the post-CRM / post-CCF total), minted from the document layer.

The weight columns vary bank to bank (25% and 250% appear and disappear),
and the PDF column labels are split across header lines, so the weights are
read from the matrix's own header row ("Risk Sınıfları / Risk Ağırlığı" with
numeric cells), then the captured column labels ("%20" / "20%"), then the
page text just above the block in the capture ledger, where token order is
column order and the mortgage-secured columns wrap their weight onto the
line above (`secured_re` marks them; they repeat a plain weight).
The lane is stored LONG: one row per (asset class, column), with the
column's `risk_weight` (NULL for "others" and the total) and `col_role`.

MINT GATE: the matrix's own arithmetic — total = Σ weight columns on the
total row AND on at least 90% of the value-bearing asset-class rows. Anchor,
dry-run (default): the grand total vs CR4's post-CRM on- + off-balance
exposure (bank_audit_exposure_class_full row 18), the same figure on the
regulator's own cross-reference.

`--write` stores into bank_audit_risk_weight_full in
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
from src.audit_reports.numbered_template import fold, num  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
CAPTURE_DB = REPO / "data" / "bank_audit_capture.db"

MAX_ROW = 18
_ROW1 = re.compile(r"^MERKEZI YONETIM|^CENTRAL GOVERNMENT|^SOVEREIGN|^CLAIMS ON SOVEREIGN|"
                   r"^EXPOSURES TO (CENTRAL|SOVEREIGN)|^RECEIVABLES FROM CENTRAL")
_OTHER_COL = re.compile(r"DIGER|OTHER")
_TOTAL_COL = re.compile(r"TOPLAM|TOTAL|TUTAR|AMOUNT")
_WEIGHTS = {0, 2, 4, 10, 20, 25, 35, 50, 70, 75, 100, 150, 200, 250, 370, 1250}
# Row roles are read off the LABEL, not the number: the 2016 template has
# sixteen asset classes and its total is row 17, the current one seventeen
# and row 18. Order matters where one label contains another.
ROLES: list[tuple[str, re.Pattern]] = [
    ("total", re.compile(r"^TOPLAM|^TOTAL")),
    ("banks_short_term", re.compile(r"KISA VADELI|SHORT.?TERM")),
    ("central_governments", re.compile(r"^MERKEZI YONETIM|CENTRAL GOVERNMENT|SOVEREIGN")),
    ("regional_governments", re.compile(r"^BOLGESEL|REGIONAL|LOCAL (GOVERNMENT|AUTHORIT)")),
    ("administrative_bodies", re.compile(r"^IDARI BIRIM|ADMINISTRATIVE|NON.?COMMERCIAL")),
    ("multilateral_development_banks", re.compile(r"^COK TARAFLI|MULTILATERAL")),
    ("international_organisations", re.compile(r"^ULUSLARARASI|INTERNATIONAL ORGANI")),
    ("banks_and_brokers", re.compile(r"^BANKALARDAN|^BANKS|^EXPOSURES TO BANKS|^CLAIMS ON BANKS|"
                                     r"^RECEIVABLES FROM BANKS")),
    ("corporates", re.compile(r"^KURUMSAL|CORPORATE")),
    ("retail", re.compile(r"^PERAKENDE|RETAIL")),
    ("residential_mortgage", re.compile(r"^IKAMET|RESIDENTIAL")),
    ("commercial_mortgage", re.compile(r"^TICARI AMACLI|COMMERCIAL")),
    ("past_due", re.compile(r"^TAHSILI GECIKMIS|PAST.?DUE|OVERDUE|NON.?PERFORMING")),
    ("high_risk", re.compile(r"RISKI YUKSEK|HIGH(ER)?.?RISK")),
    ("covered_bonds", re.compile(r"^TEMINATLI MENKUL|COVERED BOND|MORTGAGE.?BACKED")),
    ("collective_investment", re.compile(r"^KOLEKTIF|COLLECTIVE INVESTMENT|MUTUAL FUND|\bCIU")),
    ("equity", re.compile(r"^HISSE SENEDI|^EQUITY|^SHARE|^INVESTMENTS IN EQUIT")),
    ("other", re.compile(r"^DIGER|^OTHER")),
]


def role_of(label: str) -> str | None:
    f = fold(label).strip()
    for role, rx in ROLES:
        if rx.search(f):
            return role
    return None


DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_risk_weight_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    period_label TEXT NOT NULL,
    template_row INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    col_order    INTEGER NOT NULL,
    -- the column's risk weight in percent (0, 10, 20, ...); NULL for the
    -- "others" column and for the total.
    risk_weight  REAL,
    col_role     TEXT NOT NULL,      -- weight / other / unknown / total
    -- 1 where the column is the "secured by real-estate mortgage" weight
    -- (35% residential / 50% commercial), which repeats a plain weight.
    secured_re   INTEGER NOT NULL DEFAULT 0,
    col_label    TEXT,               -- as printed, where a label was read
    -- canonical thousand TL (scaled at mint). NULL = the filing printed "-".
    amount       REAL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, period_label, template_row, col_order)
);
CREATE INDEX IF NOT EXISTS idx_risk_weight_full_cell
  ON bank_audit_risk_weight_full(row_role, risk_weight);
"""


_SECURED = re.compile(r"IPOTEG|MORTGAGE|REAL.?ESTATE|PROPERTY|SECURED|G\.MENKUL|GAYRIMENKUL")
_WTOKEN = re.compile(r"^%?\s*(\d{1,4})\s*%?[\"”']?$")
_WINTEXT = re.compile(r"(?<![\d.,])%\s*(\d{1,4})|(?<![\d.,])(\d{1,4})\s*%")


def _weight_candidates(tokens: list[str]) -> set[float]:
    """Risk weights a column's header fragments could mean: any "%N"/"N%"
    token or in-text mention, plus the concatenation of consecutive bare
    numbers (a "250%" printed as "25" over "0")."""
    out: set[float] = set()
    bare: list[str] = []
    for t in tokens:
        m = _WTOKEN.match(t)
        if m:
            if int(m.group(1)) in _WEIGHTS:
                out.add(float(m.group(1)))
            if "%" not in t:
                bare.append(m.group(1))
                continue
        else:
            for a, b in _WINTEXT.findall(t):
                n = int(a or b)
                if n in _WEIGHTS:
                    out.add(float(n))
        if bare and len(bare) >= 2:
            cat = int("".join(bare))
            if cat in _WEIGHTS:
                out.add(float(cat))
        if not _WTOKEN.match(t):
            bare = []
    if len(bare) >= 2 and int("".join(bare)) in _WEIGHTS:
        out.add(float(int("".join(bare))))
    return out


def _fmt(cell) -> str | None:
    if cell is None:
        return None
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell).strip() or None


def column_model(grid: list[dict], col_labels: list, page_lines: list[str] | None = None
                 ) -> list[tuple[int, str, float | None, int, str | None]] | None:
    """[(cell index, col_role, risk_weight, secured_re, printed label)] for the
    matrix's value columns, or None when no header could be read.

    Every column live in a numbered row is a value column (nothing may drop
    out of the row sums); the total is the rightmost column live in the total
    row; each other column's weight is read from all header fragments at its
    index — in-grid unnumbered rows and the captured column labels — under a
    left-to-right non-decreasing constraint, "others" from its label.
    """
    numbered = [r for r in grid if NT.rowno(r, MAX_ROW) is not None]
    headers = [r for r in grid if NT.rowno(r, MAX_ROW) is None]
    if not numbered:
        return None
    ncol = max(len(r["cells"]) for r in numbered)
    live = [i for i in range(1, ncol)
            if any(i < len(r["cells"]) and r["cells"][i] is not None for r in numbered)]
    total_row = max(numbered, key=lambda r: NT.rowno(r, MAX_ROW))
    tot_live = [i for i in live if i < len(total_row["cells"]) and total_row["cells"][i] is not None]
    if len(live) < 6 or not tot_live:
        return None
    total_idx = tot_live[-1]
    value_idx = [i for i in live if i < total_idx]

    frags: dict[int, list[str]] = {}
    for i in value_idx:
        toks = [t for r in headers if i < len(r["cells"]) and (t := _fmt(r["cells"][i]))]
        if i < len(col_labels) and col_labels[i]:
            toks.append(str(col_labels[i]))
        frags[i] = toks
    if sum(1 for i in value_idx if _weight_candidates(frags[i])) < 4 and page_lines:
        return _model_from_lines(grid, page_lines, value_idx, total_idx)

    cols: list[tuple[int, str, float | None, int, str | None]] = []
    prev, prev_secured = -1.0, False
    for i in value_idx:
        text = fold(" ".join(frags[i]))
        secured = int(bool(_SECURED.search(text)))
        # weights never decrease left to right, and repeat only across a
        # secured / plain twin pair (secured first)
        cands = sorted(w for w in _weight_candidates(frags[i])
                       if w > prev or (w == prev and (secured or prev_secured)))
        if _OTHER_COL.search(text):       # "%150 %250 Diğerleri" is the others column
            cols.append((i, "other", None, 0, " ".join(frags[i]) or None))
        elif cands:
            w = cands[0]
            cols.append((i, "weight", w, secured, " ".join(frags[i]) or None))
            prev, prev_secured = w, bool(secured)
        elif not frags[i]:
            cols.append((i, "other", None, 0, None))
        else:
            cols.append((i, "unknown", None, secured, " ".join(frags[i]) or None))
    cols = _infer_secured(cols)
    if sum(1 for c in cols if c[1] == "weight") < 4:
        return None
    lab = " ".join(_fmt(r["cells"][total_idx]) or "" for r in headers
                   if total_idx < len(r["cells"])).strip() or None
    cols.append((total_idx, "total", None, 0, lab))
    return cols


def _infer_secured(cols):
    """A mortgage-secured column whose weight wrapped out of reach can only
    be the template's 35% (residential) or 50% (commercial); between its
    neighbours' weights that is usually one value — take it, keep the flag."""
    out = list(cols)
    for k, (i, role, w, secured, lab) in enumerate(out):
        if role != "unknown" or not secured:
            continue
        lo = max((c[2] for c in out[:k] if c[1] == "weight"), default=0.0)
        hi = min((c[2] for c in out[k + 1:] if c[1] == "weight"), default=10000.0)
        fit = [x for x in (35.0, 50.0) if lo < x <= hi]   # secured prints before its plain twin
        if len(fit) == 1:
            out[k] = (i, "weight", fit[0], 1, lab)
    return out


def _model_from_lines(grid, lines: list[str], value_idx: list[int], total_idx: int):
    """Last resort: the weight row printed above the block in the page text.
    The line with the most "%N" tokens maps token-by-token onto the value
    columns; a non-weight token is a wrapped label (the mortgage-secured
    columns), filled from the weights on the line above, in order."""
    best, best_n = None, 0
    for i, ln in enumerate(lines):
        n = sum(1 for t in ln.split() if (m := _WTOKEN.match(t)) and int(m.group(1)) in _WEIGHTS)
        if n > best_n:
            best, best_n = i, n
    if best is None or best_n < 4:
        return None
    toks = lines[best].split()
    if toks and _TOTAL_COL.search(fold(toks[-1])):
        toks = toks[:-1]
    if len(toks) != len(value_idx):
        return None
    fill = [float(m.group(1)) for i, ln in enumerate(lines) if i != best
            for t in ln.split() if (m := _WTOKEN.match(t)) and int(m.group(1)) in _WEIGHTS]
    cols: list[tuple[int, str, float | None, int, str | None]] = []
    prev = -1.0
    for i, t in zip(value_idx, toks):
        m = _WTOKEN.match(t)
        if m and int(m.group(1)) in _WEIGHTS:
            w = float(m.group(1))
            if w < prev:
                return None
            cols.append((i, "weight", w, 0, t))
            prev = w
        elif _OTHER_COL.search(fold(t)):
            cols.append((i, "other", None, 0, t))
        elif fill:
            w = fill.pop(0)
            if w < prev:
                return None
            cols.append((i, "weight", w, 1, t))
            prev = w
        else:
            return None
    cols.append((total_idx, "total", None, 0, None))
    return cols


def _is_cr5(grid: list[dict]) -> bool:
    if NT.live_value_columns(grid, MAX_ROW) < 8:      # CR4 prints six
        return False
    return any(NT.rowno(r, MAX_ROW) == 1 and _ROW1.search(
        fold(NT._LABEL_PREFIX.sub("", (r["label"] or "").strip()))) for r in grid)


def _identity_holds(inst: list[dict], step: float = 1.0) -> bool:
    """total = Σ columns on the total row (by label — row 17 or 18 depending
    on the template vintage) and on ≥90% of value-bearing rows; `step` is one
    unit of the filing's print in canonical thousands (1000 for a filing in
    millions), so rounding in the source is not a failure."""
    by_row: dict[int, dict] = {}
    is_total: dict[int, bool] = {}
    for x in inst:
        by_row.setdefault(x["template_row"], {})[x["col_role"], x["col_order"]] = x["amount"]
        is_total[x["template_row"]] = x["role"] == "total"
    checked = ok = 0
    total_ok = False
    for n, cells in by_row.items():
        tot = next((v for (role, _o), v in cells.items() if role == "total"), None)
        parts = [v for (role, _o), v in cells.items() if role != "total" and v is not None]
        if tot is None or not parts:
            continue
        hit = abs(sum(parts) - tot) <= max(2.0 * step, 1e-5 * abs(tot))
        if is_total[n]:
            total_ok = hit
        else:
            checked += 1
            ok += int(hit)
    return total_ok and checked >= 3 and ok / checked >= 0.9


def _lines_above(cap: sqlite3.Connection | None, key: tuple, page: int, block_id: int,
                 span: int = 8) -> list[str] | None:
    """The page-text lines just above a captured block, from the capture
    ledger — where the PDF printed the weight header."""
    if cap is None:
        return None
    first = cap.execute(
        "SELECT first_line FROM bank_audit_document_blocks WHERE bank_ticker=? "
        "AND period=? AND kind=? AND page=? AND block_id=?", (*key, page, block_id)).fetchone()
    if not first:
        return None
    return [t for (t,) in cap.execute(
        "SELECT text FROM bank_audit_document_lines WHERE bank_ticker=? AND period=? "
        "AND kind=? AND page=? AND line_order>=? AND line_order<? AND block_id IS NULL "
        "ORDER BY line_order", (*key, page, first[0] - span, first[0]))]


def assemble(tab: sqlite3.Connection, key: tuple,
             cap: sqlite3.Connection | None = None) -> dict | None:
    blocks = tab.execute(
        "SELECT page, block_id, grid_json, col_labels_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    found = [(pg, bid, json.loads(g), json.loads(cl or "[]"), unit)
             for pg, bid, g, cl, unit in blocks if _is_cr5(json.loads(g))]
    if not found:
        return None
    unit = found[0][4]
    factor = U.UNIT_SCALE.get(unit)
    instances: list[list[dict]] = []
    no_header = 0
    for pg, bid, grid, col_labels, _u in found:
        cols = column_model(grid, col_labels)
        if cols is None:
            cols = column_model(grid, col_labels, _lines_above(cap, key, pg, bid))
        if cols is None:
            no_header += 1
            continue
        rows: list[dict] = []
        last_no = 0
        for r in grid:
            n = NT.rowno(r, MAX_ROW)
            if n is None:
                continue
            label = NT._LABEL_PREFIX.sub("", (r["label"] or "").strip())
            if not label:
                continue
            if n <= last_no and rows:
                instances.append(rows)
                rows = []
            last_no = n
            role = role_of(label)
            cells = r["cells"]
            for order, (i, col_role, w, secured, col_label) in enumerate(cols):
                v = num(cells[i]) if i < len(cells) else None
                if factor is not None:
                    v = U.scale_amount(v, factor)
                rows.append({"template_row": n, "label": label, "role": role,
                             "col_order": order, "risk_weight": w, "col_role": col_role,
                             "secured_re": secured, "col_label": col_label, "amount": v,
                             "page": pg, "block_id": bid})
        if rows:
            instances.append(rows)
    instances = [i for i in instances if any(x["role"] == "total" for x in i)]
    labels = ("current", "prior", "extra2", "extra3")
    return {"unit": unit, "step": float(factor or 1.0), "no_header": no_header,
            "instances": {labels[i]: inst for i, inst in enumerate(instances[:4])}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--capture-db", default=str(CAPTURE_DB),
                    help="capture ledger, for the weight header printed above a block")
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    tab = sqlite3.connect(f"file:{args.tables_db}?mode=ro", uri=True)
    cap = (sqlite3.connect(f"file:{args.capture_db}?mode=ro", uri=True)
           if Path(args.capture_db).exists() else None)
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

    def cr4_post_crm(key, label) -> float | None:
        try:
            row = tab.execute(
                "SELECT on_bs_post_crm, off_bs_post_crm FROM bank_audit_exposure_class_full "
                "WHERE bank_ticker=? AND period=? AND kind=? AND period_label=? "
                "AND template_row=18", (*key, label)).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row or (row[0] is None and row[1] is None):
            return None
        return (row[0] or 0.0) + (row[1] or 0.0)

    detected = written = gated = no_header = 0
    inst_count: Counter = Counter()
    weights_seen: Counter = Counter()
    unknown_cols = [0, 0]
    anchor = {"current": [0, 0], "prior": [0, 0]}
    mism = []
    for key in keys:
        got = assemble(tab, key, cap)
        if got is None:
            continue
        detected += 1
        no_header += got["no_header"]
        kept = {}
        for lab, inst in got["instances"].items():
            if _identity_holds(inst, got["step"]):
                kept[lab] = inst
            else:
                gated += 1
        if not kept:
            continue
        inst_count[len(kept)] += 1
        for lab, inst in kept.items():
            weights_seen[tuple(sorted({x["risk_weight"] for x in inst if x["risk_weight"] is not None}))] += 1
            cols = {(x["col_order"], x["col_role"]) for x in inst}
            unknown_cols[1] += len(cols)
            unknown_cols[0] += sum(1 for _o, role in cols if role == "unknown")
            if lab in anchor:
                grand = next((x["amount"] for x in inst if x["role"] == "total"
                              and x["col_role"] == "total"), None)
                ref = cr4_post_crm(key, lab)
                if grand is not None and ref:
                    anchor[lab][1] += 1
                    ok = abs(grand - ref) <= max(2.0, 1e-3 * abs(ref))
                    anchor[lab][0] += int(ok)
                    if not ok and lab == "current" and len(mism) < 6:
                        mism.append((key, grand, ref))
        if out is not None:
            out.execute("DELETE FROM bank_audit_risk_weight_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            for lab, inst in kept.items():
                out.executemany(
                    "INSERT INTO bank_audit_risk_weight_full VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(*key, lab, x["template_row"], x["label"], x["role"], x["col_order"],
                      x["risk_weight"], x["col_role"], x["secured_re"], x["col_label"],
                      x["amount"], x["page"], x["block_id"], got["unit"]) for x in inst])
                written += len(inst)
            out.commit()

    print(f"\npartitions: {len(keys)} scanned | detected {detected} | blocks without a "
          f"readable weight header: {no_header} | instances gated out by total = Σ weights: {gated}")
    if inst_count:
        print(f"instances per filing kept: {dict(sorted(inst_count.items()))}")
        print("weight sets seen:")
        for ws, c in weights_seen.most_common(6):
            print(f"    {c:4}  {[int(w) for w in ws]}")
    if unknown_cols[1]:
        print(f"  columns kept with an unreadable weight (col_role=unknown): "
              f"{unknown_cols[0]}/{unknown_cols[1]}")
    for lab, b in anchor.items():
        print(f"  grand total vs CR4 post-CRM on+off, {lab:8} (0.1%)      {b[0]:5}/{b[1]:5}"
              + (f"  {b[0] / b[1]:6.1%}" if b[1] else ""))
    for key, g, ref in mism:
        print(f"    {' '.join(key):32} cr5={g:,.0f} cr4={ref:,.0f} ({g / ref - 1:+.1%})")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_risk_weight_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
