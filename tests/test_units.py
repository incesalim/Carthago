"""Reporting-unit normalisation: the 2026Q2 Bin -> Milyon switch.

The sector changed denomination in 2026Q2 and no in-filing check can see it —
every structural validator is a ratio of figures sharing a scale, so all eleven
Q2 filings footed perfectly while every stored figure was wrong by 1000x.

Two failure directions, both silent:
  * an amount left unscaled  -> the figure is 1000x too small;
  * a RATIO scaled by 1000   -> a 15% capital ratio becomes 15,000.

So these tests pin the classification exhaustively, pin that old filings are
untouched, and pin that an unreadable unit refuses rather than assumes.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import units as U  # noqa: E402
from src.audit_reports.registry import AUDIT_TABLES  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402

sys.path.insert(0, str(REPO / "scripts"))
from build_bank_audit_stages import build_stages  # noqa: E402


# --- the classification must be exhaustive -----------------------------------

@pytest.fixture(scope="module")
def schema():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


def _numeric_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")
            if r[2].upper() in ("REAL", "INTEGER", "INT", "NUMERIC")}


def test_every_numeric_column_is_classified(schema):
    """THE gate. A new numeric column that is money and unlisted is stored 1000x
    too small; one that is a ratio and listed as money is 1000x too large. Both
    pass every validator, so nothing else would catch it."""
    unclassified = {}
    for t in AUDIT_TABLES:
        if not schema.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (t,)).fetchone():
            continue
        known = U.MONEY_COLUMNS.get(t, frozenset()) | U.NON_MONEY_NUMERIC.get(t, frozenset())
        missing = _numeric_columns(schema, t) - known
        if missing:
            unclassified[t] = sorted(missing)
    assert not unclassified, (
        f"numeric columns classified as neither money nor non-money: {unclassified}")


def test_no_column_is_classified_as_both(schema):
    for t in AUDIT_TABLES:
        both = U.MONEY_COLUMNS.get(t, frozenset()) & U.NON_MONEY_NUMERIC.get(t, frozenset())
        assert not both, f"{t}: {sorted(both)} is both money and not-money"


def test_the_classification_names_only_real_columns(schema):
    """A typo in the registry silently stops scaling that column."""
    for t in set(U.MONEY_COLUMNS) | set(U.NON_MONEY_NUMERIC):
        if not schema.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (t,)).fetchone():
            continue
        real = {r[1] for r in schema.execute(f"PRAGMA table_info({t})")}
        named = U.MONEY_COLUMNS.get(t, frozenset()) | U.NON_MONEY_NUMERIC.get(t, frozenset())
        assert named <= real, f"{t}: {sorted(named - real)} not in the table"


def test_ratios_and_counts_are_never_money():
    """Verified against 4.5 years of stored values, not assumed: capital ratios
    run 4.85-138 while the amounts in the same table average 64,314,574; stage
    coverages are fractions; 925 of 933 lcr_total values sit below 1000."""
    assert "cet1_ratio" not in U.money_columns("bank_audit_capital")
    assert "capital_adequacy_ratio" not in U.money_columns("bank_audit_capital")
    for c in ("stage1_coverage", "stage2_coverage", "stage3_coverage"):
        assert c not in U.MONEY_COLUMNS["bank_audit_stages"]
    assert U.money_columns("bank_audit_liquidity") == frozenset(), \
        "LCR, NSFR and leverage are all ratios — nothing in liquidity is money"
    assert U.money_columns("bank_audit_profile") == frozenset(), \
        "branch and personnel counts are not money"


def test_the_money_side_covers_the_statements_that_carry_figures():
    for t, col in [("bank_audit_balance_sheet", "amount_tl"),
                   ("bank_audit_profit_loss", "amount"),
                   ("bank_audit_oci", "amount"),
                   ("bank_audit_cash_flow", "amount"),
                   ("bank_audit_capital", "total_rwa"),
                   ("bank_audit_npl_movement", "closing_balance"),
                   ("bank_audit_fx_position", "net_position"),
                   ("bank_audit_repricing", "cumulative_gap"),
                   ("bank_audit_free_provision", "free_provision"),
                   ("bank_audit_loans_by_sector", "ecl_amount"),
                   ("bank_audit_credit_quality", "total_amount"),
                   ("bank_audit_equity_change", "total_equity")]:
        assert col in U.money_columns(t), f"{t}.{col} must be scaled"


def test_stage_amounts_are_money_but_are_never_scaled_at_write():
    """bank_audit_stages is DERIVED wholesale from bank_audit_credit_quality by
    scripts/build_bank_audit_stages.py. Its amounts are money — so they belong in
    the classification — but they arrive already normalised. Scaling them again
    is x1,000,000, and because every coverage it computes is amount/amount the
    ratios would still foot perfectly. So the writer path refuses outright."""
    assert "total_ecl" in U.MONEY_COLUMNS["bank_audit_stages"]
    assert "bank_audit_stages" in U.DERIVED_MONEY_TABLES
    assert "bank_audit_stages" not in U.RAW_MONEY_TABLES
    with pytest.raises(ValueError, match="derived"):
        U.money_columns("bank_audit_stages")


def test_exactly_twelve_raw_writers_need_scaling():
    """12 raw monetary tables + 1 derived = the 13 that carry money."""
    assert len(U.RAW_MONEY_TABLES) == 12
    assert len(U.DERIVED_MONEY_TABLES) == 1
    assert U.RAW_MONEY_TABLES | U.DERIVED_MONEY_TABLES == set(U.MONEY_COLUMNS)


# --- fail closed --------------------------------------------------------------

def test_an_unknown_table_is_rejected_not_silently_unscaled():
    """Returning an empty set for an unknown name skips scaling in silence —
    the exact failure this module exists to prevent."""
    with pytest.raises(ValueError, match="unknown table"):
        U.money_columns("bank_audit_not_a_table")
    with pytest.raises(ValueError, match="unknown table"):
        U.scale_mapping("bank_audit_not_a_table", {"amount": 1.0}, 1_000)


def test_a_column_row_length_mismatch_is_rejected():
    """zip() would truncate to the shorter side; a money column falling off the
    end is stored 1000x too small with nothing to notice."""
    with pytest.raises(ValueError, match="Refusing to zip-truncate"):
        U.scale_sequence("bank_audit_balance_sheet",
                         ["bank_ticker", "amount_tl", "item_order"],
                         ("AKBNK", 2.0), 1_000)


def test_factor_one_takes_the_same_path_as_factor_one_thousand():
    """No bypass: the claim that old filings run the same code is only true if
    factor 1 is a real multiply, not an early return."""
    import ast
    import inspect
    # AST, not text: the docstrings deliberately mention `factor == 1` while
    # explaining why there is no such branch, and a substring check reads those.
    for fn in (U.scale_mapping, U.scale_amount, U.scale_sequence):
        tree = ast.parse(inspect.getsource(fn).lstrip())
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) \
                    and node.left.id == "factor":
                raise AssertionError(
                    f"{fn.__name__} branches on `factor`; a factor==1 shortcut "
                    f"leaves the old-filing path untested by every test that "
                    f"exercises the new one")
    row = {"amount_tl": 3.0, "item_order": 1}
    assert U.scale_mapping("bank_audit_balance_sheet", row, 1) == \
        {"amount_tl": 3.0, "item_order": 1}


def test_thirteen_tables_carry_money_and_nine_carry_none():
    """13 + 9 = the 22 D1 audit tables. Pinned so adding a table forces
    a deliberate classification rather than a silent default to not-money."""
    money = set(U.MONEY_COLUMNS)
    none = {"bank_audit_liquidity", "bank_audit_profile", "bank_audit_opinion",
            "bank_audit_validation", "bank_audit_extractions",
            "bank_audit_pl_roles", "bank_audit_prose",
            "bank_audit_capture_manifest", "bank_audit_document_manifest"}
    assert len(money) == 13
    assert len(none) == 9
    assert money | none == set(AUDIT_TABLES)
    for t in none:
        assert U.money_columns(t) == frozenset()


# --- old audits must be untouched --------------------------------------------

@pytest.mark.parametrize("period", [
    "2022Q1", "2023Q4", "2024Q2", "2025Q4", "2026Q1"])
def test_pre_switch_periods_resolve_to_bin_without_reading_the_pdf(period):
    """THE old-audit guarantee. The July sweep read 550 filings and found no
    pre-2026Q2 filing using millions, so these resolve without opening anything
    — a detector regression cannot rescale 4.5 years of stored data, and a
    re-extraction of an old partition stores exactly what it stored before."""
    assert U.within_sweep(period)
    assert U.resolve_unit(period, pdf_path=None) == "bin"
    assert U.scale_factor(U.resolve_unit(period)) == 1


def test_a_bin_filing_scales_by_one_and_changes_nothing():
    row = {"amount_tl": 1234.5, "amount_fc": None, "item_order": 7}
    assert U.scale_mapping("bank_audit_balance_sheet", row, 1) == row


@pytest.mark.parametrize("period,expected", [
    ("2026Q1", True), ("2026Q2", False), ("2026Q3", False), ("2027Q1", False),
    ("2025Q4", True), ("2021Q4", True)])
def test_the_sweep_horizon_is_the_boundary(period, expected):
    assert U.within_sweep(period) is expected


def test_period_ordering_crosses_the_year_boundary():
    assert U.within_sweep("2025Q4") and not U.within_sweep("2026Q2")
    assert U._period_key("2026Q1") > U._period_key("2025Q4")


# --- the new regime -----------------------------------------------------------

def test_a_milyon_filing_scales_money_by_a_thousand():
    assert U.scale_factor("milyon") == 1_000
    row = {"amount_tl": 5.0, "amount_fc": 2.5, "amount_total": 7.5, "item_order": 3}
    out = U.scale_mapping("bank_audit_balance_sheet", row, 1_000)
    assert out == {"amount_tl": 5000.0, "amount_fc": 2500.0,
                   "amount_total": 7500.0, "item_order": 3}


def test_scaling_leaves_ratios_and_ordinals_alone():
    row = {"cet1_capital": 12.0, "cet1_ratio": 15.4,
           "capital_adequacy_ratio": 21.2, "source_page": 88}
    out = U.scale_mapping("bank_audit_capital", row, 1_000)
    assert out["cet1_capital"] == 12_000.0
    assert out["cet1_ratio"] == 15.4
    assert out["capital_adequacy_ratio"] == 21.2
    assert out["source_page"] == 88


def test_a_liquidity_row_is_never_scaled():
    row = {"lcr_total": 152.3, "lcr_fc": 210.0, "nsfr": 130.1,
           "leverage_ratio": 8.4, "source_page": 5}
    assert U.scale_mapping("bank_audit_liquidity", row, 1_000) == row


def test_null_stays_null_and_zero_stays_zero():
    """`null` is not `0`: a disclosure never made must not become a figure, and
    a disclosed zero is still zero at any scale."""
    row = {"amount": None}
    assert U.scale_mapping("bank_audit_profit_loss", row, 1_000)["amount"] is None
    assert U.scale_mapping("bank_audit_profit_loss", {"amount": 0}, 1_000)["amount"] == 0


def test_negative_amounts_scale_with_their_sign():
    """Deduction lines carry negative amounts; the sign must survive."""
    out = U.scale_mapping("bank_audit_profit_loss", {"amount": -4.5}, 1_000)
    assert out["amount"] == -4500.0


def test_the_positional_variant_agrees_with_the_mapping_one():
    cols = ["bank_ticker", "amount_tl", "item_order"]
    row = ("AKBNK", 2.0, 9)
    assert U.scale_sequence("bank_audit_balance_sheet", cols, row, 1_000) == \
        ("AKBNK", 2000.0, 9)


def test_milyar_is_recognised_even_though_no_filing_uses_it_yet():
    assert U.scale_factor("milyar") == 1_000_000


# --- refuse, never guess ------------------------------------------------------

def test_an_unknown_unit_refuses():
    """UNKNOWN means 'look at this filing', never 'assume thousands'."""
    with pytest.raises(ValueError, match="UNKNOWN"):
        U.scale_factor(None)


def test_an_unrecognised_unit_refuses():
    with pytest.raises(ValueError, match="unrecognised"):
        U.scale_factor("kurus")


def test_a_post_switch_period_with_no_pdf_is_unknown():
    assert U.resolve_unit("2026Q2", pdf_path=None) is None
    with pytest.raises(ValueError, match="UNKNOWN"):
        U.scale_factor(U.resolve_unit("2026Q2", pdf_path=None))


# --- the detector itself ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Tutarlar Bin Türk Lirası olarak ifade edilmiştir", "bin"),
    ("Amounts are expressed in Thousands of Turkish Lira", "bin"),
    ("Tutarlar Milyon Türk Lirası olarak", "milyon"),
    ("expressed in Million Turkish Lira", "milyon"),
    ("Milyar Türk Lirası", "milyar"),
    ("MILYON TURK LIRASI", "milyon"),
])
def test_the_declaration_is_read_in_either_language(text, expected):
    assert U.regex_unit([text]) == expected


def test_a_declaration_deep_in_the_front_matter_is_still_found():
    """Q4 filings hide it on p7-p17 behind the full annual opinion — the reason
    the window is 22 pages and not 8."""
    pages = ["cover"] * 16 + ["Tutarlar Milyon Türk Lirası olarak ifade edilmiştir"]
    assert U.regex_unit(pages) == "milyon"


def test_a_declaration_past_the_window_is_not_found():
    pages = ["cover"] * 30 + ["Milyon Türk Lirası"]
    assert U.regex_unit(pages) is None


def test_no_declaration_is_unknown_not_bin():
    assert U.regex_unit(["balance sheet", "cash flow"]) is None


# --- filings that contradict themselves --------------------------------------
#
# 12 of the 44 2026Q2 filings in R2 declare two different units inside the front
# 22 pages, because switching to Milyon left stale boilerplate behind. WHICH
# text is stale differs by bank, so no position rule and no counting rule works
# on its own. Each shape below is taken from a real filing.

_HEADER = "(Tutarlar aksi belirtilmedikçe {} Türk Lirası (“TL”) olarak ifade edilmiştir.)"
_LETTER = "Bankamız kayıtlarına uygun olarak, aksi belirtilmediği müddetçe {} Türk Lirası cinsinden hazırlanmış"
_SWITCH = ("finansal tabloların sunum para birimi Bin Türk Lirası (Bin TL) yerine "
           "Milyon Türk Lirası (Milyon TL) olarak değiştirilmiştir.")


def test_a_stale_auditor_letter_does_not_beat_the_statement_pages():
    """ANADOLU 2026Q2 unconsolidated. The letter on p4 still said `bin` while
    all 17 statement pages said Milyon; first-match believed the letter and the
    partition stored 1000x small — 212.6bn of assets became 0.2bn, and every
    in-filing identity still footed because they all scale together."""
    pages = ["cover", "", "", _LETTER.format("bin")] + \
            [_HEADER.format("Milyon")] * 10 + [_SWITCH]
    assert U.regex_unit(pages) == "milyon"


def test_the_switch_note_beats_stale_headers_AND_the_majority():
    """ATBANK 2026Q2 consolidated — the mirror image, and the reason neither
    "headers win" nor "majority wins" is the rule. Here 16 statement-page
    headers are the stale text and only the letter plus the switch note say
    Milyon. Counting pages gives 16 bin vs 2 milyon and would store this filing
    1000x TOO BIG."""
    pages = ["cover", "", "", _LETTER.format("milyon")] + \
            [_HEADER.format("Bin")] * 16 + [_SWITCH]
    assert U.regex_unit(pages) == "milyon"
    # and the tier that would have got it wrong, in isolation:
    assert Counter(["bin"] * 16 + ["milyon"] * 2).most_common(1)[0][0] == "bin"


def test_one_stale_translated_page_loses_to_the_majority():
    """HALKB 2026Q2 consolidated: bilingual, and the single English page still
    read "thousand Turkish Lira" against 16 Turkish pages saying Milyon. It is
    the one conflicting filing in the corpus with no switch note, so it is the
    only one tier 3 decides."""
    pages = [_HEADER.format("Milyon")] * 16 + \
            ["(Amounts expressed in thousand Turkish Lira (TRY) unless otherwise stated.)"]
    assert U.regex_unit(pages) == "milyon"


def test_an_even_split_with_no_switch_note_refuses():
    """Nothing establishes the unit, so UNKNOWN — which `scale_factor` turns
    into a refusal to store. A coin-flip here is a silent 1000x error."""
    pages = [_HEADER.format("Bin"), _HEADER.format("Milyon")]
    assert U.regex_unit(pages) is None
    with pytest.raises(ValueError, match="UNKNOWN"):
        U.scale_factor(U.regex_unit(pages))


def test_the_dotted_capital_I_normalises_instead_of_crashing():
    """`'MİLYON'.lower()` is 'mi̇lyon' (i + COMBINING DOT ABOVE), which is not a
    _NORM key. UNIT_RE matches the spelling, so the lookup used to raise
    KeyError. Live in the corpus — EMLAK ×14, ZIRAATK ×7, GARAN ×1 — and it
    never fired only because it was never the FIRST declaration."""
    assert U.regex_unit(["MİLYON TÜRK LİRASI"]) == "milyon"
    assert U.regex_unit(["BİN TÜRK LİRASI"]) == "bin"
    assert U._fold("MİLYON") == "milyon"


def test_the_english_switch_note_is_read_too():
    """No 2026Q2 filing exercises this — every bank that switched printed the
    Turkish sentence, bilingual ones included — so this pins the English arm by
    construction rather than by measurement."""
    pages = [_HEADER.format("Bin")] * 8 + [
        "The presentation currency of the financial statements has been changed "
        "from thousands of Turkish Lira to millions of Turkish Lira."]
    assert U.regex_unit(pages) == "milyon"


# --- end to end: credit_quality -> stages, scaled exactly once ---------------

def test_milyon_credit_quality_reaches_stages_multiplied_exactly_once(tmp_path):
    """THE derived-table proof.

    bank_audit_stages is built wholesale FROM bank_audit_credit_quality. If the
    writer scaled both, a Milyon filing would land in stages at x1,000,000 — and
    because every coverage stages computes is ecl/amount, both scaled, the ratios
    would still foot perfectly and no validator would see it.

    So: scale credit_quality on the way in, run the REAL builder, and assert the
    amounts arrive x1,000 (not x1,000,000) while coverage is untouched.
    """
    db = tmp_path / "stages.db"
    conn = sqlite3.connect(db)
    init_schema(conn)

    B, P, K = "TEB", "2026Q2", "consolidated"
    factor = U.scale_factor("milyon")
    assert factor == 1_000

    # As printed in a Milyon filing: 1,000 (=1bn TL) of stage-1 loans, 10 of ECL.
    printed = [
        # section,           s1,     s2,    s3,  total
        ("loans_amounts", 1_000.0, 200.0, 50.0, 1_250.0),
        ("loans_ecl",        10.0,  20.0, 25.0,    55.0),
    ]
    cols = ["bank_ticker", "period", "kind", "section", "period_type",
            "stage1_amount", "stage2_amount", "stage3_amount", "total_amount"]
    for section, s1, s2, s3, tot in printed:
        row = (B, P, K, section, "current", s1, s2, s3, tot)
        scaled = U.scale_sequence("bank_audit_credit_quality", cols, row, factor)
        conn.execute(
            f"INSERT INTO bank_audit_credit_quality ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})", scaled)
    conn.commit()
    conn.close()

    conn = sqlite3.connect(db)
    build_stages(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM bank_audit_stages WHERE bank_ticker=? AND period=? AND kind=?",
        (B, P, K)).fetchone()
    assert row is not None, "the builder produced no stages row"

    # x1,000 exactly — NOT x1,000,000.
    assert row["stage1_amount"] == 1_000_000.0
    assert row["stage2_amount"] == 200_000.0
    assert row["stage3_amount"] == 50_000.0
    assert row["stage1_ecl"] == 10_000.0
    assert row["stage3_ecl"] == 25_000.0

    # Coverage is ecl/amount — scale-invariant, and must equal the raw ratio.
    assert row["stage1_coverage"] == pytest.approx(10.0 / 1_000.0)
    assert row["stage3_coverage"] == pytest.approx(25.0 / 50.0)
    assert row["stage3_coverage"] <= 1.0, "a coverage ratio was scaled"
    conn.close()


def test_the_same_flow_at_bin_is_unchanged(tmp_path):
    """The old-filing control: identical inputs at factor 1 must land as printed."""
    db = tmp_path / "stages_bin.db"
    conn = sqlite3.connect(db)
    init_schema(conn)
    B, P, K = "TEB", "2026Q1", "consolidated"
    factor = U.scale_factor(U.resolve_unit(P))      # sweep-established `bin`
    assert factor == 1

    cols = ["bank_ticker", "period", "kind", "section", "period_type",
            "stage1_amount", "stage2_amount", "stage3_amount", "total_amount"]
    for section, s1, s2, s3, tot in [("loans_amounts", 1_000.0, 200.0, 50.0, 1_250.0),
                                     ("loans_ecl", 10.0, 20.0, 25.0, 55.0)]:
        row = U.scale_sequence("bank_audit_credit_quality", cols,
                               (B, P, K, section, "current", s1, s2, s3, tot), factor)
        conn.execute(
            f"INSERT INTO bank_audit_credit_quality ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})", row)
    conn.commit()
    conn.close()

    conn = sqlite3.connect(db)
    build_stages(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM bank_audit_stages WHERE bank_ticker=?",
                       (B,)).fetchone()
    assert row["stage1_amount"] == 1_000.0
    assert row["stage1_coverage"] == pytest.approx(10.0 / 1_000.0)
    conn.close()


# --- hand-transcribed sources: legacy default, post-horizon refusal ----------
#
# audit_overrides.json (457 entries) and manual_statements.json are typed by a
# person reading the PDF, so they carry the filing's own unit. Every entry so far
# predates the switch and is `bin`, which is why an absent unit may default — but
# only for those. The first Q2 transcription that omits the field would otherwise
# recreate the 1000x error exactly: the author reads a Milyon page, types 5,000,
# and a defaulted `bin` stores it a thousandfold small while every identity foots.

@pytest.mark.parametrize("period", ["2022Q1", "2024Q3", "2025Q4", "2026Q1"])
def test_a_legacy_manual_entry_may_omit_the_unit(period):
    assert U.resolve_manual_unit(period, None) == "bin"
    assert U.scale_factor(U.resolve_manual_unit(period, None)) == 1


@pytest.mark.parametrize("period", ["2026Q2", "2026Q3", "2027Q1"])
def test_a_post_horizon_manual_entry_must_declare_its_unit(period):
    with pytest.raises(ValueError, match="must declare its unit"):
        U.resolve_manual_unit(period, None)


def test_an_unrecognised_manual_unit_is_refused():
    with pytest.raises(ValueError, match="not"):
        U.resolve_manual_unit("2026Q2", "kurus")
    with pytest.raises(ValueError, match="not"):
        U.resolve_manual_unit("2024Q1", "dollars")


def test_an_explicit_milyon_manual_entry_scales_once():
    unit = U.resolve_manual_unit("2026Q2", "milyon")
    assert unit == "milyon"
    factor = U.scale_factor(unit)
    row = U.scale_mapping("bank_audit_balance_sheet",
                          {"amount_tl": 5_000.0, "item_order": 2}, factor)
    assert row["amount_tl"] == 5_000_000.0
    assert row["item_order"] == 2


def test_an_explicit_bin_manual_entry_is_canonical_and_unscaled():
    unit = U.resolve_manual_unit("2026Q2", "bin")
    assert U.scale_factor(unit) == 1
    row = U.scale_mapping("bank_audit_balance_sheet", {"amount_tl": 5_000.0}, 1)
    assert row["amount_tl"] == 5_000.0


def test_a_refused_manual_entry_leaves_the_database_untouched(tmp_path):
    """The refusal must come BEFORE any mutation, so a Q2 override missing its
    unit cannot half-apply."""
    db = tmp_path / "ovr.db"
    conn = sqlite3.connect(db)
    init_schema(conn)
    conn.execute(
        "INSERT INTO bank_audit_balance_sheet (bank_ticker, period, kind, "
        "statement, item_order, hierarchy, item_name, amount_tl) "
        "VALUES ('TEB','2026Q2','consolidated','assets',1,'I.','Nakit',42.0)")
    conn.commit()
    before = list(conn.execute("SELECT * FROM bank_audit_balance_sheet"))

    with pytest.raises(ValueError, match="must declare its unit"):
        U.scale_factor(U.resolve_manual_unit("2026Q2", None))   # raises here
        conn.execute("UPDATE bank_audit_balance_sheet SET amount_tl = ?", (99.0,))

    assert list(conn.execute("SELECT * FROM bank_audit_balance_sheet")) == before
    conn.close()


def test_every_existing_override_entry_is_legacy_and_needs_no_unit():
    """All 457 predate the switch, so today's file stays valid unchanged."""
    import json
    data = json.loads((REPO / "data" / "audit_overrides.json").read_text(encoding="utf-8"))
    entries = data.get("overrides", data)
    for o in entries:
        period = o.get("period")
        if not period:
            continue
        unit = U.resolve_manual_unit(period, o.get("unit"))
        assert unit in U.UNIT_SCALE
        if U.within_sweep(period):
            assert U.scale_factor(unit) == 1, f"{period} legacy entry would be scaled"


# --- integration: the WIRING, not the registry -------------------------------
#
# The tests above prove the classification. These prove each writer actually
# applies it: invoked as production invokes it, against a real schema, value read
# back. A writer that accepts the context and forgets to use it passes every unit
# test and fails here.

def _db(tmp_path, name="w.db"):
    conn = sqlite3.connect(tmp_path / name)
    init_schema(conn)
    return conn


def _milyon():
    return U.UnitContext(source_unit="milyon", factor=1_000)


def test_credit_quality_writer_scales(tmp_path):
    from src.audit_reports.credit_quality import CreditQualityReport, upsert
    conn = _db(tmp_path)
    rep = CreditQualityReport(pdf_path="x.pdf", rows=[])
    row = type("R", (), {"section": "loans_amounts", "period_type": "current",
                         "page": 5, "stage1": 1.0, "stage2": 2.0, "stage3": 3.0,
                         "total": 6.0, "heading": "h"})()
    rep.rows = [row]
    upsert(conn, "TEB", "2026Q2", "consolidated", rep, unit=_milyon())
    got = conn.execute("SELECT stage1_amount, total_amount, source_page "
                       "FROM bank_audit_credit_quality").fetchone()
    assert got == (1_000.0, 6_000.0, 5), "the page number must not be scaled"


def test_liquidity_writer_scales_nothing(tmp_path):
    from src.audit_reports.liquidity import LiquidityReport, upsert
    conn = _db(tmp_path)
    rep = LiquidityReport(pdf_path="x.pdf")
    rep.rows = [type("R", (), {"period_type": "current", "leverage_ratio": 8.0,
                               "lcr_total": 150.0, "lcr_fc": 200.0,
                               "nsfr": 130.0})()]
    rep.source_page = 9
    upsert(conn, "TEB", "2026Q2", "consolidated", rep, unit=_milyon())
    got = conn.execute("SELECT leverage_ratio, lcr_total, lcr_fc, nsfr "
                       "FROM bank_audit_liquidity").fetchone()
    assert got == (8.0, 150.0, 200.0, 130.0), "LCR/NSFR/leverage are ratios"


def test_oci_writer_scales(tmp_path):
    from src.audit_reports.oci import OCIReport, upsert
    conn = _db(tmp_path)
    rep = OCIReport(pdf_path="x.pdf", rows=[
        type("R", (), {"order": 1, "hierarchy": "I.", "name": "OCI",
                       "footnote": None, "cur_amount": 7.0})()])
    upsert(conn, "TEB", "2026Q2", "consolidated", rep, unit=_milyon())
    assert conn.execute("SELECT amount, item_order FROM bank_audit_oci").fetchone() \
        == (7_000.0, 1)


def test_a_writer_cannot_be_called_without_a_context():
    """No default anywhere. A caller that forgets fails loudly rather than
    silently storing a Milyon filing unscaled."""
    from src.audit_reports.oci import OCIReport, upsert
    with pytest.raises(TypeError, match="unit"):
        upsert(sqlite3.connect(":memory:"), "T", "2026Q2", "c",
               OCIReport(pdf_path="x.pdf", rows=[]))


def test_the_loader_scales_balance_sheet_pl_and_cash_flow(tmp_path):
    from src.audit_reports.extractor import BankReport, StatementRow
    from src.audit_reports.loader import upsert_report
    conn = _db(tmp_path)
    rep = BankReport(
        pdf_path="x.pdf",
        bs_assets=[StatementRow(order=1, hierarchy="I.", name="Nakit", footnote=None,
                                cur_tl=1.0, cur_fc=2.0, cur_total=3.0)],
        bs_liabilities=[], off_balance=[],
        profit_loss=[StatementRow(order=1, hierarchy="I.", name="Faiz",
                                  footnote=None, cur_amount=4.0)])
    rep.cash_flow = [StatementRow(order=1, hierarchy="A.", name="Akis",
                                  footnote=None, cur_amount=5.0)]
    # The sixth argument is the R2 KEY, exactly as sync_audit_reports passes it.
    upsert_report(conn, "TEB", "2026Q2", "consolidated", rep,
                  "teb/TEB_2026Q2_consolidated.pdf", unit=_milyon())
    assert conn.execute("SELECT amount_tl, amount_fc, amount_total, item_order "
                        "FROM bank_audit_balance_sheet").fetchone() == \
        (1_000.0, 2_000.0, 3_000.0, 1)
    assert conn.execute(
        "SELECT amount FROM bank_audit_profit_loss").fetchone()[0] == 4_000.0
    assert conn.execute(
        "SELECT amount FROM bank_audit_cash_flow").fetchone()[0] == 5_000.0


def test_the_loader_at_factor_one_stores_exactly_what_was_extracted(tmp_path):
    """The historical control: a pre-switch partition must not move."""
    from src.audit_reports.extractor import BankReport, StatementRow
    from src.audit_reports.loader import upsert_report
    conn = _db(tmp_path)
    rep = BankReport(
        pdf_path="x.pdf",
        bs_assets=[StatementRow(order=1, hierarchy="I.", name="Nakit", footnote=None,
                                cur_tl=1234.5, cur_fc=None, cur_total=1234.5)],
        bs_liabilities=[], off_balance=[], profit_loss=[])
    upsert_report(conn, "TEB", "2025Q4", "consolidated", rep, "k.pdf",
                  unit=U.UnitContext.for_partition("2025Q4", None))
    assert conn.execute("SELECT amount_tl, amount_fc FROM bank_audit_balance_sheet") \
        .fetchone() == (1234.5, None), "null stayed null; the figure did not move"


# --- the R2 key is not a path -------------------------------------------------

def test_the_stored_identifier_and_the_detector_path_are_distinct(tmp_path):
    """THE wiring trap. sync_audit_reports hands the writer the R2 KEY while the
    downloaded file has a different name in a temp dir; load_partition,
    reextract_pl and backfill_credit_quality delete theirs before writing."""
    key = "teb/TEB_2026Q2_consolidated.pdf"
    with pytest.raises(ValueError, match="not a readable file"):
        U.UnitContext.for_partition("2026Q2", key)

    local = tmp_path / "TEB_2026Q2_consolidated.pdf"
    local.write_bytes(b"not a pdf")
    assert key != str(local)
    assert Path(local).is_file() and "/" not in key.split("/")[-1]


def test_unknown_missing_and_key_all_refuse_leaving_rows_untouched(tmp_path):
    from src.audit_reports.extractor import BankReport, StatementRow
    from src.audit_reports.loader import upsert_report
    conn = _db(tmp_path)
    rep = BankReport(pdf_path="x.pdf",
                     bs_assets=[StatementRow(order=1, hierarchy="I.", name="N",
                                             footnote=None, cur_tl=1.0)],
                     bs_liabilities=[], off_balance=[], profit_loss=[])
    upsert_report(conn, "TEB", "2025Q4", "consolidated", rep, "k.pdf",
                  unit=U.UnitContext.canonical())
    before = list(conn.execute("SELECT * FROM bank_audit_balance_sheet"))

    for bad in (None, "/no/such/file.pdf", "teb/TEB_2026Q2_consolidated.pdf"):
        with pytest.raises(ValueError):
            U.UnitContext.for_partition("2026Q2", bad)
    assert list(conn.execute("SELECT * FROM bank_audit_balance_sheet")) == before


# --- apply_overrides: the REAL path, proving no mutation ----------------------

def _override_db(tmp_path):
    conn = sqlite3.connect(tmp_path / "ovr.db")
    init_schema(conn)
    conn.execute(
        "INSERT INTO bank_audit_balance_sheet (bank_ticker, period, kind, "
        "statement, item_order, hierarchy, item_name, amount_tl, amount_total) "
        "VALUES ('TEB','2026Q2','consolidated','assets',1,'I.','Nakit',42.0,42.0)")
    conn.commit()
    return conn


def test_a_post_horizon_override_without_a_unit_aborts_the_whole_run(tmp_path,
                                                                     monkeypatch):
    """Not a resolver call with an unreachable UPDATE after it — this drives the
    real main(), which resolves EVERY entry before pulling the snapshot or
    touching a row, so one undeclared Q2 entry aborts with nothing applied."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ao", REPO / "scripts" / "apply_overrides.py")
    ao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ao)

    conn = _override_db(tmp_path)
    before = list(conn.execute("SELECT * FROM bank_audit_balance_sheet"))
    conn.commit()
    conn.close()

    ovr = tmp_path / "ovr.json"
    ovr.write_text(json.dumps({"overrides": [
        {"bank_ticker": "TEB", "period": "2026Q2", "kind": "consolidated",
         "statement": "assets", "hierarchy": "I.", "item_name": "Nakit",
         "amount_tl": 5000, "amount_total": 5000, "note": "no unit declared"}]}),
        encoding="utf-8")
    monkeypatch.setattr(ao, "OVR", ovr)
    monkeypatch.setattr(ao, "DB", tmp_path / "ovr.db")
    pulled = []
    monkeypatch.setattr(ao.r2_storage, "download_to",
                        lambda *a, **k: pulled.append(a))
    monkeypatch.setattr(sys, "argv", ["apply_overrides.py", "--dry-run"])

    assert ao.main() == 2, "an undeclared post-horizon entry must abort"
    assert pulled == [], "it aborted before even pulling the snapshot"

    conn = sqlite3.connect(tmp_path / "ovr.db")
    assert list(conn.execute("SELECT * FROM bank_audit_balance_sheet")) == before
    conn.close()


def test_an_override_declaring_milyon_is_normalised_once(tmp_path):
    """apply_overrides is standalone — it writes rows itself — so the entry is
    converted from its declared unit to canonical bin before dispatch."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ao2", REPO / "scripts" / "apply_overrides.py")
    ao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ao)

    entry = {"bank_ticker": "TEB", "period": "2026Q2", "kind": "consolidated",
             "statement": "assets", "hierarchy": "I.", "item_name": "Nakit",
             "amount_tl": 5.0, "amount_total": 5.0, "unit": "milyon"}
    out = ao._normalise_override(entry, U.UnitContext.manual("2026Q2", "milyon"))
    assert out["amount_tl"] == 5_000.0 and out["amount_total"] == 5_000.0
    # and again at bin — unchanged
    same = ao._normalise_override(entry, U.UnitContext.manual("2026Q2", "bin"))
    assert same["amount_tl"] == 5.0


def test_an_override_scales_amounts_but_not_ratios_in_fields(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ao3", REPO / "scripts" / "apply_overrides.py")
    ao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ao)

    entry = {"bank_ticker": "TEB", "period": "2026Q2", "kind": "consolidated",
             "statement": "capital", "unit": "milyon",
             "fields": {"cet1_capital": 10.0, "cet1_ratio": 15.4}}
    out = ao._normalise_override(entry, U.UnitContext.manual("2026Q2", "milyon"))
    assert out["fields"]["cet1_capital"] == 10_000.0
    assert out["fields"]["cet1_ratio"] == 15.4, "a ratio was scaled"


def test_a_legacy_override_needs_no_unit_and_is_not_scaled(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ao4", REPO / "scripts" / "apply_overrides.py")
    ao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ao)

    entry = {"bank_ticker": "TEB", "period": "2025Q4", "kind": "consolidated",
             "statement": "assets", "amount_tl": 1234.5}
    ctx = U.UnitContext.manual("2025Q4", None)
    assert ctx.factor == 1
    assert ao._normalise_override(entry, ctx)["amount_tl"] == 1234.5


# --- every monetary writer, read back from a real database -------------------
#
# THE regression the TEB smoke test caught and the suite did not: four writers
# (capital, liquidity, fx_position, repricing) accepted `unit` and never called
# it — a scripted edit's anchor omitted the intervening `cur.executemany(` line,
# so the insertion silently no-opped. Signature present, scaling absent, every
# test green, and TEB's fx net position stored at -7,662 against a Q1 of
# -6,231,165.
#
# A source-string assertion ("does the module mention scale_rows") is weaker
# than it looks: it cannot tell a call that RUNS from one sitting behind a
# branch, and it passes a writer that scales the wrong columns. So each of the
# twelve now writes a Milyon figure into a real schema and has it read back —
# amounts x1000, ordinals/pages/ratios untouched.

def _wdb(tmp_path, name):
    conn = sqlite3.connect(tmp_path / f"{name}.db")
    init_schema(conn)
    return conn


def _milyon_ctx():
    return U.UnitContext(source_unit="milyon", factor=1_000)


def test_writer_balance_sheet_pl_and_cash_flow_read_back_scaled(tmp_path):
    from src.audit_reports.extractor import BankReport, StatementRow
    from src.audit_reports.loader import upsert_report
    conn = _wdb(tmp_path, "bs_pl_cf")
    rep = BankReport(
        pdf_path="x.pdf",
        bs_assets=[StatementRow(order=1, hierarchy="I.", name="Nakit", footnote=None,
                                cur_tl=1.0, cur_fc=2.0, cur_total=3.0)],
        bs_liabilities=[], off_balance=[],
        profit_loss=[StatementRow(order=1, hierarchy="I.", name="Faiz",
                                  footnote=None, cur_amount=4.0)])
    rep.cash_flow = [StatementRow(order=1, hierarchy="A.", name="Akis",
                                  footnote=None, cur_amount=5.0)]
    upsert_report(conn, "T", "2026Q2", "consolidated", rep, "k.pdf",
                  unit=_milyon_ctx())
    assert conn.execute(
        "SELECT amount_tl, amount_fc, amount_total, item_order "
        "FROM bank_audit_balance_sheet").fetchone() == (1_000.0, 2_000.0, 3_000.0, 1)
    assert conn.execute(
        "SELECT amount FROM bank_audit_profit_loss").fetchone()[0] == 4_000.0
    assert conn.execute(
        "SELECT amount FROM bank_audit_cash_flow").fetchone()[0] == 5_000.0


def test_writer_oci_reads_back_scaled(tmp_path):
    from src.audit_reports.extractor import StatementRow
    from src.audit_reports.oci import OCIReport, upsert
    conn = _wdb(tmp_path, "oci")
    upsert(conn, "T", "2026Q2", "consolidated",
           OCIReport(pdf_path="x.pdf",
                     rows=[StatementRow(order=1, hierarchy="I.", name="O",
                                        footnote=None, cur_amount=7.0)]),
           unit=_milyon_ctx())
    assert conn.execute(
        "SELECT amount, item_order FROM bank_audit_oci").fetchone() == (7_000.0, 1)


def test_writer_credit_quality_reads_back_scaled(tmp_path):
    from src.audit_reports.credit_quality import (CreditQualityReport, StageRow,
                                                  upsert)
    conn = _wdb(tmp_path, "cq")
    rep = CreditQualityReport(pdf_path="x.pdf", rows=[
        StageRow(section="loans_amounts", period_type="current", page=5,
                 stage1=1.0, stage2=2.0, stage3=None, total=6.0, heading="h")])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT stage1_amount, stage2_amount, stage3_amount, total_amount, "
        "source_page FROM bank_audit_credit_quality").fetchone() == \
        (1_000.0, 2_000.0, None, 6_000.0, 5), "null must stay null; page must not scale"


def test_writer_loans_by_sector_reads_back_scaled(tmp_path):
    from src.audit_reports.loans_by_sector import (LoansBySectorReport, SectorRow,
                                                   upsert)
    conn = _wdb(tmp_path, "lbs")
    rep = LoansBySectorReport(pdf_path="x.pdf", rows=[
        SectorRow(sector="agriculture", stage2_amount=2.0, stage3_amount=3.0,
                  ecl_amount=1.0, period_type="current", page=7, raw_label="Tarım")])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT stage2_amount, stage3_amount, ecl_amount, source_page, sector "
        "FROM bank_audit_loans_by_sector").fetchone() == \
        (2_000.0, 3_000.0, 1_000.0, 7, "agriculture")


def test_writer_npl_movement_reads_back_scaled(tmp_path):
    from src.audit_reports.npl_movement import NplGroupRow, NplMovementReport, upsert
    conn = _wdb(tmp_path, "npl")
    rep = NplMovementReport(pdf_path="x.pdf", rows=[
        NplGroupRow(group_code="III", period_type="current", opening_balance=10.0,
                    additions=1.0, collections=-2.0, closing_balance=9.0,
                    provision=4.0, net_balance=5.0, page=9)])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT opening_balance, additions, collections, closing_balance, "
        "provision, net_balance, transfers_in, source_page "
        "FROM bank_audit_npl_movement").fetchone() == \
        (10_000.0, 1_000.0, -2_000.0, 9_000.0, 4_000.0, 5_000.0, None, 9), \
        "a negative keeps its sign; an undisclosed leg stays null"


def test_writer_capital_scales_amounts_and_leaves_ratios(tmp_path):
    from src.audit_reports.capital_adequacy import CapitalReport, CapitalRow, upsert
    conn = _wdb(tmp_path, "cap")
    rep = CapitalReport(pdf_path="x.pdf", source_page=88, rows=[
        CapitalRow(period_type="current", cet1_capital=10.0, tier1_capital=12.0,
                   total_capital=15.0, total_rwa=100.0, cet1_ratio=10.0,
                   tier1_ratio=12.0, capital_adequacy_ratio=15.0)])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT cet1_capital, tier1_capital, total_capital, total_rwa, cet1_ratio, "
        "tier1_ratio, capital_adequacy_ratio, source_page "
        "FROM bank_audit_capital").fetchone() == \
        (10_000.0, 12_000.0, 15_000.0, 100_000.0, 10.0, 12.0, 15.0, 88), \
        "a scaled ratio would print a 15% CAR as 15,000%"


def test_writer_liquidity_scales_nothing_at_all(tmp_path):
    """The negative control: every column here is a ratio, so the writer takes a
    context and must leave all four values exactly as extracted."""
    from src.audit_reports.liquidity import LiquidityReport, LiquidityRow, upsert
    conn = _wdb(tmp_path, "liq")
    rep = LiquidityReport(pdf_path="x.pdf", source_page=9, rows=[
        LiquidityRow(period_type="current", leverage_ratio=8.0, lcr_total=150.0,
                     lcr_fc=200.0, nsfr=130.0)])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT leverage_ratio, lcr_total, lcr_fc, nsfr "
        "FROM bank_audit_liquidity").fetchone() == (8.0, 150.0, 200.0, 130.0)


def test_writer_fx_position_reads_back_scaled(tmp_path):
    """The one the TEB smoke test caught: signature present, scaling absent."""
    from src.audit_reports.fx_position import FxReport, FxRow, upsert
    conn = _wdb(tmp_path, "fx")
    rep = FxReport(pdf_path="x.pdf", source_page=44, rows=[
        FxRow(period_type="current", currency="TOTAL", on_bs_assets=10.0,
              on_bs_liab=12.0, net_on_balance=-2.0, net_off_balance=1.0,
              off_bs_receivable=3.0, off_bs_payable=2.0, net_position=-1.0)])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT on_bs_assets, on_bs_liab, net_on_balance, net_off_balance, "
        "off_bs_receivable, off_bs_payable, net_position, currency, source_page "
        "FROM bank_audit_fx_position").fetchone() == \
        (10_000.0, 12_000.0, -2_000.0, 1_000.0, 3_000.0, 2_000.0, -1_000.0,
         "TOTAL", 44)


def test_writer_repricing_reads_back_scaled(tmp_path):
    from src.audit_reports.repricing import RepricingReport, RepricingRow, upsert
    conn = _wdb(tmp_path, "rp")
    rep = RepricingReport(pdf_path="x.pdf", source_page=55, rows=[
        RepricingRow(period_type="current", bucket="lt_1m",
                     rate_sensitive_assets=10.0, rate_sensitive_liab=8.0,
                     gap=2.0, cumulative_gap=2.0)])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    assert conn.execute(
        "SELECT rate_sensitive_assets, rate_sensitive_liab, gap, cumulative_gap, "
        "bucket, source_page FROM bank_audit_repricing").fetchone() == \
        (10_000.0, 8_000.0, 2_000.0, 2_000.0, "lt_1m", 55)


def test_writer_equity_change_reads_back_scaled(tmp_path):
    from src.audit_reports.equity_change import EquityChangeReport, EquityChangeRow, upsert
    conn = _wdb(tmp_path, "eq")
    rep = EquityChangeReport(pdf_path="x.pdf", rows=[
        EquityChangeRow(order=1, hierarchy="I.", name="Baslangic",
                        period_type="current", source_page=3,
                        paid_in_capital=1.0, profit_reserves=2.0,
                        period_net_profit_loss=-3.0, total_equity=9.0,
                        total_equity_incl_minority=9.0)])
    upsert(conn, "T", "2026Q2", "consolidated", rep, unit=_milyon_ctx())
    conn.commit()
    assert conn.execute(
        "SELECT paid_in_capital, profit_reserves, period_net_profit_loss, "
        "total_equity, total_equity_incl_minority, minority_interest, item_order, "
        "source_page FROM bank_audit_equity_change").fetchone() == \
        (1_000.0, 2_000.0, -3_000.0, 9_000.0, 9_000.0, None, 1, 3), \
        "item_order is an ordinal and source_page a page — neither is money"


def test_writer_free_provision_reads_back_scaled(tmp_path):
    from src.audit_reports.free_provision import FreeProvision, upsert_free_provision
    conn = _wdb(tmp_path, "fp")
    upsert_free_provision(
        conn, "T", "2026Q2", "consolidated",
        FreeProvision(free_provision=5.0, free_provision_prior=4.0, disclosed=True,
                      source_page=61, snippet="serbest karsilik"),
        unit=_milyon_ctx())
    assert conn.execute(
        "SELECT free_provision, free_provision_prior, source_page "
        "FROM bank_audit_free_provision").fetchone() == (5_000.0, 4_000.0, 61)


# Declared coverage, cross-checked against the file itself below — a literal
# that can lie is worth nothing, and "declared covered, never exercised" is the
# same failure class as the four writers that no-opped.
_READ_BACK_COVERED = frozenset({
    "bank_audit_balance_sheet", "bank_audit_profit_loss", "bank_audit_cash_flow",
    "bank_audit_oci", "bank_audit_credit_quality", "bank_audit_loans_by_sector",
    "bank_audit_npl_movement", "bank_audit_capital", "bank_audit_fx_position",
    "bank_audit_repricing", "bank_audit_equity_change",
    "bank_audit_free_provision",
})


def test_every_raw_money_table_has_a_read_back_test():
    """Guards the guard. A thirteenth monetary table added to the registry with
    no behavioural test fails here rather than shipping unscaled."""
    missing = U.RAW_MONEY_TABLES - _READ_BACK_COVERED
    assert not missing, f"no read-back test for {sorted(missing)}"


def test_the_declared_coverage_is_not_a_lie():
    """Each declared table must actually appear inside a `test_writer_*`
    function in this file — so the set above cannot be padded to pass."""
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    exercised = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_writer_"):
            body = ast.dump(node)
            exercised |= {t for t in _READ_BACK_COVERED if repr(t)[1:-1] in body}
    assert _READ_BACK_COVERED <= exercised, (
        f"declared but never exercised: {sorted(_READ_BACK_COVERED - exercised)}")
