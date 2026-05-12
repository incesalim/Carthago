/**
 * Standard line catalog for the per-bank financials view.
 *
 * BRSA Financial Reports use a fixed Roman-numeral hierarchy across every
 * bank, but the *labels* are inconsistent (Turkish vs. English, deposit
 * vs. participation banks: "Mevduat" ↔ "Toplanan Fonlar" / "Faiz Gelirleri"
 * ↔ "Kâr Payı Gelirleri", plus extraction noise). We standardize the
 * display by mapping (statement, hierarchy) → canonical English label
 * and ignoring the raw `item_name` entirely.
 *
 * The mapping was verified against real D1 rows for AKBNK 2024Q4 / 2025Q4
 * unconsolidated — see commit history for the queries that confirmed each
 * Roman numeral's content.
 */

export interface StandardLine {
  /** Stable id used as React key. */
  id: string;
  /** Canonical English label shown in the table. */
  label: string;
  /** BRSA hierarchy code (e.g. "I.", "2.1", "1.1.1", "XVI."). */
  hierarchy: string;
  /** Render bold — used for category subtotals (Roman numerals at indent 0)
   *  and P&L subtotal rows (Net Interest Income, Pre-tax Profit, etc.). */
  bold?: boolean;
}

/** Visual indent level derived from a hierarchy code.
 *    "I.", "II.", ... → 0   (Roman numeral, top-level)
 *    "1.1", "2.3", ... → 1  (one-dot sub-item)
 *    "1.1.1", "4.3.2" → 2   (two-dot sub-sub-item)
 *    "1.1.1.x"        → 3   (rarely used) */
export function indentLevel(hierarchy: string): number {
  if (/^[IVXLCDM]+\.$/.test(hierarchy)) return 0;
  return (hierarchy.match(/\./g) || []).length;
}

/** Balance-Sheet Assets — replicates the rows the user highlighted on the
 *  BRSA template, in the same order. Roman numerals (top-level) carry the
 *  category subtotal value and render bold; numeric sub-items render
 *  indented with hierarchy depth driving visual nesting. */
export const BS_ASSET_LINES: StandardLine[] = [
  { id: "fa_net",                  label: "Financial Assets (Net)",                                          hierarchy: "I.",    bold: true },
  { id: "cash_eq",                 label: "Cash and Cash Equivalents",                                       hierarchy: "1.1" },
  { id: "cash_cb",                 label: "Cash and Central Bank Balances",                                  hierarchy: "1.1.1" },
  { id: "banks",                   label: "Banks",                                                           hierarchy: "1.1.2" },
  { id: "fvtpl",                   label: "Financial Assets at FVTPL",                                       hierarchy: "1.2" },
  { id: "fvoci",                   label: "Financial Assets at FVOCI",                                       hierarchy: "1.3" },
  { id: "derivatives",             label: "Derivative Financial Assets",                                     hierarchy: "1.4" },
  { id: "amort_cost",              label: "Financial Assets at Amortized Cost (Net)",                        hierarchy: "II.",   bold: true },
  { id: "loans",                   label: "Loans",                                                           hierarchy: "2.1" },
  { id: "lease_recv",              label: "Lease Receivables",                                               hierarchy: "2.2" },
  { id: "factoring_recv",          label: "Factoring Receivables",                                           hierarchy: "2.3" },
  { id: "other_amort_cost",        label: "Other Financial Assets at Amortized Cost",                        hierarchy: "2.4" },
  { id: "held_for_sale",           label: "Held-for-Sale and Discontinued Operations Assets (Net)",          hierarchy: "III." },
  { id: "subsidiaries",            label: "Investments in Subsidiaries and Associates",                      hierarchy: "IV.",   bold: true },
  { id: "associates",              label: "Associates (Net)",                                                hierarchy: "4.1" },
  { id: "associates_non_cons",     label: "Non-Consolidated",                                                hierarchy: "4.1.2" },
  { id: "subsidiaries_net",        label: "Subsidiaries (Net)",                                              hierarchy: "4.2" },
  { id: "joint_ventures",          label: "Jointly Controlled Entities (Net)",                               hierarchy: "4.3" },
  { id: "joint_ventures_non_cons", label: "Non-Consolidated",                                                hierarchy: "4.3.2" },
  { id: "ppe",                     label: "Property, Plant & Equipment (Net)",                               hierarchy: "V." },
  { id: "intangibles",             label: "Intangible Assets (Net)",                                         hierarchy: "VI." },
  { id: "investment_property",     label: "Investment Property (Net)",                                       hierarchy: "VII." },
  { id: "current_tax_asset",       label: "Current Tax Asset",                                               hierarchy: "VIII." },
  { id: "deferred_tax_asset",      label: "Deferred Tax Asset",                                              hierarchy: "IX." },
  { id: "other_assets",            label: "Other Assets",                                                    hierarchy: "X." },
];

/** Roman-numeral subtotals to sum for Total Assets. Excludes the "Loans"
 *  sub-item (2.1) since 2.1 is already inside II.. */
export const BS_ASSET_ROMAN_HIERARCHIES = [
  "I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.", "IX.", "X.",
];

/** Balance-Sheet Liabilities (+ Equity at the end).
 *  Verified from real AKBNK data 2024Q4/2025Q4 — BRSA's actual ordering
 *  is *not* what an outsider would guess from looking at IFRS templates. */
export const BS_LIAB_LINES: StandardLine[] = [
  { id: "deposits", label: "Deposits / Funds Collected", hierarchy: "I." },
  { id: "borrowings", label: "Funds Borrowed", hierarchy: "II." },
  { id: "money_market", label: "Money Market Borrowings", hierarchy: "III." },
  { id: "issued_securities", label: "Issued Securities (Net)", hierarchy: "IV." },
  { id: "funds_sub", label: "Funds (Sub-Borrowed)", hierarchy: "V." },
  { id: "fvtpl_liab", label: "Financial Liabilities at FVTPL", hierarchy: "VI." },
  { id: "derivatives_liab", label: "Derivative Financial Liabilities", hierarchy: "VII." },
  { id: "factoring", label: "Factoring Payables", hierarchy: "VIII." },
  { id: "lease_liab", label: "Lease Payables (Net)", hierarchy: "IX." },
  { id: "provisions", label: "Provisions", hierarchy: "X." },
  { id: "current_tax_liab", label: "Current Tax Liability", hierarchy: "XI." },
  { id: "deferred_tax_liab", label: "Deferred Tax Liability", hierarchy: "XII." },
  { id: "held_for_sale_liab", label: "Held-for-Sale Liabilities", hierarchy: "XIII." },
  { id: "subordinated_debt", label: "Subordinated Debt Instruments", hierarchy: "XIV." },
  { id: "other_liab", label: "Other Liabilities", hierarchy: "XV." },
  { id: "equity", label: "Shareholders' Equity", hierarchy: "XVI.", bold: true },
];

/** Roman-numeral parents used to sum Total Liabilities (excluding equity). */
export const BS_LIAB_ROMAN_HIERARCHIES = [
  "I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.",
  "IX.", "X.", "XI.", "XII.", "XIII.", "XIV.", "XV.",
];

/** Equity hierarchy code, summed separately for the L+E grand total. */
export const BS_EQUITY_HIERARCHY = "XVI.";

/** Income Statement. */
export const PL_LINES: StandardLine[] = [
  { id: "interest_income", label: "Interest / Profit Share Income", hierarchy: "I." },
  { id: "interest_expense", label: "Interest / Profit Share Expense", hierarchy: "II." },
  { id: "net_interest", label: "Net Interest / Profit Share Income", hierarchy: "III.", bold: true },
  { id: "net_fees", label: "Net Fees & Commissions", hierarchy: "IV." },
  { id: "dividend_income", label: "Dividend Income", hierarchy: "V." },
  { id: "trading_income", label: "Net Trading Income / (Loss)", hierarchy: "VI." },
  { id: "other_op_income", label: "Other Operating Income", hierarchy: "VII." },
  { id: "gross_op_profit", label: "Gross Operating Profit", hierarchy: "VIII.", bold: true },
  { id: "ecl_provisions", label: "Expected Credit Loss Provisions", hierarchy: "IX." },
  { id: "other_provisions", label: "Other Provisions for Losses", hierarchy: "X." },
  { id: "personnel_expense", label: "Personnel Expense", hierarchy: "XI." },
  { id: "other_op_expense", label: "Other Operating Expenses", hierarchy: "XII." },
  { id: "net_op_profit", label: "Net Operating Profit / (Loss)", hierarchy: "XIII.", bold: true },
  { id: "pretax_profit", label: "Pre-tax Profit / (Loss)", hierarchy: "XVII.", bold: true },
  { id: "tax_provision", label: "Tax Provision", hierarchy: "XVIII." },
  { id: "net_profit", label: "Net Period Profit / (Loss)", hierarchy: "XIX.", bold: true },
];
