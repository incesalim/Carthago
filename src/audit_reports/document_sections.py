"""Section structure of a captured filing, from the filing's own numbers.

Shared by `scripts/view_document_capture.py` (the banners and contents box it
renders) and `scripts/build_document_tables.py` (the section columns of the
derived per-table lane). One implementation, because two copies of "where does
Section 4 start" is how the viewer and the queryable lane would drift apart.

Input everywhere is the capture ledger's line rows ordered by page then
line_order — any iterable of tuples whose first three fields are
(page, line_order, text); trailing fields are ignored.

Two independent readings, in order of authority:

* `document_contents` — the filing's own contents page, placed on real PDF
  pages by joining each item's printed folio to the folio line each page
  prints. Item-level (Section 2 / "III. Konsolide gelir tablosu" / p.10) and
  self-validating: it returns None rather than a guess when the filing's
  numbers do not corroborate each other. Measured over the 12-filing holdout,
  9 filings validate; EMLAK, ISCTR and SKBNK do not.
* `body_section_starts` — the "BEŞİNCİ BÖLÜM" / "SECTION FIVE" banners printed
  in the body. Section-level only, for filings whose contents do not validate.
  Pages carrying two or more distinct banners are the contents itself and are
  excluded, and a reading whose starts run backwards is refused the same way.

Roles come from `prose.role_from_title` over each section's own declared
title, with the printed-position fallback (`SECTION_ROLES_ANNUAL`/`_INTERIM`)
only where the title says nothing — the §6/§7 swap between annual and interim
filings is why the number alone is never the meaning.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
         "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
         "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII",
         "XXIX", "XXX"]
RALT = "|".join(sorted(ROMAN, key=len, reverse=True))

# The filing prints its own folio as the last line of each page — "11" for
# GARAN, "(13)" for EMLAK — and its contents page prints the folio each item
# starts on. Joining those two places every item on a real PDF page with no
# heuristic. Body heads were measured as the alternative and are far weaker:
# attribution ran 12%-100% of TOC items depending on the filer's convention.
_FOLIO = re.compile(r"^[(\[-]?\s*(\d{1,4})\s*[)\]-]?$")
_EN_ORD = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
           "NINE", "TEN"]
_TR_ORD = ["BIRINCI", "IKINCI", "UCUNCU", "DORDUNCU", "BESINCI", "ALTINCI",
           "YEDINCI", "SEKIZINCI"]
# Filers split on how they number sections: GARAN "SECTION ONE", ISCTR
# "SECTION I", Turkish originals "BİRİNCİ BÖLÜM". Anchoring on ^SECTION is also
# what keeps a prose cross-reference out ("As explained in Section Five Part
# II.h.4.5., …" does not start with it).
SEC_EN = re.compile(r"^SECTION\s+(" + "|".join(_EN_ORD) + "|" + RALT + r")\b")
SEC_TR = re.compile(r"^(" + "|".join(_TR_ORD) + r")\s+BOLUM\b")
# The period after the item roman is optional — ISCTR prints "III Statement of
# Off-Balance Sheet Items 5" without one.
_TOC_ITEM = re.compile(r"^(" + RALT + r")\.?\s+(\S.*)$")
# The trailing page, taking the START of a range: QNBFB indexes an item that
# spans pages as "Basis of presentation 11-13", and 11 is where it begins.
_TRAIL_PAGE = re.compile(r"^(.*?)\s+(\d{1,3})(?:\s*[-–—]\s*\d{1,3})?$")

_TR_FOLD = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")


def fold(s: str) -> str:
    """Uppercase that survives the Turkish dotted/dotless i."""
    return s.translate(_TR_FOLD).upper()


def sec_no(token: str) -> int | None:
    if token in _EN_ORD:
        return _EN_ORD.index(token) + 1
    if token in _TR_ORD:
        return _TR_ORD.index(token) + 1
    if token in ROMAN:
        return ROMAN.index(token) + 1
    return None


def document_contents(lines) -> list[tuple] | None:
    """[(pdf_page, section_no, section_name, item_no, item_title)], or None.

    Returns None rather than a guess when the filing's own numbers do not
    corroborate each other — the contents must place its items on folios that
    exist and run forward.
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
    # page off, which is exactly the silent, plausible-looking error this
    # reading exists to expose.
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
        m = SEC_EN.match(fold(t)) or SEC_TR.match(fold(t))
        if m:
            n = sec_no(m.group(1))
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
            pending = (cur, ROMAN.index(mi.group(1)) + 1, title[:90])
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


def body_section_starts(lines) -> dict[int, tuple[int, str]] | None:
    """{section_no: (start_page, declared_title)} from the body's own banners.

    The fallback reading for filings whose contents page does not validate.
    A page printing two or more DISTINCT section banners is the contents
    itself, not a section start, and is excluded; the title is the first
    non-empty line after the banner on its page. Refused (None) when the
    surviving starts do not run forward — a wrong section label is worse than
    none, exactly the contents rule.
    """
    hits: list[tuple[int, int, int, str]] = []     # (page, line_order, no, txt)
    texts_after: dict[tuple[int, int], str] = {}
    prev: tuple[int, int, int] | None = None
    for pg, lo, txt, *_rest in lines:
        t = (txt or "").strip()
        if prev is not None and t:
            key = (prev[0], prev[1])
            if key not in texts_after and prev[0] == pg:
                texts_after[key] = t[:80]
            prev = None
        m = SEC_EN.match(fold(t)) or SEC_TR.match(fold(t))
        if m:
            n = sec_no(m.group(1))
            if n is not None:
                hits.append((pg, lo, n, t))
                # ISCTR prints the title ON the banner line — "SECTION ONE:
                # GENERAL INFORMATION ABOUT THE PARENT BANK". Reading the NEXT
                # line as the title there hands `role_from_title` the first
                # ITEM instead ("I. Explanations on …"), whose "explanation"
                # keyword relabels §1 as notes — the one mine-wrong case in
                # the prose cross-check tail. `fold` is length-preserving over
                # this corpus, so the match end indexes the original text.
                inline = t[m.end():].strip(" \t:.·—–-").strip()
                if inline:
                    texts_after[(pg, lo)] = inline[:80]
                else:
                    prev = (pg, lo, n)
    per_page: dict[int, set[int]] = defaultdict(set)
    for pg, _lo, n, _t in hits:
        per_page[pg].add(n)
    starts: dict[int, tuple[int, str]] = {}
    for pg, lo, n, _t in hits:
        if len(per_page[pg]) >= 2:
            continue                     # a contents page lists many sections
        if n not in starts:
            starts[n] = (pg, texts_after.get((pg, lo), ""))
    if len(starts) < 3:
        return None
    ordered = [starts[n][0] for n in sorted(starts)]
    if any(a > b for a, b in zip(ordered, ordered[1:])):
        return None
    return starts
