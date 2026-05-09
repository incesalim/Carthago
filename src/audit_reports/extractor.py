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

import pdfplumber

# Match a numeric token. Handles both EN and TR thousands/decimal conventions:
#   EN:  1,234,567.89
#   TR:  1.234.567,89
# Also bare integers and "-" for zero. Negatives may be wrapped in parens.
NUM_PAT = r'(?:\(\s*-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*\)|-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|-)'

HIERARCHY_PAT = re.compile(
    r'^(?P<h>(?:[IVX]+\.|[A-Z]\.|\d+(?:\.\d+)*\.?))\s+(?P<rest>.+)$'
)
TOTAL_PAT = re.compile(r'TOTAL\b', re.I)


def parse_num(s: str) -> float | None:
    s = s.strip()
    if s == '-' or s == '':
        return 0.0
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()').strip()
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


def extract_page_text_repaired(page) -> str:
    """Reconstruct text per row using x-coordinates so split-digit numbers merge.

    pdfplumber's extract_text() sometimes splits a number like '586.339.528' into
    '5' and '86.339.528' if the rendering nudges the leading digit. This function
    groups words on each row by similar y-coordinate, then merges adjacent tokens
    when one is a single digit very close to a numeric token.
    """
    words = page.extract_words(use_text_flow=False)
    rows: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        # Bucket by y (round to integer)
        y_key = int(round(w['top']))
        rows[y_key].append(w)
    # Merge close y-buckets (within 2px) into single rows
    sorted_keys = sorted(rows.keys())
    merged: dict[int, list[dict]] = {}
    last_key = None
    for k in sorted_keys:
        if last_key is not None and k - last_key <= 2:
            merged[last_key].extend(rows[k])
        else:
            merged[k] = list(rows[k])
            last_key = k

    out_lines = []
    for y in sorted(merged.keys()):
        ws = sorted(merged[y], key=lambda w: w['x0'])
        # Merge digit-fragment runs: token=='[0-9]' immediately before a token starting with a digit
        merged_tokens: list[tuple[float, str]] = []
        i = 0
        while i < len(ws):
            cur = ws[i]
            text = cur['text']
            x0 = cur['x0']
            x1 = cur['x1']
            # Look ahead: if cur is a single digit (or 1-2 digits) AND next is digit-rich
            # AND gap is <5px, merge
            j = i + 1
            while j < len(ws):
                nxt = ws[j]
                gap = nxt['x0'] - x1
                if (
                    re.match(r'^\d{1,2}$', text)
                    and re.match(r'^[\d.,]', nxt['text'])
                    and gap < 4
                ):
                    text = text + nxt['text']
                    x1 = nxt['x1']
                    j += 1
                    continue
                # Allow merging continuation like `.022.683` to previous digits
                if (
                    re.match(r'^\d', text[-1] if text else '')
                    and re.match(r'^[.,]\d', nxt['text'])
                    and gap < 4
                ):
                    text = text + nxt['text']
                    x1 = nxt['x1']
                    j += 1
                    continue
                break
            merged_tokens.append((x0, text))
            i = j
        line = ' '.join(t for _, t in merged_tokens)
        out_lines.append(line)
    return '\n'.join(out_lines)


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


def _split_label(label: str) -> tuple[str, str, str]:
    """Returns (hierarchy_token, clean_name, footnote_ref). Footnote is a trailing
    pattern like '5.1.1' that follows the item name."""
    m = HIERARCHY_PAT.match(label.strip())
    if m:
        h = m.group('h')
        rest = m.group('rest').strip()
    else:
        h = ''
        rest = label.strip()
    # Footnote ref: trailing token like 5.1.1 or 5.4.12
    footnote = None
    fm = re.search(r'\s(\d+(?:\.\d+){1,3})$', rest)
    if fm:
        footnote = fm.group(1)
        rest = rest[: fm.start()].strip()
    return h, rest, footnote


def _parse_rows(text: str, n_cols: int) -> list[tuple[str, list[float | None]]]:
    """For each line that ends in N numeric tokens, return (label, values)."""
    rows: list[tuple[str, list[float | None]]] = []
    for line in text.split('\n'):
        line = line.rstrip()
        if not line.strip():
            continue
        # Find all numeric tokens
        nums = re.findall(NUM_PAT, line)
        if len(nums) < n_cols:
            continue
        last_n = nums[-n_cols:]
        # Locate label as substring before the first of the trailing N numbers
        # Find position of last_n[0] starting from the right
        pos = line.rfind(last_n[0])
        if pos == -1:
            continue
        # Walk back through any previous trailing numbers that should also be excluded
        for tok in reversed(last_n[1:]):
            new_pos = line.rfind(tok, 0, pos)
            if new_pos != -1:
                pos = new_pos
        # Find label by trimming nums[-n_cols] start
        # Simpler: split line into [label, ...nums]; label = everything before last_n[0]'s position
        label_pos = pos
        # But we may have matched a number INSIDE the label (footnote). Try walking left past
        # any numeric tokens that immediately precede last_n[0] in adjacent text.
        label = line[:label_pos].rstrip()
        # If label still contains the entire numeric trail, skip
        if not label:
            continue
        if not (HIERARCHY_PAT.match(label) or TOTAL_PAT.search(label)):
            # Continuation line or noise
            continue
        # Reject pure date labels ("1 January 2024", "31 December 2024")
        if re.match(r'^\d+\.?\s+(January|February|March|April|May|June|July|August|September|October|November|December|Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\b', label):
            continue
        vals = [parse_num(x) for x in last_n]
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


def _locate_pages(pdf: pdfplumber.PDF) -> dict[str, int]:
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
        matchers[kind] = (pat, [_norm(s) for s in cfg['support']])
    out: dict[str, int] = {}
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ''
        norm_full = _norm(text)
        norm_lines = [_norm(ln) for ln in text.split('\n')]
        for kind, (pat, supports) in matchers.items():
            if kind in out:
                continue
            first_match = any(pat.match(ln) for ln in norm_lines)
            if not first_match:
                continue
            if not any(s in norm_full for s in supports):
                continue
            out[kind] = i
            break
    return out


def extract(pdf_path: str | Path) -> BankReport:
    """Parse one BRSA-format audit report. Returns a BankReport with rows populated."""
    pdf_path = str(pdf_path)
    rep = BankReport(pdf_path=pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        loc = _locate_pages(pdf)
        if 'bs_assets' in loc:
            text = extract_page_text_repaired(pdf.pages[loc['bs_assets'] - 1])
            for order, (label, vals) in enumerate(_parse_rows(text, 6), 1):
                h, name, fn = _split_label(label)
                rep.bs_assets.append(StatementRow(
                    order=order, hierarchy=h, name=name, footnote=fn,
                    cur_tl=vals[0], cur_fc=vals[1], cur_total=vals[2],
                    pri_tl=vals[3], pri_fc=vals[4], pri_total=vals[5],
                ))
        if 'bs_liab' in loc:
            text = extract_page_text_repaired(pdf.pages[loc['bs_liab'] - 1])
            for order, (label, vals) in enumerate(_parse_rows(text, 6), 1):
                h, name, fn = _split_label(label)
                rep.bs_liabilities.append(StatementRow(
                    order=order, hierarchy=h, name=name, footnote=fn,
                    cur_tl=vals[0], cur_fc=vals[1], cur_total=vals[2],
                    pri_tl=vals[3], pri_fc=vals[4], pri_total=vals[5],
                ))
        if 'off_bs' in loc:
            text = extract_page_text_repaired(pdf.pages[loc['off_bs'] - 1])
            for order, (label, vals) in enumerate(_parse_rows(text, 6), 1):
                h, name, fn = _split_label(label)
                rep.off_balance.append(StatementRow(
                    order=order, hierarchy=h, name=name, footnote=fn,
                    cur_tl=vals[0], cur_fc=vals[1], cur_total=vals[2],
                    pri_tl=vals[3], pri_fc=vals[4], pri_total=vals[5],
                ))
        if 'pl' in loc:
            text = extract_page_text_repaired(pdf.pages[loc['pl'] - 1])
            for order, (label, vals) in enumerate(_parse_rows(text, 2), 1):
                h, name, fn = _split_label(label)
                rep.profit_loss.append(StatementRow(
                    order=order, hierarchy=h, name=name, footnote=fn,
                    cur_amount=vals[0], pri_amount=vals[1],
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
