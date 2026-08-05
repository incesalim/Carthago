"""Reporting unit: what denomination a filing's figures are printed in.

The whole sector switched from **Bin TL** (thousands) to **Milyon TL** (millions)
in 2026Q2. Nothing inside a filing can detect that: every structural validator in
this repo — TL+FC=Total, parent=Σchildren, Tier1=CET1+AT1 — is a ratio of figures
that share a scale, so all eleven Q2 filings stayed internally perfect while every
stored figure was wrong by 1000x. See scripts/watch_cross_period.py.

So the unit is read from the filing and the figures are normalised to ONE
denomination before storage. The canonical unit is `bin`, because 4.5 years of
history is already stored that way: the new arrival normalises to the established
base rather than rewriting settled balance-sheet and P&L partitions that are
explicitly frozen. A Milyon filing is therefore multiplied by 1,000.

OLD FILINGS ARE UNAFFECTED, by construction and on purpose:

- every period up to and including `SWEEP_HORIZON` is `bin` by establishment —
  the July sweep read 550 filings, two random draws over all 1,061 R2 PDFs, and
  found no pre-2026Q2 filing that ever used millions. Those partitions resolve to
  `bin` WITHOUT opening the PDF, so a re-extraction of any 2022-2026Q1 partition
  scales by 1 and stores exactly what it stored before;
- a scale factor of 1 is applied as a no-op, not skipped by a branch, so the
  "old" and "new" paths are the same path.

Past the horizon the unit must be READ. If it cannot be read, the partition is
refused: UNKNOWN means "look at this filing", never "assume thousands".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Detection. Lifted verbatim from src/analyst/extract_basis_metadata.py, which
# promoted it from the July bench (scripts/scratch_bench_unit_detection.py).
# 22 pages, not 8: the shorter window missed 15 Q4 filings whose declaration
# lands on p7-p17, behind the full annual audit opinion.
# ---------------------------------------------------------------------------
FRONT_PAGES = 22

UNIT_RE = re.compile(
    r"(bin|milyon|milyar|thousand|million|billion)s?\s+(?:of\s+)?"
    r"(?:t[uü]rk\s+liras[iı]|turkish\s+lira)", re.I)

_NORM = {
    "bin": "bin", "thousand": "bin",
    "milyon": "milyon", "million": "milyon",
    "milyar": "milyar", "billion": "milyar",
}

#: Stored denomination. History is `bin`; everything normalises to it.
CANONICAL_UNIT = "bin"

#: Multiplier that converts a figure printed in <unit> into CANONICAL_UNIT.
UNIT_SCALE: dict[str, int] = {"bin": 1, "milyon": 1_000, "milyar": 1_000_000}

#: Every period up to and including this one is sweep-established `bin`.
SWEEP_HORIZON = "2026Q1"


def _period_key(period: str) -> tuple[int, int]:
    """('2026Q1') -> (2026, 1). Sorts correctly across year boundaries."""
    y, q = period.upper().split("Q")
    return int(y), int(q)


def within_sweep(period: str) -> bool:
    """True when the period predates the Milyon switch and needs no PDF read."""
    return _period_key(period) <= _period_key(SWEEP_HORIZON)


def regex_unit(pages: list[str]) -> str | None:
    """First unit declaration in the front pages, normalised; None = UNKNOWN."""
    for text in pages[:FRONT_PAGES]:
        m = UNIT_RE.search(text)
        if m:
            return _NORM[m.group(1).lower()]
    return None


def detect_unit_from_pdf(pdf_path: str) -> str | None:
    """Read the declaration from the filing. Import is local so snapshot-only
    paths never need PyMuPDF loaded."""
    import fitz  # PyMuPDF — the repo's only sanctioned PDF engine

    with fitz.open(pdf_path) as doc:
        pages = [p.get_text() for p in doc.pages(0, min(FRONT_PAGES, doc.page_count))]
    return regex_unit(pages)


def resolve_unit(period: str, pdf_path: str | None = None) -> str | None:
    """The unit for one partition, or None when it cannot be established.

    Old filings never open the PDF: the sweep settled them. That is what keeps a
    re-extraction of 2022-2026Q1 byte-identical to what is already stored, and
    what stops a detector regression from silently rescaling 4.5 years of data.
    """
    if within_sweep(period):
        return CANONICAL_UNIT
    if pdf_path is None:
        return None
    return detect_unit_from_pdf(pdf_path)


def scale_factor(unit: str | None) -> int:
    """Multiplier to canonical. Raises on an unknown unit — never guesses."""
    if unit is None:
        raise ValueError(
            "reporting unit is UNKNOWN: refusing to store figures at an "
            "unestablished scale. UNKNOWN means 'look at this filing', never "
            "'assume thousands' — a wrong guess is a silent 1000x error that "
            "every in-filing validator will pass.")
    try:
        return UNIT_SCALE[unit]
    except KeyError:
        raise ValueError(f"unrecognised reporting unit {unit!r}; "
                         f"known: {sorted(UNIT_SCALE)}") from None


# ---------------------------------------------------------------------------
# What is money, and what only looks like a number.
#
# Scaling the wrong column is the expensive failure: a ratio multiplied by 1,000
# is as wrong as an amount left unscaled, and neither trips a validator. Both
# sets are exhaustive over every numeric column in every audit table, and
# tests/test_units.py fails if any numeric column is missing from both — so a new
# column cannot slip through unclassified.
# ---------------------------------------------------------------------------
MONEY_COLUMNS: dict[str, frozenset[str]] = {
    "bank_audit_balance_sheet": frozenset({"amount_tl", "amount_fc", "amount_total"}),
    "bank_audit_profit_loss": frozenset({"amount"}),
    "bank_audit_oci": frozenset({"amount"}),
    "bank_audit_cash_flow": frozenset({"amount"}),
    "bank_audit_equity_change": frozenset({
        "paid_in_capital", "share_premium", "share_cancellation_profits",
        "other_capital_reserves", "oci_not_reclassified_1", "oci_not_reclassified_2",
        "oci_not_reclassified_3", "oci_reclassified_1", "oci_reclassified_2",
        "oci_reclassified_3", "profit_reserves", "prior_period_profit_loss",
        "period_net_profit_loss", "total_equity", "minority_interest",
        "total_equity_incl_minority"}),
    "bank_audit_credit_quality": frozenset({
        "stage1_amount", "stage2_amount", "stage3_amount", "total_amount"}),
    "bank_audit_stages": frozenset({
        "stage1_amount", "stage2_amount", "stage3_amount", "total_amount",
        "stage1_ecl", "stage2_ecl", "stage3_ecl", "total_ecl"}),
    "bank_audit_loans_by_sector": frozenset({
        "stage2_amount", "stage3_amount", "ecl_amount"}),
    "bank_audit_npl_movement": frozenset({
        "opening_balance", "additions", "transfers_in", "transfers_out",
        "collections", "write_offs", "sold", "fx_diff", "closing_balance",
        "provision", "net_balance"}),
    "bank_audit_capital": frozenset({
        "cet1_capital", "additional_tier1_capital", "tier1_capital",
        "tier2_capital", "total_capital", "total_rwa"}),
    "bank_audit_fx_position": frozenset({
        "on_bs_assets", "on_bs_liab", "net_on_balance", "net_off_balance",
        "off_bs_receivable", "off_bs_payable", "net_position"}),
    "bank_audit_repricing": frozenset({
        "rate_sensitive_assets", "rate_sensitive_liab", "gap", "cumulative_gap"}),
    "bank_audit_free_provision": frozenset({"free_provision", "free_provision_prior"}),
}

#: Numeric but NOT money. Ratios, percentages, counts, page numbers, ordinals.
#: Verified against 4.5 years of stored values rather than assumed: the capital
#: ratios run 4.85-138 while the capital amounts in the same table average
#: 64,314,574; the stage coverages are fractions 0-0.54; and 925 of 933
#: `lcr_total` values sit below 1000. Nothing in bank_audit_liquidity is money —
#: LCR, NSFR and leverage are all ratios.
NON_MONEY_NUMERIC: dict[str, frozenset[str]] = {
    "bank_audit_balance_sheet": frozenset({"item_order"}),
    "bank_audit_profit_loss": frozenset({"item_order"}),
    "bank_audit_oci": frozenset({"item_order"}),
    "bank_audit_cash_flow": frozenset({"item_order"}),
    "bank_audit_equity_change": frozenset({"item_order", "source_page"}),
    "bank_audit_credit_quality": frozenset({"source_page"}),
    "bank_audit_stages": frozenset({
        "stage1_coverage", "stage2_coverage", "stage3_coverage"}),
    "bank_audit_loans_by_sector": frozenset({"source_page"}),
    "bank_audit_npl_movement": frozenset({"source_page"}),
    "bank_audit_capital": frozenset({
        "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio", "source_page"}),
    "bank_audit_liquidity": frozenset({
        "leverage_ratio", "lcr_total", "lcr_fc", "nsfr", "source_page"}),
    "bank_audit_fx_position": frozenset({"source_page"}),
    "bank_audit_repricing": frozenset({"source_page"}),
    "bank_audit_free_provision": frozenset({"source_page"}),
    "bank_audit_profile": frozenset({
        "branches_domestic", "branches_foreign", "branches_total", "personnel"}),
    "bank_audit_opinion": frozenset({"is_modified", "source_page"}),
    "bank_audit_validation": frozenset({
        "checks_passed", "checks_failed", "checks_skipped"}),
    "bank_audit_extractions": frozenset({
        "rows_bs_assets", "rows_bs_liabilities", "rows_off_balance",
        "rows_profit_loss", "rows_credit_quality", "success", "rows_oci",
        "rows_cash_flow", "rows_equity_change", "rows_fx_position",
        "rows_repricing"}),
    "bank_audit_prose": frozenset({
        "item_order", "section", "page_start", "page_end", "char_count"}),
    "bank_audit_pl_roles": frozenset(),
}


#: Monetary, but NOT scaled at write: built from an already-normalised source.
#: `bank_audit_stages` is derived wholesale from `bank_audit_credit_quality` by
#: scripts/build_bank_audit_stages.py, so its amounts and ECLs arrive already
#: scaled. Scaling them again would be x1,000,000 — and every coverage ratio it
#: computes is amount/amount, so the ratios would still foot perfectly.
DERIVED_MONEY_TABLES: frozenset[str] = frozenset({"bank_audit_stages"})

#: The tables a writer must scale: money, minus the derived ones. Twelve.
RAW_MONEY_TABLES: frozenset[str] = frozenset(MONEY_COLUMNS) - DERIVED_MONEY_TABLES


def money_columns(table: str) -> frozenset[str]:
    """Columns to scale when WRITING `table`. Raises on a table this module has
    never classified: returning an empty set for an unknown name silently skips
    scaling, which is the failure this whole module exists to prevent."""
    if table in DERIVED_MONEY_TABLES:
        raise ValueError(
            f"{table} is derived from an already-normalised source and must not "
            f"be scaled again — that would be x1,000,000, and its coverage "
            f"ratios are amount/amount so they would still foot.")
    if table not in MONEY_COLUMNS and table not in NON_MONEY_NUMERIC:
        raise ValueError(
            f"unknown table {table!r}: classify its numeric columns in "
            f"units.MONEY_COLUMNS / NON_MONEY_NUMERIC before writing to it.")
    return MONEY_COLUMNS.get(table, frozenset())


def scale_amount(value, factor: int):
    """Scale one figure. None stays None — a disclosure never made is not zero,
    and 0 x 1000 is still 0, which is the correct answer for a disclosed zero.

    There is deliberately NO `factor == 1` shortcut anywhere in this module: a
    pre-2026Q2 filing multiplies by 1 and takes exactly the code path a Milyon
    filing takes. A bypass would leave the old path untested by every test that
    exercises the new one, which is how the "old filings are unaffected" claim
    would quietly stop being true.
    """
    if value is None:
        return value
    return value * factor


def scale_mapping(table: str, row: dict, factor: int) -> dict:
    """Return `row` with this table's money columns scaled. Non-money columns
    and NULLs pass through. No factor==1 shortcut — see scale_amount."""
    money = money_columns(table)
    return {k: (scale_amount(v, factor) if k in money else v) for k, v in row.items()}


def scale_sequence(table: str, columns: list[str], row: tuple, factor: int) -> tuple:
    """Positional variant, for the writers that build value tuples.

    Length mismatch RAISES. `zip` would silently truncate to the shorter of the
    two, dropping trailing columns from the scaling — and a money column that
    falls off the end is stored 1000x too small with nothing to notice.
    """
    if len(columns) != len(row):
        raise ValueError(
            f"{table}: {len(columns)} columns but {len(row)} values. Refusing to "
            f"zip-truncate: a money column dropped off the end would be stored "
            f"unscaled and no validator would see it.")
    money = money_columns(table)
    return tuple(scale_amount(v, factor) if c in money else v
                 for c, v in zip(columns, row))


# ---------------------------------------------------------------------------
# Hand-transcribed sources: data/audit_overrides.json, data/manual_statements.json.
#
# A person reads the PDF and types what the page says, so these are SOURCE-NATIVE
# and carry the filing's own unit. Every one of the 457 override entries written
# so far predates the switch and is therefore `bin`, which is why an absent
# `unit` may default — but ONLY for those.
#
# Past the horizon the default is withdrawn. The first Q2 transcription that
# omits the field would otherwise silently recreate the exact 1000x error this
# module exists to prevent: the author reads a Milyon page, types 5,000, and a
# defaulted `bin` stores it a thousandfold small with every identity still
# footing. So post-horizon entries must declare, and a missing or unrecognised
# declaration refuses BEFORE any row is touched.
# ---------------------------------------------------------------------------
def resolve_manual_unit(period: str, declared: str | None) -> str:
    """Unit for a hand-transcribed entry. Raises rather than assume."""
    if declared is not None:
        norm = str(declared).strip().lower()
        if norm not in UNIT_SCALE:
            raise ValueError(
                f"{period}: manual entry declares unit {declared!r}, which is not "
                f"one of {sorted(UNIT_SCALE)}. Refusing before any row is touched.")
        return norm
    if within_sweep(period):
        return CANONICAL_UNIT
    raise ValueError(
        f"{period}: a hand-transcribed entry past {SWEEP_HORIZON} must declare its "
        f'unit (e.g. "unit": "milyon"). The sector switched Bin -> Milyon in '
        f"2026Q2, so defaulting to thousands here would store the figure 1000x "
        f"small while every in-filing identity still foots — the one error no "
        f"validator in this repo can see.")


@dataclass(frozen=True)
class UnitContext:
    """What a filing printed, and the multiplier to canonical `bin`.

    Passed explicitly rather than re-derived per writer, because the writers do
    not have the PDF: `sync_audit_reports` hands `upsert_report` the R2 KEY
    (`akbnk/AKBNK_2026Q2_consolidated.pdf`) while the downloaded file lives in a
    temp dir under a different name, and `load_partition`, `reextract_pl` and
    `backfill_credit_quality` all close their TemporaryDirectory before writing.
    A writer that tried to open `pdf_path` would get a name that is not a file.

    So: resolve ONCE while the local file exists, thread the result, and keep the
    stored R2 key as a separate value used only for provenance.
    """

    source_unit: str
    factor: int

    def __post_init__(self) -> None:
        """A context is only meaningful if the two fields agree.

        Direct construction is the loophole the classmethods close: nothing else
        stops `UnitContext("milyon", 1)`, which says "this filing prints
        millions" and "do not scale" in the same breath — a silent 1000x error
        wearing the type that exists to prevent one. Tests build these by hand,
        so the invariant belongs on the type.
        """
        expected = UNIT_SCALE.get(self.source_unit)
        if expected is None:
            raise ValueError(
                f"unrecognised reporting unit {self.source_unit!r}; "
                f"known: {sorted(UNIT_SCALE)}")
        if self.factor != expected:
            raise ValueError(
                f"inconsistent UnitContext: source_unit={self.source_unit!r} "
                f"implies factor {expected}, got {self.factor}. The two fields "
                f"must agree — a mismatch stores figures at a scale nothing "
                f"declared.")

    @classmethod
    def for_partition(cls, period: str, local_pdf_path: str | None) -> "UnitContext":
        """Resolve from the REAL local file. Raises when it cannot be established.

        `local_pdf_path` must be a path that exists right now — never an R2 key.
        """
        if not within_sweep(period):
            if local_pdf_path is None:
                raise ValueError(
                    f"{period} is past {SWEEP_HORIZON} and no local PDF was given: "
                    f"the reporting unit must be READ from the filing. Resolve it "
                    f"while the temporary file still exists and pass the context in.")
            if not Path(local_pdf_path).is_file():
                raise ValueError(
                    f"{period}: {local_pdf_path!r} is not a readable file. This is "
                    f"the R2-key-versus-temp-path trap: the stored identifier is a "
                    f"key like 'akbnk/AKBNK_2026Q2_consolidated.pdf', not a path. "
                    f"Resolve the unit from the downloaded file.")
        unit = resolve_unit(period, local_pdf_path)
        return cls(source_unit=unit, factor=scale_factor(unit))

    @classmethod
    def manual(cls, period: str, declared: str | None) -> "UnitContext":
        """For a hand-transcribed entry, which carries the filing's own unit."""
        unit = resolve_manual_unit(period, declared)
        return cls(source_unit=unit, factor=scale_factor(unit))

    @classmethod
    def canonical(cls) -> "UnitContext":
        """Values already in `bin` — a derived rebuild, or a legacy repair."""
        return cls(source_unit=CANONICAL_UNIT, factor=1)

    def scale_rows(self, table: str, columns: list[str],
                   rows: list[tuple]) -> list[tuple]:
        """Scale a writer's value tuples. Raises for a derived or unknown table."""
        return [scale_sequence(table, columns, r, self.factor) for r in rows]
