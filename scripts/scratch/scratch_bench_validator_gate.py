#!/usr/bin/env python3
"""Scratch bench: would the validators CATCH a wrong LLM figure?

The proposed architecture is regex first, LLM where regex fails, validators as
the gate, hand-fix whatever survives. That design lives or dies on one question:
when the model returns a confidently wrong number — `found=true`, no hesitation —
does an existing validator reject it?

If yes, the LLM is safe to use as a fallback: its errors cannot reach the
database, they surface as a red partition for a human.
If no, its hit rate is irrelevant. A silent wrong figure is exactly the failure
mode this repo has spent the most effort eliminating.

Method: take the stored, validated rows for a partition, substitute the model's
answer into the one cell it got wrong, re-run that lane's real validator, and see
whether the failure count rises. No PDF re-read, no writes.

Scratch by design.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.audit_reports import validator as v  # noqa: E402
from scripts.revalidate_audit_db import (  # noqa: E402
    _bs_rows, _oci_rows, _pl_rows,
)

ROOT = Path(__file__).resolve().parents[2]

# The confidently-wrong answers the text-cell bench produced: model said
# found=true and returned a figure that is not what is printed. Each is
# (bank, period, kind, lane, HIERARCHY, true value, model value).
#
# Addressed by hierarchy, not by name. QNBFB 2023Q1 prints "Non-cashloans"
# TWICE — 4.1.1 (fees received, 175,010) and 4.2.1 (fees paid, 449) — so a
# name-keyed lookup silently mutated the wrong row and reported ESCAPED for a
# substitution that never happened. The same ambiguity is why the model
# answered 175,010 when asked for 4.2.1.
WRONG = [
    # A spine row: the model zeroed the net operating result.
    ("QNBFB", "2023Q1", "unconsolidated", "profit_loss",
     "XIX.", 6632553, 0),
    # A discontinued-operations roman the model invented a figure for.
    ("TAKAS", "2023Q3", "unconsolidated", "profit_loss", "XXIV.", 0, 2260614),
    # A deep leaf (4.2.1) — the hardest case for a sum check to see.
    ("QNBFB", "2023Q1", "unconsolidated", "profit_loss", "4.2.1", 449, 175010),
]


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def run_lane(conn, bank: str, period: str, kind: str, lane: str,
             mutate: tuple[str, float] | None) -> v.ValidationResult:
    """Validate one lane, optionally substituting a value into one row first."""
    pl = _pl_rows(conn, bank, period, kind)
    liab = _bs_rows(conn, bank, period, kind, "liabilities")
    oci = _oci_rows(conn, bank, period, kind)
    off = _bs_rows(conn, bank, period, kind, "off_balance")

    if mutate:
        label, value = mutate
        target = {"profit_loss": pl, "oci": oci, "off_balance": off}[lane]
        hit = False
        for r in target:
            if (r.get("hierarchy") or "").strip().rstrip(".") == label.rstrip("."):
                if lane == "off_balance":
                    r["amount_total"] = value
                else:
                    r["amount"] = value
                hit = True
                break
        if not hit:
            raise KeyError(f"hierarchy {label!r} not found in {lane}")

    if lane == "profit_loss":
        return v.check_profit_loss(pl, liab)
    if lane == "oci":
        return v.check_oci(oci, pl)
    return v.validate_off_balance(off)


def main() -> int:
    conn = sqlite3.connect(f"file:{ROOT / 'data/bank_audit.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    print("Does an existing validator reject the model's wrong figure?\n")

    caught = escaped = skipped = 0
    for bank, period, kind, lane, label, truth, model in WRONG:
        tag = f"{bank} {period} {kind[:5]} {lane}"
        if label is None:
            print(f"  {tag}: no row label recorded — skipped")
            skipped += 1
            continue
        try:
            base = run_lane(conn, bank, period, kind, lane, None)
            bad = run_lane(conn, bank, period, kind, lane, (label, float(model)))
        except KeyError as e:
            print(f"  {tag}: {e} — skipped")
            skipped += 1
            continue

        rose = bad.failed > base.failed
        verdict = "CAUGHT" if rose else "ESCAPED"
        caught += rose
        escaped += not rose
        print(f"  {tag}")
        print(f"     truth={truth:,} model={model:,}")
        print(f"     validator failures: clean={base.failed} "
              f"with-model-value={bad.failed}  -> {verdict}")
        if rose:
            new = [f for f in bad.failures if f not in base.failures][:3]
            for f in new:
                print(f"        {f['check']} @ {f['node']}: "
                      f"expected {f['expected']:,} got {f['actual']:,}")

    print(f"\n  caught {caught}, escaped {escaped}, skipped {skipped}")
    if escaped:
        print("  ⚠️ An escaped wrong figure means the validator gate does NOT "
              "make an LLM fallback safe for that lane.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
