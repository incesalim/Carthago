"""Discover and parse earnings-call transcripts from AlphaSpread.

Two calls per bank, both against server-rendered HTML:

* :func:`discover_quarters` — GET the bank's ``/investor-relations/earnings-call``
  index and read every ``/earnings-call/q<N>-<YYYY>`` slug out of it. The archive
  enumerates itself, so there is no filename skeleton to learn (contrast
  ``src/earnings/presentations.py``, where the deck URLs had to be guessed from a
  seed) and no quarter can be missed because nobody hand-added it.
* :func:`parse_call` — GET one call page and split the transcript into speaker
  turns.

The turn markup is a Semantic-UI comment list, stable across every page sampled::

    <div class="comment">
      <div class="avatar-container"><div class="avatar">
        <div class="ui circular label">C</div>
        <div class="author">Cenk Gur<div class="description">executive</div></div>
      </div></div>
      <div class="content"><div class="text"><p>…</p><p>…</p></div></div>
    </div>

stdlib ``html.parser`` + ``requests`` only — no bs4/lxml — so the lane runs under
the CI job's minimal dependency set rather than being silently skipped there.

Two source properties worth knowing before trusting the output:

* A default ``urllib``/``requests`` User-Agent gets **403**; a browser UA gets 200.
  The block is UA-based, not a bot wall, so :data:`_UA` is load-bearing.
* Attribution is the weak axis. The content runs opening remarks → Q&A → closing
  remarks in full, but the operator naming a Turkish analyst often transcribes as
  ``[indiscernible]``, and those turns also lose their ``role='analyst'`` tag.
  :func:`parse_call` counts the markers rather than hiding them.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser

import requests

SOURCE = "alphaspread"

# First backoff wait after a 429; tripled on each retry (10s → 30s → 90s).
_BACKOFF_S = 10
BASE = "https://www.alphaspread.com/security/ist/{slug}/investor-relations/earnings-call"

# A browser UA is required — the default one 403s. See the module docstring.
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_SLUG_RE = re.compile(r"earnings-call/(q[1-4])-((?:19|20)\d{2})\b", re.I)
_DATE_RE = re.compile(
    r"Earnings Call on\s+([A-Z][a-z]{2})[a-z]*\s+(\d{1,2}),?\s+((?:19|20)\d{2})"
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

# Earliest call we ingest. Anything older predates the reporting-unit and
# CPI-linker regimes the dashboard covers, so it would be read out of context.
MIN_PERIOD = "2018Q1"


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    for k, v in attrs:
        if k == "class" and v:
            return set(v.split())
    return set()


@dataclass
class Turn:
    seq: int
    speaker: str | None
    role: str | None
    text: str

    def as_dict(self) -> dict:
        return {"seq": self.seq, "speaker": self.speaker,
                "role": self.role, "text": self.text}


@dataclass
class Call:
    bank_ticker: str
    period: str
    call_date: str | None
    source_url: str
    turns: list[Turn] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(len(t.text.split()) for t in self.turns)

    @property
    def speaker_count(self) -> int:
        return len({t.speaker for t in self.turns if t.speaker})

    @property
    def analyst_turn_count(self) -> int:
        return sum(1 for t in self.turns if (t.role or "").lower() == "analyst")

    @property
    def indiscernible_count(self) -> int:
        return sum(len(re.findall(r"\[indiscernible\]", t.text, re.I))
                   for t in self.turns)

    def transcript_json(self) -> str:
        return json.dumps([t.as_dict() for t in self.turns], ensure_ascii=False)


class _TranscriptParser(HTMLParser):
    """Pull ``(speaker, role, text)`` out of the comment list.

    Depth-tracked rather than regex-sliced: the blocks nest, and Livewire wraps
    each one in ``<!--[if BLOCK]>`` conditional comments that a naive split on
    ``<div class="comment">`` would happily swallow.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.turns: list[Turn] = []
        self._depth = 0
        self._comment_at: int | None = None
        self._author_at: int | None = None
        self._desc_at: int | None = None
        self._text_at: int | None = None
        self._author: list[str] = []
        self._role: list[str] = []
        self._body: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "div":
            return
        self._depth += 1
        cls = _classes(attrs)
        if self._comment_at is None:
            if "comment" in cls:
                self._comment_at = self._depth
                self._author, self._role, self._body = [], [], []
            return
        # description is nested INSIDE author — check it first so the role text
        # doesn't get appended to the speaker's name.
        if "description" in cls and self._desc_at is None:
            self._desc_at = self._depth
        elif "author" in cls and self._author_at is None:
            self._author_at = self._depth
        elif "text" in cls and self._text_at is None:
            self._text_at = self._depth

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return
        for attr in ("_desc_at", "_author_at", "_text_at"):
            if getattr(self, attr) == self._depth:
                setattr(self, attr, None)
        if self._comment_at == self._depth:
            self._flush()
            self._comment_at = None
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._comment_at is None:
            return
        if self._desc_at is not None:
            self._role.append(data)
        elif self._author_at is not None:
            self._author.append(data)
        elif self._text_at is not None:
            self._body.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", " ".join(self._body)).strip()
        if not text:
            return
        speaker = re.sub(r"\s+", " ", " ".join(self._author)).strip() or None
        role = re.sub(r"\s+", " ", " ".join(self._role)).strip().lower() or None
        self.turns.append(Turn(len(self.turns) + 1, speaker, role, text))


def _get(url: str, *, attempts: int = 4) -> requests.Response:
    """GET with backoff on 429/5xx.

    The source rate-limits: a first full-corpus run at one request per second
    started returning 429 around the 70th page and then stayed there, which cost
    five banks their *index* fetch and so their entire archive. A 429 is a "come
    back later", not a failure, so it is retried — and because the limiter stays
    tripped for a while, the waits are long rather than polite-looking.
    """
    delay = _BACKOFF_S
    last: requests.Response | None = None
    for attempt in range(attempts):
        r = requests.get(url, headers=_UA, timeout=60, allow_redirects=True)
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
            return r
        last = r
        if attempt == attempts - 1:
            break
        # Honour Retry-After when the server sends one; it knows better than we do.
        wait = delay
        retry_after = r.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            wait = max(wait, int(retry_after))
        print(f"[calls] {r.status_code} on {url.rsplit('/', 1)[-1]} — "
              f"waiting {wait}s (attempt {attempt + 1}/{attempts})", flush=True)
        time.sleep(wait)
        delay *= 3
    assert last is not None
    last.raise_for_status()
    return last


def _period_of(quarter_slug: str) -> str:
    """``'q1-2026'`` -> ``'2026Q1'``."""
    q, year = quarter_slug.split("-")
    return f"{year}Q{q[1]}"


def _call_date(html: str) -> str | None:
    m = _DATE_RE.search(html)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).title())
    if not month:
        return None
    return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"


def discover_quarters(slug: str, min_period: str = MIN_PERIOD) -> list[str]:
    """Every ``'YYYYQn'`` this bank has a call page for, oldest first.

    Returns ``[]`` for a bank whose index says "No Earnings Calls Available" —
    an absence at the source, not an error to retry.
    """
    html = _get(BASE.format(slug=slug)).text
    periods = {_period_of(f"{q.lower()}-{y}") for q, y in _SLUG_RE.findall(html)}
    return sorted(p for p in periods if p >= min_period)


def parse_call(bank_ticker: str, slug: str, period: str) -> Call:
    """Fetch and parse one call page into a :class:`Call`."""
    quarter = f"q{period[5]}-{period[:4]}"
    url = f"{BASE.format(slug=slug)}/{quarter}"
    html = _get(url).text

    # Scope to the transcript block: the same page also carries an AI summary and
    # a valuation write-up, and both would otherwise land in the turn list.
    anchor = html.find('id="earnings-call-transcript"')
    body = html[anchor:] if anchor >= 0 else html

    parser = _TranscriptParser()
    parser.feed(body)
    parser.close()

    return Call(
        bank_ticker=bank_ticker,
        period=period,
        call_date=_call_date(html),
        source_url=url,
        turns=parser.turns,
    )
