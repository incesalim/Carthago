"""Offline tests for the KAP ownership lane (no network)."""
from __future__ import annotations

import json
import sqlite3

from src.kap.client import decode_flight, item_objects
from src.kap.loader import replace_bank_rows
from src.kap.parser import ownership_rows, parse_as_of, parse_tr_number
from src.kap.schema import init_schema

# --- fixtures ---------------------------------------------------------------

_DIRECT = {
    "itemKey": "kpy41_acc5_sermayede_dogrudan",
    "creationDate": "01/08/2020",
    "value": [
        {"shareholder": "HACI ÖMER SABANCI HOLDİNG ANONİM ŞİRKETİ",
         "shareInCapital": "2.119.027.173,7", "ratioInCapital": "40,75",
         "votingRightRatio": "40,75"},
        {"shareholder": "DİĞER", "shareInCapital": "3.080.972.826,3",
         "ratioInCapital": "59,25", "votingRightRatio": "59,25"},
        {"shareholder": "TOPLAM", "shareInCapital": "5.200.000.000",
         "ratioInCapital": "100", "votingRightRatio": "100"},
    ],
}
_FREE_FLOAT = {
    "itemKey": "kpy41_acc5_fiili_dolasimdaki_pay",
    "creationDate": "10/06/2026",
    "value": [
        {"isin": "AKBNK", "actualSharesOutstanding": "2.795.935.346,88",
         "actualOutstandingSharesRatio": "53,77", "creationDate": "20260610"},
    ],
}
_PAID_IN = {"itemKey": "kpy41_acc5_odenmis_sermaye", "value": "5.200.000.000"}
_SUBS = {
    "itemKey": "kpy41_acc7_bagli_ortakliklar",
    "creationDate": "21/05/2026 16:49:19",
    "value": [
        {"companyTitle": "AKBANK AG", "scopeOfActivitiesOfCompany": "BANKACILIK",
         "taxNo": "4722007023", "leiCode": "   529900P90XJRYLOJNP77",
         "paidInOrIssuedCapital": "320000000", "capitalShareOfCompany": "320000000",
         "monetaryUnit": {"key": "EUR", "text": "EUR"},
         "ratioOfCapitalShareOfCompany": "100",
         "relationWithTheCompany": "BAĞLI ORTAKLIK"},
        {"companyTitle": "ARAP-TÜRK BANKASI A.Ş.",
         "scopeOfActivitiesOfCompany": "Bankacılık",
         "paidInOrIssuedCapital": "3221000000,00",
         "capitalShareOfCompany": "662748519,40",
         "monetaryUnit": {"key": "TRY", "text": "TRY"},
         "ratioOfCapitalShareOfCompany": "20,58",
         "relationWithTheCompany": "İştirak"},
    ],
}

# Non-listed variant (Ziraat-style): grid under ortaklik_yapisi, scalar
# under odenmis_sermaye_2, null ceiling.
_VARIANT_ITEMS = {
    "kpy41_acc5_ortaklik_yapisi": {
        "itemKey": "kpy41_acc5_ortaklik_yapisi",
        "creationDate": "22/09/2017 19:38:26",
        "value": [
            {"shareholder": "Türkiye Varlık Fonu", "shareInCapital": "100",
             "ratioInCapital": "100"},
            {"shareholder": "TOPLAM", "shareInCapital": "100",
             "ratioInCapital": "100"},
        ],
    },
    "kpy41_acc5_odenmis_sermaye_2": {
        "itemKey": "kpy41_acc5_odenmis_sermaye_2",
        "creationDate": "28/04/2023 17:42:04",
        "value": "84600000000",
    },
    "kpy41_acc5_kayitli_sermaye_tavani_2": {
        "itemKey": "kpy41_acc5_kayitli_sermaye_tavani_2",
        "value": None,
    },
}


def _flight_html(*objs: dict) -> str:
    """Embed itemObjects in a minimal Next.js flight-payload page."""
    payload = ",".join('["$","$L29",null,{"itemObject":' +
                       json.dumps(o, ensure_ascii=False) + "}]" for o in objs)
    escaped = json.dumps(payload)  # JS string literal, quotes escaped
    return ("<html><body><script>self.__next_f.push([1," + escaped +
            "])</script></body></html>")


# --- number / date parsing ---------------------------------------------------

def test_parse_tr_number():
    assert parse_tr_number("2.119.027.173,7") == 2119027173.7
    assert parse_tr_number("294493196,25") == 294493196.25
    assert parse_tr_number("100") == 100.0
    assert parse_tr_number("84600000000") == 84600000000.0
    assert parse_tr_number("53,77") == 53.77
    assert parse_tr_number("-") is None
    assert parse_tr_number("") is None
    assert parse_tr_number(None) is None


def test_parse_as_of():
    assert parse_as_of("01/08/2020") == "2020-08-01"
    assert parse_as_of("17/06/2016 16:36:29") == "2016-06-17"
    assert parse_as_of("20260610") == "2026-06-10"
    assert parse_as_of(None) is None
    assert parse_as_of("garbage") is None


# --- flight decode -----------------------------------------------------------

def test_decode_flight_and_item_objects():
    html = _flight_html(_DIRECT, _FREE_FLOAT, _PAID_IN)
    items = item_objects(decode_flight(html))
    assert set(items) == {
        "kpy41_acc5_sermayede_dogrudan",
        "kpy41_acc5_fiili_dolasimdaki_pay",
        "kpy41_acc5_odenmis_sermaye",
    }
    holders = items["kpy41_acc5_sermayede_dogrudan"]["value"]
    assert holders[0]["shareholder"].startswith("HACI ÖMER SABANCI")


def test_item_objects_first_occurrence_wins():
    dup = dict(_PAID_IN, value="999")
    html = _flight_html(_PAID_IN, dup)
    items = item_objects(decode_flight(html))
    assert items["kpy41_acc5_odenmis_sermaye"]["value"] == "5.200.000.000"


# --- ownership rows ----------------------------------------------------------

def test_ownership_rows_listed_bank():
    items = {o["itemKey"]: o for o in (_DIRECT, _FREE_FLOAT, _PAID_IN)}
    rows = ownership_rows("AKBNK", "AKBANK T.A.Ş.", 2413, items)
    by_item = {}
    for r in rows:
        by_item.setdefault(r.item, []).append(r)

    sh = by_item["shareholder"]
    assert [r.seq for r in sh] == [0, 1, 2]
    assert sh[0].ratio_pct == 40.75 and sh[0].voting_pct == 40.75
    assert sh[2].holder == "TOPLAM" and sh[2].share_tl == 5_200_000_000
    assert sh[0].as_of == "2020-08-01"

    ff = by_item["free_float"][0]
    assert ff.holder == "AKBNK" and ff.ratio_pct == 53.77
    assert ff.as_of == "2026-06-10"  # row-level YYYYMMDD wins

    assert by_item["paid_in_capital"][0].share_tl == 5_200_000_000


def test_ownership_rows_nonlisted_variant():
    rows = ownership_rows("ZIRAAT", "T.C. ZİRAAT BANKASI A.Ş.", 2419, _VARIANT_ITEMS)
    by_item = {}
    for r in rows:
        by_item.setdefault(r.item, []).append(r)
    assert by_item["shareholder"][0].holder == "Türkiye Varlık Fonu"
    assert by_item["shareholder"][0].ratio_pct == 100.0
    assert by_item["paid_in_capital"][0].share_tl == 84_600_000_000
    assert "capital_ceiling" not in by_item  # null value → no row


def test_ownership_rows_subsidiaries():
    rows = ownership_rows("AKBNK", "AKBANK T.A.Ş.", 2413,
                          {o["itemKey"]: o for o in (_SUBS,)})
    assert [r.item for r in rows] == ["subsidiary", "subsidiary"]
    ag, atb = rows
    assert ag.holder == "AKBANK AG"
    assert ag.share_tl == 320_000_000 and ag.currency == "EUR"
    assert ag.ratio_pct == 100.0 and ag.relation == "BAĞLI ORTAKLIK"
    assert ag.activity == "BANKACILIK"
    assert ag.as_of == "2026-05-21"
    assert atb.share_tl == 662748519.40 and atb.currency == "TRY"
    assert atb.ratio_pct == 20.58 and atb.relation == "İştirak"


def test_ownership_rows_empty_items():
    assert ownership_rows("ATBANK", "ARAP TÜRK BANKASI A.Ş.", 2030, {}) == []


# --- loader replace semantics -------------------------------------------------

def test_replace_bank_rows_reports_shrink():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    items = {o["itemKey"]: o for o in (_DIRECT, _PAID_IN)}
    rows = ownership_rows("AKBNK", "AKBANK T.A.Ş.", 2413, items)
    n, removed = replace_bank_rows(conn, "AKBNK", rows)
    assert n == 4 and removed == []

    # Shrink the grid: TOPLAM-only refile → seq 1..2 must be reported stale.
    shrunk = ownership_rows(
        "AKBNK", "AKBANK T.A.Ş.", 2413,
        {"kpy41_acc5_sermayede_dogrudan": dict(_DIRECT, value=_DIRECT["value"][:1])},
    )
    n, removed = replace_bank_rows(conn, "AKBNK", shrunk)
    assert n == 1
    assert ("AKBNK", "paid_in_capital", 0) in removed
    assert ("AKBNK", "shareholder", 1) in removed
    assert ("AKBNK", "shareholder", 2) in removed
    left = conn.execute("SELECT COUNT(*) FROM kap_ownership").fetchone()[0]
    assert left == 1
