"""Lossless source evidence for audit tables with intentionally narrow schemas.

The analytical tables remain stable and typed.  This module stores every text
line from the source pages that contain the eight target disclosures, marks the
numeric rows the current extractor knows how to map, and writes one compact
manifest per partition/lane.  Unknown numeric rows therefore remain inspectable
instead of disappearing, and the manifest gives validators/alerts a cheap D1
contract without pushing the high-volume raw ledger.

PDF access is PyMuPDF-only, matching the audit pipeline's single-engine rule.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable


TARGET_LANES: tuple[str, ...] = (
    "equity_change",
    "loans_by_sector",
    "npl_movement",
    "credit_quality",
    "capital",
    "liquidity",
    "fx_position",
    "repricing",
)

NEAR_FULL_LANES = frozenset({
    "equity_change", "loans_by_sector", "npl_movement",
})

_TABLE_BY_LANE = {
    "equity_change": "bank_audit_equity_change",
    "loans_by_sector": "bank_audit_loans_by_sector",
    "npl_movement": "bank_audit_npl_movement",
    "credit_quality": "bank_audit_credit_quality",
    "capital": "bank_audit_capital",
    "liquidity": "bank_audit_liquidity",
    "fx_position": "bank_audit_fx_position",
    "repricing": "bank_audit_repricing",
}


@dataclass(frozen=True)
class _LaneConfig:
    anchor_groups: tuple[tuple[str, ...], ...]
    min_value_tokens: int
    pages_after: int = 0
    section_range: bool = False


# Each page must match at least one phrase from EVERY group.  Matching is over a
# compact Turkish-aware ASCII fold, so spacing damage and dotted/dotless-I do not
# change the result.  These anchors are deliberately independent of the parser:
# they can find a disclosure even when the normalized extractor returned no row.
_CONFIG: dict[str, _LaneConfig] = {
    "equity_change": _LaneConfig((
        ("ozkaynak degisim", "ozkaynaklarda muhasebelestirilen",
         "changes in equity", "changes in shareholders equity"),
    ), min_value_tokens=5, pages_after=1),
    "loans_by_sector": _LaneConfig((
        ("sektor", "sector"),
        ("ikinci asama", "stage 2", "yakin izlemedeki"),
        ("ucuncu asama", "stage 3", "takipteki"),
    ), min_value_tokens=3, pages_after=1),
    "npl_movement": _LaneConfig((
        ("donuk alacak", "non performing loan", "nonperforming loan"),
        ("donem sonu", "closing balance", "period end", "collections", "tahsilat"),
    ), min_value_tokens=3, pages_after=1),
    "credit_quality": _LaneConfig((
        ("birinci asama", "stage 1"),
        ("ikinci asama", "stage 2"),
        ("ucuncu asama", "stage 3"),
    ), min_value_tokens=3),
    "capital": _LaneConfig((
        ("sermaye yeterliligi", "capital adequacy", "components of total capital"),
        ("cekirdek sermaye", "common equity tier", "core tier"),
    ), min_value_tokens=1, pages_after=7, section_range=True),
    "liquidity": _LaneConfig((
        ("likidite karsilama", "liquidity coverage", "net stable funding",
         "net istikrarli fonlama", "kaldirac orani", "leverage ratio",
         "yuksek kaliteli likit", "high quality liquid"),
    ), min_value_tokens=1, pages_after=1),
    "fx_position": _LaneConfig((
        ("yabanci para", "foreign currency", "currency risk"),
        ("net pozisyon", "net position", "net bilan", "net balance"),
    ), min_value_tokens=2, pages_after=3, section_range=True),
    "repricing": _LaneConfig((
        ("faizsiz", "faiz getirmeyen", "non interest", "interest free"),
        ("toplam varlik", "total assets"),
        ("pozisyon", "position", "gap"),
    ), min_value_tokens=3, pages_after=5, section_range=True),
}


_STATIC_MAPPINGS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "npl_movement": (
        ("opening_balance", ("donem basi bakiyesi", "opening balance", "beginning balance")),
        ("additions", ("donem icinde intikal", "additions during", "new non performing")),
        ("transfers_in", ("diger donuk alacak hesaplarindan giris", "transfers from other")),
        ("transfers_out", ("diger donuk alacak hesaplarina cikis", "transfers to other")),
        ("collections", ("tahsilat", "collections")),
        ("write_offs", ("aktiften silinen", "write off", "written off")),
        ("sold", ("satilan", "sold")),
        ("fx_diff", ("kur fark", "foreign exchange difference", "fx difference")),
        ("closing_balance", ("donem sonu bakiyesi", "closing balance", "period end balance")),
        ("provision", ("karsilik", "provision")),
        ("net_balance", ("net bakiye", "net balance")),
    ),
    "credit_quality": (
        ("ending_balance", ("donem sonu bakiyesi", "closing balance", "period end balance",
                            "balance at end of period")),
    ),
    "capital": (
        ("cet1_capital", ("cekirdek sermaye", "common equity tier 1", "core tier 1 capital")),
        ("additional_tier1_capital", ("ilave ana sermaye", "additional tier 1 capital")),
        ("tier1_capital", ("ana sermaye", "tier 1 capital")),
        ("tier2_capital", ("katki sermaye", "tier 2 capital")),
        ("total_capital", ("toplam ozkaynak", "total own funds", "total capital")),
        ("total_rwa", ("risk agirlikli tutar", "risk weighted assets")),
        ("cet1_ratio", ("cekirdek sermaye yeterliligi orani", "common equity tier 1 ratio")),
        ("tier1_ratio", ("ana sermaye yeterliligi orani", "tier 1 capital ratio")),
        ("capital_adequacy_ratio", ("sermaye yeterliligi standart orani",
                                    "capital adequacy standard ratio",
                                    "capital adequacy ratio")),
    ),
    "liquidity": (
        ("lcr", ("likidite karsilama orani", "liquidity coverage ratio")),
        ("nsfr", ("net istikrarli fonlama orani", "net stable funding ratio",
                  "net stable funding rate")),
        ("leverage_ratio", ("kaldirac orani", "leverage ratio")),
    ),
    "fx_position": (
        ("on_bs_assets", ("toplam varliklar", "total assets")),
        ("on_bs_liab", ("toplam yukumlulukler", "total liabilities")),
        ("net_on_balance", ("net bilanco pozisyonu", "net balance sheet position")),
        ("net_off_balance", ("net nazim hesap pozisyonu", "net off balance sheet position")),
        ("off_bs_receivable", ("turev finansal araclar alacak", "derivative financial instruments receivable")),
        ("off_bs_payable", ("turev finansal araclar borc", "derivative financial instruments payable")),
        ("net_position", ("yabanci para net genel pozisyon", "foreign currency net position",
                          "net general position")),
    ),
    "repricing": (
        ("rate_sensitive_assets", ("toplam varliklar", "total assets")),
        ("rate_sensitive_liab", ("toplam yukumlulukler", "total liabilities")),
        ("gap", ("bilanco pozisyonu", "balance sheet position", "toplam pozisyon",
                 "total position", "repricing gap")),
    ),
}


_TR_TRANSLATION = str.maketrans({
    "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
    "ç": "c", "Ç": "C", "ö": "o", "Ö": "O", "ü": "u", "Ü": "U",
})
_SPACE_RX = re.compile(r"\s+")
_VALUE_RX = re.compile(
    r"(?<![\w])(?:%?\(?-?\d(?:[\d.,]*\d)?%?\)?|[-–—]+)(?![\w])"
)


@lru_cache(maxsize=1)
def _npl_parser_mappings() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Use the production parser's complete, longest-first NPL taxonomy.

    Keeping a second abbreviated label list here would turn known legacy
    wording into false ``capture_unmapped_rows`` failures.  The local import
    avoids adding parser dependencies to module import/startup for lanes that
    do not need it.
    """
    from .npl_movement import _ROW_LABELS_SORTED

    return tuple((key, (phrase,)) for phrase, key in _ROW_LABELS_SORTED)


def _fold(value: str) -> str:
    translated = value.translate(_TR_TRANSLATION)
    ascii_text = unicodedata.normalize("NFKD", translated).encode(
        "ascii", "ignore").decode("ascii")
    return _SPACE_RX.sub(" ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower()).strip()


def _compact(value: str) -> str:
    return _fold(value).replace(" ", "")


def _digest(parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8", "replace"))
        h.update(b"\n")
    return h.hexdigest()


def _shape(value: str) -> str:
    return _SPACE_RX.sub(" ", _VALUE_RX.sub("<N>", value)).strip()


@dataclass(frozen=True)
class CapturedLine:
    source_page: int
    line_order: int
    line_text: str
    numeric_tokens: tuple[str, ...]
    is_data_row: bool
    mapped_key: str | None
    line_hash: str
    shape_hash: str


@dataclass(frozen=True)
class LaneCapture:
    statement_type: str
    capture_scope: str
    source_pages: tuple[int, ...]
    lines: tuple[CapturedLine, ...]
    content_hash: str
    shape_hash: str
    mapping_hash: str
    capture_status: str

    @property
    def source_numeric_line_count(self) -> int:
        return sum(
            any(any(char.isdigit() for char in token)
                for token in line.numeric_tokens)
            for line in self.lines
        )

    @property
    def data_rows(self) -> tuple[CapturedLine, ...]:
        return tuple(line for line in self.lines if line.is_data_row)


@dataclass
class CaptureWriteResult:
    source_changed_lanes: set[str] = field(default_factory=set)
    manifest_changed_lanes: set[str] = field(default_factory=set)

    @property
    def changed(self) -> bool:
        return bool(self.source_changed_lanes or self.manifest_changed_lanes)


def _anchor_matches(text: str, cfg: _LaneConfig) -> bool:
    compact = _compact(text)
    return bool(compact) and all(
        any(_compact(phrase) in compact for phrase in group)
        for group in cfg.anchor_groups
    )


def _report_pages(report: object | None, lane: str) -> set[int]:
    if report is None:
        return set()
    if lane == "equity_change":
        rows = getattr(getattr(report, "equity_change", None), "rows", []) or []
        return {int(r.source_page) for r in rows if getattr(r, "source_page", 0)}
    if lane in {"loans_by_sector", "npl_movement", "credit_quality"}:
        rows = getattr(report, lane, []) or []
        return {int(r.page) for r in rows if getattr(r, "page", 0)}
    obj = getattr(report, lane, None)
    page = getattr(obj, "source_page", None)
    return {int(page)} if page else set()


def _selected_pages(
    lane: str,
    texts: list[str],
    hints: set[int],
) -> tuple[int, ...]:
    cfg = _CONFIG[lane]
    n = len(texts)
    anchors = {i + 1 for i, text in enumerate(texts) if _anchor_matches(text, cfg)}
    origins = {p for p in hints | anchors if 1 <= p <= n}
    if not origins:
        return ()

    pages: set[int] = set()
    if cfg.section_range:
        # Report-provided source pages are stronger than text anchors; otherwise
        # start at the first independent anchor and retain the bounded section.
        start = min((p for p in hints if 1 <= p <= n), default=min(origins))
        pages.update(range(start, min(n, start + cfg.pages_after) + 1))
    else:
        for page in origins:
            pages.update(range(page, min(n, page + cfg.pages_after) + 1))
    return tuple(sorted(pages))


def _word_lines(page: object, y_tolerance: float = 3.0) -> list[str]:
    words = sorted(page.get_text("words"), key=lambda word: (word[1], word[0]))
    if not words:
        return [line.strip() for line in page.get_text("text").splitlines() if line.strip()]
    rows: list[tuple[float, list[tuple[float, str]]]] = []
    for word in words:
        if rows and word[1] - rows[-1][0] <= y_tolerance:
            rows[-1][1].append((word[0], str(word[4])))
        else:
            rows.append((word[1], [(word[0], str(word[4]))]))
    return [
        " ".join(token for _, token in sorted(tokens)).strip()
        for _, tokens in rows
        if tokens
    ]


def _dynamic_mappings(report: object | None, lane: str) -> list[tuple[str, str]]:
    if report is None:
        return []
    out: list[tuple[str, str]] = []
    if lane == "equity_change":
        rows = getattr(getattr(report, "equity_change", None), "rows", []) or []
        for row in rows:
            label = _fold(getattr(row, "name", "") or "")
            if len(label.replace(" ", "")) >= 4:
                key = str(getattr(row, "hierarchy", "") or getattr(row, "order", ""))
                out.append((key, label))
    elif lane == "loans_by_sector":
        for row in getattr(report, "loans_by_sector", []) or []:
            label = _fold(getattr(row, "raw_label", "") or "")
            if len(label.replace(" ", "")) >= 4:
                out.append((str(getattr(row, "sector", "")), label))
    return out


def _mapped_key(
    line_text: str,
    report: object | None,
    lane: str,
    dynamic_mappings: Iterable[tuple[str, str]] = (),
) -> str | None:
    label = _fold(_VALUE_RX.sub(" ", line_text))
    compact = label.replace(" ", "")
    static_mappings = _STATIC_MAPPINGS.get(lane, ())
    if lane == "npl_movement":
        static_mappings = (*_npl_parser_mappings(), *static_mappings)
    for key, phrases in static_mappings:
        if any(_compact(phrase) in compact for phrase in phrases):
            return key
    candidates = [*_dynamic_mappings(report, lane), *dynamic_mappings]
    for key, candidate in candidates:
        candidate_compact = candidate.replace(" ", "")
        if (candidate_compact in compact
                or (len(compact) >= 7 and compact in candidate_compact)):
            return key
    return None


def _credit_quality_context_mappings(lines: list[str]) -> dict[int, str]:
    """Map date-only NPL closing labels through their table context.

    ALNTF prints ``30 Haziran 2026`` instead of ``Dönem Sonu Bakiyesi``.
    Matching a date alone would also mark page headings and opening balances;
    the same III/IV/V header and following provision anchor used by the reader
    distinguish the actual closing row. Keep the exact three source cells.
    """
    from .credit_quality import (
        _NPL_DATE_BALANCE_ROW,
        _NPL_HEADER_LINE,
        _NPL_PROVISION_ROW,
        _is_fc_only_block,
    )

    headers = [i for i, line in enumerate(lines)
               if _NPL_HEADER_LINE.match(line.strip())]
    if not headers:
        return {}
    out: dict[int, str] = {}
    for i, line in enumerate(lines[:-1]):
        date = _NPL_DATE_BALANCE_ROW.match(line)
        provision = _NPL_PROVISION_ROW.match(lines[i + 1])
        if (date is None or provision is None
                or not any(header < i for header in headers)
                or _is_fc_only_block(lines, headers, i)):
            continue
        if (len(_VALUE_RX.findall(line[date.end():])) == 3
                and len(_VALUE_RX.findall(lines[i + 1][provision.end():])) == 3):
            out[i + 1] = "ending_balance"
    return out


def _capture_lane(
    doc: object,
    texts: list[str],
    lane: str,
    pages: tuple[int, ...],
    report: object | None,
    dynamic_mappings: Iterable[tuple[str, str]] = (),
) -> LaneCapture:
    cfg = _CONFIG[lane]
    captured: list[CapturedLine] = []
    for page_number in pages:
        page_lines = _word_lines(doc[page_number - 1])
        context_mappings = (_credit_quality_context_mappings(page_lines)
                            if lane == "credit_quality" else {})
        for order, text in enumerate(page_lines, 1):
            clean = _SPACE_RX.sub(" ", text).strip()
            value_tokens = tuple(_VALUE_RX.findall(clean))
            has_numeric_token = any(
                any(char.isdigit() for char in token) for token in value_tokens)
            label = _fold(_VALUE_RX.sub(" ", clean))
            has_letters = any(c.isalpha() for c in clean)
            is_data = bool(
                has_numeric_token
                and len(value_tokens) >= cfg.min_value_tokens
                and has_letters
                and len(label.replace(" ", "")) >= 3
                and len(clean) <= 320
            )
            mapped = _mapped_key(
                clean, report, lane, dynamic_mappings) if is_data else None
            if is_data and mapped is None:
                mapped = context_mappings.get(order)
            captured.append(CapturedLine(
                source_page=page_number,
                line_order=order,
                line_text=clean,
                numeric_tokens=value_tokens,
                is_data_row=is_data,
                mapped_key=mapped,
                line_hash=_digest((clean,)),
                shape_hash=_digest((_shape(clean),)),
            ))

    if not pages:
        status = "not_found"
    elif not captured or not any(
            any(any(char.isdigit() for char in token)
                for token in line.numeric_tokens)
            for line in captured):
        status = "unreadable"
    else:
        status = "captured"
    page_parts = [f"page:{page}" for page in pages]
    return LaneCapture(
        statement_type=lane,
        capture_scope="near_full" if lane in NEAR_FULL_LANES else "selected_summary",
        source_pages=pages,
        lines=tuple(captured),
        content_hash=_digest(page_parts + [line.line_hash for line in captured]),
        shape_hash=_digest(page_parts + [line.shape_hash for line in captured]),
        mapping_hash=_digest(
            f"{line.source_page}:{line.line_order}:{int(line.is_data_row)}:{line.mapped_key or ''}"
            for line in captured
        ),
        capture_status=status,
    )


def capture_pdf(
    pdf_path: str | Path,
    *,
    report: object | None = None,
    lanes: Iterable[str] | None = None,
    page_hints: dict[str, set[int]] | None = None,
    mapping_labels: dict[str, list[tuple[str, str]]] | None = None,
) -> dict[str, LaneCapture]:
    """Capture source lines for ``lanes`` from one local PDF.

    ``page_hints`` normally comes from already-stored ``source_page`` columns;
    independent anchors are always scanned as a second signal so a parser that
    missed the disclosure cannot also hide it from completeness capture.
    """
    import fitz

    selected = tuple(dict.fromkeys(lanes or TARGET_LANES))
    unknown = set(selected) - set(TARGET_LANES)
    if unknown:
        raise ValueError(f"unsupported source-capture lane(s): {sorted(unknown)}")
    doc = fitz.open(str(pdf_path))
    try:
        texts = [doc[i].get_text("text") for i in range(len(doc))]
        out: dict[str, LaneCapture] = {}
        for lane in selected:
            hints = set((page_hints or {}).get(lane, set()))
            hints.update(_report_pages(report, lane))
            pages = _selected_pages(lane, texts, hints)
            out[lane] = _capture_lane(
                doc, texts, lane, pages, report,
                (mapping_labels or {}).get(lane, ()),
            )
        return out
    finally:
        doc.close()


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def stored_page_hints(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    lanes: Iterable[str] | None = None,
) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for lane in lanes or TARGET_LANES:
        table = _TABLE_BY_LANE[lane]
        if not _has_table(conn, table):
            out[lane] = set()
            continue
        out[lane] = {
            int(row[0]) for row in conn.execute(
                f"SELECT DISTINCT source_page FROM {table} "
                "WHERE bank_ticker=? AND period=? AND kind=? AND source_page IS NOT NULL",
                (bank_ticker, period, kind),
            )
            if row[0] and int(row[0]) > 0
        }
    return out


def stored_mapping_labels(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    lanes: Iterable[str] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Labels needed to classify near-full rows during a PDF-only backfill."""
    selected = set(lanes or TARGET_LANES)
    out: dict[str, list[tuple[str, str]]] = {lane: [] for lane in selected}
    if "equity_change" in selected and _has_table(conn, _TABLE_BY_LANE["equity_change"]):
        for hierarchy, name in conn.execute(
            "SELECT DISTINCT hierarchy,item_name FROM bank_audit_equity_change "
            "WHERE bank_ticker=? AND period=? AND kind=?",
            (bank_ticker, period, kind),
        ):
            label = _fold(name or "")
            if len(label.replace(" ", "")) >= 4:
                out["equity_change"].append((str(hierarchy or ""), label))
    if "loans_by_sector" in selected and _has_table(
            conn, _TABLE_BY_LANE["loans_by_sector"]):
        for sector, raw_label in conn.execute(
            "SELECT DISTINCT sector,raw_label FROM bank_audit_loans_by_sector "
            "WHERE bank_ticker=? AND period=? AND kind=?",
            (bank_ticker, period, kind),
        ):
            label = _fold(raw_label or "")
            if len(label.replace(" ", "")) >= 4:
                out["loans_by_sector"].append((str(sector or ""), label))
    return out


def normalized_row_count(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    lane: str,
) -> int:
    table = _TABLE_BY_LANE[lane]
    if not _has_table(conn, table):
        return 0
    return int(conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE bank_ticker=? AND period=? AND kind=?",
        (bank_ticker, period, kind),
    ).fetchone()[0])


_MANIFEST_COLUMNS = (
    "capture_scope", "source_pages_json", "source_page_count",
    "source_line_count", "source_numeric_line_count", "source_data_row_count",
    "mapped_data_row_count", "unmapped_data_row_count", "normalized_row_count",
    "content_hash", "shape_hash", "mapping_hash", "capture_status",
)


def load_manifest(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    lane: str,
) -> dict | None:
    if not _has_table(conn, "bank_audit_capture_manifest"):
        return None
    row = conn.execute(
        "SELECT " + ",".join(_MANIFEST_COLUMNS) +
        " FROM bank_audit_capture_manifest "
        "WHERE bank_ticker=? AND period=? AND kind=? AND statement_type=?",
        (bank_ticker, period, kind, lane),
    ).fetchone()
    return dict(zip(_MANIFEST_COLUMNS, row)) if row else None


def _source_rows(capture: LaneCapture) -> list[tuple]:
    return [
        (
            line.source_page, line.line_order, line.line_text,
            json.dumps(line.numeric_tokens, ensure_ascii=False, separators=(",", ":")),
            len(line.numeric_tokens), int(line.is_data_row), line.mapped_key,
            line.line_hash, line.shape_hash,
        )
        for line in capture.lines
    ]


def _upsert_source_lines(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    capture: LaneCapture,
) -> bool:
    desired = _source_rows(capture)
    current = conn.execute(
        "SELECT source_page,line_order,line_text,numeric_tokens_json,"
        "numeric_token_count,is_data_row,mapped_key,line_hash,shape_hash "
        "FROM bank_audit_source_lines WHERE bank_ticker=? AND period=? AND kind=? "
        "AND statement_type=? ORDER BY source_page,line_order",
        (bank_ticker, period, kind, capture.statement_type),
    ).fetchall()
    if current == desired:
        return False
    conn.execute(
        "DELETE FROM bank_audit_source_lines WHERE bank_ticker=? AND period=? "
        "AND kind=? AND statement_type=?",
        (bank_ticker, period, kind, capture.statement_type),
    )
    if desired:
        conn.executemany(
            "INSERT INTO bank_audit_source_lines "
            "(bank_ticker,period,kind,statement_type,source_page,line_order,line_text,"
            "numeric_tokens_json,numeric_token_count,is_data_row,mapped_key,line_hash,shape_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (bank_ticker, period, kind, capture.statement_type, *row)
                for row in desired
            ],
        )
    return True


def _manifest_values(capture: LaneCapture, normalized_count: int) -> tuple:
    data_rows = capture.data_rows
    mapped = sum(line.mapped_key is not None for line in data_rows)
    return (
        capture.capture_scope,
        json.dumps(capture.source_pages, separators=(",", ":")),
        len(capture.source_pages),
        len(capture.lines),
        capture.source_numeric_line_count,
        len(data_rows),
        mapped,
        len(data_rows) - mapped,
        normalized_count,
        capture.content_hash,
        capture.shape_hash,
        capture.mapping_hash,
        capture.capture_status,
    )


def _upsert_manifest(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    capture: LaneCapture,
    normalized_count: int,
) -> bool:
    desired = _manifest_values(capture, normalized_count)
    current = conn.execute(
        "SELECT " + ",".join(_MANIFEST_COLUMNS) +
        " FROM bank_audit_capture_manifest WHERE bank_ticker=? AND period=? "
        "AND kind=? AND statement_type=?",
        (bank_ticker, period, kind, capture.statement_type),
    ).fetchone()
    if current == desired:
        return False
    columns = ",".join(_MANIFEST_COLUMNS)
    placeholders = ",".join("?" for _ in _MANIFEST_COLUMNS)
    updates = ",".join(f"{column}=excluded.{column}" for column in _MANIFEST_COLUMNS)
    conn.execute(
        "INSERT INTO bank_audit_capture_manifest "
        f"(bank_ticker,period,kind,statement_type,{columns}) "
        f"VALUES (?,?,?,?,{placeholders}) "
        "ON CONFLICT(bank_ticker,period,kind,statement_type) DO UPDATE SET "
        f"{updates},extracted_at=CURRENT_TIMESTAMP",
        (bank_ticker, period, kind, capture.statement_type, *desired),
    )
    return True


def upsert_lane_capture(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    capture: LaneCapture,
    *,
    normalized_count: int | None = None,
) -> tuple[bool, bool]:
    """Persist one prepared capture, returning ``(source_changed, manifest_changed)``."""
    row_count = (
        normalized_row_count(
            conn, bank_ticker, period, kind, capture.statement_type)
        if normalized_count is None else normalized_count
    )
    source_changed = _upsert_source_lines(
        conn, bank_ticker, period, kind, capture)
    manifest_changed = _upsert_manifest(
        conn, bank_ticker, period, kind, capture, row_count)
    return source_changed, manifest_changed


def capture_and_upsert(
    conn: sqlite3.Connection,
    bank_ticker: str,
    period: str,
    kind: str,
    pdf_path: str | Path,
    *,
    report: object | None = None,
    lanes: Iterable[str] | None = None,
) -> CaptureWriteResult:
    """Capture and persist one PDF without committing the caller's transaction.

    A genuinely absent disclosure (no normalized rows, no independent anchor,
    and no prior manifest) remains absent rather than manufacturing a failing
    manifest.  If rows exist or a source table is independently detected, a
    manifest is mandatory and its validator becomes active for that partition.
    """
    selected = tuple(dict.fromkeys(lanes or TARGET_LANES))
    hints = stored_page_hints(conn, bank_ticker, period, kind, selected)
    mappings = stored_mapping_labels(conn, bank_ticker, period, kind, selected)
    captures = capture_pdf(
        pdf_path, report=report, lanes=selected, page_hints=hints,
        mapping_labels=mappings,
    )
    result = CaptureWriteResult()
    for lane, capture in captures.items():
        row_count = normalized_row_count(conn, bank_ticker, period, kind, lane)
        existing = load_manifest(conn, bank_ticker, period, kind, lane)
        if not capture.source_pages and row_count == 0 and existing is None:
            continue
        source_changed, manifest_changed = upsert_lane_capture(
            conn, bank_ticker, period, kind, capture,
            normalized_count=row_count,
        )
        if source_changed:
            result.source_changed_lanes.add(lane)
        if manifest_changed:
            result.manifest_changed_lanes.add(lane)
    return result
