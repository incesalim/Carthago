"""Value-bound, source-reviewed comparison bases for equity versus OCI.

These are not data overrides. Source amounts remain untouched, and a review
applies only while every independently printed operand still matches its ledger.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _reviews() -> list[dict]:
    path = Path(__file__).resolve().parents[2] / "data" / "audit_equity_oci_scope_reviews.json"
    try:
        reviews = json.loads(path.read_text(encoding="utf-8"))["reviews"]
        return reviews if isinstance(reviews, list) else []
    except (OSError, ValueError, KeyError, TypeError):
        # Missing review evidence must retain the ordinary comparison failure,
        # not abort validation and leave a stale verdict in the database.
        return []


def _unique_rows(rows: list[dict]) -> dict[str, dict] | None:
    result = {}
    for row in rows:
        hierarchy = (row.get("hierarchy") or "").strip().rstrip(".")
        if hierarchy in result:
            return None
        result[hierarchy] = row
    return result


def _grand(row: dict) -> float | None:
    total = row.get("total_equity_incl_minority")
    return row.get("total_equity") if total is None else total


def reviewed_equity_oci_total(
    equity_rows: list[dict], oci_rows: list[dict], *,
    bank_ticker: str | None, period: str | None, kind: str | None,
) -> float | None:
    """Return the source-supported comparison amount, or leave the usual check.

    The DB has no PDF digest column, so runtime binding is the exact partition
    plus complete reviewed current-row operands. The ledger retains source hashes
    and pages for review; changed/missing operands never inherit an exception.
    """
    review = next((r for r in _reviews()
                   if (r["bank_ticker"], r["period"], r["kind"])
                   == (bank_ticker, period, kind)), None)
    if review is None:
        return None
    oci = _unique_rows(oci_rows)
    # Other equity movements retain their ordinary structural checks. Only the
    # explicitly reviewed IV/X rows participate in this comparison rule.
    eq = _unique_rows([r for r in equity_rows if r.get("period_type") == "current"
                       and (r.get("hierarchy") or "").strip().rstrip(".") in review["equity"]])
    if oci is None or eq is None or oci.keys() != review["oci"].keys() or eq.keys() != review["equity"].keys():
        return None
    if any(oci[h].get("amount") != amount for h, amount in review["oci"].items()):
        return None
    for h, expected in review["equity"].items():
        if any(field not in eq[h] or eq[h][field] != amount for field, amount in expected.items()):
            return None
    r4_total = _grand(eq["IV"])
    adjustment = review["adjustment"]
    if r4_total is None or adjustment is None:
        return None
    if review["rule"] == "translation_in_other_changes":
        other = eq["X"]
        translation = other["oci_reclassified_1"]
        if (eq["IV"]["oci_reclassified_1"] != 0
                or translation != oci["2.2.1"]["amount"] or translation != adjustment
                or _grand(other) != translation):
            return None
        # No capital/profit/minority movement may piggyback on the FX adjustment.
        for field, value in other.items():
            if field in review["equity"]["X"] and field not in {
                "oci_reclassified_1", "total_equity", "total_equity_incl_minority",
            } and value not in (0, None):
                return None
    elif review["rule"] != "participant_risk_fund":
        return None
    # KUVEYT's adjustment is the explicitly quantified participant-fund amount
    # in its source footnote, not a number computed from the cross-check gap.
    adjusted = r4_total + adjustment
    return adjusted if adjusted == oci["III"]["amount"] else None
