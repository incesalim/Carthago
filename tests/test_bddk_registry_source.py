"""The registry was complete, and the scraper never read it.

2026Q3: 24 of 38 banks had filed, BDDK's own registry (BdrUyg) held all 41 of
their reports, and each daily run printed `new=0` and exited green. The target
list was the hand-maintained config plus IR-page discovery for 13 banks, so
those 24 banks had no target at all. The listing reader already existed — as
evidence, never as a source.

Pinned here, each one a way the first real read of the registry went wrong
(2026-11-26):

  1. the fallback offers exactly what no other source targets, and only for
     banks we track — it adds, it never replaces;
  2. a registry zip is not necessarily "a PDF": QNB files Word + Excel;
  3. nor one document: ANADOLU's report sorts behind its one-page
     responsibility statement;
  4. nor unwrapped: five zips carry the PDF behind a 27-byte Java header.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports import bddk_registry_source  # noqa: E402
from src.audit_reports.bddk_registry_source import (  # noqa: E402
    BDDK_REGISTRY_FAILURES, bddk_registry_targets, is_bddk_registry_url)

NAMES = json.loads(
    (REPO / "data/banks/bddk_audit_registry_names.json").read_bytes())["banks"]


def _sync():
    spec = importlib.util.spec_from_file_location(
        "sync_registry", REPO / "scripts" / "sync_audit_reports.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def _no_failures_left_behind():
    BDDK_REGISTRY_FAILURES.clear()
    yield
    BDDK_REGISTRY_FAILURES.clear()


# --- the listing, as the regulator renders it ---------------------------------

def _link(code: int, basis: str, year: int, month: int) -> str:
    return (f"https://www.bddk.org.tr/BdrUyg/Home/DosyaIndir?raporUrl=~%2FDosya%2F"
            f"BDREki-{code:03d}-{basis}-{year}-{month:02d}.zip")


def _row(name: str, year: int, month: int, basis: str, code: int,
         link_basis: str | None = None) -> str:
    href = _link(code, link_basis or basis, year, month).replace(
        "https://www.bddk.org.tr", "")
    return (f"<tr><td>{name}</td><td>{year}</td><td>{month}</td><td>{basis}</td>"
            f'<td><a class="downloadLink" href="{href}">İndir</a></td></tr>')


def _serving(monkeypatch, *rows: str) -> None:
    body = (f'<html><div id="divTab_raporlar"><table>{"".join(rows)}'
            f'</table></div></html>').encode("utf-8")
    monkeypatch.setattr(bddk_registry_source, "fetch_listing", lambda: (body, {}))


AKTIF, QNB = NAMES["AKTIF"], NAMES["QNBFB"]


# --- 1. it offers what nothing else targets -----------------------------------

def test_it_offers_what_no_other_source_targets(monkeypatch):
    _serving(monkeypatch, _row(AKTIF, 2026, 9, "SOLO", 143),
             _row(AKTIF, 2026, 9, "KONSOLIDE", 143))
    out = bddk_registry_targets(
        {"AKTIF": {}}, skip={("AKTIF", "2026Q3", "consolidated")})
    assert out == [("AKTIF", "2026Q3", "unconsolidated", _link(143, "SOLO", 2026, 9))]


def test_it_leaves_history_below_the_dataset_floor_alone(monkeypatch):
    """The lane starts 2022Q1 (see discovery.MIN_PERIOD). The registry goes
    back to 2013; none of that may arrive as a side effect of a new quarter."""
    _serving(monkeypatch, _row(AKTIF, 2021, 12, "SOLO", 143),
             _row(AKTIF, 2022, 3, "SOLO", 143))
    assert bddk_registry_targets({"AKTIF": {}}) == [
        ("AKTIF", "2022Q1", "unconsolidated", _link(143, "SOLO", 2022, 3))]


def test_it_offers_only_banks_we_track_and_only_the_ones_asked_for(monkeypatch):
    _serving(monkeypatch, _row(AKTIF, 2026, 9, "SOLO", 143),
             _row(QNB, 2026, 9, "SOLO", 111))
    # QNB is in the registry and in the name map, but not in the config.
    assert [t[0] for t in bddk_registry_targets({"AKTIF": {}})] == ["AKTIF"]
    # A scoped repair run stays scoped.
    assert [t[0] for t in bddk_registry_targets(
        {"AKTIF": {}, "QNBFB": {}}, only={"QNBFB"})] == ["QNBFB"]


def test_a_row_whose_link_contradicts_itself_is_refused(monkeypatch):
    """The listing says SOLO, the download target says KONSOLIDE. Whichever is
    right, the document's basis would be a guess — so it is not offered."""
    _serving(monkeypatch,
             _row(AKTIF, 2026, 9, "SOLO", 143, link_basis="KONSOLIDE"))
    assert bddk_registry_targets({"AKTIF": {}}) == []
    assert BDDK_REGISTRY_FAILURES == []   # a bad row is not an unreadable registry


def test_an_unreadable_registry_adds_nothing_and_says_so(monkeypatch):
    def boom():
        raise ConnectionError("listing timed out")
    monkeypatch.setattr(bddk_registry_source, "fetch_listing", boom)
    assert bddk_registry_targets({"AKTIF": {}}) == []
    assert BDDK_REGISTRY_FAILURES == ["ConnectionError: listing timed out"]


def test_is_bddk_registry_url_recognises_only_the_regulator():
    assert is_bddk_registry_url(_link(143, "SOLO", 2026, 9))
    assert not is_bddk_registry_url("https://www.bddk.org.tr/Bulten/aylik")
    assert not is_bddk_registry_url("https://ir.example/BdrUyg/Home/DosyaIndir")


def test_the_scrape_adds_registry_targets_and_never_duplicates(monkeypatch, tmp_path):
    M = _sync()
    cfg = tmp_path / "urls.json"
    cfg.write_text(json.dumps({"banks": {"AKTIF": {"urls": {
        "unconsolidated": {"2026Q3": "https://x.test/solo.pdf"}}}}}), encoding="utf-8")
    monkeypatch.setattr(M, "CONFIG", cfg)
    monkeypatch.setattr(M, "discover_targets", lambda t, b: [])
    handed = {}

    def registry(banks, only=None, skip=None):
        handed.update(banks=sorted(banks), only=only, skip=skip)
        # A partition the config already binds, and one nothing does.
        return [("AKTIF", "2026Q3", "unconsolidated", "https://x.test/dup.pdf"),
                ("AKTIF", "2026Q3", "consolidated", _link(143, "KONSOLIDE", 2026, 9))]
    monkeypatch.setattr(M, "bddk_registry_targets", registry)
    fetched = []
    monkeypatch.setattr(M, "fetch_pdf_bytes",
                        lambda url, t: (fetched.append(url), (None, "stub"))[1])
    monkeypatch.setattr(M.r2_storage, "exists", lambda k: False)
    M.scrape_to_r2(workers=1, db_path=None)

    assert fetched == ["https://x.test/solo.pdf", _link(143, "KONSOLIDE", 2026, 9)]
    # It is told what the other sources already target, so it never has to
    # propose it — and a scoped run stays scoped.
    assert handed["skip"] == {("AKTIF", "2026Q3", "unconsolidated")}
    assert handed["banks"] == ["AKTIF"] and handed["only"] is None


def test_a_scoped_run_keeps_the_registry_scoped(monkeypatch, tmp_path):
    M = _sync()
    cfg = tmp_path / "urls.json"
    cfg.write_text(json.dumps({"banks": {"AKTIF": {"urls": {}}}}), encoding="utf-8")
    monkeypatch.setattr(M, "CONFIG", cfg)
    monkeypatch.setattr(M, "discover_targets", lambda t, b: [])
    seen = {}
    monkeypatch.setattr(M, "bddk_registry_targets",
                        lambda banks, only=None, skip=None: seen.update(only=only) or [])
    M.scrape_to_r2(workers=1, db_path=None, only={"AKTIF"})
    assert seen["only"] == {"AKTIF"}


def test_an_unreadable_registry_reaches_the_run_summary(monkeypatch, tmp_path):
    """The scrape counts cannot show it — an unattempted target is in no
    denominator — so it travels the same channel a failed discovery does."""
    M = _sync()
    M.BDDK_REGISTRY_FAILURES.append("ConnectionError: listing timed out")
    out = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", [
        "sync_audit_reports.py", "--no-scrape", "--no-extract", "--db",
        str(tmp_path / "a.db"), "--result-file", str(out)])
    M.main()
    assert json.loads(out.read_text(encoding="utf-8"))["bddk_registry_failures"] == [
        "ConnectionError: listing timed out"]

    wf = (REPO / ".github/workflows/refresh-audit.yml").read_text(encoding="utf-8")
    assert "::warning title=BDDK registry fallback unavailable::" in wf


# --- 2–4. a registry zip is not "a PDF" ---------------------------------------

class _Resp:
    def __init__(self, body: bytes, status: int = 200):
        self.status_code = status
        self.content = body


def _pdf(pages: int, text: str) -> bytes:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page()
        if i == 0:
            pg.insert_textbox(fitz.Rect(40, 40, 560, 760), text, fontsize=9)
        else:
            pg.insert_text((72, 72), f"page {i}", fontsize=9)
    out = doc.tobytes()
    doc.close()
    return out


# ASCII, like the fixtures in test_report_validity: fitz's default font cannot
# draw Turkish letters, and the validator keys on "BIRINCI BOLUM".
STATEMENT = _pdf(1, "ANADOLUBANK A.S. SORUMLULUK BEYANI")
REPORT = _pdf(90, "ANADOLUBANK ANONIM SIRKETI VE FINANSAL ORTAKLILKARI 30 EYLUL 2026 "
                  "TARIHINDE SONA EREN HESAP DONEMINE AIT KONSOLIDE FINANSAL TABLOLAR "
                  "BIRINCI BOLUM (Tutarlar Milyon Turk Lirasi olarak)")

# The header as DUNYAK's 2026Q3 consolidated zip actually carries it.
JAVA_HEADER = b"\xac\xed\x00\x05ur\x00\x02[B\xac\xf3\x17\xf8\x06\x08T\xe0\x02\x00\x00xp\x00:\x95\x9b"


def _zip(*members: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def _fetch_zip(monkeypatch, M, payload: bytes, ticker="ANADOLU"):
    monkeypatch.setattr(M.requests, "get", lambda url, **kw: _Resp(payload))
    return M.fetch_pdf_bytes(_link(135, "KONSOLIDE", 2026, 9), ticker)


def test_the_report_is_taken_from_behind_its_responsibility_statement(monkeypatch):
    M = _sync()
    body, note = _fetch_zip(monkeypatch, M, _zip(
        ("Anadolubank A.Ş  Konsolide  Sorumluluk Beyanı-30.09.2026.pdf", STATEMENT),
        ("Anadolubank A.Ş. - 30.09.2026 - Konsolide  Rapor.pdf", REPORT)))
    assert body == REPORT and note == "ok"


def test_an_unnamed_companion_costs_nothing_either(monkeypatch):
    """The next document a bank files beside its report has no name yet. What
    separates it is that it is not a report."""
    M = _sync()
    body, _ = _fetch_zip(monkeypatch, M, _zip(
        ("something-new.pdf", STATEMENT), ("rapor.pdf", REPORT)))
    assert body == REPORT


def test_the_activity_report_is_still_set_aside_by_name(monkeypatch):
    """The pre-existing rule, unchanged: an activity report that is itself a
    long, marker-carrying document must not win on validity."""
    M = _sync()
    activity = _pdf(95, "ARA DÖNEM FAALİYET RAPORU BİRİNCİ BÖLÜM "
                        "(Tutarlar Milyon Türk Lirası olarak)")
    body, _ = _fetch_zip(monkeypatch, M, _zip(
        ("… Aradönem Faaliyet Raporu.pdf", activity), ("finansal.pdf", REPORT)))
    assert body == REPORT


def test_a_pdf_behind_the_java_header_is_unwrapped(monkeypatch):
    """Five of the registry's 2026Q3 zips (DUNYAK, EMLAK ×2, EXIM, VAKIFK).
    The header was already stripped from VAKIFK's own downloads — but from the
    download, never from the file inside a zip, which is where these carry it."""
    assert len(JAVA_HEADER) == 27 and (JAVA_HEADER + REPORT).find(b"%PDF") == 27
    M = _sync()
    body, note = _fetch_zip(monkeypatch, M, _zip(
        ("DÜNYA KATILIM BANKASI 09.2026 TR Konsolide.pdf", JAVA_HEADER + REPORT)),
        ticker="DUNYAK")
    assert body == REPORT and note == "ok"


def test_the_header_does_not_hide_a_report_from_the_choice(monkeypatch):
    M = _sync()
    body, _ = _fetch_zip(monkeypatch, M, _zip(
        ("something-new.pdf", STATEMENT),
        ("Türkiye Emlak Katılım Bankası_30.09.2026_TR_Konsolide.pdf.pdf", JAVA_HEADER + REPORT)))
    assert body == REPORT


def test_a_registry_zip_without_a_pdf_is_pending_not_a_failure(monkeypatch, tmp_path):
    """QNB files Word + Excel with the regulator. Nothing here can read that,
    so it is that bank's "not published yet" — looked at again next run, and
    outside the systemic alarm's numerator."""
    M = _sync()
    db = tmp_path / "qnb.db"
    cfg = tmp_path / "urls.json"
    cfg.write_text(json.dumps({"banks": {"QNBFB": {"urls": {}}}}), encoding="utf-8")
    monkeypatch.setattr(M, "CONFIG", cfg)
    monkeypatch.setattr(M, "discover_targets", lambda t, b: [])
    monkeypatch.setattr(M, "bddk_registry_targets", lambda *a, **k: [
        ("QNBFB", "2026Q3", "unconsolidated", _link(111, "SOLO", 2026, 9))])
    monkeypatch.setattr(M.r2_storage, "exists", lambda k: False)
    monkeypatch.setattr(M.requests, "get", lambda url, **kw: _Resp(
        _zip(("QNB Bank 30.09.2026 Solo_Final.docx", b"PK-docx"))))
    counts = M.scrape_to_r2(workers=1, db_path=db)

    assert counts["pending"] == 1 and counts["failed"] == 0
    # ...and recorded with the reason, so coverage can say why without a download.
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT reason FROM bank_audit_invalid_pdfs").fetchall() == [
            ("no-pdf-in-zip",)]


def test_a_config_bound_zip_without_a_pdf_is_still_a_failure(monkeypatch, tmp_path):
    """There the URL is ours. Same note, opposite meaning."""
    M = _sync()
    cfg = tmp_path / "urls.json"
    cfg.write_text(json.dumps({"banks": {"VAKBN": {"urls": {"unconsolidated_zip": {
        "2026Q3": "https://x.test/solo.zip"}}}}}), encoding="utf-8")
    monkeypatch.setattr(M, "CONFIG", cfg)
    monkeypatch.setattr(M, "discover_targets", lambda t, b: [])
    monkeypatch.setattr(M, "bddk_registry_targets", lambda *a, **k: [])
    monkeypatch.setattr(M.r2_storage, "exists", lambda k: False)
    monkeypatch.setattr(M.requests, "get", lambda url, **kw: _Resp(
        _zip(("solo.docx", b"PK-docx"))))
    counts = M.scrape_to_r2(workers=1, db_path=None)

    assert counts["failed"] == 1 and counts["pending"] == 0
