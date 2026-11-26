"""BDDK's own registry of filed audit reports (BdrUyg) as an acquisition source.

Every bank hands its quarterly report to the regulator, and the regulator
publishes one listing of what it received: a row per filing with the
institution, the year and month, SOLO / KONSOLIDE, and a download link. It is
the only source that is complete by construction, and until 2026-11-26 the
scraper never read it for acquisition. The listing reader in
``document_origin_listing`` existed, but only to witness a filing's origin
after the fact.

What that cost, 2026Q3. The scraper's targets were the hand-maintained URL
config plus IR-page discovery for 13 banks, so 24 of 38 banks never got a Q3
target. All 24 had filed, and the registry held every report — 41 files — for
up to 30 days while each daily run printed ``new=0`` and exited green. Discovery
was not the answer either: it missed three banks whose only change was the
filename (ANADOLU dropped ``as``, PASHA dropped ``tr``, VAKIFK gained a ``(1)``
re-upload suffix).

This module turns the listing into the third target source. It only ever ADDS
partitions no other source targets, so nothing already held is re-fetched or
re-extracted, and what it proposes goes through the same acquisition guards as
every other source in ``scrape_to_r2`` — ``report_validity``, the
consolidation-basis check, the R2 key.

What a registry zip is NOT is handled in ``sync_audit_reports.fetch_pdf_bytes``:

  - Not necessarily "a PDF". QNB files its copy as ``.docx`` + ``.xls``, so a
    zip with no PDF in it is ``pending`` — looked at again next run, outside
    the alarm's numerator — rather than a failure.
  - Not necessarily one document. ANADOLU's 2026Q3 zips hold a one-page
    responsibility statement that sorts ahead of the report.
  - Not necessarily unwrapped. Five of the 2026Q3 zips — DUNYAK, EMLAK (both),
    EXIM, VAKIFK — carry the PDF behind the 27-byte Java header VAKIFK's own
    site uses.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit

from .document_corpus import Filing
from .document_origin_listing import (
    NAMES_PATH, _listed_rows, _literal, fetch_listing, listing_rows)
from .discovery import MIN_PERIOD

_BASIS = {"SOLO": "unconsolidated", "KONSOLIDE": "consolidated"}
_QUARTER_MONTHS = ("3", "6", "9", "12")

# ``"<ExceptionName>: <message>"`` for the last failure to read the listing —
# one entry per ``bddk_registry_targets`` call, empty on success. Same contract as
# discovery's ``DISCOVERY_FAILURES``: the fail-safe is right, but "the registry
# refused us" and "nothing new was filed" must not be the same observation.
BDDK_REGISTRY_FAILURES: list[str] = []


def is_bddk_registry_url(url: str) -> bool:
    """True for a download link on BDDK's audit registry (``BdrUyg``)."""
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.netloc == "www.bddk.org.tr"
            and parts.path.startswith("/BdrUyg/"))


def bddk_registry_targets(banks: dict, only: set[str] | None = None,
                     skip: set[tuple[str, str, str]] | None = None,
                     ) -> list[tuple[str, str, str, str]]:
    """``(ticker, period, kind, download_url)`` for every filing the registry
    holds for ``banks`` that ``skip`` does not already target.

    ``skip`` carries ``(ticker, period, kind)`` keys in the scraper's form
    (upper-case ticker and period, normalised kind). Never raises: on any
    failure to read the listing it records the cause and returns ``[]``.
    """
    BDDK_REGISTRY_FAILURES.clear()
    skip = skip or set()
    try:
        body, _response = fetch_listing()
        names = json.loads(NAMES_PATH.read_bytes())["banks"]
        rows = _listed_rows(body)
    except Exception as e:  # noqa: BLE001 — the fallback must never break the sync
        BDDK_REGISTRY_FAILURES.append(f"{type(e).__name__}: {e}")
        return []

    by_name = {_literal(name): ticker for ticker, name in names.items()}
    wanted = {str(t).upper() for t in banks}
    if only:
        wanted &= {str(t).upper() for t in only}

    # A lenient first pass names the candidates: a row that is not a
    # (name, year, month, basis, link) for a bank we track is not ours to judge.
    # The strict pass below then validates each candidate on its own, so one
    # inconsistent row anywhere in a 7,744-row listing costs its own filing and
    # nothing else — unfiltered, that pass refuses the whole listing on a 2013
    # QNB row.
    candidates: list[Filing] = []
    for _ordinal, texts, links in rows:
        if len(texts) != 5 or not links or texts[0] not in by_name:
            continue
        ticker = by_name[texts[0]]
        basis = _BASIS.get(texts[3])
        if (ticker not in wanted or basis is None
                or not (len(texts[1]) == 4 and texts[1].isdigit())
                or texts[2] not in _QUARTER_MONTHS):
            continue
        period = f"{texts[1]}Q{int(texts[2]) // 3}"
        if period < MIN_PERIOD or (ticker, period, basis) in skip:
            continue
        candidates.append(Filing(ticker, period, basis))

    out: list[tuple[str, str, str, str]] = []
    refused: dict[str, int] = {}
    for filing in candidates:
        try:
            found = listing_rows(body, names, {filing})
        except ValueError as e:
            refused[str(e)] = refused.get(str(e), 0) + 1
            continue
        if len(found) != 1:
            why = f"Official listing needs review: {len(found)} exact filing rows"
            refused[why] = refused.get(why, 0) + 1
            continue
        out.append((filing.bank_ticker, filing.period, filing.kind,
                    found[0]["download_url"]))

    if refused:
        for why, n in sorted(refused.items(), key=lambda kv: -kv[1]):
            print(f"[bddk-registry] {n} filing(s) not offered — {why}",
                  file=sys.stderr, flush=True)
    if out:
        print(f"[bddk-registry] {len(out)} filing(s) listed that no other source "
              f"targets", flush=True)
    return out
