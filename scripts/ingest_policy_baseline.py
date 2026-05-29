"""Ingest TCMB's annual "Monetary Policy for YYYY" document as the briefing
baseline.

That document (its Annex tables 1-6) is the authoritative current-status of
the whole regulatory regime as of the start of the year — policy-rate path,
macroprudential simplification, deposits, liquidity, loans, credit programs.
summarize_regulations.py grounds the snapshot on the latest baseline row and
then layers the year's raw feed on top, which makes the output both complete
(Credit Cards / CAR are seeded by the baseline) and consistent (the model
edits a known scaffold instead of free-composing).

Auto-discovery isn't reliable — the doc isn't in any scrapable press-release
feed or index — so this is a pin: pass the PDF URL (or a local path) once a
year (TCMB publishes it in late December). Idempotent: re-running with the
same content is a no-op (content hash unchanged).

Usage:
  python scripts/ingest_policy_baseline.py --year 2026 --url "https://www.tcmb.gov.tr/.../December28.pdf?..."
  python scripts/ingest_policy_baseline.py --year 2026 --file path/to/MonetaryPolicy2026.pdf
  python scripts/ingest_policy_baseline.py --list          # show stored baselines
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.news.schema import init_schema  # noqa: E402

DB_PATH = REPO_ROOT / "data" / "bddk_data.db"
CONTENT_CAP = 40_000  # chars (~13k tokens) — full doc incl. annex tables fits

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}


def extract_pdf_text(data: bytes) -> str:
    """Extract text from the policy PDF, annex tables included. pdfplumber's
    line extraction renders the date-keyed annex tables readably enough for
    the LLM to parse."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    return text[:CONTENT_CAP]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, help="Policy year the document covers (e.g. 2026)")
    ap.add_argument("--url", help="URL of the Monetary Policy PDF")
    ap.add_argument("--file", help="Local path to the Monetary Policy PDF")
    ap.add_argument("--title", default=None, help="Override stored title")
    ap.add_argument("--list", action="store_true", help="List stored baselines and exit")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        init_schema(conn)

        if args.list:
            rows = conn.execute(
                "SELECT year, title, length(content), fetched_at FROM regulation_baseline ORDER BY year DESC"
            ).fetchall()
            if not rows:
                print("(no baselines stored)")
            for y, t, n, f in rows:
                print(f"  {y}  {n:>6} chars  fetched {f}  {t}")
            return 0

        if not args.year or not (args.url or args.file):
            ap.error("--year and one of --url/--file are required (or use --list)")

        if args.file:
            data = Path(args.file).read_bytes()
            src = str(Path(args.file).resolve())
        else:
            print(f"[baseline] downloading {args.url[:80]}...", flush=True)
            r = requests.get(args.url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            data = r.content
            src = args.url

        content = extract_pdf_text(data)
        if len(content) < 500:
            print(f"[baseline] WARNING: extracted only {len(content)} chars — check the source", flush=True)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        title = args.title or f"Monetary Policy for {args.year}"

        existing = conn.execute(
            "SELECT content_hash FROM regulation_baseline WHERE year = ?", (args.year,)
        ).fetchone()
        if existing and existing[0] == content_hash:
            print(f"[baseline] {args.year} unchanged (hash match) — no-op.")
            return 0

        conn.execute(
            """INSERT OR REPLACE INTO regulation_baseline
               (year, title, source_url, content, content_hash, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (args.year, title, src, content, content_hash,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        print(f"[baseline] stored {args.year}: {len(content)} chars "
              f"(hash {content_hash[:12]}) from {src[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
