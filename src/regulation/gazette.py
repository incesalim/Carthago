"""Resmî Gazete (Official Gazette) → `regulation_events`.

What the regulator and the central bank actually published, dated from the
primary record, with a link to the document.

How the Gazette is read (measured 2026-11-27):

- `https://www.resmigazete.gov.tr/DD.MM.YYYY` lists every document of that
  day's main issue with its title and a link to the document — `.htm` when an
  HTML rendering exists, otherwise `.pdf`. Nothing needs JavaScript.
- A document page opens with a fixed header: the date, `Resmî Gazete`, `Sayı :
  <issue>`, the instrument (TEBLİĞ, GENELGE, YÖNETMELİK, KARAR …), the issuing
  body ending in a colon, then the title, then the text. HTML pages declare
  `Windows-1254`.
- Not every document has text. BDDK board decisions are scanned images: the
  PDF has no text layer and every extracted line is empty. For those the
  listing's title is all there is, so an event is stored with the title and the
  link and `summary = NULL`.
- Supplementary ("mükerrer") issues are separate listings and are not read
  here. They are rare — the last one in 2026 was 27 October.

Which documents count: the issuing body, read off the document's own header
when it has text, else the listing title. In 75 days of issues (630 documents)
three named BDDK — all board decisions, all scanned — and none named TCMB;
central-bank communiqués are infrequent, and no live one was available when
this was written, so its match is the same header rule and is untested against
a real TCMB document.

Run through scripts/update_regulation.py.
"""
from __future__ import annotations

import datetime as dt
import html as htmlmod
import re
import sqlite3
from dataclasses import dataclass

import requests
from lxml import html as lh

BASE = "https://www.resmigazete.gov.tr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 40
MAX_PDF_BYTES = 8_000_000        # a Gazette document is 30 KB - 1 MB; refuse outliers
REQUEST_PAUSE = 0.3

# The issuer, named in the document's issuer line or in the listing's title.
# re.I covers the ASCII letters. It does not fold Turkish I/ı/İ, so those
# four are spelled out in classes — and the flag is load-bearing: without it
# "MERKEZ BANKASI" in capitals matched nothing and every document was dropped.
ISSUER_PATTERNS: dict[str, tuple[re.Pattern, ...]] = {
    "TCMB": (re.compile(r"merkez\s*bankas[ıiIİ]", re.I),),
    "BDDK": (
        re.compile(r"bankac[ıiIİ]l[ıiIİ]k\s+d[üuUÜ]zenleme", re.I),
        re.compile(r"\bbddk\b", re.I),
    ),
}
# Used only when a document has no text, to name an instrument from its title.
# Stems rather than whole words: a title says "Tebliğinde", "Yönetmeliğinde",
# "Kararı". "karar" alone keeps its boundary so that a Kararname stays unnamed.
_INSTRUMENT_IN_TITLE = (
    ("KARAR", re.compile(r"\bkarar[ıiIİ]?\b", re.I)),
    ("TEBLIĞ", re.compile(r"\btebli[ğgĞ]", re.I)),
    ("GENELGE", re.compile(r"\bgenelge", re.I)),
    ("YÖNETMELİK", re.compile(r"\by[öoÖO]netmeli", re.I)),
)

_MONTHS = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
           "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
_DATE = re.compile(r"^(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})(?:\s+\S+)?$")
_SAYI = re.compile(r"^say[ıi]\s*:\s*(\d+)$", re.I)
_HAS_LOWERCASE = re.compile(r"[a-zçğışöü]")
_BODY_START = re.compile(
    r"^(madde\b|karar\b|i\.|ii\.|iii\.|iv\.|v\.|vi\.|vii\.|viii\.|ix\.|x\.|"
    r"birinci\b|\d{1,2}\s*[.\-)])", re.I)
# `20261127-2.htm`, `20261127-6.pdf`. The `-N` is required: an id of bare digits
# is the whole issue's PDF, which is not a document. (A first version accepted
# the bare digits and rejected every real document, so it stored nothing.)
_DOC_NAME = re.compile(r"^(\d{8}[A-Za-z]*-\d+[A-Za-z]*)\.(htm|pdf)$")
MAX_TITLE = 500
MAX_SUMMARY = 700


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def classify_issuer(text: str) -> str | None:
    """'TCMB' or 'BDDK' when the text names one, else None.

    The regulator is checked first. Its name is specific, while a BDDK title
    can mention the central bank ("… Kurulu Kararı" beside a Merkez Bankası
    reference); a central-bank page names only itself."""
    for issuer in ("BDDK", "TCMB"):
        if any(p.search(text) for p in ISSUER_PATTERNS[issuer]):
            return issuer
    return None


def instrument_from_title(title: str) -> str | None:
    for instrument, pattern in _INSTRUMENT_IN_TITLE:
        if pattern.search(title):
            return instrument
    return None


def parse_listing(page_html: str) -> list[dict]:
    """Every document a day's listing names: id, format, title, url."""
    root = lh.fromstring(page_html)
    docs: dict[str, dict] = {}
    for a in root.xpath("//a[contains(@href, '/eskiler/')]"):
        name = (a.get("href") or "").rsplit("/", 1)[-1]
        m = _DOC_NAME.match(name)
        if not m:                        # the whole issue's PDF, or a directory
            continue
        title = " ".join(a.getparent().text_content().split())
        title = re.sub(r"^[\s\-–—]+", "", title).strip()
        doc = docs.setdefault(m.group(1), {"document_id": m.group(1), "fmt": m.group(2),
                                           "title": title, "url": f"{BASE}/eskiler/{_path(m.group(1))}{name}"})
        # A document with both links is read as HTML: it is smaller and has text.
        if m.group(2) == "htm" and title:
            doc.update(fmt="htm", url=f"{BASE}/eskiler/{_path(m.group(1))}{name}", title=title)
        elif title and not doc["title"]:
            doc["title"] = title
    return [d for d in docs.values() if d["title"] and d["fmt"] in ("htm", "pdf")]


def _path(document_id: str) -> str:
    """`20261127-2` lives under `/2026/11/`."""
    return f"{document_id[:4]}/{document_id[4:6]}/"


def html_to_lines(content: bytes) -> list[str]:
    m = re.search(rb'charset=["\']?([\w-]+)', content[:4000], re.I)
    text = content.decode(m.group(1).decode() if m else "windows-1254", errors="replace")
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    # Word's export writes its document properties into XML islands and
    # conditional comments; stripped as tags they left "Print 120 1 1 Clean
    # Clean 21 false false false …" standing above the header.
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<xml\b.*?</xml>", " ", text)
    # Block boundaries become line breaks, so one paragraph is one line.
    text = re.sub(
        r"(?i)<\s*(?:br\b|/p\b|/o:p\b|/div\b|/tr\b|/h[1-6]\b|/li\b|/td\b|/th\b|/table\b)[^>]*>",
        "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = htmlmod.unescape(text).replace("\xa0", " ")
    return [" ".join(line.split()) for line in text.split("\n") if line.strip()]


def pdf_to_lines(content: bytes) -> list[str]:
    import fitz  # the lane's only PyMuPDF user; the repo's single PDF engine
    with fitz.open(stream=content, filetype="pdf") as doc:
        raw = "\n".join(page.get_text() for page in doc)
    return [" ".join(line.split()) for line in raw.split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Header:
    event_date: str
    gazette_no: str | None
    instrument: str | None
    issuer: str | None
    title: str
    summary: str | None


def parse_header(lines: list[str]) -> Header | None:
    """The Gazette's own header, or None when the page has none.

    A document with no text layer yields no usable lines and therefore no
    header. A page that is not a regulation document (no `Sayı :` line) is not
    one either, and is left to the listing-title path.

    Every document's header is parsed; `issuer` is None when the issuing body
    is neither of the two institutions this lane reads. Parsing and that
    choice are kept apart on purpose: no TCMB document with text appeared in
    75 days of issues when this was written, so the header rule can be run
    against real pages only because it works on any ministry's."""
    sayi = next((i for i, line in enumerate(lines) if _SAYI.match(line)), None)
    if sayi is None:
        return None

    gazette_no = _SAYI.match(lines[sayi]).group(1)     # type: ignore[union-attr]
    event_date = None
    for line in lines[max(0, sayi - 4):sayi]:
        m = _DATE.match(line)
        if m and m.group(2).lower() in _MONTHS:
            event_date = dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
            break
    if event_date is None:
        return None

    cursor = sayi + 1
    instrument = None
    if cursor < len(lines) and not _HAS_LOWERCASE.search(lines[cursor]) and len(lines[cursor]) <= 40:
        instrument = lines[cursor].upper()
        cursor += 1

    # The issuing body ends in a colon, and it can wrap: on the real page it
    # is "Çevre, Şehircilik ve İklim Değişikliği" / "Bakanlığından:". Take
    # lines up to the first one that closes it, three at most, so a wrapped
    # "TÜRKİYE CUMHURİYET MERKEZ" / "BANKASI'ndan:" is still recognised.
    # `issuer` is None for every institution this lane does not read — the
    # header is still a header.
    issuer_parts: list[str] = []
    for line in lines[cursor:cursor + 3]:
        issuer_parts.append(line)
        if line.endswith(":"):
            break
    if issuer_parts and issuer_parts[-1].endswith(":"):
        issuer_line: str | None = " ".join(issuer_parts)
        cursor += len(issuer_parts)
    else:
        issuer_line = None
    issuer = classify_issuer(issuer_line) if issuer_line else None

    title_lines: list[str] = []
    while cursor < len(lines) and len(title_lines) < 8:
        line = lines[cursor]
        if _BODY_START.match(line) or line in ("&nbsp;", "—", "-"):
            break
        title_lines.append(line)
        cursor += 1
    title = " ".join(title_lines)[:MAX_TITLE] or "(başlıksız)"

    body = []
    length = 0
    for line in lines[cursor:]:
        if line in ("&nbsp;", "—", "-"):
            continue
        body.append(line)
        length += len(line)
        if length >= MAX_SUMMARY:
            break
    summary = " ".join(body)[:MAX_SUMMARY] or None
    return Header(event_date, gazette_no, instrument, issuer, title, summary)


# ---------------------------------------------------------------------------
# Network + storage
# ---------------------------------------------------------------------------
def fetch_listing(session: requests.Session, day: dt.date) -> list[dict]:
    """A day's documents; an unpublished day is an empty list, not an error."""
    r = session.get(f"{BASE}/{day.strftime('%d.%m.%Y')}", timeout=TIMEOUT)
    r.raise_for_status()
    return parse_listing(r.content.decode("utf-8", errors="replace"))


def fetch_lines(session: requests.Session, doc: dict) -> list[str]:
    r = session.get(doc["url"], timeout=TIMEOUT)
    r.raise_for_status()
    if len(r.content) > MAX_PDF_BYTES:
        return []
    return html_to_lines(r.content) if doc["fmt"] == "htm" else pdf_to_lines(r.content)


def build_event(doc: dict, lines: list[str] | None, listing_day: dt.date) -> dict | None:
    """One event from a listing entry and, when it could be read, its text.

    `lines` is None when the document could not be fetched: the event is still
    recorded from the listing, with no text and no instrument unless the title
    carries one."""
    header = parse_header(lines) if lines else None
    issuer = (header.issuer if header else None) or classify_issuer(doc["title"])
    if issuer is None:
        return None
    return {
        "document_id": f"RG-{doc['document_id']}",
        "event_date": header.event_date if header else listing_day.isoformat(),
        "issuer": issuer,
        "instrument": (header.instrument if header else None) or instrument_from_title(doc["title"]),
        "title": header.title if header else doc["title"][:MAX_TITLE],
        "summary": header.summary if header else None,
        "gazette_no": header.gazette_no if header else None,
        "source_url": doc["url"],
    }


_EVENTS_COLS = ("document_id", "event_date", "issuer", "instrument", "title", "summary", "gazette_no", "source_url")


def store_event(conn: sqlite3.Connection, event: dict) -> str:
    """'new', 'changed' or 'same'. An unchanged event keeps its `downloaded_at`,
    so the push window never sees it and no D1 row is billed for it."""
    cur = conn.execute(
        "SELECT event_date, issuer, instrument, title, summary, gazette_no, source_url "
        "FROM regulation_events WHERE document_id = ?", (event["document_id"],))
    row = cur.fetchone()
    values = tuple(event[c] for c in _EVENTS_COLS[1:])
    if row is None:
        conn.execute(f"INSERT INTO regulation_events ({', '.join(_EVENTS_COLS)}) "
                     f"VALUES ({', '.join('?' * len(_EVENTS_COLS))})", (event["document_id"],) + values)
        return "new"
    if tuple(row) == values:
        return "same"
    conn.execute(f"UPDATE regulation_events SET {', '.join(c + ' = ?' for c in _EVENTS_COLS[1:])}, "
                 "downloaded_at = CURRENT_TIMESTAMP WHERE document_id = ?", values + (event["document_id"],))
    return "changed"
