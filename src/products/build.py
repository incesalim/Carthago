"""Load the frozen product-shelf research snapshot into the SQLite staging DB.

Reads the source of truth in data/product_benchmark/ — one <TICKER>.json per bank
(the cells + Turkish prose), the English attribute catalog (labels_en.py) and the
English per-bank prose (profiles_en.json) — and writes the three tables defined in
web/migrations/0034_bank_products.sql.

Deterministic and idempotent: a re-run for the same snapshot_date replaces that
snapshot's rows, so the row counts never drift. Reuses the coverage / penetration
math from data/product_benchmark/aggregate.py + matrix.py so the page can never
disagree with the report.

Evidence rule (also checked by aggregate.py's QC): every 'yes'/'partial' must carry
an evidence_url on the bank's own domain, or the build fails loudly rather than
shipping an uncited claim.

    python -m src.products.build [path/to/bddk_data.db]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from src.products.labels_en import BLOCKS_EN, CLUSTERS_EN, LABELS_EN
from src.products.schema import init_schema

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "product_benchmark"
SNAPSHOT_DATE = "2026-07-22"

# The taxonomy (CODES / LABELS / CLUSTERS) lives beside the source JSONs as a
# plain module, not a package — add it to the path and import.
sys.path.insert(0, str(DATA))
from aggregate import CLUSTERS, CODES, LABELS, ORDER  # type: ignore  # noqa: E402

# Attributes flagged "ayrıştırıcı" (discriminating) in TAXONOMY.md — the same set
# make_artifact.py marks with a diamond.
DISTINCTIVE = set(
    "A04 A07 A09 C03 C04 C08 D02 D04 D09 D10 D11 D12 E06 F04 F05 F07 F09 "
    "G03 G07 G08 G11 G12 G13 H04 H07 I06 I08 I09 I10 I12".split()
)


def _load_banks() -> dict[str, dict]:
    banks: dict[str, dict] = {}
    for f in DATA.glob("*.json"):
        if f.name.startswith("_") or f.name in {"profiles_en.json"}:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        banks[d["ticker"]] = d
    return banks


def _validate(banks: dict[str, dict]) -> None:
    """Fail loudly on the two invariants the page depends on."""
    missing_en = [c for c in CODES if c not in LABELS_EN]
    if missing_en:
        raise SystemExit(f"labels_en.py missing English for: {missing_en}")
    for t, d in banks.items():
        mc = [c for c in CODES if c not in d.get("attributes", {})]
        if mc:
            raise SystemExit(f"{t}: attributes missing codes {mc}")
        for c in CODES:
            a = d["attributes"][c]
            if a.get("v") in ("yes", "partial") and not a.get("url"):
                raise SystemExit(
                    f"{t} {c}: value '{a['v']}' with no evidence_url — uncited claim"
                )


def build(conn: sqlite3.Connection) -> dict[str, int]:
    init_schema(conn)
    banks = _load_banks()
    _validate(banks)
    present = [t for t in ORDER if t in banks]
    cl_of = {t: name for name, bs in CLUSTERS for t in bs}
    profiles_en = json.loads((DATA / "profiles_en.json").read_text(encoding="utf-8"))

    cur = conn.cursor()
    # Catalog: full replace (it is not snapshot-scoped).
    cur.execute("DELETE FROM product_attributes")
    cur.executemany(
        "INSERT INTO product_attributes "
        "(code, block, block_name_en, label_en, label_tr, is_distinctive, sort_order) "
        "VALUES (?,?,?,?,?,?,?)",
        [
            (c, c[0], BLOCKS_EN[c[0]], LABELS_EN[c], LABELS.get(c),
             1 if c in DISTINCTIVE else 0, i)
            for i, c in enumerate(CODES)
        ],
    )

    # Cells + profile: replace only THIS snapshot (history for other dates stays).
    cur.execute("DELETE FROM bank_products WHERE snapshot_date = ?", (SNAPSHOT_DATE,))
    cur.execute(
        "DELETE FROM bank_product_profile WHERE snapshot_date = ?", (SNAPSHOT_DATE,)
    )

    cells = []
    profiles = []
    for t in present:
        d = banks[t]
        c = Counter(d["attributes"][x]["v"] for x in CODES)
        ver = c["yes"] + c["no"] + c["partial"]
        shelf = (c["yes"] + 0.5 * c["partial"]) / ver if ver else 0.0
        coverage = ver / len(CODES)
        p_en = profiles_en.get(t, {})
        profiles.append((
            t, SNAPSHOT_DATE, CLUSTERS_EN.get(cl_of[t], cl_of[t]),
            round(shelf, 4), round(coverage, 4),
            c["yes"], c["no"], c["partial"], c["unknown"],
            p_en.get("shelf_notes_en"),
            json.dumps(p_en.get("distinctive_en", []), ensure_ascii=False),
        ))
        for x in CODES:
            a = d["attributes"][x]
            cells.append((
                t, x, a["v"], a.get("note") or None, a.get("url") or None,
                SNAPSHOT_DATE,
            ))

    cur.executemany(
        "INSERT INTO bank_products "
        "(bank_ticker, attr_code, value, note, evidence_url, snapshot_date) "
        "VALUES (?,?,?,?,?,?)",
        cells,
    )
    cur.executemany(
        "INSERT INTO bank_product_profile "
        "(bank_ticker, snapshot_date, cluster_en, shelf, coverage, "
        " n_yes, n_no, n_partial, n_unknown, shelf_notes_en, distinctive_en) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        profiles,
    )
    conn.commit()
    return {"attributes": len(CODES), "cells": len(cells), "profiles": len(profiles)}


def main() -> int:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "bddk_data.db"
    with sqlite3.connect(db) as conn:
        counts = build(conn)
    print(
        f"Loaded product-shelf snapshot {SNAPSHOT_DATE} into {db}: "
        f"{counts['attributes']} attributes, {counts['cells']} cells, "
        f"{counts['profiles']} profiles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
