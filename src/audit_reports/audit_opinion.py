"""Audit-opinion extractor — the auditor's verdict, from the front of the report.

Every BRSA report opens with the independent auditor's report. For annual (Q4)
filings it is a full audit carrying an **Opinion**; for interim (Q1-Q3) filings
it is a limited review carrying a **Conclusion**. Either can be *modified*:

  clean       unqualified / unmodified — the numbers are presented fairly
  qualified   "except for" one matter — everything else is fair
  adverse     the statements as a whole do not present fairly
  disclaimer  the auditor could not form an opinion at all

We captured none of this before — the pipeline read the numbers a bank reported
but never whether its own auditor stood behind them. That blind spot is exactly
what let ALBRK's Q1-2025 "record profit" pass unremarked: PwC had qualified the
accounts (over a ₺7bn free-provision reversal), and we had no field to see it.
A modified opinion is strictly more informative than any ratio computed from the
same numbers — the person paid to verify them is telling you not to.

This is a deterministic, fitz-only text classifier (no LLM, no pdfplumber). It
anchors on the section HEADINGS the auditing standards mandate, which appear only
in the auditor's report at the very front — so it never trips on the word
"qualified" buried in a later footnote.

Observed heading forms (English convenience translations and Turkish originals):
  Audit (annual):
    "Qualified Opinion" / "Basis for Qualified Opinion"                (ALBRK FY24)
    "Unqualified Opinion" / plain "Opinion" + "present fairly"
    "Şartlı Görüş" / "Şartlı Görüşün Dayanağı" / "Olumlu Görüş"
  Review (interim):
    "Basis for the Qualified Conclusion" / "Qualified Conclusion"      (ALBRK Q125)
    "Conclusion" + "nothing has come to our attention"                 (clean)
    "Şartlı Sonuç" / "Sınırlı Denetim ... Sonuç"

Stored in `bank_audit_opinion`, one row per (bank_ticker, period, kind).
"""
from __future__ import annotations

import re
import sqlite3
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# --- Opinion modifiers (checked most-severe first) -------------------------
# Each is a section heading, not stray prose. `Şartlı`/`Olumsuz` are matched
# case-insensitively; the ASCII-folded variants cover reports whose text layer
# drops the Turkish diacritics.
_ADVERSE = re.compile(r"\bAdverse\s+(?:Opinion|Conclusion)\b|Olumsuz\s+Görü[sş]", re.I)
_DISCLAIMER = re.compile(
    r"\bDisclaimer\s+of\s+(?:Opinion|Conclusion)\b"
    r"|Görü[sş]\s+(?:Bildirmekten|Vermekten)\s+Ka[çc][ıi]nma",
    re.I,
)
# Qualified — the "Qualified Opinion/Conclusion" heading (the `(?<![A-Za-z])`
# lookbehind is essential: it keeps the "qualified Opinion" inside the CLEAN
# heading "Unqualified Opinion" from matching), or the Turkish equivalents.
# Turkish qualified is written either "Şartlı Görüş/Sonuç" or, in review
# reports, "Sınırlı Olumlu Görüş/Sonuç" ("limited-positive" = qualified — note
# it embeds "Olumlu", so it MUST be tested before the clean "Olumlu Görüş").
_QUALIFIED = re.compile(
    r"(?<![A-Za-z])Qualified\s+(?:Opinion|Conclusion)"
    r"|[ŞS]artl[ıi]\s+(?:Görü[sş]|Sonu[çc])"
    r"|S[ıi]n[ıi]rl[ıi]\s+Olumlu\s+(?:Görü[sş]|Sonu[çc])",
    re.I,
)
# Clean signals — an explicit unmodified heading, or the fair-presentation
# language that only a clean opinion/conclusion carries (English audit, English
# review "nothing has come to our attention", and their Turkish equivalents:
# clean audit "Olumlu Görüş"; clean review "...dikkatimizi çekmemiştir").
_CLEAN = re.compile(
    r"\bUn(?:qualified|modified)\s+(?:Opinion|Conclusion)\b"
    r"|(?<![ıiİI]\s)Olumlu\s+Görü[sş]"
    r"|nothing\s+has\s+come\s+to\s+our\s+attention"
    r"|present[s]?\s+fairly,\s+in\s+all\s+material\s+respects"
    r"|In\s+our\s+opinion,\s+the\s+accompanying"
    r"|ger[çc]e[ğg]e\s+uygun\s+bir\s+bi[çc]imde\s+sunmaktad[ıi]r"
    r"|dikkatimizi\s+çekmemi[sş]tir"
    r"|kanaatine\s+varmam[ıi]za\s+sebep\s+ol",
    re.I,
)

# --- Report kind: full audit vs limited review ----------------------------
_REVIEW_MARK = re.compile(
    r"review\s+report|interim\s+financial|limited\s+review|SRE\s*2410"
    r"|we\s+have\s+reviewed|S[ıi]n[ıi]rl[ıi]\s+(?:Ba[ğg][ıi]ms[ıi]z\s+)?Denetim"
    r"|[İI]nceleme|ara\s+d[öo]nem",
    re.I,
)
_AUDIT_MARK = re.compile(
    r"we\s+have\s+audited|independent\s+auditor.?s\s+report"
    r"|Ba[ğg][ıi]ms[ıi]z\s+Denet[çc]i\s+Raporu|denetlemi[sş]",
    re.I,
)

# --- Auditor firm (best-effort; canonicalised to the global brand) --------
_AUDITORS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"PwC|PricewaterhouseCoopers|Ba[şs]aran\s+Nas", re.I), "PwC"),
    (re.compile(r"KPMG|Akis\s+Ba[ğg][ıi]ms[ıi]z", re.I), "KPMG"),
    (re.compile(r"Güney\s+Ba[ğg][ıi]ms[ıi]z|Ernst\s*&\s*Young|\bEY\b", re.I), "EY"),
    (re.compile(r"Deloitte|DRT\s+Ba[ğg][ıi]ms[ıi]z", re.I), "Deloitte"),
    (re.compile(r"Grant\s+Thornton", re.I), "Grant Thornton"),
    (re.compile(r"BDO\b", re.I), "BDO"),
    (re.compile(r"Aksis\s+Uluslararas[ıi]\s+Ba[ğg][ıi]ms[ıi]z", re.I), "Aksis"),
]

# Where the basis paragraph ends — the next section heading in the report.
_BASIS_END = re.compile(
    r"\n\s*(?:[0-9A-Za-z]{1,3}[.)]\s*)?"
    r"(?:Qualified|Adverse|Unqualified)\s+(?:Opinion|Conclusion)"
    r"|\n\s*(?:Key\s+Audit\s+Matters|Emphasis\s+of\s+Matter"
    r"|Responsibilities?\s+of|Management.?s\s+Responsib|Auditor.?s\s+Responsib"
    r"|Other\s+Matter|Conclusion\b|Sonu[çc]\b|Görü[sş]\b"
    r"|[ŞS]artl[ıi]\s+(?:Sonu[çc]|Görü[sş])"
    r"|S[ıi]n[ıi]rl[ıi]\s+Olumlu\s+(?:Sonu[çc]|Görü[sş])"
    r"|Kilit\s+Denetim\s+Konular[ıi]|Di[ğg]er\s+Husus"
    r"|Mevzuattan\s+Kaynaklanan|Y[öo]netimin\s+ve)",
    re.I,
)

# This section describes other reporting matters, often the PREVIOUS auditor's
# opinion. It is after the current conclusion and must not change that verdict.
# ALNTF's clean 2023 reviews mention 2022 qualified opinions in this paragraph.
_OTHER_MATTER_HEADING = re.compile(
    r"(?m)^\s*(?:[0-9A-Za-z]{1,3}[.)]\s*)?"
    r"(?:Other\s+Matters?|Di[ğg]er\s+Husus(?:lar)?)\s*(?:\n|$)",
    re.I,
)

_OPINION_TYPES = ("clean", "qualified", "adverse", "disclaimer", "unknown")


@dataclass
class OpinionResult:
    opinion_type: str = "unknown"     # clean | qualified | adverse | disclaimer | unknown
    report_kind: str = "audit"        # audit (annual) | review (interim)
    basis_text: str | None = None     # the "Basis for ..." paragraph, if modified
    auditor: str | None = None        # canonical firm brand, if detected
    language: str = "en"              # en | tr
    source_page: int | None = None    # 0-indexed page the opinion heading sat on

    @property
    def is_modified(self) -> bool:
        return self.opinion_type in ("qualified", "adverse", "disclaimer")

    def is_empty(self) -> bool:
        return self.opinion_type == "unknown"


def _detect_language(text: str) -> str:
    """Turkish original vs English convenience translation. English reports
    still embed some Turkish, so decide on the auditor's own verbs."""
    if re.search(r"we\s+have\s+(?:audited|reviewed)|In\s+our\s+opinion", text, re.I):
        return "en"
    if re.search(r"Ba[ğg][ıi]ms[ıi]z\s+Denet|Görü[sş]üm[üu]z|denetlemi[sş]", text, re.I):
        return "tr"
    return "en"


def _detect_report_kind(text: str, period: str = "") -> str:
    """Limited review (interim) vs full audit (annual). Text wins; the period
    quarter is only a tiebreaker (Q4 ⇒ audit, else review)."""
    audit = bool(_AUDIT_MARK.search(text))
    review = bool(_REVIEW_MARK.search(text))
    if review and not audit:
        return "review"
    if audit and not review:
        return "audit"
    # Ambiguous or both present — fall back to the period.
    if period:
        return "audit" if period.upper().endswith("Q4") else "review"
    return "review" if review else "audit"


# The "Basis for/of ..." heading — English (EY templates write "Basis OF
# Qualified Conclusion", others "Basis FOR") and both Turkish forms (Şartlı /
# Sınırlı Olumlu, Görüş / Sonuç).
# Turkish basis endings: "Dayanağı" (singular) and KPMG's "Dayanakları" (plural).
_BASIS_HEADING = re.compile(
    r"Basis\s+(?:for|of)\s+(?:the\s+)?(?:Qualified|Adverse)\s+(?:Opinion|Conclusion)"
    r"|[ŞS]artl[ıi]\s+(?:Görü[sş]ün|Sonucun)\s+Dayana(?:[ğg][ıi]|klar[ıi])"
    # TFKB 2024Q4 consolidated actually prints "Olumlı" in this heading.
    r"|S[ıi]n[ıi]rl[ıi]\s+Oluml[uıi]\s+(?:Görü[sş]ün|Sonucun)\s+Dayana(?:[ğg][ıi]|klar[ıi])",
    re.I,
)


def _extract_basis(text: str) -> str | None:
    """Capture the 'Basis for [the] Qualified/Adverse ...' paragraph up to the
    next section heading. Whitespace-collapsed and length-capped.

    The heading phrase appears twice in most reports — once as an in-sentence
    cross-reference inside the Opinion paragraph ("…described in the Basis for
    Qualified Opinion section below…") and once as the actual heading on its own
    line. Prefer the standalone-heading occurrence so we capture the real basis,
    not the fair-presentation sentence that references it."""
    chosen = None
    for m in _BASIS_HEADING.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[line_start:m.start()].strip(" \t0123456789.)-")
        line_end = text.find("\n", m.end())
        rest_of_line = text[m.end(): line_end if line_end >= 0 else len(text)]
        # Heading alone on its line: nothing meaningful before it, little after.
        if prefix == "" and len(rest_of_line.strip()) < 15:
            chosen = m
            break
    if chosen is None:
        matches = list(_BASIS_HEADING.finditer(text))
        if not matches:
            return None
        chosen = matches[-1]  # fall back to the last occurrence

    tail = text[chosen.end():]
    end = _BASIS_END.search(tail)
    para = tail[: end.start()] if end else tail[:1800]
    # Collapse the fitz line-per-token layout into readable prose.
    para = re.sub(r"\s*\n\s*", " ", para)
    para = re.sub(r"\s{2,}", " ", para).strip(" :.-–\t")
    return (para[:1800]).strip() or None


def _detect_auditor(text: str) -> str | None:
    for pat, name in _AUDITORS:
        if pat.search(text):
            return name
    return None


def _current_opinion_text(text: str) -> str:
    end = _OTHER_MATTER_HEADING.search(text)
    return text[:end.start()] if end else text


_OVERRIDE_PATH = Path(__file__).resolve().parents[2] / "data" / "audit_opinion_overrides.json"


@lru_cache(maxsize=1)
def _auditor_overrides() -> dict:
    try:
        return json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8")).get("reports", {})
    except (OSError, ValueError):
        return {}


def _verified_auditor_override(pdf_path: str) -> str | None:
    """A visually read image-only signature applies only to those exact bytes."""
    path = Path(pdf_path)
    entry = _auditor_overrides().get(path.name)
    if not entry:
        return None
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    if digest != entry.get("sha256"):
        return None
    return entry.get("auditor") or None


def classify_opinion(text: str, period: str = "") -> OpinionResult:
    """Classify the auditor's verdict from the front-matter text of a BRSA report.

    Pure function over already-extracted text — no PDF, no fitz — so it is unit
    testable and safe to import in the minimal-deps CI job. `period` (e.g.
    '2025Q1') is an optional tiebreaker for audit-vs-review only."""
    if not text or not text.strip():
        return OpinionResult(opinion_type="unknown")

    res = OpinionResult(
        report_kind=_detect_report_kind(text, period),
        language=_detect_language(text),
        auditor=_detect_auditor(text),
    )

    # Severity order: adverse > disclaimer > qualified > clean. `Disclaimer of
    # Opinion` is a heading; the review boilerplate "we do not express an
    # opinion" is NOT a disclaimer and is deliberately not matched here.
    verdict_text = _current_opinion_text(text)
    if _ADVERSE.search(verdict_text):
        res.opinion_type = "adverse"
    elif _DISCLAIMER.search(verdict_text):
        res.opinion_type = "disclaimer"
    elif _QUALIFIED.search(verdict_text):
        res.opinion_type = "qualified"
    elif _CLEAN.search(verdict_text):
        res.opinion_type = "clean"
    else:
        res.opinion_type = "unknown"

    if res.is_modified:
        res.basis_text = _extract_basis(verdict_text)
    return res


def extract_opinion_from_pdf(
    pdf_path: str = "",
    period: str = "",
    max_pages: int = 6,
) -> OpinionResult:
    """Classify the opening pages and, if needed, find the signature through p10.

    Annual reports can sign on pages 7–9. Those extra pages supply only the firm,
    never verdict text: later financial notes can mention historical opinions.
    fitz-only, same engine as every other lane.
    """
    # Lazy import so the pure classifier above stays importable without fitz
    # (the CI unit tests exercise classify_opinion directly).
    from .extractor import _fitz_page_count, _fitz_page_text, _HAS_FITZ

    if not (pdf_path and _HAS_FITZ):
        return OpinionResult(opinion_type="unknown")

    page_count = _fitz_page_count(pdf_path) or 0
    n = min(max_pages, page_count)
    pages = [_fitz_page_text(pdf_path, i) for i in range(n)]
    text = "\n".join(pages)
    res = classify_opinion(text, period=period)

    # Best-effort: which page carried the opinion/basis heading.
    if not res.is_empty():
        anchor = {"adverse": _ADVERSE, "disclaimer": _DISCLAIMER,
                  "qualified": _QUALIFIED}.get(res.opinion_type, _CLEAN)
        for i, pg in enumerate(pages):
            if anchor.search(pg):
                res.source_page = i
                break
        if res.auditor is None:
            for i in range(n, min(10, page_count)):
                res.auditor = _detect_auditor(_fitz_page_text(pdf_path, i))
                if res.auditor:
                    break
        if res.auditor is None:
            res.auditor = _verified_auditor_override(pdf_path)
    return res


def upsert_opinion(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    result: OpinionResult,
    *,
    commit: bool = True,
) -> int | None:
    """Idempotently store one bank's opinion row. Returns 1 if written, None if
    the classification was 'unknown' (so a failed re-extract can't overwrite a
    previously-captured opinion — same skip-if-empty rule as bank_profile)."""
    if result is None or result.is_empty():
        return None
    conn.execute(
        "INSERT OR REPLACE INTO bank_audit_opinion "
        "(bank_ticker, period, kind, opinion_type, is_modified, report_kind, "
        " basis_text, auditor, language, source_page) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            bank_ticker, period, kind,
            result.opinion_type, int(result.is_modified), result.report_kind,
            result.basis_text, result.auditor, result.language, result.source_page,
        ),
    )
    if commit:
        conn.commit()
    return 1


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    period = sys.argv[2] if len(sys.argv) > 2 else ""
    r = extract_opinion_from_pdf(path, period=period)
    print(f"{Path(path).name}: {r.opinion_type.upper()} ({r.report_kind}) "
          f"auditor={r.auditor} lang={r.language} page={r.source_page}")
    if r.basis_text:
        print("  basis:", r.basis_text[:300])
