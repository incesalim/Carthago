"""Weekly generator for "The Read" LLM headlines (perspective layer, Option 1).

Reads the deterministic takeaways from {SITE_URL}/api/reads, skips tabs whose
`det_hash` is unchanged since the last run (queried from read_headlines), rewrites
the rest with a free model (src/news/free_llm.py: Cerebras gpt-oss-120b → Groq →
gemma), and upserts read_headlines in remote D1 via wrangler.

The dashboard shows a rewrite ONLY while its det_hash still matches the live page
(web/app/lib/read-headlines.ts), so a failed/stale row is harmless — the tab just
shows the deterministic sentence.

Usage:
  python scripts/generate_read_headlines.py            # generate changed tabs
  python scripts/generate_read_headlines.py --dry-run  # print, don't write D1
  python scripts/generate_read_headlines.py --force     # regenerate all tabs

Env: SITE_URL (default prod), CEREBRAS_KEY, GROQ_API_KEY, CLOUDFLARE_API_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.news import free_llm  # noqa: E402

DEFAULT_SITE = "https://turkish-banking-dashboard.incesalim10.workers.dev"
D1_NAME = "bddk-data"


def _wrangler(args: list[str], capture: bool) -> subprocess.CompletedProcess:
    cmd = ["npx", "--yes", "wrangler", "d1", "execute", D1_NAME, "--remote", *args]
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(
        cmd, cwd=str(WEB), shell=os.name == "nt",
        capture_output=capture, text=True, encoding="utf-8",
    )


def fetch_reads(site: str) -> list[dict]:
    r = requests.get(f"{site}/api/reads", timeout=90)
    r.raise_for_status()
    return r.json()


def existing_hashes() -> dict[str, str]:
    """Current {tab: det_hash} from D1. Empty if the table is missing (first run)."""
    res = _wrangler(
        ["--command", "SELECT tab, det_hash FROM read_headlines", "--json"],
        capture=True,
    )
    if res.returncode != 0:
        print("  (read_headlines not queryable yet — treating all tabs as new)", flush=True)
        return {}
    try:
        data = json.loads(res.stdout)
        rows = data[0]["results"] if isinstance(data, list) else data["results"]
        return {r["tab"]: r["det_hash"] for r in rows}
    except Exception as e:  # noqa: BLE001
        print(f"  (couldn't parse existing hashes: {e})", flush=True)
        return {}


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def upsert(rows: list[dict]) -> int:
    """INSERT OR REPLACE the given rows via a wrangler --file execute."""
    values = ",\n".join(
        "(" + ",".join([
            _sql_str(r["tab"]), _sql_str(r["det_hash"]), _sql_str(r["headline"]),
            _sql_str(r["model"]), _sql_str(r["generated_at"]),
        ]) + ")"
        for r in rows
    )
    sql = (
        "INSERT OR REPLACE INTO read_headlines "
        "(tab, det_hash, headline, model, generated_at) VALUES\n" + values + ";\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
        fh.write(sql)
        path = Path(fh.name)
    try:
        res = _wrangler([f"--file={path}"], capture=False)
        return res.returncode
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    # `or` (not dict-default): the CI env sets SITE_URL to "" when the repo var
    # is unset, which would otherwise slip past a get(...) default.
    ap.add_argument("--site", default=os.environ.get("SITE_URL") or DEFAULT_SITE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if a tab's det_hash is unchanged.")
    args = ap.parse_args()

    reads = fetch_reads(args.site)
    print(f"[reads] {len(reads)} tabs from {args.site}/api/reads", flush=True)
    existing = {} if args.force else existing_hashes()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    updates: list[dict] = []
    for rd in reads:
        tab, headline = rd["tab"], rd["headline"]
        items, det_hash = rd.get("items", []), rd["det_hash"]
        if not args.force and existing.get(tab) == det_hash:
            print(f"[{tab}] unchanged — skip", flush=True)
            continue
        new, model = free_llm.rewrite_headline(headline, items)
        if not new:
            print(f"[{tab}] no valid rewrite — leaving deterministic", flush=True)
            continue
        print(f"[{tab}] via {model}: {new}", flush=True)
        updates.append({"tab": tab, "det_hash": det_hash, "headline": new,
                        "model": model, "generated_at": now})

    if not updates:
        print("[done] nothing to update.", flush=True)
        return 0
    if args.dry_run:
        print(f"[dry-run] would upsert {len(updates)} row(s).", flush=True)
        return 0

    rc = upsert(updates)
    if rc != 0:
        print(f"[error] wrangler upsert failed ({rc})", file=sys.stderr)
        return rc
    print(f"[done] upserted {len(updates)} headline(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
