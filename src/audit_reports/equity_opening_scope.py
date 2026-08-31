"""Source-bound opening-balance comparison for a disclosed prior restatement."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _reviews() -> list[dict]:
    path = Path(__file__).resolve().parents[2] / "data" / "audit_equity_opening_scope_reviews.json"
    try:
        reviews = json.loads(path.read_text(encoding="utf-8"))["reviews"]
        return reviews if isinstance(reviews, list) else []
    except (OSError, ValueError, KeyError, TypeError):
        return []  # Missing evidence retains the ordinary comparison failure.


def reviewed_adjusted_opening(
    current_rows: list[dict], prior_closing: dict, *,
    bank_ticker: str | None, period: str | None, kind: str | None,
) -> float | None:
    """Use adjusted opening only for the exact reviewed source operands.

    EXIM's prior comparative is already restated for investment-property policy,
    while current row I is before that adjustment. Row II/2.2 explicitly prints
    the adjustment and row III is the comparable opening. No residual is inferred.
    """
    review = next((r for r in _reviews()
                   if (r["bank_ticker"], r["period"], r["kind"])
                   == (bank_ticker, period, kind)), None)
    if review is None or review["rule"] != "adjusted_opening_matches_restated_prior":
        return None
    current = {}
    for row in current_rows:
        h = (row.get("hierarchy") or "").strip().rstrip(".")
        if h in review["current"]:
            if h in current or row.get("period_type") != "current":
                return None
            current[h] = row
    if current.keys() != review["current"].keys():
        return None
    if prior_closing.get("period_type") != "prior" or prior_closing.get("hierarchy"):
        return None
    fingerprints = [(current[h], expected) for h, expected in review["current"].items()]
    fingerprints.append((prior_closing, review["prior_closing"]))
    for actual, expected in fingerprints:
        if any(field not in actual or actual[field] != amount for field, amount in expected.items()):
            return None
    adjustment = review["adjustment"]
    if adjustment is None or adjustment == 0:
        return None
    for h in ("II", "2.2"):
        row = current[h]
        if row["total_equity"] != adjustment or row["prior_period_profit_loss"] != adjustment:
            return None
        if any(value not in (0, None) for field, value in review["current"][h].items()
               if field not in {"total_equity", "prior_period_profit_loss"}):
            return None
    opening, adjusted = current["I"]["total_equity"], current["III"]["total_equity"]
    if opening is None or adjusted is None or opening + adjustment != adjusted:
        return None
    if adjusted != prior_closing["total_equity"]:
        return None
    return adjusted
