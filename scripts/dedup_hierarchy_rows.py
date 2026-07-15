"""One-time cleanup of duplicate / junk hierarchy rows in the frozen BS/PL tables.

Three classes of pre-existing extraction defect, each leaving a (bank, period, kind,
hierarchy) code DUPLICATED. Data-only (no re-extraction); values are only ever
DELETED (garbage) or their KEY re-coded — never edited.

1. HEADER / PLACEHOLDER JUNK (59 P&L rows) — DELETE.
   A statement TITLE ("STATEMENT OF PROFIT OR LOSS", "KAR VEYA ZARAR TABLOSU") or a
   template placeholder ("...doldurulacaktır.)") was mis-parsed as a data row with a
   garbage amount (<=202) and stamped with a nearby real line's roman code. Verified
   fleet-wide: the tight title/placeholder match hits exactly these, max |amount| =
   202, zero rows >= 1000 — so no real value is ever removed.

2. MIS-NUMBERED REAL ROWS — RE-CODE (key only).
   Two real lines collide on one code because the lower section was extracted one
   numeral short / shifted. The ARABIC sub-codes (18.1, 20.1, 23.1...) and the P&L
   arithmetic confirm the TRUE numbers:
     - TSKB 2025Q1/Q2/Q3 assets: Current Tax Asset VII. -> VIII. (VIII. free; catalog).
     - TOMK 2025Q2/Q3 P&L: tax XVII. -> XVIII., disc-tax XXII. -> XXIII. (targets free).
     - DUNYAK 2023Q4 P&L: 2 junk placeholders deleted above; recode the shifted block
       (loan-prov XI->IX, personnel XII->XI, other-opex XIII->XII, net-op XII->XIII);
       arithmetic: VIII 108466 - IX 71 - XI 43587 - XII 51811 = XIII 12997. ✓
     - TOMK 2023Q3 P&L: whole lower section is +1 (X->XI ... XXIV->XXV) with a stray
       XIII(ord47)->XIX; the arabic sub-codes already encode the true numbers.
   These are currently FAILING the pl_chain roman-identity checks; the recode CLEARS
   the failure (verified by re-running the validator on the corrected rows).

NOT TOUCHED — EXIM/VAKBN off_balance duplicate code (Forward-Sell "3.2.2.2" /
"Diğer Cayılamaz Taahhütler" 2.1.12): a known SOURCE typo, deliberately leave-flagged
(fidelity to the filed PDF), currently accepted by the off_balance validator.

Flow: apply to the R2 snapshot (master) + live D1, then refresh bank_audit_validation
and the coverage spine via sync_audit_expected.py --push. --dry-run applies to the
pulled snapshot, re-validates the recoded partitions, prints, and pushes nothing.

  python scripts/dedup_hierarchy_rows.py --dry-run
  python scripts/dedup_hierarchy_rows.py
"""
from __future__ import annotations

import shutil
import gzip
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import r2_storage  # noqa: E402
from scripts.audit_d1 import (  # noqa: E402
    guard_against_ci_writers,
    push_snapshot,
    retry_wrangler,
)
from scripts.revalidate_audit_db import revalidate_partition  # noqa: E402

DB = REPO / "data" / "bank_audit.db"
GZ = REPO / "data" / "bank_audit.db.gz"
SNAP = "state/bank_audit.db.gz"

# --- 1. Header / placeholder junk (DELETE) --------------------------------
JUNK_WHERE = (
    "(item_name LIKE '%STATEMENT OF PROFIT OR LOSS%' OR item_name LIKE '%STATEMENTOFPROFITORLOSS%' "
    "OR item_name LIKE '%INCOME STATEMENT%' OR item_name LIKE '%STATEMENT OF INCOME%' "
    "OR item_name LIKE '%STATEMENTS OF INCOME%' OR item_name LIKE '%ZARAR TABLOSU%' "
    "OR item_name LIKE '%ZARARTABLOSU%' OR item_name LIKE '%doldurulacak%') "
    "AND (amount IS NULL OR ABS(amount) < 1000)"
)
JUNK_DELETE = f"DELETE FROM bank_audit_profit_loss WHERE {JUNK_WHERE}"
EXPECT_JUNK = 59

# --- 2. Mis-numbered rows (RE-CODE key only) ------------------------------
# (bank, period, kind, item_order, new_hierarchy)
PL_RECODES = [
    ("TOMK", "2025Q2", "unconsolidated", 43, "XVIII."),
    ("TOMK", "2025Q2", "unconsolidated", 57, "XXIII."),
    ("TOMK", "2025Q3", "unconsolidated", 43, "XVIII."),
    ("TOMK", "2025Q3", "unconsolidated", 57, "XXIII."),
    ("DUNYAK", "2023Q4", "unconsolidated", 36, "IX."),
    ("DUNYAK", "2023Q4", "unconsolidated", 37, "XI."),
    ("DUNYAK", "2023Q4", "unconsolidated", 38, "XII."),
    ("DUNYAK", "2023Q4", "unconsolidated", 39, "XIII."),
    ("TOMK", "2023Q3", "unconsolidated", 36, "XI."),
    ("TOMK", "2023Q3", "unconsolidated", 37, "XII."),
    ("TOMK", "2023Q3", "unconsolidated", 38, "XIII."),
    ("TOMK", "2023Q3", "unconsolidated", 39, "XIV."),
    ("TOMK", "2023Q3", "unconsolidated", 40, "XV."),
    ("TOMK", "2023Q3", "unconsolidated", 41, "XVI."),
    ("TOMK", "2023Q3", "unconsolidated", 42, "XVII."),
    ("TOMK", "2023Q3", "unconsolidated", 43, "XVIII."),
    ("TOMK", "2023Q3", "unconsolidated", 47, "XIX."),
    ("TOMK", "2023Q3", "unconsolidated", 48, "XX."),
    ("TOMK", "2023Q3", "unconsolidated", 52, "XXI."),
    ("TOMK", "2023Q3", "unconsolidated", 56, "XXII."),
    ("TOMK", "2023Q3", "unconsolidated", 57, "XXIII."),
    ("TOMK", "2023Q3", "unconsolidated", 61, "XXIV."),
    ("TOMK", "2023Q3", "unconsolidated", 62, "XXV."),
]
# (bank, period, kind, statement, item_order, new_hierarchy)
BS_RECODES = [
    ("TSKB", "2025Q1", "consolidated", "assets", 44, "VIII."),
    ("TSKB", "2025Q2", "consolidated", "assets", 44, "VIII."),
    ("TSKB", "2025Q3", "consolidated", "assets", 43, "VIII."),
]
# Partitions whose P&L / assets verdict should FLIP to passing after the recode.
RECODE_PARTS = [
    ("DUNYAK", "2023Q4", "unconsolidated", "profit_loss"),
    ("TOMK", "2023Q3", "unconsolidated", "profit_loss"),
    ("TOMK", "2025Q2", "unconsolidated", "profit_loss"),
    ("TOMK", "2025Q3", "unconsolidated", "profit_loss"),
    ("TSKB", "2025Q1", "consolidated", "assets"),
    ("TSKB", "2025Q2", "consolidated", "assets"),
    ("TSKB", "2025Q3", "consolidated", "assets"),
]


def _pl_update(b, p, k, o, new):
    return (f"UPDATE bank_audit_profit_loss SET hierarchy='{new}' "
            f"WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}' AND item_order={o}")


def _bs_update(b, p, k, st, o, new):
    return (f"UPDATE bank_audit_balance_sheet SET hierarchy='{new}' "
            f"WHERE bank_ticker='{b}' AND period='{p}' AND kind='{k}' "
            f"AND statement='{st}' AND item_order={o}")


def _apply_local(conn: sqlite3.Connection) -> None:
    n = conn.execute(f"SELECT COUNT(*) FROM bank_audit_profit_loss WHERE {JUNK_WHERE}").fetchone()[0]
    if n != EXPECT_JUNK:
        sys.exit(f"[dedup] ABORT: junk-delete matches {n} rows, expected {EXPECT_JUNK} — investigate")
    conn.execute(JUNK_DELETE)
    print(f"[dedup] deleted {n} header/placeholder junk rows")
    for r in PL_RECODES:
        c = conn.execute(_pl_update(*r)).rowcount
        if c != 1:
            sys.exit(f"[dedup] ABORT: PL recode {r} touched {c} rows, expected 1")
    for r in BS_RECODES:
        c = conn.execute(_bs_update(*r)).rowcount
        if c != 1:
            sys.exit(f"[dedup] ABORT: BS recode {r} touched {c} rows, expected 1")
    print(f"[dedup] re-coded {len(PL_RECODES)} P&L + {len(BS_RECODES)} BS rows")
    conn.commit()


def _all_sql() -> str:
    stmts = [JUNK_DELETE]
    stmts += [_pl_update(*r) for r in PL_RECODES]
    stmts += [_bs_update(*r) for r in BS_RECODES]
    return ";\n".join(stmts) + ";\n"


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not dry:
        guard_against_ci_writers()
    r2_storage.download_to(SNAP, str(GZ))
    with gzip.open(GZ, "rb") as s, open(DB, "wb") as d:
        shutil.copyfileobj(s, d)
    print(f"[dedup] pulled snapshot -> {DB.stat().st_size / 1e6:.1f} MB")

    conn = sqlite3.connect(str(DB))
    _apply_local(conn)

    # Re-validate the recoded partitions from the corrected rows — the recode must
    # CLEAR the pl_chain failure, else the mapping is wrong and we must not push.
    ok = True
    for b, p, k, stmt in RECODE_PARTS:
        res = revalidate_partition(conn, b, p, k)[stmt]
        state = "PASS" if not res.failed else f"FAIL {res.failed}"
        print(f"[dedup] revalidate {b} {p} {k[:5]} {stmt:11}: {state}")
        if res.failed:
            ok = False
    conn.close()
    if not ok:
        sys.exit("[dedup] ABORT: a recoded partition still fails validation — do not push")

    if dry:
        print("[dedup] dry-run — validated locally; no D1/snapshot write")
        return 0

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(_all_sql())
        sql_path = Path(f.name)
    try:
        retry_wrangler(sql_path, "D1 hierarchy dedup")
    finally:
        sql_path.unlink(missing_ok=True)
    print("[dedup] D1 rows updated")

    # Refresh bank_audit_validation (current code, from corrected rows) + the coverage
    # spine, then push both to D1. sync_audit_expected revalidates the whole DB, so the
    # recoded partitions flip to passing and every untouched partition recomputes identically.
    subprocess.run([sys.executable, str(REPO / "scripts" / "sync_audit_expected.py"),
                    "--db", str(DB), "--push"], check=True)

    push_snapshot(DB)
    print("[dedup] uploaded snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
