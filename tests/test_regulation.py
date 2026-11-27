"""The regulation lane (2026-11-27): Official Gazette documents and TCMB's
card-rate caps, as dated rows.

The fixtures mirror what the two sources printed when the lane was written: a
Gazette document page (Word-exported HTML, Windows-1254, a fixed header), a
day listing, a BDDK board decision that is a scanned image with no text layer,
and TCMB's card-rate table with its two-level header. No test touches the
network.
"""
import datetime as dt
import re
import sqlite3
from pathlib import Path

import pytest

from scripts import update_regulation
from src.regulation import card_rates as cr
from src.regulation import gazette as gz
from src.regulation.schema import init_schema

ROOT = Path(__file__).resolve().parents[1]


# --- issuer and instrument ---------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("TÜRKİYE CUMHURİYET MERKEZ BANKASI'ndan:", "TCMB"),
    ("Türkiye Cumhuriyet Merkez Bankası'ndan:", "TCMB"),
    ("TÜRKİYE CUMHURİYET MERKEZ BANKASINDAN:", "TCMB"),
    ("BANKACILIK DÜZENLEME VE DENETLEME KURUMU'ndan:", "BDDK"),
    ("Bankacılık Düzenleme ve Denetleme Kurulunun 17/11/2026 Tarihli ve 11601 Sayılı Kararı", "BDDK"),
    ("Çevre, Şehircilik ve İklim Değişikliği Bakanlığından:", None),
    ("Tahsilat Genel Tebliği (Seri:C Sıra No:10)", None),
])
def test_which_institution_a_text_names(text, expected):
    assert gz.classify_issuer(text) == expected


def test_a_regulator_title_that_mentions_the_central_bank_is_the_regulators():
    # A BDDK title can name the central bank; the specific name wins.
    assert gz.classify_issuer("Bankacılık Düzenleme ve Denetleme Kurumu'ndan: Merkez Bankası …") == "BDDK"


def test_an_instrument_is_named_from_a_title_when_there_is_no_text():
    assert gz.instrument_from_title("Bankacılık Düzenleme ve Denetleme Kurulunun … Sayılı Kararı") == "KARAR"
    assert gz.instrument_from_title("Zorunlu Karşılıklar Hakkında Tebliğ") == "TEBLIĞ"
    assert gz.instrument_from_title("Kredi Kartı İşlemlerine İlişkin Genelge") == "GENELGE"
    assert gz.instrument_from_title("Güvence Hesabı Yönetmeliğinde Değişiklik Yapılmasına Dair Yönetmelik") == "YÖNETMELİK"
    assert gz.instrument_from_title("Tahsilat Genel Tebliği (Seri:C Sıra No:10)") == "TEBLIĞ"


# --- a day's listing ---------------------------------------------------------


LISTING_HTML = """
<html><body>
<a href="https://www.resmigazete.gov.tr/eskiler/2026/11/20261127.pdf">PDF Görüntüle</a>
<div><a href="https://www.resmigazete.gov.tr/eskiler/2026/11/20261127-1.pdf">–</a>
  <span>–– Hâkimler ve Savcılar Kurulu Genel Kurulunca Yargıtay Üyeliklerine Seçilenler Hakkında Karar</span></div>
<div><a href="https://www.resmigazete.gov.tr/eskiler/2026/11/20261127-2.htm">––</a>
  <span>–– Korunan Alanların Tespit, Tescil ve Onayuna İlişkin Usul ve Esaslara Dair Yönetmelikte Değişiklik Yapılması Hakkında Yönetmelik</span></div>
<div><a href="https://www.resmigazete.gov.tr/eskiler/2026/11/20261127-6.pdf">––</a>
  <span>–– Bankacılık Düzenleme ve Denetleme Kurulunun 26/11/2026 Tarihli ve 11620 Sayılı Kararı</span></div>
</body></html>
"""
YONETMELIK = ("Korunan Alanların Tespit, Tescil ve Onayuna İlişkin Usul ve Esaslara Dair "
              "Yönetmelikte Değişiklik Yapılması Hakkında Yönetmelik")


def test_a_listing_names_every_document_with_its_title_and_format():
    docs = {d["document_id"]: d for d in gz.parse_listing(LISTING_HTML)}
    assert set(docs) == {"20261127-1", "20261127-2", "20261127-6"}   # the whole issue's PDF is not a document
    assert docs["20261127-1"]["fmt"] == "pdf"
    assert docs["20261127-1"]["title"] == "Hâkimler ve Savcılar Kurulu Genel Kurulunca Yargıtay Üyeliklerine Seçilenler Hakkında Karar"
    assert docs["20261127-2"]["fmt"] == "htm"
    assert docs["20261127-2"]["url"] == "https://www.resmigazete.gov.tr/eskiler/2026/11/20261127-2.htm"
    assert docs["20261127-6"]["title"].startswith("Bankacılık Düzenleme ve Denetleme Kurulunun")


def test_a_document_offered_both_ways_is_read_as_html():
    pdf_too = LISTING_HTML.replace(
        "</body></html>",
        '<div><a href="https://www.resmigazete.gov.tr/eskiler/2026/11/20261127-2.pdf">––</a>'
        f"<span>–– {YONETMELIK}</span></div></body></html>")
    doc = {d["document_id"]: d for d in gz.parse_listing(pdf_too)}["20261127-2"]
    assert doc["fmt"] == "htm"           # smaller, and the only one that has text


# --- a document page with a header ------------------------------------------


def _gazette_page(issuer_line: str, body: str) -> bytes:
    # A "/" in the issuer line splits it over two paragraphs, as the real page
    # does when the issuing body is long.
    paragraphs = [
        "27 Kasım 2026 CUMA", "Resmî Gazete", "Sayı : 33443", "TEBLİĞ", *issuer_line.split("/"),
        "KREDİ KARTI İŞLEMLERİNDE UYGULANACAK", "AZAMİ FAİZ ORANLARI HAKKINDA TEBLİĞ", "&nbsp;",
        f"MADDE 1- {body}",
    ]
    html = ('<html><head><meta charset="Windows-1254"></head><body>'
            + "".join(f'<p class=MsoNormal><span lang=TR>{p}</span></p>' for p in paragraphs)
            + "</body></html>")
    return html.encode("windows-1254")


TCMB_LINES = gz.html_to_lines(_gazette_page(
    "TÜRKİYE CUMHURİYET MERKEZ BANKASI'ndan:",
    "Bu Tebliğin amacı, kredi kartı işlemlerinde uygulanacak azami faiz oranlarını belirlemektir."))


def test_a_windows_1254_page_becomes_one_line_per_paragraph():
    assert TCMB_LINES[:5] == ["27 Kasım 2026 CUMA", "Resmî Gazete", "Sayı : 33443", "TEBLİĞ",
                              "TÜRKİYE CUMHURİYET MERKEZ BANKASI'ndan:"]


def test_the_header_gives_date_issue_instrument_issuer_title_and_text():
    h = gz.parse_header(TCMB_LINES)
    assert h.event_date == "2026-11-27"
    assert h.gazette_no == "33443"
    assert h.instrument == "TEBLİĞ"
    assert h.issuer == "TCMB"
    assert h.title == "KREDİ KARTI İŞLEMLERİNDE UYGULANACAK AZAMİ FAİZ ORANLARI HAKKINDA TEBLİĞ"
    assert h.summary.startswith("MADDE 1- Bu Tebliğin amacı")


def _ministry_lines():
    return gz.html_to_lines(_gazette_page("Çevre, Şehircilik ve İklim Değişikliği Bakanlığından:", "x"))


def test_another_institutions_header_is_parsed_but_its_issuer_is_none():
    # Parsing and "is it ours" are separate: the header rule has to be
    # checkable on any ministry's page, since no TCMB page with text was
    # available when the lane was written.
    h = gz.parse_header(_ministry_lines())
    assert h is not None and h.issuer is None
    assert (h.event_date, h.gazette_no, h.instrument) == ("2026-11-27", "33443", "TEBLİĞ")


def test_a_readable_document_of_another_institution_is_not_stored():
    ministry = dict(TCMB_DOC, document_id="20261127-2",
                    title="Güvence Hesabı Yönetmeliğinde Değişiklik Yapılmasına Dair Yönetmelik")
    assert gz.build_event(ministry, _ministry_lines(), LISTING_DAY) is None


def test_an_issuing_body_wrapped_over_two_lines_is_still_recognised():
    # Measured on the real page: "…ve İklim Değişikliği" / "Bakanlığından:".
    lines = gz.html_to_lines(_gazette_page("TÜRKİYE CUMHURİYET MERKEZ/BANKASI'ndan:", "x"))
    h = gz.parse_header(lines)
    assert h.issuer == "TCMB"
    assert h.title.startswith("KREDİ KARTI")           # neither half leaked into it


def test_words_export_metadata_does_not_become_lines():
    page = ('<html><head><meta charset="Windows-1254"><!--[if gte mso 9]><xml><w:WordDocument>'
            '<w:Zoom>120</w:Zoom></w:WordDocument></xml><![endif]--></head><body>'
            '<p>27 Kasım 2026 CUMA</p><p>Resmî Gazete</p><p>Sayı : 33443</p><p>TEBLİĞ</p>'
            "<p>TÜRKİYE CUMHURİYET MERKEZ BANKASI'ndan:</p><p>Başlık</p><p>MADDE 1- metin</p></body></html>")
    assert gz.html_to_lines(page.encode("windows-1254")) == [
        "27 Kasım 2026 CUMA", "Resmî Gazete", "Sayı : 33443", "TEBLİĞ",
        "TÜRKİYE CUMHURİYET MERKEZ BANKASI'ndan:", "Başlık", "MADDE 1- metin"]


def test_a_page_with_no_gazette_header_is_not_a_document():
    assert gz.parse_header(["Tahsilat Genel Tebliği (Seri:C Sıra No:10)", "1. …"]) is None
    assert gz.parse_header([]) is None            # a scanned image: no text layer at all


# --- building and storing events ---------------------------------------------


TCMB_DOC = {"document_id": "20261127-4", "fmt": "htm",
            "title": "Kredi Kartı İşlemlerinde Uygulanacak Azami Faiz Oranları Hakkında Tebliğ",
            "url": "https://www.resmigazete.gov.tr/eskiler/2026/11/20261127-4.htm"}
BDDK_DECISION = {
    "document_id": "20261118-6", "fmt": "pdf",
    "title": "Bankacılık Düzenleme ve Denetleme Kurulunun 17/11/2026 Tarihli ve 11601 Sayılı Kararı",
    "url": "https://www.resmigazete.gov.tr/eskiler/2026/11/20261118-6.pdf"}
COURT_DECISION = dict(BDDK_DECISION, document_id="20261118-9",
                      title="Anayasa Mahkemesinin 25/6/2026 Tarihli ve E:2025/211 Sayılı Kararı")
LISTING_DAY = dt.date(2026, 11, 18)


def test_an_event_from_the_documents_own_header():
    e = gz.build_event(TCMB_DOC, TCMB_LINES, LISTING_DAY)
    assert e["document_id"] == "RG-20261127-4"
    assert (e["event_date"], e["issuer"], e["instrument"], e["gazette_no"]) == ("2026-11-27", "TCMB", "TEBLİĞ", "33443")
    assert e["source_url"] == TCMB_DOC["url"]
    assert e["summary"].startswith("MADDE 1-")


def test_a_scanned_board_decision_is_an_event_with_a_title_and_no_text():
    # Measured 2026-11-27: BDDK board decisions in the Gazette are images. The
    # event is still real and dated; what is missing is recorded as NULL.
    e = gz.build_event(BDDK_DECISION, [], LISTING_DAY)
    assert e["issuer"] == "BDDK"
    assert e["instrument"] == "KARAR"
    assert e["event_date"] == "2026-11-18"            # the day of the listing
    assert e["title"] == BDDK_DECISION["title"]
    assert e["summary"] is None and e["gazette_no"] is None


def test_an_unreadable_document_still_leaves_a_title_level_event():
    assert gz.build_event(BDDK_DECISION, None, LISTING_DAY)["issuer"] == "BDDK"


def test_a_document_of_another_institution_is_not_stored():
    assert gz.build_event(COURT_DECISION, [], LISTING_DAY) is None
    assert gz.build_event(COURT_DECISION, None, LISTING_DAY) is None


def _db():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


def _event_stamp(conn):
    return conn.execute(
        "SELECT downloaded_at FROM regulation_events WHERE document_id = ?", (f"RG-{BDDK_DECISION['document_id']}",)
    ).fetchone()[0]


def test_an_unchanged_event_is_not_restamped():
    conn = _db()
    event = gz.build_event(BDDK_DECISION, [], LISTING_DAY)
    assert gz.store_event(conn, event) == "new"
    first = _event_stamp(conn)
    assert gz.store_event(conn, dict(event)) == "same"
    assert _event_stamp(conn) == first                 # so the push window never sees it again
    assert gz.store_event(conn, dict(event, title=event["title"] + " (düzeltme)")) == "changed"
    held = conn.execute("SELECT title FROM regulation_events").fetchone()[0]
    assert held.endswith("(düzeltme)")                 # a corrected document does replace its row


# --- the card-rate table -------------------------------------------------------


def _card_table(rows, header="30.000 TL altında|30.000-180.000 TL arasında|180.000 TL üzerinde*"):
    def cells(values):
        return "".join(f"<td>{v}</td>" for v in values)

    header_rows = (
        f"<tr>{cells(['Geçerlilik Tarihi', 'Referans Oran (%)', *header.split('|'), 'Türk Lirası', 'Yabancı Para'])}</tr>"
        f"<tr>{cells(['Kredi Kartı İşlemlerinde Uygulanacak', '', '', '', '', 'Nakit Çekim veya Kullanım İşlemlerinde', ''])}</tr>")
    return ("<html><body><table>" + header_rows
            + "".join(f"<tr>{cells(r)}</tr>" for r in rows) + "</table></body></html>")


# Printed on TCMB's page, newest month first.
DECEMBER = ["1/12/2026", "2,94", "3,08", "3,38", "3,58", "3,88", "4,08", "4,38", "4,08", "4,38", "2,86", "3,16"]
NOVEMBER = ["1/11/2026", "3,11", "3,25", "3,55", "3,75", "4,05", "4,25", "4,55", "4,25", "4,55", "2,98", "3,28"]


def test_turkish_numbers():
    assert cr._number("3,25") == 3.25
    assert cr._number("30.000") == 30000
    assert cr._percent("3,08") == 3.08
    assert cr._percent("2,94 ") == 2.94        # a non-breaking space after a cell


def test_each_month_becomes_eleven_rows_with_the_bands_as_values():
    rows = cr.parse_table(_card_table([NOVEMBER]))
    assert len(rows) == 11
    assert {r["period_date"] for r in rows} == {"2026-11-01"}
    by_key = {(r["currency"], r["tier"], r["rate_kind"]): r for r in rows}

    def cell(key):
        return tuple(by_key[key][c] for c in ("rate", "tier_floor_tl", "tier_ceiling_tl"))

    assert by_key[("TL", "all", "reference")]["rate"] == 3.11
    assert cell(("TL", "statement_under", "contractual")) == (3.25, None, 30000.0)
    assert cell(("TL", "statement_mid", "late_payment")) == (4.05, 30000.0, 180000.0)
    assert cell(("TL", "statement_over", "contractual")) == (4.25, 180000.0, None)
    assert cell(("TL", "cash_withdrawal", "contractual")) == (4.25, None, None)
    assert cell(("FX", "all", "contractual"))[:1] == (2.98,)
    assert cell(("FX", "all", "late_payment"))[:1] == (3.28,)


def test_a_moved_threshold_is_read_from_the_header_not_assumed():
    rows = cr.parse_table(_card_table([NOVEMBER], header="25.000 TL altında|25.000-150.000 TL arasında|150.000 TL üzerinde*"))
    mid = next(r for r in rows if r["tier"] == "statement_mid")
    assert (mid["tier_floor_tl"], mid["tier_ceiling_tl"]) == (25000.0, 150000.0)


def test_a_blank_cell_is_null_not_zero():
    rows = cr.parse_table(_card_table([NOVEMBER[:2] + [""] + NOVEMBER[3:]]))
    under = next(r for r in rows if (r["tier"], r["rate_kind"]) == ("statement_under", "contractual"))
    assert under["rate"] is None


def test_a_changed_column_layout_raises_instead_of_misassigning_rates():
    with pytest.raises(ValueError, match="expected 12"):
        cr.parse_table(_card_table([NOVEMBER + ["0,00"]]))


def test_a_page_without_a_dated_table_is_empty():
    assert cr.parse_table("<html><body><p>bakım</p></body></html>") == []


def test_the_changes_are_the_months_a_rate_moved():
    # A month in which nothing moved yields nothing; one moved rate yields it.
    quiet = ["1/10/2026", *NOVEMBER[1:]]
    assert cr.changed_rates(cr.parse_table(_card_table([NOVEMBER, quiet]))) == []
    october_reference_only = ["1/10/2026", "3,20", *NOVEMBER[2:]]
    assert cr.changed_rates(cr.parse_table(_card_table([NOVEMBER, october_reference_only]))) == [
        ("2026-11-01", "TL", "all", "reference", 3.11)]


def test_a_cut_across_every_cap_is_eleven_changes():
    # What TCMB printed for December 2026 against November: every rate is lower.
    changes = cr.changed_rates(cr.parse_table(_card_table([DECEMBER, NOVEMBER])))
    assert len(changes) == 11
    assert ("2026-12-01", "TL", "all", "reference", 2.94) in changes
    assert ("2026-12-01", "TL", "statement_under", "contractual", 3.08) in changes


def test_unchanged_rate_rows_are_not_restamped():
    conn = _db()
    rows = cr.parse_table(_card_table([NOVEMBER]))
    query = "SELECT period_date, currency, tier, rate_kind, downloaded_at FROM tcmb_card_rate_caps ORDER BY 1, 2, 3, 4"
    assert cr.store_rows(conn, rows) == {"new": 11, "changed": 0, "same": 0}
    before = conn.execute(query).fetchall()
    assert cr.store_rows(conn, rows) == {"new": 0, "changed": 0, "same": 11}
    assert conn.execute(query).fetchall() == before


# --- the command --------------------------------------------------------------


def _run(monkeypatch, db, *, card_rows, listing, days="1"):
    """main() against faked sources."""
    monkeypatch.setattr(cr, "fetch_rows", lambda session: card_rows)
    monkeypatch.setattr(gz, "fetch_listing", listing)
    monkeypatch.setattr(gz, "fetch_lines", lambda session, doc: [])
    monkeypatch.setattr(update_regulation.time, "sleep", lambda seconds: None)
    monkeypatch.setattr("sys.argv", ["update_regulation.py", "--db", str(db), "--days", days])
    return update_regulation.main()


def _rows(db, table, order):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
    finally:
        conn.close()


def test_the_command_writes_both_tables_and_a_re_run_writes_nothing(monkeypatch, tmp_path):
    db = tmp_path / "reg.db"
    listing = [gz.parse_listing(LISTING_HTML)[2]]            # the scanned BDDK decision
    card_rows = cr.parse_table(_card_table([NOVEMBER]))

    def run():
        return _run(monkeypatch, db, card_rows=card_rows, listing=lambda session, day: listing)

    assert run() == 0
    assert len(_rows(db, "regulation_events", "document_id")) == 1
    assert len(_rows(db, "tcmb_card_rate_caps", "period_date, currency, tier, rate_kind")) == 11
    first = (_rows(db, "regulation_events", "document_id"), _rows(db, "tcmb_card_rate_caps", "period_date, currency, tier, rate_kind"))
    assert run() == 0
    after = (_rows(db, "regulation_events", "document_id"), _rows(db, "tcmb_card_rate_caps", "period_date, currency, tier, rate_kind"))
    assert after == first                                   # not one row, not one timestamp


def _gazette_down(session, day):
    raise ConnectionError("gazete down")


def test_both_sources_failing_is_an_error(monkeypatch, tmp_path):
    db = tmp_path / "reg.db"
    assert _run(monkeypatch, db, card_rows=[], listing=_gazette_down, days="2") == 1


def test_one_source_failing_does_not_fail_the_run(monkeypatch, tmp_path):
    db = tmp_path / "reg.db"
    assert _run(monkeypatch, db, card_rows=cr.parse_table(_card_table([NOVEMBER])), listing=_gazette_down) == 0
    assert len(_rows(db, "tcmb_card_rate_caps", "period_date, currency, tier, rate_kind")) == 11


# --- the lane's wiring ---------------------------------------------------------


def test_both_tables_belong_to_the_bulletin_lane_and_the_regulation_push_scope():
    from src.pipeline import registry
    tables = {"regulation_events", "tcmb_card_rate_caps"}
    assert tables <= registry.LANES["bulletin"]
    assert tables <= set(registry.TABLE_SETS["regulations"])
    assert registry.owner(tables) == "bulletin"


def test_the_python_ddl_and_the_migration_say_the_same_thing():
    statement = re.compile(r"CREATE TABLE IF NOT EXISTS \w+.*?\n\);", re.S)
    schema = (ROOT / "src" / "regulation" / "schema.py").read_text(encoding="utf-8")
    migration = (ROOT / "web" / "migrations" / "0056_regulation_events.sql").read_text(encoding="utf-8")
    assert len(statement.findall(schema)) == 2
    assert statement.findall(schema) == statement.findall(migration)


def test_the_two_daily_workflows_still_skip_the_lane():
    for name in ("refresh-bddk-bulletins.yml", "refresh-evds-daily.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "--skip-regulation" in text, name
