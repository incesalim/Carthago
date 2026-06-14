"""OCI validation-guided scorer (src/audit_reports/oci.py): the chain identity
III = I + II is the tier-1 signal, with a degenerate guard on row I (net profit,
never ~0) so a near-empty 0==0 parse can't win."""
from src.audit_reports.extractor import StatementRow
from src.audit_reports.oci import _oci_candidate_score, _oci_chain_closes, _oci_romans


def _row(order: int, h: str, name: str, amt: float) -> StatementRow:
    return StatementRow(order=order, hierarchy=h, name=name, footnote=None, cur_amount=amt)


def _valid_rows() -> list[StatementRow]:
    # I + II = III (1000 + -300 = 700); the 2.2 sub-tree foots (-300 == -300)
    return [
        _row(1, "I.", "current period profit", 1000.0),
        _row(2, "II.", "other comprehensive income", -300.0),
        _row(3, "2.1", "not to be recycled", 0.0),
        _row(4, "2.2", "to be recycled", -300.0),
        _row(5, "2.2.1", "fx differences", -300.0),
        _row(6, "III.", "total comprehensive income", 700.0),
    ]


def test_romans_spine():
    assert _oci_romans(_valid_rows()) == {1: 1000.0, 2: -300.0, 3: 700.0}


def test_chain_closes_on_valid():
    assert _oci_chain_closes(_valid_rows())


def test_chain_fails_when_total_wrong():
    rows = _valid_rows()
    rows[-1] = _row(6, "III.", "total", 9999.0)
    assert not _oci_chain_closes(rows)


def test_degenerate_zero_profit_rejected():
    # I ~ 0 → reject (a 0==0 parse must not be treated as a valid chain)
    rows = [_row(1, "I.", "p", 0.0), _row(2, "II.", "o", 0.0), _row(3, "III.", "t", 0.0)]
    assert not _oci_chain_closes(rows)


def test_chain_needs_all_three_romans():
    assert not _oci_chain_closes([_row(1, "I.", "p", 1000.0), _row(3, "III.", "t", 1000.0)])


def test_score_tier1_for_validating():
    s = _oci_candidate_score(_valid_rows())
    assert s[0] == 1


def test_score_tier0_for_empty():
    assert _oci_candidate_score([]) == (0, 0, 0, 0)


def test_score_tier0_when_too_few_real_rows():
    # chain closes but only 2 rows carry a real (>1) amount → below the floor
    rows = [_row(1, "I.", "p", 1000.0), _row(2, "II.", "o", 0.0), _row(3, "III.", "t", 1000.0)]
    assert _oci_candidate_score(rows)[0] == 0
