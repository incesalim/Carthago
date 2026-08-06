"""Why the broad classifier change was reverted, and what replaced it.

TEB 2026Q1 stored `free_provision = 0` while cons p74 / unco p71 state
1,108,135 TL. The classifier had read a SEPARATE reversal note on a later page
whose parenthetical said "(31 Mart 2025: Bulunmamaktadır)".

Three parser fixes were built for it — Turkish `k`→`ğ` softening in the subject,
an amount-before-subject pattern tolerating the prior-period parenthetical, and
a genitive/direct distinction so "X serbest karşılığın Y kısmı iptal edildi"
could not read X as the balance. All three worked on their target sentences.

The full-corpus run (1,061 PDFs, read-only, Actions) rejected them anyway:
37 partitions moved and 11 carried a value the filing does not support. Page
selection turns out to be corpus-wide in a way three sentence shapes cannot
bound, so the change was reverted and only the partitions verified against their
own source passage are encoded as overrides.

Kept here as the record of what was measured, because the next person to widen
`_SUBJ_TR` needs to know it has been tried.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.free_provision import (  # noqa: E402
    _override_for, _SUBJ_TR, upsert_free_provision,
)
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.units import UnitContext  # noqa: E402


# --- the classifier is back to its measured-good state -----------------------

def test_the_subject_pattern_is_not_widened():
    """`serbest karşılı[kğ]` moved 37 partitions, 11 of them wrong. If this is
    widened again, re-run measure-free-provision.yml FIRST — the movers were
    ALNTF (a reversed provision read as a stock), ICBCT 2022Q4 unconsolidated
    (a malformed parenthetical read as 'none' where the same sentence states
    7,015), and ZIRAATK 2025Q1–Q4 (a prior of 500,000 that belongs to 2023)."""
    assert _SUBJ_TR == r"serbest\s+kar[şs][ıi]l[ıi]k"


# --- what the overrides must produce -----------------------------------------

@pytest.mark.parametrize("bank,period,kind,stock,prior", [
    # Cancelled in FULL -> the stock is 0 and the named amount is the prior.
    # p78: "tamamı geçmiş yıllarda ayrılan 500.000 TL tutarında serbest karşılık
    # cari dönemde iptal edilmiştir". Stored 0 was right, but sourced from an
    # unrelated sentence's prior-period "Bulunmamaktadır".
    ("ZIRAATK", "2024Q1", "consolidated", 0, 500_000),
    ("ZIRAATK", "2024Q1", "unconsolidated", 0, 500_000),
    # p74/p71: "1,108,135 TL (31 Aralık 2025: 1,230,000 TL) tutarında serbest
    # karşılığı içermektedir."
    ("TEB", "2026Q1", "consolidated", 1_108_135, 1_230_000),
    ("TEB", "2026Q1", "unconsolidated", 1_108_135, 1_230_000),
    # Milyon filing: 368 and 1,230 on the page, canonical bin in the row.
    ("TEB", "2026Q2", "consolidated", 368_000, 1_230_000),
    ("TEB", "2026Q2", "unconsolidated", 368_000, 1_230_000),
])
def test_the_curated_partitions_store_their_verified_values(
        tmp_path, bank, period, kind, stock, prior):
    """End to end through the real override file and the real writer."""
    fp = _override_for(bank, period, kind)
    assert fp is not None, f"{bank} {period} {kind} override missing"
    conn = sqlite3.connect(tmp_path / f"{bank}{period}{kind}.db")
    init_schema(conn)
    # The FILING's context — Milyon for 2026Q2, Bin before it. A manual entry
    # carries its own unit, so neither may be scaled twice.
    filing = UnitContext("milyon", 1_000) if period == "2026Q2" \
        else UnitContext("bin", 1)
    upsert_free_provision(conn, bank, period, kind, fp, unit=filing)
    assert conn.execute(
        "SELECT free_provision, free_provision_prior "
        "FROM bank_audit_free_provision").fetchone() == (stock, prior)


def test_the_teb_chain_reconciles_across_three_quarters():
    """2025Q4 stock, less each period's reversal, equals the next stock. The
    arithmetic is why these four figures are trusted without a parser."""
    q4_2025 = 1_230_000
    assert q4_2025 - 121_865 == 1_108_135          # Q1 reversal -> 2026Q1
    assert q4_2025 - 862_000 == 368_000            # H1 reversal -> 2026Q2


def test_every_override_declaring_a_post_horizon_period_names_its_unit():
    """A 2026Q2+ entry that forgets `unit` stores 1000x small, and no in-filing
    identity can see it."""
    raw = json.loads(
        (REPO / "data" / "free_provision_overrides.json").read_text(encoding="utf-8"))
    for bank, periods in raw.items():
        if bank.startswith("_"):
            continue
        for period, kinds in periods.items():
            for kind, entry in kinds.items():
                if period > "2026Q1":
                    assert "unit" in entry, f"{bank} {period} {kind}"


def test_the_curated_set_is_exactly_what_the_corpus_run_verified():
    """Bounded on purpose. 37 partitions moved under the parser change; only
    these were confirmed against their own source passage."""
    raw = json.loads(
        (REPO / "data" / "free_provision_overrides.json").read_text(encoding="utf-8"))
    for bank, period in (("TEB", "2026Q1"), ("TEB", "2026Q2"),
                         ("ZIRAATK", "2024Q1")):
        assert set(raw[bank][period]) == {"consolidated", "unconsolidated"}, \
            f"{bank} {period} must curate both kinds or neither"
