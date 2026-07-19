"""Cache BDDK's OFFICIAL English labels for the monthly tables (1-17).

BDDK publishes the same monthly bulletin in both languages: the scraper's
endpoint is `.../BultenAylik/tr/Home/BasitRaporGetir`, and swapping `tr` for
`en` returns identical rows in identical order with English labels. Verified
2026-07-19: all 17 tables, same row count in both languages.

These are BDDK's own words, not a translation of ours. That matters — these are
regulatory line items ("Beklenen Zarar Karşılıkları", "Gerçeğe Uygun Değer Farkı
K/Z Yan. Menk. Değ.") where an invented rendering would quietly misname a
supervisory concept. If BDDK has no English for a line, we leave it blank rather
than guess.

Output: data/bddk_labels_en.json, keyed "<table_no>:<item_order>" -> label.
Cached in the repo so the catalog build stays offline and deterministic; labels
change about as often as the report template does, i.e. rarely.

Usage:
    python scripts/fetch_bddk_english_labels.py             # refresh the cache
    python scripts/fetch_bddk_english_labels.py --check     # report drift, write nothing
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.scrapers._http import bddk_verify  # noqa: E402

OUT = ROOT / "data" / "bddk_labels_en.json"
URL = "https://www.bddk.org.tr/BultenAylik/{lang}/Home/BasitRaporGetir"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
}
TABLES = range(1, 18)

# A period every table is known to be filed for. The labels are template-level,
# so any well-populated month yields the same set.
PROBE_YEAR, PROBE_MONTH = 2026, 4
SECTOR = "10001"          # whole sector — the widest row set
DELAY = 0.6               # be polite; this is 17 requests


def fetch_labels(table_no: int, lang: str) -> dict[int, str]:
    """(item_order -> label) for one table in one language."""
    payload = {
        "tabloNo": str(table_no), "yil": str(PROBE_YEAR), "ay": str(PROBE_MONTH),
        "paraBirimi": "TL", "taraf[0]": SECTOR,
    }
    r = requests.post(URL.format(lang=lang), headers=HEADERS, data=payload,
                      timeout=30, verify=bddk_verify())
    r.raise_for_status()
    j = r.json().get("Json", {})
    cols = {m.get("name", ""): i for i, m in enumerate(j.get("colModels", []))}
    order_ix = cols.get("BasitSira", 1)
    name_ix = cols.get("Ad", 2)
    out: dict[int, str] = {}
    for row in j.get("data", {}).get("rows", []):
        cells = row.get("cell", [])
        if len(cells) <= max(order_ix, name_ix):
            continue
        try:
            order = int(str(cells[order_ix]).strip())
        except (TypeError, ValueError):
            continue
        label = str(cells[name_ix] or "").strip()
        if label:
            out[order] = label
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the cached file; write nothing")
    args = ap.parse_args()

    labels: dict[str, str] = {}
    mismatches: list[str] = []

    for t in TABLES:
        try:
            en = fetch_labels(t, "en")
            tr = fetch_labels(t, "tr")
        except Exception as e:
            print(f"  T{t:<3} FAILED: {type(e).__name__}: {str(e)[:60]}")
            continue

        # The two languages must describe the SAME rows. A count mismatch means
        # the English template has drifted and item_order can no longer be
        # trusted to align — skip rather than mislabel every line in the table.
        if len(en) != len(tr):
            mismatches.append(f"T{t}: tr={len(tr)} rows vs en={len(en)} — SKIPPED")
            print(f"  T{t:<3} SKIP  tr={len(tr)} en={len(en)} (row sets diverge)")
            continue

        for order, label in en.items():
            labels[f"{t}:{order}"] = label
        print(f"  T{t:<3} {len(en):3} labels   e.g. {list(en.values())[0][:44]}")
        time.sleep(DELAY)

    if not labels:
        print("ERROR: no labels fetched — refusing to overwrite the cache",
              file=sys.stderr)
        return 1

    if args.check:
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        added = set(labels) - set(old)
        removed = set(old) - set(labels)
        changed = {k for k in set(labels) & set(old) if labels[k] != old[k]}
        print(f"\ncheck: {len(added)} added, {len(removed)} removed, "
              f"{len(changed)} changed")
        for k in sorted(changed)[:10]:
            print(f"  {k}: {old[k]!r} -> {labels[k]!r}")
        return 1 if (added or removed or changed) else 0

    OUT.write_text(json.dumps(labels, ensure_ascii=False, indent=1,
                              sort_keys=True), encoding="utf-8")
    print(f"\nwrote {len(labels)} English labels to {OUT.relative_to(ROOT)}")
    if mismatches:
        print("WARNING — tables skipped (row sets diverge between languages):")
        for m in mismatches:
            print(f"  {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
