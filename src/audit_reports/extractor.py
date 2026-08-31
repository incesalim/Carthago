"""Extract financial statements from Turkish BRSA-format audit-report PDFs.

BRSA reports follow a standardized template across banks. Statements live on a few
specific pages near the start:
  - Balance Sheet — Assets       (6 columns: TL/FC/Total × current/prior period)
  - Balance Sheet — Liabilities  (same 6 columns)
  - Off-Balance Sheet Items      (same 6 columns)
  - Statement of Profit or Loss  (2 columns: current/prior period)

We locate the pages by header signatures, then parse rows where each line is:
  hierarchy_token  item_name  [footnote_ref]  N numeric_columns
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# The audit-statement parsers are fitz (PyMuPDF) only. `_fitz_page_text`
# reconstructs each row from word x/y boxes — a superset of the old pdfplumber
# layout-repair: it also maps /Rotate 90 pages through the page rotation matrix
# (GARAN/AKBNK landscape statements), which pdfplumber handled implicitly and
# naive fitz did not. See the 2026-06-27 equity migration and this change.
try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:  # pragma: no cover - fitz is a hard dep in CI/local
    _HAS_FITZ = False


# --- fitz-based page count -----------------------------------------------------
def _fitz_page_count(pdf_path: str) -> int | None:
    """Page count via fitz (instant, and immune to the pdfminer page-tree
    enumeration that hangs on a few poison PDFs, e.g. VAKBN 2025Q4)."""
    if not _HAS_FITZ:
        return None
    try:
        doc = fitz.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return None


# Match a numeric token. Handles both EN and TR thousands/decimal conventions:
#   EN:  1,234,567.89
#   TR:  1.234.567,89
# Also bare integers and standalone dash runs ("-"/"--") for disclosed zero.
# Negatives may be wrapped in parens. DENIZ uses "--" for each nil cell; losing
# those cells shifts a complete triplet into the short-row recovery path.
# The bare-dash alternative is anchored to whitespace on both sides so the
# dash inside a label decoration like "Expected Credit Losses (-)" — or a
# hyphenated word ("Held-for-Sale") — is never counted as a value column.
NUM_PAT = r'(?:\(\s*-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*\)|-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|(?<!\S)-+(?!\S))'

# Hierarchy marker at line start. The bare-roman alternative
# (`[IVX]+(?=\s+[A-ZÇĞİÖŞÜ])`) matches a Roman numeral with NO trailing dot
# when it's immediately followed by an uppercase (section-header) label —
# ALNTF prints its first section as "I FİNANSAL VARLIKLAR (Net)" (no dot)
# while later sections keep the dot, so the dotted-only pattern dropped roman I
# and Σromans fell short of the grand total. The `(?!\s+ARLIKLAR…)` guard stops
# it eating the column-header word "VARLIKLAR" (assets) when its text layer
# splits it as "V ARLIKLAR" (ATBANK) — the only observed false positive.
# Gated further by the uppercase lookahead plus the n-numeric-column
# requirement in _parse_rows, so it can't admit prose.
HIERARCHY_PAT = re.compile(
    r'^(?P<h>(?:[IVX]+\.|[IVX]+(?=\s+[A-ZÇĞİÖŞÜ])(?!\s+ARLIKLAR)|[A-Z]\.|\d+(?:\.\d+)*\.?))\s+(?P<rest>.+)$'
)
# Grand-total rows ("TOTAL ASSETS", "VARLIKLAR TOPLAMI", "TOPLAM AKTİFLER",
# "PASİF TOPLAMI", …) carry no hierarchy prefix, so they're admitted as data
# rows via this pattern. Must cover Turkish (TOPLAM) as well as English (TOTAL),
# or Turkish-language reports lose their total-assets / total-liabilities lines.
TOTAL_PAT = re.compile(r'(?:TOTAL|TOPLAM)', re.I)

_NUM_RX = re.compile(NUM_PAT)
# Leading hierarchy marker on a data line ("2.4", "1.1.4.", "IX.", "A.").
# Set aside before scanning for value tokens: a dotted-decimal marker like
# "1.1.4." otherwise matches NUM_PAT ("1.1" + "4"), inflating the token count
# into the multi-period branch and shifting the label boundary — which dropped
# rows like "2.4 Expected Credit Losses (-) (6) …" or stored the footnote
# "(6)" as the value -6 under a label truncated at "(".
_LINE_HIER_RX = re.compile(
    r'^\s*(?:[IVX]+\.|[A-Z]\.|\d+(?:\.\d+)*\.?)(?=\s|[A-Za-zÇĞİÖŞÜçğıöşü(])')
# A parenthesized 1-2 digit integer next to the label is a dipnot (footnote
# section) reference, not a value.
_FOOTNOTE_RX = re.compile(r'\(\s*\d{1,2}\s*\)')
# Bracketed footnote section-refs like "(5.I.14)", "(5.II.10)", "(5.1.14)".
# NUM_PAT splits these at the dots into spurious value tokens ("5","14") — and
# on long wrapping labels the all-dash value columns interleave around the ref
# (ICBCT held-for-sale rows: "…İLİŞKİN - - - DURAN VARLIKLAR (Net) (5.I.16) - - -"),
# so the leaked digits land in the value slots. Masked (offset-preserved) before
# tokenizing so neither the digits nor the label boundary are disturbed.
# Two safe shapes ONLY, so a TR-format negative value "(178.162)" (= -178,162,
# three-digit thousands group) is NOT mistaken for a footnote ref and masked
# away (that zeroed HSBC's 16.3 equity row): (a) contains a roman part —
# "(5.I.16)", "(5.II.10)"; (b) digit-only with every dotted group 1-2 digits —
# "(5.1.14)". A 3-digit dotted group means thousands (a value), never a ref.
_SECTION_REF_RX = re.compile(
    r'\(\s*\d+\.[IVXivx]+(?:\.[0-9A-Za-z]+)*\.?\s*\)'  # roman section, optional letter
    r'|\(\s*\d+(?:\.\d{1,2}){1,3}\.?\s*\)')       # all groups 1-2 digits
# A label that is nothing but a hierarchy marker — the row's text label wrapped
# onto an adjacent line, leaving "<marker> <values>". Such a row is real data.
# Numeric groups are capped at 1-2 digits: real BRSA markers are "16.5.4", never
# 3-digit groups — so a TR-format number like "37.239.656" (EXIM's label-less
# total line) is NOT mistaken for a marker and turned into a bogus row.
_BARE_MARKER_RX = re.compile(r'(?:[IVX]+\.?|[A-Z]\.|\d{1,2}(?:\.\d{1,2})*\.?)')
# Duplicated-digit render artifact: a thousands group of 3 digits "XYZ" comes
# out as the 5-digit "XYZYZ" — the final two digits repeated (ANADOLU:
# "21,817,92727" for 21,817,927; "16,370,25252" for 16,370,252). A real group
# is always exactly 3 digits, so a 5-digit group with this XYZYZ shape is
# unambiguously the artifact. Repaired to "XYZ" before tokenizing.
_DUP_DIGIT_RX = re.compile(r'([.,])(\d)(\d{2})\3(?=\D|$)')
# Roman-numeral footnote refs. Two forms, both safe to mask (a real value never
# starts with a roman letter, and roman-roman pairs never occur in a BS label):
#   (a) PARENTHESIZED "(I-10)", "(II-8)", "(I-e-f)" — TEB/EXIM dipnot column;
#       the trailing digits ("-10") otherwise leak as a value and truncate the
#       label (TEB 4.3 "(I-10)" → stored -10 / -5).
#   (b) UNPARENTHESIZED "V-II-9", "V-I-15", "V - I - 13" — ANADOLU; and the
#       digit-led dipnot column "5-II-5", "5-II-10" — DUNYAK/EMLAK, where the
#       "5" is the note SECTION number. The middle element is always roman, so a
#       plain value (which never carries a roman letter) can't match either way.
_ROMAN_FN_RX = re.compile(
    r'\(\s*[IVXivx]+\s*-\s*[A-Za-z0-9][A-Za-z0-9.\s-]*\)'         # (a) parenthesized
    r'|\b(?:[IVX]+|\d{1,2})\s*-\s*[IVX]+(?:\s*-\s*\d{1,3})?\b'
    r'|\b[IVX]+-\d{1,3}\b')  # simple unbracketed note: IV-6, IV-12
# Comma-for-dot hierarchy markers: BURGAN 2025Q3's text layer renders the
# marker separator as a comma — "I,", "1,1", "1,1,1" — the SAME glyph as the
# thousands separator. TSKB goes further and renders ONLY the last separator as
# a comma once a section passes nine sub-items ("2.1.9" then "2.1,10" … "2.1,13")
# — a MIXED dot/comma marker. Both forms are normalized: any comma in the
# leading marker becomes a dot, so "2.1,13" → "2.1.13" and its value rejoins the
# parent 2.1 sum (else the whole 2.1.13 row is dropped). Only the LEADING marker
# is touched; thousands groups are 3 digits ("17,740,253") so they never match
# the 1-2-digit components here, and a normal dotted marker has no comma →
# unchanged. The substitution is comma→dot (1-for-1), so column offsets hold.
# The numeric branch also accepts a marker GLUED to its label with no space —
# AKBNK renders off-balance row 1.1 as "1,1Teminat Mektupları" (comma AND no
# separator). Requiring a following space dropped that row from 2026Q2, and with
# it the hierarchy sum for "I. GARANTİ ve KEFALETLER", ₺483.5bn short. A letter
# can never follow a thousands separator, and the components here are 1-2 digits
# while a thousands group is 3, so this cannot match a value.
_COMMA_MARKER_RX = re.compile(
    r'^\s*(?:[IVXivx]+,(?=\s)|\d{1,2}(?:[.,]\d{1,2}){1,3}(?=\s|[^\W\d_]))')


def _value_matches(line: str) -> list:
    """Numeric-token matches on a data line, excluding the hierarchy marker."""
    m0 = _LINE_HIER_RX.match(line)
    return list(_NUM_RX.finditer(line, m0.end() if m0 else 0))


def _count_values(line: str) -> int:
    """How many true value columns a line carries (no marker, no dipnot refs)."""
    line = _ROMAN_FN_RX.sub(" ", _SECTION_REF_RX.sub(" ", line))
    return sum(1 for m in _value_matches(line) if not _FOOTNOTE_RX.fullmatch(m.group()))


def _triplet_ok(tl: float | None, fc: float | None, tot: float | None) -> bool:
    """The BRSA row identity TL + FC = Total, with thousands-rounding slack."""
    if tl is None or fc is None or tot is None:
        return False
    return abs((tl + fc) - tot) <= max(3.0, abs(tot) * 1e-5)


def _try_split_digit_joins(line: str, nums_m: list) -> list[float] | None:
    """TSKB-class text damage splits a number into two tokens ('16. 462.594'
    → '16' + '462.594', the separator stranded in the gap). For a 6-column
    row carrying 7-8 tokens, try re-joining gap-adjacent fragments and accept
    ONLY an interpretation where BOTH the current and prior triplets satisfy
    TL + FC = Total — a false join can't pass two identities at once."""
    n_extra = len(nums_m) - 6
    if n_extra not in (1, 2):
        return None
    joinable: dict[int, float] = {}
    for i in range(len(nums_m) - 1):
        gap = line[nums_m[i].end():nums_m[i + 1].start()].strip()
        if gap not in ("", ".", ","):
            continue
        v = parse_num(nums_m[i].group() + gap + nums_m[i + 1].group())
        if v is not None:
            joinable[i] = v

    def interpretation(join_at: tuple[int, ...]) -> list[float] | None:
        vals: list[float] = []
        i = 0
        while i < len(nums_m):
            if i in join_at:
                vals.append(joinable[i])
                i += 2
            else:
                v = parse_num(nums_m[i].group())
                if v is None:
                    return None
                vals.append(v)
                i += 1
        if len(vals) != 6:
            return None
        if _triplet_ok(*vals[0:3]) and _triplet_ok(*vals[3:6]):
            return vals
        return None

    if n_extra == 1:
        for i in joinable:
            got = interpretation((i,))
            if got is not None:
                return got
    else:
        idxs = sorted(joinable)
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                if idxs[b] > idxs[a] + 1:  # non-overlapping
                    got = interpretation((idxs[a], idxs[b]))
                    if got is not None:
                        return got
        # Chain: one number split into THREE fragments ("5. 219 . 274" —
        # TSKB). Merge tokens i, i+1, i+2 when both gaps are joinable.
        for i in range(len(nums_m) - 2):
            if i in joinable and (i + 1) in joinable:
                g1 = line[nums_m[i].end():nums_m[i + 1].start()].strip()
                g2 = line[nums_m[i + 1].end():nums_m[i + 2].start()].strip()
                v = parse_num(nums_m[i].group() + g1 + nums_m[i + 1].group()
                              + g2 + nums_m[i + 2].group())
                if v is None:
                    continue
                vals: list[float] = []
                j = 0
                bad = False
                while j < len(nums_m):
                    if j == i:
                        vals.append(v)
                        j += 3
                    else:
                        pv = parse_num(nums_m[j].group())
                        if pv is None:
                            bad = True
                            break
                        vals.append(pv)
                        j += 1
                if (not bad and len(vals) == 6
                        and _triplet_ok(*vals[0:3]) and _triplet_ok(*vals[3:6])):
                    return vals
    return None


def _recover_current_triplet(tokens: list[float | None]) -> list[float | None] | None:
    """Identity-gated recovery for a 6-column row that lost tokens (a dash
    glyph the text layer drops — SKBNK '239,160 - 239,160 159,400 159,400' is
    5 tokens for 6 columns). We only store the CURRENT triplet, and the BRSA
    row identity TL + FC = Total tells us when a recovery is sound:
      1. the first three tokens already form a valid triplet (the shortfall
         was in the prior-period columns), or
      2. inserting a single 0 at the TL or FC position completes a valid
         triplet (the lost token was a dash = zero).
    Returns [tl, fc, total, None, None, None] or None — NEVER guesses without
    the identity confirming."""
    _ok = _triplet_ok
    if len(tokens) >= 3 and _ok(tokens[0], tokens[1], tokens[2]):
        return [tokens[0], tokens[1], tokens[2], None, None, None]
    # Zero-insertion needs ≥3 tokens for non-zero values (a bare hierarchy +
    # two coincidentally-equal numbers shouldn't fabricate a row); an
    # all-dash pair is safe (a genuine zero row).
    if len(tokens) >= 3 or (len(tokens) == 2 and tokens[0] == 0 and tokens[1] == 0):
        if _ok(0.0, tokens[0], tokens[1]):
            return [0.0, tokens[0], tokens[1], None, None, None]
        if _ok(tokens[0], 0.0, tokens[1]):
            return [tokens[0], 0.0, tokens[1], None, None, None]
    return None


def parse_num(s: str) -> float | None:
    s = s.strip()
    if s == '' or re.fullmatch(r'-+', s):
        return 0.0
    # The SIGN is stripped before the format sniff below, and must be, because
    # the sniff is anchored (`^\d{1,3}…$`) — a leading '-' failed it, so a
    # hyphen-negative with exactly ONE thousands group fell through to the
    # English branch and its separator was read as a DECIMAL POINT:
    # "-319.110" came back as -319.11 instead of -319110, a silent 1000× error.
    # Two groups ("-1.234.567") survived on the count('.') > 1 clause and
    # parenthesised negatives never reached the sniff, which is why this only
    # ever bit single-group hyphen-negatives — the §4 market-risk net-off and
    # gap rows. A number's sign must not change how its FORMAT is read: after
    # this, negatives parse exactly as the same digits do positive.
    neg = (s.startswith('(') and s.endswith(')')) or s.startswith('-')
    s = s.strip('()').strip().lstrip('-').strip()
    # Turkish format uses '.' as thousands separator and ',' as decimal
    # English format uses ',' as thousands separator and '.' as decimal
    # Distinguish by counting: if multiple dots and last group is 3 digits → TR
    if s.count('.') > 1 or (s.count('.') == 1 and s.count(',') == 0
                            and re.match(r'^\d{1,3}(\.\d{3})+$', s)):
        # Turkish format: dots are thousands, comma is decimal
        s = s.replace('.', '').replace(',', '.')
    else:
        # English format: commas are thousands, dot is decimal
        s = s.replace(',', '')
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def parse_amount(s: str) -> float | None:
    """`parse_num`, but a cell that is EMPTY or nothing but dashes reads as nil.

    Footnote tables print a nil cell as "-", "--" or an en/em dash, and a run of
    dashes is not a value `parse_num` can see: it only special-cases the single
    "-". Lanes that read note tables (loans_by_sector, npl_movement) need the
    run form too, or a trailing "--" drops the row and the next line's numbers
    get merged onto the wrong label.
    """
    s = s.strip()
    if not s or all(c in "-–—" for c in s):   # "", "-", "--", "—" … → nil
        return 0.0
    return parse_num(s)


@dataclass
class StatementRow:
    order: int
    hierarchy: str
    name: str
    footnote: str | None
    cur_tl: float | None = None
    cur_fc: float | None = None
    cur_total: float | None = None
    pri_tl: float | None = None
    pri_fc: float | None = None
    pri_total: float | None = None
    cur_amount: float | None = None  # for P&L
    pri_amount: float | None = None  # for P&L


@dataclass
class BankReport:
    pdf_path: str
    bs_assets: list[StatementRow] = field(default_factory=list)
    bs_liabilities: list[StatementRow] = field(default_factory=list)
    off_balance: list[StatementRow] = field(default_factory=list)
    profit_loss: list[StatementRow] = field(default_factory=list)
    # Other Comprehensive Income — single-column statement that follows P&L.
    other_comprehensive_income: list[StatementRow] = field(default_factory=list)
    # Populated by extract() when credit-quality scan succeeds. Kept on the
    # same object so downstream callers (upsert_report) get one report per PDF.
    credit_quality: "list" = field(default_factory=list)
    # Branch counts + personnel extracted from the qualitative section.
    # Stored as a dict (or None) so the loader can persist it cheaply.
    bank_profile: object = None
    # Sector-level loan exposure (Stage 2 / Stage 3 / ECL by sector).
    loans_by_sector: "list" = field(default_factory=list)
    # NPL gross-amount roll-forward by BRSA group (III / IV / V).
    npl_movement: "list" = field(default_factory=list)
    # §4 risk-management ratios — full report objects (capital_adequacy.py /
    # liquidity.py) carrying rows + source_page; persisted by upsert_report.
    capital: object = None
    liquidity: object = None
    # §4 market-risk (CAMELS "S") — full report objects (fx_position.py /
    # repricing.py) carrying rows + source_page; persisted by upsert_report.
    fx_position: object = None
    repricing: object = None
    # Cash flow statement — single-column like OCI (current period only).
    cash_flow: list[StatementRow] = field(default_factory=list)
    # Statement of changes in equity — wide BRSA template, two pages.
    equity_change: object = None
    # Independent auditor's verdict (audit_opinion.OpinionResult or None).
    audit_opinion: object = None
    # Free provision / serbest karşılık stock (free_provision.FreeProvision or None).
    free_provision: object = None
    # Section-scoped narrative prose (prose.ProseResult or None).
    prose: object = None


def _split_label(label: str) -> tuple[str, str, str]:
    """Returns (hierarchy_token, clean_name, footnote_ref). Footnote is a trailing
    pattern like '5.1.1' that follows the item name."""
    stripped = label.strip()
    m = HIERARCHY_PAT.match(stripped)
    if m:
        h = m.group('h')
        rest = m.group('rest').strip()
    elif _BARE_MARKER_RX.fullmatch(stripped):
        # Label is ONLY a marker — text wrapped to an adjacent line (KUVEYT
        # "1.2."). Keep the marker as the hierarchy so the validator/dashboard
        # can place the row; name is empty (dashboard labels by code).
        h = stripped
        rest = ''
    else:
        h = ''
        rest = stripped
    # Footnote ref: trailing token like 5.1.1 or 5.4.12
    footnote = None
    fm = re.search(r'\s(\d+(?:\.\d+){1,3})$', rest)
    if fm:
        footnote = fm.group(1)
        rest = rest[: fm.start()].strip()
    return h, rest, footnote


def _triplets_foot(vals: list[float | None], n_cols: int) -> bool:
    """True when every 3-column period block satisfies tl + fc == total.

    Balance-sheet and off-balance rows come in triplets (TL, FC, Total) per
    period, so a row can check ITSELF — no other row, no validator. Used to tell
    a genuine small paren-negative from a dipnot reference, a distinction that
    only became ambiguous when the sector switched to Milyon TL.
    """
    if n_cols <= 0 or n_cols % 3 or len(vals) != n_cols:
        return False
    for s in range(0, n_cols, 3):
        tl, fc, total = vals[s], vals[s + 1], vals[s + 2]
        if tl is None or fc is None or total is None:
            return False
        # ABSOLUTE, not relative. A 5e-5 relative band is ~56 units on a
        # ₺1.1bn row, wide enough to admit TOMK's "1.2 … (3) 1.117.694
        # 1.117.694 1.084.780 308.064 1.392.844", where the (3) is a dipnot ref
        # and the row is off by exactly 3. This test is only worth having if it
        # means the row proves itself, so it has to be exact.
        if abs((tl + fc) - total) > 1.0:
            return False
    return True


def _parse_rows(text: str, n_cols: int, *,
                keep_small_negatives: bool = False) -> list[tuple[str, list[float | None]]]:
    """For each line that ends in N numeric tokens, return (label, values)."""
    rows: list[tuple[str, list[float | None]]] = []
    for line in text.split('\n'):
        line = line.rstrip()
        if not line.strip():
            continue
        # Blank bracketed footnote section-refs ("(5.I.16)") with equal-length
        # spaces — kills the spurious value tokens NUM_PAT would split out of
        # them while preserving every other token's offset (so the label slice
        # and the recovery paths below stay correct).
        # Normalize a leading comma-for-dot hierarchy marker ("1,1" → "1.1",
        # "I," → "I.") — same length, so downstream offsets are preserved.
        line = _COMMA_MARKER_RX.sub(lambda m: m.group(0).replace(',', '.'), line, count=1)
        line = _SECTION_REF_RX.sub(lambda m: ' ' * len(m.group()), line)
        line = _ROMAN_FN_RX.sub(lambda m: ' ' * len(m.group()), line)
        # Repair the duplicated-digit artifact (XYZYZ → XYZ) so the garbled
        # token doesn't shift the value window or break its triplet.
        line = _DUP_DIGIT_RX.sub(r'\1\2\3', line)
        # Find all numeric tokens (positions included, marker excluded)
        nums_m = _value_matches(line)
        # A parenthesized 1-2 digit token IMMEDIATELY after the label is a
        # dipnot ref even when the line carries no surplus (SKBNK prints
        # "INVESTMENT PROPERTY (Net) (14) - - - - -", which used to store -14
        # as a value). Drop it; if the row then falls below n_cols it is
        # skipped — better lost than corrupted. EXCEPTION: paren-negative banks
        # (PASHA/ING/KLNMA/TFKB) print negative VALUES in parens, so "(69)" can
        # be a real value — recognisable because the NEXT token is also
        # parenthesized (a value sequence, not a lone footnote). Don't drop then.
        def _next_is_paren(ms):
            return len(ms) > 1 and ms[1].group().lstrip().startswith('(')
        while (nums_m and _FOOTNOTE_RX.fullmatch(nums_m[0].group())
               and not _next_is_paren(nums_m)):
            if keep_small_negatives and len(nums_m) == n_cols:
                break  # caller must validate the complete statement candidate
            # The 2026Q2 Milyon switch made a real value routinely 1-2 digits,
            # so a leading "(10)" is now as likely to be -10mn as a dipnot ref.
            # Keep it when the row only foots WITH it: KLNMA's
            # "1.1.4 Beklenen Zarar Karşılıkları (-) (10) - (10) (8) - (8)" is
            # two exact tl+fc=total triplets and lost its first cell, shifting
            # the whole row; SKBNK's "(14) - - - - -" foots as none and is still
            # a footnote. Only ever consulted when the count already matches the
            # template, so a row that needs the strip is unaffected.
            # With no surplus token, stripping GUARANTEES the row is lost — so
            # keep it, but ONLY when the row can prove itself complete by its
            # own triplet identity.
            #
            # Deliberately not extended to statements without triplets. It is
            # tempting: a 2-column cash flow has nowhere to put a dipnot ref
            # without creating surplus, so "(58) 4.480" looks like two values.
            # But SKBNK's P&L prints "XXII. … (8) -" directly above "(9) - -",
            # "(10) - -" and "(11) 1,502,150 254,698" — a note-number sequence,
            # and that reading would store -8, -9, -10, -11 as amounts. With no
            # identity to appeal to there is no way to tell the two apart, so
            # cash flow and P&L keep the old strip-and-drop behaviour.
            if len(nums_m) == n_cols and _triplets_foot(
                    [parse_num(x.group()) for x in nums_m], n_cols):
                break
            nums_m = nums_m[1:]
        # Dipnot refs like "(6)" sit between the label and the value columns;
        # drop them while the line still has surplus tokens, so they can never
        # be taken as a value (-6) or skew the triplet count below. Skip when
        # most tokens are parenthesized (paren-negative value row).
        if len(nums_m) > n_cols:
            paren = sum(1 for m in nums_m if m.group().lstrip().startswith('('))
            if paren <= 1:
                kept = [m for m in nums_m if not _FOOTNOTE_RX.fullmatch(m.group())]
                if len(kept) >= n_cols:
                    nums_m = kept
        recovered_vals: list[float | None] | None = None
        if n_cols == 6 and n_cols < len(nums_m) <= n_cols + 2:
            joined = _try_split_digit_joins(line, nums_m)
            if joined is not None:
                recovered_vals = list(joined)
                take = nums_m
        if recovered_vals is not None:
            pass
        elif len(nums_m) < n_cols:
            # Identity-gated short-row recovery: the text layer sometimes
            # loses a token (usually a dash glyph), which used to skip the
            # whole row. We only store the CURRENT triplet, and TL+FC=Total
            # confirms when a recovery is sound. 6-column statements only —
            # a 2-column P&L row has no internal identity to confirm with.
            if n_cols == 6 and len(nums_m) >= 2:
                recovered_vals = _recover_current_triplet(
                    [parse_num(m.group()) for m in nums_m])
            if recovered_vals is None:
                continue
            take = nums_m  # label boundary = first surviving token
        # Multi-period balance sheets (e.g. Eximbank) print 3+ periods, each as
        # a TL / FC / Total triplet, so a row carries 9, 12, … numbers. The
        # current and prior periods are the FIRST two triplets; the default
        # "last n_cols" grabs the prior + an older restated period instead,
        # storing the prior year-end as the current period. When the row is a
        # clean multiple of the 3-column triplet and has more than n_cols, take
        # the first n_cols. (Only affects 6-column statements — assets,
        # liabilities, off-balance — never the 2-column P&L.)
        elif n_cols % 3 == 0 and len(nums_m) > n_cols and len(nums_m) % 3 == 0:
            take = nums_m[:n_cols]
        else:
            take = nums_m[-n_cols:]
        # Garbled-token fallback: a duplicated-digit render artifact in a
        # PRIOR-period column ("21,817,92727", "16,370,25252" — ANADOLU) makes
        # the token count not a clean multiple of 3, so "last n_cols" slides the
        # window and the stored current triplet stops balancing. BRSA always
        # prints the current period as the FIRST TP/YP/Toplam triplet — if the
        # window's current triplet is broken but the first three tokens satisfy
        # TP+FC=Total, use those (prior slots left None). Only fires on failure,
        # so it can't disturb the clean EXIM multi-period rows.
        if (recovered_vals is None and n_cols == 6 and len(nums_m) > n_cols):
            win = [parse_num(m.group()) for m in take[:3]]
            if not _triplet_ok(*win):
                first3 = [parse_num(m.group()) for m in nums_m[:3]]
                if _triplet_ok(*first3):
                    recovered_vals = first3 + [None, None, None]
                    take = nums_m[:3]
        # Label = everything before the first taken value token.
        label = line[:take[0].start()].rstrip()
        if not label:
            continue
        # A label is admissible if it has a hierarchy marker + text, is a grand
        # total, OR is a BARE marker (label wrapped to an adjacent line — KUVEYT
        # "1.2. <6 numbers>"). HIERARCHY_PAT requires text after the marker, so
        # the bare-marker case needs its own clause.
        if not (HIERARCHY_PAT.match(label) or TOTAL_PAT.search(label)
                or _BARE_MARKER_RX.fullmatch(label.strip())):
            # Continuation line or noise
            continue
        # Reject pure date labels ("1 January 2024", "31 December 2024")
        if re.match(r'^\d+\.?\s+(January|February|March|April|May|June|July|August|September|October|November|December|Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\b', label):
            continue
        # Reject labels that look like page-/section-headers rather than BS rows.
        # AKBNK has a section header "I. 31 ARALIK 2025 TARİHİ İTİBARIYLA
        # KONSOLİDE OLMAYAN BİLANÇO ..." that the wrap-merge sometimes splices
        # together with the page-column header until 6 numbers accumulate. That
        # phantom-header splice only happens on the wide 6-column statements
        # (balance sheet / off-balance), so keep the strict 150-char cap there —
        # the frozen BS path is unaffected. The 2-column statements never accrete
        # a header that long, yet a few banks (ALBRK, ANADOLU, VAKBN) print a
        # genuinely verbose OCI line item — "2.2.2 Income/Expenses from Valuation
        # …/Reclassification of Financial Assets Measured at Fair Value through
        # Other Comprehensive Income" runs to ~167 chars — which a flat 150 cap
        # silently dropped. Give the narrow statements headroom (real line items
        # top out near 134 chars; the keyword/date regexes above still catch any
        # spliced header well before 200).
        if len(label) > (150 if n_cols >= 6 else 200):
            continue
        if re.search(
            r'(?:\d+\s+(?:Aralık|Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|'
            r'Ağustos|Eylül|Ekim|Kasım)\s+\d{2,4}'
            r'|TARİHİ\s+İTİBARIYLA|KONSOLİDE\s+OLMAYAN|FİNANSAL\s+DURUM\s+TABLOSU'
            r'|DİPNOT|CARİ\s+DÖNEM\s+ÖNCEKİ\s+DÖNEM'
            r'|FINANCIAL\s+(?:STATEMENTS|POSITION\s+STATEMENT)'
            # English / mixed-language section + column headers — QNBFB,
            # HSBC, BURGAN emit "I. BALANCE SHEET (STATEMENT OF FINANCIAL
            # POSITION) Curre…", "I. BİLANÇO Bağımsız Denetimden …",
            # "I. BALANCE SHEET Audited Audited Note" as phantom rows.
            # \s* (not \s+) so squished variants ("BALANCESHEET-ASSETS
            # CurrentPeriod PriorPeriod 31.12.2023 …", QNBFB) match too —
            # the two dates fragment into exactly 6 numeric tokens, which
            # otherwise admits the page header as a roman-I data row.
            # Lookarounds keep real OFF-balance data rows alive: ISCTR's
            # squished "A. OFF-BALANCESHEETCONTINGENCIES…" and
            # "TOTALOFF-BALANCESHEETCOMMITMENTS(A+B)" are data, not headers,
            # and Turkish "BİLANÇO DIŞI…" rows likewise.
            r'|(?<!OFF)(?<!OFF-)BALANCE\s*SHEET(?!\s*TOTAL)'
            # The off-balance PAGE TITLE ("… UNCONSOLIDATED STATEMENT OF
            # OFF-BALANCE SHEET ITEMS", ISCTR 2025Q4) is spared by the OFF- guard
            # above, then a date fragment ("31") tokenises as its value and it
            # posts as a phantom hierarchy-"5" row. A data row never says
            # "STATEMENT OF", so this reaches the title without touching
            # "A. OFF-BALANCE SHEET COMMITMENTS" / "TOTAL OFF-BALANCE SHEET…".
            r'|STATEMENT\s+OF\s+OFF[\s-]*BALANCE\s*SHEET'
            r'|STATEMENT\s+OF\s+FINANCIAL\s+POSITION'
            r'|BİLANÇO(?!\s*(?:TOPLAMI|DI[ŞS]I))'
            r'|Current\s*Period\s+Prior\s*Period'
            r'|Bağımsız\s+Denetimden'
            r'|Audited\s+Audited'
            r'|\bNote\s*$)',
            label,
            re.IGNORECASE,
        ):
            continue
        # After stripping the hierarchy prefix, a real BS row label always
        # starts with an alphabetic character (Turkish-extended). Numeric/date
        # starts (e.g. "31 ARALIK 202") are page-header noise. EXCEPTION: a
        # label that is ONLY a hierarchy marker ("1.2.") is a real data row
        # whose text label wrapped onto the adjacent line(s) — KUVEYT prints
        # "Gerçeğe Uygun…Zarara / 1.2. <6 numbers> / Yansıtılan Finansal…", so
        # the marker line carries the values but no inline label. Keep it; its
        # values reconcile the section sum, and the dashboard labels by code.
        if not _BARE_MARKER_RX.fullmatch(label.strip()):
            m_h = HIERARCHY_PAT.match(label)
            rest_after_hier = (m_h.group('rest') if m_h else label).lstrip()
            if rest_after_hier and not re.match(r"^[A-Za-zÇĞİÖŞÜçğıöşü(\[]", rest_after_hier):
                continue
        if recovered_vals is not None:
            vals = recovered_vals  # prior-period slots stay None by design
        else:
            vals = [parse_num(m.group()) for m in take]
            if any(v is None for v in vals):
                continue
        rows.append((label, vals))
    return rows


_TR_FOLD = str.maketrans({
    'ç': 'c', 'Ç': 'C', 'ğ': 'g', 'Ğ': 'G',
    'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O',
    'ş': 's', 'Ş': 'S', 'ü': 'u', 'Ü': 'U',
})


def _norm(s: str) -> str:
    """Normalize text for tolerant anchor matching:
       1. ASCII-fold Turkish characters (Ğ→G, İ→I, etc.)
       2. Uppercase
       3. Strip everything except A-Z

    This handles:
      * Squished output (TSKB: 'FINANCIALASSETS')
      * Mixed casing where Python's locale-blind upper() loses dots
        ('Nakit' uppercases to 'NAKIT' not 'NAKİT')
    """
    return re.sub(r'[^A-Z]', '', s.translate(_TR_FOLD).upper())


# Anchor token sets per statement. A page matches if the page text — once
# normalized — contains a "first-line" keyword preceded only by Roman 'I' marker(s)
# AND at least one supporting keyword.
#
# We store anchors as raw keyword fragments; matching uses a regex that allows
# the line to begin with one or more 'I' characters (handles cases like
# Alternatifbank where a section heading "I." merges into the first data row's
# hierarchy "I." → line starts with "II...").
#
# Supports:
#   * EN reports (Garanti, TSKB English)
#   * TR reports (Akbank, Halk, Ziraat, etc.)
#   * Participation banks ("Toplanan Fonlar", "Kâr Payı")
#   * Investment banks (no deposits → "Funds Borrowed" / "Alınan Krediler")
ANCHORS = {
    'bs_assets': {
        # Keyword (without leading 'I.') that should follow the Roman numeral
        'keywords': ['FINANCIALASSETS', 'FİNANSALVARLIKLAR', 'FINANSALVARLIKLAR'],
        # ANY of these in the page text → BS Assets confirmed
        'support': [
            'CASHANDBALANCES', 'CASHANDCASHEQUIVALENTS', 'CASHANDCENTRAL',
            'NAKİTDEĞERLER', 'NAKITDEGERLER', 'NAKİTVENAKİTBENZER', 'NAKITVENAKITBENZER',
            'MONEYMARKETPLACEMENTS', 'EXPECTEDCREDITLOSS',
            'AMORTIZEDCOST', 'İTFAEDİLMİŞMALİYET', 'ITFAEDILMISMALIYET',
        ],
    },
    'bs_liab': {
        'keywords': [
            'DEPOSITS', 'MEVDUAT',
            'TOPLANANFONLAR', 'FUNDSCOLLECTED',
            'FUNDSBORROWED', 'LOANSRECEIVED',
            'ALINANKREDİLER', 'ALINANKREDILER',
        ],
        'support': [
            'FUNDSBORROWED', 'LOANSRECEIVED',
            'ALINANKREDİLER', 'ALINANKREDILER',
            'MARKETABLESECURITIES', 'ISSUEDSECURITIES',
            'İHRAÇEDİLENMENKUL', 'IHRACEDILENMENKUL',
            'MONEYMARKET', 'PAYABLESTOMONEY',
            'PROVISIONS', 'KARŞILIKLAR', 'KARSILIKLAR',
        ],
    },
    'off_bs': {
        'keywords': ['GUARANTEES', 'GARANTİ', 'GARANTI'],
        'support': [
            'OFFBALANCESHEET', 'BİLANÇODIŞI', 'BILANCODIŞI', 'BILANCODISI',
            'NAZIMHESAPLAR', 'COMMITMENTSANDCONTINGENCIES', 'TAAHHÜTLER', 'TAAHHUTLER',
        ],
    },
    'pl': {
        # 'INTERSTINCOME' covers a typo in Eximbank PDFs
        'keywords': [
            'INTERESTINCOME', 'INTERSTINCOME', 'FAİZGELİRLERİ', 'FAIZGELIRLERI',
            'PROFITSHAREINCOME', 'KÂRPAYIGELİRLERİ', 'KARPAYIGELIRLERI',
        ],
        'support': [
            'INTERESTEXPENSE', 'FAİZGİDERLERİ', 'FAIZGIDERLERI',
            'PROFITSHAREEXPENSE', 'KÂRPAYIGİDERLERİ', 'KARPAYIGIDERLERI',
            'NETINTERESTINCOME', 'NETFAİZGELİRİ', 'NETKARPAYI',
            'NETFEESANDCOMMISSIONS', 'NETÜCRETVEKOMİSYON', 'NETUCRETVEKOMISYON',
        ],
    },
}


def _locate_pages(pdf_path: str) -> dict[str, int]:
    """Return 1-indexed page numbers for the four key statements.

    A line matches a 'kind' if its normalized form starts with one or more 'I'
    characters followed by one of the keywords for that kind. Supports cases
    where a section heading "I." gets merged with the first data row's "I."
    (e.g. Alternatifbank: 'I. I FİNANSAL VARLIKLAR' → 'IIFINANSALVARLIKLAR').
    """
    # Pre-compile per-kind matchers
    matchers = {}
    for kind, cfg in ANCHORS.items():
        kws = [_norm(k) for k in cfg['keywords']]
        # Pattern: ^I+ followed by any keyword
        pat = re.compile(r'^I+(?:' + '|'.join(re.escape(k) for k in kws) + r')')
        matchers[kind] = (
            pat,
            [_norm(k) for k in cfg['keywords']],
            [_norm(s) for s in cfg['support']],
        )
    out: dict[str, int] = {}
    # Helper: count rows that look like hierarchy+number patterns. Used to confirm
    # a page is actually a statement (not a section heading mentioning the words).
    def has_data_rows(text: str, min_rows: int = 8) -> bool:
        cnt = 0
        for ln in text.split('\n'):
            if re.match(r'^\s*(?:[IVX]+\.?|\d+(?:\.\d+){0,3}\.?)\s', ln) and re.search(r'\d{2,}', ln):
                cnt += 1
                if cnt >= min_rows:
                    return True
        return False
    # Iterate page indices via fitz's count — never materialise pdfplumber pages
    # (the pdfminer page-tree enumeration hangs on poison PDFs).
    for i in range(1, (_fitz_page_count(pdf_path) or 0) + 1):
        # Fitz text only — ~50× faster than pdfplumber's extract_text (which
        # dominated page-location time) and a SUPERSET for anchor detection: it
        # captures the absolutely-positioned text pdfplumber's column-flatten drops
        # (e.g. Akbank 2026Q1).
        text = _fitz_page_text(pdf_path, i - 1)
        norm_full = _norm(text)
        norm_lines = [_norm(ln) for ln in text.split('\n')]
        for kind, (pat, keywords, supports) in matchers.items():
            if kind in out:
                continue
            first_match = any(pat.match(ln) for ln in norm_lines)
            if not first_match:
                continue
            if not any(s in norm_full for s in supports):
                continue
            out[kind] = i
            break
        # All target statements located — stop scanning. BRSA statements all sit
        # in the first ~25 pages; without this the loop scanned every page (159 on
        # VAKBN), re-opening the PDF with fitz each time (~6 s wasted per report).
        if len(out) == len(matchers):
            break
    return out


def _fitz_page_text(pdf_path: str, page_idx_0: int) -> str:
    """Extract page text with PyMuPDF using word-level coordinates.

    Reconstructs each line by y-bucketing word boxes (and merging split-digit
    fragments). This catches text that fitz's default get_text() ordering splits
    across lines, and — unlike a naive column-flatten — preserves the row
    structure some banks (e.g. Akbank 2026Q1) would otherwise lose. This is the
    single text reader for every audit-statement parser.

    Thin join over `_fitz_page_line_tokens` — that function holds the bucketing,
    and callers that need the geometry (the prose lane, which separates narrative
    from tables by column alignment) read the tokens instead of re-deriving them
    from this string. Output is byte-identical to the pre-split implementation."""
    return '\n'.join(' '.join(t for _, _, t in line)
                     for line in _fitz_page_line_tokens(pdf_path, page_idx_0))


def _fitz_page_line_tokens(
    pdf_path: str, page_idx_0: int,
) -> list[list[tuple[float, float, str]]]:
    """One list per visual line, each holding that line's (x0, x1, text) tokens
    in reading order — the shared body of `_fitz_page_text`, with the coordinates
    kept instead of flattened away.

    Unlike `_fitz_visual_rows` this applies the page rotation matrix, so a
    /Rotate 90 page yields display-space columns rather than scrambled ones."""
    if not _HAS_FITZ:
        return []
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_idx_0]
        # get_text("words") returns (x0, y0, x1, y1, "text", block, line, word) with
        # bboxes in the page's UN-rotated space. On a /Rotate 90/270 page (e.g.
        # GARAN/AKBNK render their landscape equity statement that way) the visual
        # columns then share a y and the rows share an x, so y-bucketing scrambles
        # the table into garbage. Map each bbox through the page's rotation_matrix
        # into DISPLAY space first; rotation_matrix is identity when rotation==0, so
        # the (vast majority of) upright pages are byte-for-byte unchanged.
        words = page.get_text("words")
        rot_m = page.rotation_matrix if page.rotation else None
        doc.close()
        if not words:
            return []
        rows: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
        for w in words:
            x0, y0, x1, _y1, text = w[0], w[1], w[2], w[3], w[4]
            if rot_m is not None:
                r = (fitz.Rect(x0, y0, x1, w[3]) * rot_m)
                r.normalize()
                x0, y0, x1 = r.x0, r.y0, r.x1
            y_key = int(round(y0))
            rows[y_key].append((x0, x1, text))
        # Merge close y-buckets (within 3px) into single rows
        sorted_keys = sorted(rows.keys())
        merged: dict[int, list[tuple[float, float, str]]] = {}
        last_key = None
        for k in sorted_keys:
            if last_key is not None and k - last_key <= 3:
                merged[last_key].extend(rows[k])
            else:
                merged[k] = list(rows[k])
                last_key = k
        out_lines: list[list[tuple[float, float, str]]] = []
        for y in sorted(merged.keys()):
            ws = sorted(merged[y], key=lambda t: t[0])
            # Merge digit-fragment runs: a single digit token immediately before
            # a digit-rich token within ~4px → join them (same fix as the
            # pdfplumber path uses).
            tokens: list[tuple[float, float, str]] = []
            i = 0
            while i < len(ws):
                x0, x1, text = ws[i]
                j = i + 1
                while j < len(ws):
                    nx0, nx1, ntext = ws[j]
                    gap = nx0 - x1
                    if (
                        re.match(r'^\d{1,2}$', text)
                        and re.match(r'^[\d.,]', ntext)
                        and gap < 4
                    ):
                        text = text + ntext
                        x1 = nx1
                        j += 1
                        continue
                    if (
                        text and re.match(r'^\d', text[-1])
                        and re.match(r'^[.,]\d', ntext)
                        and gap < 4
                    ):
                        text = text + ntext
                        x1 = nx1
                        j += 1
                        continue
                    break
                tokens.append((x0, x1, text))
                i = j
            out_lines.append(tokens)
        return out_lines
    except Exception:
        return []


def _fitz_visual_rows(pdf_path: str, page_idx_0: int) -> list[list[tuple[float, float, str]]]:
    """Word tokens grouped into visual rows by y, each row sorted by x with digit
    fragments merged — the SAME bucketing as `_fitz_page_text` but KEEPING each
    token's (x0, x1, text) coordinates instead of flattening to a string.

    The OCI coordinate reconstruction ([[oci]]) uses this to reassemble rows whose
    hierarchy marker, label and values land on different physical lines (wrapped
    labels, or a value sitting on its own line above the marker)."""
    if not _HAS_FITZ:
        return []
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_idx_0]
        words = page.get_text("words")  # (x0,y0,x1,y1, word, block, line, word_no)
        doc.close()
    except Exception:
        return []
    if not words:
        return []
    rows: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
    for w in words:
        rows[int(round(w[1]))].append((w[0], w[2], w[4]))
    sorted_keys = sorted(rows.keys())
    merged: dict[int, list[tuple[float, float, str]]] = {}
    last_key = None
    for k in sorted_keys:
        if last_key is not None and k - last_key <= 3:
            merged[last_key].extend(rows[k])
        else:
            merged[k] = list(rows[k])
            last_key = k
    out: list[list[tuple[float, float, str]]] = []
    for y in sorted(merged.keys()):
        ws = sorted(merged[y], key=lambda t: t[0])
        tokens: list[tuple[float, float, str]] = []
        i = 0
        while i < len(ws):
            x0, x1, text = ws[i]
            j = i + 1
            while j < len(ws):
                nx0, nx1, ntext = ws[j]
                gap = nx0 - x1
                if re.match(r'^\d{1,2}$', text) and re.match(r'^[\d.,]', ntext) and gap < 4:
                    text, x1 = text + ntext, nx1
                    j += 1
                    continue
                if text and re.match(r'^\d', text[-1]) and re.match(r'^[.,]\d', ntext) and gap < 4:
                    text, x1 = text + ntext, nx1
                    j += 1
                    continue
                break
            tokens.append((x0, x1, text))
            i = j
        out.append(tokens)
    return out


def _fitz_merge_rows(text: str, n_cols: int) -> str:
    """Some banks (e.g. Akbank 2026Q1) split each row across multiple physical
    lines: label on one line, N values across the next 1–2 lines. Re-join them
    so the standard _parse_rows logic can recognize them as single rows.

    Also fixes fitz's no-space output (e.g. "1.1.1Nakit Değerler …" → "1.1.1 Nakit…").
    """
    # Inject space after hierarchy markers that have no whitespace before the
    # label. The numeric separator may be a COMMA: AKBNK prints off-balance row
    # 1.1 as "1,1Teminat Mektupları" — comma AND glued. Without both allowances
    # the line never reaches _parse_rows, the row is dropped, and the hierarchy
    # sum for "I. GARANTİ ve KEFALETLER" comes up ₺483.5bn short. (_parse_rows
    # has its own comma normaliser, but only for markers that already stand
    # apart from their label, so it never sees this line.) The marker is
    # normalised to dots on the way out.
    _INSERT_SPACE = re.compile(
        r'^([IVX]+\.|[A-Z]\.|\d+(?:[.,]\d+)*\.?)([A-Za-zÇĞİÖŞÜçğıöşü(])')
    # A line that is JUST a hierarchy marker, nothing else (VAKIFK 2024+ wraps a
    # long label around the marker so it lands on its own physical line).
    _BARE_HIER = re.compile(r'^(?:[IVX]+\.|[A-Z]\.|\d+(?:\.\d+)*\.?)$')
    lines: list[str] = []
    for raw in text.split('\n'):
        s = raw.strip()
        if not s:
            continue
        m = _INSERT_SPACE.match(s)
        if m:
            s = m.group(1).replace(',', '.') + ' ' + s[m.end(1):]
        lines.append(s)
    out: list[str] = []
    i = 0
    _HAS_ALPHA = re.compile(r'[A-Za-zÇĞİÖŞÜçğıöşü]')
    while i < len(lines):
        ln = lines[i]
        # Already has hierarchy + enough numbers → keep as-is
        nums_in_line = _count_values(ln)
        # Hierarchy marker isolated on its own line — the label wraps around it:
        #   line i-1: 'İTFA EDİLMİŞ MALİYETİ İLE ÖLÇÜLEN FİNANSAL'  (label, part 1)
        #   line i  : 'II.'                                          (bare marker)
        #   line i+1: 'VARLIKLAR (Net) <6 numbers>'                 (label part 2 + values)
        # Reattach the marker to the preceding label fragment (already emitted)
        # and pull following lines until the value columns accumulate, so
        # _parse_rows sees one '<marker> <full label> <numbers>' row.
        if _BARE_HIER.match(ln):
            pre = ''
            if (out and not HIERARCHY_PAT.match(out[-1]) and not _BARE_HIER.match(out[-1])
                    and _count_values(out[-1]) < n_cols
                    and _HAS_ALPHA.search(out[-1])):
                pre = out.pop()
            accumulated = ln + ((' ' + pre) if pre else '')
            j = i + 1
            while (j < len(lines) and _count_values(accumulated) < n_cols
                   and j - i <= 3):
                if _BARE_HIER.match(lines[j]):
                    break
                m_h = HIERARCHY_PAT.match(lines[j])
                if m_h and _HAS_ALPHA.search(m_h.group('rest')[:30]):
                    break
                accumulated += ' ' + lines[j]
                j += 1
            out.append(accumulated)
            i = j
            continue
        if HIERARCHY_PAT.match(ln) and nums_in_line >= n_cols:
            out.append(ln)
            i += 1
            continue
        # Line is hierarchy + label only → look ahead for value lines
        if HIERARCHY_PAT.match(ln) and nums_in_line < n_cols:
            accumulated = ln
            j = i + 1
            while j < len(lines) and _count_values(accumulated) < n_cols and j - i <= 3:
                # Stop if we hit a NEW item header — hierarchy + alphabetic label.
                # Plain value lines (e.g. "228.693.745 272.963.728 501.657.473")
                # also match HIERARCHY_PAT (the first number looks like a hierarchy
                # marker), so we additionally check for alphabetic text in the rest.
                m_h = HIERARCHY_PAT.match(lines[j])
                if m_h and re.search(r'[A-Za-zÇĞİÖŞÜçğıöşü]', m_h.group('rest')[:30]):
                    break
                accumulated += ' ' + lines[j]
                j += 1
            out.append(accumulated)
            i = j
            continue
        out.append(ln)
        i += 1
    return '\n'.join(out)


def _parse_page(pdf_path: str, page_idx_1: int, n_cols: int) -> list[tuple[str, list[float | None]]]:
    """Parse one statement page from fitz coordinate-reconstructed text.

    `_fitz_page_text` rebuilds each row from word x/y boxes — mapping /Rotate 90
    pages through the rotation matrix and merging split-digit fragments. It is a
    superset of the old pdfplumber layout-repair and does not suffer pdfplumber's
    column-flatten, which on some banks (e.g. Akbank 2026Q1) silently truncated
    item labels to 'I-a' instead of '1.1.1 Nakit Değerler ve Merkez Bankası (I-a)'.

    `_fitz_merge_rows` then rejoins a single logical row a bank wraps across two
    physical lines (ZIRAAT / VAKBN public-sector reports: `II. İTFA EDİLMİŞ
    MALİYETİ İLE ÖLÇÜLEN` on one line, `FİNANSAL VARLIKLAR (Net) <6 numbers>` on
    the next). It is text-source agnostic and idempotent on already-merged rows.
    """
    text = _fitz_page_text(pdf_path, page_idx_1 - 1)
    return _parse_rows(_fitz_merge_rows(text, n_cols), n_cols)


def _parse_bs_with_checks(text: str) -> list[tuple[str, list[float | None]]]:
    """Repair displaced BS labels/cells only when the whole statement reconciles."""
    from .validator import validate_statement, _statement_total
    original = _parse_rows(_fitz_merge_rows(text, 6), 6)
    replaced: set[str] = set()
    renamed: dict[str, str] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i in range(1, len(lines)):
        match = HIERARCHY_PAT.match(lines[i])
        if not match:
            continue
        # EXIM wraps the hierarchy below its label and all three period triplets.
        if (_count_values(lines[i]) == 0 and _count_values(lines[i - 1]) >= 6
                and not HIERARCHY_PAT.match(lines[i - 1])
                and not (i >= 2 and HIERARCHY_PAT.match(lines[i - 2])
                         and _count_values(lines[i - 2]) < 6)):
            previous = lines[i - 1]
            values = _value_matches(previous)
            start = values[0].start() if values else len(previous)
            label, cells = previous[:start], previous[start:]
            replaced.add(match.group('h').rstrip('.'))
            lines[i] = f"{match.group('h')} {label} {match.group('rest')} {cells}"
            lines[i - 1] = ""
        # EMLAK's wrapped label has a stray three-dash fragment above a complete
        # six-cell row. Never select a later triplet on a normal multiperiod row.
        elif (i + 1 < len(lines) and _count_values(lines[i]) == 3
              and re.search(r"(?:\s[-–—]){3}$", lines[i])
              and not HIERARCHY_PAT.match(lines[i + 1])):
            cleaned = _SECTION_REF_RX.sub("", lines[i + 1])
            values = [parse_num(m.group()) for m in _value_matches(cleaned)
                      if not _FOOTNOTE_RX.fullmatch(m.group())]
            if len(values) == 6 and _triplets_foot(values, 6):
                replaced.add(match.group('h').rstrip('.'))
                lines[i] = re.sub(r"(?:\s[-–—]){3}$", "", lines[i]) + " " + lines[i + 1]
                lines[i + 1] = ""
    candidate = _parse_rows(_fitz_merge_rows("\n".join(lines), 6), 6)
    for i in range(1, len(candidate) - 1):
        label, values = candidate[i]
        h, _, _ = _split_label(label)
        prev = _split_label(candidate[i - 1][0])[0].rstrip('.').split('.')
        nxt = _split_label(candidate[i + 1][0])[0].rstrip('.').split('.')
        parts = h.rstrip('.').split('.')
        if (len(parts) < 2 or len(prev) != len(parts) or len(nxt) != len(parts)
                or prev[:-1] != nxt[:-1] or not all(p.isdigit() for p in prev + nxt + parts)):
            continue
        if int(prev[-1]) + 1 != int(parts[-1]) or int(nxt[-1]) - 1 != int(parts[-1]):
            continue
        expected = '.'.join([*prev[:-1], parts[-1]])
        actual = h.rstrip('.')
        # A single omitted digit in an otherwise uniquely bracketed sibling,
        # e.g. source 1.5.3 between 15.5.2 and 15.5.4. No value is inferred.
        if len(expected) == len(actual) + 1 and any(
                expected[:j] + expected[j + 1:] == actual for j in range(len(expected))):
            renamed[actual] = expected
            candidate[i] = (expected + label[len(h):], values)

    # Reattaching a value line must never steal a preceding row's continuation.
    # Preserve every original hierarchy and its values, except the explicit
    # dash-fragment replacement or digit-typo rename identified above.
    remaining = [(_split_label(label)[0].rstrip('.'), values) for label, values in candidate]
    for label, values in original:
        h = _split_label(label)[0].rstrip('.')
        if h in replaced:
            index = next((j for j, item in enumerate(remaining) if item[0] == h), None)
            if index is None:
                return original
            remaining.pop(index)
            continue
        item = (renamed.get(h, h), values)
        if item not in remaining:
            return original
        remaining.remove(item)

    def validate(rows):
        adapted = [
            {"hierarchy": _split_label(label)[0], "item_name": _split_label(label)[1],
             "amount_tl": v[0], "amount_fc": v[1], "amount_total": v[2]}
            for label, v in rows]
        return validate_statement(adapted), _statement_total(adapted)

    (before, _), (after, (total, romans)) = validate(original), validate(candidate)
    if (before.failed > 0 and after.failed == 0 and after.passed > 0
            and total is not None and romans is not None
            and len(candidate) >= len(original)):
        return candidate
    return original


def _parse_with_chain(text: str, n_cols: int, lane: str) -> list[tuple[str, list[float | None]]]:
    """Resolve small parenthesized amounts only when the statement proves them.

    A million-TL cash-flow `(58)` can be a real negative amount or a note
    reference. Keeping it globally would corrupt sparse old P&Ls. Compare the
    complete candidate with the conservative parse and require all relevant
    identities to pass before accepting that reading.
    """
    from .validator import check_cash_flow, check_oci, check_profit_loss
    validators = {"cash_flow": check_cash_flow, "oci": check_oci,
                  "profit_loss": check_profit_loss}
    validate = validators[lane]
    merged = _fitz_merge_rows(text, n_cols)
    original = _parse_rows(merged, n_cols)
    # Some wrapped section rows print their values immediately ABOVE the
    # roman marker. Reattach only a standalone, complete value line to an
    # otherwise value-less roman row; the chain gate below still decides.
    lines = text.splitlines()
    for i in range(1, len(lines)):
        if not re.match(r"^\s*[IVX]+\.\s+\D", lines[i]):
            continue
        if _value_matches(_SECTION_REF_RX.sub("", lines[i])):
            continue
        cells = lines[i - 1].split()
        if len(cells) == n_cols and all(_NUM_RX.fullmatch(c) for c in cells):
            lines[i] += " " + lines[i - 1].strip()
            lines[i - 1] = ""
    repaired = _fitz_merge_rows("\n".join(lines), n_cols)
    candidate = _parse_rows(repaired, n_cols, keep_small_negatives=True)
    if lane == "profit_loss":
        # TOMK prints XVII twice (pre-tax, then tax) and XXII twice (the
        # discontinued equivalents). Canonicalize the duplicated marker only
        # when its exact tax role and the missing successor identify the typo.
        # A genuinely compressed template has no duplicate and is unchanged.
        hierarchies = [_split_label(label)[0].rstrip(".") for label, _ in candidate]
        corrected = []
        for label, values in candidate:
            hierarchy, name, _ = _split_label(label)
            h = hierarchy.rstrip(".")
            successor = {"XVII": "XVIII", "XXII": "XXIII"}.get(h)
            tax_label = "VERGIKARSILIGI" in _norm(name)
            if (successor and tax_label and hierarchies.count(h) == 2
                    and successor not in hierarchies):
                label = re.sub(r"^\s*" + h + r"\.?", successor + ".", label, count=1)
            corrected.append((label, values))
        candidate = corrected
    if candidate == original:
        return original

    def result(parsed):
        adapted = []
        for label, values in parsed:
            hierarchy, name, _ = _split_label(label)
            adapted.append({"hierarchy": hierarchy, "item_name": name,
                            "amount": values[0]})
        return validate(adapted)

    before, after = result(original), result(candidate)
    if (after.failed == 0 and after.passed > 0
            and (before.failed > 0 or after.passed > before.passed)):
        return candidate
    return original


def _detect_pl_ncols(pdf_path: str, page_idx_1: int) -> int:
    """Modal value-column count on a P&L page.

    BRSA income statements come 2-column (current / prior, cumulative only) or
    4-column for interim reports (current / prior × cumulative / 3-month, in the
    BRSA order: cur-cumulative, cur-quarter, prior-cumulative, prior-quarter).
    We take the modal column count across data rows — robust to footnote numbers
    that inflate individual rows — so the caller can map cumulative-current to
    col 0 and cumulative-prior to col n//2, instead of blindly taking the last
    two (which grabs the prior period on a 4-column page). 2-column pages return
    2, so the mapping is identical to the old behaviour and can't regress them.

    A P&L is NEVER more than 4 value columns. We read the coordinate-reconstructed
    fitz text, which (unlike pdfplumber's letter-spaced output on some banks, e.g.
    ISCTR 2024Q4 unconsolidated) never shatters a value into several number-tokens
    ('38,9 06,5 46' → 3) and so can't inflate the count above 4.
    """
    from collections import Counter

    def _mode_from(text: str) -> int | None:
        counts = []
        for line in _fitz_merge_rows(text, 2).splitlines():
            s = line.strip()
            if not (HIERARCHY_PAT.match(s) or TOTAL_PAT.search(s)):
                continue
            n = len(re.findall(NUM_PAT, s))
            if n >= 2:
                counts.append(n)
        if not counts:
            return None
        mode = Counter(counts).most_common(1)[0][0]
        return mode if mode % 2 == 0 else mode - 1  # an odd count = a footnote number

    # Single-column P&L (no prior-period column): some banks print only the
    # current period — e.g. Dünya Katılım's Q1/Q4 reports. `_mode_from` can't see
    # this because NUM_PAT counts the hierarchy marker ("1.1") as a number, so
    # every single-value row looks like it has 2. Use the marker/footnote-aware
    # `_count_values` on the clean (never-shattered) fitz text: a ≥70% single-value
    # majority over ≥8 data rows means ONE value column → return 1, so _parse_rows
    # keeps those rows (n_cols=2 skips every 1-number row → only ~2 survive).
    # A genuine 2-column report prints "-" for an empty prior, which counts as a
    # value, so its rows carry 2 — this can't misfire onto them.
    if _HAS_FITZ:
        cvs = [
            _count_values(s)
            for s in (
                ln.strip()
                for ln in _fitz_merge_rows(
                    _fitz_page_text(pdf_path, page_idx_1 - 1), 2
                ).splitlines()
            )
            if HIERARCHY_PAT.match(s) or TOTAL_PAT.search(s)
        ]
        cvs = [c for c in cvs if c >= 1]
        if len(cvs) >= 8 and sum(1 for c in cvs if c == 1) >= 0.7 * len(cvs):
            return 1

    n = _mode_from(_fitz_page_text(pdf_path, page_idx_1 - 1))
    if n is None:
        return 2
    return max(2, min(4, n))


def _locate_oci_page(pdf_path: str, pl_page_idx_1: int | None) -> int | None:
    """Find the OCI (Other Comprehensive Income) statement page.

    The OCI always follows the P&L page in BRSA reports. Searches the next
    1-6 pages after P&L for the OCI anchor keywords, then confirms the page
    has at least two numeric data rows (not just a section-title page).

    BRSA titles the income statement "KÂR VEYA ZARAR VE DİĞER KAPSAMLI GELİR
    TABLOSU", so the OCI keyword also appears on the P&L page(s). Banks that
    print the P&L twice — cumulative period-to-date AND quarter-only columns,
    e.g. Yapı Kredi interim reports — leave a second P&L page sitting between
    the located P&L and the real OCI. Such a page carries the OCI keyword and
    plenty of roman rows, so it would be wrongly returned. Skip any candidate
    that also carries P&L income anchors (interest / profit-share income); the
    genuine OCI page never lists those.

    Wide-interleaved-table banks (GARAN/AKBNK) present a combined "…Profit or Loss
    AND Other Comprehensive Income" page on a /Rotate-90 landscape page; the
    rotation-aware _fitz_page_text reads its anchor cleanly (it used to scatter
    because fitz returns un-rotated word bboxes), so fitz alone locates every bank.
    """
    if pl_page_idx_1 is None:
        return None
    _OCI_NORMS = ("KAPSAMLIGELIR", "KAPSAMLIKAZAN", "COMPREHENSIVEINCOME", "KAPSAMLIGEL")
    _PL_NORMS = ("INTERESTINCOME", "INTERSTINCOME", "FAIZGELIRLERI",
                 "PROFITSHAREINCOME", "KARPAYIGELIRLERI", "NETINTERESTINCOME")

    # The equity-change statement carries the OCI keyword in a COLUMN header but
    # is not the OCI statement — exclude it (EXIM's equity page would otherwise win
    # over the real OCI page, whose rows aren't roman-prefixed; see below).
    _EQ_NORMS = ("OZKAYNAKDEGISIM", "OZKAYNAKLARDEGISIM", "CHANGESINEQUITY", "CHANGESINSHAREHOLDERS",
                 "BALANCESATBEGINNING", "BALANCESATENDOF")

    def _is_oci_page(text: str) -> bool:
        # DUNYAK's separate prior P&L prints 'KÂR PAYI GELİRLERİ'; fold that
        # circumflex locally so its income anchor still excludes the P&L page.
        norm = _norm(text.replace("Â", "A").replace("â", "a"))
        if not any(kw in norm for kw in _OCI_NORMS):
            return False
        # A P&L (or its quarter-only twin) carries an income anchor — not OCI.
        if any(kw in norm for kw in _PL_NORMS):
            return False
        if any(kw in norm for kw in _EQ_NORMS):
            return False
        # Require at least 2 labelled numeric data rows. NOT roman-only: EXIM's
        # English OCI page numbers items "1.5.2 …" or leaves them unprefixed
        # ("Revaluation Surplus on Tangible Assets …"), so a roman-only count was 0
        # and the page was skipped in favour of the (roman-prefixed) equity page.
        data_rows = sum(
            1 for ln in text.split("\n")
            if re.search(r'\d{3,}', ln) and re.search(r'[A-Za-zÇĞİÖŞÜçğıöşü]{3,}', ln)
        )
        # Million-TL filers can have an entire valid OCI spine below 100 (HAYATK:
        # I=90, II=-37, III=53). Requiring three digit tokens skipped the actual
        # statement and selected the following wide equity matrix instead.
        small_oci_rows = sum(
            1 for ln in text.splitlines()
            if re.match(r"^\s*(?:I{1,3}\.?\s+|2(?:\.\d+){1,2}\.?\s+)", ln)
            and _value_matches(ln)
        )
        return data_rows >= 2 or small_oci_rows >= 2

    lo, hi = pl_page_idx_1 + 1, min(pl_page_idx_1 + 7, (_fitz_page_count(pdf_path) or 0) + 1)
    # fitz reads the OCI anchor for every bank — including the wide-interleaved
    # GARAN/AKBNK "…Profit or Loss AND Other Comprehensive Income" page, now that
    # _fitz_page_text applies the page rotation (those are /Rotate-90 landscape
    # pages; un-rotated word bboxes used to scatter the anchor).
    for i in range(lo, hi):
        if _is_oci_page(_fitz_page_text(pdf_path, i - 1)):
            return i
    return None


def _locate_cash_flow_page(pdf_path: str, start_page_idx_1: int | None) -> int | None:
    """Find the cash flow statement page.

    Searches pages start+1 … start+8 for the cash flow anchor keywords, then
    confirms the page has at least 2 numeric data rows. The cash flow follows
    the two equity-change pages (which follow OCI, which follows P&L).
    """
    if start_page_idx_1 is None:
        return None
    _CF_NORMS = ("NAKITAKIS", "STATEMENTOFCASHFLOWS", "CASHFLOWSTATEMENT",
                 "STATEMENTOFCASHFLOW")
    # Equity-change pages must NOT be confused with cash flow pages.
    _EQ_NORMS = ("OZKAYNAKDEGISIM", "CHANGESINSHAREHOLDERS", "CHANGESINEQUITY")
    # Content fallback: some reports (EXIM, English) carry the CF data rows on a
    # page whose text omits the "Statement of Cash Flows" title (it sits in a
    # running header that pdfplumber drops). The CF statement is uniquely the page
    # that pairs an operating-activities section with an investing-activities one.
    _cf_op = re.compile(r"operating\s+(?:activit|profit)|i[şs]letme\s+faaliyet|"
                        r"bankac[ıi]l[ıi]k\s+faaliyet|esas\s+faaliyet", re.IGNORECASE)
    _cf_inv = re.compile(r"investing\s+activit|yat[ıi]r[ıi]m\s+faaliyet", re.IGNORECASE)
    for i in range(start_page_idx_1 + 1, min(start_page_idx_1 + 9, (_fitz_page_count(pdf_path) or 0) + 1)):
        text = _fitz_page_text(pdf_path, i - 1)
        norm = _norm(text)
        if not (any(kw in norm for kw in _CF_NORMS)
                or (_cf_op.search(text) and _cf_inv.search(text))):
            continue
        # Skip pages dominated by an equity-change anchor — these are mis-detections
        # caused by banks that combine equity and CF content on the same page or by
        # the equity extractor missing its pages and leaving us pointing at them.
        if any(kw in norm for kw in _EQ_NORMS):
            continue
        # Require at least 2 numeric data rows (hierarchy-preceded lines)
        data_rows = sum(
            1 for ln in text.split("\n")
            if re.match(r'^\s*(?:[IVX]+\.|[A-Z]\.|[0-9]+[.\s])', ln)
            and re.search(r'\d{3,}', ln)
        )
        if data_rows >= 2:
            return i
    return None


def extract(pdf_path: str | Path, only: set[str] | None = None) -> BankReport:
    """Parse one BRSA-format audit report. Returns a BankReport with rows populated.

    `only` restricts work to a subset of statement types — used by the targeted
    single-statement re-extraction path so a one-lane fix doesn't re-run all 14
    extractors per PDF. Valid names: bs_assets, bs_liabilities, off_balance,
    profit_loss, oci, equity_change, cash_flow, credit_quality, bank_profile,
    audit_opinion, free_provision, loans_by_sector, npl_movement, capital, liquidity. The page-location chain a
    requested statement depends on is always run (e.g. only={'cash_flow'} still
    locates P&L/OCI/equity to find the cash-flow page). `only=None` is unchanged —
    a full extract, identical to before."""
    def _want(name: str) -> bool:
        return only is None or name in only

    pdf_path = str(pdf_path)
    rep = BankReport(pdf_path=pdf_path)
    # Every lane below reads via pdf_path with fitz — no PDF is materialised
    # through pdfminer, so none risks the page-tree hang on poison PDFs. The
    # "deep-scan" extractors each sweep most of the PDF, so skipping them when
    # `only` excludes them is the bulk of the single-statement speed-up.
    if _want('credit_quality'):
        try:
            from .credit_quality import extract_from_pdf as _extract_cq
            rep.credit_quality = _extract_cq(pdf_path=pdf_path).rows
        except Exception:
            rep.credit_quality = []
    # Bank profile (branches + personnel) from the qualitative section.
    if _want('bank_profile'):
        try:
            from .bank_profile import extract_profile_from_pdf as _extract_bp
            rep.bank_profile = _extract_bp(pdf_path)
        except Exception:
            rep.bank_profile = None
    # Independent auditor's opinion (clean / qualified / …) from the front matter.
    if _want('audit_opinion'):
        try:
            from .audit_opinion import extract_opinion_from_pdf as _extract_op
            _m = re.search(r"_(\d{4}Q\d)_", Path(pdf_path).name)
            rep.audit_opinion = _extract_op(pdf_path, period=_m.group(1) if _m else "")
        except Exception:
            rep.audit_opinion = None
    # Free provision (serbest karşılık) stock from the "Other provisions" note.
    if _want('free_provision'):
        try:
            from .free_provision import extract_free_provision_from_pdf as _extract_fp
            rep.free_provision = _extract_fp(pdf_path)
        except Exception:
            rep.free_provision = None
    # Narrative prose, section-scoped — everything the tables leave behind.
    if _want('prose'):
        try:
            from .prose import extract_prose as _extract_prose
            _mp = re.search(r"_(\d{4}Q\d)_", Path(pdf_path).name)
            rep.prose = _extract_prose(pdf_path, period=_mp.group(1) if _mp else "")
        except Exception:
            rep.prose = None
    # Loans-by-sector (Stage 2 / Stage 3 / ECL per sector).
    if _want('loans_by_sector'):
        try:
            from .loans_by_sector import extract_from_pdf as _extract_lbs
            rep.loans_by_sector = _extract_lbs(pdf_path).rows
        except Exception:
            rep.loans_by_sector = []
    # NPL gross-amount roll-forward.
    if _want('npl_movement'):
        try:
            from .npl_movement import extract_from_pdf as _extract_nplm
            rep.npl_movement = _extract_nplm(pdf_path).rows
        except Exception:
            rep.npl_movement = []
    # Capital adequacy (§4.1) and liquidity/leverage (§4.6/4.7).
    if _want('capital'):
        try:
            from .capital_adequacy import extract_from_pdf as _extract_cap
            rep.capital = _extract_cap(pdf_path)
        except Exception:
            rep.capital = None
    if _want('liquidity'):
        try:
            from .liquidity import extract_from_pdf as _extract_liq
            rep.liquidity = _extract_liq(pdf_path)
        except Exception:
            rep.liquidity = None
    # §4 market-risk: FX net open position + interest-rate repricing gap.
    if _want('fx_position'):
        try:
            from .fx_position import extract_from_pdf as _extract_fx
            rep.fx_position = _extract_fx(pdf_path=pdf_path)
        except Exception:
            rep.fx_position = None
    if _want('repricing'):
        try:
            from .repricing import extract_from_pdf as _extract_rp
            rep.repricing = _extract_rp(pdf_path=pdf_path)
        except Exception:
            rep.repricing = None
    loc = _locate_pages(pdf_path)
    if 'bs_assets' in loc and _want('bs_assets'):
        rows = _parse_bs_with_checks(_fitz_page_text(pdf_path, loc['bs_assets'] - 1))
        for order, (label, vals) in enumerate(rows, 1):
            h, name, fn = _split_label(label)
            rep.bs_assets.append(StatementRow(
                order=order, hierarchy=h, name=name, footnote=fn,
                cur_tl=vals[0], cur_fc=vals[1], cur_total=vals[2],
                pri_tl=vals[3], pri_fc=vals[4], pri_total=vals[5],
            ))
    if 'bs_liab' in loc and _want('bs_liabilities'):
        rows = _parse_bs_with_checks(_fitz_page_text(pdf_path, loc['bs_liab'] - 1))
        for order, (label, vals) in enumerate(rows, 1):
            h, name, fn = _split_label(label)
            rep.bs_liabilities.append(StatementRow(
                order=order, hierarchy=h, name=name, footnote=fn,
                cur_tl=vals[0], cur_fc=vals[1], cur_total=vals[2],
                pri_tl=vals[3], pri_fc=vals[4], pri_total=vals[5],
            ))
    if 'off_bs' in loc and _want('off_balance'):
        _off_order = 0
        for label, vals in _parse_page(pdf_path, loc['off_bs'], 6):
            h, name, fn = _split_label(label)
            cur_tot = vals[2]
            # Drop section-level rows (depth-1: single roman or letter) that
            # have a suspiciously small non-zero total — these are table-header
            # lines whose column positions happen to align with date fragments
            # (e.g. "31.03.2022 31.12.2021" → 31.03 / 202 / 2 in the TL/FC/
            # Total slots) and section-reference numbers ("III-a-2,3" → 105/4/
            # 305).  All legitimate depth-1 section totals for any Turkish bank
            # are in at least the millions of TRY.
            #
            # That floor is denominated in the FILING's unit, and 2026Q2 moved
            # the sector from Bin TL to Milyon TL — so ₺115mn now prints as
            # "115" and KLNMA's "IV. EMANET KIYMETLER 115 - 115 126 - 126" fell
            # through it, taking the B = IV+V+VI identity down with it. Rather
            # than rescale the floor, let a row that FOOTS escape it: the
            # spurious rows this guard exists for never do — a date fragment
            # reads 31.03 / 202 / 2 and a section ref 105 / 4 / 305, and
            # neither satisfies tl + fc = total in both periods.
            if (h and re.fullmatch(r'[IVX]+\.|[A-Z]\.', h)
                    and cur_tot is not None and 0 < abs(cur_tot) < 1_000
                    and not _triplets_foot(vals, 6)):
                continue
            _off_order += 1
            rep.off_balance.append(StatementRow(
                order=_off_order, hierarchy=h, name=name, footnote=fn,
                cur_tl=vals[0], cur_fc=vals[1], cur_total=cur_tot,
                pri_tl=vals[3], pri_fc=vals[4], pri_total=vals[5],
            ))
    if 'pl' in loc:
        # Interim income statements can carry 4 columns (cumulative + 3-month
        # for current/prior). Detect the structure and take the cumulative
        # current (col 0) and cumulative prior (col n//2), not the last two.
        if _want('profit_loss'):
            pl_n = _detect_pl_ncols(pdf_path, loc['pl'])
            pl_text = _fitz_page_text(pdf_path, loc['pl'] - 1)
            for order, (label, vals) in enumerate(_parse_with_chain(pl_text, pl_n, 'profit_loss'), 1):
                h, name, fn = _split_label(label)
                rep.profit_loss.append(StatementRow(
                    order=order, hierarchy=h, name=name, footnote=fn,
                    cur_amount=vals[0],
                    # Single-column reports (pl_n == 1) carry no prior period.
                    pri_amount=(vals[pl_n // 2] if pl_n >= 2 else None),
                ))
        # OCI always follows the P&L page (same single-value-column structure).
        # Its page is ALSO the after-anchor for equity + cash flow, so locate it
        # whenever any of OCI / equity_change / cash_flow is wanted; store OCI
        # rows only when OCI itself is wanted.
        oci_page = (_locate_oci_page(pdf_path, loc['pl'])
                    if (_want('oci') or _want('equity_change') or _want('cash_flow'))
                    else None)
        if oci_page and _want('oci'):
            # Validation-guided OCI parse (picks the chain that closes — fixes the
            # n_cols mis-detection that yielded 0/garbage rows). Isolated so an
            # OCI failure can't sink P&L/equity/CF.
            try:
                from .oci import extract_oci
                rep.other_comprehensive_income = extract_oci(pdf_path, oci_page).rows
            except Exception:
                rep.other_comprehensive_income = []
        # Equity-change pages follow OCI (or P&L when OCI is absent). Equity rows
        # are also the cash-flow page anchor (_eq_last), so run the extractor when
        # equity OR cash_flow is wanted; store on rep only when equity is wanted.
        eq_report = None
        if _want('equity_change') or _want('cash_flow'):
            try:
                from .equity_change import extract_from_pdf as _extract_eq
                eq_report = _extract_eq(pdf_path, oci_page or loc.get('pl'))
            except Exception:
                eq_report = None
            if _want('equity_change'):
                rep.equity_change = eq_report
        # Cash flow follows the equity-change pages. Use the OCI anchor as the
        # search window start when equity extraction failed to locate pages.
        if _want('cash_flow'):
            _eq_last = None
            if eq_report and getattr(eq_report, 'rows', []):
                _eq_last = max((r.source_page for r in eq_report.rows), default=None)
            cf_start = _eq_last or oci_page or loc.get('pl')
            cf_page = _locate_cash_flow_page(pdf_path, cf_start)
            if cf_page:
                # The cash flow statement ALWAYS carries exactly two value columns
                # (current + prior, cumulative) — for annual AND interim reports
                # alike, since CF is only ever reported year-to-date.  We must NOT
                # use _detect_pl_ncols here: it is tuned for the P&L (4 columns on
                # interim) and misreads the CF page's parenthesised date headers
                # "(31/12/2024) (31/12/2023)" as a 4-column layout, which then makes
                # row-parsing reject every 2-value data row (AKBNK/ING annual → 0
                # rows).  Pin to 2 so both columns are picked directly.
                cf_text = _fitz_page_text(pdf_path, cf_page - 1) if _HAS_FITZ else ''
                # Column count is normally 2 (current + prior, year-to-date). But a
                # bank's FIRST report after establishment / status-change carries NO
                # prior comparative (DUNYAK 2024, HAYATK 2023 — "bir önceki dönem ile
                # karşılaştırmalı sunulmamıştır"), so the CF is a SINGLE current-period
                # column and the 2-column parse rejects every 1-value row (41 rows →
                # 2 on DUNYAK). Detect from the page: parse as 1 column only when the
                # hierarchy rows carry ONE value far more often than two — conservative
                # so a genuine 2-column page (every row has current+prior) stays at 2.
                cf_n = 2
                if cf_text:
                    _one = _two = 0
                    for _ln in cf_text.split('\n'):
                        if not HIERARCHY_PAT.match(_ln.strip()):
                            continue
                        _nv = len(_value_matches(_ln))
                        if _nv == 1:
                            _one += 1
                        elif _nv >= 2:
                            _two += 1
                    if _one >= 5 and _one >= 2 * _two:
                        cf_n = 1
                cf_parsed = _parse_with_chain(cf_text, cf_n, 'cash_flow') if cf_text else []
                for order, (label, vals) in enumerate(cf_parsed, 1):
                    h, name, fn = _split_label(label)
                    rep.cash_flow.append(StatementRow(
                        order=order, hierarchy=h, name=name, footnote=fn,
                        cur_amount=vals[0], pri_amount=vals[1] if len(vals) > 1 else None,
                    ))
    return rep


def summarize(rep: BankReport) -> str:
    return (
        f'{Path(rep.pdf_path).name}\n'
        f'  bs_assets:      {len(rep.bs_assets)} rows\n'
        f'  bs_liabilities: {len(rep.bs_liabilities)} rows\n'
        f'  off_balance:    {len(rep.off_balance)} rows\n'
        f'  profit_loss:    {len(rep.profit_loss)} rows'
    )


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    path = sys.argv[1] if len(sys.argv) > 1 else 'data/audit_reports/garanti/31_December_2024_Unconsolidated_Financial_Report.pdf'
    rep = extract(path)
    print(summarize(rep))
    print('\nBS Assets sample:')
    for r in rep.bs_assets[:5]:
        print(f'  {r.hierarchy:8} {r.name[:50]:50} fn={r.footnote}  total={r.cur_total}')
    print('\nP&L sample:')
    for r in rep.profit_loss[:5]:
        print(f'  {r.hierarchy:8} {r.name[:50]:50} fn={r.footnote}  cur={r.cur_amount}')
