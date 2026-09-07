import json

import fitz
import pytest

import build_document_corpus as build


def _config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"banks": {"TEST": {"urls": {"consolidated": {
        "2026Q1": "https://bank.example/report.pdf"}}}}}), encoding="utf-8")
    return path


def _args(tmp_path):
    return ["--config", str(_config(tmp_path)), "--source-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out")]


def test_unqueried_r2_is_unknown_not_a_missing_source(tmp_path):
    assert build.main(_args(tmp_path)) == 0
    report = json.loads((tmp_path / "out/inventory.json").read_text())
    assert report["registered_missing"] is None
    assert report["acquisition_checked"] is False
    assert report["filings"][0]["acquisition_status"] == "not_checked"


def test_annotation_only_scope_keeps_inventory_denominator(tmp_path):
    args = _args(tmp_path) + ['--capture', '--bank', 'TEST']
    config = json.loads((tmp_path / 'config.json').read_text())
    config['banks']['TEST']['urls']['consolidated']['2025Q4'] = 'https://bank.example/prior.pdf'
    (tmp_path / 'config.json').write_text(json.dumps(config))
    annotations = tmp_path / 'annotations'
    annotations.mkdir()
    (annotations / 'one.json').write_text(json.dumps({'filing': {
        'bank_ticker': 'TEST', 'period': '2026Q1', 'kind': 'consolidated'}, 'cases': []}))
    assert build.main(args + ['--annotated-only', '--annotations-dir', str(annotations)]) == 1
    report = json.loads((tmp_path / 'out/inventory.json').read_text())
    assert len(report['filings']) == 2
    assert report['run_scope']['selected_filings'] == 1
    assert report['run_scope']['annotated_only'] is True
    with pytest.raises(SystemExit):
        build.main(args + ['--annotated-only', '--annotations-dir', str(annotations), '--period', '2025Q4'])


def test_annotation_only_requires_its_registry(tmp_path):
    with pytest.raises(SystemExit):
        build.main(_args(tmp_path) + ['--capture', '--bank', 'TEST', '--annotated-only', '--annotations-dir', str(tmp_path / 'missing')])


def test_missing_source_fails_capture_and_remains_in_results(tmp_path):
    assert build.main(_args(tmp_path) + ["--capture", "--bank", "TEST"]) == 1
    results = json.loads((tmp_path / "out/capture-results.json").read_text())["filings"]
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert "Missing" in results[0]["error"]


def test_capture_keeps_source_artifacts_and_never_claims_verified(tmp_path):
    with fitz.open() as doc:
        doc.new_page().insert_text((40, 50), "A complete source sentence.")
        doc.save(tmp_path / "TEST_2026Q1_consolidated.pdf")
    assert build.main(_args(tmp_path) + ["--capture", "--bank", "TEST"]) == 0
    result = json.loads((tmp_path / "out/capture-results.json").read_text())["filings"][0]
    assert result["status"] == "source_preserved"
    assert result["semantic_verification"] == "not_performed"
    assert (tmp_path / "out" / result["artifact"]).exists()
    assert result["source"]["object_key"] is None


def test_unbounded_local_capture_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(SystemExit):
        build.main(_args(tmp_path) + ["--capture"])


def test_read_only_structure_probe_cannot_silently_skip_a_missing_benchmark(tmp_path):
    with pytest.raises(SystemExit):
        build.main(_args(tmp_path) + ["--capture", "--structure", "--bank", "TEST",
                                     "--annotations-dir", str(tmp_path / "missing-benchmark")])


def test_source_only_capture_runs_source_annotations_and_retains_a_failed_original(tmp_path):
    import hashlib
    from src.audit_reports.document_benchmark import paragraph_digest
    path = tmp_path / "TEST_2026Q1_consolidated.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 80), "A disclosed value of zero.")
        pdf.save(path)
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    case = {"filing": {"bank_ticker": "TEST", "period": "2026Q1", "kind": "consolidated"},
            "pdf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "cases": [
                {"id": "complete_footnote", "kind": "source_span", "page": 1,
                 "text_sha256": paragraph_digest("A disclosed value of zero. Missing qualification.")}]}
    (annotations / "case.json").write_text(json.dumps(case))
    args = _args(tmp_path) + ["--capture", "--bank", "TEST", "--annotations-dir", str(annotations)]
    assert build.main(args) == 1
    result = json.loads((tmp_path / "out/capture-results.json").read_text())["filings"][0]
    assert result["source_benchmark"]["status"] == "failed"
    assert (tmp_path / "out" / result["original"]).read_bytes() == path.read_bytes()


def test_password_protected_pdf_is_preserved_even_when_capture_fails(tmp_path):
    with fitz.open() as doc:
        doc.new_page().insert_text((40, 50), "Protected original")
        doc.save(tmp_path / "TEST_2026Q1_consolidated.pdf", encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw="owner", user_pw="reader")
    assert build.main(_args(tmp_path) + ["--capture", "--bank", "TEST"]) == 1
    result = json.loads((tmp_path / "out/capture-results.json").read_text())["filings"][0]
    assert result["status"] == "failed" and "password" in result["error"]
    archived = tmp_path / "out" / result["original"]
    assert archived.read_bytes() == (tmp_path / "TEST_2026Q1_consolidated.pdf").read_bytes()


def test_r2_capture_reads_current_object_instead_of_a_stale_local_copy(tmp_path, monkeypatch):
    from src.audit_reports import r2_storage as r2
    args = _args(tmp_path)
    local = tmp_path / "TEST_2026Q1_consolidated.pdf"
    local.write_bytes(b"stale local non-PDF")
    with fitz.open() as doc:
        doc.new_page().insert_text((40, 50), "Current source revision")
        body = doc.tobytes()
    key = "test/TEST_2026Q1_consolidated.pdf"
    monkeypatch.setattr(r2, "list_audit_pdfs", lambda: [("TEST", "2026Q1", "consolidated", key)])
    monkeypatch.setattr(r2, "download_to", lambda _key, destination: destination.write_bytes(body))
    assert build.main(args + ["--from-r2", "--capture", "--bank", "TEST"]) == 0
    result = json.loads((tmp_path / "out/capture-results.json").read_text())["filings"][0]
    assert result["source"]["object_key"] == key
    assert result["source"]["byte_count"] == len(body)
    assert local.read_bytes() == b"stale local non-PDF"


def test_filing_groups_are_disjoint_exhaustive_and_stable_when_inventory_changes():
    rows = [{"bank_ticker": bank, "period": f"202{year}Q{quarter}", "kind": kind}
            for bank in ("AKBNK", "ALBRK", "QNBFB") for year in range(2, 7)
            for quarter in range(1, 5) for kind in ("consolidated", "unconsolidated")]
    groups = [{build.Filing(**row).filename for row in rows if build.filing_shard(row, 4) == index}
              for index in range(4)]
    assert set.union(*groups) == {build.Filing(**row).filename for row in rows}
    assert sum(map(len, groups)) == len(rows)
    assert all(groups)
    expanded = [{"bank_ticker": "OTHER", "period": "2021Q1", "kind": "consolidated"}] + rows[::-1]
    for index, group in enumerate(groups):
        reassigned = {build.Filing(**row).filename for row in expanded if build.filing_shard(row, 4) == index}
        assert group <= reassigned


@pytest.mark.parametrize("count,index", [(0, 0), (-1, 0), (4, -1), (4, 4)])
def test_invalid_group_is_rejected_before_inventory(tmp_path, count, index):
    with pytest.raises(SystemExit):
        build.main(_args(tmp_path) + ["--shard-count", str(count), "--shard-index", str(index)])
    assert not (tmp_path / "out/inventory.json").exists()


def test_empty_assigned_group_reports_full_scope_without_hiding_invalid_selection(tmp_path):
    filing = {"bank_ticker": "TEST", "period": "2026Q1", "kind": "consolidated"}
    empty_group = (build.filing_shard(filing, 4) + 1) % 4
    args = _args(tmp_path) + ["--capture", "--bank", "TEST", "--shard-count", "4",
                              "--shard-index", str(empty_group)]
    assert build.main(args) == 0
    report = json.loads((tmp_path / "out/capture-results.json").read_text())
    assert report["filings"] == []
    assert report["run_scope"]["assigned_filings"] == 0
    assert report["run_scope"]["selected_filings"] == 1
    assert json.loads((tmp_path / "out/inventory.json").read_text())["registered_filings"] == 1
    with pytest.raises(SystemExit):
        build.main(args + ["--period", "2025Q1"])


def test_limit_applies_to_global_scope_before_group_assignment(tmp_path):
    config = _config(tmp_path)
    data = json.loads(config.read_text())
    data["banks"]["TEST"]["urls"]["consolidated"]["2026Q2"] = "https://bank.example/q2.pdf"
    config.write_text(json.dumps(data))
    results = []
    for index in range(4):
        output = tmp_path / f"out-{index}"
        build.main(["--config", str(config), "--source-dir", str(tmp_path), "--output-dir", str(output),
                    "--capture", "--limit", "1", "--shard-count", "4", "--shard-index", str(index)])
        report = json.loads((output / "capture-results.json").read_text())
        assert report["run_scope"]["selected_filings"] == 1
        results.extend(report["filings"])
    assert len(results) == 1  # A per-group limit would incorrectly process both filings.


@pytest.mark.parametrize("extra", [["--ocr-pages", "1"], ["--ocr-pages", "0", "--limit", "1"],
    ["--ocr-pages", "1,1", "--limit", "1"], ["--ocr-pages", "1,2,3,4,5", "--limit", "1"],
    ["--ocr-pages", "1", "--limit", "1", "--publish"], ["--ocr-pages", "1", "--limit", "5"]])
def test_ocr_probe_scope_is_bounded_and_read_only(tmp_path, extra):
    with pytest.raises(SystemExit):
        build.main(_args(tmp_path) + ["--capture", "--bank", "TEST"] + extra)
    assert not (tmp_path / "out/inventory.json").exists()


@pytest.mark.parametrize("extra", [["--vector-pages", "1"], ["--vector-pages", "0", "--limit", "1"],
    ["--vector-pages", "1,1", "--limit", "1"], ["--vector-pages", "1,2,3,4,5", "--limit", "1"],
    ["--vector-pages", "1", "--limit", "1", "--publish"], ["--vector-pages", "1", "--limit", "5"]])
def test_vector_probe_scope_is_bounded_and_read_only(tmp_path, extra):
    with pytest.raises(SystemExit):
        build.main(_args(tmp_path) + ["--capture", "--bank", "TEST"] + extra)


@pytest.mark.parametrize('extra', [[], ['--publish'], ['--limit', '5'], ['--review-pages', '0'],
                                  ['--review-pages', '2,1'], ['--review-pages', '1,1'],
                                  ['--review-pages', 'ALL']])
def test_visual_review_scope_stays_bounded_and_read_only(tmp_path, extra, monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    args = _args(tmp_path) + ['--capture', '--bank', 'TEST', '--review-pages', '1']
    if extra:
        args += ['--limit', '1', *extra]
    with pytest.raises(SystemExit):
        build.main(args)
    assert not (tmp_path / "out/inventory.json").exists()
