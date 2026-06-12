"""Unified manual-correction CLI for the audit lane — one entry point for the
three ways to fix a partition by hand. All three share scripts/audit_d1.py
(pull snapshot → mutate local DB → validate to 0 → clear+push partition →
snapshot) and validate before pushing. See docs/AUDIT_PIPELINE.md §repair playbook.

  python scripts/audit_correct.py overlay-statement --bank FIBA --period 2025Q1 --kind unconsolidated
  python scripts/audit_correct.py override-cells [--dry-run] [--no-push]
  python scripts/audit_correct.py reextract-pl --bank ISCTR --period 2024Q4 --kind unconsolidated

Subcommands (each delegates to its implementation script; flags pass straight through):
  overlay-statement  hand-transcribed whole statements from data/manual_statements.json
                     (for scanned-image statement pages)            → load_partition.py
  override-cells     curated per-cell fixes from data/audit_overrides.json
                     (one-off OCR artifacts / digit typos)          → apply_overrides.py
  reextract-pl       re-extract ONE partition's profit_loss only    → reextract_pl.py
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

SUBCOMMANDS = {
    "overlay-statement": "load_partition.py",
    "override-cells": "apply_overrides.py",
    "reextract-pl": "reextract_pl.py",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    sub = sys.argv[1]
    if sub not in SUBCOMMANDS:
        sys.exit(f"unknown subcommand {sub!r}; choose from {', '.join(SUBCOMMANDS)}")
    target = REPO / "scripts" / SUBCOMMANDS[sub]
    # Hand the rest of argv to the implementation, as if it were invoked directly.
    sys.argv = [str(target)] + sys.argv[2:]
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
