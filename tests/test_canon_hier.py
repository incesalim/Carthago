"""loader._canon_hier canonicalises hierarchy KEYS on write, for the catalog-driven
displayed statements only (assets / liabilities / profit_loss): it STRIPS a trailing
dot from a multi-level numeric sub-code and ADDS a trailing dot to a bare roman code.
Off-balance / oci / cash-flow keys and every value are left untouched."""
import pytest

pytest.importorskip("fitz")  # CI runs minimal deps; loader imports the extractor (fitz)

from src.audit_reports.loader import _canon_hier  # noqa: E402


@pytest.mark.parametrize("stmt, raw, expected", [
    # ADD a dot to a bare roman code (EXIM "XI" personnel, ALNTF "I" financial assets).
    ("profit_loss", "XI", "XI."),
    ("assets", "I", "I."),
    ("liabilities", "X", "X."),
    ("profit_loss", "VIII", "VIII."),
    ("assets", "XXIV", "XXIV."),
    # STRIP a trailing dot from a multi-level numeric sub-code (KUVEYT "1.1.").
    ("profit_loss", "1.1.", "1.1"),
    ("assets", "2.3.1.", "2.3.1"),
    # Idempotent: already-canonical codes pass through unchanged.
    ("profit_loss", "XI.", "XI."),
    ("assets", "1.1", "1.1"),
    ("profit_loss", "1.", "1."),          # single-level numeric dot is kept
    ("profit_loss", "1.1.ecl", "1.1.ecl"),  # synthetic suffix untouched
    # Non-normalised statements + off_balance keep their keys verbatim.
    ("off_balance", "2.1.13", "2.1.13"),
    ("cash_flow", "IV", "IV"),
    ("oci", "V", "V"),
    # Null / empty passthrough.
    ("profit_loss", None, None),
])
def test_canon_hier(stmt, raw, expected):
    assert _canon_hier(stmt, raw) == expected
