from copy import deepcopy

import pytest

from src.audit_reports import document_region_upgrade as upgrade
from src.audit_reports import document_structure as structure
from src.audit_reports.document_corpus import Filing
from src.audit_reports.document_evidence import capture_source_evidence
from test_document_table_regions import source_page


@pytest.fixture
def pair(tmp_path, monkeypatch, request):
    rotation = getattr(request, 'param', 0)
    raw_base = isinstance(rotation, tuple)
    if raw_base:
        rotation = rotation[0]
    path = tmp_path / 'TEST_2026Q1_consolidated.pdf'
    with source_page(rotation) as pdf:
        pdf.new_page().insert_text((50, 70), 'Separate prose, with no ruled grid.')
        pdf.save(path)
    evidence = capture_source_evidence(path, Filing('TEST', '2026Q1', 'consolidated'))
    with monkeypatch.context() as old:
        old.setattr(structure, 'refine_ruled_regions', lambda page, source, tables, *args: tables)
        if raw_base:
            old.setattr(structure, 'link_cell_fragments', lambda table, source, geometry: table)
        base = structure.build_document_structure(path, evidence)
    base['engine'] = deepcopy(upgrade.RAW_BASE_ENGINE if raw_base else upgrade.BASE_ENGINE)
    fresh = structure.build_document_structure(path, evidence)
    # Simulate this historical transition's pinned target, not whichever newer
    # adapter happens to own the current working tree's extraction fingerprint.
    from src.audit_reports import document_corpus_upgrade as router
    target = deepcopy(upgrade.TARGET_ENGINE)
    fresh['engine'] = target
    monkeypatch.setattr(upgrade, 'structure_engine', lambda: target)
    monkeypatch.setattr(router, 'structure_engine', lambda: target)
    return path, evidence, base, fresh


@pytest.mark.parametrize('pair', [0, 90, 180, 270, (0,), (90,), (180,), (270,)], indirect=True)
def test_retained_region_replay_equals_all_fresh_fields(pair):
    path, evidence, base, fresh = pair
    prior, records, pdf = deepcopy(base), deepcopy(evidence), path.read_bytes()
    result, receipt = upgrade.upgrade_table_regions(path, evidence, base)
    assert result == fresh
    assert receipt['ruled_pages_inspected'] == [1]
    assert len(receipt['refined_tables']) == 2
    assert result['pages'][1] == base['pages'][1]
    assert base == prior and evidence == records and path.read_bytes() == pdf


@pytest.mark.parametrize('field', ['source_engine', 'target_engine', 'library'])
def test_different_versions_cannot_take_the_replay_path(pair, monkeypatch, field):
    path, evidence, base, fresh = pair
    if field == 'source_engine':
        base['engine']['implementation_sha256'] = 'different'
    else:
        monkeypatch.setattr(upgrade, 'structure_engine', lambda: {
            **fresh['engine'], 'pymupdf' if field == 'library' else 'implementation_sha256': 'different'})
    assert upgrade.upgrade_table_regions(path.with_name('missing.pdf'), evidence, base) is None


@pytest.mark.parametrize('field', ['source_bytes', 'word', 'structure', 'cell_diagnostic', 'boundary_diagnostic'])
def test_invalid_supported_inputs_are_rejected(pair, field):
    path, evidence, base, _ = pair
    if field == 'source_bytes':
        path.write_bytes(path.read_bytes() + b'changed')
    elif field == 'word':
        evidence[1]['words'][0]['text'] = 'Invented'
    elif field == 'structure':
        base['pages'][0]['text_blocks'][0]['text'] = 'Invented'
    elif field == 'cell_diagnostic':
        base['pages'][0]['issues'].append({'kind': 'table_cell_source_mismatch', 'table_id': 'invented'})
    else:
        base['pages'][0]['issues'] = [i for i in base['pages'][0]['issues']
                                    if i['kind'] != 'word_crosses_table_cells']
    with pytest.raises(ValueError):
        upgrade.upgrade_table_regions(path, evidence, base)


@pytest.mark.parametrize('pair', [0, (0,)], indirect=True)
def test_probe_compares_all_fresh_fields_and_reports_missing_base(pair):
    path, evidence, base, fresh = pair

    class Store:
        def cached_structure(self, records, engine):
            assert records == evidence and engine in upgrade.SUPPORTED_BASE_ENGINES
            return base if engine == base['engine'] else None

    check = upgrade.compare_retained_regions(path, evidence, fresh, Store())
    assert check['status'] == 'matched'
    assert check['replay']['ruled_pages_inspected'] == [1]
    changed = {**fresh, 'unexpected_field': 'not present in the replay'}
    with pytest.raises(ValueError, match='complete fresh extraction'):
        upgrade.compare_retained_regions(path, evidence, changed, Store())

    class Missing:
        def cached_structure(self, records, engine):
            return None

    assert upgrade.compare_retained_regions(path, evidence, fresh, Missing())['status'] == 'no_supported_retained_base'


@pytest.mark.parametrize('pair', [0, (0,)], indirect=True)
def test_publishing_router_reuses_regions_without_repeating_full_capture(pair, monkeypatch):
    from src.audit_reports import document_corpus_upgrade as router
    path, evidence, base, fresh = pair
    queries = []

    class Store:
        def cached_structure(self, records, engine):
            queries.append(engine)
            return base if engine == base['engine'] else None

    def fail(*args):
        pytest.fail('Region replay called full extraction')

    monkeypatch.setattr(router, 'build_document_structure', fail)
    result, receipt = router.build_or_reuse_structure(path, evidence, Store())
    assert result == fresh and receipt['method'] == 'retained_table_region_upgrade'
    expected = [fresh['engine'], upgrade.BASE_ENGINE]
    if base['engine'] == upgrade.RAW_BASE_ENGINE:
        expected.append(upgrade.RAW_BASE_ENGINE)
    assert queries == expected
