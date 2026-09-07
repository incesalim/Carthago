"""Source-bound LCR observations; period headings outrank occurrence order."""
from __future__ import annotations

import json
import re

from .capital_adequacy import _parse_ratio
from .extractor import parse_num

_FOLD = str.maketrans("İI", "iı")
_RN = r"(?:\d+\.?\s*)?"
_LABEL = re.compile(rf"^{_RN}(?:liquidity\s*coverage\s*ratio|likidite\s+kar[şs]ılama\s+oranı)\s*\(\s*%\s*\)", re.I)
_CURRENT = re.compile(r"^(?:cari\s+dönem|current\s+period)\b", re.I)
_PRIOR = re.compile(r"^(?:önceki\s+dönem|geçmiş\s+dönem|prior\s+period|previous\s+period)\b", re.I)
_HQLA = re.compile(rf"^{_RN}(?:total\s*hqla|total\s*high[\s-]*quality\s*liquid\s*assets|toplam\s+yklv\s+stoku)\b", re.I)
_OUTFLOW = re.compile(rf"^{_RN}(?:total\s*net\s*cash\s*outflows|toplam\s+net\s+nakit\s+çıkışları)\b", re.I)
_TOKEN = re.compile(r"^(?:[-—–]+|%?\(?-?\d[\d.,]*\)?%?)$")
_DATED_RANGE = re.compile(r"^(TP\+YP|TL\+FC|YP|FC)\s+(%?\d[\d.,]*%?)\s+\d{2}[./]\d{2}[./]\d{4}\s+(%?\d[\d.,]*%?)\s+\d{2}[./]\d{2}[./]\d{4}$", re.I)


def heading_period(raw: str) -> str | None:
    line = raw.strip().translate(_FOLD).lower()
    return "prior" if _PRIOR.match(line) else "current" if _CURRENT.match(line) else None


def ratio_value(raw: str, numerator: str = "", denominator: str = "") -> float | None:
    """Read a literal percentage; single ambiguous grouping needs components.

    Repeated complete groups (142.085.400) are unambiguous integers. A lone
    3,768 remains decimal unless separately printed HQLA/outflow scale supports
    3768. Never substitute a component-derived ratio for the printed ratio.
    """
    token = raw.strip().strip("%")
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("()")
    if re.fullmatch(r"\d{1,3}([.,])\d{3}(?:\1\d{3})+", token):
        result = float(token.replace(".", "").replace(",", ""))
    else:
        result = _parse_ratio(token)
        if result and re.fullmatch(r"\d{1,3}[,.]\d{3}", token):
            num, den = parse_num(numerator), parse_num(denominator)
            grouped = float(token.replace(",", "").replace(".", ""))
            if num and den and den > 0:
                implied = num / den * 100
                if (abs(grouped - implied) <= abs(implied) * 0.05
                        and abs(result - implied) > abs(implied) * 0.5):
                    result = grouped
    return -result if negative and result is not None else result


def _tail(line: str) -> list[str]:
    tokens: list[str] = []
    for token in reversed(line.split()):
        if not _TOKEN.fullmatch(token):
            break
        tokens.append(token)
    return list(reversed(tokens))


def scan_lcr(pages: list[tuple[int, list[str]]]) -> list[dict]:
    observations = []
    period, heading, heading_page = None, "", None
    hqla, outflows = [], []
    ranges: dict[str, dict] = {}
    range_layout = None
    for page, lines in pages:
        for index, raw in enumerate(lines):
            line = raw.strip().translate(_FOLD).lower()
            hint = heading_period(raw)
            if hint:
                period = hint
                heading, heading_page = raw, page
                hqla, outflows = [], []
            if period and "en yüksek" in line and "en düşük" in line:
                range_layout = line.index("en yüksek") < line.index("en düşük")
                continue
            if range_layout is not None:
                match = _DATED_RANGE.fullmatch(raw.strip())
                if match and period:
                    currency, first, second = match.groups()
                    field = "lcr_total" if "+" in currency else "lcr_fc"
                    low, high = (second, first) if range_layout else (first, second)
                    ranges.setdefault(period, {})[field] = dict(minimum=low, maximum=high,
                        source_page=page, raw_snippet=raw, period_type=period)
                    continue
                if line:
                    range_layout = None
            anchor = _LABEL.match(line)
            component = _HQLA.match(line) or _OUTFLOW.match(line)
            if not (anchor or component):
                continue
            tokens = _tail(raw)
            snippet = raw
            # A displaced value band may immediately follow its label. Require
            # an entirely numeric band on the SAME page; do not skip another row.
            if not tokens and index + 1 < len(lines):
                following = lines[index + 1].strip().split()
                if len(following) in (2, 4) and all(_TOKEN.fullmatch(t) for t in following):
                    tokens = following
                    snippet += "\n" + lines[index + 1]
            if len(tokens) not in (1, 2, 4):
                continue
            if len(tokens) == 4:
                # LCR's first two slots are unweighted placeholders. Four real
                # ratio values have ambiguous semantics and must not be sliced.
                if anchor and any(t not in ("-", "—", "–", "--") for t in tokens[:2]):
                    continue
                tokens = tokens[-2:]
            if _HQLA.match(line):
                hqla = tokens
            elif _OUTFLOW.match(line):
                outflows = tokens
            else:
                values = [ratio_value(t, hqla[i] if i < len(hqla) else "",
                                      outflows[i] if i < len(outflows) else "")
                          for i, t in enumerate(tokens)]
                observations.append(dict(period_type=period, source_page=page,
                    period_heading=heading, period_heading_page=heading_page,
                    raw_snippet=snippet, raw_values=tokens, values=values,
                    hqla=hqla, outflows=outflows, reported_ranges=dict(ranges.get(period, {}))))
                # No components may be borrowed by the following ratio/table.
                hqla, outflows = [], []
    return observations


def resolve_lcr(observations: list[dict]) -> dict[str, dict]:
    """Keep explicit period evidence; only the first unheaded row defaults current.

    Later unheaded rows never become prior merely because they came second.
    Conflicting explicitly headed observations abstain and retain both sources.
    """
    result: dict[str, dict] = {}
    for period in ("current", "prior"):
        selected = [o for o in observations if o["period_type"] == period]
        if not selected and period == "current" and observations and observations[0]["period_type"] is None:
            selected = observations[:1]
        if not selected:
            continue
        values, evidence = {}, {}
        for col, field in enumerate(("lcr_total", "lcr_fc")):
            sources = [{"source_page": o["source_page"], "raw_snippet": o["raw_snippet"],
                        "raw_value": o["raw_values"][col],
                        "period_type": period,
                        "period_assignment": "heading" if o["period_type"] else "first_unheaded_row",
                        "period_heading": o["period_heading"],
                        "period_heading_page": o["period_heading_page"],
                        "reported_range": o["reported_ranges"].get(field),
                        "hqla": o["hqla"][col] if col < len(o["hqla"]) else "",
                        "outflows": o["outflows"][col] if col < len(o["outflows"]) else ""}
                       for o in selected if col < len(o["raw_values"])]
            if not sources:
                continue
            readings = {ratio_value(s["raw_value"], s["hqla"], s["outflows"]) for s in sources}
            conflict = len(readings) != 1
            values[field] = None if conflict else next(iter(readings))
            evidence[field] = {"status": "conflicting_rows" if conflict else "read", "sources": sources}
        values["lcr_source_json"] = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        result[period] = values
    return result
