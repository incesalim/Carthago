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
  /** BRSA hierarchy code (e.g. "I.", "2.1", "XVI."). */
  hierarchy: string;
  /** Whether to render bold (subtotal / total row). */
  isTotal?: boolean;
  /** Visually indent (used for sub-items shown alongside a parent). */
  indent?: boolean;
}

/** Balance-Sheet Assets.
 *  Roman numerals are the BRSA template's top-level rows; sub-items
 *  (2.1 etc.) are pulled in where the breakdown matters for a bank reader
 *  (mainly "Loans" — the dominant asset for any commercial bank). */
export const BS_ASSET_LINES: StandardLine[] = [
  { id: "fa_net", label: "Financial Assets (Net)", hierarchy: "I." },
  { id: "amort_cost", label: "Financial Assets at Amortized Cost (Net)", hierarchy: "II." },
  { id: "loans", label: "of which: Loans (Net)", hierarchy: "2.1", indent: true },
  { id: "held_for_sale", label: "Held-for-Sale Assets", hierarchy: "III." },
  { id: "subsidiaries", label: "Investments in Associates & Subsidiaries", hierarchy: "IV." },
  { id: "ppe", label: "Property, Plant & Equipment (Net)", hierarchy: "V." },
  { id: "intangibles", label: "Intangible Assets (Net)", hierarchy: "VI." },
  { id: "investment_property", label: "Investment Property (Net)", hierarchy: "VII." },
  { id: "current_tax_asset", label: "Current Tax Asset", hierarchy: "VIII." },
  { id: "deferred_tax_asset", label: "Deferred Tax Asset", hierarchy: "IX." },
  { id: "other_assets", label: "Other Assets", hierarchy: "X." },
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
  { id: "equity", label: "Shareholders' Equity", hierarchy: "XVI.", isTotal: true },
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
  { id: "net_interest", label: "Net Interest / Profit Share Income", hierarchy: "III.", isTotal: true },
  { id: "net_fees", label: "Net Fees & Commissions", hierarchy: "IV." },
  { id: "dividend_income", label: "Dividend Income", hierarchy: "V." },
  { id: "trading_income", label: "Net Trading Income / (Loss)", hierarchy: "VI." },
  { id: "other_op_income", label: "Other Operating Income", hierarchy: "VII." },
  { id: "gross_op_profit", label: "Gross Operating Profit", hierarchy: "VIII.", isTotal: true },
  { id: "ecl_provisions", label: "Expected Credit Loss Provisions", hierarchy: "IX." },
  { id: "other_provisions", label: "Other Provisions for Losses", hierarchy: "X." },
  { id: "personnel_expense", label: "Personnel Expense", hierarchy: "XI." },
  { id: "other_op_expense", label: "Other Operating Expenses", hierarchy: "XII." },
  { id: "net_op_profit", label: "Net Operating Profit / (Loss)", hierarchy: "XIII.", isTotal: true },
  { id: "pretax_profit", label: "Pre-tax Profit / (Loss)", hierarchy: "XVII.", isTotal: true },
  { id: "tax_provision", label: "Tax Provision", hierarchy: "XVIII." },
  { id: "net_profit", label: "Net Period Profit / (Loss)", hierarchy: "XIX.", isTotal: true },
];
