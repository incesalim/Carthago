"""Classify a KAP disclosure into an earnings event kind + period.

Grounded in the real KAP feed for BIST banks (verified against the local
snapshot, 2026-06): KAP uses standardized SPK disclosure templates, not
free-text subjects. The only earnings-relevant disclosures banks file are
their *financial reports*:

* ``Finansal Rapor``                       — disclosureType ``FR``, category ``FR``
* ``Faaliyet Raporu (Konsolide[ Olmayan])``— disclosureType ``FR``, category ``ODA``
* ``Sorumluluk Beyanı (...)``              — disclosureType ``FR`` (the sign-off that
                                             accompanies the report — NOT an event)

So ``classify_kind`` keys ``results_filing`` on ``disclosureType == 'FR'`` and
explicitly drops the ``Sorumluluk Beyanı`` sign-off. Earnings-call invites,
webcast replays and investor-presentation decks are simply NOT filed on KAP by
Turkish banks — the keyword paths for ``call`` / ``presentation_filing`` are
kept (cheap, future-proof) but in practice match nothing from this source.

Period derivation is reliable from the structured KAP fields (``year`` +
``period``/``ruleType``); title/date parsing is only a fallback. Only stdlib +
``re`` are imported (plus ``_extract_qend`` from the audit discovery module,
which is itself ``requests``+stdlib) so this runs under CI's minimal deps.
"""
from __future__ import annotations

import re

from src.audit_reports.discovery import _extract_qend, _period_for

# Kinds we emit. Only the first two are ever populated today (see module docs).
RESULTS_FILING = "results_filing"
PRESENTATION_DECK = "presentation_deck"   # tier 2 (IR), not produced here
CALL = "call"
PRESENTATION_FILING = "presentation_filing"
WEBCAST_REPLAY = "webcast_replay"


def _norm(s: str | None) -> str:
    """Turkish-aware lowercase (dotted/dotless I) — mirrors press._normalize_tr."""
    if not s:
        return ""
    return s.replace("İ", "i").replace("I", "ı").lower()


# Subject substrings (normalized) → kind. Checked in order; first hit wins.
# ``results_filing`` is matched primarily on disclosureType FR (see
# classify_kind); these are the title-only fallbacks + the future-proof kinds.
_RESULTS_KW = (
    "finansal rapor", "finansal tablo", "konsolide finansal",
    "konsolide olmayan finansal", "faaliyet raporu", "bağımsız denetim raporu",
)
_CALL_KW = (
    "telekonferans", "konferans", "webcast", "web yayını", "web yayini",
    "analist toplant", "yatırımcı toplant", "bilgilendirme toplant",
    "earnings call", "conference call",
)
_PRESENTATION_KW = (
    "yatırımcı sunumu", "yatirimci sunumu", "investor presentation",
    "sonuç sunumu", "sonuc sunumu", "finansal sonuç sunum",
)
# Sign-off / supporting docs that share disclosureType FR but are not events.
_EXCLUDE_SUBJECT_KW = ("sorumluluk beyanı", "sorumluluk beyani")


def classify_kind(
    subject: str | None,
    disclosure_type: str | None = None,
    summary: str | None = None,
) -> str | None:
    """Return the earnings kind for a KAP disclosure, or ``None`` to skip.

    ``disclosure_type`` is the KAP ``disclosureType`` from raw_json (NOT the
    stored ``category``, which is ``disclosureCategory`` — a ``Faaliyet Raporu``
    is category ``ODA`` but type ``FR``).
    """
    subj = _norm(subject)
    blob = subj + " " + _norm(summary)

    # The responsibility-statement sign-off is disclosureType FR but is a
    # supporting document, not a results event — drop it before the FR check.
    if any(kw in subj for kw in _EXCLUDE_SUBJECT_KW):
        return None

    # Earnings-call / presentation filings would be free-text ODA disclosures;
    # match them by keyword first so a future "Yatırımcı Sunumu Telekonferans"
    # resolves to ``call`` (more specific) rather than ``presentation_filing``.
    if any(kw in blob for kw in _CALL_KW):
        return CALL
    if any(kw in blob for kw in _PRESENTATION_KW):
        return PRESENTATION_FILING

    # The actual signal: a financial report. Keyed on the structured type code,
    # with a subject-keyword fallback when raw_json lacks the type.
    if (disclosure_type or "").upper() == "FR":
        return RESULTS_FILING
    if any(kw in blob for kw in _RESULTS_KW):
        return RESULTS_FILING

    return None


# ``ruleType`` (the KAP interim-period label) → quarter ordinal. Turkish interim
# reports are cumulative: 3 aylık = Q1, 6 aylık = H1/Q2, 9 aylık = 9M/Q3,
# 12 aylık / yıllık = full-year/Q4.
_RULETYPE_Q = {3: 1, 6: 2, 9: 3, 12: 4}
_RULETYPE_RE = re.compile(r"(\d+)\s*ay")           # "3 Aylık" → 3


def _quarter_from_rule(period_field, rule_type: str | None) -> int | None:
    """Quarter 1-4 from the structured KAP ``period`` field + ``ruleType``."""
    rt = _norm(rule_type)
    if "yıl sonu" in rt or "yil sonu" in rt or rt.strip() in ("yıllık", "yillik"):
        return 4
    m = _RULETYPE_RE.search(rt)
    if m:
        months = int(m.group(1))
        if months in _RULETYPE_Q:
            return _RULETYPE_Q[months]
    # Fall back to the numeric period field: 1-4 directly, or 3/6/9/12 → /3.
    try:
        p = int(period_field)
    except (TypeError, ValueError):
        return None
    if 1 <= p <= 4:
        return p
    if p in _RULETYPE_Q:
        return _RULETYPE_Q[p]
    return None


def derive_period(
    raw: dict | None,
    subject: str | None = None,
    summary: str | None = None,
    publish_date_iso: str | None = None,
) -> str | None:
    """Best-effort ``'YYYYQn'`` for a KAP disclosure.

    Priority: structured KAP fields (``year`` + ``period``/``ruleType``) →
    quarter-end date strings in the subject/summary → publishDate fallback.
    Returns ``None`` when nothing is determinable.
    """
    raw = raw or {}
    year = raw.get("year")
    q = _quarter_from_rule(raw.get("period"), raw.get("ruleType"))
    if year and q:
        try:
            return f"{int(year)}Q{q}"
        except (TypeError, ValueError):
            pass

    # Quarter-end date embedded in free text (reuse the audit-lane parser).
    ymd = _extract_qend(f"{subject or ''} {summary or ''}")
    if ymd:
        p = _period_for(ymd[0], ymd[1])
        if p:
            return p

    # Fallback: map the filing date to the most-recently-ended quarter. Turkish
    # banks file interim results ~6-8 weeks after quarter-end.
    if publish_date_iso and len(publish_date_iso) >= 7:
        try:
            y, m = int(publish_date_iso[:4]), int(publish_date_iso[5:7])
        except ValueError:
            return None
        if m in (4, 5, 6):
            return f"{y}Q1"
        if m in (7, 8, 9):
            return f"{y}Q2"
        if m in (10, 11, 12):
            return f"{y}Q3"
        if m in (1, 2, 3):
            return f"{y - 1}Q4"
    return None
