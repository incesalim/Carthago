"""TBB **Uzaktan ve Şubeden Müşteri Edinim İstatistikleri** — remote (digital)
vs branch (non-digital) customer-acquisition statistics.

This is a *separate* monthly TBB report from the quarterly digital/internet/mobile
one (``src/tbb/parser.py``). It exists because of the 2021 "Uzaktan Kimlik Tespiti"
(remote e-KYC) regulation, and reports, per month, how many customers each member
bank acquired **remotely** (without visiting a branch) vs **at a branch**.

Layout of the single ``müşteri edinim`` sheet — three side-by-side panels, one per
customer type, each a monthly time series (Mayıs 2021 → latest):

    Gerçek Kişiler (individual)   | Gerçek Kişi Tacirler (merchant) | Tüzel Kişiler (legal)
    cols 0–6                      | cols 8–14                       | cols 16–20

Each panel has the same method columns (legal omits bulk/courier):
  - **Uzaktan - Başvuru Sayısı**            → ``remote_application`` (applications, funnel intake — NOT a finalized customer)
  - **Uzaktan - Müşteri Temsilcisi ile …**  → ``remote_rep``         (finalized remotely via a video call with a rep)
  - **Toplu Edinim - …**                    → ``bulk``               (bulk onboarding, e.g. payroll/corporate deals)
  - **Uzaktan Başvuru - Kurye ile …**       → ``remote_courier``     (online application, ID confirmed by courier/field staff)
  - **Şubeden - …**                         → ``branch``             (finalized physically at a branch)

So "acquired without visiting a branch" = ``remote_rep + remote_courier + bulk``;
``branch`` is the non-digital channel. ``remote_application`` is a separate funnel
(intake) figure and must not be summed with the finalized counts.

**Definition breaks** (carried through verbatim; flagged for the dashboard):
  - *Individuals* — definitions refined as of **Ocak 2023** (the series continues).
  - *Merchants / legal entities* — only reported from **Temmuz 2024** (``-`` before).

Each monthly workbook is **cumulative** (full history every time), so ingestion only
ever needs the newest file.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from src.tbb.client import _HEADERS, _DOWNLOAD_RE, download_xls, find_xls_url

BASE = "https://www.tbb.org.tr/istatistiki-raporlar/"
SUFFIX = "-uzaktan-ve-subeden-musteri-edinimi-istatistikleri"
DATA_SHEET = "müşteri edinim"

# Month slug ↔ number (the report is monthly).
_MONTH_SLUGS = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}
_SLUG_FOR = {v: k for k, v in _MONTH_SLUGS.items()}

_TR_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
    "kasim": 11, "aralık": 12, "aralik": 12,
}
# A data row's month cell is *exactly* "MonthName YYYY" (after stripping trailing
# footnote stars). Footnote rows ("** Ocak 2023 itibarıyla …") carry trailing text
# and so never match — that's how data rows are told apart from notes.
_PERIOD_RE = re.compile(
    r"^\s*(" + "|".join(_TR_MONTHS) + r")\s+(\d{4})\s*$", re.IGNORECASE
)

# Panel title (row 0) → entity_type. Matched on the trailing customer-type phrase.
_ENTITY_FOR = [
    ("gercek kisi tacir", "merchant"),   # check before plain "gercek kisi"
    ("tuzel", "legal"),
    ("gercek kisi", "individual"),
]


def _norm(s: str) -> str:
    s = (s.replace("İ", "i").replace("ı", "i").replace("Ş", "s").replace("ş", "s")
         .replace("Ğ", "g").replace("ğ", "g").replace("Ç", "c").replace("ç", "c")
         .replace("Ö", "o").replace("ö", "o").replace("Ü", "u").replace("ü", "u"))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _classify_method(header: str) -> str | None:
    """Map a row-2 column header to a method slug (None = not a data column)."""
    h = _norm(header)
    if "subeden" in h:
        return "branch"
    if "kurye" in h:
        return "remote_courier"
    if "musteri temsilcisi" in h:
        return "remote_rep"
    if "toplu edinim" in h:
        return "bulk"
    if "basvuru sayisi" in h:          # plain "Uzaktan - Başvuru Sayısı"
        return "remote_application"
    return None


METHOD_TR = {
    "remote_application": "Uzaktan - Başvuru Sayısı",
    "remote_rep": "Uzaktan - Müşteri Temsilcisi ile Sonuçlandırılan Müşteri Sayısı",
    "bulk": "Toplu Edinim - Sonuçlandırılan Müşteri Sayısı",
    "remote_courier": "Uzaktan Başvuru - Kurye ile Sonuçlandırılan Müşteri Sayısı",
    "branch": "Şubeden - Sonuçlandırılan Müşteri Sayısı",
}


@dataclass
class AcqStat:
    period: str        # YYYY-MM (monthly)
    entity_type: str   # individual | merchant | legal
    method: str        # remote_application | remote_rep | bulk | remote_courier | branch
    method_tr: str
    value: float

    def key(self) -> tuple:
        return (self.period, self.entity_type, self.method)


def _to_float(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "").replace(" ", "")
    if not s or s == "-":      # "-" = not reported that month
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_period(text: str) -> str | None:
    t = str(text).strip().rstrip("*").strip()
    m = _PERIOD_RE.match(t)
    if not m:
        return None
    return f"{int(m.group(2)):04d}-{_TR_MONTHS[m.group(1).lower()]:02d}"


def parse_workbook(path: str) -> list[AcqStat]:
    """Parse the ``müşteri edinim`` sheet into tidy rows, deduped on the natural
    key (period, entity_type, method)."""
    with pd.ExcelFile(path, engine="openpyxl") as xl:
        sheet = next((s for s in xl.sheet_names if _norm(s) == _norm(DATA_SHEET)), None)
        if sheet is None:
            raise ValueError(f"'{DATA_SHEET}' sheet not found in {path}: {xl.sheet_names}")
        df = xl.parse(sheet, header=None)
    return parse_frame(df)


def parse_frame(df) -> list[AcqStat]:
    """Parse the ``müşteri edinim`` grid (a header-less DataFrame) into tidy rows.
    Split out from :func:`parse_workbook` so the layout logic is unit-testable
    without an Excel file."""
    nrows, ncols = df.shape

    def cell(r, c):
        v = df.iat[r, c]
        return "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v).strip()

    # Locate panels from the row-0 titles: (start_col, entity_type), ordered L→R.
    panels: list[tuple[int, str]] = []
    for c in range(ncols):
        h = _norm(cell(0, c))
        if not h:
            continue
        for needle, ent in _ENTITY_FOR:
            if needle in h:
                panels.append((c, ent))
                break
    if not panels:
        raise ValueError("No panel titles found on row 0 of the acquisition sheet")
    bounds = [p[0] for p in panels] + [ncols]

    # Per panel: the method columns (row-2 header → slug). The month lives in the
    # panel's leading column.
    out: dict[tuple, AcqStat] = {}
    for i, (start, ent) in enumerate(panels):
        end = bounds[i + 1]
        method_cols: dict[int, str] = {}
        for c in range(start, end):
            slug = _classify_method(cell(2, c))
            if slug:
                method_cols[c] = slug
        month_col = start
        for r in range(3, nrows):
            period = _normalize_period(cell(r, month_col))
            if not period:
                continue
            for c, slug in method_cols.items():
                val = _to_float(df.iat[r, c])
                if val is None:
                    continue
                stat = AcqStat(period, ent, slug, METHOD_TR[slug], val)
                out[stat.key()] = stat
    return list(out.values())


# ---------------------------------------------------------------------------
# Discovery / download (monthly; cumulative file → only the newest is needed)
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def report_url(year: int, month: int) -> str:
    return f"{BASE}{year}-{_SLUG_FOR[month]}{SUFFIX}"


def discover_latest(session: requests.Session | None = None,
                    max_lookback: int = 8) -> tuple[str, str, str] | None:
    """Find the newest published report. Returns ``(period, page_url, xls_url)``
    or ``None``. Probes month-by-month backward from the current month; TBB
    serves a 200 placeholder for unpublished months, so each candidate is
    confirmed by resolving its Excel link.
    """
    s = session or _session()
    now = datetime.now()
    y, m = now.year, now.month
    for _ in range(max_lookback):
        page = report_url(y, m)
        try:
            xls = find_xls_url(page, session=s)
        except requests.RequestException:
            xls = None
        if xls:
            return (f"{y:04d}-{m:02d}", page, xls)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return None


def download_latest(dest_dir: str | Path,
                    session: requests.Session | None = None) -> tuple[str, Path] | None:
    """Download the newest report's Excel. Returns ``(period, path)`` or ``None``."""
    s = session or _session()
    found = discover_latest(session=s)
    if not found:
        return None
    period, page, xls = found
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"tbb_acquisition_{period}.xlsx"
    with s.get(xls, timeout=120, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
    return period, dest


# Re-export so callers can mock the digital downloader symmetry if needed.
__all__ = ["AcqStat", "parse_workbook", "parse_frame", "discover_latest",
           "download_latest", "report_url", "METHOD_TR", "_DOWNLOAD_RE",
           "download_xls", "_classify_method", "_normalize_period"]
