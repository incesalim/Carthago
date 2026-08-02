"""The triage engine: what it may conclude, and what it must refuse to.

A triage note is a hypothesis a human acts on, so a wrong-but-confident label
costs more than no label at all. Each case below pins one of the discriminations
that cost real debugging to find, and most of them are guards against the engine
over-claiming:

  * a statement spans several pages, so judging it against one page marks its own
    figures absent and invents an extraction defect out of ordinary pagination;
  * a figure below six digits is not distinctive, so "it's on the page" is
    satisfied by chance and must never be evidence;
  * one value matching at ÷1000 is a coincidence on a page dense with figures —
    a unit switch needs several values agreeing on the same factor;
  * BRSA statements legitimately mix 'I.' with '2.1', so mixed dot styles are NOT
    a hierarchy defect; the same node under two spellings is;
  * "every stored figure is printed" does not establish that the source is at
    fault — a figure taken from the wrong line is still printed.

No PDF and no database: the page is synthesised, so this runs in the minimal-deps
CI job.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.audit_reports import triage as T  # noqa: E402


def page(tokens, page1=1, **kw):
    """A PageFacts from ('text', x) pairs, laid out on one line each."""
    facts = T.PageFacts(page1=page1, **kw)
    facts.tokens = [(x, x + 40.0, t) for t, x in tokens]
    facts.rows = [[tok] for tok in facts.tokens]
    return facts


def cell(column, value, verdict, label="row", page1=1):
    return T.CellCheck(label, column, value, verdict, page1)


# --------------------------------------------------------------- value matching

def test_finds_a_value_in_either_separator_style():
    p = page([("1.234.567", 100)])
    assert T.find_value(p, 1234567)[0] == "exact"
    assert T.find_value(page([("1,234,567", 100)]), 1234567)[0] == "exact"
    assert T.find_value(page([("7.654.321", 100)]), 1234567)[0] == "absent"


def test_wrapped_cell_is_a_prefix_plus_the_remaining_digits():
    """11,476,247,288 does not fit its column, so the final digits drop to a
    second line inside the same cell. get_text() emits two tokens and discards
    the cell border: position is not cell membership."""
    p = page([("11.476.247.28", 100), ("8", 150)])
    verdict, ev = T.find_value(p, 11476247288)
    assert verdict == "wrapped"
    assert "8" in ev


def test_short_values_are_reported_unjudgeable_not_absent():
    """A ratio or a branch count is not distinctive; a page prints hundreds of
    short numbers, so presence would be satisfied by chance. Such a value must
    never be called ABSENT either — that would manufacture an extraction defect
    out of a figure nobody can check."""
    assert not T.judgeable(15.62)
    assert not T.judgeable(711)
    assert T.judgeable(1_597_256)
    rows = [_Row({"item_name": "branches", "branches_total": 711,
                  "cet1_capital": 1_597_256})]
    got = {c.column: c.verdict for c in
           T.audit_stored_values([page([("1.597.256", 100)])], rows,
                                 ["branches_total", "cet1_capital"])}
    assert got == {"branches_total": "unjudgeable", "cet1_capital": "exact"}


# ------------------------------------------------------------ multi-page window

def test_a_statement_spanning_pages_is_judged_across_all_of_them():
    """The §4 capital table runs CET1, then AT1/Tier1, then RWA over three
    consecutive pages. Judging it against the best single page would mark two
    thirds of its own figures absent."""
    window = [page([("2.169.272", 100)], page1=31),
              page([("2.862.707", 100)], page1=32),
              page([("18.350.596", 100)], page1=33)]
    assert T.find_in_window(window, 18350596)[:2] == ("exact", 33)
    assert T.find_in_window(window, 2169272)[:2] == ("exact", 31)
    assert T.find_in_window(window, 99999999)[0] == "absent"


def test_window_stops_at_the_neighbouring_statement():
    """Adjacent statements share figures — total equity is printed on the balance
    sheet too — so a page must carry a real SHARE of the statement to join, or the
    window walks into the next table and imports its row markers."""
    scores = {10: 2, 11: 3, 12: 40, 13: 38, 14: 2}
    assert T.statement_window(scores, 12) == [12, 13]


def test_window_keeps_a_genuine_continuation_page():
    scores = {30: 0, 31: 9, 32: 12, 33: 8, 34: 1}
    assert T.statement_window(scores, 32) == [31, 32, 33]


# ------------------------------------------------------------------ unit switch

def test_one_scaled_match_is_not_a_unit_switch():
    """For any large value some shorter token on a dense page matches its
    thousands-scaled form. Corroboration is mandatory."""
    p = page([("1.597.256", 100), ("2.359.569", 200), ("3.956.825", 300)])
    cells = [cell("tier1_capital", 1_597_256_000, "absent")]
    assert T.detect_unit_switch([p], cells) is None


def test_several_values_agreeing_on_one_factor_is_a_unit_switch():
    p = page([("1.597.256", 100), ("2.359.569", 200),
              ("3.956.825", 300), ("18.350.596", 400)])
    cells = [cell("cet1_capital", 1_597_256_000, "absent"),
             cell("additional_tier1_capital", 2_359_569_000, "absent"),
             cell("tier1_capital", 3_956_825_000, "absent"),
             cell("total_rwa", 18_350_596_000, "absent")]
    f = T.detect_unit_switch([p], cells)
    assert f is not None and f.label == T.UNIT_SWITCH


def test_scaled_search_ignores_a_scaled_form_too_short_to_be_distinctive():
    """Dividing a 7-digit figure by 1000 leaves 4 digits, which match by chance.
    Refusing those is why the in-filing check cannot see a sector-wide Bin→Milyon
    change at all — that one is the cross-period watch's job, not this one's."""
    assert T.find_scaled(page([("1.597", 100)]), 1_597_256) is None


# ------------------------------------------------------------------- hierarchy

def test_mixed_roman_and_decimal_markers_are_not_a_defect():
    """BRSA romans carry a dot and their children do not. That is the normal
    convention across the whole corpus, not a hierarchy bug."""
    rows = [{"hierarchy": h} for h in ("I.", "II.", "2.1", "2.2", "III.", "11.3")]
    assert T.detect_trailing_dot([_Row(r) for r in rows], None) is None


def test_the_same_node_under_two_spellings_is_a_defect():
    rows = [{"hierarchy": h} for h in ("1", "1.", "1.1", "2.")]
    f = T.detect_trailing_dot([_Row(r) for r in rows], None)
    assert f is not None and f.label == T.TRAILING_DOT_HIERARCHY


def test_roman_rank_orders_the_brsa_spine():
    assert T._roman_rank("XI.") == 11
    assert T._roman_rank("XXV.") == 25
    assert T._roman_rank("2.1") is None


# --------------------------------------------------------------- missing rows

def test_marker_regex_matches_a_label_glued_to_its_marker():
    """fitz emits 'I.Önceki Dönem Sonu Bakiyesi' with no space. A marker pattern
    that insists on whitespace matches almost nothing on a real statement page."""
    assert T._ROW_MARKER_RX.match("I.Önceki Dönem Sonu Bakiyesi").group("h") == "I."
    assert T._ROW_MARKER_RX.match("III. Yeni Bakiye (I+II)").group("h") == "III."
    assert T._ROW_MARKER_RX.match("11.3Diğer").group("h") == "11.3"


def test_token_value_reads_turkish_grouping_and_parentheses():
    assert T._token_value("302.601.785") == 302601785
    assert T._token_value("(11.449.360)") == 11449360
    assert T._token_value("-") is None
    assert T._token_value("Bakiyesi") is None


# ------------------------------------------------------- refusing to over-claim

def test_all_figures_printed_is_not_enough_for_a_source_defect():
    """A figure lifted from the wrong line is still a figure printed on the page.
    If the figure the identity REQUIRES is also printed, a correct cell exists and
    the verdict is a slip, not 'the bank's statement is wrong'."""
    p = page([("22.744.249", 100), ("97.286.237", 300)])
    cells = [cell("total_capital", 22_744_249, "exact")]
    checks = [T.BrokenCheck("cap_composition", "Total = Tier1 + Tier2 [prior]",
                            97_286_237.0, 22_744_249.0, -74_541_988.0)]
    out = T.classify_partition([p], cells, checks)
    assert [f.label for f in out] == [T.COLUMN_SLIP]


def test_ratio_only_identities_are_refused_rather_than_guessed():
    """Ratios are argued in numbers too short to presence-check, so there is no
    evidence either way — and saying so beats a confident label."""
    p = page([("339.170.127", 100)])
    cells = [cell("cet1_capital", 339_170_127, "exact")]
    checks = [T.BrokenCheck("cap_ratio_reconcile", "Tier1 ratio = Tier1 / RWA * 100",
                            84.02, 14.42, -69.6)]
    out = T.classify_partition([p], cells, checks)
    assert [f.label for f in out] == [T.UNCLASSIFIED]


def test_source_defect_needs_the_required_figure_to_be_absent():
    p = page([("22.744.249", 100)])
    cells = [cell("total_capital", 22_744_249, "exact")]
    checks = [T.BrokenCheck("cap_composition", "Total = Tier1 + Tier2",
                            97_286_237.0, 22_744_249.0, -74_541_988.0)]
    out = T.classify_partition([p], cells, checks)
    assert [f.label for f in out] == [T.SOURCE_DEFECT]


def test_dropped_cell_is_proved_by_the_shortfall_being_printed():
    """The one cause the filing can prove rather than suggest: the identity is
    short by D, D is printed, and we store a 0 in a column it sums over."""
    p = page([("2.359.569", 100)])
    cells = [cell("additional_tier1_capital", 0.0, "zero"),
             cell("cet1_capital", 1_597_256, "exact")]
    checks = [T.BrokenCheck("cap_composition", "Tier1 = CET1 + AT1 [prior]",
                            3_956_825.0, 1_597_256.0, -2_359_569.0)]
    f = T.detect_dropped_cell([p], cells, checks)
    assert f is not None
    assert f.label == T.DROPPED_CELL and f.confidence == "confirmed"


def test_dropped_cell_refuses_the_circular_case():
    """When the stored side is 0 the shortfall EQUALS the figure the identity
    wants, so "the shortfall is printed" restates the premise and says nothing
    about which cell went missing. Refusing keeps the note from pinning a remedy
    on whichever unrelated zeros the partition happens to hold."""
    p = page([("5.200.000", 100)])
    cells = [cell("minority_interest", 0.0, "zero"),
             cell("share_cancellation_profits", 0.0, "zero")]
    checks = [T.BrokenCheck("eq_paid_in_capital", "equity closing paid-in capital vs BS",
                            5_200_000.0, 0.0, 5_200_000.0)]
    assert T.detect_dropped_cell([p], cells, checks) is None


def test_dropped_cell_names_the_column_the_identity_sums_over():
    p = page([("2.359.569", 100)])
    cells = [cell("additional_tier1_capital", 0.0, "zero"),
             cell("minority_interest", 0.0, "zero")]
    checks = [T.BrokenCheck("cap_composition", "Tier1 = CET1 + AT1 [prior]",
                            3_956_825.0, 1_597_256.0, -2_359_569.0)]
    f = T.detect_dropped_cell([p], cells, checks)
    assert f is not None
    assert "additional_tier1_capital" in f.detail
    assert "minority_interest" not in f.detail


def test_dropped_cell_stays_silent_without_a_stored_zero():
    p = page([("2.359.569", 100)])
    cells = [cell("cet1_capital", 1_597_256, "exact")]
    checks = [T.BrokenCheck("cap_composition", "Tier1 = CET1 + AT1",
                            3_956_825.0, 1_597_256.0, -2_359_569.0)]
    assert T.detect_dropped_cell([p], cells, checks) is None


def test_verdict_takes_the_most_severe_finding():
    note = T.TriageNote("AKBNK", "2026Q1", "consolidated", "equity_change")
    note.findings = [T.Finding(T.SOURCE_DEFECT, "x"), T.Finding(T.DROPPED_CELL, "y")]
    assert note.verdict == T.DROPPED_CELL


def test_every_taxonomy_label_carries_a_remedy():
    """The note tells a human what to DO. A label with no remedy is a dead end."""
    for label in T.SEVERITY_ORDER:
        assert T.REMEDY.get(label), label


# ------------------------------------------------------------ cross-period watch

def test_previous_quarter_wraps_the_year():
    from watch_cross_period import prev_period, scale_factor
    assert prev_period("2026Q1") == "2025Q4"
    assert prev_period("2025Q3") == "2025Q2"
    assert prev_period("garbage") is None
    # a clean power of ten is a unit change; ordinary growth is not
    assert scale_factor(1_000_000, 1_000) == 1000.0
    assert scale_factor(1_000, 1_000_000) == 0.001
    assert scale_factor(1_150, 1_000) is None


class _Row(dict):
    """A stand-in for sqlite3.Row: item access plus .keys()."""

    def keys(self):            # noqa: D102 - dict already provides it
        return list(super().keys())
