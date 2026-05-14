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

from .extractor import parse_num


# ---------------------------------------------------------------------------
# Row-label taxonomy — map each observed label (TR + EN, with variants) to
# a canonical column key. Longest-first matching.
# ---------------------------------------------------------------------------
_ROW_LABELS: list[tuple[str, str]] = [
    # Opening (always the first row)
    ("önceki dönem sonu bakiyesi", "opening_balance"),
    ("prior period end balance", "opening_balance"),
    ("balances at end of prior period", "opening_balance"),
    ("beginning balance", "opening_balance"),
    ("opening balance", "opening_balance"),
    # Closing — must come BEFORE "balance" prefixes for longest-first.
    ("current period end balance", "closing_balance"),
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
    ("transfers from other categories", "transfers_in"),
    # Transfers out
    ("diğer donuk alacak hesaplarına çıkış", "transfers_out"),
    ("transfer to other npl categories", "transfers_out"),
    ("transfers to other categories of loans under non-performing", "transfers_out"),
    ("transfers to other categories", "transfers_out"),
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
    # Sold
    ("debt sale", "sold"),
    ("satılan", "sold"),
    ("sold", "sold"),
    # FX revaluation differential
    ("foreign currency differences", "fx_diff"),
    ("yabancı para çevrim farkları", "fx_diff"),
    # Provision
    ("provisions (-)", "provision"),
    ("provision (-)", "provision"),
    ("karşılık (-)", "provision"),
    ("provisions", "provision"),
    ("provision", "provision"),
    ("karşılık", "provision"),
    # Net balance
    ("net balance on balance sheet", "net_balance"),
    ("bilançodaki net bakiyesi", "net_balance"),
]
_ROW_LABELS_SORTED = sorted(_ROW_LABELS, key=lambda kv: -len(kv[0]))


# Heading detector — the page must mention NPL movement / hareket explicitly.
_HEADING_RX = re.compile(
    r"(?:Movements?\s+in\s+non[-\s]?performing\s+loans?(?:\s+groups?)?|"
    r"movement\s+of\s+non[-\s]?performing\s+loans?|"
    r"information\s+on\s+the\s+movement\s+of\s+non[-\s]?performing\s+loans?|"
    r"donuk\s+alacak\s+hareketlerine|"
    r"takipteki\s+kredilerin\s+hareketleri)",
    re.IGNORECASE,
)
# Group-column header (3 columns, Roman III/IV/V or Group/Grup variants).
_GROUPS_RX = re.compile(
    r"(?:III\.\s*(?:Group|Grup).{0,80}?IV\.\s*(?:Group|Grup).{0,80}?V\.\s*(?:Group|Grup)|"
    r"Group\s*III.{0,80}?Group\s*IV.{0,80}?Group\s*V)",
    re.IGNORECASE | re.DOTALL,
)


# Three trailing numbers (the III / IV / V column values per row). Accept
# digits with TR/EN thousand-separators, "-" for nil, and parenthesised
# negatives.
_THREE_NUMS_TAIL = re.compile(
    r"(?P<n3>(?:\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|-))"
    r"\s+"
    r"(?P<n4>(?:\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|-))"
    r"\s+"
    r"(?P<n5>(?:\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\)?|-))"
    r"\s*$"
)


def _parse_amount(s: str) -> float | None:
    s = s.strip()
    if s in ("-", "—", "–", ""):
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


def _merge_wrapped_labels(lines: list[str]) -> list[str]:
    """Same row-wrap merge as loans_by_sector: a numberless short line
    followed by a 3-number line is merged into one logical row."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if not cur.strip():
            out.append(cur)
            i += 1
            continue
        cur_has_num = bool(re.search(r"\d", cur))
        looks_like_label_head = (
            not cur_has_num
            and len(cur.strip()) <= 80
            and not cur.strip().endswith((".", ":", ";"))
        )
        if looks_like_label_head and i + 1 < len(lines):
            nxt = lines[i + 1]
            if _THREE_NUMS_TAIL.search(nxt.strip()):
                out.append(cur.strip() + " " + nxt.strip())
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
    lines = text.splitlines()
    out: list[NplGroupRow] = []
    period_sequence = ["current", "prior"]
    period_idx = -1
    cur: dict[str, NplGroupRow] | None = None
    block_done = False  # True after net_balance: lock cur until next opening

    def _flush():
        nonlocal cur
        if cur is None:
            return
        for code in ("III", "IV", "V"):
            row = cur[code]
            if row.opening_balance is not None or row.closing_balance is not None:
                out.append(row)
        cur = None

    for ln in lines:
        line_stripped = ln.strip()
        if not line_stripped:
            continue
        key = _match_row_label(line_stripped)
        if key is None:
            continue
        m = _THREE_NUMS_TAIL.search(line_stripped)
        if not m:
            continue
        n3 = _parse_amount(m.group("n3"))
        n4 = _parse_amount(m.group("n4"))
        n5 = _parse_amount(m.group("n5"))
        # New block starts when we see opening_balance.
        if key == "opening_balance":
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
        if cur is None or block_done:
            # block_done: net_balance has fired, the table proper has ended.
            # Any further matches on this page belong to a sub-table (FX-only
            # NPL, related-party loans, etc.) — don't pollute cur.
            continue
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

    `skip_pages` defaults to 60 because the NPL footnote is consistently
    deep in the credit-risk section — typically pages 80–140 of the
    audit report. Scanning earlier pages is wasted text-extraction
    cost.
    """
    rep = NplMovementReport(pdf_path=pdf_path)
    for i, page in enumerate(pdf.pages, 1):
        if i <= skip_pages:
            continue
        text = page.extract_text() or ""
        if not (_HEADING_RX.search(text) and _GROUPS_RX.search(text)):
            continue
        rows = _extract_from_block(i, text)
        if rows:
            rep.rows.extend(rows)
            # The table is rarely repeated — once we've found it on one
            # page we stop scanning. This saves time on big PDFs.
            break
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
