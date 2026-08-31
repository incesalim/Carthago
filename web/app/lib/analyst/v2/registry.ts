/**
 * Analyst V2 — the statement registry: the complete, allowlisted map of what
 * the research tools may read. Every table, every column, the row identity,
 * and the caveats a reader must know (the corpus rules bought with production
 * wrong-answers live HERE, not in prompt prose).
 *
 * This registry is the exact opposite of V1's `series.ts`: nothing is
 * reduced. The equity-change matrix ships with all fourteen component
 * columns; OCI and cash flow ship whole; labels ship with their known
 * fragility stated.
 */
import { BANK_COUNT } from "../../bank_names";

export interface StatementSpec {
  /** The SQLite/D1 table. */
  table: string;
  /** Extra fixed WHERE fragment (parameter-free, allowlisted here only). */
  where?: string;
  /** Columns returned, in order. Never `*` — the allowlist IS the contract. */
  columns: string[];
  /** Columns that identify a row across periods (for history + joins). */
  rowIdentity: string[];
  /** Numeric columns a scout/ranker may difference. */
  numericColumns: string[];
  /** Has a period_type column (current|prior). */
  hasPeriodType: boolean;
  /** Carries source_page. */
  hasSourcePage: boolean;
  /** Non-obvious reading rules — surfaced on every tool result. */
  caveats: string[];
}

export const STATEMENTS: Record<string, StatementSpec> = {
  balance_sheet_assets: {
    table: "bank_audit_balance_sheet",
    where: "statement = 'assets'",
    columns: ["item_order", "hierarchy", "item_name", "footnote", "amount_tl", "amount_fc", "amount_total"],
    rowIdentity: ["hierarchy", "item_name"],
    numericColumns: ["amount_tl", "amount_fc", "amount_total"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: [
      "the grand-total row has hierarchy='' (empty), never a label match — labels vary by language and sometimes fuse",
      "total assets = MAX(amount_total) across BOTH legs; a sub-line can never exceed it",
      "amounts are THOUSAND TL; NULL means not printed, never zero",
    ],
  },
  balance_sheet_liabilities: {
    table: "bank_audit_balance_sheet",
    where: "statement = 'liabilities'",
    columns: ["item_order", "hierarchy", "item_name", "footnote", "amount_tl", "amount_fc", "amount_total"],
    rowIdentity: ["hierarchy", "item_name"],
    numericColumns: ["amount_tl", "amount_fc", "amount_total"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: [
      "deposits/funds-collected is usually the FIRST line; equity sections sit at the bottom",
      "the grand-total row has hierarchy=''; amounts are THOUSAND TL",
    ],
  },
  off_balance: {
    table: "bank_audit_balance_sheet",
    where: "statement = 'off_balance'",
    columns: ["item_order", "hierarchy", "item_name", "footnote", "amount_tl", "amount_fc", "amount_total"],
    rowIdentity: ["hierarchy", "item_name"],
    numericColumns: ["amount_tl", "amount_fc", "amount_total"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: ["commitments/guarantees ladder — a BRSA primary statement, not a note"],
  },
  profit_loss: {
    table: "bank_audit_profit_loss",
    columns: ["item_order", "hierarchy", "item_name", "footnote", "amount"],
    rowIdentity: ["hierarchy", "item_name"],
    numericColumns: ["amount"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: [
      "amount is YTD-CUMULATIVE within the year: a single quarter = YTD(Qn) − YTD(Qn−1)",
      "row ordinals differ across template generations — match rows by label meaning, not roman numeral alone",
      "bottom-line net profit is the pl_roles 'period_net' row; other roles: gross, net_op, pretax, tax, cont_net, disc_net, opex_personnel, opex_other",
    ],
  },
  oci: {
    table: "bank_audit_oci",
    columns: ["item_order", "hierarchy", "item_name", "footnote", "amount"],
    rowIdentity: ["hierarchy", "item_name"],
    numericColumns: ["amount"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: ["YTD-cumulative like the P&L; signs follow the filing"],
  },
  cash_flow: {
    table: "bank_audit_cash_flow",
    columns: ["item_order", "hierarchy", "item_name", "footnote", "amount"],
    rowIdentity: ["hierarchy", "item_name"],
    numericColumns: ["amount"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: [
      "YTD-cumulative; this lane historically had the WEAKEST validation coverage (~80% of injected errors passed) — read with the partition's validation status",
    ],
  },
  equity_change: {
    table: "bank_audit_equity_change",
    columns: [
      "item_order", "hierarchy", "item_name", "paid_in_capital", "share_premium",
      "share_cancellation_profits", "other_capital_reserves",
      "oci_not_reclassified_1", "oci_not_reclassified_2", "oci_not_reclassified_3",
      "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
      "profit_reserves", "prior_period_profit_loss", "period_net_profit_loss",
      "total_equity", "minority_interest", "total_equity_incl_minority", "source_page",
    ],
    rowIdentity: ["item_order", "item_name"],
    numericColumns: [
      "paid_in_capital", "share_premium", "share_cancellation_profits", "other_capital_reserves",
      "oci_not_reclassified_1", "oci_not_reclassified_2", "oci_not_reclassified_3",
      "oci_reclassified_1", "oci_reclassified_2", "oci_reclassified_3",
      "profit_reserves", "prior_period_profit_loss", "period_net_profit_loss",
      "total_equity", "minority_interest", "total_equity_incl_minority",
    ],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: [
      "a WIDE MATRIX: each row is a movement line, each column an equity component; a row's total_equity is that movement's impact",
      "the opening row is the first hierarchy-'' or roman-I row; the closing row is the LAST hierarchy-'' row (label ~'Balances at end of the period')",
      "row labels can be template-shifted on some banks (a label may sit one row off its numbers) — reconcile by arithmetic, not by label alone",
      "the prior block (period_type='prior') is the prior YEAR'S SAME QUARTER, not year-end",
      "this lane has open validation failures on several banks — always read get_validation_status alongside",
    ],
  },
  npl_movement: {
    table: "bank_audit_npl_movement",
    columns: [
      "group_code", "opening_balance", "additions", "transfers_in", "transfers_out",
      "collections", "write_offs", "sold", "fx_diff", "accrual_movement", "closing_balance", "provision",
      "net_balance", "source_page",
    ],
    rowIdentity: ["group_code"],
    numericColumns: [
      "opening_balance", "additions", "transfers_in", "transfers_out", "collections",
      "write_offs", "sold", "fx_diff", "accrual_movement", "closing_balance", "provision", "net_balance",
    ],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: [
      "YTD within the year: opening = start of YEAR (= prior year-end closing) for every quarter",
      "group_code III/IV/V are the BRSA loan groups (substandard/doubtful/loss), not IFRS stages",
      "transfers are BETWEEN groups — the table foots per group only with them included",
      "accrual_movement is the signed movement of NPL interest/profit-share accruals, separate from fx_diff; NULL means not separately disclosed",
    ],
  },
  credit_quality: {
    table: "bank_audit_credit_quality",
    columns: ["section", "stage1_amount", "stage2_amount", "stage3_amount", "total_amount", "heading_snippet", "source_page"],
    rowIdentity: ["section"],
    numericColumns: ["stage1_amount", "stage2_amount", "stage3_amount", "total_amount"],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: [
      "stage columns are SECTION-DEPENDENT: in the npl_brsa_* sections they hold BRSA groups III/IV/V, not IFRS stages",
      "prefer sections loans_by_stage / npl_brsa_gross / npl_brsa_provision / npl_brsa_net / loans_ecl_expense — the legacy sections cover ≤2 banks",
      "prior columns in this lane were historically unvalidated — treat prior-side anomalies as possible extraction defects first",
    ],
  },
  capital: {
    table: "bank_audit_capital",
    columns: [
      "cet1_capital", "additional_tier1_capital", "tier1_capital", "tier2_capital",
      "total_capital", "total_rwa", "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio", "source_page",
    ],
    rowIdentity: [],
    numericColumns: [
      "cet1_capital", "additional_tier1_capital", "tier1_capital", "tier2_capital",
      "total_capital", "total_rwa", "cet1_ratio", "tier1_ratio", "capital_adequacy_ratio",
    ],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: ["ratios are PERCENT numbers (16.2 = 16.2%); capital and RWA are thousand TL", "the prior column is the prior YEAR-END for every quarter"],
  },
  liquidity: {
    table: "bank_audit_liquidity",
    columns: ["leverage_ratio", "lcr_total", "lcr_fc", "nsfr", "source_page"],
    rowIdentity: [],
    numericColumns: ["leverage_ratio", "lcr_total", "lcr_fc", "nsfr"],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: ["nsfr is NULL before 2024Q1 fleet-wide — a disclosure gap, not a zero"],
  },
  fx_position: {
    table: "bank_audit_fx_position",
    columns: [
      "currency", "on_bs_assets", "on_bs_liab", "net_on_balance", "net_off_balance",
      "off_bs_receivable", "off_bs_payable", "net_position",
    ],
    rowIdentity: ["currency"],
    numericColumns: [
      "on_bs_assets", "on_bs_liab", "net_on_balance", "net_off_balance",
      "off_bs_receivable", "off_bs_payable", "net_position",
    ],
    hasPeriodType: true,
    hasSourcePage: false,
    caveats: ["currency='TOTAL' is a ROLLUP of USD/EUR/OTHER — never sum across currencies"],
  },
  repricing: {
    table: "bank_audit_repricing",
    columns: ["bucket", "rate_sensitive_assets", "rate_sensitive_liab", "gap", "cumulative_gap", "source_page"],
    rowIdentity: ["bucket"],
    numericColumns: ["rate_sensitive_assets", "rate_sensitive_liab", "gap", "cumulative_gap"],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: [`bucket 'total' is a rollup; exclude legacy 'b1'..'b8' rows unless asked; ~29 of ${BANK_COUNT} banks covered`],
  },
  stages: {
    table: "bank_audit_stages",
    columns: [
      "stage1_amount", "stage2_amount", "stage3_amount", "total_amount",
      "stage1_ecl", "stage2_ecl", "stage3_ecl", "total_ecl",
      "stage1_coverage", "stage2_coverage", "stage3_coverage",
    ],
    rowIdentity: [],
    numericColumns: [
      "stage1_amount", "stage2_amount", "stage3_amount", "total_amount",
      "stage1_ecl", "stage2_ecl", "stage3_ecl", "total_ecl",
      "stage1_coverage", "stage2_coverage", "stage3_coverage",
    ],
    hasPeriodType: true,
    hasSourcePage: false,
    caveats: [
      "DERIVED from credit_quality's loans_by_stage — not a printed statement",
      "coverage columns are FRACTIONS (0.629 = 62.9%), unlike capital's percent ratios",
      "total_amount = the gross loan book (stage1+2+3) — the structured 'total loans'",
    ],
  },
  free_provision: {
    table: "bank_audit_free_provision",
    columns: ["free_provision", "free_provision_prior", "source_page", "source_text"],
    rowIdentity: [],
    numericColumns: ["free_provision", "free_provision_prior"],
    hasPeriodType: false,
    hasSourcePage: true,
    caveats: [
      "stocks, not flows: free_provision is the period-end stock, free_provision_prior the prior YEAR-END comparative; YTD release = prior − current",
      "absence of a row means the bank discloses no free provision — that is N/A, not zero",
    ],
  },
  loans_by_sector: {
    table: "bank_audit_loans_by_sector",
    columns: ["sector", "stage2_amount", "stage3_amount", "ecl_amount", "raw_label", "source_page"],
    rowIdentity: ["sector"],
    numericColumns: ["stage2_amount", "stage3_amount", "ecl_amount"],
    hasPeriodType: true,
    hasSourcePage: true,
    caveats: [
      "ANNUAL ONLY (Q4 periods); sector mixes leaves and rollups ('total', 'agri_total', 'mfg_total', 'svc_total' roll up) — never sum the column",
      "gross loans per sector are NOT stored — only stage2/stage3/ecl",
    ],
  },
  profile: {
    table: "bank_audit_profile",
    columns: ["branches_domestic", "branches_foreign", "branches_total", "personnel"],
    rowIdentity: [],
    numericColumns: ["branches_domestic", "branches_foreign", "branches_total", "personnel"],
    hasPeriodType: false,
    hasSourcePage: false,
    caveats: ["incomplete and uneven — digital banks have no branches; ATBANK/TSKB file annually"],
  },
  opinion: {
    table: "bank_audit_opinion",
    columns: ["opinion_type", "is_modified", "report_kind", "auditor", "language", "basis_text", "source_page"],
    rowIdentity: [],
    numericColumns: [],
    hasPeriodType: false,
    hasSourcePage: true,
    caveats: [
      "basis_text is in the FILING'S language (tr or en), one row per filing; the qualification sits in the leading ~600 chars — the tail can over-run into Key Audit Matters",
      "report_kind: Q1–Q3 = review (limited/negative assurance), Q4 = audit",
    ],
  },
};

export const STATEMENT_KEYS = Object.keys(STATEMENTS);

/** Reconciliations the reconcile tool can compute, by name. */
export const RECONCILIATIONS = [
  "bs_legs_balance",
  "equity_opening_to_closing",
  "equity_net_profit_vs_pl",
  "equity_closing_vs_balance_sheet",
  "npl_movement_footing",
] as const;
export type ReconciliationName = (typeof RECONCILIATIONS)[number];

/** Metrics the peer tool can compare, by name. */
export const PEER_METRICS = [
  "total_assets", "car", "cet1", "npl_ratio_pct", "stage2_ratio_pct",
  "stage3_coverage_pct", "roe_ttm_pct",
] as const;
export type PeerMetric = (typeof PEER_METRICS)[number];
