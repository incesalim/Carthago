"""Daily data-freshness health check against D1 → alert via notify() when a
source is stale, audit extractions are failing, or a bank has published a
quarter the audit lane never acquired (see `filing_gap_problem`).

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
sys.path.insert(0, str(ROOT))  # so the lazy BDDK-probe import resolves
# Stdlib-only by design, so this stays importable in the minimal-deps job.
from src.d1_usage import (  # noqa: E402
    D1_MONTHLY_ALLOWANCE,
    cycle_rows_written,
    cycle_start,
)

# (key, label, max_age_hours). Age-based staleness for the sources that publish
# on a steady cadence. The MONTHLY bulletin is NOT here — it publishes ~once a
# month with a variable 4–11 week lag, and the non-destructive upsert freezes
# `downloaded_at` the day a month lands, so an age check reads "stale" for the
# weeks between releases even when we hold the latest data. It gets a
# schedule-aware check instead (see monthly_problem). Audit is excluded from
# staleness (banks publish quarterly) — it's covered by the failure count and,
# for the quarter that never arrived at all, by filing_gap_problem.
THRESHOLDS = [
    # 13 days, not the 8 it was until 2026-08-04. `weekly` is checked on
    # MAX(downloaded_at), and that column changed MEANING on that date: the
    # weekly scraper used to re-stamp all ~26,600 rows of BDDK's trailing
    # 13-week window on every run, so the check really asked "did the cron run".
    # Now that only changed rows are written, it asks the better question —
    # "did a new week actually land" — and so it must tolerate BDDK's real
    # publication cadence instead of the cron's. Measured over 341 gaps since
    # 2019-11: 307 are exactly 7 days, but 17 exceed a week (twelve 8-day, one
    # 9, three 10, one 11 — public holidays). 8 days would have cried wolf
    # ~2.5x a year. 13 still fires on two consecutive missed weeks.
    ("weekly", "Weekly bulletin", 312),
    # Checked on the latest DATA date, like TEFAS below and for the same reason:
    # since 2026-07-27 the EVDS scraper only writes rows whose value CHANGED, so
    # `downloaded_at` now means "when the data last moved", not "when the cron
    # last ran". (It re-fetched each series' full history every day and rewrote
    # it identically — ~17M rows/month to D1, all waste.) `MAX(period_date)`
    # advances on every TCMB business-day publication, so it also catches a
    # genuine publishing break, which `downloaded_at` never could. 120h survives
    # a normal long weekend.
    ("evds", "EVDS rates/FX", 120),
    ("news", "News", 48),
    # Checked on the latest DATA date (not downloaded_at, which refreshes even
    # when TEFAS publishes nothing) so publishing breaks are caught. 120h
    # survives normal long weekends; multi-day religious holidays (Kurban)
    # may fire one benign alert.
    ("tefas", "TEFAS funds", 120),
]
AUDIT_FAILED_ALERT = 25  # baseline known-partial extractions is ~20

# Warn at 80% of the D1 write allowance, not at 100%.
#
# July 2026 ran 18.1M rows past the 50M included and nobody saw it until the
# invoice: the crons were watched, the bill was not. Three campaign days did it
# (12.4M + 15.4M + 9.4M), so the useful moment to hear about it is while there is
# still headroom to spend deliberately — at 100% the only choices left are stop
# or pay. `push_to_d1` enforces; this one tells you before it has to.
D1_SPEND_WARN_FRACTION = 0.80

# Days past the expected monthly release before a missing month is worth an
# alert (mirrors MONTHLY_OVERDUE_GRACE_DAYS in web/app/lib/admin-health.ts).
MONTHLY_OVERDUE_GRACE_DAYS = 14

SQL = (
    "SELECT "
    "(SELECT PRINTF('%04d-%02d', year, month) FROM balance_sheet "
    " ORDER BY year DESC, month DESC LIMIT 1) AS monthly_period,"
    "(SELECT MAX(downloaded_at) FROM weekly_series) AS weekly,"
    "(SELECT MAX(period_date) FROM evds_series) AS evds,"
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


def _next_month(period: str) -> tuple[int, int]:
    y, m = int(period[:4]), int(period[5:7])
    return (y + 1, 1) if m == 12 else (y, m + 1)


def monthly_freshness(period: str | None, probe=None) -> dict:
    """Monthly freshness by ASKING BDDK, not by guessing a date.

    BDDK publishes no calendar, so the authoritative question is "has BDDK
    published the next month yet?" — the same one-request probe the extractor
    uses (src/scrapers/bddk_probe). If BDDK has published it and D1 doesn't have
    it → the extractor missed a release (stale). If BDDK hasn't → we hold the
    latest data that exists → fresh. Only when BDDK can't be reached do we fall
    back to the schedule estimate (next_monthly_due). `probe` is injectable.

    Returns {status: fresh|stale|unknown, latest_period, next_period, note} —
    consumed both by the alert (below) and the /admin panel (via source_freshness).
    """
    if not period:
        return {"status": "unknown", "latest_period": None, "next_period": None,
                "note": "no monthly data in D1"}
    ny, nm = _next_month(period)
    next_period = f"{ny}-{nm:02d}"

    if probe is None:
        try:
            from src.scrapers.bddk_probe import monthly_is_published as probe
        except Exception:
            probe = None
    published: bool | None = None
    if probe is not None:
        try:
            published = probe(ny, nm)
        except Exception as e:
            print(f"monthly probe unreachable ({e}); using schedule backstop", file=sys.stderr)
            published = None

    if published is True:
        status = "stale"
        note = f"{next_period} is published by BDDK but not in D1 — the extractor missed a release"
    elif published is False:
        status = "fresh"
        note = f"{next_period} not yet published by BDDK"
    else:
        # Backstop only: BDDK unreachable — lean on the schedule estimate.
        due = next_monthly_due(period)
        overdue = due and (date.today() - due).days > MONTHLY_OVERDUE_GRACE_DAYS
        status = "stale" if overdue else "fresh"
        note = (
            f"next was due ~{due.isoformat()} and BDDK could not be probed"
            if overdue
            else f"next (~{next_period}) not due yet; BDDK not probed"
        )
    return {"status": status, "latest_period": period, "next_period": next_period, "note": note}


def monthly_problem(period: str | None, probe=None) -> str | None:
    """The alert line (None = nothing to alert), derived from monthly_freshness."""
    f = monthly_freshness(period, probe)
    if f["latest_period"] is None:
        return "Monthly bulletin: no data"
    return f"Monthly bulletin: {f['note']}" if f["status"] == "stale" else None


def write_freshness(source: str, f: dict) -> None:
    """Persist the freshness verdict to remote D1 (source_freshness) for /admin."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def lit(v) -> str:
        return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"

    sql = (
        "INSERT OR REPLACE INTO source_freshness "
        "(source, checked_at, status, latest_period, note) VALUES "
        f"({lit(source)}, {lit(now)}, {lit(f['status'])}, "
        f"{lit(f['latest_period'])}, {lit(f['note'])})"
    )
    cmd = ["npx", "--yes", "wrangler", "d1", "execute", "bddk-data", "--remote", "--command", sql]
    res = subprocess.run(
        cmd, cwd=str(WEB), capture_output=True, text=True, shell=os.name == "nt"
    )
    if res.returncode != 0:
        # Non-fatal: the table may not exist yet (pre-deploy), or D1 hiccupped.
        # The alert still fires; the panel falls back to the schedule estimate.
        print(f"could not write source_freshness: {res.stderr[-300:]}", file=sys.stderr)


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


def query_d1(sql: str = SQL) -> dict:
    rows = query_d1_rows(sql)
    if not rows:
        raise RuntimeError("query returned no rows")
    return rows[0]


def query_d1_rows(sql: str) -> list[dict]:
    """Every row of a read-only query. `query_d1` is the one-row case.

    The statement is flattened to one line first. `wrangler d1 execute
    --command` does not survive an embedded newline: measured on Windows
    2026-08-16 it failed every attempt, twice with `exit 1` and twice with a
    libuv assertion (`UV_HANDLE_CLOSING`, exit 3221226505). The module's own
    SQL constant is newline-free by construction, which is why nothing had hit
    this before; a readable triple-quoted query is the natural way to write the
    next one.
    """
    cmd = [
        "npx", "--yes", "wrangler", "d1", "execute", "bddk-data",
        "--remote", "--json", "--command", " ".join(sql.split()),
    ]
    res = subprocess.run(
        cmd, cwd=str(WEB), capture_output=True, text=True, shell=os.name == "nt"
    )
    if res.returncode != 0:
        raise RuntimeError(f"wrangler exit {res.returncode}: {res.stderr[-500:]}")
    data = json.loads(res.stdout)
    return (data[0] if isinstance(data, list) else data)["results"]


# --- the filing-season gap ---------------------------------------------------
#
# Every other check here asks whether data we HAVE has gone stale. None of them
# can see data we never acquired, and that is the failure this lane actually
# has: on 2026-08-16, thirteen banks had published 2026Q2 — İş Bankası ten days
# earlier — and the audit pipeline held nothing for any of them. Each daily run
# reported `new=0 changed=False` and exited green, which is also exactly what a
# quarter in which nobody filed looks like.
#
# The signal was already in the database. `bank_earnings` carries a KAP
# `results_filing` per (bank, period); `bank_audit_extractions` carries what we
# extracted. The gap between them is the alert, and no calendar is needed: the
# period tracked is simply the newest one anyone has filed.
#
# Grace, because a KAP filing genuinely precedes the bank's own IR page — TEB
# filed on 07-23 and the PDF appeared on 07-26. Alerting on the filing day would
# fire on every bank every quarter and get muted.
FILING_GAP_GRACE_DAYS = 4

FILING_GAP_SQL = """
SELECT e.ticker AS ticker, e.period AS period,
       MIN(substr(e.event_date, 1, 10)) AS filed_on
FROM bank_earnings e
WHERE e.kind = 'results_filing'
  AND e.period = (SELECT MAX(period) FROM bank_earnings WHERE kind='results_filing')
  AND NOT EXISTS (
        SELECT 1 FROM bank_audit_extractions x
        WHERE x.bank_ticker = e.ticker AND x.period = e.period AND x.success = 1)
GROUP BY e.ticker, e.period
ORDER BY filed_on, ticker
"""


def filing_gap_problem(rows: list[dict] | None = None,
                       today: date | None = None) -> str | None:
    """Alert text for banks that published the quarter but are not in the lane.

    Silent when nothing is overdue. Never raises on a query failure — a check
    that takes the health-check down teaches you to ignore the health check.
    """
    if rows is None:
        try:
            rows = query_d1_rows(FILING_GAP_SQL)
        except Exception as e:                                   # noqa: BLE001
            print(f"filing-gap check unavailable: {e}", file=sys.stderr)
            return None
    today = today or datetime.now(timezone.utc).date()
    overdue = []
    for r in rows:
        filed_on = r.get("filed_on")
        if not filed_on:
            continue
        try:
            age = (today - date.fromisoformat(filed_on)).days
        except ValueError:
            continue
        if age >= FILING_GAP_GRACE_DAYS:
            overdue.append((r.get("ticker"), age))
    if not overdue:
        return None
    period = rows[0].get("period", "?")
    overdue.sort(key=lambda t: -t[1])
    listed = ", ".join(f"{t} ({a}d)" for t, a in overdue)
    return (f"{period} published but not acquired: {len(overdue)} bank(s) — "
            f"{listed}")


def d1_spend_problem(used: int | None = None) -> str | None:
    """Alert text when this cycle's D1 writes cross the warn line, else None.

    Silent when the reading is unavailable (no credentials, no network): a spend
    alert that fires on its own blindness gets muted, and a muted alert is worse
    than none. The push guard is the enforcing half and does not depend on this.
    """
    if used is None:
        acct = os.environ.get("CF_ACCOUNT_TAG") or os.environ.get("R2_ACCOUNT_ID")
        tok = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not (acct and tok):
            return None
        used = cycle_rows_written(acct, tok)
    if used is None:
        return None
    pct = used / D1_MONTHLY_ALLOWANCE
    if pct < D1_SPEND_WARN_FRACTION:
        return None
    cycle = cycle_start(date.today())
    if used <= D1_MONTHLY_ALLOWANCE:
        return (f"D1 writes {used:,} of {D1_MONTHLY_ALLOWANCE:,} this cycle "
                f"({pct:.0%}, since {cycle}) — headroom is nearly gone")
    over = used - D1_MONTHLY_ALLOWANCE
    return (f"D1 writes {used:,} this cycle (since {cycle}) — {over:,} OVER the "
            f"{D1_MONTHLY_ALLOWANCE:,} allowance, ~${over / 1e6:.2f} so far; "
            f"campaign pushes are being refused until it rolls over")


def main() -> int:
    try:
        row = query_d1()
    except Exception as e:
        notify(f"⚠️ BDDK health-check could not query D1: {e}")
        print(f"health-check error: {e}", file=sys.stderr)
        return 0

    problems: list[str] = []

    # Monthly bulletin — ask BDDK (one probe), record the verdict for /admin, and
    # alert only if a published month is missing.
    mf = monthly_freshness(row.get("monthly_period"))
    write_freshness("bddk_monthly", mf)
    if mf["latest_period"] is None:
        problems.append("Monthly bulletin: no data")
    elif mf["status"] == "stale":
        problems.append(f"Monthly bulletin: {mf['note']}")

    for key, label, max_age in THRESHOLDS:
        age = hours_since(row.get(key))
        if age is None:
            problems.append(f"{label}: no data")
        elif age > max_age:
            problems.append(f"{label}: stale ({age / 24:.1f}d old, limit {max_age // 24}d)")

    failed = row.get("audit_failed") or 0
    if failed > AUDIT_FAILED_ALERT:
        problems.append(f"Audit extractions failing: {failed} (baseline ~20)")

    gap = filing_gap_problem()
    if gap:
        problems.append(gap)

    spend = d1_spend_problem()
    if spend:
        problems.append(spend)

    if problems:
        msg = "🟡 BDDK data health:\n- " + "\n- ".join(problems)
        notify(msg)
        print(msg)
    else:
        print("✅ all sources fresh; audit extractions nominal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
