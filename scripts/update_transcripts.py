"""Refresh the earnings-call transcript rows in bank_call_transcripts.

For each bank in data/banks/call_transcript_sources.json, read the call archive
off the source's index page and fetch any quarter not already stored. Idempotent:
rows are keyed (source, bank_ticker, period), so a re-run overwrites in place.

Default behaviour is incremental — only quarters missing from the DB are fetched,
which after the first full run means one index GET per bank and nothing else.
``--refresh`` refetches everything (use when the parser changes, not routinely).

Usage:
  python scripts/update_transcripts.py                        # all banks, incremental
  python scripts/update_transcripts.py --banks AKBNK,GARAN
  python scripts/update_transcripts.py --banks ALL --refresh
  python scripts/update_transcripts.py --json-dir data/transcripts

The `--banks` sentinel matters for CI: a workflow_dispatch input left blank does
NOT arrive empty, the default wins, so the scope is spelled ALL/NONE explicitly
and echoed once resolved.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from src.transcripts.alphaspread import (  # noqa: E402
    MIN_PERIOD,
    Call,
    discover_quarters,
    parse_call,
)
from src.transcripts.loader import existing_periods, upsert_calls  # noqa: E402
from src.transcripts.schema import init_schema  # noqa: E402

CONFIG = REPO / "data" / "banks" / "call_transcript_sources.json"
DB_PATH = REPO / "data" / "bddk_data.db"

# Gap between page fetches. Not just courtesy — at 1.0s the source starts
# returning 429 around the 70th page of a full-corpus run and stays tripped, which
# on the first run cost five banks their index fetch. 3s plus the fetcher's
# backoff (src/transcripts/alphaspread._get) walks the whole archive cleanly.
DELAY_S = 3.0


def _resolve_banks(arg: str, configured: list[str]) -> list[str]:
    token = (arg or "").strip().upper()
    if token in ("", "ALL"):
        return configured
    if token == "NONE":
        return []
    wanted = [t.strip().upper() for t in token.split(",") if t.strip()]
    unknown = sorted(set(wanted) - set(configured))
    if unknown:
        raise SystemExit(
            f"--banks names bank(s) with no transcript source configured: "
            f"{', '.join(unknown)}. Known: {', '.join(configured)}. "
            f"(SKBNK/QNBFB/ICBCT hold no call — see _deferred in {CONFIG.name}.)"
        )
    return wanted


def _fetch_bank(ticker: str, slug: str, have: set[str], *,
                refresh: bool, limit: int | None) -> tuple[list[Call], list[str]]:
    """Fetched calls + a list of human-readable failures for one bank."""
    failures: list[str] = []
    try:
        periods = discover_quarters(slug)
    except Exception as e:  # noqa: BLE001 — one bank's outage must not stop the lane
        return [], [f"{ticker}: index unreachable ({type(e).__name__}: {e})"]

    if not periods:
        print(f"[calls] {ticker}: no calls published (source archive is empty)",
              flush=True)
        return [], []

    todo = periods if refresh else [p for p in periods if p not in have]
    todo = sorted(todo, reverse=True)[:limit] if limit else todo

    calls: list[Call] = []
    for i, period in enumerate(todo):
        try:
            call = parse_call(ticker, slug, period)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{ticker} {period}: fetch failed ({type(e).__name__}: {e})")
            continue
        if not call.turns:
            failures.append(f"{ticker} {period}: page fetched but no turns parsed")
            continue
        calls.append(call)
        if i < len(todo) - 1:
            time.sleep(DELAY_S)

    skipped = len(periods) - len(todo)
    print(f"[calls] {ticker}: {len(calls)} fetched, {skipped} already stored, "
          f"{len(periods)} in archive ({periods[0]}..{periods[-1]})", flush=True)
    return calls, failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--banks", default="ALL",
                    help="ALL | NONE | comma-separated tickers")
    ap.add_argument("--refresh", action="store_true",
                    help="refetch quarters already stored (parser changes only)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap fetches per bank (newest first)")
    ap.add_argument("--json-dir", default=None,
                    help="also write one JSON file per call for local inspection")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    banks: dict[str, dict] = cfg.get("banks", {})
    tickers = _resolve_banks(args.banks, list(banks))
    print(f"[calls] scope resolved to {len(tickers)} bank(s): "
          f"{', '.join(tickers) or '(none)'}  · min period {MIN_PERIOD}", flush=True)
    if not tickers:
        return 0

    json_dir = Path(args.json_dir) if args.json_dir else None
    if json_dir:
        json_dir.mkdir(parents=True, exist_ok=True)

    total, failures = 0, []
    with sqlite3.connect(args.db) as conn:
        init_schema(conn)
        for ticker in tickers:
            have = set() if args.refresh else existing_periods(conn, ticker)
            calls, fails = _fetch_bank(
                ticker, banks[ticker]["slug"], have,
                refresh=args.refresh, limit=args.limit,
            )
            failures.extend(fails)
            total += upsert_calls(conn, calls)
            for call in calls:
                if json_dir:
                    (json_dir / f"{ticker}_{call.period}.json").write_text(
                        json.dumps({
                            "bank_ticker": ticker, "period": call.period,
                            "call_date": call.call_date, "source_url": call.source_url,
                            "turns": [t.as_dict() for t in call.turns],
                        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[calls] upserted {total} call(s) across {len(tickers)} bank(s)")
    for f in failures:
        print(f"[calls] FAILED — {f}", file=sys.stderr)
    # Failures are reported, not fatal: a single unreachable quarter must not
    # abort a run that successfully refreshed every other bank.
    return 0


if __name__ == "__main__":
    sys.exit(main())
