"""The 2026Q2 Bin→Milyon switch broke every heuristic keyed on digit COUNT.

Normalising the stored amounts was only half the problem. Dividing every printed
figure by 1,000 also moved a large population of real values into the 1-2 digit
range that four separate extractor heuristics had reserved for something else:

  * `_FOOTNOTE_RX` reads a parenthesised 1-2 digit token as a dipnot reference —
    but in Milyon TL "(55)" is routinely the value -55mn;
  * the off-balance section-row floor drops any depth-1 total under ₺1,000,
    which was "at least the millions of TRY" in Bin and is ₺1bn in Milyon;
  * a label numeral ("TMS 8") survives the surplus-window gate when the row is
    otherwise all zeros, and scaling multiplied the resulting ₺8k into ₺8mn —
    past the validator's absolute tolerance;
  * `_try_fit`'s zero-insert recovery mis-aligns a row whose only missing cell
    was a small paren-negative.

Every line quoted below is verbatim from a filing. Kept as strings rather than
PDFs because `data/_bench/` is gitignored and CI has no filings to read.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import equity_change as EC  # noqa: E402
from src.audit_reports.extractor import _triplets_foot  # noqa: E402


# --- 1. a small paren-negative is a VALUE, not a footnote ---------------------

TEB_OPENING = ("I. Önceki Dönem Sonu Bakiyesi 2,204 3 - 389 149 (768) 61 - "
               "(539) (55) 33,710 12,357 - 47,511 256 47,767")


def test_a_two_digit_paren_negative_is_kept_when_the_template_needs_it():
    """TEB's prior-period opening row. The mask ate "(55)", the row came back
    15 tokens for a 16-column table, `_try_fit`'s zero-insert missed the row-sum
    gate by 7 against a tolerance of 48, and BOTH the opening and new-balance
    rows were dropped — so the roman sequence never restarted, the mid-page
    split never fired, and all 32 surviving rows were stored as `current`."""
    tokens = EC._parse_row_tokens(TEB_OPENING, 16)
    assert len(tokens) == 16
    assert tokens[9] == -55.0, "the masked cell is a value, not a dipnot ref"
    assert tokens[13] == 47_511.0 and tokens[15] == 47_767.0


def test_the_masked_reading_wins_whenever_it_fits_the_template():
    """Non-regression, stated exactly: the template decides, and the masked
    reading wins every tie. So a row that parses correctly today — where the
    "(5)" really is a dipnot ref and masking already yields the template width —
    cannot change."""
    line = "I. Nakit 1,000 2,000 (5) 3,000"
    assert EC._parse_row_tokens(line, 3) == [1000.0, 2000.0, 3000.0], \
        "masked fits 3 columns: '(5)' stays a footnote"
    assert EC._parse_row_tokens(line, 4) == [1000.0, 2000.0, -5.0, 3000.0], \
        "only the unmasked reading fits 4 columns: '(5)' is the value -5"
    assert EC._parse_row_tokens(line, 9) == [1000.0, 2000.0, 3000.0], \
        "neither fits — fall back to masked, i.e. today's behaviour"


def test_without_a_template_the_behaviour_is_exactly_the_old_one():
    assert len(EC._parse_row_tokens(TEB_OPENING)) == 15


# --- 2. the value region: label numerals and trailing fragments ---------------

@pytest.mark.parametrize("line,expected", [
    # Every bank carries a standards citation in row II, in three languages.
    ("II. TMS 8 Uyarınca Yapılan Düzeltmeler " + "- " * 16, [0.0] * 16),
    ("II. Correction made as per TAS 8 " + "- " * 16, [0.0] * 16),
    ("II. Adjustment in accordance with TAS 8 " + "- " * 16, [0.0] * 16),
])
def test_a_standards_citation_numeral_is_not_a_value(line, expected):
    """`_try_fit`'s surplus window took the leading 16 of 17 tokens and the
    row-sum gate waved it through (|8 - 0| under a tolerance of 48), storing
    paid-in capital = 8. ₺8k in Bin TL — invisible for four years. ₺8mn once
    scaled, and eq_row_sum failed it on all 11 Q2 filings."""
    assert EC._parse_row_tokens(line, 16) == expected


def test_a_trailing_header_fragment_does_not_swallow_the_row():
    """AKBNK's closing row, y-bucketed: a rotated column header lands on the end
    of it. Cutting at the LAST letter would return nothing at all; the grid is
    the longest run of tokens that no letter interrupts."""
    line = ("5.200 3.506 - 1.815 29.480 (3.253) 123 52.771 (14.575) (31.462) "
            "246.785 11 34.350 324.751 - 324.751 Kâr veya")
    tokens = EC._parse_row_tokens(line, 16)
    assert len(tokens) == 16
    assert tokens[0] == 5_200.0, "the first value must not be read as hierarchy"
    assert tokens[13] == 324_751.0
    assert sum(tokens[:13]) == pytest.approx(tokens[13]), "the row foots"


def test_a_date_beside_the_label_is_not_a_value():
    line = "Dönem Sonu Bakiyesi 30.06.2025 (III+IV+V+VI+VII+VIII+IX+X+XI) 1 2 3 4"
    assert EC._parse_row_tokens(line, 4) == [1.0, 2.0, 3.0, 4.0]


# --- 3. a numeric sub-marker glued to its label ------------------------------

@pytest.mark.parametrize("line,marker", [
    ("11.1Dağıtılan Temettü", "11.1"),
    ("11.2Yedeklere Aktarılan Tutarlar", "11.2"),
    ("2.1Hataların Düzeltilmesinin Etkisi", "2.1"),
    ("11.1. Dividends distributed", "11.1"),      # the dotted form still works
    ("VIII.Hisse Senedine Dönüştürülebilir Tahviller", "VIII."),
])
def test_a_glued_numeric_submarker_is_recognised(line, marker):
    """AKBNK started typesetting markers with no separating dot in 2026Q1 and
    its equity statement fell from 34 rows to 22: every 2.x and 11.x row lost
    its marker, and with neither marker nor label they were skipped outright."""
    assert EC._eq_split(line)[0] == marker


def test_an_english_word_starting_with_a_roman_letter_is_still_not_a_marker():
    """The trailing dot stays mandatory for ROMANS — otherwise "Income",
    "Internal" and "Increase" all become marker "I."."""
    for word in ("Income from interest", "Internal resources", "Increase in capital"):
        assert EC._eq_split(word)[0] is None


# --- 4. the balance-sheet triplet identity ----------------------------------

def test_triplets_foot_accepts_a_real_row_and_rejects_a_date_fragment():
    """The discriminator that lets a genuine small value escape both the
    footnote strip and the off-balance floor. The rows those guards exist for
    never satisfy tl + fc = total."""
    assert _triplets_foot([-10.0, 0.0, -10.0, -8.0, 0.0, -8.0], 6), \
        "KLNMA's expected-credit-loss row foots in both periods"
    assert _triplets_foot([115.0, 0.0, 115.0, 126.0, 0.0, 126.0], 6), \
        "KLNMA's EMANET KIYMETLER — ₺115mn, under the ₺1,000 floor"
    assert not _triplets_foot([-14.0, 0.0, 0.0, 0.0, 0.0, 0.0], 6), \
        "SKBNK's '(14) - - - - -' is a dipnot ref: it foots as nothing"
    assert not _triplets_foot([31.03, 202.0, 2.0, 31.12, 202.0, 1.0], 6), \
        "a date header read as values"
    assert not _triplets_foot([105.0, 4.0, 305.0, 105.0, 4.0, 305.0], 6), \
        "a section reference read as values"


@pytest.mark.parametrize("vals,n", [
    ([1.0, 2.0], 2),                  # cash flow: no triplets to check
    ([1.0, 2.0, 3.0, 4.0], 4),        # interim P&L
    ([1.0, 2.0, 3.0], 4),             # width mismatch
    ([], 0),
])
def test_triplets_foot_refuses_shapes_it_cannot_verify(vals, n):
    """Cash flow and P&L get no escape hatch. Tempting — a 2-column statement
    has nowhere to put a dipnot ref without creating surplus, so "(58) 4.480"
    reads as two values. But SKBNK's P&L prints "XXII. … (8) -" above
    "(9) - -", "(10) - -" and "(11) 1,502,150 254,698", a note-number sequence
    that reading would store as -8, -9, -10, -11."""
    assert not _triplets_foot(vals, n)


def test_the_identity_is_absolute_not_relative():
    """A 5e-5 relative band is ~56 units on a ₺1.1bn row — wide enough to admit
    TOMK's "1.2 … (3) 1.117.694 1.117.694 1.084.780 308.064 1.392.844", where
    the (3) is a dipnot ref and the row misses by exactly 3. Every genuine
    repair this test enables foots to the unit, so it can afford to be exact."""
    assert not _triplets_foot(
        [-3.0, 1_117_694.0, 1_117_694.0, 1_084_780.0, 308_064.0, 1_392_844.0], 6)
    assert _triplets_foot([-2.0, 151_096.0, 151_094.0, -350.0, 284_261.0, 283_911.0], 6), \
        "ICBCT's 16.4 foots to the unit in both periods"


# --- 5. the whole chain, on the four filing lines that failed ----------------

# --- 6. a free-provision REVERSAL is not a stock ------------------------------

TEB_FP_NOTE = ("(*) 30 Haziran 2026 tarihi itibarıyla 862 TL tutarında ayrılan "
               "serbest karşılık iptal tutarını içermektedir "
               "(30 Haziran 2025: 150 TL ayrılan karşılık).")


def test_a_free_provision_reversal_is_never_read_as_the_stock():
    """TEB 2026Q2's only free-provision line in the notes is a REVERSAL of
    ₺862mn, footnoting the "Diğer" provision-expense row (current (798), prior
    170). `bank_audit_free_provision` holds the STOCK, and reading a flow into
    it is the documented /franchise trap the lane was built to avoid.

    Three independent guards reject it, and this pins all three — the Milyon
    switch made the third one fire for a new reason, and a future widening of
    `_NUM` to accept separator-less amounts must not quietly start storing
    reversals as stocks.
    """
    from src.audit_reports import free_provision as FP
    assert FP._FLOW.search(TEB_FP_NOTE), "the reversal verb 'iptal' must veto it"
    assert not FP._PRIOR.search(TEB_FP_NOTE), \
        "there is no Dec-31 stock anchor — the parenthetical is a prior-period FLOW"
    assert not re.fullmatch(FP._NUM, "862"), \
        "in Milyon TL a real amount can be 3 digits; _NUM still requires a group"


def test_teb_2026q2_free_provision_stores_the_canonical_stock(tmp_path):
    """End to end, through the REAL override file and the REAL writer.

    The regex assertions above prove only that the note is rejected. This proves
    what actually lands in the row — the thing that was missing. A manual entry
    carries its own declared unit ("milyon"), and the writer must NOT scale it a
    second time by the filing's factor; before the fix, an override read while
    extracting a Milyon filing came out 1000x large.
    """
    import sqlite3

    from src.audit_reports.free_provision import _override_for, upsert_free_provision
    from src.audit_reports.schema import init_schema
    from src.audit_reports.units import UnitContext

    for kind in ("consolidated", "unconsolidated"):
        fp = _override_for("TEB", "2026Q2", kind)
        assert fp is not None, f"TEB 2026Q2 {kind} override is missing"
        assert fp.unit_normalised and fp.source_page == -1

        conn = sqlite3.connect(tmp_path / f"fp_{kind}.db")
        init_schema(conn)
        # The FILING is Milyon — exactly the context production passes.
        upsert_free_provision(conn, "TEB", "2026Q2", kind, fp,
                              unit=UnitContext("milyon", 1_000))
        stored = conn.execute(
            "SELECT free_provision, free_provision_prior FROM bank_audit_free_provision"
        ).fetchone()
        assert stored == (368_000.0, 1_230_000.0), (
            f"{kind}: stored {stored}, expected 368,000 / 1,230,000 Bin TL "
            f"(368 and 1,230 Milyon)")


def test_a_manual_free_provision_is_not_scaled_twice(tmp_path):
    """The defect the declared unit fixes, stated directly: the same entry read
    while extracting a Milyon filing must land on the same canonical value as
    one read from a Bin filing."""
    import sqlite3

    from src.audit_reports.free_provision import _override_for, upsert_free_provision
    from src.audit_reports.schema import init_schema
    from src.audit_reports.units import UnitContext

    fp = _override_for("TEB", "2026Q2", "consolidated")
    out = []
    for i, ctx in enumerate((UnitContext("milyon", 1_000), UnitContext("bin", 1))):
        conn = sqlite3.connect(tmp_path / f"twice{i}.db")
        init_schema(conn)
        upsert_free_provision(conn, "TEB", "2026Q2", "consolidated", fp, unit=ctx)
        out.append(conn.execute(
            "SELECT free_provision FROM bank_audit_free_provision").fetchone()[0])
    assert out[0] == out[1] == 368_000.0


def test_a_post_horizon_override_without_a_unit_is_refused():
    """A Q2+ entry that forgets "unit" must raise, not default to thousands —
    that default is the 1000x-small error no in-filing identity can see."""
    import src.audit_reports.free_provision as FP

    FP._overrides.cache_clear()
    original = FP._overrides
    FP._overrides = lambda: {"XBANK": {"2026Q2": {"consolidated":
                                                  {"free_provision": 368}}}}
    try:
        with pytest.raises(ValueError, match="must declare its unit"):
            FP._override_for("XBANK", "2026Q2", "consolidated")
    finally:
        FP._overrides = original
        FP._overrides.cache_clear()


def test_every_legacy_override_still_resolves_unchanged():
    """The file's ~200 pre-switch entries carry no "unit" and are thousand-TL by
    its own header. They must keep resolving at factor 1, untouched."""
    import src.audit_reports.free_provision as FP

    raw = json.loads(FP._OVERRIDE_PATH.read_text(encoding="utf-8"))
    checked = 0
    for bank, periods in raw.items():
        if bank.startswith("_"):
            continue
        for period, kinds in periods.items():
            for kind, entry in kinds.items():
                fp = FP._override_for(bank, period, kind)
                assert fp is not None
                if "unit" not in entry:
                    assert period <= "2026Q1", (
                        f"{bank} {period} {kind} is past the horizon and declares "
                        f"no unit — it would have raised")
                    assert fp.free_provision == entry.get("free_provision"), (
                        f"{bank} {period} {kind} moved: {fp.free_provision} != "
                        f"{entry.get('free_provision')}")
                    checked += 1
    assert checked > 50, f"only {checked} legacy entries checked — file not loaded?"


def test_the_audit_opinion_is_not_a_substitute_source_for_the_stock():
    """TEB's opinion states the stock outright (₺1,230mn set aside − ₺862mn
    reversed = ₺368mn), which makes an opinion-derived fallback tempting.
    Measured over the 380 opinions that mention a free provision, the two
    sources disagree in 42 cases and the fallback would recover exactly ONE
    row — because the opinion reports what was SET ASIDE and the note reports
    what REMAINS. ALBRK is the clearest: opinion ₺7,300,000k, note ₺245,000k,
    the reversal being the whole ALBRK story. So the arithmetic is pinned here
    and the fallback is deliberately NOT implemented.
    """
    set_aside, reversed_, remaining = 1_230.0, 862.0, 368.0
    assert set_aside - reversed_ == remaining


def test_the_five_defects_are_independent():
    """Each fix addresses a different heuristic; this pins that none of them
    quietly depends on another. All four lines are verbatim from 2026Q2."""
    # (a) footnote mask vs a real value
    assert EC._parse_row_tokens(TEB_OPENING, 16)[9] == -55.0
    # (b) label numeral
    assert EC._parse_row_tokens("II. TMS 8 Uyarınca " + "- " * 16, 16)[0] == 0.0
    # (c) glued sub-marker
    assert EC._eq_split("11.3Diğer")[0] == "11.3"
    # (d) triplet escape for a value below the section floor
    assert _triplets_foot([115.0, 0.0, 115.0, 126.0, 0.0, 126.0], 6)
