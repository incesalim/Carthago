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
