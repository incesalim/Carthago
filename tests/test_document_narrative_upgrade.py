from copy import deepcopy

import fitz
import pytest

from src.audit_reports import document_narrative as narrative
from src.audit_reports import document_narrative_upgrade as upgrade
from src.audit_reports import document_corpus_upgrade as router
from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_evidence import capture_source_evidence
from src.audit_reports.document_structure import build_document_structure, verify_document_structure


@pytest.fixture
def pair(tmp_path, monkeypatch):
    path = tmp_path / 'TEST_2023Q3_consolidated.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=500, height=500)
        page.insert_text((40, 60), 'OWNERSHIP', fontsize=10, fontname='hebo')
        page.insert_text((40, 90), 'Capital includes 100 shares and 200 rights.', fontsize=9)
        page.insert_text((40, 105), 'There are 300 ordinary and 400 preference units.', fontsize=9)
        for x in [40, 250, 340, 440]:
            page.draw_line((x, 140), (x, 200))
        for y in [140, 160, 180, 200]:
            page.draw_line((40, y), (440, y))
        for x, y, text in [(50, 154, 'SOURCE TABLE'), (260, 154, '2023'), (350, 154, '2022'),
                           (50, 174, 'Cash'), (260, 174, '1,000'), (350, 174, '800'),
                           (50, 194, 'Total'), (260, 194, '1,000'), (350, 194, '800')]:
            page.insert_text((x, y), text, fontsize=8)
        pdf.new_page().insert_text((40, 80), 'A separate page keeps every original word.')
        pdf.save(path)
    evidence = capture_source_evidence(path, Filing('TEST', '2023Q3', 'consolidated'))
    fresh = build_document_structure(path, evidence)
    base = deepcopy(fresh)
    with monkeypatch.context() as context:
        context.setattr(narrative, '_table_envelopes', lambda tables: set())
        base = upgrade.refresh_narrative_views(base, evidence)
    for page in base['pages']:
        for element in page['narrative_elements']:
            element.pop('candidate_table_ids')
            element['method'] = 'source_line_spacing_and_style'
    base['engine'] = deepcopy(upgrade.BASE_ENGINE)
    monkeypatch.setattr(upgrade, 'TARGET_ENGINE', fresh['engine'])
    assert verify_document_structure(base, evidence)['valid']
    assert any(e['candidate_table_ids'] for p in fresh['pages'] for e in p['narrative_elements'])
    return path, evidence, base, fresh


def test_full_replay_matches_fresh_and_preserves_every_source_and_table(pair, monkeypatch):
    path, evidence, base, fresh = pair
    before = deepcopy(base), deepcopy(evidence), path.read_bytes()
    def no_pdf(*args, **kwargs):
        pytest.fail('Retained narrative replay opened or extracted a PDF page')
    monkeypatch.setattr(fitz, 'open', no_pdf)
    result, receipt = upgrade.upgrade_narrative(path, evidence, base)
    assert result == fresh
    assert receipt['pdf_pages_extracted'] == 0
    assert (base, evidence, path.read_bytes()) == before
    assert [p['tables'] for p in result['pages']] == [p['tables'] for p in base['pages']]
    assert [p['text_blocks'] for p in result['pages']] == [p['text_blocks'] for p in base['pages']]


@pytest.mark.parametrize('change', ['original', 'native', 'structure'])
def test_narrative_replay_rejects_changed_source_or_retained_bytes(pair, change):
    path, evidence, base, _ = pair
    if change == 'original':
        path.write_bytes(path.read_bytes() + b'changed')
    elif change == 'native':
        evidence[1]['words'][0]['text'] = 'invented'
    else:
        base['pages'][0]['text_blocks'][0]['text'] = 'invented'
    with pytest.raises(ValueError):
        upgrade.upgrade_narrative(path, evidence, base)


def test_exact_cache_then_retained_narrative_then_fresh_and_full_comparison(pair):
    path, evidence, base, fresh = pair
    class Store:
        exact = False
        missing = False
        def cached_structure(self, records, engine):
            if self.exact and engine == fresh['engine']:
                return fresh
            return base if not self.missing and engine == base['engine'] else None
    store = Store()
    result, receipt = router.build_or_reuse_structure(path, evidence, store)
    assert result == fresh and receipt['method'] == 'retained_narrative_upgrade'
    assert router.compare_retained_structure(path, evidence, fresh, store)['status'] == 'matched'
    with pytest.raises(ValueError, match='complete fresh extraction'):
        router.compare_retained_structure(path, evidence, {**fresh, 'extra': 'not equivalent'}, store)
    store.exact = True
    assert router.build_or_reuse_structure(path, evidence, store)[1]['method'] == 'exact_engine_cache'
    store.exact, store.missing = False, True
    assert router.build_or_reuse_structure(path, evidence, store)[1]['method'] == 'fresh_extraction'
    assert router.compare_retained_structure(path, evidence, fresh, store)['status'] == 'no_supported_retained_base'
    base['engine'] = {**base['engine'], 'implementation_sha256': 'unsupported'}
    assert upgrade.upgrade_narrative(path.with_name('missing.pdf'), evidence, base) is None
