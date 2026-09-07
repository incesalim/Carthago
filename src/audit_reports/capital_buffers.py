"""Source-disclosed capital-buffer percentages, following the own-funds table.

This extends the existing capital summary; it is not full-table coverage.
Literal cells and page/line evidence are retained beside each percentage.
"""
from __future__ import annotations

import json
import re

BUFFER_FIELDS = (
    "total_buffer_requirement_ratio",
    "capital_conservation_buffer_ratio",
    "countercyclical_buffer_ratio",
    "systemic_buffer_ratio",
    "cet1_available_buffer_ratio",
)
_FOLD = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")
_PREFIX = r"^(?:[ABC][.)]\s*)?"
_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"^TOPLAM ILAVE CEKIRDEK SERMAYE GEREKSINIMI ORANI\b|"
    r"^TOTAL ADDITIONAL (?:COMMON EQUITY TIER [I1]|CET1) CAPITAL (?:REQUIREMENT|RATIO)\b",
    _PREFIX + r"(?:SERMAYE KORUMA TAMPONU|CAPITAL CONSERVATION BUFFER)\b",
    _PREFIX + r"(?:(?:BANKAYA OZGU )?DONGUSEL SERMAYE TAMPONU|"
    r"(?:BANK[ -]SPECIFIC )?COUNTER[ -]?CYCLICAL (?:CAPITAL )?BUFFER)\b",
    _PREFIX + r"(?:SISTEMIK ONEMLI BANKA TAMPONU|SYSTEMICALLY IMPORTANT BANK BUFFER)\b",
    r"^SERMAYE KORUMA VE DONGUSEL SERMAYE TAMPONLARINA ILISKIN YONETMELIGIN 4\b|"
    r"^(?:THE )?RATIO OF ADDITIONAL COMMON EQUITY TIER [I1] CAPITAL WHICH WILL BE\b",
))
_HEADING = re.compile(r"^(?:TAMPONLAR|(?:CAPITAL )?BUFFERS)$")
_END = re.compile(r"^UYGULANACAK INDIRIM|^AMOUNTS BELOW|^AMOUNTS SUBJECT TO|"
                  r"^KATKI SERMAYE HESAPLAMASINDA|^APPLICABLE CAPS")


def parse_buffer_value(cell: str | None) -> float | None:
    from .capital_adequacy import _parse_ratio

    if cell is None:
        return None
    value = _parse_ratio(cell)
    if value is not None and cell.strip().startswith('(') and cell.strip().endswith(')'):
        return -abs(value)
    return value


def parse_buffers(lines: list[tuple[int, str]]) -> tuple[dict, dict]:
    """Parse one buffer block from the already located capital section.

    Require a buffer heading or the aggregate requirement as the opener. Only
    explicitly named rows qualify; a regulation mentioned inside another row
    cannot become the countercyclical requirement. Ambiguous duplicate values
    remain NULL with their conflicting evidence, rather than first/last wins.
    """
    from .capital_adequacy import _NUM_TOKEN

    def literal_values(text: str) -> list[str]:
        cells = []
        for token in reversed(text.split()):
            if token in ("-", "–", "—", "--", "---") or _NUM_TOKEN.fullmatch(token):
                cells.append(token)
            else:
                break
        # A detached digit cannot be distinguished from a third value here.
        # Keep only complete literal columns, without the amount-lane repair
        # that would concatenate legitimate small ratios such as `0 0.01`.
        return list(reversed(cells)) if len(cells) in (1, 2) else []

    def fold(text: str) -> str:
        return text.translate(_FOLD).upper().strip()

    records: dict[str, list[dict]] = {}
    active = False
    for index, (page, text) in enumerate(lines):
        label = fold(text)
        if _HEADING.fullmatch(label) or _PATTERNS[0].match(label):
            active = True
        if not active:
            continue
        if _END.match(label):
            break
        field = next((name for name, rx in zip(BUFFER_FIELDS, _PATTERNS)
                      if rx.match(label)), None)
        if field is None:
            continue
        source = text.strip()
        tokens = literal_values(source)
        # Long regulation-qualified labels wrap over three or four lines.
        # Never borrow a subsequent disclosure's values or cross a page.
        for next_page, continuation in lines[index + 1:index + 5]:
            if tokens or next_page != page or _END.match(fold(continuation)) or any(
                    rx.match(fold(continuation)) for rx in _PATTERNS):
                break
            source += " " + continuation.strip()
            tokens = literal_values(source)
        if not tokens:
            continue
        records.setdefault(field, []).append({
            "source_page": page, "raw_snippet": source, "raw_values": tokens,
        })

    output = []
    for column in (0, 1):
        values, evidence = {}, {}
        for field, sources in records.items():
            if not any(len(s["raw_values"]) > column for s in sources):
                continue
            cells = [s["raw_values"][column] if len(s["raw_values"]) > column else None
                     for s in sources]
            parsed = {parse_buffer_value(cell) for cell in cells}
            values[field] = next(iter(parsed)) if len(parsed) == 1 else None
            evidence[field] = {
                "status": "read" if len(parsed) == 1 else "conflicting_rows",
                "sources": [{"source_page": s["source_page"],
                             "raw_snippet": s["raw_snippet"], "raw_value": cell}
                            for s, cell in zip(sources, cells)],
            }
        if evidence:
            values["buffer_source_json"] = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        output.append(values)
    return output[0], output[1]
