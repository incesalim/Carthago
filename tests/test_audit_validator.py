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


def test_statement_total_spurious_dup_ordinal_does_not_hide_section():
    """A stray page-header row captured with a numeric hierarchy ('5', amount 0)
    shares ordinal 5 with the real section V — the larger contribution must win so
    V isn't dropped from Σromans (the ISCTR 2025Q4 off_balance false positive)."""
    rows = [
        _row("I.", "GUARANTEES", 0, 0, 100),
        _row("5", "BANK NAME A.Ş. UNCONSOLIDATED STATEMENT", 0, 0, 0),  # stray header
        _row("V.", "PLEDGED ITEMS", 0, 0, 600),
        _row("", "TOTAL OFF-BALANCE (A+B)", 0, 0, 700),
    ]
    total, romans = v._statement_total(rows)
    assert (total, romans) == (700_000, 700_000)  # 100 (I) + 600 (V), header ignored
    assert v.check_statement_total(rows).failed == 0


def test_off_balance_catches_dropped_derivative_leg():
    """Off-balance now runs V2: a "Forward FX Buy/Sell" parent whose Sell leg
    (3.2.1.2) was dropped foots to half — the real EXIM/VAKBN 2022 defect that
    V1 triplets alone (each surviving row foots TL+FC=Total) could not see."""
    rows = [
        _row("3.2.1", "Forward Foreign Currency Buy/Sell", 80, 54, 134),
        _row("3.2.1.1", "Forward FX Transactions-Buy", 40, 27, 67),
        # 3.2.1.2 "…-Sell" (40/27/67) is missing → parent != Σ children
    ]
    res = v.validate_off_balance(rows)
    assert any(f["check"] == "hierarchy_sum" for f in res.failures), res.failures


def test_off_balance_skip_level_does_not_false_fail():
    """A parent with no captured children is skipped, not failed — so the
    off-balance skip-level numbering (1. → 1.1.1 with no 1.1) stays clean."""
    rows = [
        _row("1", "GUARANTEES AND SURETIES", 60, 40, 100),   # no 1.x children
        _row("1.1.1", "Letters of Guarantee in TL", 36, 24, 60),  # orphan leaf
    ]
    res = v.validate_off_balance(rows)
    assert res.failed == 0, res.failures


def test_off_balance_does_not_run_statement_total():
    """V3 stays OFF for off-balance: the A/B custody-split grand total exceeds
    Σ top-level rows by a stable per-bank offset (structural, not a bug), so
    validate_off_balance must not raise statement_total."""
    rows = [
        _row("1", "IRREVOCABLE COMMITMENTS", 60, 40, 100),
        _row("2", "DERIVATIVES", 100, 100, 200),
        # custody side (B.) not captured as numeric rows → labelled total > Σ
        _row("", "TOTAL OFF-BALANCE SHEET ITEMS (A+B)", 200, 150, 350),
    ]
    res = v.validate_off_balance(rows)
    assert all(f["check"] != "statement_total" for f in res.failures), res.failures


def test_duplicate_hierarchy_collision_flagged():
    # EXIM/VAKBN source typo: two DIFFERENT line items stamped on one key
    # (the Forward-FX Sell leg mislabelled 3.2.2.2, colliding with Swap-Sell).
    rows = [
        _row("3.2.2.2", "Forward Foreign Currency Transactions-Sell", 36, 30, 67),
        _row("3.2.2.2", "Foreign Currency Swap-Sell", 3600, 3823, 7423),
    ]
    assert any(f["check"] == "dup_hierarchy"
               for f in v.check_no_duplicate_hierarchy(rows).failures)


def test_duplicate_hierarchy_benign_cases_pass():
    # same key + SAME item (trailing-dot spelling) is one row, not a collision
    same = [_row("2.1", "Irrevocable Commitments", 60, 40, 100),
            _row("2.1.", "Irrevocable Commitments", 60, 40, 100)]
    assert v.check_no_duplicate_hierarchy(same).failed == 0
    # different names but both all-zero (template placeholder rows) — not flagged
    zeros = [_row("3.2.3.1", "FX Options-Buy", 0, 0, 0),
             _row("3.2.3.1", "Something Else", 0, 0, 0)]
    assert v.check_no_duplicate_hierarchy(zeros).failed == 0


def test_grand_total_ab_reconciles_and_catches_lost_block():
    ok = [
        _row("A", "COMMITMENTS AND CONTINGENCIES (I+II+III)", 60, 40, 100),
        _row("B", "CUSTODY AND PLEDGED ITEMS (IV+V+VI)", 120, 80, 200),
        _row("", "TOTAL OFF-BALANCE SHEET ITEMS (A+B)", 180, 120, 300),
    ]
    r = v.check_grand_total_ab(ok)
    assert r.failed == 0 and r.passed == 1
    # B block's value silently lost (row present, zeroed) but the total still
    # carries it — the case V2's parent-sums can't see. A + B != total -> fail.
    lost = [
        _row("A", "COMMITMENTS", 60, 40, 100),
        _row("B", "CUSTODY", 0, 0, 0),
        _row("", "TOTAL (A+B)", 108, 72, 300),
    ]
    assert v.check_grand_total_ab(lost).failed == 1
    # no B row at all -> can't reconcile -> skip, never fail
    r2 = v.check_grand_total_ab([_row("A", "COMMITMENTS", 60, 40, 100),
                                 _row("", "TOTAL (A+B)", 60, 40, 100)])
    assert r2.failed == 0 and r2.skipped == 1


def test_prior_column_identities_checked():
    from types import SimpleNamespace
    good = [SimpleNamespace(hierarchy="1.1", name="Cash",
                            cur_tl=60_000, cur_fc=40_000, cur_total=100_000,
                            pri_tl=30_000, pri_fc=20_000, pri_total=50_000)]
    pr = v._prior_rows(good)
    assert pr[0]["amount_tl"] == 30_000 and pr[0]["amount_total"] == 50_000
    assert v.check_row_triplets(pr).failed == 0
    # a value error in the PRIOR column (current still foots) is now caught
    bad = [SimpleNamespace(hierarchy="1.1", name="Cash",
                           cur_tl=60_000, cur_fc=40_000, cur_total=100_000,
                           pri_tl=30_000, pri_fc=20_000, pri_total=999_000)]
    assert v.check_row_triplets(v._prior_rows(bad)).failed == 1


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


def _compressed_pl(cont_net="XVIII.", period_net="XXIV."):
    """The compressed template some participation banks file (DUNYAK, TOMK):
    one fewer opex roman, so net-operating lands at XII and every later subtotal
    shifts down one — pre-tax XVI, tax XVII. The report states this numbering in
    the formulas it prints. Same arithmetic as _clean_pl: III=150, VIII=215,
    XII=160, XVI=160, continuing-net=130, period-net=130.

    cont_net/period_net vary by filer: DUNYAK runs XVIII/XXIV, TOMK skips XVIII
    entirely and prints continuing-net at XIX with period-net back at XXV.
    """
    disc_net = _roman(_int_roman(period_net) - 1)
    return [
        _pl("I.", "KÂR PAYI GELİRLERİ", 200),
        _pl("II.", "KÂR PAYI GİDERLERİ (-)", 50),
        _pl("III.", "NET KÂR PAYI GELİRİ/GİDERİ", 150),
        _pl("IV.", "NET ÜCRET VE KOMİSYON GELİRLERİ/GİDERLERİ", 10),
        _pl("V.", "TEMETTÜ GELİRLERİ", 20),
        _pl("VI.", "TİCARİ KAR/ZARAR (Net)", 30),
        _pl("VII.", "DİĞER FAALİYET GELİRLERİ", 5),
        _pl("VIII.", "FAALİYET BRÜT KÂRI (III+IV+V+VI+VII)", 215),
        _pl("IX.", "KREDİ KARŞILIKLARI (-)", 40),
        _pl("X.", "PERSONEL GİDERLERİ (-)", 10),
        _pl("XI.", "DİĞER FAALİYET GİDERLERİ (-)", 5),
        _pl("XII.", "NET FAALİYET KÂRI/ZARARI (VIII-IX-X-XI)", 160),
        _pl("XIII.", "BİRLEŞME İŞLEMİ SONRASINDA GELİR OLARAK KAYDEDİLEN", 0),
        _pl("XIV.", "ÖZKAYNAK YÖNTEMİ UYGULANAN ORTAKLIKLARDAN KÂR/ZARAR", 0),
        _pl("XV.", "NET PARASAL POZİSYON KÂRI/ZARARI", 0),
        _pl("XVI.", "SÜRDÜRÜLEN FAALİYETLER VERGİ ÖNCESİ K/Z (XII+...+XV)", 160),
        _pl("XVII.", "SÜRDÜRÜLEN FAALİYETLER VERGİ KARŞILIĞI (±)", 30),
        _pl(cont_net, "SÜRDÜRÜLEN FAALİYETLER DÖNEM NET K/Z (XVI±XVII)", 130),
        _pl(disc_net, "DURDURULAN FAALİYETLER DÖNEM NET K/Z", 0),
        _pl(period_net, "DÖNEM NET KARI/ZARARI", 130),
    ]


_ROMANS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
           "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI",
           "XXII", "XXIII", "XXIV", "XXV"]


def _int_roman(h):
    return _ROMANS.index(h.rstrip("."))


def _roman(i):
    return _ROMANS[i] + "."


def test_pl_compressed_template_passes():
    """DUNYAK's numbering: pre-tax XVI / tax XVII / continuing-net XVIII /
    period-net XXIV. Hardcoding 17/18/19/25 compared the TAX row against the
    pre-tax sum and failed 8 correct partitions."""
    res = v.check_pl_chain(_compressed_pl())
    assert res.failed == 0, res.failures
    assert res.passed == 6  # every identity RUNS — not skipped into silence


def test_pl_compressed_template_with_missing_tax_roman_passes():
    """TOMK's variant: same compressed head, but the filing has no XVIII roman
    at all — tax sits at XVII with 18.x children and continuing-net at XIX."""
    res = v.check_pl_chain(_compressed_pl(cont_net="XIX.", period_net="XXV."))
    assert res.failed == 0, res.failures
    assert res.passed == 6


def test_pl_compressed_template_still_catches_a_real_break():
    """The template-aware chain must not pass everything: corrupt net-operating
    (XII here, not XIII) and the identity that owns it still fails."""
    rows = _compressed_pl()
    for r in rows:
        if r["hierarchy"] == "XII.":
            r["amount"] = 999 * 1000
    res = v.check_pl_chain(rows)
    assert any(f["check"] == "pl_chain" and "12" in f["node"] for f in res.failures), res.failures


def test_pl_unreadable_anchor_labels_fall_back_to_standard():
    """HAYATK 2024Q2's wrapped labels leave XIX as 'OPERATIONS (XV±XVI)' — no
    anchor to read. An unreadable partition must behave exactly as it did before
    (standard ordinals), never guess a template."""
    rows = _clean_pl()
    for r in rows:  # strip the semantics off every anchor label
        r["item_name"] = "OPERATIONS (XV±XVI)"
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures
    assert res.passed == 6


def test_pl_roles_standard_template():
    """The role map heatmap.ts joins: on the standard template the period-net is
    XXV. and the two opex lines are XI./XII."""
    roles = v.pl_roles(_clean_pl())
    assert roles["XXV."] == "period_net"
    assert roles["XI."] == "opex_personnel"
    assert roles["XII."] == "opex_other"
    assert roles["VIII."] == "gross"


def test_pl_roles_compressed_template_moves_period_net_and_opex():
    """DUNYAK's numbering: period-net XXIV. (not XXV.) and opex X./XI. (not
    XI./XII.). Hardcoding the standard ordinals read XIX. — discontinued-ops
    income, nil — as net profit, and summed net operating PROFIT into opex."""
    roles = v.pl_roles(_compressed_pl())
    assert roles["XXIV."] == "period_net"
    assert "XXV." not in roles
    assert roles["X."] == "opex_personnel"
    assert roles["XI."] == "opex_other"
    # the rows the old query named are NOT opex here
    assert roles.get("XII.") == "net_op"


def test_pl_roles_compressed_variant_with_period_net_at_25():
    """TOMK: compressed head (opex X./XI.) but period-net back at XXV."""
    roles = v.pl_roles(_compressed_pl(cont_net="XIX.", period_net="XXV."))
    assert roles["XXV."] == "period_net"
    assert roles["X."] == "opex_personnel"
    assert roles["XI."] == "opex_other"


def test_pl_roles_positional_fallback_when_labels_are_empty():
    """AKBNK 2022Q4/2026Q1 print the whole P&L with EMPTY item_names — nothing to
    label-match. The opex pair falls back to the last two rows of the deduction
    band, which is what the ordinal read got right for those four partitions.
    (Verified corpus-wide: the fallback agrees with the label match on all 1,046
    partitions that HAVE labels.)"""
    rows = _clean_pl()
    for r in rows:
        r["item_name"] = ""
    roles = v.pl_roles(rows)
    assert roles["XI."] == "opex_personnel"
    assert roles["XII."] == "opex_other"
    assert roles["XXV."] == "period_net"   # anchors fall back to standard ordinals


def test_pl_roles_opex_label_match_is_confined_to_the_deduction_band():
    """A like-named row OUTSIDE the band must not claim the opex tag — 'DİĞER
    FAALİYET GELİRLERİ' (income, VII.) sits right above gross and reads almost
    the same as 'DİĞER FAALİYET GİDERLERİ' (expense)."""
    roles = v.pl_roles(_clean_pl())
    assert "VII." not in roles          # other operating INCOME never tagged
    assert sorted(r for r in roles.values() if r.startswith("opex_")) == \
        ["opex_other", "opex_personnel"]


def test_pl_discontinued_block_does_not_anchor_continuing_rows():
    """The discontinued block mirrors the continuing block almost word for word.
    If 'DURDURULAN … VERGİ ÖNCESİ' were allowed to claim the pre-tax anchor the
    whole chain would shift and false-fail."""
    rows = _clean_pl() + [
        _pl("XXII.", "DURDURULAN FAALİYETLER VERGİ ÖNCESİ K/Z", 0),
        _pl("XXIII.", "DURDURULAN FAALİYETLER VERGİ KARŞILIĞI (±)", 0),
    ]
    rows.sort(key=lambda r: _int_roman(r["hierarchy"]))
    tpl = v._pl_template(rows, v._pl_spine(rows))
    assert (tpl["pretax"], tpl["tax"]) == (17, 18)
    assert v.check_pl_chain(rows).failed == 0


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


def test_pl_spine_stray_mid_statement_keeps_tail():
    """HSBC-style: 'XIV.' misparsed as hierarchy 'X' mid-statement. The stray
    must drop out ALONE — the valid XV–XXV tail stays in the spine and all six
    chain identities still run (the old contiguous-run spine severed the tail
    and silently skipped XVII/XIX/XXV)."""
    rows = _clean_pl()
    i = next(k for k, r in enumerate(rows) if r["hierarchy"] == "XIV.")
    rows.insert(i, {"hierarchy": "X", "item_name": "IV. BİRLEŞME İŞLEMİ SONRASINDA", "amount": 0.0})
    res = v.check_pl_chain(rows)
    assert res.failed == 0, res.failures
    assert res.passed == 6


def test_pl_bottomline_hierarchy_fallback_english_label():
    """GARAN-style English template: 'NET PROFIT/LOSS (XIX+XXIV)' matches no
    label pattern — the XXV row must still be found by hierarchy."""
    rows = _clean_pl()
    for r in rows:
        r["item_name"] = {"XXV.": "NET PROFIT/LOSS (XIX+XXIV)"}.get(r["hierarchy"], "x")
    li = [_row("16.6.2", "Net Dönem Kârı/Zararı", 70, 60, 130)]
    res = v.check_pl_bottomline(rows, li)
    assert res.passed == 1 and res.failed == 0, res.failures


def test_pl_bottomline_hierarchy_fallback_empty_labels():
    """AKBNK 2026Q1-style: every P&L label empty — hierarchy alone must carry
    the net-profit cross-check."""
    rows = _clean_pl()
    for r in rows:
        r["item_name"] = ""
    li = [_row("16.6.2", "Net Dönem Kârı/Zararı", 70, 60, 130)]
    res = v.check_pl_bottomline(rows, li)
    assert res.passed == 1 and res.failed == 0, res.failures


def test_pl_bottomline_hierarchy_fallback_still_fails_mismatch():
    """The fallback widens REACH, not tolerance: a label-less XXV that doesn't
    tie to BS equity still fails."""
    rows = _clean_pl()
    for r in rows:
        r["item_name"] = ""
    li = [_row("16.6.2", "Net Dönem Kârı/Zararı", 50, 40, 90)]
    res = v.check_pl_bottomline(rows, li)
    assert res.failed == 1


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


def test_oci_cross_check_runs_on_the_compressed_template():
    """The cross-check must find period-net at whatever roman THIS filer uses.
    It hardcoded XXV, so on the compressed template (period-net at XXIV) it read
    None and SKIPPED — silently disabling the only cross-statement check OCI has,
    on 6 DUNYAK partitions that then read green on internal footing alone. Both
    fixtures net to 130, so the check must RUN and PASS for each."""
    for period_net in ("XXIV.", "XXV."):        # DUNYAK's numbering, then TOMK's
        res = v.check_oci(_clean_oci(), _compressed_pl(period_net=period_net))
        assert res.failed == 0, (period_net, res.failures)
        # skipped == 0 is the whole point: the cross-check is the only thing here
        # that can skip, so a zero proves it RAN rather than passing by absence.
        assert res.skipped == 0, (period_net, res.skipped)


def test_oci_cross_check_still_fails_on_the_compressed_template():
    """…and running is worth nothing if it can't fail: same numbering, wrong net."""
    oci = _clean_oci()
    for r in oci:
        if r["hierarchy"] == "I.":
            r["amount"] = 999 * 1000
    res = v.check_oci(oci, _compressed_pl(period_net="XXIV."))
    assert any(f["check"] == "oci_cross" for f in res.failures), res.failures


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


def test_capital_dropped_rwa_fails():
    # Total RWA is the mandatory §4 denominator; NULL = dropped column. Must FAIL,
    # not skip — every ratio reconcile skips without it, so it would pass 'ok'.
    res = v.check_capital([_cap_row(total_rwa=None)])
    assert any(f["check"] == "cap_rwa_missing" for f in res.failures)


def test_capital_dropped_car_not_derivable_fails():
    # CAR null AND total_capital null = not derivable → dropped column → FAIL.
    res = v.check_capital([_cap_row(capital_adequacy_ratio=None, total_capital=None)])
    assert any(f["check"] == "cap_car_missing" for f in res.failures)


def test_capital_car_derivable_skips():
    # CAR null but RWA + total_capital present → CAR = TC/RWA computable, cell
    # complete → must NOT false-fail (banks that simply don't print the ratio line).
    res = v.check_capital([_cap_row(capital_adequacy_ratio=None)])
    assert not any(f["check"] == "cap_car_missing" for f in res.failures)


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
    """s3=None is meaningful, not missing: loans_by_stage carries no stage-3
    column (the BRSA stage-3 balance lives in npl_brsa_gross)."""
    def _x(v):
        return None if v is None else v * 1000
    return {"section": section, "period_type": period_type,
            "stage1_amount": _x(s1), "stage2_amount": _x(s2),
            "stage3_amount": _x(s3), "total_amount": _x(tot)}


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


def test_cq_loans_by_stage_two_stage_total_passes():
    """S3 is NULL on loans_by_stage BY DESIGN (the BRSA stage-3 balance lives in
    npl_brsa_gross) — 1,036/1,036 rows — so the four-column identity skips every
    one of them. The two-stage form covers the section that carries the split."""
    res = v.check_credit_quality([_cq_row("loans_by_stage", 100, 50, None, 150)])
    assert res.failed == 0 and res.passed == 1, res.failures


def test_cq_loans_by_stage_two_stage_total_fails():
    res = v.check_credit_quality([_cq_row("loans_by_stage", 100, 50, None, 900)])
    assert any(f["check"] == "cq_loans_by_stage_total" for f in res.failures), res.failures


def test_cq_loans_by_stage_with_s3_uses_the_generic_check_only():
    """A section that does carry all four stays with the generic identity and is
    not counted twice."""
    res = v.check_credit_quality([_cq_row("loans_by_stage", 100, 50, 30, 180)])
    assert res.failed == 0 and res.passed == 1, res.failures


def test_cq_gross_vs_movement_disagreement_fails():
    """The mirror of npl_closing_vs_gross, raised on THIS lane too — the evidence
    says credit_quality is usually the defective side (ICBCT's gross freezes for
    quarters while the movement closing tracks), and flagging only the movement
    lane would leave the wrong number protected by statement_passes()."""
    cq = [_cq_row("npl_brsa_gross", 1, 1, 1, 3)]
    npl = [{"group_code": "III", "period_type": "current",
            "closing_balance": 999_000}]
    res = v.check_credit_quality(cq, npl)
    assert any(f["check"] == "cq_gross_vs_movement" for f in res.failures), res.failures


def test_cq_gross_vs_movement_agrees_passes():
    cq = [_cq_row("npl_brsa_gross", 150, 200, 150, 500)]
    npl = [{"group_code": "III", "period_type": "current",
            "closing_balance": 150 * 1000}]
    res = v.check_credit_quality(cq, npl)
    assert res.failed == 0, res.failures


def test_cq_without_movement_rows_is_unchanged():
    res = v.check_credit_quality([_cq_row("npl_brsa_gross", 150, 200, 150, 500)])
    assert res.failed == 0, res.failures


def test_npl_brsa_sections_flagged_as_group_basis():
    # The stage1/2/3 columns mean BRSA groups III/IV/V (NOT IFRS stages) only for
    # the npl_brsa_* sections; everything else is a real IFRS stage.
    import pytest
    # credit_quality is fitz-only AND pulls in extractor (fitz at module top);
    # CI's minimal deps omit fitz, so skip there (runs locally / full-deps env).
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


# --- stages ⋈ balance-sheet loans (2.1) ------------------------------------
# _clean_assets() carries `2.1 Loans` at 210_000, so a stage row totalling
# 210_000 reconciles exactly.

def test_stages_bs_loans_reconciles_passes():
    res = v.check_stages([_stage_row(stage1_amount=160_000, stage2_amount=30_000,
                                     stage3_amount=20_000, total_amount=210_000)],
                         bs_loans=_clean_assets())
    assert res.failed == 0, res.failures


def test_stages_bs_loans_fragment_table_fails():
    """The SKBNK/FIBA defect: a fragment sub-table read as the whole loan book.
    Every internal identity still foots (the row is self-consistent) — only the
    balance sheet contradicts it. SKBNK 2025Q4 publishes a 39.51% NPL this way
    against a truth of ~1.33%, scoring 6 passed / 0 failed."""
    rows = [_fragment_stage_row()]
    assert v.check_stages(rows).failed == 0          # internally consistent…
    res = v.check_stages(rows, bs_loans=_clean_assets())   # …but 7k vs 210k
    assert any(f["check"] == "stages_bs_loans" for f in res.failures), res.failures


def test_stages_bs_loans_structural_offset_passes():
    """No false positive on the real 1.05–1.20 band: consolidated groups carry
    leasing/factoring inside the IFRS-9 table but outside BS 2.1 (BURGAN, TOMK,
    YKBNK, DENIZ do this EVERY quarter). 250k/210k = 1.19 must PASS."""
    res = v.check_stages([_stage_row(stage1_amount=180_000, stage2_amount=50_000,
                                     stage3_amount=20_000, total_amount=250_000)],
                         bs_loans=_clean_assets())
    assert res.failed == 0, res.failures


def test_stages_bs_loans_zero_loans_skips():
    """A bank whose loan book hasn't started (BS 2.1 = 0) — 6 real partitions.
    A ratio is undefined, not wrong."""
    assets = [_row("2.1", "Loans", 0, 0, 0)]
    res = v.check_stages([_stage_row(total_amount=650_000)], bs_loans=assets)
    assert res.failed == 0, res.failures


def _fragment_stage_row():
    """A self-consistent stage row that is nonetheless a fragment of the real loan
    book: 5+1+1 = 7 foots, but the balance sheet says 210."""
    return _stage_row(stage1_amount=5_000, stage2_amount=1_000,
                      stage3_amount=1_000, total_amount=7_000,
                      stage1_ecl=40, stage2_ecl=80, stage3_ecl=400, total_ecl=520)


def test_stages_bs_loans_trailing_dot_hierarchy_resolves():
    """Anchored by _path, not string equality — '2.1.' must resolve like '2.1'.
    Both spellings have shipped defects in this corpus."""
    assets = [_row("2.1.", "Krediler", 130, 80, 210)]
    res = v.check_stages([_fragment_stage_row()], bs_loans=assets)
    assert any(f["check"] == "stages_bs_loans" for f in res.failures), res.failures


def test_stages_without_bs_loans_is_unchanged():
    """The arg is optional — omitting it must not add a check either way, so the
    fragment row above is invisible without the anchor."""
    assert v.check_stages([_fragment_stage_row()]).failed == 0


# --- off-balance V7: B. block = Σ romans IV+V+VI ---------------------------

def _clean_b_block():
    return [
        _row("IV.", "EMANET KIYMETLER", 30, 20, 50),
        _row("V.", "REHİNLİ KIYMETLER", 60, 40, 100),
        _row("VI.", "KABUL EDİLEN AVALLER VE KEFALETLER", 12, 8, 20),
        _row("B.", "EMANET VE REHİNLİ KIYMETLER", 102, 68, 170),
    ]


def test_off_balance_b_block_passes():
    res = v.check_b_block(_clean_b_block())
    assert res.failed == 0 and res.passed == 1, res.failures


def test_off_balance_b_block_catches_dropped_section():
    """The whole point: V6 cannot see this (dropping a section leaves A+B=total
    intact), and V2 cannot either (every surviving row's parent still foots).
    V7 sees it because B is what it checks AGAINST, not an operand it needs."""
    rows = [r for r in _clean_b_block() if r["hierarchy"] != "V."]
    res = v.check_b_block(rows)
    assert any(f["check"] == "off_balance_b_block" for f in res.failures), res.failures


def test_off_balance_b_block_absent_section_still_foots():
    """A legitimately absent section contributes 0 and B foots anyway — the
    distinction from a DROPPED one, which leaves the sum short."""
    rows = [_row("IV.", "EMANET KIYMETLER", 30, 20, 50),
            _row("V.", "REHİNLİ KIYMETLER", 60, 40, 100),
            _row("B.", "EMANET VE REHİNLİ KIYMETLER", 90, 60, 150)]
    res = v.check_b_block(rows)
    assert res.failed == 0 and res.passed == 1, res.failures


def test_off_balance_b_block_no_letter_row_skips():
    res = v.check_b_block([_row("IV.", "EMANET KIYMETLER", 30, 20, 50)])
    assert res.failed == 0 and res.skipped == 1


# --- equity closing paid-in capital ⋈ BS S.1 -------------------------------

def _eq_closing_row(**kw):
    d = {"hierarchy": "", "item_name": "Dönem Sonu Bakiyesi", "period_type": "current",
         "paid_in_capital": 10_000_000.0, "share_premium": 0.0,
         "total_equity": 12_000_000.0}
    d.update(kw)
    return d


def _bs_equity_16():
    return [_row("XVI.", "ÖZKAYNAKLAR", 12_000, 0, 12_000),
            _row("16.1", "Ödenmiş Sermaye", 10_000, 0, 10_000)]


def test_eq_paid_in_capital_ties_passes():
    res = v.check_eq_paid_in_capital([_eq_closing_row()], _bs_equity_16())
    assert res.failed == 0 and res.passed == 1, res.failures


def test_eq_paid_in_capital_column_shift_fails():
    """EXIM 2024Q2's shape: ₺35.7bn of paid-in filed under share_premium leaves
    paid_in_capital = 0. The row's SUM is unchanged, so eq_row_sum and the
    total_equity chain both still foot — only the balance sheet contradicts it."""
    shifted = _eq_closing_row(paid_in_capital=0.0, share_premium=10_000_000.0)
    res = v.check_eq_paid_in_capital([shifted], _bs_equity_16())
    assert any(f["check"] == "eq_paid_in_capital" for f in res.failures), res.failures


def test_eq_paid_in_capital_resolves_participation_section():
    """Participation banks carry equity at XIV, so paid-in is 14.1 — resolved
    from the statement, never assumed."""
    liab = [_row("XIV.", "ÖZKAYNAKLAR", 12_000, 0, 12_000),
            _row("14.1", "Ödenmiş Sermaye", 10_000, 0, 10_000)]
    assert v.check_eq_paid_in_capital([_eq_closing_row()], liab).passed == 1


def test_eq_paid_in_capital_does_not_read_loans_as_capital():
    """The trap this check must not fall into. For a bank whose equity is at XVI,
    row 14.1 is KREDİLER — 801 partitions in the corpus. A tuple-set anchor of
    (16,1)-or-(14,1) (the shape check_pl_bottomline safely uses at DEPTH 3) would
    compare paid-in capital against the BORROWINGS line here and call it a
    defect. Resolving the section first is what makes that impossible."""
    liab = _bs_equity_16() + [_row("14.1", "Krediler", 900_000, 0, 900_000)]
    res = v.check_eq_paid_in_capital([_eq_closing_row()], liab)
    assert res.failed == 0 and res.passed == 1, res.failures


def test_eq_paid_in_capital_no_equity_section_skips():
    """AKBNK 2026Q1 prints the statement with empty labels — the section can't be
    resolved, so the check must skip rather than guess an ordinal."""
    liab = [_row("16.1", "", 10_000, 0, 10_000)]
    res = v.check_eq_paid_in_capital([_eq_closing_row()], liab)
    assert res.failed == 0 and res.skipped == 1


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


# These fixtures carry no gross_by_group and no provision/net_balance, so the two
# checks that are independent of the roll-forward (npl_closing_vs_gross,
# npl_provision_net) always skip here. The assertions below therefore pin the
# roll-forward's own verdict — passed/failed — rather than a total skip count,
# which would break every time the lane gains a check.

def test_npl_movement_null_col_that_ties_passes():
    # A flow column absent from the disclosure (NULL) that is genuinely 0 — the
    # roll-forward ties with it as 0 → PASS (the bank simply omitted a zero row),
    # not a false skip. closing 120 = 100 + 30 - 10 - 0(write_offs).
    res = v.check_npl_movement([_npl_row(write_offs=None, closing_balance=120_000)])
    assert res.passed == 1 and res.failed == 0, res.failures


def test_npl_movement_null_col_that_breaks_tie_skips():
    # NULL flow column where treating it as 0 does NOT tie → could be a genuinely
    # non-zero value the extractor missed → SKIP, never a false fail.
    # (base ties only with write_offs=5000; nulling it leaves implied 120 ≠ 115.)
    # Neither passed nor failed ⇒ the roll-forward skipped.
    res = v.check_npl_movement([_npl_row(write_offs=None)])
    assert res.failed == 0 and res.passed == 0, res.failures


def test_npl_movement_dropped_closing_fails():
    # opening + flows present but closing NULL = dropped closing column (the bank
    # reported this group; a genuinely-omitted group has no row at all). Must FAIL,
    # not skip — the blind spot that masked AKBNK's dropped closing column.
    res = v.check_npl_movement([_npl_row(closing_balance=None)])
    assert any(f["check"] == "npl_movement_balance_missing" for f in res.failures)


def test_npl_movement_empty_group_skips():
    # No balances AND no flows = a genuinely empty/omitted group → skip, not fail.
    res = v.check_npl_movement([_npl_row(
        opening_balance=None, closing_balance=None, additions=None,
        transfers_in=None, transfers_out=None, collections=None,
        write_offs=None, sold=None)])
    assert res.failed == 0 and res.passed == 0


# --- NPL closing ⋈ npl_brsa_gross (runs unconditionally) -------------------

def test_npl_closing_vs_gross_passes():
    res = v.check_npl_movement([_npl_row()], gross_by_group={"III": 115_000})
    assert res.failed == 0, res.failures


def test_npl_closing_vs_gross_disagreement_fails():
    """FIBA 2025Q4's shape: the roll-forward ties perfectly, and the closing still
    contradicts the independently-reported gross. Previously the gross was only
    consulted AFTER a roll-forward failure, so a tying partition was never
    compared and this was invisible."""
    res = v.check_npl_movement([_npl_row()], gross_by_group={"III": 1_000})
    assert any(f["check"] == "npl_closing_vs_gross" for f in res.failures), res.failures


def test_npl_closing_vs_gross_no_gross_skips():
    res = v.check_npl_movement([_npl_row()])
    assert res.failed == 0, res.failures


def test_npl_gross_rescue_still_excuses_an_unmodeled_flow():
    """The rescue branch must survive: a roll-forward that doesn't tie only
    because of an unmodeled 'Diğer' flow, whose closing DOES match the gross, is
    faithful data and must not fail the roll-forward."""
    res = v.check_npl_movement([_npl_row(closing_balance=140_000)],
                               gross_by_group={"III": 140_000})
    assert not any(f["check"] == "npl_movement" for f in res.failures), res.failures


# --- NPL closing − |provision| = net ---------------------------------------

def test_npl_provision_net_passes():
    res = v.check_npl_movement([_npl_row(provision=15_000, net_balance=100_000)])
    assert res.failed == 0, res.failures


def test_npl_provision_net_fails():
    res = v.check_npl_movement([_npl_row(provision=15_000, net_balance=50_000)])
    assert any(f["check"] == "npl_provision_net" for f in res.failures), res.failures


def test_npl_provision_net_paren_negative_storage_passes():
    """Some banks print the provision in parentheses → stored negative. Both
    conventions must subtract (the storage lesson from the P&L deductions)."""
    res = v.check_npl_movement([_npl_row(provision=-15_000, net_balance=100_000)])
    assert res.failed == 0, res.failures


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


def test_loans_by_sector_dropped_total_fails():
    # Sector detail present but no TOTAL row = dropped total; footing can't run.
    rows = [_sector_row("agri_total", 10, 5, 3), _sector_row("mfg_total", 20, 10, 6),
            _sector_row("svc_total", 30, 15, 9)]
    res = v.check_loans_by_sector(rows)
    assert any(f["check"] == "loans_sector_total_missing" for f in res.failures)


def test_loans_by_sector_dropped_sector_cols_fails():
    # Total present but every sector row's amount columns NULL = dropped detail →
    # footing never runs → FAIL not skip.
    rows = [
        {"sector": "agri_total", "period_type": "current",
         "stage2_amount": None, "stage3_amount": None, "ecl_amount": None},
        {"sector": "mfg_total", "period_type": "current",
         "stage2_amount": None, "stage3_amount": None, "ecl_amount": None},
        _sector_row("total", 70, 35, 21),
    ]
    res = v.check_loans_by_sector(rows)
    assert any(f["check"] == "loans_sector_columns_missing" for f in res.failures)


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
