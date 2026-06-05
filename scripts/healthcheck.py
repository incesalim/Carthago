"""Daily data-freshness health check against D1 → alert via notify() when a
source is stale or audit extractions are failing.

Run in CI with CLOUDFLARE_API_TOKEN (for wrangler) and the Telegram/Discord
secrets set. Exits 0 even when it alerts — the webhook *is* the alert, so we
don't also spam GitHub failure emails. Prints a summary either way.

  python scripts/healthcheck.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import notify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# (key, label, max_age_hours). Audit is excluded from staleness (banks publish
# quarterly) — it's covered by the failure-count check instead.
THRESHOLDS = [
    ("monthly", "Monthly bulletin", 192),  # weekly cron (168h) + margin
    ("weekly", "Weekly bulletin", 192),
    ("evds", "EVDS rates/FX", 48),  # daily cron (24h) + margin
    ("news", "News", 48),
]
AUDIT_FAILED_ALERT = 25  # baseline known-partial extractions is ~20

SQL = (
    "SELECT "
    "(SELECT MAX(downloaded_at) FROM balance_sheet) AS monthly,"
    "(SELECT MAX(downloaded_at) FROM weekly_series) AS weekly,"
    "(SELECT MAX(downloaded_at) FROM evds_series) AS evds,"
    "(SELECT MAX(fetched_at) FROM news_items) AS news,"
    "(SELECT MAX(extracted_at) FROM bank_audit_extractions) AS audit,"
    "(SELECT COUNT(*) FROM bank_audit_extractions WHERE success=0) AS audit_failed"
)


def hours_since(ts: str | None) -> float | None:
    if not ts:
        return None
    norm = ts if "T" in ts else ts.replace(" ", "T")
    iso = norm.replace("Z", "") + "+00:00" if not norm.endswith("+00:00") else norm
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def query_d1() -> dict:
    cmd = [
        "npx", "--yes", "wrangler", "d1", "execute", "bddk-data",
        "--remote", "--json", "--command", SQL,
    ]
    res = subprocess.run(
        cmd, cwd=str(WEB), capture_output=True, text=True, shell=os.name == "nt"
    )
    if res.returncode != 0:
        raise RuntimeError(f"wrangler exit {res.returncode}: {res.stderr[-500:]}")
    data = json.loads(res.stdout)
    rows = (data[0] if isinstance(data, list) else data)["results"]
    if not rows:
        raise RuntimeError("query returned no rows")
    return rows[0]


def main() -> int:
    try:
        row = query_d1()
    except Exception as e:
        notify(f"⚠️ BDDK health-check could not query D1: {e}")
        print(f"health-check error: {e}", file=sys.stderr)
        return 0

    problems: list[str] = []
    for key, label, max_age in THRESHOLDS:
        age = hours_since(row.get(key))
        if age is None:
            problems.append(f"{label}: no data")
        elif age > max_age:
            problems.append(f"{label}: stale ({age / 24:.1f}d old, limit {max_age // 24}d)")

    failed = row.get("audit_failed") or 0
    if failed > AUDIT_FAILED_ALERT:
        problems.append(f"Audit extractions failing: {failed} (baseline ~20)")

    if problems:
        msg = "🟡 BDDK data health:\n- " + "\n- ".join(problems)
        notify(msg)
        print(msg)
    else:
        print("✅ all sources fresh; audit extractions nominal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
