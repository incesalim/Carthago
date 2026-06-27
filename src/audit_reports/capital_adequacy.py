"""Capital-adequacy extractor — BRSA §4.1 "Total capital" table.

Every BRSA audit report carries a capital-adequacy disclosure with two numeric
columns (Current Period | Prior Period) and clearly-labelled total rows:

    Total Common Equity Tier I Capital ............ 444,145,526  439,429,164
    Total Tier I Capital .......................... 444,145,526  439,429,164
    Total Tier II Capital ......................... 147,663,444  138,736,242
    Total Capital ( Total of Tier I and Tier II ).. 591,806,874  578,162,530
    Total Risk Weighted Assets .................... 3,154,771,905 2,645,600,330
    CET1 Capital Ratio (%) ........................ 14.08  16.61
    Tier I Capital Ratio (%) ...................... 14.08  16.61
    Capital Adequacy Ratio (%) .................... 18.76  21.85

This is the same deterministic approach as loans_by_sector.py / npl_movement.py:
locate the section by heading anchors, then pull each metric's value off its
labelled row. Amounts are kept in the report's native unit (thousand TRY);
ratios are stored as percentages (18.76 = 18.76%). Two rows are emitted per
report: period_type 'current' and 'prior'.

Arithmetic sanity (CET1<=Tier1<=Total, CAR≈capital/RWA) is checked downstream in
scripts/check_audit_quality.py, consistent with the other audit tables.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import _HAS_FITZ, parse_num


# ---------------------------------------------------------------------------
# Metric label registry. Ordered so the first matching field wins on a line.
# Each entry: (field, is_ratio, [regex variants]). Regexes are matched
# case-insensitively against the line's leading label. Turkish variants cover
# Turkish-language reports (the English ones are convenience translations).
# ---------------------------------------------------------------------------
# Banks label these rows in English ("Tier I" roman OR "Tier 1" digit) or in
# Turkish, and mix number formats (TR: 1.234.567 / 16,79 ; EN: 1,234,567 / 16.79).
# `_TI` / `_TII` absorb the roman-vs-digit variation everywhere.
_TI = r"Tier\s*(?:I|1)"
_TII = r"Tier\s*(?:II|2)"
_KON = r"(?:Konsolide\s+)?"      # TR consolidated-report label prefix (VAKIFK)
_CONS = r"(?:Consolidated\s+)?"  # EN equivalent
# Label patterns use \s* between words throughout: TSKB's 2023–2024 reports
# squish ALL inter-word spaces out of the text layer ("Core EquityTier1Capital
# BeforeDeductions", "CapitalAdequacyRatio(%) 22,87 26,16") while the numbers
# keep their separating spaces, and EXIM glues word pairs the same way.
_FIELDS: list[tuple[str, bool, list[str]]] = [
    ("cet1_capital", False, [
        rf"^Total\s*Common\s*Equity\s*{_TI}\s*Capital\b",
        rf"^Common\s*Equity\s*{_TI}\s*[Cc]apital\s*\(\s*CET\s*1\s*\)",
        # TSKB says "Core" instead of "Common" and writes the post-deduction
        # total without a "Total" prefix ("Core Equity Tier I Capital
        # 44.540.818"). The Before-Deductions line never matches: squished or
        # not, "Capital" is followed by "Before" (\b/lookahead reject it),
        # and the all-caps section header carries no numbers.
        rf"^(?:Total\s*)?Core\s*Equity\s*{_TI}\s*Capital\b(?!\s*Before)",
        r"^Çekirdek\s+Sermaye\s+Toplamı\b",
    ]),
    ("additional_tier1_capital", False, [
        rf"^Total\s*Additional\s*(?:{_TI}|Core)\s*[Cc]apital\b",
        r"^İlave\s+Ana\s+Sermaye\s+Toplamı\b",
    ]),
    ("tier1_capital", False, [
        rf"^Total\s*{_TI}\s*[Cc]apital\b(?!\s*(?:Ratio|Adequacy))",
        r"^Ana\s+Sermaye\s+Toplamı\b",
    ]),
    ("tier2_capital", False, [
        rf"^Total\s*{_TII}\s*[Cc]apital\b",
        r"^Katkı\s+Sermaye\s+Toplamı\b",
    ]),
    ("total_capital", False, [
        r"^Total\s*Capital\b",
        r"^Total\s*Own\s*Funds\b",
        r"^Toplam\s+Özkaynak\b",
        # EXIM words the current-period total differently from the prior table:
        # "Total Equity (Total Tier I and Tier II Capital)" /
        # "The sum of Tier I Capital and Tier II Capital (Total Capital)".
        rf"^Total\s*Equity\s*\(\s*Total\s*(?:of\s+)?{_TI}\s*and\s*{_TII}",
        rf"^The\s*sum\s*of\s*{_TI}\s*Capital\s*and\s*{_TII}\s*Capital",
    ]),
    ("total_rwa", False, [
        r"^Total\s*Risk[\s-]?Weighted\s*(?:Assets|Amount|Items)",
        # \s* not \s+: the text layer routinely glues the words of this row
        # ("Toplam RiskAğırlıklı" VAKBN, "ToplamRisk Ağırlıklı" ANADOLU,
        # "ToplamRiskAğırlıklı" ATBANK) even though the figures keep their
        # spaces — same squish the §4 start anchor already tolerates. [ğg]
        # absorbs the occasional de-accented "Agirlikli".
        r"^Toplam\s*Risk\s*A[ğg]ırlıklı\s*(?:Tutar|Varlık)",
    ]),
    # Ratio labels use \s* between words: pdfplumber sometimes drops the space
    # between words in these rows (EXIM: "Capital AdequacyRatio (%)").
    # Consolidated reports may prefix the labels (VAKIFK: "Konsolide Sermaye
    # Yeterliliği Oranı") — _KON/_CONS absorb that.
    ("cet1_ratio", True, [
        rf"^{_CONS}CET\s*1\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_CONS}Common\s*Equity\s*{_TI}\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_CONS}Core\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_KON}Çekirdek\s+Sermaye\s+Yeterlili[ğg]i\s+Oranı",
    ]),
    ("tier1_ratio", True, [
        rf"^{_CONS}{_TI}\s*Capital\s*(?:Adequacy\s*)?Ratio",
        rf"^{_KON}Ana\s+Sermaye\s+Yeterlili[ğg]i\s+Oranı",
    ]),
    ("capital_adequacy_ratio", True, [
        rf"^{_CONS}Capital\s*Adequacy\s*(?:Standard\s*)?Ratio",
        rf"^{_KON}Sermaye\s+Yeterlili[ğg]i\s+(?:Standart\s+)?Oranı",
    ]),
]
_FIELD_RX = [(f, is_ratio, [re.compile(p, re.IGNORECASE) for p in pats])
             for f, is_ratio, pats in _FIELDS]

# Section anchors (where the §4.1 capital table starts / ends). The start is the
# "before deductions" CET1 line, which sits at the top of the components table.
_START_RX = [re.compile(p, re.IGNORECASE) for p in [
    rf"(?:Common|Core)\s*Equity\s*{_TI}\s*[Cc]apital\s*[Bb]efore",
    # \s* not \s+: ANADOLU's text layer squishes this header
    # ("İndirimler ÖncesiÇekirdekSermaye") even though the rows below keep spaces.
    r"İndirimler\s*Öncesi\s*Çekirdek\s*Sermaye",
    r"Components\s+of\s+(?:the\s+)?total\s+capital",
]]
_END_RX = [re.compile(p, re.IGNORECASE) for p in [
    r"Capital\s*Adequacy\s*(?:Standard\s*)?Ratio\s*\(\s*%",
    r"^Sermaye\s+Yeterlili[ğg]i\s+(?:Standart\s+)?Oranı",
]]
_SKIP_PAGES = 12          # clear cover / auditor / TOC / statements front matter
_MAX_SECTION_PAGES = 8    # how far past the start we keep scanning


# A numeric token: 1,234.56 / 1.234,56 / (1,208) / 14.08 / 16,79 / 11,71% / %5.50 / - (nil)
# Allows a leading OR trailing '%' (Turkish reports often write "%5.50").
_NUM_TOKEN = re.compile(r"^%?\(?-?\d[\d.,]*%?\)?$")
_NIL = {"-", "—", "–"}
# Superscript footnote markers rendered inline, e.g. ATBANK's
# "Sermaye Yeterliliği Oranı (%) (2) 17.77" — "(2)" is a note reference, not a
# value. A real negative amount always carries separators/decimals.
_FOOTNOTE = re.compile(r"^\(\d\)$")
# Capital ratios are percentages well under 100; anything outside the band is a
# parse artefact (e.g. the year "2021." off a wrapped narrative sentence).
_RATIO_BAND = (0.0, 100.0)

# TFKB-class text damage: the PDF text layer detaches the leading digit of
# every number ("Toplam Özkaynak 1 1,372,338 1 0,094,760" = 11,372,338 and
# 10,094,760; "Oranı (%) 2 0.20 1 7.85" = 20.20 and 17.85). Rejoin a lone digit
# to the numeric/decimal fragment that follows. Values on the rows we read are
# never genuine bare single digits, so the join is unambiguous in practice.
_SPLIT_SEP = re.compile(r"(\d)\s+([.,]\d)")               # "7 ,348,196" / "2 .500"
_SPLIT_DIGIT = re.compile(r"\b(\d)\s+(?=\d[\d.,]*(?:\s|$))")  # "2 0.20" / "1 1,372,338"


def _repair_split_digits(line: str) -> str:
    line = _SPLIT_SEP.sub(r"\1\2", line)
    return _SPLIT_DIGIT.sub(r"\1", line)


def _parse_ratio(tok: str) -> float | None:
    """Parse a percentage token, tolerant of TR (16,79) and EN (16.79) decimals.
    Ratios are small (<~100), so a lone comma is always the decimal separator."""
    t = tok.strip().strip("%").strip("()").strip()
    if t in _NIL or not t:
        return None
    if "," in t and "." not in t:
        t = t.replace(",", ".")            # 16,79 -> 16.79
    elif "," in t and "." in t:
        # Both separators present: the RIGHTMOST one is the decimal separator.
        # A ratio can exceed 1000 (an FC LCR of "1.158,00" = 1158.00%), so the
        # format must be inferred, not assumed EN — blindly stripping commas read
        # TR "1.158,00" as 1.158 (the FIBA lcr_fc bug). TR "1.158,00" (comma last)
        # -> drop "." then ",→."; EN "1,016.79" (dot last) -> drop ",".
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")  # 1.158,00 -> 1158.00
        else:
            t = t.replace(",", "")                     # 1,016.79 -> 1016.79
    try:
        return float(t)
    except ValueError:
        return None


@dataclass
class CapitalRow:
    period_type: str  # 'current' | 'prior'
    cet1_capital: float | None = None
    additional_tier1_capital: float | None = None
    tier1_capital: float | None = None
    tier2_capital: float | None = None
    total_capital: float | None = None
    total_rwa: float | None = None
    cet1_ratio: float | None = None
    tier1_ratio: float | None = None
    capital_adequacy_ratio: float | None = None


@dataclass
class CapitalReport:
    pdf_path: str = ""
    source_page: int | None = None
    rows: list[CapitalRow] = field(default_factory=list)


def _trailing_two_tokens(line: str) -> list[str]:
    """Return the last two numeric tokens on a line, left-to-right [current,
    prior]. Walks right-to-left and stops at the first non-numeric token, so
    digits embedded in labels (the '1' in 'CET1') are ignored."""
    collected: list[str] = []
    for tok in reversed(line.split()):
        if _FOOTNOTE.match(tok):
            continue
        if tok in _NIL or _NUM_TOKEN.match(tok):
            collected.append(tok)
            if len(collected) == 2:
                break
        else:
            break
    collected.reverse()
    return collected


def _fitz_lines(pdf_path: str):
    """Return a (get_lines, n) pair that rebuilds each page's text LINES from
    fitz words by tight y-clustering (≤3px), so a row's label and its trailing
    numbers land on one line again.

    pdfplumber sometimes letter-spaces a whole §4 page ("T o p lam R isk
    A ğ ırlık lı T u tarlar") AND drops the figures onto separate baselines, so
    its line text carries no value — the RWA/ratio rows then never parse.
    fitz reads the same page with the label and its two figures on the same
    baseline, so the STANDARD `_parse_section` (label → trailing-two-numbers)
    pairs them correctly. This is preferred over the wide-table window parser
    for TFKB-class damage: the window parser mis-pairs columns (it grabbed the
    PRIOR-period RWA as current); a clean clustered line does not."""
    import fitz
    doc = fitz.open(pdf_path)

    def get_lines(i: int) -> list[str]:
        if i >= len(doc):
            return []
        words = doc[i].get_text("words")
        rows: list[tuple[float, list[tuple[float, str]]]] = []
        for w in sorted(words, key=lambda w: (w[1], w[0])):
            if rows and w[1] - rows[-1][0] <= 3.0:
                rows[-1][1].append((w[0], w[4]))
            else:
                rows.append((w[1], [(w[0], w[4])]))
        return [" ".join(t for _, t in sorted(toks)) for _, toks in rows]

    return get_lines, len(doc), doc


def _parse_section_fitz(pdf_path: str, start: int, n: int) -> tuple[dict, dict, list]:
    """Wide-table fallback: FIBA renders the §4 table with the value on a
    different baseline from its (often wrapped) label — pdfplumber drops the
    label onto a value-less line. Here each label line is matched on a tight
    y-cluster, then its value is taken from the number tokens in a y-window
    [y-3, y+12] (values sit on or just below the label's first line; the row
    above is excluded), so wrapped labels still pair with the right row."""
    if not _HAS_FITZ:
        return {}, {}, []
    import fitz
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return {}, {}, []
    current: dict[str, float | None] = {}
    prior: dict[str, float | None] = {}
    tc_candidates: list[tuple[float, float | None]] = []
    end_seen = False
    for i in range(start, min(n, start + _MAX_SECTION_PAGES)):
        words = doc[i].get_text("words")
        # tight y-clusters for the LABEL text (so we read each printed line)
        rows: list[tuple[float, list[tuple[float, str]]]] = []
        for w in sorted(words, key=lambda w: (w[1], w[0])):
            if rows and w[1] - rows[-1][0] <= 3.0:
                rows[-1][1].append((w[0], w[4]))
            else:
                rows.append((w[1], [(w[0], w[4])]))
        for y, toks in rows:
            label = _repair_split_digits(" ".join(t for _, t in sorted(toks)).strip())
            if not label:
                continue
            for fld, is_ratio, rxs in _FIELD_RX:
                if fld != "total_capital" and fld in current:
                    continue
                if not any(rx.match(label) for rx in rxs):
                    continue
                window = sorted(w for w in words if y - 3 <= w[1] <= y + 12
                                and (_NUM_TOKEN.match(w[4]) or w[4] in _NIL))
                # _repair_split_digits: TFKB's interim splits the leading digit of
                # every figure ("1 4,988,678" = 14,988,678) — rejoin in x-order.
                num_toks = _trailing_two_tokens(
                    _repair_split_digits(" ".join(w[4] for w in window)))
                if not num_toks:
                    break
                parse = _parse_ratio if is_ratio else parse_num
                cur = parse(num_toks[0])
                if cur is None or (is_ratio and not (_RATIO_BAND[0] < cur < _RATIO_BAND[1])):
                    break
                pri = parse(num_toks[1]) if len(num_toks) > 1 else None
                if is_ratio and pri is not None and not (_RATIO_BAND[0] < pri < _RATIO_BAND[1]):
                    pri = None
                if fld == "total_capital":
                    tc_candidates.append((cur, pri))
                else:
                    current[fld] = cur
                    prior[fld] = pri
                break
            if current and any(rx.search(label) for rx in _END_RX):
                end_seen = True
        if end_seen:
            break
    doc.close()
    return current, prior, tc_candidates


def _parse_section(get_lines, start: int, n: int) -> tuple[dict, dict, list]:
    """Walk the §4 section from `start`, matching each field's label and reading
    the trailing two numbers. `get_lines(i)` supplies page i's text lines (from
    pdfplumber or the fitz fallback). total_capital is collected as candidates
    (an intermediate 'Tier I+II' line plus the final own-funds line)."""
    current: dict[str, float | None] = {}
    prior: dict[str, float | None] = {}
    tc_candidates: list[tuple[float, float | None]] = []
    end_seen = False
    for i in range(start, min(n, start + _MAX_SECTION_PAGES)):
        for raw in get_lines(i):
            ln = _repair_split_digits(raw.strip())
            if not ln:
                continue
            for fld, is_ratio, rxs in _FIELD_RX:
                if fld != "total_capital" and fld in current:
                    continue  # first occurrence wins (except total_capital)
                if any(rx.match(ln) for rx in rxs):
                    toks = _trailing_two_tokens(ln)
                    if not toks:
                        continue
                    parse = _parse_ratio if is_ratio else parse_num
                    cur = parse(toks[0])
                    if cur is None:
                        continue
                    if is_ratio and not (_RATIO_BAND[0] < cur < _RATIO_BAND[1]):
                        continue  # year/footnote artefact; let a real row match later
                    pri = parse(toks[1]) if len(toks) > 1 else None
                    if (is_ratio and pri is not None
                            and not (_RATIO_BAND[0] < pri < _RATIO_BAND[1])):
                        pri = None
                    if fld == "total_capital":
                        tc_candidates.append((cur, pri))
                    else:
                        current[fld] = cur
                        prior[fld] = pri
                    break
            # Only treat the CAR-ratio line as the section end AFTER some component
            # has been read — ALNTF's §4 opens with an intro "…Sermaye Yeterliliği
            # Standart Oranına İlişkin Açıklamalar" on the start page, which matches
            # _END_RX and otherwise stops the scan before the component rows (on the
            # next page) are ever reached, yielding 0 rows.
            if current and any(rx.search(ln) for rx in _END_RX):
                end_seen = True
        if end_seen:
            break
    return current, prior, tc_candidates


def extract_from_pdf(pdf: pdfplumber.PDF, pdf_path: str = "") -> CapitalReport:
    rep = CapitalReport(pdf_path=pdf_path)
    n = len(pdf.pages)
    # Locate the section start.
    start = None
    for i in range(min(_SKIP_PAGES, n), n):
        if any(rx.search(pdf.pages[i].extract_text() or "") for rx in _START_RX):
            start = i
            break
    # fitz fallback for the locator too: TFKB's interim text layer mangles the
    # header so badly under pdfplumber that even the \s*-tolerant anchor misses
    # it — fitz reads the same page cleanly (the components then come via
    # _parse_section_fitz below).
    if start is None and pdf_path and _HAS_FITZ:
        import fitz
        try:
            doc = fitz.open(pdf_path)
            for i in range(min(_SKIP_PAGES, n), n):
                if any(rx.search(doc[i].get_text()) for rx in _START_RX):
                    start = i
                    break
            doc.close()
        except Exception:
            pass
    if start is None:
        return rep
    rep.source_page = start + 1

    current, prior, tc_candidates = _parse_section(
        lambda i: (pdf.pages[i].extract_text() or "").splitlines(), start, n)
    # Fitz fallback when pdfplumber's text layer fails some rows. Two distinct
    # damage modes need two strategies:
    #
    #  (a) pdfplumber read NOTHING (FIBA): the §4 table renders the value a few px
    #      off the label's baseline, so pdfplumber's line-clustering drops the
    #      label onto its own value-less line. The wide-table WINDOW parser
    #      (`_parse_section_fitz`) re-pairs label↔value across baselines.
    #
    #  (b) pdfplumber read the components but MISSED total_rwa / the ratios (TFKB:
    #      a whole §4 page is letter-spaced — "T o p lam R isk A ğ ırlık lı" — and
    #      the figures sit on separate baselines, so pdfplumber's line text is
    #      value-less). Rebuilding the LINES off fitz words (label + its two
    #      figures cluster back onto one baseline) lets the STANDARD parser pair
    #      them. Preferred over the window parser, which mis-pairs the columns
    #      (it grabbed the PRIOR-period RWA as current) — so only the components
    #      pdfplumber missed are filled, and RWA/ratios come from the reliable
    #      clustered-line parse.
    need_fitz = not current or "total_rwa" not in current or "cet1_capital" not in current
    if pdf_path and _HAS_FITZ and need_fitz:
        if not current:
            current, prior, tc_candidates = _parse_section_fitz(pdf_path, start, n)
        else:
            # Try the clustered-LINE parse first (TFKB: correct column pairing).
            try:
                get_lines, fn, doc = _fitz_lines(pdf_path)
            except Exception:
                get_lines = None
            if get_lines is not None:
                try:
                    fcur, fpri, ftc = _parse_section(get_lines, start, fn)
                finally:
                    doc.close()
                for k, v in fcur.items():
                    current.setdefault(k, v)
                    prior.setdefault(k, fpri.get(k))
                if not tc_candidates:
                    tc_candidates = ftc
            # FIBA-class still misses total_rwa here (its values sit off the
            # label baseline, so clustered lines stay value-less) — fall back to
            # the wide-table window parser, filling only the safe fields. NOT
            # additional_tier1 / tier2: the window pass mis-pairs them (it can
            # grab the prior-period CET1 as AT1), which would break composition.
            if "total_rwa" not in current:
                wcur, wpri, wtc = _parse_section_fitz(pdf_path, start, n)
                _MERGE_OK = {"cet1_capital", "tier1_capital", "total_rwa",
                             "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio"}
                for k in _MERGE_OK:
                    if k in wcur:
                        current.setdefault(k, wcur[k])
                        prior.setdefault(k, wpri.get(k))
                if not tc_candidates:
                    tc_candidates = wtc

    if tc_candidates:
        best_cur, best_pri = max(tc_candidates, key=lambda t: t[0])
        current["total_capital"] = best_cur
        prior["total_capital"] = best_pri

    # SKBNK-class row shift: the labelled Tier1 row can carry a neighbouring
    # row's value (usually the AT1 amount). Tier1 = CET1 + AT1 by definition,
    # so a Tier1 below CET1 is always a misread — rebuild from the identity,
    # picking the candidate that best matches the reported Tier1 ratio × RWA
    # when both are available (SKBNK 2022Q4: misread 16,233 IS the AT1 →
    # 4,502,933; 2025Q4: misread 8,585,373 IS the AT1 → 21,144,203).
    # When the Tier1 row is missing entirely (TSKB: the wrapped label never
    # yields tokens), fill CET1+AT1 only if the reported Tier1 ratio × RWA
    # confirms it within 2% — quarters where AT1 itself was missed stay NULL
    # rather than storing a confidently wrong number.
    for vals in (current, prior):
        cet1, t1 = vals.get("cet1_capital"), vals.get("tier1_capital")
        if cet1 is None:
            continue
        at1 = vals.get("additional_tier1_capital") or 0
        ratio, rwa = vals.get("tier1_ratio"), vals.get("total_rwa")
        target = ratio * rwa / 100.0 if (ratio and rwa) else None
        if t1 is not None and t1 < cet1:
            cands = [cet1 + at1, cet1 + t1]
            vals["tier1_capital"] = (min(cands, key=lambda c: abs(c - target))
                                     if target else cands[0])
        elif t1 is None and target:
            cand = cet1 + at1
            if abs(cand - target) <= 0.02 * target:
                vals["tier1_capital"] = cand

    if current:
        rep.rows.append(CapitalRow(period_type="current", **current))
    if any(v is not None for v in prior.values()):
        rep.rows.append(CapitalRow(period_type="prior", **prior))
    return rep


def extract(pdf_path: str | Path) -> CapitalReport:
    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        return extract_from_pdf(pdf, pdf_path)


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
_VALUE_COLS = [
    "cet1_capital", "additional_tier1_capital", "tier1_capital", "tier2_capital",
    "total_capital", "total_rwa", "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio",
]


def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: CapitalReport,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_capital WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    cols = ["bank_ticker", "period", "kind", "period_type", *_VALUE_COLS, "source_page"]
    ph = ", ".join("?" for _ in cols)
    rows = [(
        bank_ticker, period, kind, r.period_type,
        *[getattr(r, c) for c in _VALUE_COLS],
        rep.source_page,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            f"INSERT INTO bank_audit_capital ({', '.join(cols)}) VALUES ({ph})", rows
        )
    conn.commit()
    return len(rows)


def summarize(rep: CapitalReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no capital table found)"
    lines = [f"{Path(rep.pdf_path).name}  (page {rep.source_page})"]
    for r in rep.rows:
        def f(v):
            return f"{v:,.0f}" if v is not None and abs(v) >= 1000 else (
                f"{v}" if v is not None else "-")
        lines.append(
            f"  {r.period_type:<7} CET1={f(r.cet1_capital):>16} T1={f(r.tier1_capital):>16} "
            f"T2={f(r.tier2_capital):>16} TC={f(r.total_capital):>16} RWA={f(r.total_rwa):>18} "
            f"| CET1%={r.cet1_ratio} T1%={r.tier1_ratio} CAR%={r.capital_adequacy_ratio}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "data/raw/_diag/GARAN_2026Q1_unconsolidated.pdf"
    print(summarize(extract(path)))
