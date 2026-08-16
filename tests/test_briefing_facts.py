"""The regulation-briefing fact checklist (src/news/briefing_facts.py).

The fixtures are the LIVE production briefing of 2026-08-16 — the one the
after-the-fact checker scored 69% while the alert went to Telegram and the
page shipped anyway. Of its four flagged facts, two were checker bugs
(`\\bSME\\b` cannot match "SMEs"; a bare `FX` keyword read an RR bullet's
"up to 1 month" as a superseded FX-loan cap) and two were real briefing
defects (January's overdraft cap printed beside May's; the repo-auction
suspension absent). These tests pin all four classifications and the gate
helpers the generator now repairs with.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.news.briefing_facts import (  # noqa: E402
    FACTS,
    _num_present,
    retry_addendum,
    score,
    section_missing_facts,
    stale_bare_indexes,
)

# --- the 2026-08-16 production briefing, verbatim --------------------------

LOAN_BULLETS = [
    "The eight-week growth limit for general-purpose loans extended to consumers is 3%, down from 4%.",
    "The eight-week growth limit for vehicle loans extended to consumers is 3%, down from 4%.",
    "The eight-week growth limit for overdraft account limits extended to consumers is 1%, down from 2%.",
    "The eight-week growth limit for Turkish lira loans extended to SMEs is 4.5%, down from 5%.",
    "The eight-week growth limit for Turkish lira loans extended to non-SME enterprises is 2%, down from 3%.",
    "The eight-week growth limit for foreign currency loans is 0.5%.",
    # The real defect: January's introduction printed beside May's revision.
    "An eight-week growth limit of 2% has been introduced for overdraft account limits allocated to consumers.",
]

MPC_BULLETS = [
    "The one-week repo auction rate, the main policy instrument, is 37 percent.",
    "The interest-rate corridor is set with an overnight lending rate at 40 percent and an overnight borrowing rate at 35.5 percent.",
    "At the latest Monetary Policy Committee meeting, the policy rate was kept unchanged, indicating a neutral stance.",
    "The Central Bank of the Republic of Türkiye may conduct location swap transactions with banks depending on market conditions.",
    "The CBRT will continue to provide banks with FX liquidity at one-week and one-month maturities at the CBRT FX Deposit Market, with a limit of approximately USD 50 billion in total.",
]

RR_BULLETS = [
    "The reserve requirement ratio for foreign currency deposits/participation funds has been revised to 32% for demand deposits and deposits with maturities up to 1 month, and 28% for deposits with longer maturities.",
    "The additional Turkish lira reserve requirement ratio for FX deposits/participation funds, which was introduced in 2023 and applied at 2.5%, has been terminated.",
    "The reserve requirement ratios for Turkish lira-denominated funds from repo transactions abroad and loans obtained from abroad have been raised to 20% for maturities up to one month, 16% for maturities up to three months, and 14% for maturities up to one year.",
    "The reserve requirement ratios for deposits/participation funds from banks abroad and liabilities to the head office abroad with maturities up to one year have been raised to 14%.",
]

DEP_BULLETS = [
    "The growth target for the share of Turkish lira deposits of legal persons is reintroduced.",
    "The growth targets for the share of Turkish lira deposits of real persons were increased.",
]

OTHER_BULLETS = [
    "The CBRT has completed the evaluation process for the Call to Join the Digital Turkish Lira Project Ecosystem.",
]


def _payload(loan=None, mpc=None):
    def cat(name, texts):
        return {"name": name, "bullets": [{"text": t, "source_ids": []} for t in texts]}
    return {"categories": [
        cat("Monetary Policy Stance", mpc if mpc is not None else MPC_BULLETS),
        cat("Regulations for TL Deposit Share", DEP_BULLETS),
        cat("Loan Growth Caps", loan if loan is not None else LOAN_BULLETS),
        cat("Regulations on RRs", RR_BULLETS),
        cat("Other Regulatory Actions", OTHER_BULLETS),
    ]}


def _verdict(res: dict, fact_id: str) -> str:
    return next(r["verdict"] for r in res["results"] if r["id"] == fact_id)


def test_live_2026_08_16_briefing_scores_11_of_13():
    """The two real defects flagged, the two checker false verdicts gone."""
    res = score(_payload())
    # Real defects — must stay flagged:
    assert _verdict(res, "loan_overdraft") == "CONTRADICTED"
    assert _verdict(res, "repo_suspended") == "MISSING"
    # Checker bugs of 2026-08-16 — must be fixed:
    assert _verdict(res, "loan_sme") == "PASS", "\\bSMEs?\\b must match the plural"
    assert _verdict(res, "loan_fx") == "PASS", \
        "an RR bullet's 'up to 1 month' must not read as a superseded FX-loan cap"
    assert res["counts"]["PASS"] == 11
    assert res["counts"]["CONTRADICTED"] == 1
    assert res["counts"]["MISSING"] == 1


def test_repaired_briefing_scores_13_of_13():
    loan = [b for b in LOAN_BULLETS if "has been introduced" not in b]
    mpc = MPC_BULLETS + [
        "One-week repo auctions remain suspended; funding is provided at the overnight lending rate.",
    ]
    res = score(_payload(loan=loan, mpc=mpc))
    assert res["score"] == 1.0, res["results"]


def test_stale_bare_indexes_finds_exactly_the_january_overdraft_bullet():
    bullets = [{"text": t} for t in LOAN_BULLETS]
    assert stale_bare_indexes(bullets) == [6]
    # Transition bullets carry both values and are never strippable.
    assert stale_bare_indexes([{"text": LOAN_BULLETS[2]}]) == []
    # The other sections hold nothing strippable.
    assert stale_bare_indexes([{"text": t} for t in MPC_BULLETS + RR_BULLETS]) == []


def test_section_missing_facts_names_the_repo_suspension():
    missing = section_missing_facts("Monetary Policy Stance",
                                    [{"text": t} for t in MPC_BULLETS])
    assert [f["id"] for f in missing] == ["repo_suspended"]
    healed = MPC_BULLETS + ["One-week repo auctions remain halted."]
    assert section_missing_facts("Monetary Policy Stance",
                                 [{"text": t} for t in healed]) == []


def test_suspension_accepts_the_ways_it_is_actually_worded():
    for phrasing in ("suspended", "halted", "paused", "will not be conducted",
                     "are no longer held", "ceased"):
        bullets = [{"text": f"One-week repo auctions {phrasing}."}]
        missing = {f["id"] for f in
                   section_missing_facts("Monetary Policy Stance", bullets)}
        assert "repo_suspended" not in missing, phrasing


def test_retry_addendum_names_the_rule_but_never_the_value():
    """The repair hint must not leak the answer, or the checklist stops
    measuring extraction and starts measuring echo."""
    for f in FACTS:
        text = retry_addendum([f])
        assert f["hint"] in text
        if f["value"] is not None:
            assert not _num_present(text, f["value"]), \
                f"{f['id']}: hint leaks the current value {f['value']}"


def test_missing_section_detection_survives_the_refactor():
    payload = _payload()
    payload["categories"] = [c for c in payload["categories"]
                             if c["name"] != "Regulations for TL Deposit Share"]
    res = score(payload)
    assert res["missing_sections"] == ["Regulations for TL Deposit Share"]
