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
              "capital", "liquidity_funding", "franchise", "market_position", "esg", "macro"},
    "level": {"bank", "group", "sector", "macro"},
    "availability": {"mandatory", "voluntary", "third_party", "none"},
    "cadence": {"daily", "weekly", "monthly", "quarterly", "annual", "adhoc", "none"},
    "reproducible": {"direct", "derived", "partial", "no"},
    "source_datasets": {"bank_audit", "bddk_monthly", "bddk_weekly", "evds",
                        "tbb_digital", "external", "none"},
}

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
    for m in metrics:
        mid = m.get("id", "?")
        for field in REQUIRED:
            if field not in m:
                errs.append(f"{mid}: missing required field {field!r}")
        if mid in seen:
            errs.append(f"{mid}: duplicate id")
        seen.add(mid)
        for field, valid in ENUMS.items():
            if field == "source_datasets":
                for v in m.get("source_datasets", []):
                    if v not in valid:
                        errs.append(f"{mid}: invalid source_dataset {v!r}")
            elif field in m and m[field] not in valid:
                errs.append(f"{mid}: invalid {field} {m[field]!r}")
        if not isinstance(m.get("standard_across_banks"), bool):
            errs.append(f"{mid}: standard_across_banks must be a boolean")
        if "reproducible_from_audit" in m and m["reproducible_from_audit"] != is_reproducible_from_audit(m):
            errs.append(
                f"{mid}: reproducible_from_audit={m['reproducible_from_audit']} contradicts "
                f"source/reproducible (expected {is_reproducible_from_audit(m)})"
            )
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group")
    ap.add_argument("--reproducible", help="comma list, e.g. direct,derived")
    ap.add_argument("--source", help="filter by a source_dataset, e.g. bank_audit")
    ap.add_argument("--audit", action="store_true", help="reproducible from audit reports")
    ap.add_argument("--not-reproducible", action="store_true", help="reproducible == no")
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

    sel = metrics
    if args.group:
        sel = [m for m in sel if m["group"] == args.group]
    if args.reproducible:
        want = {s.strip() for s in args.reproducible.split(",")}
        sel = [m for m in sel if m["reproducible"] in want]
    if args.source:
        sel = [m for m in sel if args.source in m["source_datasets"]]
    if args.audit:
        sel = [m for m in sel if is_reproducible_from_audit(m)]
    if args.not_reproducible:
        sel = [m for m in sel if m["reproducible"] == "no"]

    if args.group or args.reproducible or args.source or args.audit or args.not_reproducible:
        _list(sel)
        print(f"\n{len(sel)} metric(s)")
    else:
        _matrix(metrics)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
