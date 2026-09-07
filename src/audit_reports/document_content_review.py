"""Source-bound open review notes; never corrected values or semantic approval."""
from __future__ import annotations

import hashlib
import math

from .document_evidence import _canonical_json


def validate_content_review(case: dict, pages: dict[int, dict]) -> bool:
    """Require exact retained page bytes, span occurrences, wording and geometry.

    The note is a reviewer's interpretation. Only its source references are
    checked here. No comparison of accounting meanings is inferred from this.
    """
    if (case.get("status") != "open" or case.get("semantic_verification") != "not_performed"
            or not all(isinstance(case.get(k), str) and case[k].strip() for k in ("id", "title", "note"))
            or not isinstance(case.get("points"), list) or not 2 <= len(case["points"]) <= 20):
        return False
    for point in case["points"]:
        if not isinstance(point, dict) or type(point.get("page")) is not int or point["page"] not in pages:
            return False
        page = pages[point["page"]]
        if hashlib.sha256(_canonical_json(page).encode("utf-8")).hexdigest() != point.get("source_page_artifact_sha256"):
            return False
        ids, box = point.get("source_span_ids"), point.get("bbox")
        if (not isinstance(ids, list) or not ids or any(type(i) is not int for i in ids)
                or ids != sorted(set(ids)) or not isinstance(box, list) or len(box) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            return False
        spans = {s["id"]: s for s in page["spans"]}
        if any(i not in spans for i in ids):
            return False
        selected = [spans[i] for i in ids]
        if "\n".join(s["text"] for s in selected) != point.get("source_text"):
            return False
        if any(not (box[0] <= s["bbox"][0] <= s["bbox"][2] <= box[2]
                    and box[1] <= s["bbox"][1] <= s["bbox"][3] <= box[3]) for s in selected):
            return False
    return True
