"""Bank-type code namespaces — the single Python mirror of the constants in
`web/app/lib/metrics.ts`.

The BDDK monthly and weekly bulletins reuse the SAME numeric range (10001-100xx)
for DIFFERENT bank groups. That collision has bitten this project before, so the
chart-spec catalog never writes raw codes — specs carry `bank_types_named`
("SECTOR", "PRIVATE", …) and the resolver translates them through the namespace
chosen by the series `source`:

    bddk_monthly  -> MONTHLY
    bddk_weekly   -> WEEKLY

Keep these dicts in sync with metrics.ts (`BANK_TYPES` / `WEEKLY_BANK_TYPES`).
`tests/test_verify_chart_spec.py::test_bank_type_namespaces` asserts the values
below, and any drift between this file and metrics.ts will surface as a failed
`verify[]` point in `scripts/verify_chart_spec.py`.
"""
from __future__ import annotations

# Monthly tables: balance_sheet, financial_ratios, loans, deposits.
# Two partitions each sum to the sector and OVERLAP: by type {10002,10003,10004};
# by ownership {10005,10006,10007}. 10008/9/10 = deposit-bank-only subsets.
MONTHLY: dict[str, str] = {
    "SECTOR": "10001",
    "DEPOSIT": "10002",
    "PARTICIPATION": "10003",
    "DEV_INV": "10004",
    "PRIVATE": "10005",
    "STATE": "10006",
    "FOREIGN": "10007",
    "DEPOSIT_PRIVATE": "10008",
    "DEPOSIT_STATE": "10009",
    "DEPOSIT_FOREIGN": "10010",
}

# Weekly bulletin (weekly_series) — same numbers, different groups.
WEEKLY: dict[str, str] = {
    "SECTOR": "10001",
    "PRIVATE": "10003",
    "STATE": "10004",
    "FOREIGN": "10005",
    "PARTICIPATION": "10006",
    "DEV_INV": "10007",
}

# Map a series `source` to its namespace dict.
NAMESPACES: dict[str, dict[str, str]] = {
    "bddk_monthly": MONTHLY,
    "bddk_weekly": WEEKLY,
}


def resolve_codes(source: str, names: list[str]) -> list[str]:
    """Translate `bank_types_named` (e.g. ['SECTOR']) to numeric codes in the
    namespace for `source`. Raises on an unknown source or name so a typo fails
    loudly instead of silently selecting the wrong banks."""
    ns = NAMESPACES.get(source)
    if ns is None:
        raise ValueError(
            f"source {source!r} has no bank-type namespace "
            f"(only {sorted(NAMESPACES)} use bank_types_named)"
        )
    codes: list[str] = []
    for name in names:
        code = ns.get(name)
        if code is None:
            raise ValueError(
                f"unknown bank type {name!r} for source {source!r}; "
                f"valid names: {sorted(ns)}"
            )
        codes.append(code)
    return codes
