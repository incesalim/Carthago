"""Refresh bank ownership structure from KAP (kap.org.tr) into SQLite.

For every bank in ``data/banks/kap_company_map.json``, fetches the KAP
"Genel Bilgi Formu" page (server-rendered — plain requests, no API key) and
replaces the bank's rows in ``kap_ownership`` in the bulletin-lane DB
(``data/bddk_data.db``). ``scripts/push_to_d1.py`` then syncs the rows to
Cloudflare D1; if a bank's grid shrank, the loader queues DELETEs in
``d1_pending_deletes`` which the push replays remotely.

Runs weekly as a non-critical step of ``scripts/refresh.py`` (Saturday
``refresh-data.yml`` cron). A KAP outage or per-bank parse failure keeps the
previous rows in place — partitions are only replaced on a successful parse.

Usage:
  python scripts/update_kap_ownership.py                  # all mapped banks
  python scripts/update_kap_ownership.py --banks AKBNK,ZIRAAT
  python scripts/update_kap_ownership.py --discover       # (re)build the map
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.kap.client import fetch_company_items, fetch_directory  # noqa: E402
from src.kap.loader import replace_bank_rows                     # noqa: E402
from src.kap.parser import ownership_rows                        # noqa: E402
from src.kap.schema import init_schema                           # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"
MAP_PATH = REPO_ROOT / "data" / "banks" / "kap_company_map.json"
AUDIT_URLS = REPO_ROOT / "data" / "banks" / "audit_report_urls.json"
SLEEP_BETWEEN_BANKS = 1.0  # polite pacing; ~35 requests total

_TR = str.maketrans("ÇĞİÖŞÜçğıöşüÂâÎîÛû", "CGIOSUcgiosuAaIiUu")


def _norm(name: str) -> str:
    """Diacritic-free uppercase alnum, corporate suffixes dropped."""
    t = name.translate(_TR).upper()
    for suffix in ("TURK ANONIM SIRKETI", "ANONIM SIRKETI", "T.A.S.", "A.S.",
                   "T.A.S", "A.S", "TAS", "AS"):
        t = t.replace(suffix, " ")
    return "".join(ch for ch in t if ch.isalnum())


def discover() -> int:
    """Match our audit-lane banks against the KAP company directory."""
    banks = json.loads(AUDIT_URLS.read_text(encoding="utf-8"))["banks"]
    print(f"Resolving {len(banks)} audit banks against the KAP directory …", flush=True)
    directory = fetch_directory()
    print(f"KAP directory: {len(directory)} companies", flush=True)
    by_norm = {_norm(e["title"]): e for e in directory}

    existing = {}
    if MAP_PATH.exists():
        existing = json.loads(MAP_PATH.read_text(encoding="utf-8")).get("banks", {})

    out, unmatched = {}, []
    for ticker, cfg in sorted(banks.items()):
        prev = existing.get(ticker)
        if prev and prev.get("manual"):
            out[ticker] = prev  # hand-pinned mapping wins over re-discovery
            print(f"  {ticker}: kept manual mapping → {prev['slug']}")
            continue
        name = cfg["name"]
        key = _norm(name)
        hit = by_norm.get(key)
        if not hit:  # containment fallback (e.g. 'T.C. ZİRAAT BANKASI' vs KAP title)
            cands = [e for n, e in by_norm.items() if key and (key in n or n in key)]
            hit = cands[0] if len(cands) == 1 else None
        if hit:
            out[ticker] = {
                "kap_id": int(hit["permaLink"].split("-", 1)[0]),
                "slug": hit["permaLink"],
                "kap_title": hit["title"],
                "mkk_member_oid": hit.get("mkkMemberOid"),
            }
            print(f"  {ticker}: {name} → {hit['permaLink']}")
        else:
            unmatched.append({"ticker": ticker, "name": name})
            print(f"  {ticker}: NO MATCH for {name!r}")

    MAP_PATH.write_text(json.dumps({
        "_doc": "Bank → KAP company mapping for the kap_ownership lane. "
                "Rebuilt with scripts/update_kap_ownership.py --discover; entries "
                "with \"manual\": true are hand-pinned and survive re-discovery.",
        "_generated": date.today().isoformat(),
        "banks": out,
        "unmatched": unmatched,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {MAP_PATH.relative_to(REPO_ROOT)}: "
          f"{len(out)} matched, {len(unmatched)} unmatched.", flush=True)
    return 0 if out else 1


def refresh(db_path: Path, only: set[str] | None) -> int:
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))["banks"]
    targets = {t: m for t, m in mapping.items() if not only or t in only}
    if not targets:
        print("No banks selected.", flush=True)
        return 1

    ok = skipped = failed = total_rows = 0
    with sqlite3.connect(str(db_path)) as conn:
        init_schema(conn)
        for ticker, m in sorted(targets.items()):
            try:
                items = fetch_company_items(m["slug"])
                rows = ownership_rows(ticker, m["kap_title"], m["kap_id"], items)
                if not rows:
                    # No published form, or §5 missing — keep previous rows.
                    print(f"  {ticker}: no §5 items — kept previous rows", flush=True)
                    skipped += 1
                    continue
                n, removed = replace_bank_rows(conn, ticker, rows)
                for bt, item, seq in removed:
                    conn.execute(
                        "INSERT INTO d1_pending_deletes (sql) VALUES (?)",
                        ("DELETE FROM kap_ownership WHERE bank_ticker='{0}' "
                         "AND item='{1}' AND seq={2};".format(bt, item, seq),),
                    )
                conn.commit()
                holders = sum(1 for r in rows if r.item == "shareholder")
                note = f", {len(removed)} stale keys queued for D1 delete" if removed else ""
                print(f"  {ticker}: {n} rows ({holders} shareholder lines){note}", flush=True)
                ok += 1
                total_rows += n
            except Exception as exc:  # noqa: BLE001 — one bank must not kill the run
                print(f"  {ticker}: FAILED — {exc}", flush=True)
                failed += 1
            time.sleep(SLEEP_BETWEEN_BANKS)

        count = conn.execute("SELECT COUNT(*) FROM kap_ownership").fetchone()[0]
    print(f"\nDone. {ok} banks refreshed ({total_rows} rows), "
          f"{skipped} skipped, {failed} failed; table holds {count} rows.", flush=True)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    ap.add_argument("--banks", default=None,
                    help="Comma-separated ticker subset (default: all mapped)")
    ap.add_argument("--discover", action="store_true",
                    help="Rebuild data/banks/kap_company_map.json from the KAP "
                         "directory instead of refreshing ownership rows")
    args = ap.parse_args()

    if args.discover:
        return discover()
    only = {t.strip().upper() for t in args.banks.split(",")} if args.banks else None
    return refresh(Path(args.db), only)


if __name__ == "__main__":
    raise SystemExit(main())
