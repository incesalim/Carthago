"""Deterministic franchise-stat extractor for bank annual reports (Faaliyet Raporları).

Extracts only the operational statistics the BRSA audited statements do NOT
carry — ATM / POS / merchant / customer / card counts. Branches and employees
are deliberately out of scope: they're already sourced from the audit reports'
qualitative section (``audit_reports/bank_profile.py`` → ``bank_audit_profile``),
so this lane defers to that and never re-extracts them.

These stats cluster in a report's front-matter "Rakamlarla / Bir Bakışta / Öne
Çıkan Göstergeler / At a Glance / Key Figures" infographic. Two complementary,
fully deterministic passes — NO LLM:

  Pass A — prose regex (primary): anchored ``<label> … <number>`` /
           ``<number> … <noun>`` patterns.
  Pass B — coordinate anchor (secondary fill): for a metric still missing, find
           the anchor token's word-box and take the nearest numeric token in the
           same / adjacent row (infographics stack a big number over its label).
           Reuses the y-bucketing of ``audit_reports/loans_by_sector._xy_lines``.

Every value ships with a ``confidence`` flag and a ``raw_snippet``; sanity bands
drop implausible captures. Values are never treated as silent truth — registry
availability is only flipped once a fleet backfill validates.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:  # pragma: no cover - fitz is a hard dep in CI/local
    _HAS_FITZ = False


# Canonical metric keys this lane emits. Branch/employee counts are NOT here —
# they come from bank_audit_profile (the audit lane), not annual reports.
METRIC_KEYS = (
    "atm_count", "pos_count", "merchant_count",
    "customer_total", "customer_active", "customer_digital",
    "cards_credit", "cards_debit", "cards_total",
)

# Absolute-person sanity bands (value rescaled to raw counts before checking).
# Out-of-band captures are dropped.
ABS_BANDS: dict[str, tuple[float, float]] = {
    "atm_count":        (1, 25_000),
    "pos_count":        (1, 5_000_000),
    "merchant_count":   (1, 5_000_000),
    "customer_total":   (10_000, 90_000_000),
    "customer_active":  (10_000, 90_000_000),
    "customer_digital": (10_000, 90_000_000),
    "cards_credit":     (10_000, 200_000_000),
    "cards_debit":      (10_000, 200_000_000),
    "cards_total":      (10_000, 400_000_000),
}

_SCALE = {"count": 1.0, "count_th": 1_000.0, "count_mn": 1_000_000.0}
_MN_SUF = {"milyon", "million", "mio", "mn"}
_TH_SUF = {"bin", "thousand", "k"}


# ---------------------------------------------------------------------------
# Number parsing — suffix + language aware (fixes the 1.769 vs 1,769 trap)
# ---------------------------------------------------------------------------
def parse_count(num: str, suffix: str | None = None, lang: str = "tr"
                ) -> tuple[float, str] | None:
    """Parse a franchise number into ``(value, unit)``.

    Counts (no scale suffix) are exact integers → strip every separator. A
    scaled figure ("15,5 milyon") keeps its decimal, resolved by language
    convention: TR uses ',' as the decimal mark and '.' as the thousands
    separator; EN is the reverse.
    """
    if num is None:
        return None
    num = re.sub(r"\s", "", num.strip().strip("()"))
    if not num:
        return None
    suf = (suffix or "").strip().lower()
    if suf in _MN_SUF:
        unit = "count_mn"
    elif suf in _TH_SUF:
        unit = "count_th"
    else:
        unit = "count"

    if unit == "count":
        digits = re.sub(r"[^\d]", "", num)
        if not digits:
            return None
        return float(int(digits)), unit

    # Scaled figure — respect the decimal convention for the language.
    if lang == "en":
        norm = num.replace(",", "")
    else:
        norm = num.replace(".", "").replace(",", ".")
    try:
        return float(norm), unit
    except ValueError:
        return None


def _abs_value(value: float, unit: str) -> float:
    return value * _SCALE.get(unit, 1.0)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class FranchiseStat:
    metric_key: str
    value: float
    unit: str = "count"
    period_type: str = "current"           # 'current' | 'prior' (reserved)
    source_page: int | None = None         # 1-based
    source_lang: str | None = None         # 'tr' | 'en'
    anchor: str | None = None
    raw_snippet: str | None = None
    confidence: str = "medium"             # 'high' | 'medium' | 'low'


@dataclass
class FranchiseReport:
    pdf_path: str = ""
    fiscal_year: int | None = None
    report_lang: str = "tr"
    is_ocr: bool = False
    n_pages: int = 0
    stats: list[FranchiseStat] = field(default_factory=list)

    def by_metric(self) -> dict[str, FranchiseStat]:
        """The current-period stat per metric_key (first/best wins)."""
        return {s.metric_key: s for s in self.stats if s.period_type == "current"}


# ---------------------------------------------------------------------------
# Prose anchors (Pass A)
# ---------------------------------------------------------------------------
# Number token: Turkish/English grouped digits with an optional decimal tail.
_NUM = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_SUF = r"(?:\s*(?P<suf>milyon|million|mio|mn|bin|thousand))?"


@dataclass
class _Anchor:
    metric: str
    rx: re.Pattern
    lang: str
    conf: str = "high"


def _a(metric: str, pattern: str, lang: str, conf: str = "high") -> _Anchor:
    return _Anchor(metric, re.compile(pattern, re.IGNORECASE | re.DOTALL), lang, conf)


# Single-value anchors: each yields named group 'num' (+ optional 'suf'). Ordered
# specific→generic; first match per metric wins.
_ANCHORS: list[_Anchor] = [
    # --- ATM -------------------------------------------------------------
    _a("atm_count", rf"ATM\s+(?:say[ıi]s[ıi]|aded[ıi])\D{{0,10}}(?P<num>{_NUM})", "tr", "high"),
    _a("atm_count", rf"(?:number\s+of\s+ATMs?)\D{{0,10}}(?P<num>{_NUM})", "en", "high"),
    _a("atm_count", rf"(?P<num>{_NUM})\s+(?:adet\s+)?(?:ATM|BTM)\b", "tr", "medium"),
    _a("atm_count", rf"(?P<num>{_NUM})\s+ATMs?\b", "en", "medium"),
    # --- POS (require an explicit device noun; "POS cirosu"/turnover is a TL
    #     amount, not a count, so a bare "<n> POS" is too loose) --------------
    _a("pos_count", rf"POS\s+(?:terminali|cihaz[ıi]|say[ıi]s[ıi]|aded[ıi])\D{{0,10}}(?P<num>{_NUM})", "tr", "high"),
    _a("pos_count", rf"(?P<num>{_NUM})\s+(?:adet\s+)?POS\s+(?:terminali|cihaz[ıi])\b", "tr", "medium"),
    _a("pos_count", rf"(?P<num>{_NUM})\s+POS\s+(?:terminals?|devices?)\b", "en", "medium"),
    # --- merchants (label-before REQUIRES "sayısı" so a trailing "+%3.1"
    #     growth figure can't be grabbed; number-before takes a scale suffix
    #     for the common "647 bin üye iş yeri" form) ------------------------
    _a("merchant_count", rf"üye\s*i[şs]\s*yeri\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    _a("merchant_count", rf"(?P<num>{_NUM}){_SUF}\s+üye\s*i[şs]\s*yeri", "tr", "high"),
    _a("merchant_count", rf"(?P<num>{_NUM})\s+(?:member\s+)?merchants?\b", "en", "medium"),
    # --- customers (often "X milyon müşteri") ----------------------------
    _a("customer_active", rf"aktif\s+müşteri\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    _a("customer_active", rf"(?P<num>{_NUM}){_SUF}\s+aktif\s+müşteri", "tr", "medium"),
    _a("customer_digital", rf"dijital\s+müşteri\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    _a("customer_digital", rf"(?P<num>{_NUM}){_SUF}\s+dijital\s+müşteri", "tr", "medium"),
    _a("customer_digital", rf"(?P<num>{_NUM}){_SUF}\s+(?:active\s+)?digital\s+customers", "en", "medium"),
    _a("customer_total", rf"toplam\s+müşteri\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    # number-before-noun: drop the dative "müşteriye" (almost always prose like
    # "700 bin müşteriye uzanan", a sub-segment) — headline form is "<n> müşteri".
    _a("customer_total", rf"(?P<num>{_NUM}){_SUF}\s+(?:toplam\s+)?müşteri(?:si)?\b", "tr", "low"),
    _a("customer_total", rf"(?P<num>{_NUM}){_SUF}\s+customers\b", "en", "low"),
    # --- cards (usually in millions) -------------------------------------
    _a("cards_credit", rf"kredi\s+kart[ıi]\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    _a("cards_debit", rf"banka\s+kart[ıi]\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    _a("cards_total", rf"toplam\s+kart\s+say[ıi]s[ıi]\D{{0,10}}(?P<num>{_NUM}){_SUF}", "tr", "high"),
    _a("cards_credit", rf"(?P<num>{_NUM}){_SUF}\s+credit\s+cards\b", "en", "medium"),
    _a("cards_debit", rf"(?P<num>{_NUM}){_SUF}\s+debit\s+cards\b", "en", "medium"),
]

# Coordinate-anchor keywords per metric (Pass B). Lowercased substring match on a
# word cluster; the nearest numeric token in the same/adjacent row is taken.
# Coordinate anchoring is reserved for SHORT, DISTINCTIVE tile labels. POS and
# customers are intentionally excluded: "pos" matches "POS Cirosu" (turnover) and
# "müşteri"/"customer" appears in nearly every paragraph, so both steal stray
# nearby numbers. Customer counts come from the prose "<n> milyon müşteri" anchor.
_COORD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "atm_count":     ("atm",),
    "merchant_count": ("üye işyeri", "üye iş yeri", "merchant"),
}


def _norm(s: str) -> str:
    """Lowercase + drop the combining dot Python adds when lowercasing Turkish
    'İ' (lowercasing "İ" yields "i" + U+0307), so ASCII-ish keyword substrings match."""
    return s.lower().replace("̇", "")


def _detect_lang(text: str) -> str:
    """'en' if the report reads English, else 'tr'. Cheap heuristic on common words."""
    low = text.lower()
    tr_hits = sum(low.count(w) for w in ("şube", "müşteri", "personel", "yıl", "ve "))
    en_hits = sum(low.count(w) for w in ("branch", "customer", "employee", "the ", "and "))
    return "en" if en_hits > tr_hits else "tr"


def _in_band(metric: str, value: float, unit: str) -> bool:
    lo, hi = ABS_BANDS.get(metric, (0, float("inf")))
    return lo <= _abs_value(value, unit) <= hi


def extract_stats_from_text(text: str, page: int | None = None, lang: str = "tr"
                            ) -> list[FranchiseStat]:
    """Pass A — pull franchise stats from a block of page text. First match per
    metric wins (anchors are ordered specific→generic)."""
    out: list[FranchiseStat] = []
    found: set[str] = set()
    for anc in _ANCHORS:
        if anc.metric in found:
            continue
        for m in anc.rx.finditer(text):
            parsed = parse_count(m.group("num"), m.groupdict().get("suf"), lang)
            if parsed is None:
                continue
            val, unit = parsed
            if not _in_band(anc.metric, val, unit):
                continue
            snippet = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ").strip()
            out.append(FranchiseStat(anc.metric, val, unit, "current", page, lang,
                                     anc.rx.pattern[:24], snippet, anc.conf))
            found.add(anc.metric)
            break
    return out


# ---------------------------------------------------------------------------
# Coordinate anchor (Pass B)
# ---------------------------------------------------------------------------
def _xy_lines(pdf_path: str, page_idx_0: int, ytol: float = 3.0
              ) -> list[list[tuple[float, float, str]]]:
    """Page words clustered into rows by y. Each row is (x0, x1, text) sorted
    left-to-right. Mirrors loans_by_sector._xy_lines (kept local, no import)."""
    if not _HAS_FITZ:
        return []
    try:
        doc = fitz.open(pdf_path)
        words = doc[page_idx_0].get_text("words")
        doc.close()
    except Exception:
        return []
    if not words:
        return []
    buckets: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
    for w in words:
        buckets[int(round(w[1]))].append((w[0], w[2], w[4]))
    keys = sorted(buckets)
    merged: dict[int, list[tuple[float, float, str]]] = {}
    last = None
    for k in keys:
        if last is not None and k - last <= ytol:
            merged[last].extend(buckets[k])
        else:
            merged[k] = list(buckets[k])
            last = k
    out: list[list[tuple[float, float, str]]] = []
    for y in sorted(merged):
        out.append(sorted(merged[y], key=lambda t: t[0]))
    return out


_NUM_ONLY = re.compile(rf"^\(?(?P<num>{_NUM})\)?$")


def extract_stats_from_words(rows: list[list[tuple[float, float, str]]],
                             page: int | None = None, lang: str = "tr",
                             want: set[str] | None = None) -> list[FranchiseStat]:
    """Pass B — for each wanted metric, locate its anchor keyword cluster and take
    the nearest numeric token (same row, or the row directly above/below — an
    infographic stacks a big number over its label). Geometry only; emitted at
    'low' confidence (unvalidated against a real layout)."""
    want = want or set(_COORD_KEYWORDS)
    out: list[FranchiseStat] = []
    # Flatten numeric tokens with their row index and x-centre.
    numbers: list[tuple[int, float, str]] = []  # (row_idx, x_centre, token)
    for ri, row in enumerate(rows):
        for x0, x1, t in row:
            if _NUM_ONLY.match(t.strip()):
                numbers.append((ri, (x0 + x1) / 2.0, t.strip()))
    for metric in want:
        kws = _COORD_KEYWORDS.get(metric, ())
        best: tuple[float, str] | None = None
        best_d = 1e9
        for ri, row in enumerate(rows):
            line = _norm(" ".join(t for _, _, t in row))
            if not any(k in line for k in kws):
                continue
            # anchor x-centre = midpoint of the keyword tokens on this row. A
            # multi-word keyword ("üye işyeri") is split across tokens, so a token
            # counts when it overlaps any keyword either way.
            kw_xs = [(x0 + x1) / 2.0 for x0, x1, t in row
                     if any(_norm(t) in k or k in _norm(t) for k in kws)]
            ax = sum(kw_xs) / len(kw_xs) if kw_xs else 0.0
            for nri, xc, tok in numbers:
                if abs(nri - ri) > 1:            # same / adjacent row only
                    continue
                d = abs(xc - ax) + abs(nri - ri) * 1000.0  # prefer same row, then x-near
                if d < best_d:
                    parsed = parse_count(tok, None, lang)
                    if parsed and _in_band(metric, parsed[0], parsed[1]):
                        best, best_d = (parsed[0], parsed[1]), d
        if best is not None:
            out.append(FranchiseStat(metric, best[0], best[1], "current", page, lang,
                                     "coord", None, "low"))
    return out


# ---------------------------------------------------------------------------
# PDF driver
# ---------------------------------------------------------------------------
def _n_pages(pdf: pdfplumber.PDF, pdf_path: str = "") -> int:
    if _HAS_FITZ and pdf_path:
        try:
            doc = fitz.open(pdf_path)
            n = doc.page_count
            doc.close()
            return n
        except Exception:
            pass
    return len(pdf.pages)


def extract_from_pdf(pdf: pdfplumber.PDF, pdf_path: str = "",
                     fiscal_year: int | None = None, max_pages: int = 60
                     ) -> FranchiseReport:
    """Scan the first ``max_pages`` pages (franchise highlights live up front).

    Pass A (prose regex) runs on the concatenated text; Pass B (coordinate) fills
    only metrics A missed. An image-only PDF (no text layer) is flagged is_ocr and
    yields zero stats — a coverage gap, not a failure.
    """
    rep = FranchiseReport(pdf_path=pdf_path, fiscal_year=fiscal_year)
    rep.n_pages = _n_pages(pdf, pdf_path)
    limit = min(max_pages, rep.n_pages)

    page_texts: list[str] = []
    for i in range(limit):
        try:
            page_texts.append(pdf.pages[i].extract_text() or "")
        except Exception:
            page_texts.append("")
    full = "\n".join(page_texts)
    if not full.strip():
        rep.is_ocr = True
        return rep
    rep.report_lang = _detect_lang(full)

    # Pass A — per page so we can record source_page; first match per metric wins.
    found: dict[str, FranchiseStat] = {}
    for i, txt in enumerate(page_texts):
        if not txt.strip():
            continue
        for s in extract_stats_from_text(txt, page=i + 1, lang=rep.report_lang):
            if s.metric_key not in found:
                found[s.metric_key] = s

    # Pass B — coordinate fill for still-missing coord-supported metrics.
    missing = {m for m in _COORD_KEYWORDS if m not in found}
    if missing and _HAS_FITZ and pdf_path:
        for i in range(limit):
            if not missing:
                break
            rows = _xy_lines(pdf_path, i)
            for s in extract_stats_from_words(rows, page=i + 1, lang=rep.report_lang,
                                              want=missing):
                if s.metric_key not in found:
                    found[s.metric_key] = s
                    missing.discard(s.metric_key)

    rep.stats = list(found.values())
    return rep


def extract(pdf_path: str | Path, fiscal_year: int | None = None) -> FranchiseReport:
    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        return extract_from_pdf(pdf, pdf_path, fiscal_year)


def summarize(rep: FranchiseReport) -> str:
    head = (f"{Path(rep.pdf_path).name}  [{rep.report_lang}]  "
            f"pages={rep.n_pages}  ocr={rep.is_ocr}")
    if not rep.stats:
        return head + "\n  (no franchise stats found)"
    lines = [head]
    for s in sorted(rep.stats, key=lambda x: (x.period_type, x.metric_key)):
        v = f"{s.value:,.2f}".rstrip("0").rstrip(".") if s.unit != "count" else f"{int(s.value):,}"
        lines.append(f"  {s.period_type:<7} {s.metric_key:<17} {v:>15} {s.unit:<9} "
                     f"p.{s.source_page or 0:<3} {s.confidence:<6} | {(s.raw_snippet or '')[:50]}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else "data/_tmp_faaliyet.pdf"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(summarize(extract(path, year)))
