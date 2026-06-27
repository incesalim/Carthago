"""Banking-metric knowledge registry — loader, validator, and query CLI.

The registry (data/metric_knowledge/registry.json) is our stored knowledge of
banking metrics: for each metric, whether it is disclosed at all, standardized
across banks, on a regular cadence, and whether WE can reproduce it from the data
we hold — especially the BRSA quarterly audit reports (bank_audit_*).

See docs/BANKING_METRICS.md for the taxonomy. This module is the programmatic
entry point so the knowledge is queryable, not just prose.

Usage:
    python scripts/metric_knowledge.py                      # summary matrix
    python scripts/metric_knowledge.py --audit              # reproducible from audit reports
    python scripts/metric_knowledge.py --not-reproducible   # what we CAN'T get
    python scripts/metric_knowledge.py --group asset_quality
    python scripts/metric_knowledge.py --reproducible direct,derived
    python scripts/metric_knowledge.py --framework ifrs9    # filter by definitional framework
    python scripts/metric_knowledge.py --unstructured       # non-comparable metrics + why
    python scripts/metric_knowledge.py --reason window_varies    # filter by nonstandard reason
    python scripts/metric_knowledge.py --channel investor_deck   # filter by disclosure channel
    python scripts/metric_knowledge.py --show active_digital_customers  # full knowledge dump
    python scripts/metric_knowledge.py --tree roe           # decomposition tree of a metric
    python scripts/metric_knowledge.py --validate           # integrity check only

Stdlib only — safe under the minimal-deps CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "metric_knowledge" / "registry.json"
SCHEMA = ROOT / "data" / "metric_knowledge" / "schema.json"
CHART_SPECS = ROOT / "web" / "app" / "lib" / "chart-specs.catalog.json"

# Valid enum values — mirror data/metric_knowledge/schema.json.
# tests/test_metric_knowledge.py asserts these match the schema (parity guard).
ENUMS: dict[str, set[str]] = {
    "group": {"profitability", "income", "balance_sheet", "growth", "asset_quality",
              "capital", "liquidity_funding", "efficiency", "valuation", "franchise",
              "market_position", "esg", "macro"},
    "level": {"bank", "group", "sector", "macro"},
    "availability": {"mandatory", "voluntary", "third_party", "none"},
    "cadence": {"daily", "weekly", "monthly", "quarterly", "annual", "adhoc", "none"},
    "reproducible": {"direct", "derived", "partial", "no"},
    "source_datasets": {"bank_audit", "bddk_monthly", "bddk_weekly", "evds",
                        "tbb_digital", "faaliyet", "external", "none"},
    "frameworks": {"basel_iii", "ifrs9", "tfrs", "brsa", "market", "management", "none"},
    "nonstandard_reasons": {"definition_varies", "window_varies", "peer_set_varies",
                            "methodology_varies", "provider_varies", "cadence_irregular",
                            "scope_varies", "not_disclosed"},
    "disclosure_channels": {"investor_deck", "earnings_press", "sustainability_report",
                            "annual_report", "kap", "third_party", "regulatory", "none"},
}

# Enum fields stored as arrays (each element validated against the enum), vs the
# scalar enum fields above.
ARRAY_ENUMS = ("source_datasets", "frameworks", "nonstandard_reasons", "disclosure_channels")

REQUIRED = ("id", "name_en", "group", "definition", "level", "availability",
            "cadence", "standard_across_banks", "reproducible", "source_datasets")


def load() -> list[dict]:
    """Load the metrics list from the registry."""
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["metrics"]


def is_reproducible_from_audit(m: dict) -> bool:
    """A metric is reproducible from the BRSA audit reports iff bank_audit is a
    source AND we can get it directly or via a derivation."""
    return "bank_audit" in m.get("source_datasets", []) and m.get("reproducible") in ("direct", "derived")


def validate(metrics: list[dict]) -> list[str]:
    """Return a list of integrity errors (empty = ok)."""
    errs: list[str] = []
    seen: set[str] = set()
    spec_ids = _known_spec_ids()
    ids = {m.get("id") for m in metrics}
    for m in metrics:
        mid = m.get("id", "?")
        for field in REQUIRED:
            if field not in m:
                errs.append(f"{mid}: missing required field {field!r}")
        if mid in seen:
            errs.append(f"{mid}: duplicate id")
        seen.add(mid)
        for field, valid in ENUMS.items():
            if field in ARRAY_ENUMS:
                for v in m.get(field, []):
                    if v not in valid:
                        errs.append(f"{mid}: invalid {field[:-1] if field.endswith('s') else field} {v!r}")
            elif field in m and m[field] not in valid:
                errs.append(f"{mid}: invalid {field} {m[field]!r}")
        if not isinstance(m.get("standard_across_banks"), bool):
            errs.append(f"{mid}: standard_across_banks must be a boolean")
        if "reproducible_from_audit" in m and m["reproducible_from_audit"] != is_reproducible_from_audit(m):
            errs.append(
                f"{mid}: reproducible_from_audit={m['reproducible_from_audit']} contradicts "
                f"source/reproducible (expected {is_reproducible_from_audit(m)})"
            )
        for field in ("decomposes_into", "related"):
            for ref in m.get(field, []):
                if ref not in ids:
                    errs.append(f"{mid}: {field} references unknown metric {ref!r}")
        for sid in m.get("spec_ids", []):
            if spec_ids is not None and sid not in spec_ids:
                errs.append(f"{mid}: spec_id {sid!r} not in chart-specs catalog")
    return errs


def _known_spec_ids() -> set[str] | None:
    if not CHART_SPECS.exists():
        return None
    try:
        return {s["id"] for s in json.loads(CHART_SPECS.read_text(encoding="utf-8"))}
    except Exception:
        return None


def _matrix(metrics: list[dict]) -> None:
    """Print a group × reproducibility count matrix + availability tallies."""
    cols = ["direct", "derived", "partial", "no"]
    groups = sorted({m["group"] for m in metrics})
    width = max(len(g) for g in groups + ["group"])
    print(f"{'group':{width}}  " + "  ".join(f"{c:>7}" for c in cols) + "   total")
    for g in groups:
        row = [sum(1 for m in metrics if m["group"] == g and m["reproducible"] == c) for c in cols]
        print(f"{g:{width}}  " + "  ".join(f"{n:>7}" for n in row) + f"   {sum(row):>5}")
    tot = [sum(1 for m in metrics if m["reproducible"] == c) for c in cols]
    print(f"{'TOTAL':{width}}  " + "  ".join(f"{n:>7}" for n in tot) + f"   {sum(tot):>5}")

    print("\nby availability:")
    for a in sorted(ENUMS["availability"]):
        n = sum(1 for m in metrics if m["availability"] == a)
        if n:
            print(f"  {a:12} {n}")
    print(f"\nreproducible from audit reports: "
          f"{sum(1 for m in metrics if is_reproducible_from_audit(m))} / {len(metrics)}")


def _list(metrics: list[dict]) -> None:
    width = max((len(m["id"]) for m in metrics), default=4)
    for m in sorted(metrics, key=lambda x: (x["group"], x["id"])):
        flags = f"{m['reproducible']:<7} {m['availability']:<10} {m['cadence']:<9}"
        std = "std" if m["standard_across_banks"] else "non-std"
        print(f"  {m['id']:{width}}  {flags} {std:8} [{','.join(m['source_datasets'])}]  {m['name_en']}")


def _tree(by_id: dict[str, dict], root: str, indent: int = 0, seen: set[str] | None = None) -> None:
    """Print a metric's decomposition tree (via decomposes_into)."""
    seen = seen or set()
    m = by_id.get(root)
    if m is None:
        print(f"{'  ' * indent}? {root} (unknown)")
        return
    suffix = f"  = {m['formula']}" if m.get("formula") else ""
    print(f"{'  ' * indent}{m['id']} ({m['name_en']}){suffix}")
    if root in seen:
        return
    seen = seen | {root}
    for child in m.get("decomposes_into", []):
        _tree(by_id, child, indent + 1, seen)


def _unstructured(metrics: list[dict]) -> None:
    """List the non-comparable metrics (standard_across_banks == False) grouped by
    family, with the structured reasons + where they're disclosed — the
    'these aren't structured' view."""
    sel = [m for m in metrics if not m.get("standard_across_banks", True)]
    width = max((len(m["id"]) for m in sel), default=4)
    for m in sorted(sel, key=lambda x: (x["group"], x["id"])):
        reasons = ",".join(m.get("nonstandard_reasons", [])) or "—"
        channels = ",".join(m.get("disclosure_channels", [])) or "—"
        print(f"  {m['id']:{width}}  [{m['group']}] {m['availability']:<10} "
              f"reasons={reasons}  via={channels}")
    print(f"\n{len(sel)} non-standardized metric(s)")
    counts: dict[str, int] = {}
    for m in sel:
        for r in m.get("nonstandard_reasons", []):
            counts[r] = counts.get(r, 0) + 1
    if counts:
        print("\nby reason:")
        for r, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {r:18} {n}")


def _show(by_id: dict[str, dict], mid: str) -> None:
    """Full knowledge dump for one metric."""
    m = by_id.get(mid)
    if m is None:
        print(f"unknown metric {mid!r}")
        return
    print(f"{m['id']}  —  {m.get('name_en', '')}")
    if m.get("name_tr"):
        print(f"  tr:  {m['name_tr']}")
    if m.get("aliases"):
        print(f"  aka: {', '.join(m['aliases'])}")
    print(f"  group={m['group']}  level={m['level']}  availability={m['availability']}  "
          f"cadence={m['cadence']}  standard={m['standard_across_banks']}  "
          f"reproducible={m['reproducible']}")
    print(f"  source_datasets: {', '.join(m.get('source_datasets', []))}")
    if m.get("frameworks"):
        print(f"  frameworks: {', '.join(m['frameworks'])}")
    print(f"\n  definition: {m.get('definition', '')}")
    for label, key in (("formula", "formula"), ("derivation", "derivation"),
                       ("caveats", "caveats")):
        if m.get(key):
            print(f"  {label}: {m[key]}")
    if m.get("nonstandard_reasons"):
        print(f"\n  not comparable because: {', '.join(m['nonstandard_reasons'])}")
    if m.get("disclosure_channels"):
        print(f"  disclosed via: {', '.join(m['disclosure_channels'])}")
    for v in m.get("definition_variants", []):
        print(f"    · variant: {v}")
    for ex in m.get("examples", []):
        bank = ex.get("bank", "?")
        period = ex.get("period", "")
        print(f"  e.g. {bank} {period}: {ex.get('value')} {ex.get('unit', '')} "
              f"({ex.get('source', '')})".rstrip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group")
    ap.add_argument("--reproducible", help="comma list, e.g. direct,derived")
    ap.add_argument("--source", help="filter by a source_dataset, e.g. bank_audit")
    ap.add_argument("--framework", help="filter by a framework, e.g. ifrs9, basel_iii")
    ap.add_argument("--audit", action="store_true", help="reproducible from audit reports")
    ap.add_argument("--not-reproducible", action="store_true", help="reproducible == no")
    ap.add_argument("--unstructured", action="store_true",
                    help="non-comparable metrics (standard_across_banks false) + reasons")
    ap.add_argument("--reason", help="filter by a nonstandard_reason, e.g. window_varies")
    ap.add_argument("--channel", help="filter by a disclosure_channel, e.g. investor_deck")
    ap.add_argument("--show", help="full knowledge dump for a metric id")
    ap.add_argument("--tree", help="print the decomposition tree of a metric id")
    ap.add_argument("--validate", action="store_true", help="integrity check only")
    args = ap.parse_args()

    metrics = load()
    errs = validate(metrics)
    if args.validate:
        for e in errs:
            print(f"  ✗ {e}")
        print(f"\n{len(metrics)} metrics · {len(errs)} error(s)")
        return 1 if errs else 0
    if errs:
        print(f"WARNING: registry has {len(errs)} integrity error(s); run --validate", file=sys.stderr)

    if args.tree:
        _tree({m["id"]: m for m in metrics}, args.tree)
        return 0
    if args.show:
        _show({m["id"]: m for m in metrics}, args.show)
        return 0
    if args.unstructured:
        _unstructured(metrics)
        return 0

    sel = metrics
    if args.group:
        sel = [m for m in sel if m["group"] == args.group]
    if args.reproducible:
        want = {s.strip() for s in args.reproducible.split(",")}
        sel = [m for m in sel if m["reproducible"] in want]
    if args.source:
        sel = [m for m in sel if args.source in m["source_datasets"]]
    if args.framework:
        sel = [m for m in sel if args.framework in m.get("frameworks", [])]
    if args.reason:
        sel = [m for m in sel if args.reason in m.get("nonstandard_reasons", [])]
    if args.channel:
        sel = [m for m in sel if args.channel in m.get("disclosure_channels", [])]
    if args.audit:
        sel = [m for m in sel if is_reproducible_from_audit(m)]
    if args.not_reproducible:
        sel = [m for m in sel if m["reproducible"] == "no"]

    if any([args.group, args.reproducible, args.source, args.framework, args.reason,
            args.channel, args.audit, args.not_reproducible]):
        _list(sel)
        print(f"\n{len(sel)} metric(s)")
    else:
        _matrix(metrics)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
