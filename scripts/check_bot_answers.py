"""Run the bot's canonical questions against D1 and assert the right answers.

`check_bot_schema.py` verifies that the prompt's FACTS match the data. This
verifies that its RECIPES produce correct numbers — the step that would have
caught every wrong answer the bot has shipped:

  • the sector's total assets read 198,874,433 million TL (3.84x) because the
    recipe summed overlapping bank_type_code groups;
  • İş Bankası ranked 7th at 2.72trn instead of 3rd at 4.94trn because the
    total-assets recipe used MAX on one leg and hit a sub-line;
  • a profit ranking returned 36 of 38 banks because it matched a label;
  • a branch-productivity ranking returned 8 of 27 because the model picked
    the banks itself.

Each case runs the SQL the prompt now teaches and asserts a value verified
independently. A failure means either the data moved or a recipe regressed —
both worth knowing before a user finds out.

Expected values are pinned to a PERIOD, so they stay valid as new data lands.

Usage:
    python scripts/check_bot_answers.py
    python scripts/check_bot_answers.py --alert
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.stdout.reconfigure(encoding="utf-8")

PERIOD = "2026Q1"      # per-bank (quarterly)
MONTH = (2026, 5)      # sector (monthly)


def d1(sql: str) -> list[dict]:
    proc = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "bddk-data", "--remote", "--json",
         "--command", " ".join(sql.split())],
        cwd=WEB, capture_output=True, text=True, encoding="utf-8",
        # shell=True is required on Windows (npx is a .cmd) but on POSIX it
        # runs `sh -c "npx"` and DISCARDS the argument list — stdout comes
        # back empty and every check raises. That is exactly how this
        # passed locally and failed on every CI run.
        shell=(os.name == "nt"),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"d1 failed: {proc.stderr[-300:]}")
    m = re.search(r"\[[\s\S]*\]", proc.stdout)
    if not m:
        raise RuntimeError(f"unparseable: {proc.stdout[:200]}")
    return json.loads(m.group(0))[0]["results"]


FAILURES: list[str] = []


def expect(name: str, got, want, note: str = "") -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got {got!r}, expected {want!r}" + (f"  ({note})" if note else ""))
        FAILURES.append(f"{name}: got {got!r}, expected {want!r}")


# ---------------------------------------------------------------------------
def sector_total_assets() -> None:
    """The whole sector is ONE row (10001), never a sum of groups."""
    v = d1(f"""
        SELECT amount_total FROM balance_sheet
         WHERE year={MONTH[0]} AND month={MONTH[1]} AND currency='TL'
           AND bank_type_code='10001' AND item_name='TOPLAM AKTİFLER'
    """)[0]["amount_total"]
    expect("sector total assets = the 10001 row, not a sum", v, 51760765,
           "summing all ten groups gives 198,874,433 — 3.84x")

    # The leg/total confusion: filtering currency='TL' invites reading amount_tl,
    # which is the LIRA leg, not the figure. Live test caught the bot doing
    # exactly this AFTER the overlap fix — a 39% understatement that reads fine.
    legs = d1(f"""
        SELECT amount_tl, amount_fx, amount_total FROM balance_sheet
         WHERE year={MONTH[0]} AND month={MONTH[1]} AND currency='TL'
           AND bank_type_code='10001' AND item_name='TOPLAM AKTİFLER'
    """)[0]
    expect("amount_tl is the LIRA LEG, not the total", legs["amount_tl"], 31777002,
           "the bot reported this as 'total assets'")
    expect("amount_tl + amount_fx = amount_total",
           legs["amount_tl"] + legs["amount_fx"], legs["amount_total"])

    # And the trap it replaced, asserted explicitly so it can't creep back.
    bad = d1(f"""
        SELECT SUM(amount_total) AS s FROM balance_sheet
         WHERE year={MONTH[0]} AND month={MONTH[1]} AND currency='TL'
           AND item_name='TOPLAM AKTİFLER'
    """)[0]["s"]
    expect("summing every bank_type_code still reproduces the 3.84x trap",
           bad, 198874433, "if this changed, the overlap structure moved")


def total_assets_ranking() -> None:
    """MAX across BOTH legs — one leg alone hits a sub-line."""
    rows = d1(f"""
        SELECT bank_ticker, MAX(amount_total) AS ta
          FROM bank_audit_balance_sheet
         WHERE statement IN ('assets','liabilities') AND kind='unconsolidated'
           AND period='{PERIOD}'
         GROUP BY bank_ticker ORDER BY ta DESC
    """)
    expect("total-assets ranking covers every bank", len(rows), 38)
    expect("ISCTR ranks 3rd", rows[2]["bank_ticker"], "ISCTR",
           "with statement='assets' alone it falls to 7th")
    expect("ISCTR total assets", rows[2]["ta"], 4935546613,
           "the assets leg alone returns 2,715,905,125 — a sub-line")

    # The single-leg recipe must still be demonstrably wrong, or the fix is moot.
    one = d1(f"""
        SELECT MAX(amount_total) AS ta FROM bank_audit_balance_sheet
         WHERE statement='assets' AND kind='unconsolidated'
           AND period='{PERIOD}' AND bank_ticker='ISCTR'
    """)[0]["ta"]
    expect("the single-leg recipe is still the broken one", one, 2715905125)


def roman_sum_fallback() -> None:
    """Summing the top-level romans works with no total row at all."""
    v = d1(f"""
        SELECT SUM(amount_total) AS s FROM bank_audit_balance_sheet
         WHERE bank_ticker='ISCTR' AND period='{PERIOD}' AND kind='unconsolidated'
           AND statement='assets'
           AND hierarchy GLOB '[IVX]*.' AND hierarchy NOT GLOB '*.*.*'
    """)[0]["s"]
    expect("roman-section sum equals the true total", v, 4935546613)

    # DUNYAK 2025Q4 has no total row on EITHER leg — the only route.
    rows = d1("""
        SELECT statement, SUM(amount_total) AS s FROM bank_audit_balance_sheet
         WHERE bank_ticker='DUNYAK' AND period='2025Q4' AND kind='unconsolidated'
           AND statement IN ('assets','liabilities')
           AND hierarchy GLOB '[IVX]*.' AND hierarchy NOT GLOB '*.*.*'
         GROUP BY statement
    """)
    vals = {r["statement"]: r["s"] for r in rows}
    expect("DUNYAK 2025Q4 assets recovered by roman sum", vals.get("assets"), 99678154)
    expect("DUNYAK 2025Q4 both legs agree", vals.get("liabilities"), 99678154)


def profit_ranking() -> None:
    """Join pl_roles — a label match drops AKBNK (blank) and HAYATK."""
    rows = d1(f"""
        SELECT p.bank_ticker, p.amount FROM bank_audit_profit_loss p
          JOIN bank_audit_pl_roles r ON r.bank_ticker=p.bank_ticker
           AND r.period=p.period AND r.kind=p.kind AND r.hierarchy=p.hierarchy
         WHERE r.role='period_net' AND p.kind='unconsolidated' AND p.period='{PERIOD}'
         ORDER BY p.amount DESC
    """)
    expect("profit ranking covers every bank", len(rows), 38)
    expect("AKBNK is present", any(r["bank_ticker"] == "AKBNK" for r in rows), True,
           "the '%XIX+XXIV%' label match drops it — its item_name is blank")

    label = d1(f"""
        SELECT COUNT(DISTINCT bank_ticker) AS n FROM bank_audit_profit_loss
         WHERE kind='unconsolidated' AND period='{PERIOD}'
           AND item_name LIKE '%XIX+XXIV%'
    """)[0]["n"]
    expect("the old label recipe is still the broken one", label, 36)


def branch_productivity() -> None:
    """Only banks WITH branches; the model must not pick them."""
    rows = d1(f"""
        SELECT bank_ticker FROM bank_audit_profile
         WHERE period='{PERIOD}' AND kind='unconsolidated' AND branches_total > 0
    """)
    expect("branch-productivity population", len(rows), 30,
           "the model's self-chosen list answered for 8")


def sector_ratio_labels() -> None:
    """The ratio labels the prompt hands the model must still exist verbatim.

    These are quoted in the prompt so the model does not have to search for
    them — searching failed, because there is no 'Sermaye Yeterlilik' label and
    SQLite's LIKE does not fold Turkish letters. If a label is reworded upstream
    the lookup silently returns nothing, which is how this cost five queries and
    an apology the first time.
    """
    labels = {
        "CAR": "Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı (%)",
        "ROE": "Dönem Net Kârı (Zararı) / Ortalama Özkaynaklar (%)",
        "NPL": "Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler (%)",
        "loan/deposit": "Toplam Nakdi Krediler / Toplam Mevduat (%)",
    }
    for name, label in labels.items():
        n = d1(f"""
            SELECT COUNT(*) AS n FROM financial_ratios
             WHERE year={MONTH[0]} AND month={MONTH[1]}
               AND item_name = '{label.replace("'", "''")}'
        """)[0]["n"]
        expect(f"sector ratio label resolves: {name}", n > 0, True,
               "the prompt quotes this verbatim; a reworded label returns nothing")

    # bank_types joins on `code`, not `bank_type_code` — the model got this
    # wrong and errored its last step.
    car = d1(f"""
        SELECT ROUND(fr.ratio_value,2) AS car FROM financial_ratios fr
          JOIN bank_types bt ON bt.code = fr.bank_type_code
         WHERE fr.year={MONTH[0]} AND fr.month={MONTH[1]} AND bt.code='10001'
           AND fr.item_name='Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı (%)'
    """)[0]["car"]
    expect("sector CAR via the documented join", car, 16.34)


def units_and_enums() -> None:
    """Unit and value-set claims that scale or void an answer if wrong."""
    unit5 = d1("SELECT unit FROM table_definitions WHERE table_number=5")[0]["unit"]
    expect("loans table 5 is thousand TL (others are million)", unit5, "thousand TL")

    n = d1("""SELECT COUNT(*) AS n FROM balance_sheet WHERE currency='USD'
                AND (year*100+month) != 202512""")[0]["n"]
    expect("USD basis exists for 2025-12 only", n, 0,
           "mixing it with TL is a 43x error")

    cq = d1(f"""
        SELECT COUNT(DISTINCT bank_ticker) AS n FROM bank_audit_credit_quality
         WHERE period='{PERIOD}' AND kind='unconsolidated' AND period_type='current'
           AND section='loans_by_stage'
    """)[0]["n"]
    expect("credit_quality 'loans_by_stage' covers the fleet", cq, 38,
           "the sections the prompt used to name cover 0-2 banks")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true")
    args = ap.parse_args()

    print(f"verifying the bot's recipes against D1 ({PERIOD} / {MONTH[0]}-{MONTH[1]:02d})…")
    for fn in (sector_total_assets, total_assets_ranking, roman_sum_fallback,
               profit_ranking, branch_productivity, sector_ratio_labels,
               units_and_enums):
        try:
            fn()
        except Exception as e:  # a broken check is itself a failure
            print(f"  ERROR in {fn.__name__}: {type(e).__name__}: {str(e)[:160]}")
            FAILURES.append(f"{fn.__name__} raised {type(e).__name__}")

    if FAILURES:
        msg = "❌ Bot answer checks failed:\n" + "\n".join(f"• {f}" for f in FAILURES)
        print(f"\n{len(FAILURES)} check(s) failed", file=sys.stderr)
        if args.alert:
            sys.path.insert(0, str(ROOT / "scripts"))
            from notify import notify
            notify(msg[:1500])
        return 1
    print("\nall recipes return the verified answers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
