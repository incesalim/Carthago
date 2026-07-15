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
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import notify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# (key, label, max_age_hours). Age-based staleness for the sources that publish
# on a steady cadence. The MONTHLY bulletin is NOT here — it publishes ~once a
# month with a variable 4–11 week lag, and the non-destructive upsert freezes
# `downloaded_at` the day a month lands, so an age check reads "stale" for the
# weeks between releases even when we hold the latest data. It gets a
# schedule-aware check instead (see monthly_problem). Audit is excluded from
# staleness (banks publish quarterly) — it's covered by the failure count.
THRESHOLDS = [
    ("weekly", "Weekly bulletin", 192),
    ("evds", "EVDS rates/FX", 48),  # daily cron (24h) + margin
    ("news", "News", 48),
    # Checked on the latest DATA date (not downloaded_at, which refreshes even
    # when TEFAS publishes nothing) so publishing breaks are caught. 120h
    # survives normal long weekends; multi-day religious holidays (Kurban)
    # may fire one benign alert.
    ("tefas", "TEFAS funds", 120),
]
AUDIT_FAILED_ALERT = 25  # baseline known-partial extractions is ~20

# Days past the expected monthly release before a missing month is worth an
# alert (mirrors MONTHLY_OVERDUE_GRACE_DAYS in web/app/lib/admin-health.ts).
MONTHLY_OVERDUE_GRACE_DAYS = 14

SQL = (
    "SELECT "
    "(SELECT PRINTF('%04d-%02d', year, month) FROM balance_sheet "
    " ORDER BY year DESC, month DESC LIMIT 1) AS monthly_period,"
    "(SELECT MAX(downloaded_at) FROM weekly_series) AS weekly,"
    "(SELECT MAX(downloaded_at) FROM evds_series) AS evds,"
    "(SELECT MAX(fetched_at) FROM news_items) AS news,"
    "(SELECT MAX(date) FROM tefas_manager_daily) AS tefas,"
    "(SELECT MAX(extracted_at) FROM bank_audit_extractions) AS audit,"
    "(SELECT COUNT(*) FROM bank_audit_extractions WHERE success=0) AS audit_failed"
)


def next_monthly_due(period: str) -> date | None:
    """When the NEXT monthly bulletin is due, given the latest month held.

    Mirrors nextMonthlyBulletinDue() in web/app/lib/ahead.ts: month M lands ~the
    12th of month M+2, so the month AFTER `period` (M+1) is due ~day 12 of M+3.
    """
    if not period or len(period) < 7:
        return None
    y, m = int(period[:4]), int(period[5:7])
    pub_month = m + 3  # (m + 1) published ~day 12 of +2 months
    pub_year = y
    while pub_month > 12:
        pub_month -= 12
        pub_year += 1
    return date(pub_year, pub_month, 12)


def monthly_problem(period: str | None) -> str | None:
    """Schedule-aware monthly freshness. None = fresh (nothing to alert)."""
    if not period:
        return "Monthly bulletin: no data"
    due = next_monthly_due(period)
    if due is None:
        return None
    overdue = (date.today() - due).days
    if overdue > MONTHLY_OVERDUE_GRACE_DAYS:
        return (
            f"Monthly bulletin: {period} is the latest, but the next month was "
            f"due ~{due.isoformat()} ({overdue}d ago) — a release may have been missed"
        )
    return None  # before the next release (or only just due) → fresh


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

    # Monthly bulletin — schedule-aware (not age-based; see monthly_problem).
    monthly = monthly_problem(row.get("monthly_period"))
    if monthly:
        problems.append(monthly)

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
