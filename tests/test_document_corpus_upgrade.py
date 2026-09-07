"""A retained-structure replay must equal fresh extraction, including failures."""
from copy import deepcopy

import fitz
import pytest

from src.audit_reports import document_corpus_upgrade as upgrade
from src.audit_reports import document_structure as structure
from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_evidence import capture_source_evidence


@pytest.fixture
def pair(tmp_path, monkeypatch, request):
    rotation = getattr(request, 'param', 0)
    path = tmp_path / 'TEST_2026Q1_consolidated.pdf'
    with fitz.open() as upright, fitz.open() as pdf:
        page = upright.new_page(width=400, height=300)
        for x in (50, 110, 240, 330):
            page.draw_line((x, 50), (x, 140))
        for y in (50, 80, 110, 140):
            page.draw_line((50, y), (330, y))
        for x, y, text in [(60, 70, 'No'), (120, 70, 'Item'), (250, 70, 'Value'),
                           (103.9, 100, '1Label'), (250, 100, '-'),
                           (103.9, 130, '2Other'), (250, 130, '0')]:
            page.insert_text((x, y), text, fontsize=10)
        size = (300, 400) if rotation in (90, 270) else (400, 300)
        shown = pdf.new_page(width=size[0], height=size[1])
        shown.show_pdf_page(shown.rect, upright, 0, rotate=rotation)
        shown.set_rotation(rotation)
        pdf.new_page().insert_text((50, 70), 'A separate prose page with no table.')
        pdf.save(path)
    evidence = capture_source_evidence(path, Filing('TEST', '2026Q1', 'consolidated'))
    # For this synthetic source the supported old diff is precisely the absent
    # fragment step. Real cloud artifacts are compared independently as well.
    with monkeypatch.context() as old:
        old.setattr(structure, 'link_cell_fragments', lambda table, source, geometry: table)
        base = structure.build_document_structure(path, evidence)
    base['engine'] = deepcopy(upgrade.BASE_ENGINE)
    fresh = structure.build_document_structure(path, evidence)
    # Exercise this historical target independently of newer adapters and
    # worktree line endings. The real cloud artifacts are checked separately.
    target = deepcopy(upgrade.TARGET_ENGINE)
    fresh['engine'] = target
    monkeypatch.setattr(upgrade, 'structure_engine', lambda: target)
    return path, evidence, base, fresh


@pytest.mark.parametrize('pair', [0, 90, 180, 270], indirect=True)
def test_replay_equals_full_fresh_extraction_and_reads_only_affected_page(pair, monkeypatch):
    path, evidence, base, fresh = pair
    original, records, prior = path.read_bytes(), deepcopy(evidence), deepcopy(base)
    seen = []
    observe = upgrade.word_character_geometry

    def observe_page(page, source, words):
        seen.append(source['page'])
        return observe(page, source, words)

    monkeypatch.setattr(upgrade, 'word_character_geometry', observe_page)
    result, receipt = upgrade.upgrade_cell_fragments(path, evidence, base)
    assert result == fresh
    assert seen == receipt['glyph_pages_inspected'] == [1]
    assert receipt['changed_tables'] == [{'page': 1, 'table_id': 'p1:ruled0'}]
    assert result['semantic_verification'] == 'not_performed'
    assert path.read_bytes() == original and evidence == records and base == prior
    assert result['pages'][1] == base['pages'][1]


@pytest.mark.parametrize('field', ['base_code', 'base_library', 'target_code', 'target_library'])
def test_unsupported_engine_abstains_before_opening_source(pair, monkeypatch, field):
    path, evidence, base, _ = pair
    if field.startswith('base'):
        base['engine']['pymupdf' if field.endswith('library') else 'implementation_sha256'] = 'changed'
    else:
        engine = {**upgrade.TARGET_ENGINE,
                  ('pymupdf' if field.endswith('library') else 'implementation_sha256'): 'changed'}
        monkeypatch.setattr(upgrade, 'structure_engine', lambda: engine)
    assert upgrade.upgrade_cell_fragments(path.with_name('missing.pdf'), evidence, base) is None


@pytest.mark.parametrize('mutation', ['pdf', 'native', 'structure', 'page_inventory', 'diagnostics'])
def test_invalid_supported_base_is_rejected(pair, mutation):
    path, evidence, base, _ = pair
    if mutation == 'pdf':
        with fitz.open() as pdf:
            pdf.new_page().insert_text((50, 70), 'Different source')
            pdf.save(path)
    elif mutation == 'native':
        evidence[1]['words'][0]['text'] = 'Invented'
    elif mutation == 'structure':
        base['pages'][0]['text_blocks'][0]['text'] = 'Invented'
    elif mutation == 'page_inventory':
        base['pages'].pop()
    else:
        base['pages'][0]['issues'] = [i for i in base['pages'][0]['issues']
                                    if i['kind'] != 'table_cell_source_mismatch']
    with pytest.raises(ValueError):
        upgrade.upgrade_cell_fragments(path, evidence, base)


def test_exact_cache_wins_and_read_only_probe_remains_fresh(pair, monkeypatch):
    path, evidence, base, fresh = pair
    calls = []

    class Store:
        def cached_structure(self, records, engine):
            calls.append(engine)
            assert records == evidence
            return fresh

    result, receipt = upgrade.build_or_reuse_structure(path, evidence, Store())
    assert result == fresh and receipt == {'method': 'exact_engine_cache'}
    assert calls == [fresh['engine']]
    monkeypatch.setattr(upgrade, 'build_document_structure', lambda path, records: fresh)
    assert upgrade.build_or_reuse_structure(path, evidence)[1] == {'method': 'fresh_extraction'}


def test_cache_upgrade_avoids_table_extraction_and_cache_miss_falls_back(pair, monkeypatch):
    path, evidence, base, fresh = pair
    calls = []

    class Store:
        def cached_structure(self, records, engine):
            calls.append(engine)
            return base if engine == upgrade.BASE_ENGINE else None

    def fail(*args):
        pytest.fail('Eligible replay invoked full extraction')

    monkeypatch.setattr(upgrade, 'build_document_structure', fail)
    result, receipt = upgrade.build_or_reuse_structure(path, evidence, Store())
    assert result == fresh and receipt['method'] == 'retained_cell_fragment_upgrade'
    assert calls == [fresh['engine'], upgrade.BASE_ENGINE]
    monkeypatch.setattr(Store, 'cached_structure', lambda self, records, engine: None)
    monkeypatch.setattr(upgrade, 'build_document_structure', lambda path, records: fresh)
    assert upgrade.build_or_reuse_structure(path, evidence, Store()) == (fresh, {'method': 'fresh_extraction'})


def test_corrupt_cache_failure_is_not_hidden_by_fresh_extraction(pair):
    path, evidence, base, fresh = pair

    class Store:
        def cached_structure(self, records, engine):
            raise ValueError('Cached structure is missing or corrupted')

    with pytest.raises(ValueError, match='corrupted'):
        upgrade.build_or_reuse_structure(path, evidence, Store())
