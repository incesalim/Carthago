"""Physical boundaries and displaced printed nil cells in NPL disclosures.

No missing value is synthesized. Nil fragments remain individually addressed
to their original source line and column; uncertain assignments are left alone.
"""
from __future__ import annotations

import re
from statistics import median


def is_category_other(lines: list[str], index: int) -> bool:
    """Recognize a fourth category only when its three printed sums tie.

    An Other row following a complete three-category sale breakdown is a
    separate movement. Category labels alone cannot establish that relationship.
    """
    from .extractor import parse_amount
    from .npl_movement import _THREE_NUMS_TAIL, _match_row_label

    category = re.compile(
        r'^(?:corporate and commercial loans|retail loans|consumer loans|credit cards|'
        r'kurumsal (?:ve )?ticari krediler|bireysel krediler|kredi kartları)\b', re.I)

    def amounts(line):
        tail = _THREE_NUMS_TAIL.search(line)
        return [parse_amount(tail[f'n{g}']) for g in (3, 4, 5)] if tail else None

    other = amounts(lines[index])
    if other is None:
        return False
    children = []
    parent = None
    for line in reversed(lines[:index]):
        if not line.strip():
            continue
        values = amounts(line)
        if values is None:
            break
        if category.match(line.strip()) and len(children) < 3:
            children.append(values)
            continue
        if _match_row_label(line) not in {None, 'other_movement'}:
            parent = values
        break
    if not children or parent is None:
        return False
    sums = [sum(row[c] for row in children) for c in range(3)]
    if all(abs(sums[c] - abs(parent[c])) <= 1.5 for c in range(3)):
        return False
    return all(abs(sums[c] + other[c] - abs(parent[c])) <= 1.5 for c in range(3))


def star_notes(pages: dict[int, list[str]]) -> list[dict]:
    """Retain printed star-note paragraphs inside the bounded disclosure."""
    selected = disclosure_lines(pages)
    if selected is None:
        return []
    out, active = [], None
    period = None
    for page, lines in sorted(pages.items()):
        for order, text in enumerate(lines, 1):
            if (page, order) not in selected:
                continue
            caption = re.match(r'^(current|prior|cari|önceki)\s+(?:period|dönem)\b', text, re.I)
            if caption:
                period = 'prior' if caption[1].lower() in {'prior', 'önceki'} else 'current'
            marker = re.match(r'^\s*(\(\*+\))\s+\S', text)
            if marker:
                if active:
                    active['boundary'] = 'next_note'
                active = {'id': f'npl-note:p{page}:l{order}', 'marker': marker[1],
                          'period_context': period, 'source_lines': [], 'boundary': 'disclosure_end'}
                out.append(active)
            if active:
                # A page number is furniture. At a page transition an unreviewed
                # running header cannot silently become part of the paragraph.
                if re.fullmatch(r'\d+', text.strip()):
                    continue
                if active['source_lines'] and active['source_lines'][-1]['source_page'] != page:
                    active['boundary'] = 'page_continuation_unverified'
                    active = None
                    continue
                active['source_lines'].append({'source_page': page, 'line_order': order, 'text': text})
    for note in out:
        note['text'] = '\n'.join(row['text'] for row in note['source_lines'])
    return out


def row_note_links(text: str, period: str, row_key: str | None, notes: list[dict]) -> list[dict]:
    """Link literal markers without resolving cross-period renumbering by guess."""
    from .npl_movement import _THREE_NUMS_TAIL
    from .extractor import parse_amount

    links = []
    for marker in dict.fromkeys(re.findall(r'\(\*+\)', text)):
        matches = [n for n in notes if n['marker'] == marker]
        status = ('unresolved' if not matches else 'resolved' if len(matches) == 1
                  and matches[0]['period_context'] == period
                  and matches[0]['boundary'] != 'page_continuation_unverified' else 'ambiguous')
        links.append({'marker': marker, 'status': status, 'method': 'printed_star_marker',
                      'targets': matches})
    # GARAN current Other uses a different printed marker from the following
    # comparative's note sequence. Keep that literal mismatch and a separately
    # labelled, amount-supported candidate; never replace the printed marker.
    if row_key == 'other_movement' and (tail := _THREE_NUMS_TAIL.search(text)):
        amounts = {abs(parse_amount(tail[f'n{g}'])) for g in (3, 4, 5)} - {0}
        for note in notes:
            if not re.search(r'reclass\w*\s+to\s+non[- ]defaulted', note['text'], re.I):
                continue
            disclosed = {float(t.replace(',', '')) for t in re.findall(r'\b\d{1,3}(?:,\d{3})+\b', note['text'])}
            if amounts and amounts <= disclosed and not any(note in link['targets'] and link['status'] == 'resolved' for link in links):
                links.append({'marker': note['marker'], 'status': 'candidate',
                              'method': 'source_amount_and_reclassification_text', 'targets': [note]})
    return links


def disclosure_lines(pages: dict[int, list[str]]) -> set[tuple[int, int]] | None:
    from .npl_movement import _HEADING_RX

    following = re.compile(
        r"non[- ]performing loans in foreign currenc|"
        r"gross and net non[- ]performing loans as per customer|"
        r"yabancı para.*donuk alacak|donuk alacak.*yabancı para", re.I)
    selected: set[tuple[int, int]] = set()
    active = False
    previous = None
    for page, lines in sorted(pages.items()):
        if active and previous is not None and page != previous + 1:
            return None
        for order, line in enumerate(lines, 1):
            if _HEADING_RX.search(line):
                active = True
            if active and following.search(line):
                return selected
            if active:
                selected.add((page, order))
        previous = page
    return None


def recover_nil_fragments(lines: list[list[tuple[float, float, str]]]):
    """Join only printed, column-aligned dashes around one incomplete row.

    GARAN prints two vertically displaced dash glyphs in a single nil cell.
    An orphan must have exactly one adjacent incomplete-row candidate, and all
    complete balance rows must agree on the three numeric column positions.
    """
    from .npl_movement import _GROUPS_RX, _NUM_TOKEN, _match_row_label

    text = [" ".join(t for _, _, t in row) for row in lines]
    headers = [i for i, value in enumerate(text) if _GROUPS_RX.search(value)]
    corrected = [list(row) for row in lines]
    fragments: dict[int, list[list[dict]]] = {}
    numeric = re.compile(_NUM_TOKEN)
    dash = re.compile(r"[-–—]+")
    for index, start in enumerate(headers):
        end = headers[index + 1] if index + 1 < len(headers) else len(lines)
        anchors = [tuple(token[1] for token in lines[i][-3:])
                   for i in range(start + 1, end)
                   if _match_row_label(text[i]) in {"opening_balance", "closing_balance", "provision", "net_balance"}
                   and len(lines[i]) > 3 and all(numeric.fullmatch(t[2]) for t in lines[i][-3:])]
        if len(anchors) < 3:
            continue
        columns = [median(row[c] for row in anchors) for c in range(3)]
        if (min(columns[c + 1] - columns[c] for c in (0, 1)) < 20
                or any(abs(row[c] - columns[c]) > 4 for row in anchors for c in range(3))):
            continue
        band = columns[0] - (columns[1] - columns[0]) / 2
        orphan = {i for i in range(start + 1, end)
                  if lines[i] and all(dash.fullmatch(t[2]) and t[0] > band for t in lines[i])}
        incomplete = {}
        for i in range(start + 1, end):
            cells = [(n, t) for n, t in enumerate(lines[i]) if t[0] > band and numeric.fullmatch(t[2])]
            if len(cells) != 2 or not any(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", t[2]) for t in lines[i]):
                continue
            assigned = {}
            for n, token in cells:
                c = min(range(3), key=lambda c: abs(token[1] - columns[c]))
                if c in assigned or abs(token[1] - columns[c]) > 4:
                    break
                assigned[c] = [(i, n, token)]
            else:
                incomplete[i] = assigned
        claims: dict[int, list[tuple[int, int, tuple]]] = {}
        for i in orphan:
            neighbors = []
            for direction in (-1, 1):
                j = i + direction
                while j in orphan:
                    j += direction
                if j in incomplete and abs(j - i) <= 2:
                    missing = next(c for c in range(3) if c not in incomplete[j])
                    if all(abs(t[1] - columns[missing]) <= 4 for t in lines[i]):
                        neighbors.append(j)
            if len(neighbors) == 1:
                claims.setdefault(neighbors[0], []).extend((i, n, t) for n, t in enumerate(lines[i]))
        for i, extra in claims.items():
            assigned = dict(incomplete[i])
            missing = next(c for c in range(3) if c not in assigned)
            assigned[missing] = sorted(extra)
            fragments[i] = [[{"line_order": j + 1, "token_order": n,
                              "text": t[2], "x0": t[0], "x1": t[1]}
                             for j, n, t in assigned[c]] for c in range(3)]
            corrected[i] = [t for t in lines[i] if t[0] <= band] + [
                (min(t[0] for _, _, t in assigned[c]), max(t[1] for _, _, t in assigned[c]),
                 "".join(t[2] for _, _, t in assigned[c])) for c in range(3)]
            for j, _, _ in extra:
                corrected[j] = []
    return corrected, fragments
