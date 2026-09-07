from copy import deepcopy

import fitz
import pytest

from src.audit_reports import document_header_upgrade as upgrade
from src.audit_reports import document_corpus_upgrade as router
from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_evidence import capture_source_evidence
from src.audit_reports.document_structure import build_document_structure


@pytest.fixture
def pair(tmp_path, monkeypatch, request):
    rotation = getattr(request, 'param', 0)
    path = tmp_path / 'TEST_2023Q3_consolidated.pdf'
    with fitz.open() as upright, fitz.open() as pdf:
        page = upright.new_page(width=400, height=250)
        for x in [40, 220, 300, 390]:
            page.draw_line((x, 40 if x in (40, 390) else 80), (x, 140))
        for y in [40, 80, 110, 140]:
            page.draw_line((40, y), (390, y))
        for x, y, text in [(50, 75, 'CAPITAL'), (225, 55, 'Current period'), (305, 55, 'Prior period'),
                           (225, 70, '30 Sep 2023'), (305, 70, '31 Dec 2022'),
                           (50, 100, 'Paid capital'), (230, 100, '900'), (310, 100, '800'),
                           (50, 130, 'Total'), (230, 130, '900'), (310, 130, '800')]:
            page.insert_text((x, y), text, fontsize=8)
        size = (250, 400) if rotation in (90, 270) else (400, 250)
        shown = pdf.new_page(width=size[0], height=size[1])
        shown.show_pdf_page(shown.rect, upright, 0, rotate=rotation)
        shown.set_rotation(rotation)
        pdf.new_page().insert_text((50, 70), 'Separate prose retains every word.')
        pdf.save(path)
    evidence = capture_source_evidence(path, Filing('TEST', '2023Q3', 'consolidated'))
    fresh = build_document_structure(path, evidence)
    base = deepcopy(fresh)
    base['engine'] = deepcopy(upgrade.BASE_ENGINE)
    del base['table_period_headers_schema']
    for page in base['pages']:
        del page['table_period_headers']
    monkeypatch.setattr(upgrade, 'TARGET_ENGINE', fresh['engine'])
    # This fixture simulates the historical header transition at the installed
    # engine. Keep the newer production adapter from claiming that test target.
    from src.audit_reports import document_narrative_upgrade
    monkeypatch.setattr(document_narrative_upgrade, 'TARGET_ENGINE', {'test': 'not_the_header_transition'})
    return path, evidence, base, fresh


@pytest.mark.parametrize('pair', [0, 90, 180, 270], indirect=True)
def test_complete_replay_equals_fresh_without_opening_or_extracting_pdf_pages(pair, monkeypatch):
    path, evidence, base, fresh = pair
    originals = deepcopy(base), deepcopy(evidence), path.read_bytes()
    assert fresh['pages'][0]['table_period_headers']['tables']
    def no_pdf(*args, **kwargs):
        pytest.fail('Pure header replay opened or extracted a PDF page')
    monkeypatch.setattr(fitz, 'open', no_pdf)
    result, receipt = upgrade.upgrade_period_headers(path, evidence, base)
    assert result == fresh
    assert receipt['pdf_pages_extracted'] == 0
    assert len(receipt['header_tables']) == 1
    assert (base, evidence, path.read_bytes()) == originals


@pytest.mark.parametrize('change', ['original', 'native_word', 'structure', 'unexpected_view'])
def test_corrupt_eligible_base_fails_instead_of_silently_reusing_it(pair, change):
    path, evidence, base, _ = pair
    if change == 'original':
        path.write_bytes(path.read_bytes() + b'changed')
    elif change == 'native_word':
        evidence[1]['words'][0]['text'] = 'invented'
    elif change == 'structure':
        base['pages'][1]['text_blocks'][0]['text'] = 'invented'
    else:
        base['pages'][0]['table_period_headers'] = {}
    with pytest.raises(ValueError):
        upgrade.upgrade_period_headers(path, evidence, base)


def test_exact_cache_then_header_replay_then_fresh_fallback(pair, monkeypatch):
    path, evidence, base, fresh = pair
    calls = []
    class Store:
        exact = False
        missing = False
        def cached_structure(self, records, engine):
            calls.append(engine)
            if self.exact and engine == fresh['engine']:
                return fresh
            return base if not self.missing and engine == base['engine'] else None
    store = Store()
    result, receipt = router.build_or_reuse_structure(path, evidence, store)
    assert result == fresh and receipt['method'] == 'retained_period_header_upgrade'
    assert calls == [fresh['engine'], base['engine']]
    store.exact = True
    assert router.build_or_reuse_structure(path, evidence, store)[1]['method'] == 'exact_engine_cache'
    store.exact, store.missing = False, True
    assert router.build_or_reuse_structure(path, evidence, store)[1]['method'] == 'fresh_extraction'
    base['engine'] = {**base['engine'], 'implementation_sha256': 'unsupported'}
    assert upgrade.upgrade_period_headers(path.with_name('missing.pdf'), evidence, base) is None


def test_cloud_comparison_checks_entire_structure_not_only_headers(pair):
    path, evidence, base, fresh = pair
    class Store:
        def cached_structure(self, records, engine):
            return base
    assert router.compare_retained_structure(path, evidence, fresh, Store())['status'] == 'matched'
    with pytest.raises(ValueError, match='complete fresh extraction'):
        router.compare_retained_structure(path, evidence, {**fresh, 'unexpected': 'extra'}, Store())
    class Missing:
        def cached_structure(self, records, engine):
            return None
    assert router.compare_retained_structure(path, evidence, fresh, Missing())['status'] == 'no_supported_retained_base'
