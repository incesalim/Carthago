"""Regression tests for the §4 capital/liquidity data-quality cross-checks.

These exercise scripts/check_audit_quality.py against a synthetic in-memory DB —
no PDF parsing, so they run under CI's minimal dependency set (sqlite + stdlib).
"""
import json
import sqlite3

import pytest

import check_audit_quality as q  # scripts/ is on pythonpath (see pyproject.toml)
from src.audit_reports.schema import init_schema


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    return c


def _ins_capital(c, **kw):
    cols = ["bank_ticker", "period", "kind", "period_type", "cet1_capital",
            "tier1_capital", "total_capital", "total_rwa", "capital_adequacy_ratio",
            "cet1_ratio", "tier1_ratio"]
    vals = [kw.get(k) for k in cols]
    c.execute(f"INSERT INTO bank_audit_capital ({','.join(cols)}) "
              f"VALUES ({','.join('?' for _ in cols)})", vals)
    c.commit()


def _ins_liquidity(c, **kw):
    cols = ["bank_ticker", "period", "kind", "period_type",
            "leverage_ratio", "lcr_total", "nsfr"]
    vals = [kw.get(k) for k in cols]
    c.execute(f"INSERT INTO bank_audit_liquidity ({','.join(cols)}) "
              f"VALUES ({','.join('?' for _ in cols)})", vals)
    c.commit()


def test_capital_clean_passes():
    c = _conn()
    # GARAN-like: CAR = 520/2500*100 = 20.8, tier ordering holds.
    _ins_capital(c, bank_ticker="X", period="2026Q1", kind="unconsolidated",
                 period_type="current", cet1_capital=400, tier1_capital=420,
                 total_capital=520, total_rwa=2500, capital_adequacy_ratio=20.8)
    assert q._capital_consistency(c) == []


def test_capital_flags_tier_order():
    c = _conn()
    _ins_capital(c, bank_ticker="Y", period="2026Q1", kind="unconsolidated",
                 period_type="current", cet1_capital=500, tier1_capital=400,
                 total_capital=520, total_rwa=2500, capital_adequacy_ratio=20.8)
    issues = q._capital_consistency(c)
    assert any("CET1" in i for i in issues)   # 500 > 400 (CET1 ⊆ Tier1)


def test_capital_flags_inconsistent_reported_ratios():
    # A real column-slip: the reported ratios imply different RWAs (CAR→3095,
    # tier1_ratio→1680, cet1_ratio→2500), so a capital component or ratio is
    # mis-parsed. This replaces the old CAR-vs-printed-RWA reconcile.
    c = _conn()
    _ins_capital(c, bank_ticker="Y2", period="2026Q1", kind="unconsolidated",
                 period_type="current", cet1_capital=400, tier1_capital=420,
                 total_capital=520, total_rwa=2500, capital_adequacy_ratio=16.8,
                 cet1_ratio=16.0, tier1_ratio=25.0)
    assert any("inconsistent RWA" in i for i in q._capital_consistency(c))


def test_capital_forbearance_ratios_not_flagged():
    # ATBANK 2024Q1: printed total_capital/total_rwa = 2,208,637/12,726,290 =
    # 17.35%, but the bank reports a BDDK forbearance-adjusted CAR 18.92 (and CET1
    # ratio 18.23). The old printed-RWA reconcile false-flagged this every quarter;
    # the reported ratios are mutually consistent (each → ~11.66m RWA), so the
    # forbearance-aware check must stay silent.
    c = _conn()
    _ins_capital(c, bank_ticker="ATBANK", period="2024Q1", kind="unconsolidated",
                 period_type="current", cet1_capital=2120404, tier1_capital=2120404,
                 total_capital=2208637, total_rwa=12726290, capital_adequacy_ratio=18.92,
                 cet1_ratio=18.23, tier1_ratio=18.23)
    assert q._capital_consistency(c) == []


def test_liquidity_clean_passes():
    c = _conn()
    _ins_liquidity(c, bank_ticker="W", period="2026Q1", kind="unconsolidated",
                   period_type="current", leverage_ratio=5.5, lcr_total=140.0, nsfr=120.0)
    assert q._liquidity_bands(c) == []


def test_liquidity_flags_low_lcr_and_bad_leverage():
    c = _conn()
    _ins_liquidity(c, bank_ticker="Z", period="2026Q1", kind="unconsolidated",
                   period_type="current", leverage_ratio=100.0, lcr_total=30.0, nsfr=120.0)
    issues = q._liquidity_bands(c)
    assert any("LCR" in i for i in issues)        # 30 < 50
    assert any("leverage" in i for i in issues)   # 100 out of band


def test_reconciling_startup_capital_and_liquidity_are_not_errors():
    c = _conn()
    _ins_capital(c, bank_ticker="TOMK", period="2023Q4", kind="unconsolidated",
                 period_type="current", total_capital=1090, total_rwa=789.4,
                 capital_adequacy_ratio=138.08)
    _ins_liquidity(c, bank_ticker="COLENDI", period="2025Q2", kind="unconsolidated",
                   period_type="current", leverage_ratio=65.85, lcr_total=2316303)
    assert q._capital_consistency(c) == []
    assert q._liquidity_bands(c) == []


def test_review_is_exact_value_and_partition_bound(monkeypatch):
    c = _conn()
    for period, value in [("2024Q1", 100), ("2024Q2", 100), ("2024Q3", 100),
                          ("2024Q4", 100), ("2025Q1", 10000)]:
        _ins_liquidity(c, bank_ticker="X", period=period, kind="unconsolidated",
                       period_type="current", lcr_total=value)
    monkeypatch.setattr(q, "_liquidity_reviews", lambda: {
        ("X", "2025Q1", "unconsolidated", "lcr_total"): 10000,
    })
    reviewed = []
    assert q._liquidity_outliers(c, reviewed=reviewed) == []
    assert len(reviewed) == 1 and "matches source" in reviewed[0]
    c.execute("UPDATE bank_audit_liquidity SET lcr_total=10001 WHERE period='2025Q1'")
    assert len(q._liquidity_outliers(c)) == 1
    c.execute("UPDATE bank_audit_liquidity SET lcr_total=10000, period='2025Q2' WHERE period='2025Q1'")
    assert len(q._liquidity_outliers(c)) == 1


def test_review_never_bypasses_liquidity_validation(monkeypatch):
    c = _conn()
    _ins_liquidity(c, bank_ticker="X", period="2025Q1", kind="unconsolidated",
                   period_type="current", lcr_total=10)
    monkeypatch.setattr(q, "_liquidity_reviews", lambda: {
        ("X", "2025Q1", "unconsolidated", "lcr_total"): 10,
    })
    assert q._liquidity_bands(c)


def test_source_reviewed_nsfr_exemption_does_not_hide_other_failures():
    c = _conn()
    _ins_liquidity(c, bank_ticker="TAKAS", period="2024Q1", kind="unconsolidated",
                   period_type="current", nsfr=44.15, lcr_total=30, leverage_ratio=100)
    reviewed = []
    issues = q._liquidity_bands(c, reviewed=reviewed)
    assert len(issues) == 2
    assert any("LCR" in issue for issue in issues)
    assert any("leverage" in issue for issue in issues)
    assert len(reviewed) == 1 and "NSFR" in reviewed[0]
    c.execute("UPDATE bank_audit_liquidity SET nsfr=44.16")
    assert len(q._liquidity_bands(c)) == 3
    c.execute("UPDATE bank_audit_liquidity SET nsfr=44.15,kind='consolidated'")
    assert len(q._liquidity_bands(c)) == 3


def test_nsfr_review_requires_disclosure_evidence(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    data = {"liquidity_low_nsfr": [{"bank_ticker": "TAKAS", "period": "2024Q1",
            "kind": "unconsolidated", "source_value": 44.15, "pdf_sha256": "a" * 64,
            "source_page": 41, "source_line": "NSFR 44.15%"}]}
    (tmp_path / "data" / "audit_quality_reviews.json").write_text(json.dumps(data))
    monkeypatch.setattr(q, "REPO", tmp_path)
    assert q._low_nsfr_reviews() == {}


def test_pl_reversal_requires_complete_signed_reconciliation():
    from test_audit_validator import _clean_pl
    c = _conn()
    for period in ("2025Q1", "2025Q2"):
        rows = _clean_pl()
        for order, row in enumerate(rows):
            value = row["amount"]
            if period == "2025Q2":
                value = {"IX.": -40000, "XIII.": 240000, "XVII.": 240000,
                         "XIX.": 210000, "XXV.": 210000}.get(row["hierarchy"], value)
            c.execute("INSERT INTO bank_audit_profit_loss "
                      "(bank_ticker,period,kind,item_order,hierarchy,item_name,amount) "
                      "VALUES ('X',?,'consolidated',?,?,?,?)",
                      (period, order, row["hierarchy"], row["item_name"], value))
    reviewed = []
    assert q._pl_sign_convention(c, reviewed=reviewed) == []
    assert len(reviewed) == 1 and "preserve reversals" in reviewed[0]
    c.execute("UPDATE bank_audit_profit_loss SET amount=-50000 "
              "WHERE hierarchy='IX.' AND period='2025Q2'")
    assert len(q._pl_sign_convention(c)) == 1
    c.execute("DELETE FROM bank_audit_profit_loss WHERE hierarchy='XIII.'")
    assert len(q._pl_sign_convention(c)) == 1


def test_pl_compressed_operating_profit_is_not_a_deduction_flip():
    from test_audit_validator import _compressed_pl
    c = _conn()
    for period in ("2025Q1", "2025Q2"):
        for order, row in enumerate(_compressed_pl()):
            value = row["amount"]
            if period == "2025Q2" and row["hierarchy"] == "XII.":
                value = -value
            c.execute("INSERT INTO bank_audit_profit_loss "
                      "(bank_ticker,period,kind,item_order,hierarchy,item_name,amount) "
                      "VALUES ('X',?,'consolidated',?,?,?,?)",
                      (period, order, row["hierarchy"], row["item_name"], value))
    assert q._pl_sign_convention(c) == []
    # A high CAR without supporting components must still require review.
    _ins_capital(c, bank_ticker="BAD", period="2023Q4", kind="unconsolidated",
                 period_type="current", capital_adequacy_ratio=138.08)
    assert any("BAD" in x for x in q._capital_consistency(c))


def test_empty_scan_alerts_resolution_and_clears_baseline(tmp_path, monkeypatch):
    db = tmp_path / "audit.db"
    db.touch()
    sent, saved = [], []
    monkeypatch.setattr(q.sys, "argv", ["quality", "--db", str(db), "--alert"])
    monkeypatch.setattr(q, "check", lambda _, **kwargs: [])
    monkeypatch.setattr(q, "_load_baseline", lambda: {"old warning"})
    monkeypatch.setattr(q, "_notify", sent.append)
    monkeypatch.setattr(q, "_save_baseline", saved.append)
    assert q.main() == 0
    assert sent == ["✅ 1 audit anomaly(ies) resolved; 0 remain"]
    assert saved == [set()]


def test_checks_skip_when_tables_absent():
    # A freshly-seeded DB without the §4 tables must not raise.
    c = sqlite3.connect(":memory:")
    assert q._capital_consistency(c) == []
    assert q._liquidity_bands(c) == []


def _ins_bs(c, bank, period, rows, kind="unconsolidated", statement="assets"):
    """rows = list of (item_name, amount_total); item_order auto-assigned."""
    start = c.execute(
        "SELECT COALESCE(MAX(item_order),0) FROM bank_audit_balance_sheet "
        "WHERE bank_ticker=? AND period=? AND kind=? AND statement=?",
        (bank, period, kind, statement)).fetchone()[0]
    for i, (name, amt) in enumerate(rows, start + 1):
        c.execute(
            "INSERT INTO bank_audit_balance_sheet (bank_ticker, period, kind, "
            "statement, item_order, item_name, amount_total) VALUES (?,?,?,?,?,?,?)",
            (bank, period, kind, statement, i, name, amt))
    c.commit()


def _big_bank_quarter(c, bank, period, ecl_rows):
    """A large-bank quarter: enough asset rows + a grand total + the ECL rows."""
    filler = [(f"Line {i}", 1_000_000) for i in range(20)]
    _ins_bs(c, bank, period, filler + [("TOTAL ASSETS", 500_000_000)] + ecl_rows)


def test_ecl_clean_passes():
    c = _conn()
    _big_bank_quarter(c, "A", "2025Q4", [("Expected Credit Losses (-) (6)", 6_057_750)])
    _big_bank_quarter(c, "A", "2026Q1", [("Expected Credit Losses (-) (6)", 6_540_511)])
    assert q._ecl_sanity(c) == []


def test_ecl_flags_truncated_negative_and_tiny():
    c = _conn()
    _big_bank_quarter(c, "B", "2025Q4", [("ExpectedCreditLosses(", -6)])
    _big_bank_quarter(c, "C", "2025Q4", [("Expected Credit Losses (", 63)])
    issues = q._ecl_sanity(c)
    assert any("B 2025Q4" in i and "truncated" in i for i in issues)
    assert any("C 2025Q4" in i and "truncated" in i for i in issues)
    # a partition whose LARGEST |ECL| is tiny also flags (covers the -6 class)
    _big_bank_quarter(c, "D", "2025Q4", [("Expected Credit Losses (-)", -6)])
    _big_bank_quarter(c, "E", "2025Q4", [("Beklenen Zarar Karşılıkları (-)", 41)])
    issues = q._ecl_sanity(c)
    assert any("D 2025Q4" in i and "largest ECL" in i for i in issues)
    assert any("E 2025Q4" in i and "largest ECL" in i for i in issues)


def test_ecl_paren_negative_value_not_flagged():
    c = _conn()
    # ING/KLNMA-style: the bank prints the value itself in parens → a large
    # negative ECL is the faithful reading, not a parse error.
    _big_bank_quarter(c, "N", "2025Q4", [("Beklenen zarar karşılıkları (-) (I-5)", -2_034_323)])
    assert q._ecl_sanity(c) == []


def test_ecl_tiny_cash_row_next_to_healthy_section_ecl_not_flagged():
    c = _conn()
    # BURGAN-style: cash-section 1.1.4 ECL is genuinely 77 while the section
    # ECL is healthy — must not alarm every cron.
    _big_bank_quarter(c, "G", "2024Q1", [("Expected Credit Losses (-)", 77),
                                         ("Expected Credit Losses (-) I-e-f", 838_394)])
    assert q._ecl_sanity(c) == []


def test_ecl_small_bank_tiny_not_flagged():
    c = _conn()
    # A small bank (total assets below the gate) may legitimately carry tiny ECL.
    _ins_bs(c, "S", "2025Q4",
            [(f"Line {i}", 1_000) for i in range(20)]
            + [("TOTAL ASSETS", 80_000), ("Expected Credit Losses (-)", 12)])
    assert q._ecl_sanity(c) == []


def test_ecl_flags_vanished_rows():
    c = _conn()
    _big_bank_quarter(c, "F", "2025Q4", [("Expected Credit Losses (-) (6)", 6_000_000)])
    _big_bank_quarter(c, "F", "2026Q1", [])  # rows dropped by the parser
    issues = q._ecl_sanity(c)
    assert any("F 2026Q1" in i and "missing" in i for i in issues)


def _tomk_legacy_ecl_quarters(c):
    _big_bank_quarter(c, "TOMK", "2024Q1", [("Beklenen Zarar Karşılıkları (-)", 0)])
    _big_bank_quarter(c, "TOMK", "2024Q2", [("Özel Karşılıklar (-)", 0)])
    _ins_bs(c, "TOMK", "2024Q2", [("Genel Karşılıklar", 26538)], statement="liabilities")
    c.execute("UPDATE bank_audit_balance_sheet SET hierarchy='2.5' "
              "WHERE item_name='Özel Karşılıklar (-)'")
    c.execute("UPDATE bank_audit_balance_sheet SET hierarchy='8.1' "
              "WHERE item_name='Genel Karşılıklar'")


def test_ecl_reviewed_legacy_basis_requires_both_source_disclosures():
    # TOMK Q2 explicitly adopts general/specific provision rules (policy PDF p20),
    # replacing Q1's ECL label. Specific provisions are a printed nil, not an ECL.
    c = _conn()
    _tomk_legacy_ecl_quarters(c)
    changes = c.total_changes
    reviewed = []
    assert q._ecl_sanity(c, reviewed=reviewed) == []
    assert len(reviewed) == 1 and "PDF p20" in reviewed[0]
    assert "ECL remains null" in reviewed[0]
    assert c.total_changes == changes
    assert c.execute("SELECT COUNT(*) FROM bank_audit_balance_sheet "
                     "WHERE period='2024Q2' AND item_name LIKE 'Beklenen%'").fetchone()[0] == 0


@pytest.mark.parametrize("change", [
    "DELETE FROM bank_audit_balance_sheet WHERE hierarchy='2.5'",
    "DELETE FROM bank_audit_balance_sheet WHERE hierarchy='8.1'",
    "UPDATE bank_audit_balance_sheet SET amount_total=NULL WHERE hierarchy='2.5'",
    "UPDATE bank_audit_balance_sheet SET amount_total=1 WHERE hierarchy='2.5'",
    "UPDATE bank_audit_balance_sheet SET amount_total=26539 WHERE hierarchy='8.1'",
    "UPDATE bank_audit_balance_sheet SET statement='assets', item_order=999 WHERE hierarchy='8.1'",
    "UPDATE bank_audit_balance_sheet SET kind='consolidated'",
])
def test_ecl_legacy_basis_missing_changed_or_other_kind_still_alerts(change):
    c = _conn()
    _tomk_legacy_ecl_quarters(c)
    c.execute(change)
    reviewed = []
    assert any("missing" in issue for issue in q._ecl_sanity(c, reviewed=reviewed))
    assert reviewed == []


def test_ecl_legacy_labels_without_reviewed_policy_still_alert(monkeypatch):
    c = _conn()
    _tomk_legacy_ecl_quarters(c)
    monkeypatch.setattr(q, "_ecl_basis_reviews", dict)
    assert any("missing" in issue for issue in q._ecl_sanity(c))


@pytest.mark.parametrize("field,value", [("pdf_sha256", "invalid"), ("source_page", 0),
                                         ("policy_summary", "")])
def test_ecl_basis_review_requires_source_evidence(tmp_path, monkeypatch, field, value):
    data = json.loads((q.REPO / "data" / "audit_quality_reviews.json").read_text(encoding="utf-8"))
    data["ecl_basis"][0][field] = value
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "audit_quality_reviews.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(q, "REPO", tmp_path)
    c = _conn()
    _tomk_legacy_ecl_quarters(c)
    assert any("missing" in issue for issue in q._ecl_sanity(c))


# --- delta-alert fingerprint ------------------------------------------------

def test_fingerprint_ignores_value_nudges():
    # Same partition + check, only the numbers differ → same fingerprint, so a
    # value drift never reads as a new anomaly.
    a = "structure AKBNK 2022Q4 consolidated: assets — 2 identity check(s) failed (59 passed)"
    b = "structure AKBNK 2022Q4 consolidated: assets — 3 identity check(s) failed (58 passed)"
    assert q._fingerprint(a) == q._fingerprint(b)
    e = "capital   ATBANK 2024Q1 unconsolidated: CAR 18.92% != capital/RWA 17.35%"
    f = "capital   ATBANK 2024Q1 unconsolidated: CAR 18.90% != capital/RWA 17.30%"
    assert q._fingerprint(e) == q._fingerprint(f)


def test_fingerprint_distinguishes_identity():
    base = "structure AKBNK 2022Q4 consolidated: assets — 2 identity check(s) failed (59 passed)"
    other_kind = "structure AKBNK 2022Q4 unconsolidated: assets — 2 identity check(s) failed (59 passed)"
    other_stmt = "structure AKBNK 2022Q4 consolidated: equity_change — 4 identity check(s) failed (35 passed)"
    other_period = "structure AKBNK 2026Q1 consolidated: assets — 2 identity check(s) failed (59 passed)"
    fps = {q._fingerprint(x) for x in (base, other_kind, other_stmt, other_period)}
    assert len(fps) == 4  # period lives in the (non-stripped) head, so it's preserved


# --- Free provision (serbest karşılık) checks -----------------------------

def _ins_freeprov(c, bank, period, kind="unconsolidated", fp=None, prior=None):
    c.execute("INSERT INTO bank_audit_free_provision "
              "(bank_ticker, period, kind, free_provision, free_provision_prior) "
              "VALUES (?,?,?,?,?)", (bank, period, kind, fp, prior))
    c.commit()


def _ins_opinion(c, bank, period, kind="unconsolidated", is_modified=1, basis=""):
    c.execute("INSERT INTO bank_audit_opinion "
              "(bank_ticker, period, kind, opinion_type, is_modified, basis_text) "
              "VALUES (?,?,?,?,?,?)",
              (bank, period, kind, "qualified" if is_modified else "clean", is_modified, basis))
    c.commit()


def test_freeprov_clean_passes():
    c = _conn()
    # Consistent chain: 2024Q4 stock = 300, and 2025Q1 states its prior as 300.
    _ins_freeprov(c, "X", "2024Q4", fp=300)
    _ins_freeprov(c, "X", "2025Q1", fp=250, prior=300)
    assert q._free_provision(c) == []


def test_freeprov_band_flags_absurd_value():
    c = _conn()
    _ins_freeprov(c, "X", "2025Q1", fp=999_000_000)  # > ceiling
    assert any("out of plausible band" in i for i in q._free_provision(c))


def test_freeprov_prior_chain_break():
    c = _conn()
    # 2024Q4 captured as 38 (a sub-component), but 2025Q1 states prior = 1_314 —
    # the BURGAN fingerprint: one side mis-extracted.
    _ins_freeprov(c, "BURGAN", "2024Q4", fp=38)
    _ins_freeprov(c, "BURGAN", "2025Q1", fp=1_300, prior=1_314)
    assert any("prior-year-end current" in i for i in q._free_provision(c))


def test_freeprov_recall_gap_when_qualified_but_no_row():
    c = _conn()
    _ins_opinion(c, "DENIZ", "2023Q1", is_modified=1,
                 basis="... serbest karşılık ...")  # qualified over a free provision
    # no bank_audit_free_provision row for DENIZ 2023Q1
    assert any("none was extracted" in i for i in q._free_provision(c))


def test_freeprov_recall_not_flagged_when_zero_row_present():
    c = _conn()
    _ins_opinion(c, "DENIZ", "2023Q1", is_modified=1, basis="... serbest karşılık ...")
    _ins_freeprov(c, "DENIZ", "2023Q1", fp=0)  # captured as explicit none — not a gap
    assert not any("none was extracted" in i for i in q._free_provision(c))


def test_freeprov_precision_value_under_clean_opinion():
    c = _conn()
    _ins_opinion(c, "AKBNK", "2024Q4", is_modified=0)  # clean
    _ins_freeprov(c, "AKBNK", "2024Q4", fp=1_400)      # a value the auditor didn't qualify over
    assert any("under a\nCLEAN opinion".replace("\n", " ") in i.replace("\n", " ")
               for i in q._free_provision(c))
