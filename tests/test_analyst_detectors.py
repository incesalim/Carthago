"""The analyst detectors, tested on synthetic fixtures over the REAL audit DDL.

Each test names the plan pass-criterion it pins (build plan Tasks 1.1–1.8).
The TEB 2026Q2 rows were purged from the snapshot, so the unit-switch cases
here reconstruct the documented pattern (₺799bn printed in thousands → ~₺841m
printed in millions) — this suite is what makes re-extracting 2026Q2 safe.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from src.analyst import classify_basis, periods
from src.analyst import detect_cross_period as xp
from src.analyst import detect_divergence as dv
from src.analyst import detect_opinion_change as oc
from src.analyst import detect_perimeter_change as pc
from src.analyst import detect_unit_change as uc
from src.analyst.extract_basis_metadata import build_rows, regex_unit
from src.analyst.schema import DDL as ANALYST_DDL
from src.audit_reports.schema import init_schema

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def bs_total(conn, bank, period, total, kind="unconsolidated"):
    for stmt in ("assets", "liabilities"):
        conn.execute(
            "INSERT INTO bank_audit_balance_sheet "
            "(bank_ticker, period, kind, statement, item_order, hierarchy, item_name, amount_total) "
            "VALUES (?,?,?,?,999,'','TOPLAM',?)", (bank, period, kind, stmt, total))


# ---------------------------------------------------------------- periods

def test_period_math():
    assert periods.prev_quarter("2026Q1") == "2025Q4"
    assert periods.prev_quarter("2025Q3") == "2025Q2"
    assert periods.prior_year_end("2026Q3") == "2025Q4"
    assert periods.prior_year_same_quarter("2026Q1") == "2025Q1"
    with pytest.raises(ValueError):
        periods.parse("2026-Q1")  # the hyphen form matches zero rows — reject loudly


# ------------------------------------------------------- 1.1 unit change

def test_unit_change_fires_on_teb_pattern(db):
    bs_total(db, "TEB", "2026Q1", 799_241_647)
    bs_total(db, "TEB", "2026Q2", 841_000)  # million-printed, read as thousands
    sigs = uc.detect(db)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.severity == "critical" and s.period == "2026Q2"
    assert 0.0009 < s.payload["ratio"] < 0.0012


def test_unit_change_silent_on_fast_growth(db):
    bs_total(db, "SKBNK", "2025Q1", 127_000_000)
    bs_total(db, "SKBNK", "2025Q2", 180_000_000)  # +42% in a quarter — loud but legal
    assert uc.detect(db) == []


def test_unit_change_skips_period_gap(db):
    bs_total(db, "NEWBANK", "2024Q4", 1_000_000)
    bs_total(db, "NEWBANK", "2025Q2", 500)  # adjacent quarter missing → no comparison
    assert uc.detect(db) == []


# ------------------------------------------------- 1.2 cross-period

def cap_row(conn, bank, period, ptype, car, cet1, total=None, rwa=None,
            kind="unconsolidated"):
    conn.execute(
        "INSERT INTO bank_audit_capital "
        "(bank_ticker, period, kind, period_type, cet1_capital, tier1_capital, "
        " tier2_capital, total_capital, total_rwa, cet1_ratio, tier1_ratio, "
        " capital_adequacy_ratio) VALUES (?,?,?,?,NULL,NULL,NULL,?,?,?,NULL,?)",
        (bank, period, kind, ptype, total, rwa, cet1, car))


def test_cross_period_fires_on_restated_prior(db):
    cap_row(db, "HALKB", "2025Q4", "current", car=15.0, cet1=10.0, total=100_000_000)
    cap_row(db, "HALKB", "2026Q1", "prior", car=15.0, cet1=10.0, total=93_000_000)  # −7%
    sigs = [s for s in xp.detect(db) if s.subtype == "capital.total_capital"]
    assert len(sigs) == 1
    assert sigs[0].payload["pct_diff"] == 7.0
    assert sigs[0].severity == "alert"


def test_cross_period_silent_within_tolerance(db):
    cap_row(db, "GARAN", "2025Q4", "current", car=18.76, cet1=14.08, total=591_808_970)
    cap_row(db, "GARAN", "2026Q1", "prior", car=18.76, cet1=14.08, total=591_808_971)
    assert [s for s in xp.detect(db) if s.subtype.startswith("capital.")] == []


def test_cross_period_unit_switch_is_critical(db):
    cap_row(db, "TEB", "2025Q4", "current", car=16.0, cet1=9.0, total=90_000_000)
    cap_row(db, "TEB", "2026Q2", "prior", car=16.0, cet1=9.0, total=90_000)  # 1000×
    sigs = [s for s in xp.detect(db) if s.subtype == "capital.total_capital"]
    assert sigs and sigs[0].severity == "critical"


def test_cross_period_null_is_not_zero(db):
    cap_row(db, "EXIM", "2025Q4", "current", car=20.0, cet1=20.0, total=None)
    cap_row(db, "EXIM", "2026Q1", "prior", car=20.0, cet1=20.0, total=50_000_000)
    assert [s for s in xp.detect(db) if s.subtype == "capital.total_capital"] == []


def test_cross_period_zero_prior_is_artifact_not_restatement(db):
    # SKBNK 2023–24: dash→0.0 priors in the capital lane. A bank cannot restate
    # total capital to literal zero — skip, don't report a fiction.
    cap_row(db, "SKBNK", "2022Q4", "current", car=20.0, cet1=15.0, total=6_847_692)
    cap_row(db, "SKBNK", "2023Q1", "prior", car=20.0, cet1=15.0, total=0.0)
    assert [s for s in xp.detect(db) if s.subtype == "capital.total_capital"] == []


def test_cross_period_flags_failing_lane_validation(db):
    for period, ptype, eq in (("2025Q1", "current", 100_000_000),
                              ("2026Q1", "prior", 90_000_000)):
        db.execute(
            "INSERT INTO bank_audit_equity_change (bank_ticker, period, kind, "
            "period_type, item_order, hierarchy, item_name, total_equity) "
            "VALUES ('TFKB',?, 'unconsolidated', ?, 17, '', 'Dönem Sonu', ?)",
            (period, ptype, eq))
    db.execute(
        "INSERT INTO bank_audit_validation (bank_ticker, period, kind, statement, "
        "checks_passed, checks_failed, checks_skipped) "
        "VALUES ('TFKB','2026Q1','unconsolidated','equity_change',3,2,0)")
    sigs = [s for s in xp.detect(db) if s.subtype.startswith("equity_change")]
    assert sigs and sigs[0].payload["lane_validation_failing"] is True


def test_cross_period_npl_opening_anchor(db):
    db.execute(
        "INSERT INTO bank_audit_npl_movement (bank_ticker, period, kind, group_code, "
        "period_type, opening_balance, closing_balance) "
        "VALUES ('GARAN','2025Q4','unconsolidated','V','current',13353487,27869236)")
    db.execute(
        "INSERT INTO bank_audit_npl_movement (bank_ticker, period, kind, group_code, "
        "period_type, opening_balance, closing_balance) "
        "VALUES ('GARAN','2026Q1','unconsolidated','V','current',26000000,34958841)")
    sigs = [s for s in xp.detect(db) if s.subtype == "npl_movement.opening_group_V"]
    assert len(sigs) == 1  # opening ≠ prior year-end closing → restated
    assert sigs[0].payload["reference_period"] == "2025Q4"


def test_cross_period_equity_same_quarter_anchor(db):
    for period, ptype, order, eq in (
        ("2025Q1", "current", 17, 255_334_649),
        ("2026Q1", "prior", 17, 255_334_649),   # ties out
        ("2026Q1", "current", 17, 451_315_838),
    ):
        db.execute(
            "INSERT INTO bank_audit_equity_change (bank_ticker, period, kind, "
            "period_type, item_order, hierarchy, item_name, total_equity) "
            "VALUES ('GARAN',?, 'unconsolidated', ?, ?, '', 'Dönem Sonu Bakiyesi', ?)",
            (period, ptype, order, eq))
    assert [s for s in xp.detect(db) if s.subtype.startswith("equity_change")] == []
    db.execute("UPDATE bank_audit_equity_change SET total_equity = 240000000 "
               "WHERE period = '2026Q1' AND period_type = 'prior'")
    sigs = [s for s in xp.detect(db) if s.subtype.startswith("equity_change")]
    assert len(sigs) == 1 and sigs[0].payload["reference_period"] == "2025Q1"


def test_known_restatements_marked_documented(db):
    cap_row(db, "ALBRK", "2022Q4", "current", car=20.0, cet1=15.0, total=10_000_000,
            kind="consolidated")
    cap_row(db, "ALBRK", "2023Q1", "prior", car=20.0, cet1=15.0, total=9_000_000,
            kind="consolidated")
    sigs = [s for s in xp.detect(db) if s.subtype == "capital.total_capital"]
    assert sigs and sigs[0].payload["documented"] is True


def test_restatement_mirror_matches_validator_skiplists():
    """KNOWN_RESTATEMENTS mirrors the three documented prior-column-divergence
    skip-lists in scripts/revalidate_audit_db.py (NOT _FX_SKIP, which is a
    completeness skip). Parse those blocks so drift fails a test, not a memo."""
    src = (REPO / "scripts" / "revalidate_audit_db.py").read_text(encoding="utf-8")
    found = set()
    for name in ("_FX_XPERIOD_SKIP", "_RP_SKIP", "_RP_PRIOR_SKIP"):
        m = re.search(rf"{name} = frozenset\(\{{(.*?)\}}\)", src, re.S)
        assert m, f"{name} not found — the validator skip-lists moved"
        for t in re.finditer(
                r'\(\s*"([A-Z]+)",\s*"(\d{4}Q[1-4])",\s*"(consolidated|unconsolidated)"\s*\)',
                m.group(1)):
            found.add((t.group(1), t.group(2), t.group(3)))
    assert found == set(xp.KNOWN_RESTATEMENTS), (
        f"mirror drift — missing: {found - set(xp.KNOWN_RESTATEMENTS)}, "
        f"stale: {set(xp.KNOWN_RESTATEMENTS) - found}")


# ------------------------------------------------- 1.3 opinion + classifier

def test_classifier_free_provision_en_tr():
    en = "a portion of the free provision amounting to TL 7,000,000 thousand is reversed"
    tr = "önceki dönemlerde ayrılan SERBEST KARŞILIĞIN 350.000 bin TL tutarındaki kısmı"
    assert classify_basis.classify(en).category == "free_provision"
    assert classify_basis.classify(tr).category == "free_provision"


def test_classifier_general_reserve_is_free_provision():
    t = ("As stated in Note 2.h.2.ii of Section Five, the accompanying interim "
         "financial information includes a general reserve of TL 1,816,973 thousands")
    assert classify_basis.classify(t).category == "free_provision"


def test_classifier_bond_reclassification():
    t = "the Bank reclassified government debt securities from fair value to amortised cost"
    assert classify_basis.classify(t).category == "bond_reclassification"


def test_classifier_other_tail():
    t = "the accompanying financial statements do not include the effects of inflation"
    assert classify_basis.classify(t).category == "other"


def test_classifier_reads_leading_portion_only():
    # A KAM over-run mentioning securities reclassification downstream must not
    # flip a free-provision qualification.
    t = ("includes a free provision of TL 1,000,000 thousand " + "x" * 900
         + " Key Audit Matters: reclassified securities portfolios")
    assert classify_basis.classify(t).category == "free_provision"


def op_row(conn, bank, period, otype, rkind, auditor, basis=None, kind="unconsolidated"):
    conn.execute(
        "INSERT INTO bank_audit_opinion (bank_ticker, period, kind, opinion_type, "
        "is_modified, report_kind, basis_text, auditor) VALUES (?,?,?,?,?,?,?,?)",
        (bank, period, kind, otype, 1 if otype != "clean" else 0, rkind, basis, auditor))


def test_opinion_steady_qualified_is_silent(db):
    fp = "includes a free provision of TL 7,300,000 thousand outside of the requirements"
    for p in ("2025Q1", "2025Q2", "2025Q3"):
        op_row(db, "ALBRK", p, "qualified", "review", "PwC", fp)
    op_row(db, "ALBRK", "2025Q4", "qualified", "audit", "PwC", fp)
    assert oc.detect(db) == []


def test_opinion_type_change_fires(db):
    op_row(db, "AKBNK", "2025Q4", "clean", "audit", "EY")
    op_row(db, "AKBNK", "2026Q1", "qualified", "review", "EY",
           "includes a free provision of TL 1,000,000 thousand")
    sigs = oc.detect(db)
    assert [s.subtype for s in sigs] == ["type"]
    assert sigs[0].payload["current_type"] == "qualified"


def test_opinion_category_change_fires(db):
    op_row(db, "VAKBN", "2025Q4", "qualified", "audit", "KPMG",
           "includes a free provision of TL 2,000,000 thousand")
    op_row(db, "VAKBN", "2026Q1", "qualified", "review", "KPMG",
           "the Bank reclassified securities from fair value to amortised cost")
    assert [s.subtype for s in oc.detect(db)] == ["category"]


def test_opinion_rhythm_and_auditor_changes(db):
    op_row(db, "ZIRAAT", "2025Q3", "clean", "audit", "KPMG")  # audit in Q3 → rhythm break
    op_row(db, "ZIRAAT", "2025Q4", "clean", "audit", "PwC")   # auditor rotation
    subs = sorted(s.subtype for s in oc.detect(db))
    assert subs == ["auditor", "report_kind"]


# ------------------------------------------------- 1.4 perimeter

def pl_role(conn, bank, period, role, amount, kind="consolidated"):
    conn.execute(
        "INSERT INTO bank_audit_profit_loss (bank_ticker, period, kind, item_order, "
        "hierarchy, item_name, amount) VALUES (?,?,?,1,'XX.','Durdurulan',?)",
        (bank, period, kind, amount))
    conn.execute(
        "INSERT INTO bank_audit_pl_roles (bank_ticker, period, kind, hierarchy, role) "
        "VALUES (?,?,?,'XX.',?)", (bank, period, kind, role))


def test_disc_net_appearing_fires(db):
    pl_role(db, "GARAN", "2025Q4", "disc_net", 0.0)
    pl_role(db, "GARAN", "2026Q1", "disc_net", 399_875.0)
    sigs = [s for s in pc.detect(db) if s.subtype == "discontinued_ops"]
    assert len(sigs) == 1 and sigs[0].payload["direction"] == "appeared"


def test_disc_net_floor_suppresses_rump_line(db):
    pl_role(db, "ALBRK", "2025Q4", "disc_net", -1.0)
    pl_role(db, "ALBRK", "2026Q1", "disc_net", -1_982.0)  # ₺2m — noise, not an event
    assert [s for s in pc.detect(db) if s.subtype == "discontinued_ops"] == []


def test_cons_gap_move_fires(db):
    bs_total(db, "DENIZ", "2025Q4", 100_000_000, kind="unconsolidated")
    bs_total(db, "DENIZ", "2025Q4", 105_000_000, kind="consolidated")   # gap 5%
    bs_total(db, "DENIZ", "2026Q1", 110_000_000, kind="unconsolidated")
    bs_total(db, "DENIZ", "2026Q1", 143_000_000, kind="consolidated")   # gap 30%
    sigs = [s for s in pc.detect(db) if s.subtype == "cons_gap"]
    assert len(sigs) == 1 and sigs[0].period == "2026Q1"


def test_role_set_change_fires(db):
    pl_role(db, "TSKB", "2025Q4", "period_net", 1000.0)
    pl_role(db, "TSKB", "2026Q1", "period_net", 1100.0)
    db.execute("INSERT INTO bank_audit_profit_loss (bank_ticker, period, kind, "
               "item_order, hierarchy, item_name, amount) "
               "VALUES ('TSKB','2026Q1','consolidated',2,'XI.','Yeni Kalem',5.0)")
    db.execute("INSERT INTO bank_audit_pl_roles (bank_ticker, period, kind, hierarchy, role) "
               "VALUES ('TSKB','2026Q1','consolidated','XI.','pretax')")
    sigs = [s for s in pc.detect(db) if s.subtype == "line_item_change"]
    assert len(sigs) == 1 and sigs[0].payload["roles_added"] == ["pretax"]


# ------------------------------------------------- 1.8 divergence

def stages_row(conn, bank, period, npl_pct, cov_pct, kind="unconsolidated"):
    total = 100_000_000.0
    s3 = total * npl_pct / 100.0
    conn.execute(
        "INSERT INTO bank_audit_stages (bank_ticker, period, kind, period_type, "
        "stage3_amount, total_amount, stage3_coverage) VALUES (?,?,?,'current',?,?,?)",
        (bank, period, kind, s3, total, cov_pct / 100.0))


def test_capital_composition_fires_on_skbnk_level(db):
    cap_row(db, "SKBNK", "2026Q1", "current", car=22.13, cet1=8.64)
    sigs = [s for s in dv.detect(db) if s.subtype == "capital_composition"]
    assert len(sigs) == 1
    assert sigs[0].payload["noncore_share"] == pytest.approx(0.61, abs=0.005)


def test_capital_composition_widening_signature(db):
    cap_row(db, "SKBNK", "2025Q2", "current", car=17.87, cet1=12.92)  # gap 4.95 — below level
    cap_row(db, "SKBNK", "2025Q3", "current", car=24.18, cet1=11.46)  # gap 12.72, CAR up
    sigs = [s for s in dv.detect(db)
            if s.subtype == "capital_composition" and s.period == "2025Q3"]
    assert sigs and sigs[0].payload["widening_hit"] is True


def test_capital_composition_silent_on_core_funded_bank(db):
    cap_row(db, "GARAN", "2026Q1", "current", car=18.76, cet1=14.08)  # 25% non-core
    assert [s for s in dv.detect(db) if s.subtype == "capital_composition"] == []


def test_npl_coverage_divergence_fires_on_skbnk_pattern(db):
    series = [("2025Q1", 1.45, 67.3), ("2025Q2", 1.34, 64.4), ("2025Q3", 1.30, 58.9),
              ("2025Q4", 1.29, 53.1), ("2026Q1", 1.33, 48.3)]
    for period, npl, cov in series:
        stages_row(db, "SKBNK", period, npl, cov)
    sigs = [s for s in dv.detect(db)
            if s.subtype == "npl_coverage" and s.period == "2026Q1"]
    assert len(sigs) == 1
    assert sigs[0].payload["coverage_drop_pp"] == pytest.approx(19.0, abs=0.1)
    assert sigs[0].severity == "alert"  # coverage collapsed below 60%


def test_npl_coverage_mild_dilution_is_silent(db):
    # A 6pp drift over four quarters is the sector's 2022–26 dilution cycle,
    # not a concealment signal.
    series = [("2025Q1", 2.00, 86.0), ("2025Q2", 1.95, 84.5), ("2025Q3", 1.92, 83.0),
              ("2025Q4", 1.90, 81.5), ("2026Q1", 1.95, 80.0)]
    for period, npl, cov in series:
        stages_row(db, "AKBNK", period, npl, cov)
    assert [s for s in dv.detect(db) if s.subtype == "npl_coverage"] == []


def test_npl_coverage_silent_when_npl_rising(db):
    series = [("2025Q1", 1.41, 85.7), ("2025Q2", 1.52, 85.9), ("2025Q3", 1.74, 83.0),
              ("2025Q4", 1.89, 80.7), ("2026Q1", 2.05, 76.1)]
    for period, npl, cov in series:
        stages_row(db, "ALBRK", period, npl, cov)  # deterioration is IN the headline
    assert [s for s in dv.detect(db) if s.subtype == "npl_coverage"] == []


# ------------------------------------------------- 1.5 basis metadata

def test_regex_unit_normalizes_both_languages():
    assert regex_unit(["(Bin Türk Lirası)"]) == "bin"
    assert regex_unit(["Amounts expressed in thousands of Turkish Lira"]) == "bin"
    assert regex_unit(["(Milyon Türk Lirası olarak ifade edilmiştir)"]) == "milyon"
    assert regex_unit(["no declaration here"]) is None


def test_basis_rows_sweep_horizon(db):
    db.execute("INSERT INTO bank_audit_extractions (bank_ticker, period, kind, pdf_path) "
               "VALUES ('GARAN','2026Q1','unconsolidated','x.pdf')")
    db.execute("INSERT INTO bank_audit_extractions (bank_ticker, period, kind, pdf_path) "
               "VALUES ('GARAN','2026Q2','unconsolidated','y.pdf')")
    op_row(db, "GARAN", "2026Q1", "clean", "review", "EY")
    rows = {r["period"]: r for r in build_rows(db)}
    assert rows["2026Q1"]["reporting_unit"] == "bin"
    assert rows["2026Q1"]["assurance_level"] == "review"
    assert rows["2026Q1"]["assurance_source"] == "opinion"
    # Past the sweep horizon: never a silent 'bin'.
    assert rows["2026Q2"]["reporting_unit"] is None
    assert rows["2026Q2"]["unit_source"] == "pending_regex"
    assert rows["2026Q2"]["assurance_source"] == "expected_rhythm"


# ------------------------------------------------- schema lockstep

def test_staging_schema_matches_migration():
    """src/analyst/schema.py and web/migrations/0037_analyst_signals.sql must
    declare the same tables and columns."""
    mig = (REPO / "web" / "migrations" / "0037_analyst_signals.sql").read_text(encoding="utf-8")

    def columns(sql: str, table: str) -> list[str]:
        m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\);", sql, re.S)
        assert m, f"{table} missing"
        cols = []
        for line in m.group(1).splitlines():
            line = line.split("--")[0].strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY", "FOREIGN")):
                continue
            cols.append(line.split()[0])
        return cols

    for table in ("analyst_signals", "analyst_notes", "analyst_basis_metadata"):
        assert columns(ANALYST_DDL, table) == columns(mig, table), table


def test_signal_id_carries_subtype():
    from src.analyst.signals import Signal
    a = Signal("cross_period_mismatch", "capital.total_capital", "X", "2026Q1",
               "unconsolidated", "alert", {})
    b = Signal("cross_period_mismatch", "fx_position.net_position", "X", "2026Q1",
               "unconsolidated", "alert", {})
    assert a.signal_id != b.signal_id
