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
 * Each entry corresponds to a single Roman-numeral row in the BRSA
 * template. Items that don't have a row for some bank/period simply
 * render as "—".
 */

export interface StandardLine {
  /** Stable id used as React key. */
  id: string;
  /** Canonical English label shown in the table. */
  label: string;
  /** BRSA hierarchy code (e.g. "I.", "XVI."). */
  hierarchy: string;
  /** Whether to render bold (subtotal / total row). */
  isTotal?: boolean;
}

/** Balance-Sheet Assets — items I through X of the BRSA template. */
export const BS_ASSET_LINES: StandardLine[] = [
  { id: "fa_net", label: "Financial Assets (Net)", hierarchy: "I." },
  { id: "amort_cost", label: "Financial Assets at Amortized Cost (Net)", hierarchy: "II." },
  { id: "held_for_sale", label: "Held-for-Sale & Discontinued Operations Assets", hierarchy: "III." },
  { id: "subsidiaries", label: "Investments in Associates & Subsidiaries", hierarchy: "IV." },
  { id: "ppe", label: "Property, Plant & Equipment (Net)", hierarchy: "V." },
  { id: "intangibles", label: "Intangible Assets (Net)", hierarchy: "VI." },
  { id: "investment_property", label: "Investment Property (Net)", hierarchy: "VII." },
  { id: "current_tax_asset", label: "Current Tax Asset", hierarchy: "VIII." },
  { id: "deferred_tax_asset", label: "Deferred Tax Asset", hierarchy: "IX." },
  { id: "other_assets", label: "Other Assets", hierarchy: "X." },
];

/** Balance-Sheet Liabilities + Equity — items I through XVI of the template. */
export const BS_LIAB_LINES: StandardLine[] = [
  { id: "deposits", label: "Deposits / Funds Collected", hierarchy: "I." },
  { id: "fvtpl_liab", label: "Financial Liabilities at FVTPL", hierarchy: "II." },
  { id: "borrowings", label: "Funds Borrowed", hierarchy: "III." },
  { id: "money_market", label: "Money Market Funds", hierarchy: "IV." },
  { id: "issued_securities", label: "Issued Securities (Net)", hierarchy: "V." },
  { id: "hedging_derivatives", label: "Derivative Financial Liabilities — Hedging", hierarchy: "VI." },
  { id: "lease_liab", label: "Lease Payables", hierarchy: "VII." },
  { id: "provisions", label: "Provisions", hierarchy: "VIII." },
  { id: "current_tax_liab", label: "Current Tax Liability", hierarchy: "IX." },
  { id: "deferred_tax_liab", label: "Deferred Tax Liability", hierarchy: "X." },
  { id: "held_for_sale_liab", label: "Held-for-Sale Liabilities", hierarchy: "XI." },
  { id: "subordinated_debt", label: "Subordinated Debt Instruments", hierarchy: "XII." },
  { id: "other_liab", label: "Other Liabilities", hierarchy: "XIII." },
  { id: "equity", label: "Shareholders' Equity", hierarchy: "XVI.", isTotal: true },
];

/** Income Statement — items I through XX of the template.
 *  We surface the high-frequency rows; sparser items (e.g. XIV, XXIII)
 *  are hidden to keep the table digestible. */
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
