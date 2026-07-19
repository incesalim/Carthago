"""Health check for the public data API (/api/v1). Alert-only.

Probes the LIVE endpoints and verifies they answer with real data. Run daily
from healthcheck.yml.

WHY THIS USES stdlib urllib AND MUST KEEP DOING SO
--------------------------------------------------
Cloudflare's Browser Integrity Check rejects known-bot user agents with 403 /
CF error 1010 *at the edge*, before the request reaches the Worker. Python's
stdlib default `Python-urllib/3.x` is one of them — and `pandas.read_csv`
fetches URLs through stdlib urllib, so that block took out the single most
natural way to consume this API.

A Configuration Rule (`starts_with(http.request.uri.path, "/api/v1")` ->
Browser Integrity Check Off) exempts the API path. That rule is part of the
API's contract, it lives in zone config that this repo cannot see, and it
**fails invisibly**: `requests`, `httpx`, `curl` and browsers are never blocked,
so every ordinary smoke test keeps returning 200 while real callers get 403.

So this probe deliberately sends NO User-Agent, which makes urllib send the
blocked signature. Do NOT "improve" this by switching to requests or by setting
a User-Agent header — that would silently defeat the entire check.

Usage:
    python scripts/check_public_api.py
    python scripts/check_public_api.py --alert          # Telegram/Discord on failure
    python scripts/check_public_api.py --base https://carthago.app

Exit code 1 if any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_BASE = "https://carthago.app"
TIMEOUT = 30

# A series that must always resolve: balance sheet, first line, whole sector.
# T01/10001 is the most stable address in the catalog — if BDDK ever stops
# publishing it, the whole dashboard is broken too, so this is a fair canary.
CANARY = "BDDK.T01.I001.10001.TOT"


def fetch(url: str) -> tuple[int, str]:
    """GET with stdlib defaults. Returns (status, body). Never raises on HTTP."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # DNS, TLS, timeout
        return 0, f"{type(e).__name__}: {e}"


def bic_hint(body: str) -> str:
    """Name the real cause when Cloudflare's edge is the one saying no."""
    if "1010" in body:
        return (
            " — Cloudflare error 1010 (Browser Integrity Check). The "
            '`API v1` Configuration Rule (starts_with(http.request.uri.path, '
            '"/api/v1") -> Browser Integrity Check Off) is missing or its '
            "expression is broken. See docs/OPERATIONS.md."
        )
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--alert", action="store_true",
                    help="send a Telegram/Discord alert on failure")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    failures: list[str] = []

    # 1) Index — also tells us the catalog is populated.
    status, body = fetch(f"{base}/api/v1")
    if status != 200:
        failures.append(f"GET /api/v1 -> HTTP {status}{bic_hint(body)}")
    else:
        try:
            n = json.loads(body).get("coverage", {}).get("series", 0)
            if not n:
                failures.append("GET /api/v1 -> coverage.series is 0 "
                                "(api_series is empty in D1 — the catalog push "
                                "did not land; see docs/OPERATIONS.md)")
            else:
                print(f"  /api/v1                  OK  ({n:,} series)")
        except json.JSONDecodeError:
            failures.append("GET /api/v1 -> not JSON")

    # 2) Observations — the endpoint that actually matters.
    status, body = fetch(f"{base}/api/v1/series?series={CANARY}")
    if status != 200:
        failures.append(f"GET /api/v1/series -> HTTP {status}{bic_hint(body)}")
    else:
        try:
            obs = json.loads(body)["series"][0]["observations"]
            if not obs:
                failures.append(f"GET /api/v1/series -> {CANARY} returned 0 "
                                "observations (catalog row resolves to nothing)")
            else:
                print(f"  /api/v1/series           OK  ({len(obs)} obs, "
                      f"latest {obs[-1]['date']})")
        except (json.JSONDecodeError, KeyError, IndexError):
            failures.append(f"GET /api/v1/series -> {CANARY} missing from response")

    # 3) Discovery — a caller with no codes starts here.
    status, body = fetch(f"{base}/api/v1/serieList?dataset=T01&limit=1")
    if status != 200:
        failures.append(f"GET /api/v1/serieList -> HTTP {status}{bic_hint(body)}")
    else:
        try:
            total = json.loads(body).get("meta", {}).get("total", 0)
            if not total:
                failures.append("GET /api/v1/serieList -> dataset T01 is empty")
            else:
                print(f"  /api/v1/serieList        OK  (T01: {total:,} series)")
        except json.JSONDecodeError:
            failures.append("GET /api/v1/serieList -> not JSON")

    # 4) The exemption must stay SCOPED. This same user agent should still be
    #    turned away from the dashboard; a 200 here means Browser Integrity
    #    Check was switched off zone-wide instead of for /api/v1 only.
    status, _ = fetch(f"{base}/")
    if status == 200:
        print("  NOTE: / also serves a known-bot UA — Browser Integrity Check "
              "looks disabled zone-wide rather than scoped to /api/v1. "
              "Not fatal, but re-scope it (docs/OPERATIONS.md).")
    else:
        print(f"  / (bot protection)       OK  (HTTP {status} to a bot UA)")

    if failures:
        msg = "❌ Public API health check failed:\n" + "\n".join(f"• {f}" for f in failures)
        print(msg, file=sys.stderr)
        if args.alert:
            sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
            from notify import notify  # stdlib-only helper
            notify(msg)
        return 1

    print("public API OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
