"""HTTP client for kap.org.tr — flight-payload decoding + company directory.

KAP's post-2024 site is a Next.js App Router app whose company pages are
fully server-rendered: the data sits in the RSC "flight" payload embedded as
``self.__next_f.push([1,"…"])`` script chunks. The old documented JSON APIs
(pykap era, ``/tr/api/company/*``) are dead; this module decodes the payload
instead. A real-browser User-Agent and ``Accept-Language: tr-TR`` are
required — without them some routes 404.
"""
from __future__ import annotations

import json
import re
import time

import requests

BASE = "https://www.kap.org.tr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9",
}
TIMEOUT = 60
RETRIES = 3

# Company list pages that together cover every KAP member bank: BIST-listed
# companies plus "other KAP members" (non-listed debt issuers — Ziraat,
# Eximbank, Denizbank, …).
DIRECTORY_PAGES = ("/tr/bist-sirketler", "/tr/sirketler/DK")

_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')
_DECODER = json.JSONDecoder()


def get_html(path: str) -> str:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(BASE + path, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as exc:  # noqa: BLE001 — retry any transport error
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {path} failed after {RETRIES} attempts: {last}")


def decode_flight(html: str) -> str:
    """Concatenate and unescape the Next.js flight payload from a page."""
    parts = _FLIGHT_RE.findall(html)
    return "".join(json.loads('"' + p + '"') for p in parts)


def item_objects(blob: str) -> dict[str, dict]:
    """Extract Genel Bilgi Formu itemObjects keyed by itemKey (kpy41_*).

    The same item can be embedded more than once in the RSC tree; first
    occurrence wins (they carry identical values).
    """
    out: dict[str, dict] = {}
    for m in re.finditer(r'"itemObject":', blob):
        try:
            obj, _ = _DECODER.raw_decode(blob, m.end())
        except json.JSONDecodeError:
            continue
        key = obj.get("itemKey") if isinstance(obj, dict) else None
        if key and key not in out:
            out[key] = obj
    return out


def fetch_company_items(slug: str) -> dict[str, dict]:
    """Fetch a company's Genel Bilgi Formu items. slug e.g. '2413-akbank-t-a-s'.

    Returns an empty dict when the company has no published form — a few
    members (e.g. Arap Türk Bankası) render only the label dictionary. A
    wrong/stale slug produces the same empty result (KAP serves a generic
    error shell), so callers should treat empty as "skip", not "delete".
    """
    html = get_html(f"/tr/sirket-bilgileri/genel/{slug}")
    return item_objects(decode_flight(html))


def fetch_directory() -> list[dict]:
    """Return KAP company directory entries from the bank-relevant list pages.

    Each entry: {permaLink, title, fundCode, mkkMemberOid, kapMemberOid}.
    Entries are deduplicated by permaLink (lists repeat companies once per
    KAP membership role).
    """
    seen: dict[str, dict] = {}
    for page in DIRECTORY_PAGES:
        blob = decode_flight(get_html(page))
        for m in re.finditer(r'\{"mkkMemberOid":"', blob):
            try:
                obj, _ = _DECODER.raw_decode(blob, m.start())
            except json.JSONDecodeError:
                continue
            perma = obj.get("permaLink")
            if perma and obj.get("title") and perma not in seen:
                seen[perma] = obj
    if not seen:
        raise RuntimeError("KAP directory pages yielded no company entries")
    return list(seen.values())
