"""Unit tests for the coverage matrix's per-cell status rule.

`_cell_status` decides what the /admin matrix asserts about a cell, and it had a
blind spot worth a permanent test: it read `checks_failed` but never
`checks_passed`, so a partition whose every check SKIPPED fell through to `ok`.
262 cells (1.9%) read green with nothing verified — clustered by bank, not
scattered (ANADOLU's npl_movement, ATBANK's capital, DUNYAK/COLENDI's
credit_quality and stages, HAYATK's fx_position).

The subtle half is the exemption: a partition on one of revalidate_audit_db's
curated skip lists ALSO has checks_passed == 0, and means the opposite — a human
read the PDF and established the SOURCE doesn't foot. Conflating the two turns 53
carefully-curated cells red and punishes the diligence. Both directions are
pinned here.

Pure stdlib — no DB, no PDF.
"""
import sync_audit_expected as S


def _status(**kw):
    args = {"rows": 10, "min_rows": 1, "has_validator": True,
            "checks_failed": 0, "is_manual": False, "checks_passed": 5,
            "curated_skip": False}
    args.update(kw)
    return S._cell_status(**args)


def test_clean_cell_is_ok():
    assert _status() == "ok"


def test_failed_check_is_error():
    assert _status(checks_failed=1) == "error"


def test_too_few_rows_is_missing():
    assert _status(rows=0, min_rows=1) == "missing"


def test_missing_beats_error():
    """Worst-wins: a cell with no rows reads `missing`, not `error`."""
    assert _status(rows=0, min_rows=1, checks_failed=3) == "missing"


def test_zero_checks_passed_is_error_not_ok():
    """The fix: rows present, nothing failed — because nothing RAN."""
    assert _status(checks_passed=0) == "error"


def test_curated_skip_with_zero_passes_stays_ok():
    """ATBANK's regulatory-floor CAR, its total-less sector table, TEB's 2022
    CARs, ALBRK/TSKB's cash-flow source typos: deliberately excused, PDF-verified,
    faithful. Zero passes here means "a human checked", not "nobody checked"."""
    assert _status(checks_passed=0, curated_skip=True) == "ok"


def test_curated_skip_does_not_excuse_a_real_failure():
    """The exemption covers the zero-pass rule only — a curated lane that somehow
    FAILS a check is still an error."""
    assert _status(checks_passed=0, checks_failed=2, curated_skip=True) == "error"


def test_unvalidated_lane_is_not_errored_for_zero_passes():
    """profile / audit_opinion / free_provision have no validator, so they never
    write a validation row. They must not all turn red."""
    assert _status(has_validator=False, checks_passed=0) == "ok"


def test_manual_cell_is_manual():
    assert _status(is_manual=True) == "manual"


def test_manual_cell_with_a_failure_is_still_error():
    assert _status(is_manual=True, checks_failed=1) == "error"


def test_curated_skips_are_wired_and_nonempty():
    """The lists live in revalidate_audit_db; if the import path breaks, the
    exemption silently stops working and 53 curated cells turn red. Assert the
    accessor actually resolves."""
    skips, banks = S._curated_skips()
    assert ("ATBANK", "capital") in banks
    assert ("ATBANK", "2022Q4", "consolidated", "loans_by_sector") in skips
    assert ("ALBRK", "2023Q4", "consolidated", "cash_flow") in skips
