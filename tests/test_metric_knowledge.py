"""Tests for the banking-metric knowledge registry (data/metric_knowledge/).

Guards the stored knowledge: schema/enum parity, registry integrity (unique ids,
valid enums, the reproducible_from_audit consistency rule, spec_ids resolve), and
that the user's defining contrast is encoded — financials are reproducible &
standardized; customer metrics are neither.
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
        if field == "source_datasets":
            schema_enum = set(props["source_datasets"]["items"]["enum"])
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
