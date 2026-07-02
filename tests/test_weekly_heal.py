"""heal_missing_totals — reconstruct weekly TOTAL rows the BDDK API omitted.

Regression: private-bank SME loans (krediler 1.0.11, weekly code 10003) were
published without the TOTAL column for 13 weeks (2024-10-25 … 2025-01-17)
while the TL and FX legs existed, blanking the /credit SME chart.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.weekly_api_scraper import BDDKWeeklyAPIScraper  # noqa: E402


def _insert(conn, period, item, bank, currency, value):
    conn.execute(
        "INSERT INTO weekly_series "
        "(period_date, category, item_id, item_name, bank_type_code, currency, value) "
        "VALUES (?, 'krediler', ?, 'KOBİ Kredileri (Bilgi)', ?, ?, ?)",
        (period, item, bank, currency, value),
    )


def _scraper(tmp_path):
    s = BDDKWeeklyAPIScraper(tmp_path / "t.db")
    s.open()
    return s


def test_heals_missing_total_as_tl_plus_fx(tmp_path):
    s = _scraper(tmp_path)
    _insert(s.conn, "2024-11-15", "1.0.11", "10003", "TL", 752164.155)
    _insert(s.conn, "2024-11-15", "1.0.11", "10003", "FX", 125592.119)

    assert s.heal_missing_totals() == 1
    row = s.conn.execute(
        "SELECT value, downloaded_at FROM weekly_series "
        "WHERE currency='TOTAL' AND period_date='2024-11-15'"
    ).fetchone()
    assert row[0] == 752164.155 + 125592.119
    assert row[1] is not None  # fresh timestamp → inside push_to_d1's window

    # Idempotent: second run inserts nothing.
    assert s.heal_missing_totals() == 0
    s.close()


def test_leaves_existing_totals_and_partial_legs_alone(tmp_path):
    s = _scraper(tmp_path)
    # Complete triple — TOTAL must not be overwritten.
    _insert(s.conn, "2024-11-22", "1.0.11", "10001", "TL", 100.0)
    _insert(s.conn, "2024-11-22", "1.0.11", "10001", "FX", 50.0)
    _insert(s.conn, "2024-11-22", "1.0.11", "10001", "TOTAL", 150.0)
    # TL leg only — not reconstructible.
    _insert(s.conn, "2024-11-22", "1.0.11", "10004", "TL", 70.0)
    # NULL leg — not reconstructible.
    _insert(s.conn, "2024-11-22", "1.0.12", "10003", "TL", 70.0)
    _insert(s.conn, "2024-11-22", "1.0.12", "10003", "FX", None)

    assert s.heal_missing_totals() == 0
    assert (
        s.conn.execute(
            "SELECT COUNT(*) FROM weekly_series WHERE currency='TOTAL'"
        ).fetchone()[0]
        == 1
    )
    s.close()
