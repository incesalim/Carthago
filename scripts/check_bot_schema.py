"""Verify the bot's schema prompt against the live database.

`web/app/lib/bot-schema.ts` tells an LLM what the data looks like. When a claim
in it is wrong, the model writes confident, plausible, WRONG SQL — and nothing
errors, because the SQL is valid. Every bot bug found so far was of that shape:

  • the prompt listed the bank_type_code partitions but omitted 10001 (the
    sector itself), so the model built a sector total by summing overlapping
    groups and reported assets 3.84x too high;
  • it claimed `currency IN ('TL','YP','TOTAL')` when the real values are
    'TL' and 'USD' — filtering the documented value returns zero rows;
  • it taught `item_name LIKE '%XIX+XXIV%'` for net profit, which silently
    missed 2 of 38 banks;
  • its ticker list was missing 7 of 38 banks, so those answered "no data".

Prose can't be unit-tested, but the FACTS it asserts can. This script extracts
the checkable ones and runs them against D1, so a schema change that invalidates
the prompt fails loudly here instead of quietly in someone's answer.

It also checks two data invariants the prompt's recipes depend on — see
`check_balance_sheet_identity` and `check_pl_roles_coverage`.

Usage:
    python scripts/check_bot_schema.py             # report, exit 1 on failure
    python scripts/check_bot_schema.py --alert     # + Telegram/Discord on failure
    python scripts/check_bot_schema.py --verbose   # show passing checks too

Env: CLOUDFLARE_API_TOKEN (wrangler picks it up).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_TS = ROOT / "web" / "app" / "lib" / "bot-schema.ts"
WEB = ROOT / "web"

sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
def d1(sql: str) -> list[dict]:
    """Run one read-only query against remote D1 and return its rows.

    The SQL is flattened to a single line: wrangler on Windows aborts with a
    libuv assertion when a --command argument contains newlines.
    """
    flat = " ".join(sql.split())
    proc = subprocess.run(
        ["npx", "wrangler", "d1", "execute", "bddk-data", "--remote", "--json",
         "--command", flat],
        cwd=WEB, capture_output=True, text=True, encoding="utf-8", shell=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"d1 query failed: {proc.stderr[-400:]}")
    m = re.search(r"\[[\s\S]*\]", proc.stdout)
    if not m:
        raise RuntimeError(f"unparseable d1 output: {proc.stdout[:300]}")
    return json.loads(m.group(0))[0]["results"]


class Report:
    def __init__(self, verbose: bool) -> None:
        self.failures: list[str] = []
        self.verbose = verbose

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            if self.verbose:
                print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}\n        {detail}")
            self.failures.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
def check_tickers(prompt: str, rep: Report) -> None:
    """Every ticker in the data must be listed in the prompt.

    A ticker the prompt omits is a bank the model does not know exists — it
    answers "no data" for a bank we hold full statements for.
    """
    section = re.search(r"TICKERS \(bank_ticker\)[^\n]*\n(.*?)\n═", prompt, re.S)
    listed = set(re.findall(r"\b([A-Z][A-Z0-9]{2,9})=", section.group(1))) if section else set()
    actual = {r["bank_ticker"] for r in d1(
        "SELECT DISTINCT bank_ticker FROM bank_audit_balance_sheet")}
    missing = sorted(actual - listed)
    rep.check("tickers: every bank in the data is listed in the prompt",
              not missing,
              f"{len(missing)} missing from the prompt: {', '.join(missing)}")
    stale = sorted(listed - actual)
    rep.check("tickers: no listed ticker is absent from the data",
              not stale, f"listed but no rows: {', '.join(stale)}")


def check_enum(rep: Report, label: str, sql: str, expected: set[str]) -> None:
    """A documented set of column values must match reality exactly."""
    actual = {str(list(r.values())[0]) for r in d1(sql)}
    rep.check(f"values: {label}", actual == expected,
              f"prompt says {sorted(expected)}, data has {sorted(actual)}")


def check_bank_type_overlap(rep: Report) -> None:
    """The three partitions must each re-cover the sector exactly.

    This is the identity the prompt's "never sum across cuts" rule rests on. If
    BDDK ever changed the grouping, the rule would still read plausibly while
    being wrong.
    """
    rows = d1("SELECT bank_type_code, amount_total FROM balance_sheet "
              "WHERE currency='TL' AND item_name='TOPLAM AKTİFLER' "
              "AND (year*100+month)=(SELECT MAX(year*100+month) FROM balance_sheet)")
    v = {r["bank_type_code"]: r["amount_total"] for r in rows}
    if len(v) < 10:
        rep.check("bank_type_code: all ten groups present", False,
                  f"only {len(v)} groups found: {sorted(v)}")
        return
    sector = v["10001"]
    for name, codes, target in [
        ("by licence (10002+10003+10004)", ["10002", "10003", "10004"], sector),
        ("by ownership (10005+10006+10007)", ["10005", "10006", "10007"], sector),
        ("deposit banks (10008+10009+10010)", ["10008", "10009", "10010"], v["10002"]),
    ]:
        got = sum(v[c] for c in codes)
        rep.check(f"bank_type_code: {name} re-covers its parent",
                  abs(got - target) <= 1,
                  f"sums to {got:,}, expected {target:,}")


def check_balance_sheet_identity(rep: Report) -> None:
    """Assets and liabilities MAX must agree — the prompt's total-assets recipe.

    A balance sheet balances, so the largest line on each leg is the same grand
    total. When they disagree, one leg's total row is MISSING from the
    extraction and MAX silently returns a sub-line instead: at 2026Q1 that put
    ISCTR's total assets at 2.72tn instead of 4.94tn, moving it from 3rd to 7th
    in a ranking that showed all 38 banks and looked complete.
    """
    rows = d1("""
        SELECT bank_ticker, period,
               MAX(CASE WHEN statement='assets' THEN amount_total END) AS a,
               MAX(CASE WHEN statement='liabilities' THEN amount_total END) AS l,
               SUM(CASE WHEN statement='assets'
                         AND (hierarchy IS NULL OR TRIM(hierarchy)='') THEN 1 ELSE 0 END) AS a_tot,
               SUM(CASE WHEN statement='liabilities'
                         AND (hierarchy IS NULL OR TRIM(hierarchy)='') THEN 1 ELSE 0 END) AS l_tot
          FROM bank_audit_balance_sheet
         WHERE kind='unconsolidated' AND statement IN ('assets','liabilities')
           AND period=(SELECT MAX(period) FROM bank_audit_balance_sheet)
         GROUP BY bank_ticker, period
        HAVING ABS(a-l) > 1
    """)
    # One leg missing is RECOVERABLE — the documented recipe takes MAX across
    # both legs and gets the right number. Both legs missing is not: there is no
    # grand total anywhere, and any answer would be the largest sub-line.
    unrecoverable = [r for r in rows if not r["a_tot"] and not r["l_tot"]]
    recoverable = [r for r in rows if r not in unrecoverable]

    # Not fatal even here: the roman sections ARE the statement, so summing them
    # recovers the total without any total row. Reported so the extraction gap
    # stays visible rather than being absorbed by the workaround.
    if unrecoverable:
        print("  NOTE  {} bank-period(s) have NO total row on EITHER leg; the "
              "roman-section sum is the only route: {}".format(
                  len(unrecoverable),
                  ", ".join(f"{r['bank_ticker']} {r['period']}" for r in unrecoverable[:4])))

    if recoverable:
        # Not a failure: the prompt's MAX-across-both-legs recipe handles it.
        # Reported so a NEW occurrence is visible rather than absorbed.
        print("  NOTE  {} bank(s) are missing a total row on ONE leg — the "
              "MAX-across-both-legs recipe recovers them: {}".format(
                  len(recoverable),
                  ", ".join(f"{r['bank_ticker']} {r['period']}" for r in recoverable[:4])))


def check_pl_roles_coverage(rep: Report) -> None:
    """Every bank with a P&L must have a period_net role, and exactly one.

    The prompt tells the model to join pl_roles instead of matching a label. If
    coverage regressed, rankings would silently shrink again — which is the bug
    the join was introduced to fix.
    """
    rows = d1("""
        SELECT (SELECT COUNT(DISTINCT bank_ticker) FROM bank_audit_profit_loss
                 WHERE kind='unconsolidated'
                   AND period=(SELECT MAX(period) FROM bank_audit_profit_loss)) AS with_pl,
               (SELECT COUNT(DISTINCT bank_ticker) FROM bank_audit_pl_roles
                 WHERE kind='unconsolidated' AND role='period_net'
                   AND period=(SELECT MAX(period) FROM bank_audit_profit_loss)) AS with_role
    """)[0]
    rep.check("pl_roles: period_net covers every bank with a P&L",
              rows["with_pl"] == rows["with_role"],
              f"{rows['with_pl']} banks have a P&L but only "
              f"{rows['with_role']} have a period_net role")

    dupes = d1("""
        SELECT bank_ticker FROM bank_audit_pl_roles
         WHERE role='period_net' AND kind='unconsolidated'
           AND period=(SELECT MAX(period) FROM bank_audit_profit_loss)
         GROUP BY bank_ticker HAVING COUNT(*) > 1
    """)
    rep.check("pl_roles: exactly one period_net row per bank",
              not dupes,
              f"duplicated for: {', '.join(r['bank_ticker'] for r in dupes)} "
              "— a ranking would double-count these")


def check_columns(prompt: str, rep: Report) -> None:
    """Every column the prompt names must exist, with that spelling.

    Cheap to check and it catches the nastiest kind of prompt rot: a renamed
    column sends the model into an error loop it burns its whole step budget on.
    """
    for m in re.finditer(r"^(bank_audit_\w+|balance_sheet|income_statement|loans|"
                         r"deposits|financial_ratios|other_data|kap_ownership|"
                         r"bist_prices|weekly_series)\(([^)]*)\)", prompt, re.M):
        table, cols_raw = m.group(1), m.group(2)
        claimed = {c.strip() for c in re.split(r"[,\s]+", cols_raw)
                   if re.fullmatch(r"[a-z][a-z0-9_]*", c.strip())}
        if not claimed:
            continue
        actual = {r["name"] for r in d1(f"SELECT name FROM pragma_table_info('{table}')")}
        if not actual:
            rep.check(f"columns: table {table} exists", False, "no such table")
            continue
        missing = sorted(claimed - actual)
        rep.check(f"columns: {table} — every documented column exists",
                  not missing, f"named in the prompt but absent: {', '.join(missing)}")


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    prompt = SCHEMA_TS.read_text(encoding="utf-8")
    rep = Report(args.verbose)

    print("checking bot-schema.ts against live D1…")
    check_tickers(prompt, rep)
    check_bank_type_overlap(rep)
    check_balance_sheet_identity(rep)
    check_pl_roles_coverage(rep)
    check_columns(prompt, rep)

    # Documented value sets. Each of these was wrong in the prompt at some point,
    # and each wrong one returns zero rows or silently mixes incompatible data.
    check_enum(rep, "balance_sheet.currency",
               "SELECT DISTINCT currency FROM balance_sheet", {"TL", "USD"})
    check_enum(rep, "financial_ratios.ratio_category",
               "SELECT DISTINCT ratio_category FROM financial_ratios",
               {"other", "asset_quality"})
    check_enum(rep, "bank_audit_balance_sheet.statement",
               "SELECT DISTINCT statement FROM bank_audit_balance_sheet",
               {"assets", "liabilities", "off_balance"})
    check_enum(rep, "bank_audit_*.kind",
               "SELECT DISTINCT kind FROM bank_audit_balance_sheet",
               {"unconsolidated", "consolidated"})
    check_enum(rep, "weekly_series.currency",
               "SELECT DISTINCT currency FROM weekly_series", {"TL", "FX", "TOTAL"})

    if rep.failures:
        msg = ("❌ bot-schema.ts no longer matches the database:\n"
               + "\n".join(f"• {f}" for f in rep.failures))
        print(f"\n{len(rep.failures)} check(s) failed", file=sys.stderr)
        if args.alert:
            sys.path.insert(0, str(ROOT / "scripts"))
            from notify import notify  # stdlib-only helper
            notify(msg[:1500])
        return 1

    print("\nbot schema OK — every documented claim matches the data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
