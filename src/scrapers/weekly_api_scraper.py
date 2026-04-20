"""BDDK Weekly Bulletin — JSON API scraper.

Hits `POST /BultenHaftalik/tr/Home/KiyaslamaJsonGetir` — returns 13 weekly
observations per call (one chart-id × one bank_type × one column). Walks
backwards through history by shifting the `tarih` (anchor date) parameter
in 13-week jumps.

Design notes:
- Bank-type codes used by the weekly API differ from monthly API. This
  scraper normalises to the MONTHLY code scheme on write so tables join
  cleanly (see `WEEKLY_TO_MONTHLY_CODE`).
- Response numbers are standard JSON floats (no Turkish thousand-dots or
  comma-decimals) — verified 2026-04-19.
- All values are in million TL.
- Dates return as D.MM.YYYY or DD.MM.YYYY strings; parser handles both.
- Sanity check per value: 0 < abs(v) < 1e10 (i.e. < 10 trillion M TL)
  to catch silent corruption. Out-of-range values are logged, not stored.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
URL = "https://www.bddk.org.tr/BultenHaftalik/tr/Home/KiyaslamaJsonGetir"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.bddk.org.tr/BultenHaftalik",
}
REQUEST_PAUSE = 0.5  # seconds between calls — be nice to BDDK

# Sutun (column) → currency label
SUTUN_TO_CURRENCY = {1: "TL", 2: "FX", 3: "TOTAL"}

# BDDK weekly-API bank codes → monthly-API bank codes (monthly is canonical).
# Same numeric range 10001-10010 but different semantics between the two APIs.
WEEKLY_TO_MONTHLY_CODE = {
    "10001": "10001",   # Sektör → Sector
    "10002": "10002",   # Mevduat → Deposit Banks
    "10003": "10007",   # Kalkınma ve Yatırım → Dev & Investment Banks
    "10004": "10006",   # Katılım → Participation Banks
    "10005": "10009",   # Kamu → Public Banks (all)
    "10006": "10010",   # Yabancı → Foreign Banks (all)
    "10007": "10008",   # Yerli Özel → Domestic Private (all)
    "10008": "10004",   # Mevduat - Kamu → State Deposit Banks
    "10009": "10005",   # Mevduat - Yabancı → Foreign Deposit Banks
    "10010": "10003",   # Mevduat - Yerli Özel → Private Deposit Banks
}

# Category id → category slug (for the weekly_series.category column)
CATEGORY_NAMES = {
    1: "krediler",              # Loans
    2: "takipteki_alacaklar",   # NPL
    3: "menkul_degerler",       # Securities
    4: "mevduat",               # Deposits
    5: "diger_bilanco",         # Other balance-sheet
    6: "bilanco_disi",          # Off-balance
    7: "yp_pozisyon_saklama",   # FX pos / custodial securities
}

# Bank codes we actually need weekly (dashboard primary set, in MONTHLY scheme)
# 10001 Sector + 10003 Private Deposit + 10004 State Deposit + 10005 Foreign
# Deposit + 10006 Participation + 10007 Dev & Investment
PRIMARY_MONTHLY_CODES = ["10001", "10003", "10004", "10005", "10006", "10007"]
MONTHLY_TO_WEEKLY_CODE = {v: k for k, v in WEEKLY_TO_MONTHLY_CODE.items()}
PRIMARY_WEEKLY_CODES = [MONTHLY_TO_WEEKLY_CODE[c] for c in PRIMARY_MONTHLY_CODES]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def parse_bddk_date(s: str) -> datetime.date:
    """Accept '16.01.2026' or '6.02.2026'."""
    parts = s.split(".")
    if len(parts) != 3:
        raise ValueError(f"Bad date: {s!r}")
    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
    return datetime(y, m, d).date()


def to_api_date(d: datetime.date) -> str:
    """Format a Python date as BDDK expects: DD.MM.YYYY (zero-padded)."""
    return d.strftime("%d.%m.%Y")


def sanity_check(v: Optional[float]) -> bool:
    """True if value is None or in a plausible M TL range."""
    if v is None:
        return True
    return 0 <= abs(v) < 1e10  # under 10 trillion M TL


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS weekly_series (
    period_date    DATE    NOT NULL,
    category       TEXT    NOT NULL,
    item_id        TEXT    NOT NULL,
    item_name      TEXT    NOT NULL,
    bank_type_code TEXT    NOT NULL,
    currency       TEXT    NOT NULL,
    value          REAL,
    downloaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (period_date, item_id, bank_type_code, currency)
);
CREATE INDEX IF NOT EXISTS idx_weekly_by_item
    ON weekly_series(item_name, bank_type_code, currency, period_date);
CREATE INDEX IF NOT EXISTS idx_weekly_by_date
    ON weekly_series(period_date);

CREATE TABLE IF NOT EXISTS raw_weekly_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_date     DATE,
    item_id         TEXT,
    sutun           INTEGER,
    taraf_weekly    TEXT,
    parabirimi      TEXT,
    response_json   TEXT,
    downloaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
class BDDKWeeklyAPIScraper:
    """One instance per backfill run. Holds a DB connection."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # Quick counters for summary
        self.stats = {
            "calls": 0, "empty": 0, "errors": 0,
            "rows_inserted": 0, "sanity_drops": 0,
        }

    def open(self) -> None:
        self.conn = sqlite3.connect(self.db_path)
        ensure_schema(self.conn)

    def close(self) -> None:
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    # -------------------------------------------------------------------
    # Low-level API call
    # -------------------------------------------------------------------
    def _fetch(self, chart_id: str, tarih: str, sutun: int, taraf_weekly: str) -> dict:
        """POST to BDDK with transient-error retry (exponential backoff)."""
        payload = {
            "dil": "tr",
            "tarih": tarih,
            "id": chart_id,
            "parabirimi": "TRY",
            "sutun": str(sutun),
            "tarafKodu": taraf_weekly,
            "gun": "90",
        }
        last_err = None
        delay = 2.0
        for attempt in range(5):
            try:
                r = self.session.post(URL, data=payload, timeout=20)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                # Only retry on transient network errors / 5xx / timeouts.
                msg = str(e).lower()
                transient = ("timed out" in msg or "getaddrinfo" in msg
                             or "max retries exceeded" in msg
                             or "connection reset" in msg
                             or "503" in msg or "502" in msg or "500" in msg)
                if not transient or attempt == 4:
                    raise
                time.sleep(delay)
                delay *= 2          # 2s, 4s, 8s, 16s
        raise last_err

    # -------------------------------------------------------------------
    # One unit of work: one (chart, weekly-bank-code, sutun) at one anchor
    # -------------------------------------------------------------------
    def fetch_and_store(
        self,
        chart_id: str,
        category_slug: str,
        tarih: str,
        sutun: int,
        taraf_weekly: str,
    ) -> int:
        """Returns number of rows written."""
        self.stats["calls"] += 1
        try:
            data = self._fetch(chart_id, tarih, sutun, taraf_weekly)
        except Exception as e:
            self.stats["errors"] += 1
            print(f"  ERR {chart_id} sutun={sutun} taraf={taraf_weekly} @ {tarih}: {e}")
            return 0

        # Cache raw response
        try:
            self.conn.execute(
                "INSERT INTO raw_weekly_responses (anchor_date, item_id, sutun, taraf_weekly, parabirimi, response_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (tarih, chart_id, sutun, taraf_weekly, "TRY",
                 json.dumps(data, ensure_ascii=False)),
            )
        except Exception:
            pass  # non-fatal

        xs = data.get("XEkseni", [])
        ys = data.get("YEkseni", [])
        if not xs or not ys:
            self.stats["empty"] += 1
            return 0

        # Baslik looks like: "Toplam Krediler (2+10) (TRY) [Toplam] [Sektör]"
        # We want the bit before " (TRY)"
        baslik = data.get("Baslik", "")
        item_name = baslik.split(" (TRY)")[0].strip() if baslik else chart_id

        currency = SUTUN_TO_CURRENCY.get(sutun, f"sutun{sutun}")
        monthly_code = WEEKLY_TO_MONTHLY_CODE[taraf_weekly]

        written = 0
        for x, y in zip(xs, ys):
            try:
                dt = parse_bddk_date(x).isoformat()
            except Exception:
                continue
            v = float(y) if y is not None else None
            if not sanity_check(v):
                self.stats["sanity_drops"] += 1
                print(f"  SANITY drop {chart_id} @ {x}: value={y}")
                continue
            self.conn.execute(
                "INSERT OR REPLACE INTO weekly_series "
                "(period_date, category, item_id, item_name, bank_type_code, currency, value) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (dt, category_slug, chart_id, item_name, monthly_code, currency, v),
            )
            written += 1
        self.conn.commit()
        self.stats["rows_inserted"] += written
        return written

    # -------------------------------------------------------------------
    # Plan a backfill: anchor dates to cover [start .. end]
    # -------------------------------------------------------------------
    @staticmethod
    def plan_anchors(start: datetime.date, end: datetime.date) -> list[datetime.date]:
        """13-week anchors. The API returns 13 weeks ending at (or near) `tarih`."""
        anchors = []
        cur = end
        while cur >= start:
            anchors.append(cur)
            cur -= timedelta(weeks=13)
        return anchors

    # -------------------------------------------------------------------
    # Backfill loop
    # -------------------------------------------------------------------
    def backfill(
        self,
        catalogue: dict,               # {cat_int: [(chart_id, item_name), ...]}
        start: datetime.date,
        end: datetime.date,
        bank_codes_weekly: Iterable[str] = None,
        sutuns: Iterable[int] = (1, 2, 3),
    ) -> None:
        bank_codes_weekly = list(bank_codes_weekly or PRIMARY_WEEKLY_CODES)
        anchors = self.plan_anchors(start, end)
        all_items = [(cat, cid, name) for cat, items in catalogue.items()
                     for (cid, name) in items]
        total_units = len(all_items) * len(bank_codes_weekly) * len(sutuns) * len(anchors)
        done = 0
        t_start = time.time()
        print(f"BACKFILL {total_units:,} API calls "
              f"({len(all_items)} items × {len(bank_codes_weekly)} banks × "
              f"{len(sutuns)} sutun × {len(anchors)} anchors)", flush=True)

        for anchor in anchors:
            tarih = to_api_date(anchor)
            for (cat, cid, _) in all_items:
                category_slug = CATEGORY_NAMES.get(int(cat), f"cat{cat}")
                for taraf in bank_codes_weekly:
                    for sutun in sutuns:
                        self.fetch_and_store(cid, category_slug, tarih, sutun, taraf)
                        done += 1
                        time.sleep(REQUEST_PAUSE)
                        # progress report every 500 calls
                        if done % 500 == 0:
                            elapsed = time.time() - t_start
                            eta = elapsed * (total_units - done) / done
                            print(f"[{done:>6}/{total_units}] "
                                  f"elapsed={elapsed/60:>5.1f}m  "
                                  f"eta={eta/60:>5.1f}m  "
                                  f"rows={self.stats['rows_inserted']:,} "
                                  f"empty={self.stats['empty']} "
                                  f"err={self.stats['errors']}", flush=True)

        elapsed = time.time() - t_start
        print(f"DONE  elapsed={elapsed/60:.1f}m  stats={self.stats}", flush=True)
