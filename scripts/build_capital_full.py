#!/usr/bin/env python
"""The capital pilot: graduate the FULL own-funds table into analytical shape.

The first lane minted from the document layer instead of a PDF. The narrow
`bank_audit_capital` keeps 9 numbers of a disclosure the filing prints as a
~70-row regulatory template (Basel III own funds, whose row structure BRSA
mandates across all 38 banks in both languages). This builds
`bank_audit_capital_full`: every row of that template, typed, unit-normalized,
role-mapped where the registry pins the semantics — with the narrow lane
serving as the external validator (the wide table's CET1 total must equal
`bank_audit_capital.cet1_capital`, which five years of production already
vouch for).

How a partition is assembled:

  seed      the block containing the template's own opening row — "Bankanın
            tasfiyesi halinde … ödenmiş sermaye" / "paid-in capital to be
            entitled for compensation after all creditors". Regulatory, unique,
            and absent from the look-alike equity reconciliation table that
            follows pages later.
  chain     the template spans pages as separate captured blocks; blocks are
            chained in (page, block) order while pages stay contiguous and the
            block keeps speaking template vocabulary. The page gap before the
            reconciliation table is what ends the chain.
  columns   the LAST TWO aligned columns are Cari/Önceki Dönem (a stray
            leading furniture column appears on wrapped pages); one-column
            blocks carry current only.
  scaling   money rows scale declared_unit → canonical bin, exactly like every
            analytical lane; ratio/buffer rows (percentages) never scale.
            A printed "-" stays NULL — disclosed-nothing, never 0.

Dry-run (default) writes nothing and reports fleet numbers: detection vs the
narrow lane's coverage, per-anchor agreement, the tier1 = cet1 + at1 identity,
CAR ≈ total/rwa, role coverage, and the unmatched labels that would grow the
registry. `--write` stores rows into data/bank_audit_tables.db (local only —
the derived-lane DB; nothing here reaches the audit snapshot or D1).

  python scripts/build_capital_full.py                    # fleet dry-run
  python scripts/build_capital_full.py --bank AKBNK --period 2026Q1 --verbose
  python scripts/build_capital_full.py --write
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402

TABLES_DB = REPO / "data" / "bank_audit_tables.db"
AUDIT_DB = REPO / "data" / "bank_audit.db"

_TR_FOLD = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")


def fold(s: str | None) -> str:
    return (s or "").translate(_TR_FOLD).upper()


# The template's opening row — the seed. The equity-to-own-funds
# reconciliation table reprints CET1 labels but never this row.
_SEED = re.compile(
    r"TASFIYESI H[AÂ]LINDE.*ODENMIS SERMAYE|"
    r"ENTITLED FOR COMPENSATION AFTER ALL (CREDITORS|OTHER CREDITORS)|"
    r"PAID-IN CAPITAL.*AFTER ALL CREDITORS|"
    r"PAID.?IN CAPITAL.*CLAIM IN LIQUIDATION|"          # QNBFB's wording
    r"ODENMIS SERMAYE.*TASFIYE")
# The second dialect: YKBNK/ALBRK-style filings open the template with the
# bare section header as the block's first row instead of the tasfiyesi
# opener. Only a LARGE block counts — the header also opens the 4-row
# summary/reconciliation snippets in the notes.
_SEED_HEADER = re.compile(r"^(COMMON EQUITY TIER 1 CAPITAL|CEKIRDEK SERMAYE)$")
_SEED_HEADER_MIN_ROWS = 15
# The third dialect: the abbreviated own-funds table (FIBA) opens on a bare
# "Sermaye" / "Capital" row followed by the share-issue-premium row. The
# pair is the signature — either row alone appears all over the notes.
_SEED_PAIR = (re.compile(r"^(SERMAYE|CAPITAL|PAID.?IN CAPITAL|ODENMIS SERMAYE)$"),
              re.compile(r"^(HISSE SENEDI IHRAC PRIM|SHARE ISSUE PREMIUM|SHARE PREMIUM)"))
_SEED_PAIR_MIN_ROWS = 10
# The fourth dialect: the block carries the note's own title and says CARI
# DONEM, but opens partway down the template so none of the seed lines are
# in it. ZIRAAT 2022Q1/Q2 print the current table that way and the prior
# table in full below it, so the first seed the scan met was the PRIOR
# opener -- and 135,100,145, ZIRAAT's 31 December 2021 own funds, was stored
# as June 2022's against the narrow lane's 196,252,360.
_SEED_TITLE = re.compile(r"OZKAYNAK KALEMLERINE ILISKIN BILGILER|"
                         r"INFORMATION (ON|ABOUT) (THE )?(SHAREHOLDERS.? |OWN )?(EQUITY|FUNDS?) ITEMS")
_SEED_TITLE_MIN_ROWS = 20
_CURRENT_PERIOD = re.compile(r"\bCARI DONEM\b|\bCURRENT PERIOD\b")
_PRIOR_PERIOD = re.compile(r"\bONCEKI DONEM\b|\bPRIOR PERIOD\b|\bPREVIOUS PERIOD\b")

# A chained block must keep speaking the template's vocabulary.
_VOCAB = re.compile(
    r"SERMAYE|TIER|INDIRIM|DEDUCT|TAMPON|BUFFER|ORANI|RATIO|"
    r"RISK AGIRLIKLI|RISK WEIGHTED|OZKAYNAK|OWN FUNDS|CAPITAL|THRESHOLD|ESIK")

# A row that is a date caption, not data ("31 MART 2026" carrying [2026, 2025]).
_DATE_ROW = re.compile(
    r"^\(?\d{1,2}[./ ]\s*(OCAK|SUBAT|MART|NISAN|MAYIS|HAZIRAN|TEMMUZ|AGUSTOS|"
    r"EYLUL|EKIM|KASIM|ARALIK|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|"
    r"AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b")

# Percent-natured rows: never unit-scaled. The template prints its ratios and
# buffers in the same column as the amounts.
_PERCENT_ROW = re.compile(r"ORANI|RATIO|TAMPON|BUFFER|\(%\)|^%")

# Role registry — high-precision only, folded-uppercase regex per role, both
# languages. `last=True` roles are post-deduction totals: the template prints
# "before deductions" first, the total after, so the LAST amount-bearing match
# is the total. Growing this registry is how the lane widens safely: an
# unmatched row is stored with role NULL, never guessed.
ROLES: list[tuple[str, re.Pattern, bool]] = [
    ("paid_in_capital", _SEED, False),
    ("share_premium", re.compile(r"^HISSE SENEDI IHRAC PRIMLERI$|^SHARE PREMIUM"), False),
    ("reserves", re.compile(r"^YEDEK AKCELER$|^RESERVES$|^LEGAL RESERVES$"), False),
    ("oci_tas", re.compile(r"TMS\)? UYARINCA OZKAYNAKLARA YANSITILAN|"
                           r"COMPREHENSIVE INCOME ACCORDING TO TAS"), False),
    ("profit", re.compile(r"^K[AÂ]R$|^PROFIT$"), False),
    # Line-start anchored: "BONUS SHARES … NOT ACCOUNTED IN CURRENT PERIOD'S
    # PROFIT" contains the phrase mid-label and was stealing the role.
    ("net_profit", re.compile(r"^NET DONEM K[AÂ]RI|^NET CURRENT PERIOD PROFIT|"
                              r"^CURRENT PERIOD.{0,2}S? PROFIT$"), False),
    ("prior_profit", re.compile(r"^GECMIS YILLAR K[AÂ]RI|"
                                r"^PRIOR PERIODS?.{0,2} PROFIT$"), False),
    ("bonus_shares", re.compile(r"^BONUS SHARES FROM ASSOCIATES|"
                                r"BEDELSIZ HISSELER"), False),
    ("minority_interest", re.compile(r"^AZINLIK PAYLARI|MINORITY (SHARES|INTEREST)"), False),
    ("cet1_before_deductions", re.compile(
        r"INDIRIMLER ONCESI CEKIRDEK SERMAYE|"
        r"COMMON EQUITY TIER (I|1) CAPITAL BEFORE DEDUCTIONS"), False),
    ("cet1_deductions", re.compile(
        r"CEKIRDEK SERMAYEDEN YAPILAN INDIRIMLER TOPLAMI|"
        r"TOTAL DEDUCTIONS FROM COMMON EQUITY TIER I"), False),
    ("cet1_total", re.compile(
        r"^CEKIRDEK SERMAYE TOPLAMI|^TOTAL COMMON EQUITY TIER (I|1) CAPITAL"), True),
    ("at1_before_deductions", re.compile(
        r"^INDIRIMLER ONCESI ILAVE ANA SERMAYE|"
        r"^ADDITIONAL TIER (I|1) CAPITAL BEFORE DEDUCTIONS"), False),
    ("at1_total", re.compile(
        r"^ILAVE ANA SERMAYE TOPLAMI|^TOTAL ADDITIONAL TIER (I|1) CAPITAL"), True),
    ("tier1_total", re.compile(
        r"^ANA SERMAYE TOPLAMI|^TOTAL TIER (I|1) CAPITAL|"
        r"^TIER (I|1) CAPITAL \(TIER I"), True),
    ("tier2_before_deductions", re.compile(
        r"^INDIRIMLER ONCESI KATKI SERMAYE|^TIER (II|2) CAPITAL BEFORE DEDUCTIONS"), False),
    ("tier2_general_provisions", re.compile(
        r"^KARSILIKLAR \(BANKALARIN OZKAYNAKLARINA|"
        r"^PROVISIONS \(AMOUNTS EXPLAINED|"
        r"^STANDART YAKLASIMIN KULLANILDIGI ALACAKLAR ICIN AYRILAN GENEL KARSILIK|"
        r"^GENERAL (LOAN )?PROVISIONS FOR EXPOSURES IN STANDARD APPROACH"), False),
    ("loss_not_covered_by_reserves", re.compile(
        r"^NET DONEM ZARARI ILE GECMIS YILLAR ZARARI TOPLAMININ YEDEK AKCELER|"
        r"LOSSES (THAT CANNOT|NOT) (BE )?COVERED BY RESERVES"), False),
    ("tier2_total", re.compile(
        r"^KATKI SERMAYE TOPLAMI|^TOTAL TIER (II|2) CAPITAL"), True),
    # AKBNK prints TWO own-funds totals: the ANA+KATKI sum — the row the
    # narrow lane has served for five years, hence the anchor — and, after the
    # Banking-Law deduction block, the regulatory FINAL the ratios divide by.
    ("total_own_funds", re.compile(
        r"^TOPLAM OZKAYNAK \(ANA SERMAYE VE KATKI|"
        r"^ANA SERMAYE VE KATKI SERMAYE TOPLAMI \(TOPLAM OZKAYNAK\)|"
        r"^TOTAL CAPITAL \(TIER (I|1) (CAPITAL )?(\+|AND) TIER (II|2)|"
        r"^TOTAL CAPITAL \((THE SUM OF|TOTAL OF) TIER (I|1)|"
        r"^TOTAL EQUITY \(TOTAL TIER (I|1) AND TIER (II|2)|"
        r"^OZKAYNAK \(ANA SERMAYE|^CAPITAL \(TIER (I|1)"), False),
    ("total_own_funds_final", re.compile(
        r"^TOPLAM OZKAYNAK$|^TOTAL CAPITAL$|TOTAL OWN FUNDS"), True),
    # Anchored at line start: "ADDITIONAL CET1 CAPITAL OVER TOTAL RISK
    # WEIGHTED ASSETS RATIO …" contains the phrase and is a ratio row.
    ("total_rwa", re.compile(
        r"^TOPLAM RISK AGIRLIKLI TUTARLAR|^TOTAL RISK WEIGHTED (AMOUNTS|ASSETS)"), True),
    ("cet1_ratio", re.compile(
        r"(KONSOLIDE )?CEKIRDEK SERMAYE YETERLILIGI ORANI|"
        r"COMMON EQUITY TIER (I|1) CAPITAL (ADEQUACY )?RATIO"), True),
    ("tier1_ratio", re.compile(
        r"^(KONSOLIDE )?ANA SERMAYE YETERLILIGI ORANI|"
        r"^TIER (I|1) CAPITAL (ADEQUACY )?RATIO"), True),
    ("capital_adequacy_ratio", re.compile(
        r"^(KONSOLIDE )?SERMAYE YETERLILIGI (STANDART )?ORANI|"
        r"CAPITAL ADEQUACY (STANDARD )?RATIO"), True),
    ("total_buffer_requirement", re.compile(
        r"TOPLAM ILAVE CEKIRDEK SERMAYE GEREKSINIM(I)? ORANI|"
        r"TOTAL ADDITIONAL COMMON EQUITY TIER (I|1).*RATIO"), False),
    ("bank_specific_cet1_ratio", re.compile(
        r"^BANKAYA OZGU TOPLAM CEKIRDEK SERMAYE ORANI|"
        r"BANK.?SPECIFIC TOTAL COMMON EQUITY TIER (I|1).*RATIO"), False),
    ("capital_conservation_buffer", re.compile(
        r"SERMAYE KORUMA TAMPONU|CAPITAL CONSERVATION BUFFER"), False),
    ("countercyclical_buffer", re.compile(
        r"DONGUSEL SERMAYE TAMPONU|COUNTERCYCLICAL (CAPITAL )?BUFFER"), False),
]

# Wide-lane roles → the narrow lane's columns. The anchor: production has
# served these figures for five years, so the wide read must reproduce them.
ANCHOR_MAP = {
    "cet1_total": "cet1_capital",
    "at1_total": "additional_tier1_capital",
    "tier1_total": "tier1_capital",
    "tier2_total": "tier2_capital",
    "total_own_funds": "total_capital",
    "total_rwa": "total_rwa",
    "cet1_ratio": "cet1_ratio",
    "tier1_ratio": "tier1_ratio",
    "capital_adequacy_ratio": "capital_adequacy_ratio",
}
_RATIO_ROLES = {"cet1_ratio", "tier1_ratio", "capital_adequacy_ratio",
                "capital_conservation_buffer", "countercyclical_buffer",
                "total_buffer_requirement", "bank_specific_cet1_ratio"}

DDL = """
CREATE TABLE IF NOT EXISTS bank_audit_capital_full (
    bank_ticker  TEXT NOT NULL,
    period       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    page         INTEGER NOT NULL,
    block_id     INTEGER NOT NULL,
    row_order    INTEGER NOT NULL,
    label        TEXT NOT NULL,
    row_role     TEXT,
    -- canonical thousand TL for money rows (declared_unit scaled through at
    -- mint, like every analytical lane); percentages for ratio/buffer rows,
    -- never scaled. NULL = the filing printed "-" or nothing: not zero.
    amount       REAL,
    amount_prior REAL,
    source_unit  TEXT,
    PRIMARY KEY (bank_ticker, period, kind, page, block_id, row_order)
);
CREATE INDEX IF NOT EXISTS idx_capital_full_role
  ON bank_audit_capital_full(row_role);
"""


def _num(cell) -> float | None:
    return float(cell) if isinstance(cell, (int, float)) else None


_LANDMARKS = ("cet1_total", "at1_total", "tier1_total", "tier2_total",
              "total_own_funds", "total_own_funds_final", "total_rwa",
              "capital_adequacy_ratio")


def mint_gate(roles: dict) -> bool:
    """The own-funds form has no single sum to check, so the gate is its
    landmarks plus one of its two identities: an instance is stored only if
    it carries at least four of the template's aggregate rows AND either
    tier 1 = CET1 + AT1 or the printed CAR equals total / RWA.

    Without it a shareholders'-equity note passes for the form — AKBNK's
    "Ödenmiş Sermaye / Hisse Senedi İhraç Primleri / Yedek Akçeler" block
    seeded the chain and shipped 14.7bn as CET1 against the narrow lane's
    89.5bn.
    """
    def g(name):
        return (roles.get(name) or {}).get("cur")

    land = sum(1 for name in _LANDMARKS if g(name) is not None)
    if land < 4:
        return False
    c1, a1, t1 = g("cet1_total"), g("at1_total"), g("tier1_total")
    if None not in (c1, t1) and abs((c1 + (a1 or 0.0)) - t1) <= max(2.0, 1e-5 * abs(t1)):
        return True
    tot = g("total_own_funds_final") or g("total_own_funds")
    rwa, car = g("total_rwa"), g("capital_adequacy_ratio")
    return None not in (tot, rwa, car) and bool(rwa) and abs(tot / rwa * 100 - car) <= 0.15


def assemble(tab: sqlite3.Connection, key: tuple) -> dict | None:
    """Seed + chain the own-funds blocks of one partition; return rows."""
    blocks = tab.execute(
        "SELECT page, block_id, n_cols, grid_json, declared_unit "
        "FROM bank_audit_document_tables WHERE bank_ticker=? AND period=? "
        "AND kind=? ORDER BY page, block_id", key).fetchall()
    seed_at = None
    for i, (pg, bid, nc, g, unit) in enumerate(blocks):
        grid = json.loads(g)
        pair = (len(grid) >= _SEED_PAIR_MIN_ROWS
                and _SEED_PAIR[0].match(fold(grid[0]["label"] or "").strip())
                and _SEED_PAIR[1].match(fold(grid[1]["label"] or "").strip()))
        head = fold(" ".join(r["label"] or "" for r in grid[:6]))
        titled = (len(grid) >= _SEED_TITLE_MIN_ROWS
                  and _SEED_TITLE.search(head)
                  and _CURRENT_PERIOD.search(head) and not _PRIOR_PERIOD.search(head))
        if any(_SEED.search(fold(r["label"])) for r in grid[:6]) or pair or titled or (
                len(grid) >= _SEED_HEADER_MIN_ROWS
                and _SEED_HEADER.match(fold(grid[0]["label"]))):
            seed_at = i
            break
    if seed_at is None:
        return None

    chained, last_pg = [], None
    for pg, bid, nc, g, unit in blocks[seed_at:]:
        if last_pg is not None and pg > last_pg + 1:
            break
        grid = json.loads(g)
        labelled = [r for r in grid if r["label"]]
        vocab = sum(1 for r in labelled if _VOCAB.search(fold(r["label"])))
        if last_pg is not None and (not labelled or vocab < len(labelled) * 0.5):
            break
        chained.append((pg, bid, grid, unit))
        last_pg = pg

    unit = chained[0][3]
    factor = U.UNIT_SCALE.get(unit)
    rows, order = [], 0
    seen_seed = truncated = False
    for pg, bid, grid, _u in chained:
        if truncated:
            break
        for r in grid:
            label = (r["label"] or "").strip()
            flabel = fold(label)
            if not label or _DATE_ROW.match(flabel):
                continue
            # A SECOND opener row is a second copy of the whole template —
            # some filers print the current-period table and then the
            # prior-period one in full. Truncate there (break, so the role
            # mapping and scaling below still run over what was kept): the
            # wide lane's two value columns already carry both periods for the
            # single-template form, and letting the copy in handed every
            # last-match role the PRIOR template's row (ISCTR 2024Q1's at1
            # read tier1-sized).
            if _SEED.search(flabel):
                if seen_seed and order > 5:
                    truncated = True
                    break
                seen_seed = True
            cells = r["cells"]
            cur = _num(cells[-2]) if len(cells) >= 2 else \
                (_num(cells[-1]) if cells else None)
            pri = _num(cells[-1]) if len(cells) >= 2 else None
            rows.append({"page": pg, "block_id": bid, "row_order": order,
                         "label": label, "flabel": flabel,
                         "cur": cur, "pri": pri})
            order += 1

    # role mapping: per role the first/last amount-bearing match, and the
    # percent exemption applied to scaling below.
    for role, rx, last in ROLES:
        hits = [r for r in rows if rx.search(r["flabel"])]
        with_amt = [r for r in hits if r["cur"] is not None]
        pick = (with_amt or hits)
        if pick:
            (pick[-1] if last else pick[0])["role"] = role

    for r in rows:
        percent = r.get("role") in _RATIO_ROLES or \
            (r.get("role") is None and _PERCENT_ROW.search(r["flabel"]))
        if not percent and factor is not None:
            r["cur"] = U.scale_amount(r["cur"], factor)
            r["pri"] = U.scale_amount(r["pri"], factor)
    return {"rows": rows, "unit": unit, "blocks": len(chained),
            "pages": sorted({pg for pg, *_ in chained})}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables-db", default=str(TABLES_DB))
    ap.add_argument("--audit-db", default=str(AUDIT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind")
    ap.add_argument("--write", action="store_true",
                    help="store rows into bank_audit_capital_full (local "
                         "derived-lane DB); default is a dry-run report")
    ap.add_argument("--verbose", action="store_true")
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

    narrow_parts = {tuple(r) for r in aud.execute(
        "SELECT DISTINCT bank_ticker, period, kind FROM bank_audit_capital")}

    detected = 0
    width = Counter()
    role_cov = Counter()
    agree = defaultdict(lambda: [0, 0])          # role -> [ok, compared]
    mism: list[tuple] = []
    ident = [0, 0]
    ratio_id = [0, 0]
    unmatched = Counter()
    written = gated = 0
    gated_keys: list[tuple] = []
    for key in keys:
        got = assemble(tab, key)
        if got is None:
            continue
        detected += 1
        rows = got["rows"]
        roles = {r["role"]: r for r in rows if r.get("role")}
        if not mint_gate(roles):
            gated += 1
            if len(gated_keys) < 8:
                gated_keys.append(key)
            continue
        width[len(rows)] += 1
        role_cov[len(roles)] += 1
        for r in rows:
            if not r.get("role") and r["cur"] is not None \
                    and _VOCAB.search(r["flabel"]):
                unmatched[r["flabel"][:64]] += 1

        # anchors vs the narrow lane (any period_type row of the partition —
        # own funds is point-in-time, the values agree across period_types)
        nrow = aud.execute(
            "SELECT cet1_capital, additional_tier1_capital, tier1_capital, "
            "tier2_capital, total_capital, total_rwa, cet1_ratio, tier1_ratio, "
            "capital_adequacy_ratio FROM bank_audit_capital "
            "WHERE bank_ticker=? AND period=? AND kind=?", key).fetchall()
        if nrow:
            cols = ("cet1_capital", "additional_tier1_capital", "tier1_capital",
                    "tier2_capital", "total_capital", "total_rwa", "cet1_ratio",
                    "tier1_ratio", "capital_adequacy_ratio")
            narrow = {c: {row[i] for row in nrow if row[i] is not None}
                      for i, c in enumerate(cols)}
            for role, ncol in ANCHOR_MAP.items():
                # The narrow lane is itself inconsistent about WHICH own-funds
                # total it stored — AKBNK's rows hold the ANA+KATKI sum,
                # ANADOLU's the post-deduction final (the ~200-unit deltas in
                # the first dry-run proved it). Either printed total counts as
                # agreement; the wide lane keeps both as separate roles.
                if role == "total_own_funds":
                    cands = [roles.get("total_own_funds", {}).get("cur"),
                             roles.get("total_own_funds_final", {}).get("cur")]
                    cands = [c for c in cands if c is not None]
                else:
                    cands = [roles.get(role, {}).get("cur")]
                    cands = [c for c in cands if c is not None]
                have = narrow.get(ncol) or set()
                if not cands or not have:
                    continue
                wide = cands[0]
                tol = 0.06 if role in _RATIO_ROLES else 1.5
                ok = any(abs(c - v) <= tol for c in cands for v in have)
                agree[role][1] += 1
                agree[role][0] += int(ok)
                if not ok and len(mism) < 12:
                    mism.append((key, role, wide, sorted(have)))

        # internal identities
        c1 = roles.get("cet1_total", {}).get("cur")
        a1 = roles.get("at1_total", {}).get("cur")
        t1 = roles.get("tier1_total", {}).get("cur")
        if None not in (c1, t1):
            ident[1] += 1
            ident[0] += int(abs((c1 + (a1 or 0.0)) - t1) <= 2)
        # The printed CAR divides the FINAL total (after the Banking-Law
        # deduction block), not the ANA+KATKI sum the narrow lane stores.
        tot = (roles.get("total_own_funds_final", {}).get("cur")
               or roles.get("total_own_funds", {}).get("cur"))
        rwa = roles.get("total_rwa", {}).get("cur")
        car = roles.get("capital_adequacy_ratio", {}).get("cur")
        if None not in (tot, rwa, car) and rwa:
            ratio_id[1] += 1
            ratio_id[0] += int(abs(tot / rwa * 100 - car) <= 0.15)

        if args.verbose:
            print(f"{' '.join(key)}: {len(rows)} rows / {got['blocks']} blocks "
                  f"pages {got['pages']} unit={got['unit']} roles={len(roles)}")
        if out is not None:
            out.execute("DELETE FROM bank_audit_capital_full WHERE "
                        "bank_ticker=? AND period=? AND kind=?", key)
            out.executemany(
                "INSERT INTO bank_audit_capital_full VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(*key, r["page"], r["block_id"], r["row_order"], r["label"],
                  r.get("role"), r["cur"], r["pri"], got["unit"]) for r in rows])
            out.commit()
            written += len(rows)

    import statistics
    n_width = sorted(width.elements())
    both = [k for k in keys if k in narrow_parts]
    print(f"\npartitions: {len(keys)} scanned | detected {detected} | "
          f"refused by the mint gate (landmarks + an identity): {gated} | "
          f"narrow-lane partitions present locally {len(both)}")
    if gated_keys:
        print("  first refused: " + ", ".join(" ".join(k) for k in gated_keys[:4]))
    if n_width:
        print(f"width: median {statistics.median(n_width):.0f} rows "
              f"(min {n_width[0]}, max {n_width[-1]}) vs 9 fields in the narrow lane")
    if role_cov:
        cov = sorted(role_cov.elements())
        print(f"role coverage: median {cov[len(cov) // 2]} of {len(ROLES)} roles")
    print("\nanchor agreement vs bank_audit_capital:")
    for role in ANCHOR_MAP:
        ok, n = agree[role]
        print(f"  {role:26} {ok:5}/{n:5}  {ok/n:6.1%}" if n else
              f"  {role:26}     -/-")
    print(f"tier1 = cet1 + at1:          {ident[0]}/{ident[1]}"
          + (f"  {ident[0]/ident[1]:.1%}" if ident[1] else ""))
    print(f"CAR = total/rwa (±0.15):     {ratio_id[0]}/{ratio_id[1]}"
          + (f"  {ratio_id[0]/ratio_id[1]:.1%}" if ratio_id[1] else ""))
    if mism:
        print("\nfirst mismatches:")
        for key, role, wide, have in mism:
            print(f"  {' '.join(key):32} {role:22} wide={wide} narrow={have}")
    if unmatched:
        print("\ntop unmatched amount-bearing template rows (registry growth):")
        for lab, n in unmatched.most_common(10):
            print(f"  {n:5}  {lab}")
    if out is not None:
        print(f"\nwrote {written:,} rows to bank_audit_capital_full")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
