"""The briefing citation gate (src/news/briefing_citations.py).

Fixtures are the real D1 bodies calibrated on 2026-08-16: the Türkiye–Syria
deposit-agreement release (zero percentages) that the live briefing cited for
the policy corridor, the actual Press Release on Interest Rates (prose
"37 percent"), and the macroprudential releases whose figures live in
markdown tables ("| 4% | 3% |") and dash-lists ("reduced to 0.5% from 1%").
The matcher must accept every correct-citation shape and reject the
misattribution that shipped.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.news.briefing_citations import (  # noqa: E402
    audit_citations,
    bullet_current_pcts,
    citation_addendum,
    drop_uncited_figures,
    fetch_feed_items,
    strip_unsupported,
    supports,
)

SYRIA = ("The Central Bank of the Republic of Türkiye and the Central Bank of "
         "Syria have signed an agreement to enable opening of a Turkish lira "
         "deposit account at the Central Bank of the Republic of Türkiye in "
         "the name of the Central Bank of Syria.")

RATES = ("The Monetary Policy Committee (the Committee) has decided to keep "
         "the policy rate (the one-week repo auction rate) at 37 percent. The "
         "Committee has also maintained the Central Bank overnight lending "
         "rate and the overnight borrowing rate at 40 percent and 35.5 "
         "percent, respectively.")

MACRO_TABLE = ("| Growth Limits (For Eight Weeks) | Former Ratio | New Ratio |\n"
               "| General purpose loans extended to consumers | 4% | 3% |\n"
               "| Overdraft account limits extended to consumers | 2% | 1% |\n"
               "| Turkish lira loans extended to SMEs | 5% | 4.5% |")

MACRO_LIST = ("- The eight-week growth limit for foreign currency loans has "
              "been reduced to 0.5% from 1%,\n- An eight-week growth limit of "
              "2% has been introduced for overdraft account limits allocated "
              "to consumers.")

ITEMS = {
    "tcmb:ANO2026-31": {"id": "tcmb:ANO2026-31", "title": "Türkiye and Syria sign agreement", "body": SYRIA},
    "tcmb:ANO2026-28": {"id": "tcmb:ANO2026-28", "title": "Press Release on Interest Rates", "body": RATES},
    "tcmb:ANO2026-21": {"id": "tcmb:ANO2026-21", "title": "Press Release on Macroprudential Framework", "body": MACRO_TABLE},
    "tcmb:ANO2026-06": {"id": "tcmb:ANO2026-06", "title": "Press Release on Macroprudential Framework", "body": MACRO_LIST},
}

CORRIDOR = ("The interest-rate corridor is set with an overnight lending rate "
            "at 40 percent and an overnight borrowing rate at 35.5 percent.")


def _b(text, ids):
    return {"text": text, "source_ids": ids}


def test_current_pcts_exclude_the_bullets_own_transition_values():
    assert bullet_current_pcts(
        "The cap is 1%, down from 2%.") == {"1"}
    assert bullet_current_pcts(
        "The limit is 0.5%, reduced from 1% previously.") == {"0.5"}
    assert bullet_current_pcts("USD 50 billion in FX liquidity.") == set()


def test_the_live_misattribution_is_rejected_and_the_true_source_accepted():
    assert not supports(CORRIDOR, SYRIA)
    assert supports(CORRIDOR, RATES)
    assert supports("The policy rate is 37 percent.", RATES)


def test_table_and_list_bodies_support_their_bullets():
    assert supports("The growth limit for general-purpose loans is 3%, down from 4%.",
                    MACRO_TABLE)
    assert supports("The growth limit for foreign currency loans is 0.5%, reduced from 1%.",
                    MACRO_LIST)
    # 4.5 must not be satisfied by a body containing only 4 and 5.
    assert not supports("TL loans to SMEs are capped at 4.5%.", MACRO_LIST)


def test_strip_keeps_supported_ids_and_reports_dead_bullets():
    bullets = [
        _b(CORRIDOR, ["tcmb:ANO2026-31", "tcmb:ANO2026-28"]),  # one bad, one good
        _b("The policy rate is 37 percent.", ["tcmb:ANO2026-31"]),  # only bad
        _b("A qualitative note with no figures.", ["tcmb:ANO2026-31"]),  # prose
    ]
    out, stripped, dead = strip_unsupported(bullets, ITEMS)
    assert out[0]["source_ids"] == ["tcmb:ANO2026-28"]
    assert out[1]["source_ids"] == []
    assert out[2]["source_ids"] == ["tcmb:ANO2026-31"]  # vacuously supported
    assert len(stripped) == 2
    assert [f["text"] for f in dead] == ["The policy rate is 37 percent."]


def test_hallucinated_ids_are_stripped_as_unknown():
    out, stripped, dead = strip_unsupported(
        [_b("The policy rate is 37 percent.", ["tcmb:ANO9999-99"])], ITEMS)
    assert out[0]["source_ids"] == []
    assert stripped[0]["unknown"] == ["tcmb:ANO9999-99"]
    assert len(dead) == 1


def test_drop_uncited_figures_spares_prose():
    kept, dropped = drop_uncited_figures([
        _b("The policy rate is 37 percent.", []),
        _b("The growth target for TL deposits of legal persons is reintroduced.", []),
        _b(CORRIDOR, ["tcmb:ANO2026-28"]),
    ])
    assert [b["text"] for b in dropped] == ["The policy rate is 37 percent."]
    assert len(kept) == 2


def test_audit_reports_every_class():
    findings = audit_citations(
        [_b(CORRIDOR, ["tcmb:ANO2026-31", "tcmb:ANO2026-28", "tcmb:GHOST"])], ITEMS)
    f = findings[0]
    assert f["unknown"] == ["tcmb:GHOST"]
    assert f["unsupported"] == ["tcmb:ANO2026-31"]
    assert f["supported"] == ["tcmb:ANO2026-28"]


def test_addendum_names_the_bullets_but_suggests_no_id():
    dead = [{"text": CORRIDOR, "unknown": [], "unsupported": ["tcmb:ANO2026-31"],
             "supported": [], "index": 0}]
    text = citation_addendum(dead)
    assert CORRIDOR[:80] in text
    # Repair must not hand the model an id — re-citing is what is measured.
    assert "ANO2026" not in text


def test_fetch_feed_items_shape_survives_the_move():
    conn = sqlite3.connect(":memory:")
    from src.news.schema import init_schema
    init_schema(conn)
    conn.execute(
        "INSERT INTO news_items (source, external_id, published_at, title,"
        " body_text, url, language)"
        " VALUES ('tcmb', 'ANO2026-28', datetime('now', '-2 days'),"
        " 'Press Release on Interest Rates', ?, 'https://tcmb.gov.tr/x', 'en')",
        (RATES,))
    items = fetch_feed_items(conn, 30, 3000)
    assert len(items) == 1
    it = items[0]
    assert it["id"] == "tcmb:ANO2026-28"
    assert set(it) == {"id", "source", "date", "title", "body"}
    assert "37 percent" in it["body"]
