from copy import deepcopy

import fitz
import pytest

from src.audit_reports import document_rule_tables as rules
from src.audit_reports import document_underline_upgrade as upgrade
from src.audit_reports import document_corpus_upgrade as router
from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_evidence import capture_source_evidence
from src.audit_reports.document_structure import build_document_structure, verify_document_structure


@pytest.fixture
def pair(tmp_path, monkeypatch):
    path = tmp_path / 'TEST_2023Q3_consolidated.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=500, height=500)
        page.insert_text((40, 60), 'Daily exchange rates', fontsize=10)
        page.insert_text((220, 94), 'USD', fontsize=8)
        page.insert_text((340, 94), 'EUR', fontsize=8)
        for y in (100, 222):
            for left, right in zip((40, 200, 320), (200, 320, 440)):
                page.draw_rect((left, y, right, y + .5), fill=(0, 0, 0))
        for r in range(6):
            for x, text in [(44, f'Day {r}'), (220, '0' if r == 0 else '27,3767 TL'), (340, '-')]:
                page.insert_text((x, 115 + 20 * r), text, fontsize=8)
        page.insert_text((40, 260), 'A paragraph outside the table stays outside.', fontsize=9)
        pdf.new_page().insert_text((40, 80), 'The next page keeps every original word.')
        pdf.save(path)
    evidence = capture_source_evidence(path, Filing('TEST', '2023Q3', 'consolidated'))
    fresh = build_document_structure(path, evidence)
    with monkeypatch.context() as context:
        context.setattr(rules, '_multiline_underlines', lambda *args: [])
        base = build_document_structure(path, evidence)
    base['engine'] = deepcopy(upgrade.BASE_ENGINE)
    monkeypatch.setattr(upgrade, 'TARGET_ENGINE', fresh['engine'])
    assert verify_document_structure(base, evidence)['valid']
    assert len(fresh['pages'][0]['tables']) == len(base['pages'][0]['tables']) + 1
    return path, evidence, base, fresh


def test_full_replay_matches_fresh_without_reopening_pdf_or_changing_native_data(pair, monkeypatch):
    path, evidence, base, fresh = pair
    before = deepcopy(base), deepcopy(evidence), path.read_bytes()
    monkeypatch.setattr(fitz, 'open', lambda *a, **k: pytest.fail('Retained replay opened a PDF page'))
    result, receipt = upgrade.upgrade_underlines(path, evidence, base)
    assert result == fresh and receipt['pdf_pages_extracted'] == 0
    assert receipt['changed_pages'] == [1]
    assert (base, evidence, path.read_bytes()) == before
    assert result['pages'][1] == base['pages'][1]
    old = {t['id']: t for t in base['pages'][0]['tables']}
    assert all(t == old[t['id']] for t in result['pages'][0]['tables'] if t['id'] in old)


@pytest.mark.parametrize('change', ['original', 'native', 'structure'])
def test_replay_rejects_changed_original_or_retained_content(pair, change):
    path, evidence, base, _ = pair
    if change == 'original':
        path.write_bytes(path.read_bytes() + b'changed')
    elif change == 'native':
        evidence[1]['words'][0]['text'] = 'invented'
    else:
        base['pages'][0]['text_blocks'][0]['text'] = 'invented'
    with pytest.raises(ValueError):
        upgrade.upgrade_underlines(path, evidence, base)


def test_exact_cache_retained_route_full_comparison_and_fresh_fallback(pair):
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
    assert result == fresh and receipt['method'] == 'retained_underline_upgrade'
    assert router.compare_retained_structure(path, evidence, fresh, store)['status'] == 'matched'
    with pytest.raises(ValueError, match='complete fresh extraction'):
        router.compare_retained_structure(path, evidence, {**fresh, 'extra': 'not equivalent'}, store)
    store.exact = True
    assert router.build_or_reuse_structure(path, evidence, store)[1]['method'] == 'exact_engine_cache'
    store.exact, store.missing = False, True
    assert router.build_or_reuse_structure(path, evidence, store)[1]['method'] == 'fresh_extraction'
    assert router.compare_retained_structure(path, evidence, fresh, store)['status'] == 'no_supported_retained_base'
    base['engine'] = {**base['engine'], 'implementation_sha256': 'unsupported'}
    assert upgrade.upgrade_underlines(path.with_name('missing.pdf'), evidence, base) is None
