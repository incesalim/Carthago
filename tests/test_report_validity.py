"""An invalid R2 object must never make a partition permanently pending.

TSKB has served a KAP *notification* — 14 pages of cover sheet and "General
Information" — instead of its 2026Q2 filing since 2026-08-01. On its own that is
a nuisance. The damage was `exists(key)` being read as "acquired": once the cover
sheet sat under the key, every later acquisition run skipped that partition, so
the day the real report appeared nothing would have fetched it. One bad object
froze the partition for good.

Three acceptance cases, and nothing wider:
  1. an invalid object stays PENDING and the source is re-checked;
  2. a later real PDF REPLACES it;
  3. a valid new report reaches R2, the DB and the snapshot in one run.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.audit_reports.schema import init_schema  # noqa: E402


def _sync():
    spec = importlib.util.spec_from_file_location(
        "sync_ar", REPO / "scripts" / "sync_audit_reports.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _pdf(pages: int, text: str) -> bytes:
    """A real PDF with `pages` pages, `text` laid out on the first.

    insert_textbox, not insert_text: the latter draws ONE line and clips it at
    the page edge, so a long cover title silently loses the words the validator
    keys on.
    """
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


# The two documents, as they actually read.
KAP_COVER = _pdf(14, "TURKIYE SINAI KALKINMA BANKASI A.S. Bank Financial Report "
                     "Consolidated 2026 - 2. 3 Monthly Notification KAMUYU "
                     "AYDINLATMA PLATFORMU General Information")
REAL_REPORT = _pdf(97, "PASHA YATIRIM BANKASI A.S. 30 HAZIRAN 2026 TARIHINDE SONA "
                       "EREN ARA HESAP DONEMINE AIT KONSOLIDE OLMAYAN FINANSAL "
                       "TABLOLAR BIRINCI BOLUM Genel Bilgiler "
                       "(Tutarlar aksi belirtilmedikce Milyon Turk Lirasi olarak)")


# --- what counts as a report -------------------------------------------------

def test_a_kap_cover_sheet_is_not_a_report():
    ok, why = _sync().report_validity(KAP_COVER)
    assert ok is False
    assert "kap-cover-sheet" in why, why


def test_a_real_filing_is_a_report():
    ok, why = _sync().report_validity(REAL_REPORT)
    assert ok is True, why


@pytest.mark.parametrize("pages,text,expect", [
    (12, "BIRINCI BOLUM Genel Bilgiler Bin Turk Lirasi", "too-short"),
    (90, "Some unrelated document with no BRSA structure at all",
     "no-report-markers"),
    (0, "", "unreadable"),
], ids=["truncated-fragment", "not-a-brsa-filing", "not-a-pdf"])
def test_other_invalid_shapes_are_refused(pages, text, expect):
    body = _pdf(pages, text) if pages else b"not a pdf at all"
    ok, why = _sync().report_validity(body)
    assert ok is False and expect in why, why


# --- 1. an invalid object keeps the partition pending ------------------------

def test_an_invalid_object_does_not_count_as_acquired(tmp_path, monkeypatch):
    """`exists(key)` is not enough — the object has to BE a report, or the
    partition is frozen the day a cover sheet lands under its key."""
    M = _sync()
    db = tmp_path / "a.db"
    calls = {"fetch": 0, "upload": 0}

    monkeypatch.setattr(M.r2_storage, "exists", lambda k: True)
    monkeypatch.setattr(M.r2_storage, "download_to",
                        lambda k, d: Path(d).write_bytes(KAP_COVER))
    monkeypatch.setattr(M.r2_storage, "upload_bytes",
                        lambda b, k: calls.__setitem__("upload", calls["upload"] + 1))

    def _fetch(url, ticker):
        calls["fetch"] += 1
        return KAP_COVER, "ok"           # the source STILL serves the cover sheet
    monkeypatch.setattr(M, "fetch_pdf_bytes", _fetch)

    counts = _scrape_one(M, db, monkeypatch, tmp_path)
    assert calls["fetch"] == 1, "the source must be re-checked, not skipped"
    assert calls["upload"] == 0, "one invalid object must not replace another"
    assert counts["pending"] == 1 and counts["skipped"] == 0
    # and it is recorded, so coverage stops calling it pdf_present
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM bank_audit_invalid_pdfs").fetchone()[0] == 1


def _scrape_one(M, db, monkeypatch, tmp_path):
    """Drive the real scrape_to_r2 over exactly one target, no network."""
    import json as _json
    cfg = tmp_path / "urls.json"
    cfg.write_text(_json.dumps({"banks": {"TSKB": {"urls": {
        "consolidated": {"2026Q2": "https://example.test/r.pdf"}}}}}),
        encoding="utf-8")
    monkeypatch.setattr(M, "CONFIG", cfg)
    monkeypatch.setattr(M, "discover_targets", lambda *_a, **_k: [])
    return M.scrape_to_r2(workers=1, db_path=db)


# --- 2. a real PDF replaces the invalid one ----------------------------------

def test_a_real_report_replaces_the_invalid_object(tmp_path, monkeypatch):
    M = _sync()
    db = tmp_path / "b.db"
    uploaded = {}

    monkeypatch.setattr(M.r2_storage, "exists", lambda k: True)
    monkeypatch.setattr(M.r2_storage, "download_to",
                        lambda k, d: Path(d).write_bytes(KAP_COVER))
    monkeypatch.setattr(M.r2_storage, "upload_bytes",
                        lambda b, k: uploaded.setdefault(k, len(b)))
    monkeypatch.setattr(M, "fetch_pdf_bytes",
                        lambda url, t: (REAL_REPORT, "ok"))   # published at last

    counts = _scrape_one(M, db, monkeypatch, tmp_path)
    assert uploaded, "the real report must replace the cover sheet"
    assert counts["replaced"] == 1 and counts["new"] == 1
    # the refusal must CLEAR, or the fix trades one permanent state for another
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM bank_audit_invalid_pdfs").fetchone()[0] == 0


def test_a_valid_object_is_still_skipped_without_refetching(tmp_path, monkeypatch):
    """The common path stays cheap: a good PDF is not re-downloaded from source."""
    M = _sync()
    db = tmp_path / "c.db"
    fetched = []
    monkeypatch.setattr(M.r2_storage, "exists", lambda k: True)
    monkeypatch.setattr(M.r2_storage, "download_to",
                        lambda k, d: Path(d).write_bytes(REAL_REPORT))
    monkeypatch.setattr(M, "fetch_pdf_bytes",
                        lambda url, t: fetched.append(url) or (REAL_REPORT, "ok"))
    counts = _scrape_one(M, db, monkeypatch, tmp_path)
    assert fetched == [] and counts["skipped"] == 1


# --- 3. extraction refuses it, and coverage stops claiming it -----------------

def test_extraction_refuses_an_invalid_object_rather_than_storing_empty_rows():
    """A cover sheet parses without raising and yields near-empty statements,
    which validate as 'missing' rather than failing — the quiet kind of wrong."""
    M = _sync()
    ok, _ = M.report_validity(KAP_COVER)
    assert ok is False
    src = (REPO / "scripts" / "sync_audit_reports.py").read_text(encoding="utf-8")
    assert "not-a-report" in src.split("def _worker_extract")[1][:2000], \
        "the extraction worker must check validity before extract()"


def test_coverage_does_not_call_an_invalid_object_pdf_present(tmp_path):
    """`pdf_present` meant 'a key exists', which reported TSKB as acquired."""
    conn = sqlite3.connect(tmp_path / "cov.db")
    init_schema(conn)
    conn.execute(
        "INSERT INTO bank_audit_invalid_pdfs (bank_ticker, period, kind, reason) "
        "VALUES ('TSKB','2026Q2','consolidated','kap-cover-sheet:14pp')")
    conn.commit()
    invalid = {(b, p, k) for b, p, k in conn.execute(
        "SELECT bank_ticker, period, kind FROM bank_audit_invalid_pdfs")}
    assert ("TSKB", "2026Q2", "consolidated") in invalid
    src = (REPO / "scripts" / "sync_audit_expected.py").read_text(encoding="utf-8")
    assert "bank_audit_invalid_pdfs" in src and "if bpk in invalid:" in src


# --- the one-run guarantee ---------------------------------------------------

def test_coverage_is_built_locally_and_ships_in_the_one_audit_push():
    """Extraction and its coverage result must be one D1 batch.

    Splitting them once allowed each invocation to pass the cap independently
    and made a small audit refresh bill as two large pushes.
    """
    wf = (REPO / ".github" / "workflows" / "refresh-audit.yml").read_text(
        encoding="utf-8")
    local = wf.index("- name: Rebuild coverage spine locally")
    push = wf.index("- name: Push the complete audit batch")
    upload = wf.index("- name: Upload audit snapshot back to R2")
    assert local < push < upload
    assert "sync_audit_expected.py --db data/bank_audit.db --push" not in wf
    assert wf.count("python scripts/push_to_d1.py") == 1
    assert "--table-set audit-refresh" in wf


def test_rechecking_the_same_invalid_pdf_does_not_rewrite_its_timestamp(tmp_path):
    m = _sync()
    db = tmp_path / "audit.db"
    key = {("TSKB", "2026Q2", "consolidated"): "kap-cover-sheet:14pp"}
    assert m.record_pdf_validity(db, key) == 1
    before = sqlite3.connect(db).execute(
        "SELECT reason, checked_at FROM bank_audit_invalid_pdfs"
    ).fetchall()
    assert m.record_pdf_validity(db, key) == 0
    after = sqlite3.connect(db).execute(
        "SELECT reason, checked_at FROM bank_audit_invalid_pdfs"
    ).fetchall()
    assert after == before


def test_incremental_coverage_is_enabled():
    """The full rebuild is what breached the run cap and stranded the snapshot:
    161,728 estimated rows to restate a table that had barely changed."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "p2d_cov2", REPO / "scripts" / "push_to_d1.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    assert P._COVERAGE_INCREMENTAL is True
    assert "bank_audit_coverage" not in P._FULL_REBUILD
