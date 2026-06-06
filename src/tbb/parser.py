"""Parse the TBB digital-banking ``.xls`` workbook into tidy long rows.

The workbook (``Dijital-İnternet-Mobil Bankacılık İstatistikleri-<period>.xls``)
is a legacy BIFF/OLE2 file with ~16 sheets. The detail sheets are sector-wide
(no per-bank breakdown). Their real dimensions are:

- **channel**  : digital | internet | mobile        (from the sheet)
- **segment**  : individual | corporate | total      (from the sheet / in-block marker)
- **section**  : I customers, II non-financial, III.1–III.6 financial, IV sales
                 (plus gender / age demographics on the digital sheet)
- **unit**     : persons_thousands | count_thousands | volume_bn_try
- **metric**   : a ``>``-joined path composed from the 1–3 level merged headers
                 (e.g. ``Havale > Üçüncü şahıslara > TP Havale``)

Block detection anchors on the unambiguous period-data rows (``Mart 2025`` …)
rather than the inconsistent ``Dönem`` marker rows: a maximal run of consecutive
period rows is one data block, and its column headers are whatever non-data rows
sit above it (within the current section). Each header row is forward-filled to
the right and the per-column path composed top-to-bottom — this reproduces the
merged-cell hierarchy without hand-coding every sub-metric.

Robustness is verified by anchor assertions in ``tests/test_tbb_parser.py``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

# ---------------------------------------------------------------------------
# Period normalisation
# ---------------------------------------------------------------------------

_TR_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
    "kasim": 11, "aralık": 12, "aralik": 12,
}
_PERIOD_RE = re.compile(
    r"^\s*(" + "|".join(_TR_MONTHS) + r")\s+(\d{4})\s*$", re.IGNORECASE
)
# Section headers: "I.", "II.", "III.1.", "IV." … (Roman numeral, optional .N)
_SECTION_RE = re.compile(r"^\s*((?:I{1,3}|IV|VI{0,3}|V)(?:\.\d+)?)\.\s+(\S.*)$")

# A cell that is *purely* a unit / period descriptor (e.g. "İşlem Adedi (Bin)",
# "İşlem Hacmi (Milyar TL)", "Dönem", "Adet") — dropped from metric paths. A
# customer label like "Aktif müşteri sayısı (Bin)" merely *ends* in "(Bin)" and
# is NOT matched here (it is a real metric, cleaned by _clean_label).
_UNIT_RE = re.compile(
    r"^\s*(?:İşlem|Islem)\s+(?:Aded|Adet|Hacmi)"
    r"|^\s*Dönem\s*$|^\s*Donem\s*$|^\s*Adet\s*$",
    re.IGNORECASE,
)
# Trailing unit parentheticals stripped from metric labels for display cleanliness.
_UNIT_SUFFIX_RE = re.compile(r"\s*\((?:Bin|Milyar\s*TL|Adet)\)\s*$", re.IGNORECASE)
# "… devamı aşağıdadır…" = a 'continued below' layout note glued onto a label.
_CONT_NOTE_RE = re.compile(r"\s*devam[ıi]\s*aşağıdad[ıi]r.*$", re.IGNORECASE)
_VOLUME_RE = re.compile(r"Hacmi|Milyar\s*TL|Milyon\s*TL", re.IGNORECASE)
# Customer / demographic sections are head-counts, detected by section name.
_PERSONS_RE = re.compile(r"Müşteri\s+Sayı|Musteri\s+Sayi|Cinsiyet|Yaş|Yas", re.IGNORECASE)
# Source unit markers. TBB switched conventions over the years, so the canonical
# unit is recovered per block from the header text rather than assumed:
#   persons  → thousands  ("(Bin)" present; older reports gave absolute persons)
#   volume   → billion TL ("Milyar TL"; older reports gave "Milyon TL" = million)
_BIN_RE = re.compile(r"\(\s*Bin\s*\)", re.IGNORECASE)   # "(Bin)" = thousands
_MILYON_RE = re.compile(r"Milyon", re.IGNORECASE)        # million (→ /1000 to bn)

_SEGMENT_MARKERS = {
    "bireysel": "individual",
    "kurumsal": "corporate",
    "toplam": "total",
}


def normalize_period(text: str) -> str | None:
    """``"Mart 2026"`` → ``"2026-03"`` (quarter-end month); else ``None``."""
    m = _PERIOD_RE.match(str(text).strip())
    if not m:
        return None
    month = _TR_MONTHS[m.group(1).lower()]
    return f"{int(m.group(2)):04d}-{month:02d}"


def slugify(text: str) -> str:
    """ASCII slug stable across the Turkish/ASCII spelling of a header path."""
    s = text.replace("İ", "i").replace("ı", "i").replace("ş", "s")
    s = s.replace("ğ", "g").replace("ç", "c").replace("ö", "o").replace("ü", "u")
    s = s.replace("Ş", "s").replace("Ğ", "g").replace("Ç", "c")
    s = s.replace("Ö", "o").replace("Ü", "u")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "value"


# ---------------------------------------------------------------------------
# Per-sheet roles
# ---------------------------------------------------------------------------

# channel/segment per sheet, and which sections to take. Customers (section I)
# come *only* from the channel-total sheets (which carry the bireysel/kurumsal/
# toplam breakdown via in-block markers); the segment sheets contribute only
# their transaction sections — so no customer row is double-counted.
@dataclass(frozen=True)
class _SheetRole:
    channel: str
    segment: str            # default segment for transaction (II–IV) sections
    skip_section_i: bool    # don't emit section I — its segment breakdown is
                            # taken once, from the channel-total sheet


# Section I (customers) is emitted only by the channel-total sheets, which carry
# the full Bireysel/Kurumsal/Toplam breakdown as column groups; segment sheets
# would only duplicate it, so they skip section I and contribute transactions.
_SHEET_ROLES: dict[str, _SheetRole] = {
    "Dijital bank.istat.": _SheetRole("digital", "individual", False),
    "İnternet bank.istat.": _SheetRole("internet", "total", False),
    "Bireysel İnternet bank.istat.": _SheetRole("internet", "individual", True),
    "Kurumsal İnternet bank.istat.": _SheetRole("internet", "corporate", True),
    "Mobil bank.istat.": _SheetRole("mobile", "total", False),
    "Bireysel Mobil bank.istat.": _SheetRole("mobile", "individual", True),
    "Kurumsal Mobil bank.istat.": _SheetRole("mobile", "corporate", True),
}


# ---------------------------------------------------------------------------
# Tidy output row
# ---------------------------------------------------------------------------


@dataclass
class TbbStat:
    period: str          # YYYY-MM (quarter-end)
    channel: str         # digital | internet | mobile
    segment: str         # individual | corporate | total
    section_code: str    # I | II | III.1 | … | IV
    section_tr: str      # Turkish section name
    metric_path: str     # >-joined Turkish header path
    metric_slug: str     # ascii slug of metric_path
    unit: str            # persons_thousands | count_thousands | volume_bn_try
    value: float
    source_sheet: str

    def key(self) -> tuple:
        return (self.period, self.channel, self.segment,
                self.section_code, self.metric_slug, self.unit)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v)
    s = re.sub(r"-\s*\n\s*", "", s)   # de-hyphenate line breaks: "sa-\nyısı" → "sayısı"
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _to_float(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "")
    if not s:
        return None
    # Turkish thousands/decimal are not used in this workbook (raw floats),
    # but guard against stray formatting.
    s = s.replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _ffill_row(values: list[str]) -> list[str]:
    """Forward-fill non-empty cells to the right (merged-header expansion)."""
    out: list[str] = []
    last = ""
    for v in values:
        if v:
            last = v
        out.append(last)
    return out


def _clean_label(text: str) -> str:
    # '*' is a footnote-reference marker TBB started adding in 2025 (e.g.
    # "EFT *", "Kurumsal*", "Toplam* > Toplam"). Dropping it keeps metric slugs
    # — and the segment-group tokens — stable across the wording change.
    t = _CONT_NOTE_RE.sub("", text).replace("*", "")
    t = _UNIT_SUFFIX_RE.sub("", t)   # drops a now-trailing "(Bin)" too
    return re.sub(r"\s+", " ", t).strip()


def _classify_unit(section_tr: str, zone_texts: list[str]) -> tuple[str, float]:
    """Return (canonical_unit, scale). `scale` converts the block's source values
    to the canonical unit, normalising TBB's cross-era unit changes:

    - persons → thousands: "(Bin)" header ⇒ already thousands (×1); otherwise the
      report gives absolute persons (×1/1000).  [switched to thousands ~2020]
    - volume  → billion TL: "Milyon TL" header ⇒ million (×1/1000); else billion.
    - counts  → thousands: "(Bin)" (×1); absent ⇒ absolute (×1/1000).
    """
    blob = " ".join(zone_texts)
    has_bin = bool(_BIN_RE.search(blob))
    if _PERSONS_RE.search(section_tr):
        return "persons_thousands", (1.0 if has_bin else 0.001)
    if _VOLUME_RE.search(blob):
        return "volume_bn_try", (0.001 if _MILYON_RE.search(blob) else 1.0)
    return "count_thousands", (1.0 if has_bin else 0.001)


def _parse_sheet(df: pd.DataFrame, sheet: str, role: _SheetRole) -> list[TbbStat]:
    nrows, ncols = df.shape
    grid = [[_cell(df.iat[r, c]) for c in range(ncols)] for r in range(nrows)]

    # Index the section headers and the period-data rows.
    section_rows: list[tuple[int, str, str]] = []  # (row, code, name)
    is_data = [False] * nrows
    for r in range(nrows):
        a = grid[r][0]
        sm = _SECTION_RE.match(a)
        if sm:
            section_rows.append((r, sm.group(1), f"{sm.group(1)}. {sm.group(2)}".strip()))
        if normalize_period(a):
            is_data[r] = True

    # Group maximal runs of consecutive period rows into data blocks.
    blocks: list[tuple[int, int]] = []  # (start, end_inclusive)
    r = 0
    while r < nrows:
        if is_data[r]:
            s = r
            while r < nrows and is_data[r]:
                r += 1
            blocks.append((s, r - 1))
        else:
            r += 1

    out: list[TbbStat] = []
    prev_end = -1
    for (bstart, bend) in blocks:
        # Nearest section header above the block.
        sec_code, sec_name, sec_row = "", "", -1
        for (sr, code, name) in section_rows:
            if sr < bstart:
                sec_code, sec_name, sec_row = code, name, sr
            else:
                break

        # Top-level section number ("III.1" -> "III") decides customers vs txn.
        top = sec_code.split(".")[0]
        if role.skip_section_i and top == "I":
            prev_end = bend
            continue

        # Header zone: rows between (prev block / section header) and this block.
        lo = max(prev_end + 1, sec_row + 1, 0)
        zone = list(range(lo, bstart))

        # Collect header rows (every non-data zone row, minus unit descriptors;
        # segment group headers like "Bireysel/Kurumsal/Toplam" are kept so they
        # forward-fill across their column span).
        header_rows: list[list[str]] = []
        zone_texts: list[str] = []
        for zr in zone:
            row = grid[zr]
            zone_texts.extend(t for c, t in enumerate(row) if c >= 1 and t)
            label_row = [
                "" if (c == 0 or not t or _UNIT_RE.search(t)) else _clean_label(t)
                for c, t in enumerate(row)
            ]
            if any(label_row):
                header_rows.append(_ffill_row(label_row))

        unit, scale = _classify_unit(sec_name, zone_texts)
        is_customers = top == "I"

        # Compose a per-column metric path (top-to-bottom, de-duplicating repeats),
        # computed once per block so every period row in the block agrees. For
        # the customer matrix the leading path component is a segment token
        # (Bireysel/Kurumsal/Toplam) → it becomes the row's segment, not metric.
        def path_for(col: int) -> list[str]:
            parts: list[str] = []
            for hr in header_rows:
                t = hr[col] if col < len(hr) else ""
                if t and (not parts or parts[-1] != t):
                    parts.append(t)
            return parts

        col_meta: dict[int, tuple[str, str, str]] = {}  # col -> (path, slug, segment)
        used: dict[tuple[str, str], int] = {}           # (segment, slug) -> owning col
        fallback = sec_name.split(". ", 1)[-1] if sec_name else sheet
        for c in range(1, ncols):
            parts = path_for(c)
            seg = role.segment
            if is_customers and parts and parts[0].strip().lower() in _SEGMENT_MARKERS:
                seg = _SEGMENT_MARKERS[parts.pop(0).strip().lower()]
            mpath = " > ".join(parts) or fallback
            slug = slugify(mpath)
            # Disambiguate only true collisions: two columns of the SAME segment
            # sharing a slug. Same slug under different segments is fine — segment
            # is part of the primary key (the customer matrix reuses one label,
            # e.g. "Aktif müşteri sayısı", across Bireysel/Kurumsal/Toplam).
            if used.get((seg, slug), c) != c:
                slug = f"{slug}_{c}"
            used.setdefault((seg, slug), c)
            col_meta[c] = (mpath, slug, seg)

        for dr in range(bstart, bend + 1):
            period = normalize_period(grid[dr][0])
            if not period:
                continue
            for c in range(1, ncols):
                val = _to_float(df.iat[dr, c])
                if val is None:
                    continue
                mpath, slug, seg = col_meta[c]
                out.append(TbbStat(
                    period=period, channel=role.channel, segment=seg,
                    section_code=sec_code or "?", section_tr=sec_name or sheet,
                    metric_path=mpath, metric_slug=slug, unit=unit,
                    value=val * scale, source_sheet=sheet,
                ))
        prev_end = bend
    return out


def _engine_for(path: str) -> str | None:
    """Pick the read engine by magic bytes, not extension: TBB serves the
    workbook as ``.xls`` even in years it is really OOXML. ``D0CF11E0`` = legacy
    BIFF/OLE2 (xlrd); ``PK\\x03\\x04`` = zip-based ``.xlsx`` (openpyxl)."""
    with open(path, "rb") as fh:
        sig = fh.read(4)
    if sig == b"PK\x03\x04":
        return "openpyxl"
    if sig == b"\xd0\xcf\x11\xe0":
        return "xlrd"
    return None  # let pandas decide


def parse_workbook(path: str) -> list[TbbStat]:
    """Parse every recognised detail sheet of the workbook into tidy rows.

    Deduplicates on the natural key (period, channel, segment, section,
    metric_slug, unit); on collision the later sheet wins (sheet order is
    stable, so this is deterministic).
    """
    xl = pd.ExcelFile(path, engine=_engine_for(path))
    rows: dict[tuple, TbbStat] = {}
    for sheet, role in _SHEET_ROLES.items():
        if sheet not in xl.sheet_names:
            continue
        df = xl.parse(sheet, header=None)
        for stat in _parse_sheet(df, sheet, role):
            rows[stat.key()] = stat
    return list(rows.values())
