#!/usr/bin/env python
"""Render a captured filing to a standalone HTML page for human review.

Counts prove a capture ran; they do not prove it is RIGHT. This renders what was
actually stored — each table as a grid, each footnote under the table it
qualifies with the rows it links to — so the column inference, the wrapped-row
merging and the note linking can be judged by eye against the PDF.

Reads only `data/bank_audit_capture.db`. Writes one self-contained .html file.

Examples
--------
  python scripts/view_document_capture.py --bank AKBNK --period 2026Q1
  python scripts/view_document_capture.py --bank AKBNK --period 2026Q1 --pages 41,46
  python scripts/view_document_capture.py --list
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DEFAULT_DB = REPO / "data" / "bank_audit_capture.db"
DEFAULT_OUT = REPO / "data" / "audit_capture"

_CSS = """
:root{--bg:#fbfaf8;--fg:#1c1a17;--muted:#6b645c;--line:#e2ddd6;--card:#fff;
--accent:#8a5a2b;--note:#f6efe4;--warn:#a4472c;--chip:#efe9e1;}
@media (prefers-color-scheme:dark){:root{--bg:#16151a;--fg:#e8e4dd;--muted:#9a938a;
--line:#2e2b33;--card:#1e1d23;--accent:#d7a15f;--note:#2a2419;--warn:#e0855f;--chip:#2a272f;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:15px;margin:34px 0 10px;color:var(--muted);font-weight:600;
text-transform:uppercase;letter-spacing:.07em}
.sub{color:var(--muted);margin:0 0 22px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 26px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:8px 12px;min-width:92px}
.stat b{display:block;font-size:19px;font-variant-numeric:tabular-nums}
.stat span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.tbl{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin:0 0 22px;overflow:hidden}
.hd{padding:11px 14px;border-bottom:1px solid var(--line);display:flex;
gap:10px;align-items:baseline;flex-wrap:wrap}
.hd .pg{font:12px ui-monospace,monospace;color:var(--accent);white-space:nowrap}
.hd .cap{flex:1;min-width:220px;color:var(--fg)}
.hd .dim{font:12px ui-monospace,monospace;color:var(--muted);white-space:nowrap}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:4px 9px;text-align:right;white-space:nowrap;
font-variant-numeric:tabular-nums;border-top:1px solid var(--line)}
th{font-weight:600;color:var(--muted);font-size:11px;text-align:right;border-top:0}
td.lab,th.lab{text-align:left;white-space:normal;min-width:250px;max-width:460px;
font-variant-numeric:normal}
tr.merged td.lab{border-left:2px solid var(--accent)}
td.nil{color:var(--muted)}
.mk{color:var(--accent);font-size:11px}
.notes{border-top:1px solid var(--line);background:var(--note);padding:9px 14px}
.note{font-size:12.5px;margin:0 0 6px}
.note:last-child{margin:0}
.note b{color:var(--accent);font-family:ui-monospace,monospace}
.note .lk{color:var(--muted);font-size:11px}
.warn{color:var(--warn)}
.chip{background:var(--chip);border-radius:5px;padding:1px 6px;font-size:11px;
color:var(--muted);font-family:ui-monospace,monospace}
details{margin:0 0 22px}
summary{cursor:pointer;color:var(--muted);font-size:13px}
.warnbox{margin:18px 0;padding:12px 14px;border:1px solid var(--warn);border-left-width:4px;
 border-radius:6px;background:var(--note);color:var(--fg);font-size:13px;line-height:1.55}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:12px;overflow-x:auto;font-size:12px;white-space:pre-wrap}
/* Document-order rendering. A page rule every time the page turns, so a
   reviewer can hold the HTML beside the PDF page of the same number. */
.pg-rule{display:flex;align-items:center;gap:10px;margin:30px 0 14px}
.pg-rule::after{content:"";flex:1;height:1px;background:var(--line)}
.pg-rule b{font:12px ui-monospace,monospace;color:var(--accent);font-weight:600;
letter-spacing:.06em}
.pg-rule span{font-size:11px;color:var(--muted);text-transform:uppercase;
letter-spacing:.05em}
/* Prose keeps a reading measure; tables above stay full width. */
.prose{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 18px;margin:0 0 22px}
.prose p{margin:0 0 11px;max-width:74ch;font-size:13.5px;line-height:1.62}
.prose p:last-child{margin:0}
.prose h3{margin:16px 0 8px;font-size:13px;font-weight:600;color:var(--accent);
letter-spacing:.01em;text-wrap:balance}
.prose h3:first-child{margin-top:0}
.prose .furn{color:var(--muted);font-size:11.5px;font-family:ui-monospace,monospace;
white-space:pre-wrap}
/* The filing's own contents, and the subject banner where each item opens. */
.toc{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;margin:0 0 22px;column-width:330px;column-gap:34px}
.toc-s{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
color:var(--accent);font-weight:600;margin:12px 0 5px;break-after:avoid}
.toc-s:first-child{margin-top:0}
.toc-i{display:flex;gap:8px;align-items:baseline;font-size:12.5px;
margin:0 0 3px;break-inside:avoid}
.toc-i a{color:var(--fg);text-decoration:none;flex:1}
.toc-i a:hover,.toc-i a:focus-visible{text-decoration:underline}
.toc-n{color:var(--muted);font-family:ui-monospace,monospace;font-size:11px}
.toc-p{color:var(--muted);font-family:ui-monospace,monospace;font-size:11px;
white-space:nowrap}
.toc-i.off{opacity:.45}
.subj{margin:0 0 14px;padding:9px 14px;border-left:3px solid var(--accent);
background:var(--note);border-radius:0 8px 8px 0;scroll-margin-top:12px}
.subj-s{display:block;font-size:10.5px;text-transform:uppercase;
letter-spacing:.07em;color:var(--accent);margin:0 0 2px}
.subj b{font-size:14px;font-weight:600;text-wrap:balance}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
          "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
          "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII",
          "XXIX", "XXX"]
_RALT = "|".join(sorted(_ROMAN, key=len, reverse=True))

# A BRSA item head is numbered, in one of two conventions the filers split
# between: "3.3 Information on consolidated subsidiaries" (section-qualified,
# GARAN/KUVEYT/QNBFB) or "III. Explanations on basis of presentation"
# (bare roman, ALBRK/HALKB/DENIZ, either language).
#
# The title must START WITH A LETTER. That one test is the whole defence
# against a date: "31.12.2026 4.02%", "23.05.2017 28.02.2024" and "3.59
# 5.76-6.36" all match the numbering shape and are not heads. Display only;
# nothing stored changes.
_SECTION_HEAD = re.compile(
    r"^\d+(?:\.\d+)+\.?\s+[^\W\d_]|^\d+\.\s+[^\W\d_]|^(?:" + _RALT + r")\.\s+[^\W\d_]")


def _is_section_head(txt: str) -> bool:
    return len(txt) <= 130 and bool(_SECTION_HEAD.match(txt))


# The filing prints its own folio as the last line of each page — "11" for
# GARAN, "(13)" for EMLAK — and its contents page prints the folio each item
# starts on. Joining those two places every item on a real PDF page with no
# heuristic. Body heads were measured as the alternative and are far weaker:
# attribution ran 12%-100% of TOC items depending on the filer's convention.
_FOLIO = re.compile(r"^[(\[-]?\s*(\d{1,4})\s*[)\]-]?$")
_EN_ORD = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
           "NINE", "TEN"]
_TR_ORD = ["BIRINCI", "IKINCI", "UCUNCU", "DORDUNCU", "BESINCI", "ALTINCI",
           "YEDINCI"]
# Filers split on how they number sections: GARAN "SECTION ONE", ISCTR
# "SECTION I", Turkish originals "BİRİNCİ BÖLÜM". Anchoring on ^SECTION is also
# what keeps a prose cross-reference out ("As explained in Section Five Part
# II.h.4.5., …" does not start with it).
_SEC_EN = re.compile(r"^SECTION\s+(" + "|".join(_EN_ORD) + "|" + _RALT + r")\b")
_SEC_TR = re.compile(r"^(" + "|".join(_TR_ORD) + r")\s+BOLUM\b")
# The period after the item roman is optional — ISCTR prints "III Statement of
# Off-Balance Sheet Items 5" without one.
_TOC_ITEM = re.compile(r"^(" + _RALT + r")\.?\s+(\S.*)$")
# The trailing page, taking the START of a range: QNBFB indexes an item that
# spans pages as "Basis of presentation 11-13", and 11 is where it begins.
_TRAIL_PAGE = re.compile(r"^(.*?)\s+(\d{1,3})(?:\s*[-–—]\s*\d{1,3})?$")


def _sec_no(token: str) -> int | None:
    if token in _EN_ORD:
        return _EN_ORD.index(token) + 1
    if token in _TR_ORD:
        return _TR_ORD.index(token) + 1
    if token in _ROMAN:
        return _ROMAN.index(token) + 1
    return None
_TR_FOLD = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")


def _fold(s: str) -> str:
    """Uppercase that survives the Turkish dotted/dotless i."""
    return s.translate(_TR_FOLD).upper()


def _document_sections(lines) -> list[tuple] | None:
    """[(pdf_page, section_no, section_name, item_no, item_title)], or None.

    Returns None rather than a guess when the filing's own numbers do not
    corroborate each other — the contents must place its items on folios that
    exist and run forward. Measured over the 12-filing holdout, 9 filings
    validate; EMLAK, ISCTR and SKBNK do not and fall back to page order.
    """
    by_page: dict[int, list[str]] = defaultdict(list)
    for pg, _lo, txt, *_rest in lines:
        by_page[pg].append(txt or "")

    # A page's own folio reading is the raw signal, but any single page can lie:
    # EMLAK reads printed 2 on pdf 3 where the run says +5, SKBNK reads 13 on
    # pdf 12 where the run says +8. So a reading is kept only when it agrees
    # with the offset its NEIGHBOURS are using.
    #
    # The offset is deliberately local rather than one global constant. ISCTR
    # prints folio 9 on two consecutive pages, so its body genuinely runs at +6
    # before that point and +7 after; a single frame puts every early item one
    # page off, which is exactly the silent, plausible-looking error this whole
    # viewer exists to expose.
    pairs: list[tuple[int, int]] = []
    for pg in sorted(by_page):
        for t in reversed(by_page[pg][-4:]):
            t = t.strip()
            if not t:
                continue
            m = _FOLIO.match(t)
            if m:
                pairs.append((pg, int(m.group(1))))
            break
    if len(pairs) < 20:
        return None
    offs = [pg - pr for pg, pr in pairs]
    win = 7
    trusted: dict[int, int] = {}
    for idx, (pg, pr) in enumerate(pairs):
        near = offs[max(0, idx - win):idx + win + 1]
        if offs[idx] == Counter(near).most_common(1)[0][0]:
            trusted[pr] = pg
    if len(trusted) < 20:
        return None
    lo, hi = min(by_page), max(by_page)
    known = sorted(trusted)

    def _pdf_page(printed: int) -> int | None:
        """Nearest trusted anchor, walked out by the difference in folios."""
        if printed in trusted:
            return trusted[printed]
        near = min(known, key=lambda p: abs(p - printed))
        pg = trusted[near] + (printed - near)
        return pg if lo <= pg <= hi else None

    folio = {pr: pg for pr in range(1, max(known) + 1)
             if (pg := _pdf_page(pr)) is not None}

    items: list[tuple] = []
    names: dict[int, str] = {}
    cur, last_pg, want_name = None, None, False
    pending: tuple | None = None          # item whose page number wrapped

    def _take(printed: int) -> None:
        if pending and printed in folio:
            items.append((folio[printed], pending[0], pending[1], pending[2]))

    for pg, _lo, txt, *_rest in lines:
        t = (txt or "").strip()
        m = _SEC_EN.match(_fold(t)) or _SEC_TR.match(_fold(t))
        if m:
            n = _sec_no(m.group(1))
            # A section banner reprinted in the body is not a second contents.
            cur = None if (n is None or n in names) else n
            if cur is not None:
                names[n] = ""
                want_name = True
            pending, last_pg = None, pg
            continue
        if cur is None or (last_pg is not None and pg > last_pg + 2):
            cur, pending = None, None
            continue
        mi = _TOC_ITEM.match(t)
        if want_name and t and not mi:
            names[cur] = t[:80]
            want_name = False
            continue
        if mi:
            title, printed = mi.group(2), None
            mt = _TRAIL_PAGE.match(title)
            if mt:
                title, printed = mt.group(1), int(mt.group(2))
            pending = (cur, _ROMAN.index(mi.group(1)) + 1, title[:90])
            if printed is not None:
                _take(printed)
                pending = None
            last_pg = pg
            continue
        # A wrapped entry carries its page on the continuation: ISCTR puts the
        # number alone on the next line, QNBFB ends the run-on text with it.
        if pending:
            mf = _FOLIO.match(t)
            if mf:
                _take(int(mf.group(1)))
                pending = None
                continue
            mc = _TRAIL_PAGE.match(t)
            if mc:
                _take(int(mc.group(2)))
                pending = None

    if len(items) < 20:
        return None
    pages = [i[0] for i in items]
    if any(a > b for a, b in zip(pages, pages[1:])):
        return None                      # contents disagrees with the folios
    return [(pg, s, names.get(s, ""), i, title) for pg, s, i, title in items]


def _partitions(conn) -> list[tuple]:
    return conn.execute(
        "SELECT bank_ticker,period,kind,COUNT(*) FROM bank_audit_document_pages "
        "GROUP BY 1,2,3 ORDER BY 1,2,3").fetchall()


def render(conn, bank: str, period: str, kind: str,
           pages: set[int] | None, min_cols: int,
           show_prose: bool = True, show_furniture: bool = False) -> str:
    key = (bank, period, kind)
    lines = conn.execute(
        "SELECT page,line_order,text,label,role,block_id,logical_row,markers_json "
        "FROM bank_audit_document_lines WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,line_order", key).fetchall()
    if not lines:
        sys.exit(f"no capture stored for {bank} {period} {kind}")
    cells = conn.execute(
        "SELECT page,line_order,col_index,text,is_numeric FROM bank_audit_document_cells "
        "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY page,line_order,cell_index",
        key).fetchall()
    blocks = conn.execute(
        "SELECT page,block_id,n_cols,heading,row_count,cell_count,col_labels_json "
        "FROM bank_audit_document_blocks WHERE bank_ticker=? AND period=? AND kind=? "
        "ORDER BY page,block_id", key).fetchall()
    notes = conn.execute(
        "SELECT page,block_id,marker,text,linked_lines_json FROM bank_audit_document_notes "
        "WHERE bank_ticker=? AND period=? AND kind=? ORDER BY page,note_order", key).fetchall()
    try:
        unreadable_pages = [r[0] for r in conn.execute(
            "SELECT page FROM bank_audit_document_pages WHERE bank_ticker=? AND "
            "period=? AND kind=? AND text_layer!='text' ORDER BY page", key)]
    except sqlite3.OperationalError:
        unreadable_pages = []    # ledger predates the text_layer column

    cell_at: dict[tuple[int, int], list] = defaultdict(list)
    for pg, lo, ci, txt, isnum in cells:
        cell_at[(pg, lo)].append((ci, txt, isnum))
    lines_of: dict[tuple[int, int], list] = defaultdict(list)
    for pg, lo, txt, lab, role, bid, lr, mk in lines:
        if bid is not None:
            lines_of[(pg, bid)].append((lo, lab, lr, json.loads(mk or "[]")))
    notes_of: dict[tuple[int, int], list] = defaultdict(list)
    for pg, bid, marker, txt, lk in notes:
        notes_of[(pg, bid)].append((marker, txt, json.loads(lk or "[]")))

    total_cells = len(cells)
    # Column-assignment rate is only meaningful for cells INSIDE a table. A
    # figure quoted in a sentence has no column by construction, so counting it
    # as unassigned understates the grid quality.
    in_block = {(pg, lo) for pg, lo, _t, _lb, _r, bid, _lr, _m in lines if bid is not None}
    tbl_cells = [c for c in cells if (c[0], c[1]) in in_block]
    tbl_assigned = sum(1 for c in tbl_cells if c[2] is not None)
    roles: dict[str, int] = defaultdict(int)
    for _pg, _lo, _t, _lb, role, _b, _lr, _m in lines:
        roles[role] += 1

    out: list[str] = []
    a = out.append
    a(f"<h1>{_esc(bank)} {_esc(period)} <span class='chip'>{_esc(kind)}</span></h1>")
    a("<p class='sub'>Every table the filing prints, as captured — columns inferred "
      "from figure geometry, wrapped rows merged, footnotes linked to the rows "
      "carrying their marker"
      + (", with the narrative between them in printed order.</p>" if show_prose
         else ".</p>"))
    a("<div class='stats'>")
    for label, val in [("pages", len({p for p, *_ in lines})),
                       ("tables", len(blocks)), ("lines", len(lines)),
                       ("cells", total_cells), ("notes", len(notes)),
                       ("linked notes", sum(1 for *_x, lk in notes_of_all(notes) if lk))]:
        a(f"<div class='stat'><b>{val:,}</b><span>{label}</span></div>")
    pct = 100 * tbl_assigned / len(tbl_cells) if tbl_cells else 0
    a(f"<div class='stat'><b>{pct:.1f}%</b><span>table cells in a column</span></div>")
    a(f"<div class='stat'><b>{len(tbl_cells):,}</b><span>cells in a table</span></div>")
    a("</div>")
    # State the hole before showing what WAS captured. A viewer that lists 13
    # tables and stays quiet about 39 unreadable pages misleads exactly the way
    # the capture itself did.
    if unreadable_pages:
        a("<div class='warnbox'><b>⚠ "
          f"{len(unreadable_pages)} of these pages could not be read.</b> Their content "
          "is drawn as vector glyph outlines or embedded as a raster image rather "
          "than typed — legible on screen, invisible to any extractor — so <b>no row "
          "from them appears below</b>. Recovering them would need OCR. Pages: "
          f"{_esc(', '.join(str(p) for p in unreadable_pages))}</div>")
    a("<h2>Line roles</h2><div class='stats'>")
    for r in ("data", "heading", "footnote", "paragraph", "furniture"):
        a(f"<div class='stat'><b>{roles.get(r, 0):,}</b><span>{r}</span></div>")
    a("</div>")

    # --- document order ----------------------------------------------------
    # Tables alone are not the filing. A BRSA report is mostly narrative — for
    # GARAN 2026Q1, 3,249 paragraph lines against 2,293 data rows — and the
    # prose is what says which basis a table is on. Walking the lines in
    # printed order puts each table back among the sentences that introduce it,
    # which is also what makes the page checkable against the PDF page by page.
    block_by = {(b[0], b[1]): b for b in blocks}
    emitted: set[tuple[int, int]] = set()
    shown = 0

    # The filing's own contents, placed on real pages. None when the filing's
    # numbers do not corroborate each other, in which case the document still
    # renders — in page order, unlabelled — rather than under a wrong subject.
    sections = _document_sections(lines) if show_prose else None
    starts: dict[int, list[tuple]] = defaultdict(list)
    if sections:
        for pg, s, sname, i, title in sections:
            starts[pg].append((s, sname, i, title))
        a("<h2>Contents</h2><div class='toc'>")
        cur_s = None
        for pg, s, sname, i, title in sections:
            if s != cur_s:
                a(f"<div class='toc-s'>Section {s}{' &middot; ' + _esc(sname) if sname else ''}</div>")
                cur_s = s
            vis = "" if (not pages or pg in pages) else " class='off'"
            a(f"<div class='toc-i'{vis}><a href='#s{s}-{i}'>"
              f"<span class='toc-n'>{_ROMAN[i - 1]}.</span> {_esc(title)}</a>"
              f"<span class='toc-p'>p.{pg}</span></div>")
        a("</div>")

    a("<h2>Document</h2>")

    stream: list[tuple] = []          # ("tbl", blockrow) | ("prose", [(role,text)])
    run: list[tuple[str, str]] = []

    def _flush() -> None:
        if run:
            stream.append(("prose", run.copy()))
            run.clear()

    cur_page = None
    for pg, lo, txt, lab, role, bid, lr, mk in lines:
        if pages and pg not in pages:
            continue
        if pg != cur_page:
            _flush()
            stream.append(("page", pg))
            cur_page = pg
        if bid is not None:
            # Every line of a table belongs to the table, not to the prose.
            key = (pg, bid)
            blk = block_by.get(key)
            if key not in emitted and blk is not None and blk[2] >= min_cols:
                _flush()
                stream.append(("tbl", blk))
                emitted.add(key)
            continue
        if role == "furniture" and not show_furniture:
            continue          # running head/foot, reprinted on every page
        if role == "footnote":
            continue          # already rendered under its table, as a note
        if not (txt or "").strip():
            continue
        run.append((role, txt.strip()))
    _flush()

    if not show_prose:
        stream = [s for s in stream if s[0] != "prose"]
    # A page rule with nothing under it is noise, so drop pages that ended up
    # empty once the filters above ran.
    pruned: list[tuple] = []
    for item in stream:
        if item[0] == "page" and pruned and pruned[-1][0] == "page":
            pruned[-1] = item
            continue
        pruned.append(item)
    if pruned and pruned[-1][0] == "page":
        pruned.pop()

    for item in pruned:
        if item[0] == "page":
            pg = item[1]
            a(f"<div class='pg-rule'><b>PAGE {pg}</b><span>of the filing</span></div>")
            # The subjects that OPEN on this page, straight from the contents.
            for s, sname, i, title in starts.get(pg, []):
                a(f"<div class='subj' id='s{s}-{i}'>"
                  f"<span class='subj-s'>Section {s}"
                  f"{' &middot; ' + _esc(sname) if sname else ''}</span>"
                  f"<b>{_ROMAN[i - 1]}. {_esc(title)}</b></div>")
            continue
        if item[0] == "prose":
            a("<div class='prose'>")
            para: list[str] = []
            for role, txt in item[1]:
                if role == "heading" or _is_section_head(txt):
                    if para:
                        a(f"<p>{_esc(' '.join(para))}</p>")
                        para = []
                    a(f"<h3>{_esc(txt)}</h3>")
                elif role == "furniture":
                    if para:
                        a(f"<p>{_esc(' '.join(para))}</p>")
                        para = []
                    a(f"<div class='furn'>{_esc(txt)}</div>")
                else:
                    para.append(txt)
            if para:
                a(f"<p>{_esc(' '.join(para))}</p>")
            a("</div>")
            continue

        pg, bid, ncols, heading, rows_n, cells_n, col_labels_json = item[1]
        col_labels = json.loads(col_labels_json or "[]")
        shown += 1
        grouped: dict[int, list] = defaultdict(list)
        for lo, lab, lr, mk in lines_of[(pg, bid)]:
            grouped[lr if lr is not None else -lo].append((lo, lab, mk))
        a("<div class='tbl'>")
        a("<div class='hd'>"
          f"<span class='pg'>p.{pg}&nbsp;#{bid}</span>"
          f"<span class='cap'>{_esc((heading or '').strip()[:190]) or '<i>(no printed caption)</i>'}</span>"
          f"<span class='dim'>{rows_n}&times;{ncols}</span></div>")
        a("<div class='scroll'><table><thead><tr><th class='lab'>row label</th>")
        for c in range(ncols):
            # The filing's own printed header where we could read it, so the
            # grid is judged against real column names rather than c0/c1/…
            name = col_labels[c] if c < len(col_labels) and col_labels[c] else f"c{c}"
            a(f"<th>{_esc(name)}</th>")
        a("</tr></thead><tbody>")
        for lr in sorted(grouped):
            parts = grouped[lr]
            lab = " ".join(p[1] for p in parts if p[1]).strip()
            mks = [m for p in parts for m in p[2]]
            grid: dict[int, tuple[str, int]] = {}
            for lo, _lab, _mk in parts:
                for ci, txt, isnum in cell_at[(pg, lo)]:
                    if ci is not None:
                        grid[ci] = (txt, isnum)
            cls = " class='merged'" if len(parts) > 1 else ""
            # Only chip a marker the label does not already show. A star marker
            # survives in the label text, so chipping it again rendered
            # "Nakit Değerler ve Merkez Bankası (*) (*)".
            extra = [m for m in dict.fromkeys(mks) if f"({m})" not in lab]
            mk_html = ("&nbsp;<span class='mk'>(" + ")(".join(_esc(m) for m in extra) + ")</span>"
                       if extra else "")
            a(f"<tr{cls}><td class='lab'>{_esc(lab) or '&nbsp;'}{mk_html}</td>")
            for c in range(ncols):
                if c in grid:
                    txt, isnum = grid[c]
                    a(f"<td{'' if isnum else ' class=nil'}>{_esc(txt)}</td>")
                else:
                    a("<td class='nil'>&nbsp;</td>")
            a("</tr>")
        a("</tbody></table></div>")
        blk_notes = notes_of.get((pg, bid), [])
        if blk_notes:
            a("<div class='notes'>")
            for marker, txt, lk in blk_notes:
                # No linked row is normal, not a defect: a "(*)" caption often
                # qualifies the whole table ("monthly simple arithmetic
                # average…") rather than any single row.
                lkt = (f"<span class='lk'>&rarr; rows {', '.join(str(x) for x in lk)}</span>"
                       if lk else "<span class='lk'>&rarr; whole table</span>")
                # The stored text keeps the note exactly as printed, marker and
                # all; the marker is already shown in bold beside it, so strip
                # the leading copy rather than render "(*) (*) …".
                body = txt[:600].lstrip()
                if marker and body.startswith(f"({marker})"):
                    body = body[len(marker) + 2:].lstrip()
                a(f"<div class='note'><b>({_esc(marker)})</b> {_esc(body)} {lkt}</div>")
            a("</div>")
        a("</div>")
    if not shown and not any(i[0] == "prose" for i in pruned):
        a("<p class='sub'>Nothing matched the filter.</p>")

    # Notes that qualify no table still qualify SOMETHING — a ratings line, a
    # unit caption — and rendering only table-bound notes made them invisible
    # even once they were correctly linked.
    loose = [(pg, marker, txt, json.loads(lk or "[]"))
             for pg, bid, marker, txt, lk in notes
             if bid is None and (not pages or pg in pages)]
    if loose:
        a("<h2>Notes not attached to a table</h2>")
        for pg, marker, txt, lk in loose:
            tgt = ""
            if lk:
                tgt = (" <span class='sub'>→ lines "
                       + ", ".join(str(x) for x in lk[:6]) + "</span>")
            # The stored text keeps the marker it was printed with, so strip it
            # before prepending the badge rather than showing "(*) (*)…".
            body = txt
            if marker and body.startswith(f"({marker})"):
                body = body[len(marker) + 2:].lstrip()
            a("<div class='note'><b>" + (f"({_esc(marker)}) " if marker else "")
              + "</b>" + _esc(body[:400]) + tgt + f" <span class='sub'>p.{pg}</span></div>")
    return "\n".join(out)


def notes_of_all(notes):
    for pg, bid, marker, txt, lk in notes:
        yield pg, bid, marker, txt, json.loads(lk or "[]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--bank")
    ap.add_argument("--period")
    ap.add_argument("--kind", default="consolidated")
    ap.add_argument("--pages", help="comma-separated page numbers to include")
    ap.add_argument("--min-cols", type=int, default=2,
                    help="skip blocks narrower than this (default 2)")
    ap.add_argument("--no-prose", action="store_true",
                    help="tables only; omit the narrative between them")
    ap.add_argument("--furniture", action="store_true",
                    help="also show running heads/feet (reprinted every page)")
    ap.add_argument("--out", help="output .html path")
    ap.add_argument("--list", action="store_true", help="list captured partitions and exit")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    if args.list:
        rows = _partitions(conn)
        print(f"{len(rows)} captured partitions in {args.db}")
        for b, p, k, n in rows:
            print(f"  {b:8} {p} {k:15} {n:4} pages")
        return 0
    if not (args.bank and args.period):
        ap.error("--bank and --period are required (or use --list)")

    pages = {int(x) for x in args.pages.split(",")} if args.pages else None
    body = render(conn, args.bank.upper(), args.period.upper(), args.kind,
                  pages, args.min_cols,
                  show_prose=not args.no_prose, show_furniture=args.furniture)
    out = Path(args.out) if args.out else (
        DEFAULT_OUT / f"{args.bank.upper()}_{args.period.upper()}_{args.kind}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{_esc(args.bank.upper())} {_esc(args.period.upper())} capture</title>"
           f"<style>{_CSS}</style></head><body><div class='wrap'>{body}</div></body></html>")
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
