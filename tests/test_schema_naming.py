"""New D1 migrations must follow docs/SCHEMA_CONVENTIONS.md.

Thin pytest wrapper around scripts/check_schema_naming.py: the real repo must be
clean in the enforced range, and the rules must actually fire on synthetic bad
migrations (guards against a check that silently passes).
"""

from check_schema_naming import find_duplicate_numbers, iter_tables, lint


def _errors(migrations):
    return lint(migrations)[0]


def test_current_repo_is_clean():
    from check_schema_naming import check

    errors, _ = check()
    assert not errors, "schema naming violations in repo:\n" + "\n".join(errors)


def test_flags_bank_id_synonym():
    errs = _errors({"0099_x.sql": "CREATE TABLE foo (ticker TEXT, period TEXT);"})
    assert any("bank_ticker" in e for e in errs)


def test_flags_reserved_word():
    errs = _errors({'0099_x.sql': 'CREATE TABLE foo ("order" INTEGER);'})
    assert any("reserved" in e for e in errs)


def test_flags_non_snake_case():
    errs = _errors({"0099_x.sql": "CREATE TABLE foo (bankTicker TEXT);"})
    assert any("snake_case" in e for e in errs)


def test_flags_amount_fx():
    errs = _errors({"0099_x.sql": "CREATE TABLE foo (amount_fx REAL);"})
    assert any("amount_fc" in e for e in errs)


def test_flags_duplicate_number():
    dupes = find_duplicate_numbers(["0099_a.sql", "0099_b.sql"])
    assert "0099" in dupes


def test_grandfathers_existing_0007_dup():
    dupes = find_duplicate_numbers(["0007_a.sql", "0007_b.sql"])
    assert "0007" not in dupes


def test_banks_dimension_ticker_is_allowed():
    # The `banks` dimension keys on the bare `ticker` by design.
    errs = _errors({"0099_x.sql": "CREATE TABLE banks (ticker TEXT PRIMARY KEY);"})
    assert not any("bank_ticker" in e for e in errs)


def test_grandfathered_range_not_enforced():
    # Same synonym in an old migration number is a drift note, not an error.
    errs = _errors({"0003_x.sql": "CREATE TABLE foo (ticker TEXT);"})
    assert not any("bank_ticker" in e for e in errs)


def test_decimal_comma_not_split_into_columns():
    tables = dict(iter_tables("CREATE TABLE t (a DECIMAL(20, 2), b TEXT);"))
    assert tables["t"] == ["a", "b"]
