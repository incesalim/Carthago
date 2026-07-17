"""Build the coverage spine for the /admin audit matrix and (optionally) push it
to D1 — no R2 snapshot, no re-extraction.

Validation is recomputed from the stored data rows with the CURRENT validator code
first (see `_refresh_validation`), so the spine is always derived from current-code
verdicts rather than the verdicts frozen in whatever R2 snapshot the caller pulled.
This makes the matrix correct by construction for every caller and is the durable fix
for the "stale snapshot reverts the rollup" class of bug. The freshly-recomputed
bank_audit_validation is pushed alongside the three coverage tables.

Three coverage tables, all rebuilt wholesale:

  bank_audit_expected         what the corpus SHOULD hold (data/audit_profiles.json
                              keys), overlaid with whether the PDF is in R2.
  bank_audit_statement_types  the registry mirrored from registry.web_metadata().
  bank_audit_coverage         one row per (bank, period, kind, statement_type) with
                              a precomputed status the Worker reads directly.

Status per cell (worst → best): missing < error < manual < ok
  missing  expected but fewer than the type's minimum rows (or none).
  error    a structural validator check FAILED, or the validator verified
           NOTHING (every check skipped) — see _cell_status. The second case
           used to read 'ok'.
  manual   present, valid, and a manual overlay supplied it (human-sourced).
  ok       present, valid, machine-extracted.
  not_expected  the lane genuinely doesn't apply here: an annual-only table in an
           interim quarter, a conditional lane the bank doesn't hold, or a
           curated data/audit_not_disclosed.json entry.

Caveat worth knowing before reading a row: 'ok' is only as strong as the lane's
validator, and three lanes (profile, audit_opinion, free_provision) have none —
for those, registry.has_validator is False and 'ok' asserts only "a row exists".

  python scripts/sync_audit_expected.py --db data/bank_audit.db --dry-run
  python scripts/sync_audit_expected.py --db data/bank_audit.db --push
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.audit_reports import registry  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402

PROFILES = REPO / "data" / "audit_profiles.json"
MANUAL = REPO / "data" / "manual_statements.json"
OVERRIDES = REPO / "data" / "audit_overrides.json"
NOT_DISCLOSED = REPO / "data" / "audit_not_disclosed.json"


def _load_not_disclosed() -> list[dict]:
    """Curated 'genuinely not disclosed in the PDF' cells → shown as N/A, not
    missing. Returns the raw entries; _nd_matches does the matching (incl.
    period/kind '*' wildcards). A '*' (or omitted) period/kind covers every
    quarter / both consolidation bases — used when a bank STRUCTURALLY never
    files a lane (e.g. İşbank never states branch/personnel counts in its interim
    BRSA report; those live in the annual faaliyet report), so it doesn't need a
    fresh entry every quarter."""
    try:
        return json.loads(NOT_DISCLOSED.read_text(encoding="utf-8"))["not_disclosed"]
    except Exception:
        return []


def _nd_matches(entries: list[dict], b: str, p: str, k: str, st) -> bool:
    """True if a curated not-disclosed entry covers this (bank, period, kind,
    statement-type) cell. period/kind '*' (or omitted) is a wildcard; statement
    '*' = every NON-CORE lane, a list = any listed key, else an exact key."""
    for e in entries:
        if e["bank"].upper() != b.upper():
            continue
        ep, ek = e.get("period", "*"), e.get("kind", "*")
        if ep != "*":
            eps = ep if isinstance(ep, list) else [ep]
            if p.upper() not in [x.upper() for x in eps]:
                continue
        if ek != "*" and ek != k:
            continue
        stt = e.get("statement")
        if stt == "*":
            if not st.is_core:
                return True
        elif isinstance(stt, list):
            if st.key in stt:
                return True
        elif stt == st.key:
            return True
    return False


COVERAGE_TABLES = ["bank_audit_expected", "bank_audit_statement_types", "bank_audit_coverage"]

# Manual-overlay statement names → registry key. A cell listed here is shown in
# the matrix's MANUAL column, not OK: the figure is human-sourced, and the
# distinction is the point of that column.
_STMT_TO_KEY = {
    "assets": "balance_sheet_assets",
    "liabilities": "balance_sheet_liabilities",
    "off_balance": "off_balance",
    "profit_loss": "profit_loss",
    "oci": "other_comprehensive_income",
    "cash_flow": "cash_flow",
    # Prose-disclosed Stage-3 (NPL) figures curated into bank_audit_credit_quality —
    # see the `credit_quality` branch of apply_overrides._apply_one. Without this
    # the cells would read a plain machine-extracted 'ok' and hide that a human
    # transcribed the number out of a sentence.
    "credit_quality": "credit_quality",
    # Same reasoning, same risk: 9 partitions carry hand-read npl_movement cells —
    # COLENDI 2026Q1's roll-forward transcribed off a page whose text layer is
    # cell-per-line, ZIRAATD 2026Q1's opening balance sourced from prose
    # ("31 Aralık 2025: Bulunmamaktadır") because the cells are printed blank, the
    # six FIBA notes read out of bitmaps/vector outlines, and AKTIF 2023Q3's
    # two-page current/prior mix-up. All of them read a machine-extracted 'ok'
    # until this entry existed.
    "npl_movement": "npl_movement",
}


def _expected_universe(
    pdfs: set[tuple[str, str, str]] | None = None,
) -> dict[tuple[str, str, str], dict]:
    """{(bank, period, kind): {bank_type, language, equity_numeral}} — the
    partitions we expect to hold. This is the profile census
    (data/audit_profiles.json) UNIONED with every PDF currently in R2, so a
    freshly-acquired quarter that isn't profiled yet still appears in the matrix
    (as missing + pdf_present, i.e. "acquired, not yet extracted"). R2-only
    entries carry bare metadata until the census is regenerated. When `pdfs` is
    None (offline/--no-r2 dry-run) the universe is profiles-only."""
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    out: dict[tuple[str, str, str], dict] = {}
    for pk, prof in profiles.items():
        bank, period, kind = pk.split("|")
        eq = (prof.get("liabilities") or {}).get("equity_numeral") \
            or (prof.get("assets") or {}).get("equity_numeral")
        out[(bank.upper(), period.upper(), kind)] = {
            "bank_type": prof.get("bank_type"),
            "language": prof.get("language"),
            "equity_numeral": eq,
        }
    for bpk in pdfs or ():
        out.setdefault(bpk, {"bank_type": None, "language": None, "equity_numeral": None})
    return out


def _manual_cells() -> set[tuple[str, str, str, str]]:
    """{(bank, period, kind, registry_key)} touched by a manual overlay —
    data/manual_statements.json (whole hand-transcribed statements) or
    data/audit_overrides.json (per-cell curated fixes)."""
    cells: set[tuple[str, str, str, str]] = set()
    if MANUAL.exists():
        for m in json.loads(MANUAL.read_text(encoding="utf-8")).get("statements", []):
            key = _STMT_TO_KEY.get(m.get("statement"))
            if key:
                cells.add((m["bank"].upper(), m["period"].upper(), m["kind"], key))
    if OVERRIDES.exists():
        for o in json.loads(OVERRIDES.read_text(encoding="utf-8")).get("overrides", []):
            key = _STMT_TO_KEY.get(o.get("statement"))
            if key:
                cells.add((o["bank_ticker"].upper(), o["period"].upper(), o["kind"], key))
    return cells


def _counts_for(conn: sqlite3.Connection, st) -> dict[tuple[str, str, str], int]:
    """Row count per (bank, period, kind) for one statement type. A missing table
    (footnote extractor never run on this DB) yields an empty map, not a crash."""
    try:
        if st.statement is not None:
            cur = conn.execute(
                f"SELECT bank_ticker, period, kind, COUNT(*) FROM {st.table} "
                "WHERE statement=? GROUP BY bank_ticker, period, kind", (st.statement,))
        else:
            cur = conn.execute(
                f"SELECT bank_ticker, period, kind, COUNT(*) FROM {st.table} "
                "GROUP BY bank_ticker, period, kind")
        return {(b, p, k): n for b, p, k, n in cur}
    except sqlite3.OperationalError:
        return {}


def _refresh_validation(conn: sqlite3.Connection) -> None:
    """Recompute + persist bank_audit_validation from the stored data rows with the
    CURRENT validator code, BEFORE the spine is derived from it.

    The coverage spine's per-cell status is a rollup of bank_audit_validation. That
    table is carried in the R2 snapshot frozen at upload time, so a spine rebuilt
    straight from a pulled snapshot resurrects failures already fixed by a validator
    change made since (a check rewrite, a curated _PL_SKIP/_CF_SKIP) — exactly the
    revert that snapped cash_flow back from 0 to 135. Recomputing here makes the spine
    correct by construction for EVERY caller (acquire-audit, reextract, apply_overrides,
    manual), instead of relying on each to remember to revalidate first. Pure SQLite,
    no PDF. Best-effort: a DB without the audit data tables, or an import failure,
    leaves the stored verdicts in place."""
    try:
        from scripts.revalidate_audit_db import revalidate_all
    except Exception as e:  # noqa: BLE001
        print(f"[sync] revalidate unavailable ({type(e).__name__}); using stored verdicts")
        return
    try:
        n, failed = revalidate_all(conn)
        print(f"[sync] revalidated {n} partitions with current code ({failed} failing)")
    except Exception as e:  # noqa: BLE001
        print(f"[sync] revalidate skipped ({type(e).__name__}); using stored verdicts")


def _validation(conn: sqlite3.Connection) -> dict[tuple[str, str, str, str], tuple[int, int]]:
    """(checks_passed, checks_failed) per (bank, period, kind, statement)."""
    try:
        return {(b, p, k, s): (cp, cf) for b, p, k, s, cp, cf in conn.execute(
            "SELECT bank_ticker, period, kind, statement, checks_passed, checks_failed "
            "FROM bank_audit_validation")}
    except sqlite3.OperationalError:
        return {}


def _curated_skips() -> tuple[set, set]:
    """The partitions/banks a human has deliberately excused from a check, so the
    spine doesn't read that curation as an unverified cell. Best-effort — a DB
    without the scripts importable just gets the old behaviour."""
    try:
        from scripts.revalidate_audit_db import curated_skip_banks, curated_skips
        return curated_skips(), curated_skip_banks()
    except Exception:  # noqa: BLE001
        return set(), set()


def _cell_status(rows: int, min_rows: int, has_validator: bool,
                 checks_failed: int, is_manual: bool, checks_passed: int = 1,
                 curated_skip: bool = False) -> str:
    """Worst → best: missing < error < manual < ok.

    `error` covers BOTH "we checked it and it's wrong" (checks_failed > 0) and
    "we never actually checked it" (checks_passed == 0 — every check skipped).
    The second used to fall through to `ok`, which is how 262 cells (1.9%) came to
    read green with nothing verified, clustered by bank rather than scattered:
    ANADOLU's npl_movement, ATBANK's capital, DUNYAK/COLENDI's credit_quality and
    stages, HAYATK's fx_position.

    This is not a new concept — it resolves a three-way disagreement in which the
    matrix was the odd one out. validator.statement_passes() ("at least one check
    passed and none failed") already gates re-extraction this way, and
    reextract_statement.py already re-extracts on `checks_failed>0 OR
    checks_passed=0`. Only the matrix called those cells `ok`.

    The two are deliberately merged into one status rather than split into an
    `unverified` column: the distinction survives in bank_audit_validation
    (checks_passed) and in the coverage drawer, and a cell you have not verified
    is not a cell you can report as good.

    `curated_skip` is the exception that makes the rule safe. A partition on one
    of revalidate_audit_db's skip lists ALSO has checks_passed == 0, but its zero
    means the opposite: a human read the PDF, established the data is faithful and
    that the SOURCE itself doesn't foot, and excused the check. Treating that as
    an error would turn 53 curated cells red — ATBANK's regulatory-floor CAR (34),
    its total-less sector table (8), TEB's 2022 CARs (4), ALBRK/TSKB's cash-flow
    source typos (2), ICBCT's rounding (1), ATBANK's OCI sign typo (1) — and
    would punish exactly the diligence we want.
    """
    if rows < min_rows:
        return "missing"
    if has_validator and (checks_failed > 0
                          or (checks_passed == 0 and not curated_skip)):
        return "error"
    if is_manual:
        return "manual"
    return "ok"


def build(conn: sqlite3.Connection, use_r2: bool):
    _refresh_validation(conn)  # spine is derived from current-code verdicts, not the snapshot's frozen ones
    manual = _manual_cells()
    validation = _validation(conn)
    skips, skip_banks = _curated_skips()
    counts = {st.key: _counts_for(conn, st) for st in registry.REGISTRY}

    extracted = set()
    try:
        extracted = {(b, p, k) for b, p, k in conn.execute(
            "SELECT bank_ticker, period, kind FROM bank_audit_extractions")}
    except sqlite3.OperationalError:
        pass

    pdfs = None
    if use_r2:
        try:
            from src.audit_reports import r2_storage
            pdfs = {(b, p, k) for b, p, k, _key in r2_storage.list_audit_pdfs()}
            print(f"[sync] R2: {len(pdfs)} audit PDFs")
        except Exception as e:  # noqa: BLE001 — R2 optional for local dry-runs
            print(f"[sync] R2 unavailable ({type(e).__name__}); pdf_present via has-rows fallback")

    # Expected universe = profile census ∪ R2 PDFs, so acquired-but-unextracted
    # partitions surface in the matrix (R2-only → bare metadata, status missing).
    expected = _expected_universe(pdfs)

    def pdf_present(bpk) -> int:
        if pdfs is not None:
            return 1 if bpk in pdfs else 0
        return 1 if bpk in extracted else 0   # fallback: extracted ⇒ the PDF existed

    nd_entries = _load_not_disclosed()
    expected_rows, coverage_rows = [], []
    for bpk, meta in sorted(expected.items()):
        b, p, k = bpk
        present = pdf_present(bpk)
        expected_rows.append((b, p, k, meta["bank_type"], meta["language"],
                              meta["equity_numeral"], present))
        # check_cross_statement (total assets = liabilities + equity — the single
        # most important BS identity) writes a 'cross' row to bank_audit_validation
        # that NO registry lane maps to, so a failure reached no cell and both
        # balance-sheet lanes would have stayed green. 0 failures today, so this is
        # latent, not a live wrong number — but it is a check wired to nothing.
        # Fold it into both sides, which is where it belongs: the identity is a
        # statement about the pair, and neither is trustworthy if it breaks.
        cross_cf = validation.get((b, p, k, "cross"), (1, 0))[1]
        for st in registry.REGISTRY:
            rows = counts[st.key].get(bpk, 0)
            min_rows = st.present_min_rows or 1
            cp, cf = validation.get((b, p, k, st.validation_statement), (0, 0)) \
                if st.has_validator else (1, 0)
            if st.key in ("balance_sheet_assets", "balance_sheet_liabilities"):
                cf += cross_cf
            is_manual = (b, p, k, st.key) in manual
            curated = ((b, p, k, st.key) in skips or (b, st.key) in skip_banks)
            status = _cell_status(rows, min_rows, st.has_validator, cf, is_manual,
                                  cp, curated)
            # Annual-only statements (e.g. loans-by-sector): the table simply isn't
            # disclosed in interim reports, so an empty interim cell is NOT missing —
            # it's not-applicable. (A bank that DOES disclose interim has rows → ok/error.)
            if status == "missing" and st.annual_only and not p.upper().endswith("Q4"):
                status = "not_expected"
            # Conditional-disclosure lanes (e.g. free provision): only banks that
            # actually HOLD one disclose it, so an empty cell means "no such reserve",
            # not a gap. The recall cross-check (check_audit_quality freeprov) has
            # already proven no real holding is hidden among the empties, so absence
            # is genuinely not-applicable.
            if status == "missing" and getattr(st, "conditional", False):
                status = "not_expected"
            # Curated: this partition's report genuinely doesn't disclose the lane
            # (verified vs PDF) — a brief interim/summary filing, or a bank that
            # structurally never states the lane (period/kind '*'). '*' statement
            # covers every NON-CORE lane; core BS/PL/cross always stay flagged.
            if status == "missing" and _nd_matches(nd_entries, b, p, k, st):
                status = "not_expected"
            coverage_rows.append((b, p, k, st.key, status, rows, cf, int(is_manual), present))

    type_rows = [(m["key"], m["label"], m["table"], m["statement"], m["section"],
                  m["is_core"], m["has_validator"], m["section_rank"], m["sort_order"])
                 for m in registry.web_metadata()]
    return expected_rows, type_rows, coverage_rows


def write(conn: sqlite3.Connection, expected_rows, type_rows, coverage_rows) -> None:
    init_schema(conn)
    conn.execute("DELETE FROM bank_audit_expected")
    conn.executemany(
        "INSERT INTO bank_audit_expected (bank_ticker, period, kind, bank_type, "
        "language, equity_numeral, pdf_present) VALUES (?,?,?,?,?,?,?)", expected_rows)
    conn.execute("DELETE FROM bank_audit_statement_types")
    conn.executemany(
        "INSERT INTO bank_audit_statement_types (key, label, source_table, statement, "
        "section, is_core, has_validator, section_rank, sort_order) "
        "VALUES (?,?,?,?,?,?,?,?,?)", type_rows)
    conn.execute("DELETE FROM bank_audit_coverage")
    conn.executemany(
        "INSERT INTO bank_audit_coverage (bank_ticker, period, kind, statement_type, "
        "status, row_count, checks_failed, is_manual, pdf_present) VALUES (?,?,?,?,?,?,?,?,?)",
        coverage_rows)
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bank_audit.db"))
    ap.add_argument("--dry-run", action="store_true", help="build + write local DB; print summary, no D1 push")
    ap.add_argument("--push", action="store_true", help="push the three tables to D1 (full rebuild)")
    ap.add_argument("--no-r2", action="store_true", help="skip the R2 PDF listing (use has-rows fallback)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    expected_rows, type_rows, coverage_rows = build(conn, use_r2=not args.no_r2)
    write(conn, expected_rows, type_rows, coverage_rows)
    conn.close()

    by_status = Counter(r[4] for r in coverage_rows)
    n_pdf = sum(1 for r in expected_rows if r[6])
    print(f"[sync] expected partitions: {len(expected_rows)} ({n_pdf} with PDF in R2)")
    print(f"[sync] statement types: {len(type_rows)}")
    print(f"[sync] coverage cells: {len(coverage_rows)}  " + "  ".join(
        f"{s}={by_status[s]}" for s in ("ok", "manual", "error", "missing", "not_expected") if by_status[s]))

    if args.push:
        from scripts.audit_d1 import ensure_d1_schema
        ensure_d1_schema()  # create the three tables on D1 if a deploy hasn't yet
        print("[sync] pushing to D1 (full rebuild)…")
        # Push the freshly-recomputed validation too (its validated_at was just
        # bumped) so the /admin drill-down matches the rollup the matrix shows.
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "push_to_d1.py"), "--db", args.db,
             "--hours", "1", "--only-tables", ",".join([*COVERAGE_TABLES, "bank_audit_validation"])],
            check=True)
        print("[sync] done")
    else:
        print("[sync] local only — pass --push to write D1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
