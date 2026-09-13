"""Selected LCR totals from explicit TR/EN four-column PDF tables.

Geometry assigns currency/weighting: removing blank slots and taking the last
two tokens is unsafe. Unrecognized layouts remain absent. Recognized tables
retain missing/ambiguous rows as failed evidence, never as invented zeros.
"""
from __future__ import annotations

import json
import re

from .extractor import parse_num
from .liquidity_coverage import heading_period

ROLES = ("hqla", "cash_outflows", "cash_inflows", "net_cash_outflows")
FIELDS = tuple(f"lcr_{role}_{currency}" for role in ROLES for currency in ("total", "fc"))
_LABELS = {
    "hqla": r"(?:total\s+hqla|toplam\s+yklv\s+stoku)",
    "cash_outflows": r"(?:total\s+cash\s+outflows|toplam\s+nakit\s+çıkışları)",
    "cash_inflows": r"(?:total\s+cash\s+inflows|toplam\s+nakit\s+girişleri)",
    "net_cash_outflows": r"(?:total\s+net\s+cash\s+outflows|toplam\s+net\s+nakit\s+çıkışları)",
}
_NIL = {"-", "–", "—", "--"}
_AMOUNT = re.compile(r"^(?:\(?-?\d+(?:[.,]\d{3})*\)?|[-–—]+)$")
_FOLD = str.maketrans("İI", "iı")


def component_role(label: str) -> str | None:
    label = re.sub(r"^[\d.\s]+", "", label).translate(_FOLD).lower().strip()
    return next((role for role, pattern in _LABELS.items()
                 if re.fullmatch(pattern.replace("ı", "i"), label.replace("ı", "i"))), None)


def amount_value(raw: str | None) -> float | None:
    if raw is None or raw in _NIL:
        return None
    if not _AMOUNT.fullmatch(raw):
        raise ValueError("unsupported monetary literal")
    return parse_num(raw)


def _lines(words: list) -> list[list]:
    lines: list[list] = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        if not lines or abs((word[1] + word[3]) / 2 -
                            (lines[-1][0][1] + lines[-1][0][3]) / 2) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda w: w[0]) for line in lines]


def scan_component_page(words: list, page_number: int) -> list[dict]:
    """Input is untouched PyMuPDF word tuples, including their bounding boxes."""
    lines = _lines(words)
    readings = []
    for index, header in enumerate(lines):
        currencies = [w for w in header if w[4] in ("TP+YP", "YP", "TL+FC", "FC")]
        if [w[4] for w in currencies] not in (["TP+YP", "YP", "TP+YP", "YP"],
                                             ["TL+FC", "FC", "TL+FC", "FC"]):
            continue
        preceding = lines[max(0, index - 5):index + 1]
        heading = next((" ".join(w[4] for w in line) for line in reversed(preceding)
                        if heading_period(" ".join(w[4] for w in line))), None)
        if not heading:
            continue
        column_heading = "\n".join(" ".join(w[4] for w in line) for line in preceding)
        folded = column_heading.translate(_FOLD).lower()
        if not (("unweighted" in folded and "weighted" in folded)
                or ("uygulanmamış" in folded and "uygulanmış" in folded)):
            continue
        # Column right edges, unlike token order, survive blank unweighted or
        # currency cells. The allowance accommodates centered English headers.
        edges = [w[2] for w in currencies]
        gap = min(b - a for a, b in zip(edges, edges[1:]))
        tolerance = gap * 0.45
        table_lines = []
        for line in lines[index + 1:]:
            text = " ".join(w[4] for w in line).translate(_FOLD).lower()
            if re.search(r"(?:liquidity coverage ratio|likidite karşılama oranı)\s*\(%\)", text):
                break
            table_lines.append(line)
        else:
            continue  # no LCR table boundary; this could be another disclosure
        source_rows: dict[str, list[dict]] = {role: [] for role in ROLES}
        for line in table_lines:
            label = " ".join(w[4] for w in line if w[2] < edges[0] - tolerance)
            role = component_role(label)
            if not role:
                continue
            slots: list[list] = [[], [], [], []]
            ambiguous = False
            for word in line:
                if word[2] < edges[0] - tolerance:
                    continue
                matches = [c for c, edge in enumerate(edges) if abs(word[2] - edge) <= tolerance]
                if len(matches) != 1 or not _AMOUNT.fullmatch(word[4]):
                    ambiguous = True
                else:
                    slots[matches[0]].append(word)
            ambiguous |= any(len(slot) > 1 for slot in slots)
            source_rows[role].append(dict(
                raw_label=label, raw_snippet=" ".join(w[4] for w in line),
                cells=[dict(raw_value=slot[0][4], bbox=list(slot[0][:4])) if len(slot) == 1
                       else dict(raw_value=None, bbox=None) for slot in slots],
                status="ambiguous_columns" if ambiguous else "read"))
        if not any(source_rows.values()):
            continue
        for role in ROLES:
            for column, currency in ((2, "total"), (3, "fc")):
                for row in source_rows[role] or [dict(status="missing_row", cells=[{}] * 4)]:
                    readings.append(dict(field=f"lcr_{role}_{currency}", status=row["status"], source=dict(
                        source_page=page_number, period_type=heading_period(heading),
                        period_heading=heading, period_heading_page=page_number,
                        column_heading=column_heading, column_index=column,
                        column_right_edges=edges, column_tolerance=tolerance,
                        basis="capped" if role in ("hqla", "net_cash_outflows") else "weighted",
                        raw_label=row.get("raw_label", ""), raw_snippet=row.get("raw_snippet", ""),
                        **row["cells"][column])))
    return readings


def resolve_components(readings: list[dict]) -> dict[str, dict]:
    result = {}
    for period in ("current", "prior"):
        evidence, values = {}, {}
        for field in FIELDS:
            selected = [r for r in readings if r["field"] == field and r["source"]["period_type"] == period]
            if not selected:
                continue
            sources = [r["source"] for r in selected]
            amounts = {amount_value(s.get("raw_value")) for s in sources}
            status = (next((r["status"] for r in selected if r["status"] != "read"), "read")
                      if len(amounts) == 1 else "conflicting_rows")
            values[field] = next(iter(amounts)) if status == "read" else None
            evidence[field] = dict(status=status, sources=sources)
        if evidence:
            values["lcr_components_source_json"] = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            result[period] = values
    return result


def extract_lcr_components(pdf_path: str, start: int, stop: int) -> dict[str, dict]:
    import fitz
    with fitz.open(pdf_path) as doc:
        return resolve_components([reading for i in range(start, stop)
            for reading in scan_component_page(doc[i].get_text("words"), i + 1)])


def with_component_units(evidence: str | None, source_unit: str, factor: int) -> str | None:
    if evidence is None:
        return None
    data = json.loads(evidence)
    for item in data.values():
        for source in item["sources"]:
            source.update(source_unit=source_unit, unit_scale=factor, stored_unit="bin")
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
