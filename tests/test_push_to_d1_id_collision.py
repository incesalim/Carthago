"""Regression for #105: a local AUTOINCREMENT `id` must never be sent to D1.

`push_to_d1.fetch_recent` builds `INSERT OR REPLACE INTO <table>(<cols>)`. When
`<cols>` includes the staging database's own `id`, the conflict target becomes
that rowid alias — and a scoped/historical backfill assigns FRESH high local ids
(a new scrape put the Feb-2025 ratio rows at 27301–27650) while live D1 already
owns id 27300 for a 2026-07 row. `INSERT OR REPLACE` on `id` then deletes the
unrelated 2026 row and inserts the 2025 one in its place.

The fix drops the surrogate `id` from the emitted column list whenever the table
has a natural UNIQUE key, so the conflict target is the business key
`(table_number, year, month, bank_type_code, item_order)`, which is stable across
staging databases.

These tests fail on the pre-fix emitter: the first assertion (no `id` in the
column list) and, more damningly, the remote-row-survival check.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import push_to_d1 as P  # noqa: E402

# The exact D1/staging shape of the table in the incident: a surrogate
# AUTOINCREMENT `id` plus the business UNIQUE key.
FINANCIAL_RATIOS_DDL = """
CREATE TABLE financial_ratios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    bank_type_code VARCHAR(10) NOT NULL,
    item_order INTEGER NOT NULL,
    item_name VARCHAR(300) NOT NULL,
    ratio_value DECIMAL(10, 6),
    ratio_category VARCHAR(100),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_number, year, month, bank_type_code, item_order)
)
"""

# A table whose only key is the surrogate `id` (mirrors `other_data`).
SURROGATE_ONLY_DDL = """
CREATE TABLE surrogate_only (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_number INTEGER,
    year INTEGER,
    month INTEGER,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_COLS_RX = re.compile(r"INSERT OR REPLACE INTO \w+\(([^)]*)\)")


def _stage(rows, ddl=FINANCIAL_RATIOS_DDL):
    """A staging connection holding `rows` (id, natural-key fields) with a
    current `downloaded_at`."""
    c = sqlite3.connect(":memory:")
    c.execute(ddl)
    for r in rows:
        c.execute(
            "INSERT INTO financial_ratios"
            "(id, table_number, year, month, bank_type_code, item_order,"
            " item_name, ratio_value, ratio_category, downloaded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
            r,
        )
    c.commit()
    return c


def _emitted_columns(block):
    """The column list of the (single) INSERT header fetch_recent emitted."""
    for line in block:
        m = _COLS_RX.search(line)
        if m:
            return [c.strip() for c in m.group(1).split(",")]
    raise AssertionError(f"no INSERT emitted: {block!r}")


def _apply(remote, block):
    remote.executescript("\n".join(block))


def test_emitter_never_sends_the_local_id_when_a_natural_key_exists():
    """The direct fix: the surrogate is not in the column list."""
    c = _stage([(27300, 15, 2025, 2, "10001", 1, "R1", 1.0, "other")])
    cols = _emitted_columns(P.fetch_recent(c, "financial_ratios", 48))
    assert "id" not in cols, f"local AUTOINCREMENT id leaked into the push: {cols}"
    assert cols[0] == "table_number"     # natural key still present and leading


def test_a_colliding_local_id_cannot_replace_an_unrelated_remote_row():
    """THE regression. Local id 27300 belongs to a 2025-02 ratio; D1 already
    holds 27300 for a 2026-07 ratio. The push must leave the 2026 row alone."""
    local = _stage([
        (27300, 15, 2025, 2, "10001", 1, "2025-02 ratio", 1.0, "other"),
        (27301, 15, 2025, 2, "10001", 2, "2025-02 ratio 2", 2.0, "other"),
    ])
    block = P.fetch_recent(local, "financial_ratios", 48)

    remote = sqlite3.connect(":memory:")
    remote.execute(FINANCIAL_RATIOS_DDL)
    remote.execute(
        "INSERT INTO financial_ratios"
        "(id, table_number, year, month, bank_type_code, item_order, item_name) "
        "VALUES (27300, 15, 2026, 7, '10001', 1, '2026-07 ratio')")
    remote.execute(
        "INSERT INTO financial_ratios"
        "(id, table_number, year, month, bank_type_code, item_order, item_name) "
        "VALUES (27301, 15, 2026, 7, '10001', 2, '2026-07 ratio 2')")
    remote.commit()

    _apply(remote, block)

    survivor = remote.execute(
        "SELECT year, month, item_name FROM financial_ratios WHERE id = 27300"
    ).fetchone()
    assert survivor == (2026, 7, "2026-07 ratio"), (
        "the local 2025-02 row replaced unrelated remote id 27300 — #105 is back"
    )
    # And the intended 2025-02 facts did land, on their own key.
    landed = remote.execute(
        "SELECT item_name FROM financial_ratios "
        "WHERE table_number=15 AND year=2025 AND month=2 AND item_order=1"
    ).fetchone()
    assert landed == ("2025-02 ratio",)


def test_the_old_emitter_would_have_clobbered_that_row():
    """Pins the MECHANISM, so this file keeps catching #105 if the column list
    ever reverts: including `id` in `INSERT OR REPLACE` really does delete a
    different natural key's row occupying the same id."""
    remote = sqlite3.connect(":memory:")
    remote.execute(FINANCIAL_RATIOS_DDL)
    remote.execute(
        "INSERT INTO financial_ratios"
        "(id, table_number, year, month, bank_type_code, item_order, item_name) "
        "VALUES (27300, 15, 2026, 7, '10001', 1, '2026-07 ratio')")
    remote.commit()

    remote.execute(
        "INSERT OR REPLACE INTO financial_ratios"
        "(id, table_number, year, month, bank_type_code, item_order, item_name) "
        "VALUES (27300, 15, 2025, 2, '10001', 1, '2025-02 ratio')")
    remote.commit()

    got = remote.execute(
        "SELECT year, month FROM financial_ratios WHERE id = 27300").fetchone()
    assert got == (2025, 2), "old-style emit no longer clobbers; update this test"


def test_reapplying_the_push_is_idempotent():
    """Conflict on the natural key still resolves — no duplicate accumulation."""
    local = _stage([(27300, 15, 2025, 2, "10001", 1, "R1", 1.0, "other")])
    block = P.fetch_recent(local, "financial_ratios", 48)

    remote = sqlite3.connect(":memory:")
    remote.execute(FINANCIAL_RATIOS_DDL)
    _apply(remote, block)
    first = remote.execute(
        "SELECT COUNT(*) FROM financial_ratios WHERE year=2025 AND month=2"
    ).fetchone()[0]
    _apply(remote, block)
    second = remote.execute(
        "SELECT COUNT(*) FROM financial_ratios WHERE year=2025 AND month=2"
    ).fetchone()[0]
    assert first == 1 and second == 1


def test_emit_columns_is_schema_driven_not_name_driven():
    """Any natural-key table, not just financial_ratios, loses the surrogate."""
    assert P.emit_columns(_stage([(1, 15, 2025, 2, "10001", 1, "R", 1.0, "o")]),
                          "financial_ratios")[0] != "id"


def test_a_surrogate_only_table_keeps_its_id():
    """The residual documented in `emit_columns`: with no natural key there is
    nothing to conflict on, and dropping `id` would append a duplicate on every
    overlapping window. `other_data` is such a table and needs a key of its own.
    """
    c = sqlite3.connect(":memory:")
    c.execute(SURROGATE_ONLY_DDL)
    c.execute("INSERT INTO surrogate_only(table_number, year, month, downloaded_at) "
              "VALUES (12, 2025, 2, datetime('now'))")
    c.commit()
    cols = P.emit_columns(c, "surrogate_only")
    assert "id" in cols


def test_natural_key_columns_finds_the_business_unique_not_the_id():
    keys = P.natural_key_columns(
        _stage([(1, 15, 2025, 2, "10001", 1, "R", 1.0, "o")]), "financial_ratios")
    assert ("table_number", "year", "month", "bank_type_code", "item_order") in keys
    assert ("id",) not in keys


def test_each_run_writes_a_unique_sql_file(tmp_path, monkeypatch, capsys):
    """The old fixed `d1_incremental.sql` name raced between processes (issue
    #105). No live execute — dry-run only, and it returns before preflight."""
    db = tmp_path / "bddk.db"
    c = sqlite3.connect(db)
    c.execute(FINANCIAL_RATIOS_DDL)
    c.execute("INSERT INTO financial_ratios"
              "(table_number, year, month, bank_type_code, item_order, item_name,"
              " ratio_value, downloaded_at) "
              "VALUES (15, 2025, 2, '10001', 1, 'R1', 1.0, datetime('now'))")
    c.commit()
    c.close()

    paths = []
    for _ in range(2):
        monkeypatch.setattr(
            sys, "argv",
            ["push_to_d1.py", "--db", str(db), "--dry-run",
             "--only-tables", "financial_ratios"])
        assert P.main() == 0
        out = capsys.readouterr().out
        m = re.search(r"generated (\S+\.sql)", out)
        assert m, out
        paths.append(m.group(1))

    assert paths[0] != paths[1]
    assert all("d1_incremental_" in p for p in paths)
    for p in paths:
        Path(p).unlink(missing_ok=True)
