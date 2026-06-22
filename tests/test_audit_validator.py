"""Unit tests for the structural (internal-sum) validator.

Pure-stdlib fixtures so this runs under CI's minimal dependency set — the
shapes mirror real corpus cases: ALBRK clean, the pre-fix corrupted ALBRK
rows (must FAIL), ING paren-negative storage (must PASS), dropped-child and
multi-period EXIM shapes.
"""
import sqlite3

from src.audit_reports import validator as v
from src.audit_reports.schema import init_schema


def _row(h, name, tl, fc, total, scale=1000):
    """Amounts ×1000 by default — corpus magnitudes are TL thousands, and the
    validator tolerances assume real-world scale."""
    return {"hierarchy": h, "item_name": name,
            "amount_tl": tl * scale, "amount_fc": fc * scale,
            "amount_total": total * scale}


def _clean_assets():
    """ALBRK-shaped minimal assets statement: contra child, two romans, total."""
    return [
        _row("I.", "FINANCIAL ASSETS (Net)", 60, 40, 100),
        _row("1.1", "Cash and Cash Equivalents", 36, 24, 60),
        _row("1.1.1", "Cash and Central Bank", 20, 20, 40),
        _row("1.1.2", "Banks", 18, 7, 25),
        _row("1.1.4", "Expected Credit Losses (-)", 2, 3, 5),
        _row("1.2", "Financial Assets at FVTPL", 24, 16, 40),
        _row("II.", "AMORTISED COST (Net)", 120, 80, 200),
        _row("2.1", "Loans", 130, 80, 210),
        _row("2.4", "Expected Credit Losses (-) (6)", 10, 0, 10),
        _row("", "TOTAL ASSETS", 180, 120, 300),
    ]


def test_clean_statement_all_pass():
    res = v.validate_statement(_clean_assets())
    assert res.failed == 0, res.failures
    # V1 on every full row, V2 on I./1.1/II., V3 once
    assert res.passed >= 10


def test_corrupted_ecl_fails_triplet_and_hierarchy():
    rows = _clean_assets()
    # The pre-fix ALBRK corruption: dipnot "(6)" stored as the value.
    rows[8] = _row("2.4", "ExpectedCreditLosses(", 2.4, 0, -6, scale=1)
    res = v.validate_statement(rows)
    checks = {f["check"] for f in res.failures}
    assert "row_triplet" in checks
    assert "hierarchy_sum" in checks  # II. != 2.1 - 2.4


def test_dropped_child_fails_parent_sum():
    rows = [r for r in _clean_assets() if r["item_name"] != "Expected Credit Losses (-) (6)"]
    res = v.validate_statement(rows)
    assert any(f["check"] == "hierarchy_sum" and "AMORTISED" in f["node"]
               for f in res.failures)


def test_paren_negative_storage_passes():
    """ING-style: contra value stored negative — contribution is -|x| either way."""
    rows = [
        _row("I.", "FINANSAL VARLIKLAR", 60, 40, 100),
        _row("1.1", "Nakit Değerler", 60, 40, 100),
        _row("II.", "İTFA EDİLMİŞ MALİYET", 100, 100, 200),
        _row("2.1", "Krediler", 110, 105, 215),
        _row("2.4", "Beklenen zarar karşılıkları (-) (I-5)", -10, -5, -15),
        _row("", "VARLIKLAR TOPLAMI", 160, 140, 300),
    ]
    res = v.validate_statement(rows)
    assert res.failed == 0, res.failures


def test_missing_children_skip_not_fail():
    rows = [
        _row("I.", "FINANCIAL ASSETS", 60, 40, 100),  # no children captured
        _row("", "TOTAL ASSETS", 60, 40, 100),
    ]
    res = v.validate_statement(rows)
    assert res.failed == 0


def test_statement_total_mismatch_fails():
    rows = [
        _row("I.", "FINANCIAL ASSETS", 60, 40, 100),
        _row("II.", "AMORTISED COST", 100, 100, 200),
        _row("", "TOTAL ASSETS", 200, 150, 350),  # romans sum to 300
    ]
    res = v.validate_statement(rows)
    assert any(f["check"] == "statement_total" for f in res.failures)


def test_cross_statement():
    a = [_row("", "TOTAL ASSETS", 60, 40, 100)]
    li_ok = [_row("", "TOTAL LIABILITIES AND EQUITY", 60, 40, 100)]
    li_bad = [_row("", "TOTAL LIABILITIES AND EQUITY", 60, 30, 90)]
    assert v.check_cross_statement(a, li_ok).failed == 0
    assert v.check_cross_statement(a, li_bad).failed == 1


def test_rounding_tolerance():
    rows = [
        _row("I.", "FINANCIAL ASSETS", 60, 40, 101, scale=1),   # ±1 rounding
        _row("1.1", "Cash", 36, 24, 61, scale=1),
        _row("1.2", "FVTPL", 24, 16, 41, scale=1),
    ]
    res = v.validate_statement(rows)
    assert all(f["check"] != "hierarchy_sum" for f in res.failures)


def test_upsert_validation_roundtrip():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    res = v.validate_statement(_clean_assets())
    v.upsert_validation(conn, "X", "2025Q4", "unconsolidated",
                        {"assets": res, "cross": v.ValidationResult()})
    got = conn.execute(
        "SELECT statement, checks_passed, checks_failed FROM bank_audit_validation "
        "WHERE bank_ticker='X' ORDER BY statement").fetchall()
    assert ("assets", res.passed, 0) in got
    # idempotent replace
    v.upsert_validation(conn, "X", "2025Q4", "unconsolidated", {"assets": res})
    n = conn.execute("SELECT COUNT(*) FROM bank_audit_validation").fetchone()[0]
    assert n == 1


# --- P&L (income statement) validation ------------------------------------

def _pl(h, name, amount, scale=1000):
    """Single-column income-statement row (amount ×1000 for corpus scale)."""
    return {"hierarchy": h, "item_name": name, "amount": amount * scale}


def _clean_pl():
    """Minimal BDDK income statement satisfying the full roman chain:
    I=200, II=50 → III=150; +IV..VII(65) → VIII=215; −IX..XII(55) → XIII=160;
    +XIV..XVI(0) → XVII=160; +XVIII(tax −30) → XIX=130; +XXIV(0) → XXV=130."""
    return [
        _pl("I.", "FAİZ GELİRLERİ", 200),
        _pl("II.", "FAİZ GİDERLERİ (-)", 50),
        _pl("III.", "NET FAİZ GELİRİ", 150),
        _pl("IV.", "NET ÜCRET VE KOMİSYON GELİRLERİ", 10),
        _pl("V.", "TEMETTÜ GELİRLERİ", 20),
        _pl("VI.", "TİCARİ KÂR/ZARAR (Net)", 30),
        _pl("VII.", "DİĞER FAALİYET GELİRLERİ", 5),
        _pl("VIII.", "FAALİYET GELİRLERİ TOPLAMI", 215),
        _pl("IX.", "BEKLENEN ZARAR KARŞILIKLARI (-)", 40),
        _pl("X.", "DİĞER KARŞILIKLAR (-)", 10),
        _pl("XI.", "PERSONEL GİDERLERİ (-)", 5),
        _pl("XII.", "DİĞER FAALİYET GİDERLERİ (-)", 0),
        _pl("XIII.", "NET FAALİYET KÂRI/ZARARI", 160),
        _pl("XIV.", "BİRLEŞME İŞLEMİ SONRASI GELİR", 0),
        _pl("XV.", "ÖZKAYNAK YÖNTEMİ UYGULANAN ORTAKLIK", 0),
        _pl("XVI.", "NET PARASAL POZİSYON KÂRI/ZARARI", 0),
        _pl("XVII.", "VERGİ ÖNCESİ KÂR/ZARAR", 160),
        _pl("XVIII.", "VERGİ KARŞILIĞI (±)", 30),   # positive magnitude (tax expense)
        _pl("XIX.", "SÜRDÜRÜLEN FAALİYETLER DÖNEM NET K/Z", 130),
        _pl("XXIV.", "DURDURULAN FAALİYETLER DÖNEM NET K/Z", 0),
        _pl("XXV.", "DÖNEM NET KÂR/ZARARI", 130),
    ]


def test_clean_pl_chain_passes():
    res = v.check_pl_chain(_clean_pl())
    assert res.failed == 0, res.failures
    assert res.passed == 6  # all six roman identities run and foot


def test_pl_full_passes_with_bottomline():
    li = [_row("16.6.2", "Net Dönem Kârı/Zararı", 70, 60, 130)]
    res = v.check_profit_loss(_clean_pl(), li)
    assert res.failed == 0, res.failures
    assert res.passed == 7  # 6 chain + 1 bottom-line


def test_pl_broken_subtotal_fails():
    rows = _clean_pl()
    for r in rows:  # corrupt VIII — a dropped or mis-summed operating-income line
        if r["hierarchy"] == "VIII.":
            r["amount"] = 999 * 1000
    res = v.check_pl_chain(rows)
    assert any(f["check"] == "pl_chain" and "8" in f["node"] for f in res.failures)


def test_pl_bottomline_mismatch_fails():
    li = [_row("16.6.2", "Net Dönem Kârı/Zararı", 50, 40, 90)]  # BS equity ≠ P&L net 130
    res = v.check_pl_bottomline(_clean_pl(), li)
    assert res.failed == 1


def test_pl_participation_equity_numeral():
    """Participation banks carry equity at XIV. → net profit row 14.6.2."""
    li = [_row("14.6.2", "Net Dönem Kârı/Zararı", 70, 60, 130)]
    res = v.check_pl_bottomline(_clean_pl(), li)
    assert res.failed == 0


def test_pl_paren_negative_deduction_storage_passes():
    """ING/KLNMA-style: a deduction roman stored as a parenthesised NEGATIVE.
    −abs lands on the same contribution as the positive-magnitude convention."""
    rows = _clean_pl()
    for r in rows:  # store interest expense (II) and ECL (IX) as negatives
        if r["hierarchy"] in ("II.", "IX.", "X.", "XI.", "XII."):
            r["amount"] = -abs(r["amount"])
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures


def test_pl_tax_benefit_direction_passes():
    """A net tax BENEFIT (XIX > XVII) — the ± tax step accepts either side."""
    rows = _clean_pl()
    for r in rows:
        if r["hierarchy"] == "XIX.":
            r["amount"] = 190 * 1000   # 160 pre-tax + 30 benefit
    res = v.check_pl_chain(rows)
    assert all(f["node"] != "roman 19 identity" for f in res.failures), res.failures


def test_pl_numeric_artifact_does_not_shadow_roman():
    """A junk numeric "1" row (a captured "1 OCAK…" period-header fragment) must
    NOT shadow roman I — collection is restricted to roman-form hierarchies."""
    rows = [{"hierarchy": "1", "item_name": "OCAK", "amount": 0.0}] + _clean_pl()
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures


def test_pl_roman_title_row_does_not_shadow_subtotal():
    """A roman-form TITLE row ('III. STATEMENT OF PROFIT OR LOSS', stray note
    number as amount) above the body must not shadow the real III — the spine
    keeps the longest in-sequence run."""
    rows = [{"hierarchy": "III.", "item_name": "STATEMENT OF PROFIT OR LOSS", "amount": 202.0}] + _clean_pl()
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures


def test_pl_mixed_convention_passes():
    """TFKB-style: interest expense II stored as a positive magnitude, but the
    IX–XII expense block stored parenthesised-NEGATIVE in the same statement.
    Accept-either foots both the II identity and the XIII identity."""
    rows = _clean_pl()
    for r in rows:
        if r["hierarchy"] in ("IX.", "X.", "XI.", "XII."):
            r["amount"] = -abs(r["amount"])   # paren-negative block; II stays positive
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures


def test_pl_incomplete_chain_skips_not_fails():
    """A P&L missing optional source romans skips the affected identity rather
    than false-failing (VIII loses its IV–VII sources)."""
    rows = [r for r in _clean_pl() if r["hierarchy"] not in ("IV.", "V.", "VI.", "VII.")]
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures
    assert res.skipped >= 1


def test_structure_check_reads_validation_table():
    import check_audit_quality as q
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    bad = v.ValidationResult()
    bad.add_fail("hierarchy_sum", "II. AMORTISED", 200, 194)
    v.upsert_validation(conn, "Y", "2026Q1", "unconsolidated", {"assets": bad})
    issues = q._structure(conn)
    assert len(issues) == 1 and "Y 2026Q1" in issues[0]
    # absent table degrades gracefully
    assert q._structure(sqlite3.connect(":memory:")) == []


# --- OCI (Other Comprehensive Income) validation --------------------------

def _oci_row(h, name, amount, scale=1000):
    return {"hierarchy": h, "item_name": name, "amount": amount * scale}


def _clean_oci():
    """Minimal valid OCI statement: I.=P&L net, II.=OCI total, III.=I+II."""
    return [
        _oci_row("I.",   "Dönem Kârı/Zararı",               130),
        _oci_row("II.",  "Diğer Kapsamlı Gelir/Gider",       -20),
        _oci_row("2.1.", "Kâr veya Zarara Sınıflandırılmayan", -15),
        _oci_row("2.1.1.", "Aktüeryal Kazanç/Kayıplar",      -15),
        _oci_row("2.2.", "Kâr veya Zarara Sınıflandırılan",   -5),
        _oci_row("2.2.1.", "Kur Çevrim Farkları",             -5),
        _oci_row("III.", "TOPLAM KAPSAMLI GELİR/GİDER",       110),
    ]


def test_oci_clean_passes():
    pl = _clean_pl()
    res = v.check_oci(_clean_oci(), pl)
    assert res.failed == 0, res.failures
    assert res.passed >= 3  # hierarchy sums + chain + cross-check


def test_oci_chain_broken_fails():
    oci = _clean_oci()
    for r in oci:
        if r["hierarchy"] == "III.":
            r["amount"] = 999 * 1000  # wrong total
    res = v.check_oci(oci)
    assert any(f["check"] == "oci_chain" for f in res.failures)


def test_oci_cross_check_mismatch_fails():
    """OCI.I ≠ P&L XXV → fail oci_cross."""
    oci = _clean_oci()
    for r in oci:
        if r["hierarchy"] == "I.":
            r["amount"] = 999 * 1000  # mismatch P&L net
    pl = _clean_pl()
    res = v.check_oci(oci, pl)
    assert any(f["check"] == "oci_cross" for f in res.failures)


def test_oci_empty_skips():
    res = v.check_oci([])
    assert res.failed == 0 and res.skipped >= 1


# --- Capital adequacy validation ------------------------------------------

def _cap_row(**kw):
    defaults = {
        "period_type": "current",
        "cet1_capital": 80_000, "tier1_capital": 100_000,
        "total_capital": 120_000, "total_rwa": 750_000,
        "capital_adequacy_ratio": 16.0,
    }
    defaults.update(kw)
    return defaults


def test_capital_clean_passes():
    res = v.check_capital([_cap_row()])
    assert res.failed == 0, res.failures


def test_capital_cet1_exceeds_tier1_fails():
    # CET1 alone > Tier1 is impossible (CET1 is part of Tier1) → composition fail
    # even with AT1 unknown.
    res = v.check_capital([_cap_row(cet1_capital=120_000, tier1_capital=100_000)])
    assert any(f["check"] == "cap_composition" for f in res.failures)


def test_capital_car_mismatch_fails():
    # Total 120k / RWA 750k * 100 = 16.0%, but we report 20.0%
    res = v.check_capital([_cap_row(capital_adequacy_ratio=20.0)])
    assert any(f["check"] == "cap_ratio_reconcile" for f in res.failures)


def test_capital_total_not_tier1_plus_tier2_fails():
    # Tier1 100k + Tier2 50k = 150k, but Total says 120k → composition fail
    res = v.check_capital([_cap_row(tier2_capital=50_000, total_capital=120_000,
                                    capital_adequacy_ratio=16.0)])
    assert any(f["check"] == "cap_composition" for f in res.failures)


def test_capital_subratio_reconcile_fails():
    # tier1_ratio reported 20% but Tier1 100k / RWA 750k = 13.3% → reconcile fail
    res = v.check_capital([_cap_row(tier1_ratio=20.0)])
    assert any(f["check"] == "cap_ratio_reconcile" for f in res.failures)


def test_capital_no_current_row_skips():
    res = v.check_capital([_cap_row(period_type="prior")])
    assert res.passed == 0 and res.failed == 0


# --- Liquidity validation -------------------------------------------------

def _liq_row(**kw):
    defaults = {"period_type": "current",
                "leverage_ratio": 8.5, "lcr_total": 145.0, "nsfr": 112.0}
    defaults.update(kw)
    return defaults


def test_liquidity_clean_passes():
    res = v.check_liquidity([_liq_row()])
    assert res.failed == 0, res.failures


def test_liquidity_leverage_out_of_band_fails():
    res = v.check_liquidity([_liq_row(leverage_ratio=35.0)])
    assert any(f["check"] == "liq_leverage_band" for f in res.failures)


def test_liquidity_lcr_implausibly_low_fails():
    res = v.check_liquidity([_liq_row(lcr_total=30.0)])
    assert any(f["check"] == "liq_ratio_low" for f in res.failures)


# --- Credit quality validation --------------------------------------------

def _cq_row(section, s1, s2, s3, tot, period_type="current"):
    return {"section": section, "period_type": period_type,
            "stage1_amount": s1 * 1000, "stage2_amount": s2 * 1000,
            "stage3_amount": s3 * 1000, "total_amount": tot * 1000}


def test_credit_quality_section_total_passes():
    rows = [_cq_row("loans_ecl", 100, 50, 30, 180)]
    res = v.check_credit_quality(rows)
    assert res.failed == 0, res.failures


def test_credit_quality_section_total_fails():
    rows = [_cq_row("loans_ecl", 100, 50, 30, 250)]  # total wrong
    res = v.check_credit_quality(rows)
    assert any(f["check"] == "cq_section_total" for f in res.failures)


def test_credit_quality_npl_net_rows_dont_fail():
    # cq_npl_net check removed: BRSA provision rows include general/collective reserves
    # so the identity gross-prov=net is unreliable across bank presentation formats.
    # Section total checks (S1+S2+S3=total) still run for each section.
    rows = [
        _cq_row("npl_brsa_gross",     150, 200, 150, 500),
        _cq_row("npl_brsa_provision", 40,  100,  60, 200),
        _cq_row("npl_brsa_net",       110, 100,  90, 200),  # totals match S1+S2+S3; net≠gross-prov but no check
    ]
    res = v.check_credit_quality(rows)
    assert not any(f.get("check") == "cq_npl_net" for f in res.failures)


def test_npl_brsa_sections_flagged_as_group_basis():
    # The stage1/2/3 columns mean BRSA groups III/IV/V (NOT IFRS stages) only for
    # the npl_brsa_* sections; everything else is a real IFRS stage.
    import pytest
    # credit_quality is fitz-only AND pulls in extractor (pdfplumber at module top);
    # CI's minimal deps have neither, so skip there (runs locally / full-deps env).
    pytest.importorskip("pdfplumber")
    pytest.importorskip("fitz")
    from src.audit_reports.credit_quality import stage_columns_are_brsa_groups
    assert stage_columns_are_brsa_groups("npl_brsa_gross")
    assert stage_columns_are_brsa_groups("npl_brsa_provision")
    assert not stage_columns_are_brsa_groups("loans_ecl")
    assert not stage_columns_are_brsa_groups("loans_by_stage")
    assert not stage_columns_are_brsa_groups("loans_amounts")


def test_build_stages_maps_npl_group_total_to_stage3_not_group_iii():
    """Lock the convention that the derived Stage-3 amount comes from the
    npl_brsa_gross TOTAL (III+IV+V), never from its stage1_amount (Group III).
    Guards against anyone re-reading npl_brsa.stage1 as IFRS Stage 1."""
    from scripts.build_bank_audit_stages import _SQL_AGG
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    # Distinct values so a Group-III-as-Stage-3 mistake can't coincidentally pass.
    conn.executemany(
        "INSERT INTO bank_audit_credit_quality "
        "(bank_ticker,period,kind,section,period_type,stage1_amount,stage2_amount,stage3_amount,total_amount) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("X", "2025Q1", "unconsolidated", "loans_by_stage", "current", 1000, 200, None, 1200),
            # npl_brsa_gross: stage1=Group III=30, IV=20, V=10, TOTAL=60
            ("X", "2025Q1", "unconsolidated", "npl_brsa_gross", "current", 30, 20, 10, 60),
        ],
    )
    conn.commit()
    row = conn.execute(_SQL_AGG).fetchone()
    # columns: bank,period,kind,period_type, s1_amt, s2_amt, s3_amt, s1_ecl, s2_ecl, s3_ecl
    s1_amt, s2_amt, s3_amt = row[4], row[5], row[6]
    assert s1_amt == 1000          # IFRS Stage 1 from loans_by_stage, not an NPL group
    assert s2_amt == 200
    assert s3_amt == 60            # NPL total (III+IV+V) — NOT Group III (30)
    assert s3_amt != 30, "Stage-3 must be the npl_brsa TOTAL, never Group III"


# --- Stages validation ----------------------------------------------------

def _stage_row(**kw):
    defaults = {
        "period_type": "current",
        "stage1_amount": 500_000, "stage2_amount": 100_000,
        "stage3_amount":  50_000, "total_amount":  650_000,
        "stage1_ecl": 4_000, "stage2_ecl": 8_000, "stage3_ecl": 40_000,
        "total_ecl": 52_000,
        "stage1_coverage": 0.008, "stage2_coverage": 0.08,
        "stage3_coverage": 0.80,
    }
    defaults.update(kw)
    return defaults


def test_stages_clean_passes():
    res = v.check_stages([_stage_row()])
    assert res.failed == 0, res.failures


def test_stages_total_amount_fails():
    res = v.check_stages([_stage_row(total_amount=999_000)])
    assert any(f["check"] == "stages_total_amount" for f in res.failures)


def test_stages_coverage_out_of_range_fails():
    res = v.check_stages([_stage_row(stage3_coverage=1.42)])
    assert any(f["check"] == "stages_coverage" for f in res.failures)


def test_stages_npl100_fingerprint_fails():
    """stage3 == total (S1+S2≈0) is the broken-extraction fingerprint."""
    res = v.check_stages([_stage_row(
        stage1_amount=0, stage2_amount=0,
        stage3_amount=650_000, total_amount=650_000,
    )])
    assert any(f["check"] == "stages_npl100" for f in res.failures)


def test_stages_dropped_stage3_fails():
    """S1/S2 captured but S3 NULL (total == S1+S2) = silently-dropped NPL column.
    Must FAIL, not skip — this is the blind spot that hid EMLAK's missing NPL for
    10 quarters while the cell read 'ok'."""
    res = v.check_stages([_stage_row(
        stage1_amount=500_000, stage2_amount=100_000,
        stage3_amount=None, total_amount=600_000,
        stage3_ecl=None, total_ecl=None, stage3_coverage=None,
    )])
    assert any(f["check"] == "stages_stage3_missing" for f in res.failures)


def test_stages_genuine_zero_npl_passes():
    """A real zero-NPL bank stores S3 = 0 (not NULL) — must NOT trip the
    dropped-column check (0 is captured data, NULL is a missing column)."""
    res = v.check_stages([_stage_row(
        stage3_amount=0, total_amount=600_000, stage3_ecl=0, stage3_coverage=0.0,
    )])
    assert not any(f["check"] == "stages_stage3_missing" for f in res.failures)


def test_stages_npl100_fingerprint_fires_on_null_stages():
    """The REAL broken shape has stage1/stage2 absent (loans_by_stage missing),
    not zero — the fingerprint must still fire (NULL counts as 0)."""
    res = v.check_stages([_stage_row(
        stage1_amount=None, stage2_amount=None,
        stage3_amount=650_000, total_amount=650_000,
    )])
    assert any(f["check"] == "stages_npl100" for f in res.failures)


# --- NPL movement validation ----------------------------------------------

def _npl_row(**kw):
    defaults = {
        "group_code": "III", "period_type": "current",
        "opening_balance": 100_000, "additions": 30_000,
        "transfers_in": 0, "transfers_out": 0,
        "collections": 10_000, "write_offs": 5_000,
        "sold": 0, "fx_diff": 0,
        "closing_balance": 115_000,  # 100+30-10-5 = 115
    }
    defaults.update(kw)
    return defaults


def test_npl_movement_clean_passes():
    res = v.check_npl_movement([_npl_row()])
    assert res.failed == 0, res.failures


def test_npl_movement_broken_fails():
    res = v.check_npl_movement([_npl_row(closing_balance=200_000)])
    assert any(f["check"] == "npl_movement" for f in res.failures)


def test_npl_movement_null_col_that_ties_passes():
    # A flow column absent from the disclosure (NULL) that is genuinely 0 — the
    # roll-forward ties with it as 0 → PASS (the bank simply omitted a zero row),
    # not a false skip. closing 120 = 100 + 30 - 10 - 0(write_offs).
    res = v.check_npl_movement([_npl_row(write_offs=None, closing_balance=120_000)])
    assert res.passed == 1 and res.failed == 0 and res.skipped == 0, res.failures


def test_npl_movement_null_col_that_breaks_tie_skips():
    # NULL flow column where treating it as 0 does NOT tie → could be a genuinely
    # non-zero value the extractor missed → SKIP, never a false fail.
    # (base ties only with write_offs=5000; nulling it leaves implied 120 ≠ 115.)
    res = v.check_npl_movement([_npl_row(write_offs=None)])
    assert res.failed == 0 and res.skipped == 1, res.failures


# --- Loans by sector validation -------------------------------------------

def _sector_row(sector, s2, s3, ecl, period_type="current"):
    return {"sector": sector, "period_type": period_type,
            "stage2_amount": s2 * 1000, "stage3_amount": s3 * 1000,
            "ecl_amount": ecl * 1000}


def test_loans_by_sector_passes():
    rows = [
        _sector_row("agri_total", 10, 5, 3),
        _sector_row("mfg_total", 20, 10, 6),
        _sector_row("construction", 5, 3, 2),
        _sector_row("svc_total", 30, 15, 9),
        _sector_row("other", 5, 2, 1),
        _sector_row("total", 70, 35, 21),
    ]
    res = v.check_loans_by_sector(rows)
    assert res.failed == 0, res.failures


def test_loans_by_sector_fails():
    rows = [
        _sector_row("agri_total", 10, 5, 3),
        _sector_row("mfg_total", 20, 10, 6),
        _sector_row("construction", 5, 3, 2),
        _sector_row("svc_total", 30, 15, 9),
        _sector_row("other", 5, 2, 1),
        _sector_row("total", 999, 999, 999),  # wrong totals
    ]
    res = v.check_loans_by_sector(rows)
    assert res.failed > 0


def test_loans_by_sector_fallback_to_subs():
    # agri_total absent — should sum agri_farming + agri_fishery instead
    rows = [
        _sector_row("agri_farming",  6, 3, 1),
        _sector_row("agri_fishery",  4, 2, 1),
        _sector_row("mfg_total",    20, 10, 6),
        _sector_row("construction",  5,  3, 2),
        _sector_row("svc_total",    30, 15, 9),
        _sector_row("other",         5,  2, 1),
        _sector_row("total",        70, 35, 20),
    ]
    res = v.check_loans_by_sector(rows)
    assert res.failed == 0, res.failures


# --- Cash flow validation -------------------------------------------------

def _cf_row(h, name, amount, scale=1000):
    return {"hierarchy": h, "item_name": name, "amount": amount * scale}


def _clean_cf():
    """Minimal cash flow satisfying the roman chain V=I+II+III+IV, VII=V+VI.
    I=100 (ops), II=−30 (inv), III=20 (fin), IV=−5 (FX) → V=85; VI=15 (opening) → VII=100."""
    return [
        _cf_row("A.", "NAKİT AKIŞLARI (İŞLETME)", 0),
        _cf_row("1.1", "Faiz Gelirleri", 200),
        _cf_row("1.2", "Faiz Giderleri", -100),
        _cf_row("I.", "İŞLETME FAALİYETLERİNDEN SAĞLANAN NET NAKİT", 100),
        _cf_row("B.", "YATIRIM FAALİYETLERİ", 0),
        _cf_row("2.1", "Satın Alınan Menkul Kıymetler", -30),
        _cf_row("II.", "YATIRIM FAALİYETLERİNDEN KULLANILAN NAKİT", -30),
        _cf_row("C.", "FİNANSMAN FAALİYETLERİ", 0),
        _cf_row("3.1", "İhraç Edilen Borçlanma Araçları", 20),
        _cf_row("III.", "FİNANSMAN FAALİYETLERİNDEN SAĞLANAN NAKİT", 20),
        _cf_row("IV.", "KUR FARKLARININ NAKİT VE NAKİT BENZERLERİNE ETKİSİ", -5),
        _cf_row("V.", "NAKİT VE NAKİT BENZERLERİNDEKİ NET ARTIS/AZALIS", 85),
        _cf_row("VI.", "DÖNEM BAŞI NAKİT VE NAKİT BENZERLERİ", 15),
        _cf_row("VII.", "DÖNEM SONU NAKİT VE NAKİT BENZERLERİ", 100),
    ]


def test_cf_clean_passes():
    res = v.check_cash_flow(_clean_cf())
    assert res.failed == 0, res.failures
    assert res.passed >= 2  # two roman chain checks pass


def test_cf_chain_v_broken_fails():
    rows = _clean_cf()
    for r in rows:
        if r["hierarchy"] == "V.":
            r["amount"] = 999 * 1000
    res = v.check_cash_flow(rows)
    assert any(f["check"] == "cf_chain" for f in res.failures)


def test_cf_missing_roman_skips():
    rows = [r for r in _clean_cf() if r["hierarchy"] not in ("III.", "IV.")]
    res = v.check_cash_flow(rows)
    assert res.failed == 0 and res.skipped >= 1


def test_cf_empty_skips():
    res = v.check_cash_flow([])
    assert res.failed == 0 and res.skipped >= 1


# --- Statement of changes in equity validation ----------------------------

def _eq_row(h, name, components, total, period_type="current"):
    """14-col equity row: 13 components + total_equity (no minority cols)."""
    assert len(components) == 13, f"expected 13 components, got {len(components)}"
    fields = [
        "paid_in_capital", "share_premium", "share_cancellation_profits",
        "other_capital_reserves",
        "oci_not_reclassified_1", "oci_not_reclassified_2", "oci_not_reclassified_3",
        "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
        "profit_reserves", "prior_period_profit_loss", "period_net_profit_loss",
    ]
    row = {"hierarchy": h, "item_name": name, "period_type": period_type,
           "total_equity": total * 1000,
           "minority_interest": None, "total_equity_incl_minority": None}
    for f, v_val in zip(fields, components):
        row[f] = v_val * 1000
    return row


def _clean_equity_current():
    """Minimal equity-change for current period (14-col, Q4).
    I. Opening 100; II. period changes 0; III=I+II=100; IV. comprehensive income 20;
    VI. dividends -10; closing = III+IV+VI = 110.
    Row IV is the comprehensive income → OCI cross-check: IV.total == OCI.III.
    """
    return [
        _eq_row("I.",  "Dönem Başı Bakiye",                 [10,2,0,1, 1,0,0, 0,0,0, 30,20,36], 100),
        _eq_row("II.", "Dönem İçi Değişiklikler",           [ 0,0,0,0, 0,0,0, 0,0,0,  0, 0, 0],   0),
        _eq_row("III.","Ara Toplam (I+II)",                 [10,2,0,1, 1,0,0, 0,0,0, 30,20,36], 100),
        _eq_row("IV.", "Toplam Kapsamlı Gelir/Gider",       [ 0,0,0,0, 0,0,0, 0,0,0,  0, 0,20],  20),
        _eq_row("VI.", "Temettü Ödemeleri",                 [ 0,0,0,0, 0,0,0, 0,0,0,-10, 0, 0], -10),
        _eq_row("",    "Dönem Sonu Bakiyesi (I+...+XI)",    [10,2,0,1, 1,0,0, 0,0,0, 20,20,56], 110),
    ]


def _clean_equity_prior():
    """Prior-period page (same structure, different values).
    I. Opening 84; III=84; IV. comprehensive 16; closing = 100.
    Q4 open/close: current I.total (100) == prior closing (100) ✓.
    """
    return [
        _eq_row("I.",  "Dönem Başı Bakiye",               [10,2,0,1, 1,0,0, 0,0,0, 25,15,30],  84, "prior"),
        _eq_row("II.", "Dönem İçi Değişiklikler",         [ 0,0,0,0, 0,0,0, 0,0,0,  0, 0, 0],   0, "prior"),
        _eq_row("III.","Ara Toplam (I+II)",               [10,2,0,1, 1,0,0, 0,0,0, 25,15,30],  84, "prior"),
        _eq_row("IV.", "Toplam Kapsamlı Gelir/Gider",     [ 0,0,0,0, 0,0,0, 0,0,0,  0, 0,16],  16, "prior"),
        _eq_row("",    "Dönem Sonu Bakiyesi (I+...+XI)",  [10,2,0,1, 1,0,0, 0,0,0, 25,15,46], 100, "prior"),
    ]


def test_equity_change_clean_passes():
    rows = _clean_equity_current() + _clean_equity_prior()
    # OCI III = 20 matches current row IV (comprehensive income);
    # BS equity at "XVI." (roman top-level) so _path returns (16,), len=1 ✓
    oci = [_oci_row("III.", "TOPLAM KAPSAMLI GELİR", 20)]
    liab = [_row("XVI.", "TOPLAM ÖZKAYNAKLAR", 70, 40, 110)]
    res = v.check_equity_change(rows, oci_rows=oci, liabilities=liab, period="2024Q4")
    assert res.failed == 0, res.failures
    assert res.passed >= 3


def test_equity_change_row_sum_fails():
    rows = _clean_equity_current()
    # break row I: total doesn't match component sum (100 → 999)
    rows[0] = dict(rows[0], total_equity=999 * 1000)
    res = v.check_equity_change(rows)
    assert any(f["check"] == "eq_row_sum" for f in res.failures)


def test_equity_change_col_chain_fails():
    rows = _clean_equity_current()
    # break III: III.total ≠ I.total + II.total (I=100, II=0, III should be 100)
    rows[2] = dict(rows[2], total_equity=999 * 1000)
    res = v.check_equity_change(rows)
    assert any(f["check"] == "eq_col_chain" for f in res.failures)


def test_equity_change_oci_cross_fails():
    rows = _clean_equity_current()
    # OCI III = 999 ≠ equity row IV total (20)
    oci = [_oci_row("III.", "TOPLAM KAPSAMLI GELİR", 999)]
    res = v.check_equity_change(rows, oci_rows=oci)
    assert any(f["check"] == "eq_oci_cross" for f in res.failures)


def test_equity_change_bs_cross_fails():
    rows = _clean_equity_current()
    # "XVI." → _path returns (16,), len=1 → matcher picks it up; 999k ≠ 110k closing
    liab = [_row("XVI.", "TOPLAM ÖZKAYNAKLAR", 50, 50, 999)]
    res = v.check_equity_change(rows, liabilities=liab)
    assert any(f["check"] == "eq_bs_cross" for f in res.failures)


def test_equity_change_open_close_q4_fails():
    cur = _clean_equity_current()
    pri = _clean_equity_prior()
    # current opening (row I, total=100) != prior closing (total=100 by default — change to 90)
    pri[-1] = dict(pri[-1], total_equity=90 * 1000)
    rows = cur + pri
    res = v.check_equity_change(rows, period="2024Q4")
    assert any(f["check"] == "eq_open_close" for f in res.failures)


def test_equity_change_open_close_interim_skips():
    rows = _clean_equity_current() + _clean_equity_prior()
    res = v.check_equity_change(rows, period="2024Q3")
    assert not any(f["check"] == "eq_open_close" for f in res.failures)


def test_equity_change_empty_skips():
    res = v.check_equity_change([])
    assert res.failed == 0 and res.skipped >= 1
