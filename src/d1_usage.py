"""What this billing cycle has cost so far, read from Cloudflare's own analytics.

Stdlib only, and deliberately so: both `scripts/push_to_d1.py` (which refuses a
push that would overrun) and `scripts/healthcheck.py` (which alerts before the
allowance is gone) import it, and the health-check job installs a minimal
dependency set.

⚠️ The billing cycle is the 11th → the 10th, NOT the calendar month. The period
Cloudflare labels "Aug 2026" is Jul 11 → Aug 10; reading it as a calendar month
has twice produced the wrong days-remaining.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request

# Workers Paid: 50M rows written a cycle, then $1.00/M. Rows read are $0.001/M —
# a thousandth the price, which is why every rule here is about writes.
D1_MONTHLY_ALLOWANCE = 50_000_000

_QUERY = (
    "query($acc:String!,$start:Date!,$end:Date!){viewer{accounts(filter:{accountTag:$acc})"
    "{d1AnalyticsAdaptiveGroups(limit:10000,filter:{date_geq:$start,date_leq:$end})"
    "{sum{rowsWritten}}}}}"
)


def cycle_start(today: dt.date) -> dt.date:
    """First day of the billing cycle containing `today` (cycles run 11th→10th)."""
    if today.day >= 11:
        return today.replace(day=11)
    prev = today.replace(day=1) - dt.timedelta(days=1)
    return prev.replace(day=11)


def cycle_rows_written(account_tag: str, token: str,
                       today: dt.date | None = None) -> int | None:
    """Rows written account-wide this cycle, or None if it cannot be observed.

    None means "could not observe" — no credentials, no network, an API change.
    Callers must treat that as unknown rather than as zero: reporting a missing
    reading as "plenty of headroom" is the silent-wrong shape this repo keeps
    rediscovering.

    ⚠️ Account-wide, not per-database. `gazelhan` is a second D1 database on this
    account and is NOT this project — it was 9.5M of July's 68.1M. That makes the
    reading conservative, which is the right direction for a spend guard.
    """
    today = today or dt.date.today()
    body = json.dumps({
        "query": _QUERY,
        "variables": {"acc": account_tag,
                      "start": str(cycle_start(today)), "end": str(today)},
    }).encode()
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
        groups = payload["data"]["viewer"]["accounts"][0]["d1AnalyticsAdaptiveGroups"]
    except Exception:
        return None
    return sum(g["sum"]["rowsWritten"] for g in groups)
