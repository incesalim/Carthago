"""Non-performing loans (NPL) gross-amount roll-forward extractor.

Every BRSA audit report includes a movement table for non-performing loans
broken into the three regulatory severity groups (III / IV / V):

  Group III — Substandard / Limited Collectability — loans 90+ days past due
  Group IV  — Doubtful Loans — loans 180+ days past due
  Group V   — Uncollectible / Loss — loans 1+ year past due

The table is typically labeled in Turkish as "Toplam donuk alacak
hareketlerine ilişkin bilgiler" or in English as "Information on the
movement of non-performing loans" / "Movements in non-performing loans
groups".

For each group, the rollforward gives:
  opening_balance      Prior period end balance
  additions            Loans newly entering NPL during the period
  transfers_in         Net loans moving INTO this group from another NPL group
  transfers_out        Net loans moving OUT of this group to another NPL group
  collections          Recoveries during the period
  write_offs           Loans written off the balance sheet
  sold                 NPL portfolio sales
  fx_diff              FX revaluation (GARAN-style; many banks omit)
  closing_balance      End-of-period gross NPL balance
  provision            Cumulative loss provision against the group
  net_balance          closing_balance − provision (balance-sheet carrying amount)

`additions − (collections + write_offs + sold)` ≈ net NPL inflow, which is
the single most-watched metric in this disclosure: it tells you how
fast new credit problems are emerging versus how fast the bank is
clearing them.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .extractor import _HAS_FITZ, _fitz_page_text, _n_pages, parse_num


# ---------------------------------------------------------------------------
# Row-label taxonomy — map each observed label (TR + EN, with variants) to
# a canonical column key. Longest-first matching.
# ---------------------------------------------------------------------------
_ROW_LABELS: list[tuple[str, str]] = [
    # Opening (always the first row). ISCTR variant: "Prior Period Ending
    # Balance". YKBNK variant: bare "Prior Period" (with numeric tail) — added
    # at the end of the list as a last-resort fallback so longer labels win.
    ("önceki dönem sonu bakiyesi", "opening_balance"),
    ("prior period ending balance", "opening_balance"),
    ("prior period end balance", "opening_balance"),
    ("balances at end of prior period", "opening_balance"),
    # EXIM (English convenience translation) opens the roll-forward with
    # "Balance at the Beginning of the Period" — distinct from the closing
    # "Balance at the End of the Period" (below). Without it the opening row
    # was dropped (block started on Additions) → opening_balance NULL.
    ("balance at the beginning of the period", "opening_balance"),
    # ALBRK opens the roll-forward with the *prior* period's closing line; it
    # must out-rank the generic "closing balance" → closing_balance via the
    # longest-prefix sort.
    ("closing balance of prior period", "opening_balance"),
    ("beginning balance", "opening_balance"),
    ("opening balance", "opening_balance"),
    # Closing — must come BEFORE "balance" prefixes for longest-first.
    ("current period ending balance", "closing_balance"),
    ("current period end balance", "closing_balance"),
    # EXIM / BURGAN / AKBNK (English convenience translations) close the
    # roll-forward with "Balance at the End of the Period" — the singular
    # "the period" form was the only balance label missing from this list, so
    # the closing row was dropped fleet-wide for every English report using it
    # (closing_balance NULL while flows captured). Distinct from the EXIM
    # opening "Balance at the Beginning of the Period" (above).
    ("balance at the end of the period", "closing_balance"),
    ("balances at end of period", "closing_balance"),
    ("end of period balance", "closing_balance"),
    ("dönem sonu bakiyesi", "closing_balance"),
    ("closing balance", "closing_balance"),
    ("period end balance", "closing_balance"),
    # Additions
    ("dönem içinde intikal", "additions"),
    ("additions", "additions"),
    # Transfers in
    ("diğer donuk alacak hesaplarından giriş", "transfers_in"),
    ("transfer from other npl categories", "transfers_in"),
    ("transfers from other categories of loans under non-performing", "transfers_in"),
    ("transfers from other categories of non-performing", "transfers_in"),
    ("transfers from other categories", "transfers_in"),
    # EXIM wording ("Transfers from Non-performing Loans Accounts").
    ("transfers from non-performing loans accounts", "transfers_in"),
    ("transfers from non-performing loans", "transfers_in"),
    # Transfers out
    ("diğer donuk alacak hesaplarına çıkış", "transfers_out"),
    ("transfer to other npl categories", "transfers_out"),
    ("transfers to other categories of loans under non-performing", "transfers_out"),
    ("transfers to other categories of non-performing", "transfers_out"),
    ("transfers to other categories", "transfers_out"),
    # EXIM wording ("Transfers to Other Non-Performing Loans [Accounts]" — the
    # trailing "Accounts" wraps to the next line, so match the leading phrase).
    ("transfers to other non-performing loans", "transfers_out"),
    # Collections
    ("dönem içinde tahsilat", "collections"),
    ("collections during the period", "collections"),
    ("collections", "collections"),
    # Write-offs
    ("kayıttan düşülen", "write_offs"),
    ("write down / write-offs", "write_offs"),
    ("write down/write-offs", "write_offs"),
    ("write-offs", "write_offs"),
    ("write offs", "write_offs"),
    # ALBRK folds cure-to-standard and write-off into one outflow row.
    ("transfers to standard loans and write off", "write_offs"),
    # Sold
    ("debt sale", "sold"),
    ("satılan", "sold"),
    ("sold", "sold"),
    # FX revaluation differential. Consolidated reports add a currency-translation
    # flow row to the NPL roll-forward that solo reports omit (the roll-forward
    # then ties exactly — DENIZ cons gIII Kur farkı 416.936 closed the -416.936
    # gap). Banks word it differently: "Kur farkı"/"Kur farkları" (DENIZ/TEB),
    # "Yabancı para çevrim farkları", English "Foreign currency differences".
    ("foreign currency differences", "fx_diff"),
    ("foreign currency difference", "fx_diff"),
    ("exchange rate differences", "fx_diff"),
    ("yabancı para çevrim farkları", "fx_diff"),
    ("kur değişiminin etkisi", "fx_diff"),
    ("kur farkları", "fx_diff"),
    ("kur farkı", "fx_diff"),
    # Provision
    ("provisions (-)", "provision"),
    ("provision (-)", "provision"),
    ("karşılık (-)", "provision"),
    ("provisions", "provision"),
    ("provision", "provision"),
    ("karşılık", "provision"),
    # Net balance
    ("net balance on balance sheet", "net_balance"),
    ("net balance at the balance sheet", "net_balance"),
    # AKBNK (English) wording; EXIM wording ("Net Balance Sheet Amount"). These
    # close the movement block → fire block_done so the FX-only NPL sub-table
    # that follows on the same page can't overwrite the closing/provision.
    ("net balance at balance sheet", "net_balance"),
    ("net balance sheet amount", "net_balance"),
    ("bilançodaki net bakiyesi", "net_balance"),
    # YKBNK-style bare period labels — opening = "Prior Period <nums>",
    # closing = "Current Period <nums>". Listed last so longest-first
    # matching prefers more specific phrases ("prior period end balance",
    # "current period end balance") when they exist.
    ("prior period", "opening_balance"),
    ("current period", "closing_balance"),
]
_ROW_LABELS_SORTED = sorted(_ROW_LABELS, key=lambda kv: -len(kv[0]))
# Reductions to the NPL stock — stored as positive magnitudes regardless of how
# a bank signs them in the PDF.
_OUTFLOW_KEYS = {"transfers_out", "collections", "write_offs", "sold"}


# Heading detector — the page must mention NPL movement / hareket explicitly.
# ISCTR and YKBNK insert "total " before "non-performing", so accept that
# variant. Both English orderings ("movement of total non-performing" and
# "movement of non-performing total") are observed.
_HEADING_RX = re.compile(
    r"(?:Movements?\s+in\s+non[-\s]?performing\s+loans?(?:\s+groups?)?|"
    r"movements?\s+of\s+(?:total\s+)?non[-\s]?performing\s+loans?|"
    r"information\s+on\s+the\s+movement\s+of\s+(?:total\s+)?non[-\s]?performing\s+loans?|"
    # TSKB unconsolidated titles the movement table "Information on TOTAL
    # non-performing loans (net)" — the "total" keeps it off the plain
    # "Information on non-performing loans (net)" sub-category table; GROUPS +
    # the flow-row labels in _extract_from_block screen out any false hit.
    r"information\s+on\s+total\s+non[-\s]?performing\s+loans?|"
    r"(?:toplam\s+)?donuk\s+alacak\s+hareketlerine|"
    r"takipteki\s+kredilerin\s+hareketleri)",
    re.IGNORECASE,
)
# Group-column header (3 columns, Roman III/IV/V or Group/Grup variants).
_GROUPS_RX = re.compile(
    # ODEA labels the III/IV/V NPL groups "III. Aşama / IV. Aşama / V. Aşama"
    # (Stage, not Grup) — same buckets, different word.
    r"(?:III\.\s*(?:Group|Grup|Aşama).{0,80}?IV\.\s*(?:Group|Grup|Aşama).{0,80}?V\.\s*(?:Group|Grup|Aşama)|"
    r"Group\s*III.{0,80}?Group\s*IV.{0,80}?Group\s*V)",
    re.IGNORECASE | re.DOTALL,
)


# Three trailing numbers (the III / IV / V column values per row). Accept
# digits with TR/EN thousand-separators, "-" for nil, and parenthesised
# negatives.
# A nil cell is printed as one OR MORE dashes (BRSA uses "--" as well as "-",
# and en/em variants) — accept a run of them, else a trailing "--" column drops
# the whole row (e.g. FIBA's "transfers out … 565.308 --"), nulling that flow
# column and making the validator skip an otherwise-balancing roll-forward.
# Two numeric forms: grouped (thousands-separated, "639.907") and a bare digit
# run ("3553"). The bare-run form is REQUIRED for the occasional small flow a
# bank prints without a separator — EXIM 2023Q2 transfers_in "- 3553 -" was
# dropped (its group IV roll-forward then short by exactly that 3.553), nulling
# transfers_in for the whole table. Grouped is tried first so "639.907" still
# parses as 639,907 (not a bare 639 followed by ".907").
_NUM_TOKEN = (
    r"(?:\(?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\)?"  # grouped: 1.234 / 1,234.5
    r"|\(?\d+(?:[.,]\d+)?\)?"                        # bare run: 3553 / 12.5
    r"|[-–—]+)"
)
_THREE_NUMS_TAIL = re.compile(
    rf"(?P<n3>{_NUM_TOKEN})\s+(?P<n4>{_NUM_TOKEN})\s+(?P<n5>{_NUM_TOKEN})\s*$"
)

# Date-keyed balance rows. ODEA and ALNTF (and similar) don't label the opening
# / closing rows "Önceki/Dönem Sonu Bakiyesi" — they print the period-end DATE
# itself as the row head, optionally followed by "Bakiyesi"/"Balance":
#   ODEA:  "31 Aralık 2024 Bakiyesi 33.851 31.423 1.134.089"   (opening)
#          "31 Aralık 2025 Bakiyesi 72.116 22.101 1.101.665"   (closing)
#   ALNTF: "31 Aralık 2024 103,885 209,960 144,837"            (opening, no word)
#          "31 Aralık 2025 248,901 26,905 397,047"             (closing, no word)
# There is no opening/closing WORD to disambiguate, so the position decides:
# the date-balance row that comes BEFORE Additions = opening, the one AFTER all
# the flows (just before the provision/net rows) = closing. We only treat a
# bare date-row as a balance when _match_row_label returned None (so a labelled
# "Önceki Dönem Sonu Bakiyesi: 31 Aralık 2023" still wins as opening_balance via
# the taxonomy) and the row carries the III/IV/V numbers.
_TR_MONTHS = (
    r"ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|"
    r"ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik"
)
_EN_MONTHS = (
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december"
)
_DATE_BALANCE_RX = re.compile(
    rf"^\(?(?:\d{{1,2}}\s+(?:{_TR_MONTHS}|{_EN_MONTHS})\s+\d{{4}}|"
    rf"\d{{1,2}}[./]\d{{1,2}}[./]\d{{4}})"
    r"(?:\s+bakiyesi|\s+balance)?\b",
    re.IGNORECASE,
)


def _parse_amount(s: str) -> float | None:
    s = s.strip()
    if not s or all(c in "-–—" for c in s):  # "", "-", "--", "—" … → nil
        return 0.0
    return parse_num(s)


@dataclass
class NplGroupRow:
    """One row of the NPL movement table — i.e. one (bank, period, kind,
    group_code, period_type) tuple. Holds the full rollforward."""
    group_code: str                       # 'III' | 'IV' | 'V'
    period_type: str = "current"           # 'current' | 'prior'
    opening_balance: float | None = None
    additions: float | None = None
    transfers_in: float | None = None
    transfers_out: float | None = None
    collections: float | None = None
    write_offs: float | None = None
    sold: float | None = None
    fx_diff: float | None = None
    closing_balance: float | None = None
    provision: float | None = None
    net_balance: float | None = None
    page: int = 0


@dataclass
class NplMovementReport:
    pdf_path: str = ""
    rows: list[NplGroupRow] = field(default_factory=list)


def _tr_lower(s: str) -> str:
    """Lowercase with Turkish dotted-I fix: Python's str.lower() turns 'İ'
    into 'i' + U+0307 combining dot, which doesn't equal a plain 'i' in
    string comparison. Strip the combining dot so our taxonomy (which uses
    plain ASCII 'i' for clarity) matches Turkish source text."""
    return s.lower().replace("̇", "")


def _match_row_label(text: str) -> str | None:
    """Return the canonical column key if the text starts with a known label."""
    lower = _tr_lower(text).lstrip()
    # Strip a leading hierarchy code (a., 1., i., etc.)
    lower = re.sub(r"^(?:\(?\w{1,3}[\.\)]\s+)+", "", lower)
    for lbl, key in _ROW_LABELS_SORTED:
        if lower.startswith(lbl):
            return key
    return None


# A wrapped TRANSFER label, two observed shapes (both English convenience
# translations) where the long "Transfers from/to Other Categories of
# Non-performing Loans (+/-)" label breaks across lines, stranding its numbers:
#
#   BURGAN:  "Transfers from Other Categories of Non-performing"   (head, no nums)
#            "Loans (+) - 230,763 185,197"                         (Loans + nums)
#
#   AKBNK:   "Transfers from Other Categories of Non-"             (head, no nums)
#            "- 1.771.188 327.354"                                 (bare nums)
#            "Performing Loans (+)"                                (label tail)
#
# Either way the head is a numberless "Transfers from/to … Non[-performing]"
# line; the row's numbers are on the VERY NEXT line (a "Loans …" line or a bare
# 3-number line). We merge head + that number line into one matchable transfer
# row. Anchoring on the "transfers from/to … non" head keeps this from ever
# touching a standalone "Prior Period" label (which a broad numberless-head
# merge wrongly joined onto the restructured-loans sub-table → GARAN/TSKB
# opening corruption). Any leftover label tail ("Performing Loans (+)") matches
# no row label and is harmlessly ignored.
_TRANSFER_WRAP_HEAD_RX = re.compile(
    r"transfers?\s+(?:from|to)\b.*\bnon[-\s]?(?:performing)?\s*$", re.IGNORECASE
)


def _merge_wrapped_labels(lines: list[str]) -> list[str]:
    """Merge a transfer row whose label wrapped above its numbers; narrowly
    scoped to the "Transfers from/to … Non[-performing]" head (see
    _TRANSFER_WRAP_HEAD_RX) so it can't disturb other rows."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        cur_s = cur.strip()
        if (i + 1 < len(lines)
                and not re.search(r"\d", cur_s)
                and _TRANSFER_WRAP_HEAD_RX.search(cur_s)):
            nxt = lines[i + 1].strip()
            # The numbers are on the next line — either a "Loans (…) <nums>"
            # continuation (BURGAN) or a bare 3-number line (AKBNK).
            if _THREE_NUMS_TAIL.search(nxt) and (
                    re.match(r"^loans?\b", nxt, re.IGNORECASE)
                    or _THREE_NUMS_TAIL.match(nxt)):
                out.append(cur_s + " " + nxt)
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def _extract_from_block(page_idx: int, text: str) -> list[NplGroupRow]:
    """Parse a single page that contains an NPL movement table.

    Strategy: don't try to track "Current Period" / "Prior Period" captions
    (banks place them inconsistently — sometimes before the rows, sometimes
    embedded as "Cari Dönem - 31 Aralık 2025" column-headers). Instead, key
    the block boundary on the *opening_balance row itself*: every NPL block
    starts with one ("Önceki Dönem Sonu Bakiyesi" / "Prior period end
    balance" / "Balances at End of Prior Period"). The 1st opening row =
    current period; the 2nd = prior period. After the 2nd block finishes
    (when we've seen the second opening_balance + closing_balance), stop
    extracting on this page so later sub-tables (e.g. FX-only NPL on the
    same page) don't contaminate the closing/provision values.
    """
    # Merge the wrapped transfer-label heads onto their number line first:
    # BURGAN / AKBNK / TSKB (English) wrap the long transfer labels across lines
    # ("Transfers from Other Categories of Non-performing" / "Loans (+) …"), so
    # transfers_in / transfers_out were dropped (NULL) and the roll-forward
    # couldn't tie. _merge_wrapped_labels is narrowly scoped to that head only.
    lines = _merge_wrapped_labels(text.splitlines())
    out: list[NplGroupRow] = []
    period_sequence = ["current", "prior"]
    period_idx = -1
    cur: dict[str, NplGroupRow] | None = None
    block_done = False  # True after net_balance: lock cur until next opening
    seen_additions = False  # within the current block — disambiguates date rows

    def _flush():
        nonlocal cur
        if cur is None:
            return
        for code in ("III", "IV", "V"):
            row = cur[code]
            # Emit a block that captured real data. Opening/closing anchor the
            # usual tables; additions/net_balance cover ALNTF's opening-less one.
            if any(getattr(row, f) is not None for f in
                   ("opening_balance", "closing_balance", "additions", "net_balance")):
                out.append(row)
        cur = None

    for ln in lines:
        line_stripped = ln.strip()
        if not line_stripped:
            continue
        key = _match_row_label(line_stripped)
        # ODEA / ALNTF print the opening & closing rows as bare period-end DATES
        # ("31 Aralık 2024 …" / "31 Aralık 2025 …") with no opening/closing WORD,
        # so the taxonomy can't match them. Fall back to the date-balance
        # detector and let POSITION decide: a date-row before Additions is the
        # opening; after the flows it's the closing. Only when no taxonomy label
        # matched, so a labelled "Önceki Dönem Sonu Bakiyesi: 31 Aralık 2023"
        # still wins as opening_balance.
        if key is None and _DATE_BALANCE_RX.match(line_stripped):
            key = "closing_balance" if seen_additions else "opening_balance"
        if key is None:
            continue
        m = _THREE_NUMS_TAIL.search(line_stripped)
        if not m:
            continue
        n3 = _parse_amount(m.group("n3"))
        n4 = _parse_amount(m.group("n4"))
        n5 = _parse_amount(m.group("n5"))
        # New block starts when we see an opening_balance row — OR, for banks like
        # HALKB whose movement block carries the prior-period close at the TOP
        # under the SAME "…period end balance" label as the closing, when we hit
        # such an end-balance row with no active block. Without this the real
        # total block is skipped (its opening reads as a closing) and a later
        # loans-by-borrower sub-category block wins (closing 9.440.946 instead of
        # the correct total 16.582.889). The bare "Current/Prior Period <nums>"
        # YKBNK labels (no "end balance" phrase) are excluded so that lane is
        # unaffected, and the flush below only emits blocks that got real data.
        # English-only phrase on purpose: HALKB (an English report) labels the
        # carried-forward opening "Current period end balance". Turkish reports
        # label their opening "Önceki Dönem Sonu Bakiyesi" (→ opening_balance,
        # handled above) and reuse a bare "Dönem Sonu Bakiyesi" across many
        # sub-tables — matching that here mis-started blocks (AKTIF regression).
        start_as_opening = key == "opening_balance" or (
            key == "closing_balance" and cur is None and not block_done
            and re.search(r"period end balance|balance at the end of the period",
                          line_stripped, re.IGNORECASE)
        )
        # ALNTF omits the opening row entirely — the movement table opens straight
        # on "Dönem İçinde İntikal (+)" (additions). Start a block on the first
        # additions row when none is active, assigning it to its OWN field (not
        # opening), so the flows + net balance are still captured.
        start_as_flow = key == "additions" and cur is None and not block_done
        starts_block = start_as_opening or start_as_flow
        if starts_block:
            _flush()
            period_idx += 1
            if period_idx >= len(period_sequence):
                # Third opening row would be from an unrelated table — stop.
                break
            pt = period_sequence[period_idx]
            cur = {
                "III": NplGroupRow(group_code="III", period_type=pt, page=page_idx),
                "IV":  NplGroupRow(group_code="IV",  period_type=pt, page=page_idx),
                "V":   NplGroupRow(group_code="V",   period_type=pt, page=page_idx),
            }
            block_done = False
            seen_additions = key == "additions"
            start_key = "opening_balance" if start_as_opening else key
            setattr(cur["III"], start_key, n3)
            setattr(cur["IV"],  start_key, n4)
            setattr(cur["V"],   start_key, n5)
            continue
        if cur is None or block_done:
            # block_done: net_balance has fired, the table proper has ended.
            # Any further matches on this page belong to a sub-table (FX-only
            # NPL, related-party loans, etc.) — don't pollute cur.
            continue
        if key == "additions":
            seen_additions = True
        # Store outflows as positive magnitudes — ALNTF prints them parenthesised
        # (negative); the roll-forward (and other banks) treat them as positive.
        if key in _OUTFLOW_KEYS:
            n3, n4, n5 = (abs(x) if x is not None else None for x in (n3, n4, n5))
        setattr(cur["III"], key, n3)
        setattr(cur["IV"],  key, n4)
        setattr(cur["V"],   key, n5)
        # net_balance is the last row of the movement table proper. After it,
        # subsequent identical-keyed rows on the same page belong to a
        # different table — freeze cur.
        if key == "net_balance":
            block_done = True
            # If this was the final period_type, no point scanning further.
            if period_idx + 1 >= len(period_sequence):
                _flush()
                break
    _flush()
    return out


def extract_from_pdf(
    pdf: pdfplumber.PDF,
    pdf_path: str = "",
    skip_pages: int = 60,
) -> NplMovementReport:
    """Scan the PDF for the NPL gross-amount movement table.

    `skip_pages` defaults to 60 because the NPL footnote is usually deep in the
    credit-risk section (pages ~80–140 of an annual report); scanning earlier is
    wasted text-extraction cost. But shorter INTERIM reports place the table
    earlier (e.g. FIBA 2026Q1 at page 56), so if the deep pass finds nothing we
    retry from a lower floor (25 — still safely past the BS/P&L/CF statements).
    The retry only runs on the otherwise-empty case, so passing reports are
    unaffected (strict superset).
    """
    rep = NplMovementReport(pdf_path=pdf_path)
    # FITZ-ONLY: scan AND parse with fitz (the engine the statement locators use)
    # — ~17× faster than pdfplumber's extract_text on every page (which dominated
    # this footnote lane's runtime) and never touches pdf.pages (so no pdfminer
    # poison-hang). fitz's row text parses identically through _extract_from_block
    # here (verified). Falls back to pdfplumber text only when fitz is unavailable.
    use_fitz = _HAS_FITZ and bool(pdf_path)
    n_pages = _n_pages(pdf) if use_fitz else len(pdf.pages)
    for lo in sorted({skip_pages, 25}, reverse=True):
        for i in range(lo + 1, n_pages + 1):
            text = (_fitz_page_text(pdf_path, i - 1) if use_fitz
                    else (pdf.pages[i - 1].extract_text() or ""))
            if not (_HEADING_RX.search(text) and _GROUPS_RX.search(text)):
                continue
            rows = _extract_from_block(i, text)
            if rows:
                rep.rows.extend(rows)
                # The table is rarely repeated — stop once found.
                return rep
    return rep


def extract(pdf_path: str | Path) -> NplMovementReport:
    pdf_path = str(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        return extract_from_pdf(pdf, pdf_path)


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------
def upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    rep: NplMovementReport,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_audit_npl_movement "
        "WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    )
    rows = [(
        bank_ticker, period, kind, r.group_code, r.period_type, r.page,
        r.opening_balance, r.additions, r.transfers_in, r.transfers_out,
        r.collections, r.write_offs, r.sold, r.fx_diff,
        r.closing_balance, r.provision, r.net_balance,
    ) for r in rep.rows]
    if rows:
        cur.executemany(
            "INSERT INTO bank_audit_npl_movement "
            "(bank_ticker, period, kind, group_code, period_type, source_page, "
            " opening_balance, additions, transfers_in, transfers_out, "
            " collections, write_offs, sold, fx_diff, closing_balance, "
            " provision, net_balance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    conn.commit()
    return len(rows)


def summarize(rep: NplMovementReport) -> str:
    if not rep.rows:
        return f"{Path(rep.pdf_path).name}\n  (no NPL movement table found)"
    lines = [Path(rep.pdf_path).name]
    for r in rep.rows:
        ob = f"{r.opening_balance:,.0f}" if r.opening_balance is not None else "-"
        cb = f"{r.closing_balance:,.0f}" if r.closing_balance is not None else "-"
        add = f"{r.additions:,.0f}" if r.additions is not None else "-"
        col = f"{r.collections:,.0f}" if r.collections is not None else "-"
        wo = f"{r.write_offs:,.0f}" if r.write_offs is not None else "-"
        lines.append(
            f"  p.{r.page:>3}  group {r.group_code:<3} {r.period_type:<7}  "
            f"open={ob:>20}  close={cb:>20}  +add={add:>18}  -col={col:>14}  -wo={wo:>10}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else "data/_tmp_akbnk_2025q4.pdf"
    rep = extract(path)
    print(summarize(rep))
