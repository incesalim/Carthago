"""`--latest-period` cleared one quarter and re-extracted a different one.

`backfill_extraction.py` does two things that must agree about which quarter is
"latest": it DELETEs the named banks' rows from `bank_audit_extractions` to force
a re-extract, and it calls `extract_from_r2(latest_period=True)` to do the
re-extraction. They resolved it from different places —

    DELETE            MAX(period) FROM bank_audit_extractions   (the database)
    extract_from_r2   _restrict_to_latest_period(list_r2_pdfs()) (R2)

— and those are only equal while every acquired PDF has been extracted. Whenever
R2 is AHEAD of the database the clear takes the older quarter and the re-extract
takes the newer, so the older quarter loses its extraction log row and nothing
ever rebuilds it.

R2-ahead is not an edge case. It is the normal state during a filing season, and
it is exactly what the 2026-08-08 → 08-12 extraction stall produced: 2026Q2 sat
in R2 for six days while the database's newest extracted quarter stayed 2026Q1.
Running `backfill-audit.yml` with `latest_period=true` in that window would have
deleted 2026Q1's log rows for every named bank.

Both sides now read R2, through one shared function.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _mod():
    spec = importlib.util.spec_from_file_location(
        "backfill_lp", REPO / "scripts" / "backfill_extraction.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# R2 as it looked mid-stall: 2026Q2 acquired for three banks, 2026Q1 the newest
# quarter any of them had actually been extracted into the database.
R2_LISTING = [
    ("ALBRK", "2026Q1", "consolidated", "albrk/ALBRK_2026Q1_consolidated.pdf"),
    ("ALBRK", "2026Q2", "consolidated", "albrk/ALBRK_2026Q2_consolidated.pdf"),
    ("ALBRK", "2026Q2", "unconsolidated", "albrk/ALBRK_2026Q2_unconsolidated.pdf"),
    ("HALKB", "2026Q1", "consolidated", "halkb/HALKB_2026Q1_consolidated.pdf"),
    ("HALKB", "2026Q2", "consolidated", "halkb/HALKB_2026Q2_consolidated.pdf"),
    # never acquired a 2026Q2 — its latest really is 2026Q1
    ("KLNMA", "2025Q4", "consolidated", "klnma/KLNMA_2025Q4_consolidated.pdf"),
    ("KLNMA", "2026Q1", "consolidated", "klnma/KLNMA_2026Q1_consolidated.pdf"),
]


def test_latest_period_comes_from_r2_not_the_database(monkeypatch):
    """THE fix. R2 holds 2026Q2; the database's newest extraction is 2026Q1."""
    M = _mod()
    monkeypatch.setattr(M, "list_r2_pdfs", lambda: list(R2_LISTING))
    assert M.latest_period_in_r2({"ALBRK", "HALKB", "KLNMA"}) == {
        "ALBRK": "2026Q2",
        "HALKB": "2026Q2",
        "KLNMA": "2026Q1",     # genuinely its newest — no 2026Q2 acquired
    }


def test_it_is_per_bank_not_a_single_global_quarter(monkeypatch):
    """Banks publish on their own schedules; one global MAX would clear the
    wrong quarter for every bank that has not filed yet."""
    M = _mod()
    monkeypatch.setattr(M, "list_r2_pdfs", lambda: list(R2_LISTING))
    got = M.latest_period_in_r2({"ALBRK", "KLNMA"})
    assert got["ALBRK"] != got["KLNMA"]


def test_banks_outside_the_scope_are_ignored(monkeypatch):
    M = _mod()
    monkeypatch.setattr(M, "list_r2_pdfs", lambda: list(R2_LISTING))
    assert set(M.latest_period_in_r2({"ALBRK"})) == {"ALBRK"}


def test_the_clear_targets_the_same_quarter_that_will_be_re_extracted(monkeypatch, tmp_path):
    """End to end on the WHERE clause: with R2 ahead, 2026Q1 must survive.

    Before the fix this deleted ALBRK 2026Q1 (the database's MAX) while
    extract_from_r2 re-read 2026Q2, so 2026Q1 was left with no log row.
    """
    M = _mod()
    monkeypatch.setattr(M, "list_r2_pdfs", lambda: list(R2_LISTING))
    db = tmp_path / "audit.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE bank_audit_extractions (bank_ticker TEXT, "
                "period TEXT, kind TEXT, success INTEGER DEFAULT 1)")
    con.executemany("INSERT INTO bank_audit_extractions(bank_ticker,period,kind) "
                    "VALUES (?,?,?)",
                    [("ALBRK", "2026Q1", "consolidated"),
                     ("ALBRK", "2026Q2", "consolidated"),
                     ("HALKB", "2026Q1", "consolidated")])
    con.commit()

    banks = {"ALBRK", "HALKB"}
    latest = M.latest_period_in_r2(banks)
    ph = ",".join("?" * len(banks))
    where = f"bank_ticker IN ({ph})"
    params: tuple = tuple(banks)
    pairs = " OR ".join(["(bank_ticker=? AND period=?)"] * len(latest))
    where += f" AND ({pairs})"
    for t, p in sorted(latest.items()):
        params += (t, p)
    con.execute(f"DELETE FROM bank_audit_extractions WHERE {where}", params)
    con.commit()

    left = set(con.execute(
        "SELECT bank_ticker, period FROM bank_audit_extractions").fetchall())
    con.close()
    # 2026Q2 cleared (it is what gets re-extracted); both 2026Q1 rows survive.
    assert ("ALBRK", "2026Q2") not in left
    assert ("ALBRK", "2026Q1") in left, "the settled quarter must not be cleared"
    assert ("HALKB", "2026Q1") in left, "HALKB's 2026Q2 is not in the DB to clear"


def test_the_database_max_query_is_gone_from_the_source():
    """Pinned at source level: the two resolvers must not drift apart again."""
    src = (REPO / "scripts" / "backfill_extraction.py").read_text(encoding="utf-8")
    # The SQL itself, not the comment that explains why it is gone.
    assert "SELECT bank_ticker, MAX(period)" not in src, \
        "--latest-period must resolve from R2, not from bank_audit_extractions"
    assert "FROM bank_audit_extractions WHERE bank_ticker IN" not in src
    assert "latest_period_in_r2" in src


def test_it_refuses_rather_than_clearing_everything_when_r2_is_empty(monkeypatch):
    """An empty listing must not collapse to a WHERE that matches every row.
    Failing open here would delete the named banks' entire history."""
    M = _mod()
    monkeypatch.setattr(M, "list_r2_pdfs", lambda: [])
    assert M.latest_period_in_r2({"ALBRK"}) == {}
    src = (REPO / "scripts" / "backfill_extraction.py").read_text(encoding="utf-8")
    assert "refusing to clear anything" in src
