"""Extract per-bank IFRS-9 stage definitions from the prose lane — the
feasibility test's #1 missing dataset ("stage-definition comparability is the
missing half of asset quality"; every peer stage comparison has carried a
disclaimer since).

Scans `data/bank_audit_prose.db` (LOCAL ONLY — 298MB, never in CI) for each
bank's own disclosed staging thresholds in the notes / accounting-policy /
risk roles:

- Stage 2 (SICR):   a 30/60-day past-due trigger near SICR/watchlist language
- Stage 3 (default): a 90/180-day past-due trigger near default/NPL language

and emits `web/app/lib/analyst/stage-definitions.ts` — a GENERATED, committed
module (TS, not JSON, so no tsconfig flag is involved) that ships to both the
Worker and the CI runner. Verbatim snippets ride along: the claim is always
the bank's own sentence, not our classification.

Run locally after a prose backfill:
    python scripts/analyst/extract_stage_definitions.py
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROSE_DB = REPO / "data" / "bank_audit_prose.db"
OUT = REPO / "web" / "app" / "lib" / "analyst" / "stage-definitions.ts"

ROLES = ("notes", "accounting_policies", "risk")

DAY_RE = re.compile(r"\b(30|60|90|180)\s*(?:gün|gun|day|days)\b", re.I)
S2_CTX = re.compile(
    r"gecikme|overdue|past\s*due|yakın\s*izleme|watch\s*list|watchlist|stage\s*2|"
    r"ikinci\s*aşama|significant\s*increase|önemli\s*(?:ölçüde|derecede)?\s*art|SICR",
    re.I)
S3_CTX = re.compile(
    r"temerrüt|default|donuk|takip|stage\s*3|üçüncü\s*aşama|non.?perform|impair|"
    r"değer\s*düş", re.I)


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def scan_text(text: str) -> tuple[tuple[int, str] | None, tuple[int, str] | None]:
    """(stage2_days, snippet), (stage3_days, snippet) from one chunk."""
    s2: tuple[int, str] | None = None
    s3: tuple[int, str] | None = None
    for m in DAY_RE.finditer(text):
        days = int(m.group(1))
        window = text[max(0, m.start() - 200): m.end() + 200]
        snippet = collapse(text[max(0, m.start() - 140): m.end() + 160])
        if days in (30, 60) and s2 is None and S2_CTX.search(window):
            s2 = (days, snippet)
        elif days in (90, 180) and s3 is None and S3_CTX.search(window):
            s3 = (days, snippet)
        if s2 and s3:
            break
    return s2, s3


def main() -> int:
    if not PROSE_DB.exists():
        raise SystemExit(f"{PROSE_DB} not found — the prose DB is local-only; run on the machine that holds it")
    conn = sqlite3.connect(f"file:{PROSE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    out: dict[str, dict] = {}
    banks = [r[0] for r in conn.execute(
        "SELECT DISTINCT bank_ticker FROM bank_audit_prose ORDER BY bank_ticker")]
    for bank in banks:
        # Latest period wins; consolidated preferred (group policy statement),
        # unconsolidated fallback — the policy is the same bank's.
        best: dict | None = None
        for kind in ("consolidated", "unconsolidated"):
            periods = [r[0] for r in conn.execute(
                "SELECT DISTINCT period FROM bank_audit_prose "
                "WHERE bank_ticker = ? AND kind = ? ORDER BY period DESC LIMIT 3",
                (bank, kind))]
            for period in periods:
                s2 = s3 = None
                for row in conn.execute(
                    "SELECT text FROM bank_audit_prose "
                    "WHERE bank_ticker = ? AND kind = ? AND period = ? "
                    f"AND section_role IN ({','.join('?' * len(ROLES))}) "
                    "AND text IS NOT NULL ORDER BY item_order",
                        (bank, kind, period, *ROLES)):
                    a, b = scan_text(row["text"] or "")
                    s2 = s2 or a
                    s3 = s3 or b
                    if s2 and s3:
                        break
                if s2 or s3:
                    best = {
                        "source_period": period,
                        "source_kind": kind,
                        "dpd_stage2_days": s2[0] if s2 else None,
                        "stage2_snippet": s2[1] if s2 else None,
                        "dpd_stage3_days": s3[0] if s3 else None,
                        "stage3_snippet": s3[1] if s3 else None,
                    }
                    break
            if best:
                break
        if best:
            out[bank] = best
    conn.close()

    s2_census = Counter(v["dpd_stage2_days"] for v in out.values() if v["dpd_stage2_days"])
    s3_census = Counter(v["dpd_stage3_days"] for v in out.values() if v["dpd_stage3_days"])
    census = {
        "banks_scanned": len(banks),
        "banks_with_any": len(out),
        "stage2_days_distribution": dict(sorted(s2_census.items())),
        "stage3_days_distribution": dict(sorted(s3_census.items())),
    }

    body = (
        "// GENERATED by scripts/analyst/extract_stage_definitions.py — do not edit.\n"
        "// Per-bank IFRS-9 staging thresholds as DISCLOSED in each bank's own §3/\n"
        "// notes prose (the feasibility test's missing comparability dataset).\n"
        "// Snippets are verbatim from the filing; days are parsed from them.\n"
        "// Source: data/bank_audit_prose.db (local-only) — regenerate after a\n"
        "// prose backfill and commit the result.\n\n"
        "export interface StageDefinition {\n"
        "  source_period: string;\n"
        "  source_kind: string;\n"
        "  dpd_stage2_days: number | null;\n"
        "  stage2_snippet: string | null;\n"
        "  dpd_stage3_days: number | null;\n"
        "  stage3_snippet: string | null;\n"
        "}\n\n"
        f"export const STAGE_DEFINITIONS: Record<string, StageDefinition> = {json.dumps(out, ensure_ascii=False, indent=2)};\n\n"
        f"export const STAGE_DEFINITION_CENSUS = {json.dumps(census, ensure_ascii=False, indent=2)} as const;\n"
    )
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"{len(out)}/{len(banks)} banks with a disclosed threshold → {OUT}")
    print("stage2 days:", dict(s2_census), "| stage3 days:", dict(s3_census))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
