"""Tests for the banking-metric knowledge registry (data/metric_knowledge/).

Guards the stored knowledge: schema/enum parity, registry integrity (unique ids,
valid enums, spec_ids resolve), the relationship layer (decomposition trees are
acyclic and all decomposes_into/related/framework refs resolve), breadth (≥100
metrics incl. efficiency + valuation), and that the user's defining contrast is
encoded — financials are reproducible & standardized; customer metrics are neither.
"""
import json

import metric_knowledge as mk


def test_registry_validates():
    metrics = mk.load()
    errs = mk.validate(metrics)
    assert errs == [], "registry integrity errors:\n" + "\n".join(errs)


def test_ids_unique_and_nonempty():
    metrics = mk.load()
    ids = [m["id"] for m in metrics]
    assert len(ids) == len(set(ids))
    assert all(ids)


def test_enum_parity_with_schema():
    # The hard-coded ENUMS in the helper must match the JSON-Schema enums.
    schema = json.loads(mk.SCHEMA.read_text(encoding="utf-8"))
    props = schema["definitions"]["metric"]["properties"]
    for field, valid in mk.ENUMS.items():
        if field in ("source_datasets", "frameworks"):  # array-typed enums
            schema_enum = set(props[field]["items"]["enum"])
        else:
            schema_enum = set(props[field]["enum"])
        assert valid == schema_enum, f"enum drift on {field}: helper {valid} vs schema {schema_enum}"


def test_reproducible_from_audit_rule():
    # The flag (where present) must equal source-has-bank_audit AND reproducible in {direct,derived}.
    for m in mk.load():
        if "reproducible_from_audit" in m:
            assert m["reproducible_from_audit"] == mk.is_reproducible_from_audit(m)


def test_user_contrast_is_encoded():
    by_id = {m["id"]: m for m in mk.load()}

    # Financials: reproducible from audit, standardized, periodic.
    for fin in ("roe", "total_assets", "npl_ratio"):
        m = by_id[fin]
        assert mk.is_reproducible_from_audit(m)
        assert m["standard_across_banks"] is True
        assert m["cadence"] == "quarterly"

    # Customer metric: not reproducible from audit, not standardized, ad-hoc.
    dig = by_id["active_digital_customers"]
    assert not mk.is_reproducible_from_audit(dig)
    assert dig["standard_across_banks"] is False
    assert dig["reproducible"] == "no"
    assert dig["availability"] == "voluntary"


def test_every_metric_has_a_source():
    for m in mk.load():
        assert m["source_datasets"], f"{m['id']} has no source_datasets"


def test_decomposition_and_framework_refs_resolve():
    ids = {m["id"] for m in mk.load()}
    for m in mk.load():
        for field in ("decomposes_into", "related"):
            for ref in m.get(field, []):
                assert ref in ids, f"{m['id']}.{field} -> unknown metric {ref!r}"
        for fw in m.get("frameworks", []):
            assert fw in mk.ENUMS["frameworks"], f"{m['id']} bad framework {fw!r}"


def test_validate_catches_bad_links():
    # A dangling decomposition / related / framework ref must be flagged.
    bad = [
        {"id": "x", "name_en": "X", "group": "income", "definition": "d", "level": "bank",
         "availability": "mandatory", "cadence": "quarterly", "standard_across_banks": True,
         "reproducible": "direct", "source_datasets": ["bank_audit"],
         "decomposes_into": ["ghost"], "related": ["phantom"], "frameworks": ["bogus"]},
    ]
    errs = " ".join(mk.validate(bad))
    assert "unknown metric 'ghost'" in errs
    assert "unknown metric 'phantom'" in errs
    assert "bogus" in errs


def test_decomposition_tree_is_acyclic_and_resolvable():
    # Walk every decomposes_into edge; ensure no cycles and all nodes exist.
    by_id = {m["id"]: m for m in mk.load()}

    def walk(node, stack):
        assert node in by_id, f"unknown node {node}"
        assert node not in stack, f"cycle through {node}: {stack}"
        for child in by_id[node].get("decomposes_into", []):
            walk(child, stack + [node])

    for m in mk.load():
        walk(m["id"], [])


def test_breadth_and_new_groups_present():
    metrics = mk.load()
    groups = {m["group"] for m in metrics}
    assert {"efficiency", "valuation"} <= groups
    assert len(metrics) >= 100  # comprehensive, not a 35-metric seed
    # Valuation metrics are honestly un-reproducible (no market data).
    val = [m for m in metrics if m["group"] == "valuation"]
    assert val and all(m["reproducible"] == "no" for m in val)
