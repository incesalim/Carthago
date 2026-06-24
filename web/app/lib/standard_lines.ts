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
  /** Visual-only section title (no value cells) — used for the cash-flow
   *  Operating / Investing / Financing section headers, which most banks don't
   *  file as data rows. The `hierarchy` is a sentinel that never matches data. */
  header?: boolean;
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
  { id: "ecl_cash",                label: "Expected Credit Losses (-)",                                      hierarchy: "1.1.ecl" },
  { id: "fvtpl",                   label: "Financial Assets at FVTPL",                                       hierarchy: "1.2" },
  { id: "fvoci",                   label: "Financial Assets at FVOCI",                                       hierarchy: "1.3" },
  { id: "derivatives",             label: "Derivative Financial Assets",                                     hierarchy: "1.4" },
  { id: "amort_cost",              label: "Financial Assets at Amortized Cost (Net)",                        hierarchy: "II.",   bold: true },
  { id: "loans",                   label: "Loans",                                                           hierarchy: "2.1" },
  { id: "lease_recv",              label: "Lease Receivables",                                               hierarchy: "2.2" },
  { id: "factoring_recv",          label: "Factoring Receivables",                                           hierarchy: "2.3" },
  { id: "securities_amc",          label: "Securities at Amortized Cost",                                    hierarchy: "2.3" },
  { id: "other_amort_cost",        label: "Other Financial Assets at Amortized Cost",                        hierarchy: "2.4" },
  { id: "ecl_loans",               label: "Expected Credit Losses (-)",                                      hierarchy: "2.ecl" },
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
 *  Replicates the rows the user highlighted on the BRSA liabilities
 *  template, in the same order. Roman numerals (top-level) render bold;
 *  numeric sub-items render indented. Real AKBNK data verifies the
 *  Roman-numeral mapping (e.g. II = ALINAN KREDİLER, III = PARA
 *  PİYASALARINA BORÇLAR, IV = İHRAÇ EDİLEN MENKUL KIYMETLER, ...). */
export const BS_LIAB_LINES: StandardLine[] = [
  { id: "deposits",            label: "Deposits / Funds Collected",            hierarchy: "I.",     bold: true },
  { id: "borrowings",          label: "Funds Borrowed",                         hierarchy: "II.",    bold: true },
  { id: "money_market",        label: "Money Market Borrowings",                hierarchy: "III.",   bold: true },
  { id: "issued_securities",   label: "Issued Securities (Net)",                hierarchy: "IV.",    bold: true },
  { id: "bonds",               label: "Bonds",                                  hierarchy: "4.3" },
  { id: "funds_sub",           label: "Funds (Sub-Borrowed)",                   hierarchy: "V.",     bold: true },
  { id: "fvtpl_liab",          label: "Financial Liabilities at FVTPL",         hierarchy: "VI.",    bold: true },
  { id: "derivatives_liab",    label: "Derivative Financial Liabilities",       hierarchy: "VII.",   bold: true },
  { id: "factoring",           label: "Factoring Payables",                     hierarchy: "VIII.",  bold: true },
  { id: "lease_liab",          label: "Lease Payables (Net)",                   hierarchy: "IX.",    bold: true },
  { id: "provisions",          label: "Provisions",                             hierarchy: "X.",     bold: true },
  { id: "current_tax_liab",    label: "Current Tax Liability",                  hierarchy: "XI.",    bold: true },
  { id: "deferred_tax_liab",   label: "Deferred Tax Liability",                 hierarchy: "XII.",   bold: true },
  { id: "held_for_sale_liab",  label: "Held-for-Sale and Discontinued Liabilities (Net)", hierarchy: "XIII.",  bold: true },
  { id: "subordinated_debt",   label: "Subordinated Debt Instruments",          hierarchy: "XIV.",   bold: true },
  { id: "subordinated_loans",  label: "Loans (Subordinated)",                   hierarchy: "14.1" },
  { id: "other_liab",          label: "Other Liabilities",                      hierarchy: "XV.",    bold: true },
  // Equity (XVI) + selected sub-items. The page injects the synthetic
  // "Total Liabilities" subtotal row *before* the equity block so these
  // sit visually under their parent equity row.
  { id: "equity",              label: "Shareholders' Equity",                   hierarchy: "XVI.",   bold: true },
  { id: "capital_reserves",    label: "Capital Reserves",                       hierarchy: "16.2" },
  { id: "profit_reserves",     label: "Profit Reserves",                        hierarchy: "16.5" },
  { id: "legal_reserves",      label: "Legal Reserves",                         hierarchy: "16.5.1" },
];

/** Roman-numeral parents used to sum Total Liabilities (excluding equity). */
export const BS_LIAB_ROMAN_HIERARCHIES = [
  "I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.",
  "IX.", "X.", "XI.", "XII.", "XIII.", "XIV.", "XV.",
];

/** Equity hierarchy code, summed separately for the L+E grand total. */
export const BS_EQUITY_HIERARCHY = "XVI.";

/** Participation banks (BDDK type 10003: Kuveyt, Vakıf Katılım, Ziraat Katılım,
 *  Albaraka, Türkiye Finans, Emlak) file the BRSA *participation* balance sheet,
 *  whose LIABILITIES side has fewer roman line-items than the deposit template —
 *  most importantly equity sits at XIV., not XVI. Applying the deposit catalog
 *  above to them mislabels every row from VI. down (e.g. equity rendered as
 *  "Subordinated Debt Instruments", the real "Shareholders' Equity" row blank,
 *  and the Total-Liabilities subtotal overstated by equity). This parallel
 *  catalog maps the participation liabilities layout. The asset + income-
 *  statement hierarchies ARE identical to deposit banks, so only liabilities
 *  need a variant. Verified identical across all six participation banks. */
export const BS_LIAB_LINES_PARTICIPATION: StandardLine[] = [
  { id: "p_funds_collected",  label: "Deposits / Funds Collected",               hierarchy: "I.",    bold: true },
  { id: "p_funds_borrowed",   label: "Funds Borrowed",                           hierarchy: "II.",   bold: true },
  { id: "p_money_market",     label: "Money Market Borrowings",                  hierarchy: "III.",  bold: true },
  { id: "p_issued_sec",       label: "Issued Securities (Net)",                  hierarchy: "IV.",   bold: true },
  { id: "p_fvtpl",            label: "Financial Liabilities at FVTPL",           hierarchy: "V.",    bold: true },
  { id: "p_derivatives",      label: "Derivative Financial Liabilities",         hierarchy: "VI.",   bold: true },
  { id: "p_lease",            label: "Lease Payables (Net)",                     hierarchy: "VII.",  bold: true },
  { id: "p_provisions",       label: "Provisions",                               hierarchy: "VIII.", bold: true },
  { id: "p_current_tax",      label: "Current Tax Liability",                    hierarchy: "IX.",   bold: true },
  { id: "p_deferred_tax",     label: "Deferred Tax Liability",                   hierarchy: "X.",    bold: true },
  { id: "p_held_for_sale",    label: "Held-for-Sale and Discontinued Liabilities (Net)", hierarchy: "XI.", bold: true },
  { id: "p_subordinated",     label: "Subordinated Loans",                       hierarchy: "XII.",  bold: true },
  { id: "p_sub_loans",        label: "Loans (Subordinated)",                     hierarchy: "12.1" },
  { id: "p_other_liab",       label: "Other Liabilities",                        hierarchy: "XIII.", bold: true },
  // Equity (XIV) + selected sub-items. The page injects the synthetic "Total
  // Liabilities" subtotal before the equity block, as with deposit banks.
  { id: "p_equity",           label: "Shareholders' Equity",                     hierarchy: "XIV.",  bold: true },
  { id: "p_paid_in",          label: "Paid-In Capital",                          hierarchy: "14.1" },
  { id: "p_capital_reserves", label: "Capital Reserves",                         hierarchy: "14.2" },
  { id: "p_profit_reserves",  label: "Profit Reserves",                          hierarchy: "14.5" },
  { id: "p_legal_reserves",   label: "Legal Reserves",                           hierarchy: "14.5.1" },
  { id: "p_profit_loss",      label: "Profit or Loss",                           hierarchy: "14.6" },
];

/** Roman parents summed for participation banks' Total Liabilities (excludes
 *  equity, which is XIV. for these banks). */
export const BS_LIAB_ROMAN_HIERARCHIES_PARTICIPATION = [
  "I.", "II.", "III.", "IV.", "V.", "VI.", "VII.",
  "VIII.", "IX.", "X.", "XI.", "XII.", "XIII.",
];

/** Equity hierarchy for participation banks (deposit banks use XVI.). */
export const BS_EQUITY_HIERARCHY_PARTICIPATION = "XIV.";

/** Asset sub-items 2.3 and 2.4 reuse the same BRSA hierarchy code for DIFFERENT
 *  content depending on the bank (independent of deposit/participation type):
 *    Layout A — 2.3 = Factoring Receivables, 2.4 = Other Financial Assets at
 *               Amortized Cost  (AKBNK, İş, …)
 *    Layout B — 2.3 = Securities at Amortized Cost (govt securities / sukuk),
 *               2.4 = Expected Credit Losses (-)  (Garanti, all participation
 *               banks, …)
 *  So the hierarchy code alone can't label them — resolve from the stored
 *  item_names. `names` maps "<statement>::<hierarchy>" → representative
 *  item_name (see audit.ts `balanceSheetLineNames`). Returns `fallback`
 *  (the deposit catalog label) for every other line. */
export function resolveBsLineLabel(
  statement: "assets" | "liabilities",
  hierarchy: string,
  names: Map<string, string>,
  fallback: string,
): string {
  if (statement !== "assets" || (hierarchy !== "2.3" && hierarchy !== "2.4")) return fallback;
  const n23 = names.get("assets::2.3") ?? "";
  const n24 = names.get("assets::2.4") ?? "";
  const isFactoring = (s: string) => /fakto?ring/i.test(s);
  const isAmortizedSecurities = (s: string) =>
    /menkul|securit|amorti[sz]|maliyet|itfa/i.test(s);
  const isEcl = (s: string) => /beklenen\s*zarar|expected\s*credit/i.test(s);
  // Layout B when 2.4 is ECL, or 2.3 is clearly a securities/amortized-cost line
  // rather than factoring.
  const layoutB = isEcl(n24) || (!isFactoring(n23) && isAmortizedSecurities(n23));
  if (hierarchy === "2.3") return layoutB ? "Securities at Amortized Cost" : "Factoring Receivables";
  return layoutB ? "Expected Credit Losses (-)" : "Other Financial Assets at Amortized Cost";
}

/** Income Statement — replicates the rows the user highlighted on the
 *  BRSA template, in order. Roman numerals render bold (they're the
 *  major template rows AND subtotals); numeric sub-items render indented. */
export const PL_LINES: StandardLine[] = [
  // I. Interest Income + breakdown
  { id: "interest_income",        label: "Interest / Profit Share Income",                       hierarchy: "I.",     bold: true },
  { id: "ii_loans",               label: "Interest from Loans",                                  hierarchy: "1.1" },
  { id: "ii_reserves",            label: "Interest from Required Reserves",                      hierarchy: "1.2" },
  { id: "ii_banks",               label: "Interest from Banks",                                  hierarchy: "1.3" },
  { id: "ii_money_market",        label: "Interest from Money Market Operations",                hierarchy: "1.4" },
  { id: "ii_securities",          label: "Interest from Securities Portfolio",                   hierarchy: "1.5" },

  // II. Interest Expense + breakdown
  { id: "interest_expense",       label: "Interest / Profit Share Expense (-)",                  hierarchy: "II.",    bold: true },
  { id: "ie_deposits",            label: "Interest on Deposits / Funds Collected",               hierarchy: "2.1" },
  { id: "ie_borrowings",          label: "Interest on Funds Borrowed",                           hierarchy: "2.2" },
  { id: "ie_money_market",        label: "Interest on Money Market Operations",                  hierarchy: "2.3" },
  { id: "ie_issued_securities",   label: "Interest on Issued Securities",                        hierarchy: "2.4" },
  { id: "ie_lease",               label: "Lease Interest Expense",                               hierarchy: "2.5" },

  // III. Net Interest Income (subtotal)
  { id: "net_interest",           label: "Net Interest / Profit Share Income (I - II)",          hierarchy: "III.",   bold: true },

  // IV. Net Fees & Commissions + breakdown
  { id: "net_fees",               label: "Net Fees & Commissions",                               hierarchy: "IV.",    bold: true },
  { id: "fees_received",          label: "Fees & Commissions Received",                          hierarchy: "4.1" },
  { id: "fees_paid",              label: "Fees & Commissions Paid (-)",                          hierarchy: "4.2" },

  // V-VII. Other operating revenue lines
  { id: "dividend_income",        label: "Dividend Income",                                      hierarchy: "V.",     bold: true },
  { id: "trading_income",         label: "Net Trading Income / (Loss)",                          hierarchy: "VI.",    bold: true },
  { id: "other_op_income",        label: "Other Operating Income",                               hierarchy: "VII.",   bold: true },

  // VIII. Gross Operating Profit (subtotal)
  { id: "gross_op_profit",        label: "Gross Operating Profit (III+IV+V+VI+VII)",             hierarchy: "VIII.",  bold: true },

  // IX-XII. Provisions + operating expenses
  { id: "ecl_provisions",         label: "Expected Credit Loss Provisions (-)",                  hierarchy: "IX.",    bold: true },
  { id: "other_provisions",       label: "Other Provisions for Losses (-)",                      hierarchy: "X.",     bold: true },
  { id: "personnel_expense",      label: "Personnel Expenses (-)",                               hierarchy: "XI.",    bold: true },
  { id: "other_op_expense",       label: "Other Operating Expenses (-)",                         hierarchy: "XII.",   bold: true },

  // XIII. Net Operating Profit (subtotal)
  { id: "net_op_profit",          label: "Net Operating Profit / (Loss) (VIII-IX-X-XI-XII)",     hierarchy: "XIII.",  bold: true },

  // XV-XVI. Other below-the-line items (XIV is merger surplus — skipped)
  { id: "equity_method",          label: "Profit / (Loss) from Equity-Method Subsidiaries",      hierarchy: "XV.",    bold: true },
  { id: "monetary_position",      label: "Net Monetary Position Profit / (Loss)",                hierarchy: "XVI.",   bold: true },

  // XVII. Pre-tax Profit (subtotal)
  { id: "pretax_profit_cont",     label: "Pre-tax Profit / (Loss) from Continuing Operations",   hierarchy: "XVII.",  bold: true },

  // XVIII. Tax
  { id: "tax_provision",          label: "Tax Provision on Continuing Operations (±)",           hierarchy: "XVIII.", bold: true },

  // XIX. Net Period Profit from continuing ops (subtotal)
  { id: "net_profit_cont",        label: "Net Period Profit / (Loss) from Continuing Operations",hierarchy: "XIX.",   bold: true },

  // XXV. Total Net Period Profit (XX-XXIV are discontinued-ops detail — skipped)
  { id: "net_profit_total",       label: "Net Period Profit / (Loss) (XIX + XXIV)",              hierarchy: "XXV.",   bold: true },
];

/** Cash-flow roman subtotals/totals — I.–VII. (sections + bottom-line chain
 *  V=I+II+III+IV, VII=V+VI). Rendered bold with a top border. */
export const CF_ROMAN_HIERARCHIES = ["I.", "II.", "III.", "IV.", "V.", "VI.", "VII."];

/** Cash Flow Statement — standardized like the BS/IS catalogs. Codes follow the
 *  BRSA "Nakit Akış Tablosu" and are consistent across every bank; only the
 *  labels (Turkish/English) varied, so the raw item_name is never shown. Labels
 *  are the official BRSA English wording (from an English-filing bank). The
 *  three section headers are visual-only (`header: true`) — most banks file no
 *  A./B./C. data row, so the section totals (I./II./III.) delimit the sections.
 *  Within a section the order is detail rows → section total (some banks print
 *  the total at the top; we render by code, so display order is our choice). */
export const CF_LINES: StandardLine[] = [
  // ── A. Operating activities ──────────────────────────────────────────────
  { id: "cf_op_hdr",   label: "Operating Activities",                                       hierarchy: "§op",  header: true },
  { id: "cf_1_1",      label: "Operating Profit Before Changes in Operating Assets & Liabilities", hierarchy: "1.1", bold: true },
  { id: "cf_1_1_1",    label: "Interest / Profit Share Received",                           hierarchy: "1.1.1" },
  { id: "cf_1_1_2",    label: "Interest / Profit Share Paid",                               hierarchy: "1.1.2" },
  { id: "cf_1_1_3",    label: "Dividends Received",                                         hierarchy: "1.1.3" },
  { id: "cf_1_1_4",    label: "Fees and Commissions Received",                              hierarchy: "1.1.4" },
  { id: "cf_1_1_5",    label: "Other Income",                                               hierarchy: "1.1.5" },
  { id: "cf_1_1_6",    label: "Collections from Previously Written-off Receivables",        hierarchy: "1.1.6" },
  { id: "cf_1_1_7",    label: "Cash Payments to Personnel and Service Suppliers",           hierarchy: "1.1.7" },
  { id: "cf_1_1_8",    label: "Taxes Paid",                                                 hierarchy: "1.1.8" },
  { id: "cf_1_1_9",    label: "Other",                                                      hierarchy: "1.1.9" },
  { id: "cf_1_2",      label: "Changes in Operating Assets and Liabilities",                hierarchy: "1.2", bold: true },
  { id: "cf_1_2_1",    label: "Net Change in Financial Assets at FVTPL",                    hierarchy: "1.2.1" },
  { id: "cf_1_2_2",    label: "Net Change in Due from Banks",                               hierarchy: "1.2.2" },
  { id: "cf_1_2_3",    label: "Net Change in Loans",                                        hierarchy: "1.2.3" },
  { id: "cf_1_2_4",    label: "Net Change in Other Assets",                                 hierarchy: "1.2.4" },
  { id: "cf_1_2_5",    label: "Net Change in Bank Deposits / Funds Collected from Banks",   hierarchy: "1.2.5" },
  { id: "cf_1_2_6",    label: "Net Change in Other Deposits / Funds Collected",             hierarchy: "1.2.6" },
  { id: "cf_1_2_7",    label: "Net Change in Financial Liabilities at FVTPL",               hierarchy: "1.2.7" },
  { id: "cf_1_2_8",    label: "Net Change in Funds Borrowed",                               hierarchy: "1.2.8" },
  { id: "cf_1_2_9",    label: "Net Change in Matured Payables",                             hierarchy: "1.2.9" },
  { id: "cf_1_2_10",   label: "Net Change in Other Liabilities",                            hierarchy: "1.2.10" },
  { id: "cf_I",        label: "Net Cash Flow from Banking Operations",                      hierarchy: "I.",  bold: true },

  // ── B. Investing activities ──────────────────────────────────────────────
  { id: "cf_inv_hdr",  label: "Investing Activities",                                       hierarchy: "§inv", header: true },
  { id: "cf_2_1",      label: "Cash Paid for Purchase of Associates, Subsidiaries & Joint Ventures", hierarchy: "2.1" },
  { id: "cf_2_2",      label: "Cash from Sale of Associates, Subsidiaries & Joint Ventures", hierarchy: "2.2" },
  { id: "cf_2_3",      label: "Purchases of Tangible / Intangible Assets",                  hierarchy: "2.3" },
  { id: "cf_2_4",      label: "Sales of Tangible / Intangible Assets",                      hierarchy: "2.4" },
  { id: "cf_2_5",      label: "Cash Paid for Purchase of Financial Assets at FVOCI",        hierarchy: "2.5" },
  { id: "cf_2_6",      label: "Cash from Sale of Financial Assets at FVOCI",                hierarchy: "2.6" },
  { id: "cf_2_7",      label: "Cash Paid for Purchase of Financial Assets at Amortized Cost", hierarchy: "2.7" },
  { id: "cf_2_8",      label: "Cash from Sale of Financial Assets at Amortized Cost",       hierarchy: "2.8" },
  { id: "cf_2_9",      label: "Other",                                                      hierarchy: "2.9" },
  { id: "cf_II",       label: "Net Cash Flow from Investing Activities",                    hierarchy: "II.", bold: true },

  // ── C. Financing activities ──────────────────────────────────────────────
  { id: "cf_fin_hdr",  label: "Financing Activities",                                       hierarchy: "§fin", header: true },
  { id: "cf_3_1",      label: "Cash from Funds Borrowed and Securities Issued",             hierarchy: "3.1" },
  { id: "cf_3_2",      label: "Cash Used for Repayment of Funds Borrowed and Securities Issued", hierarchy: "3.2" },
  { id: "cf_3_3",      label: "Equity Instruments Issued",                                  hierarchy: "3.3" },
  { id: "cf_3_4",      label: "Dividends Paid",                                             hierarchy: "3.4" },
  { id: "cf_3_5",      label: "Payments for Financial Leases",                              hierarchy: "3.5" },
  { id: "cf_3_6",      label: "Other",                                                      hierarchy: "3.6" },
  { id: "cf_III",      label: "Net Cash Flow from Financing Activities",                    hierarchy: "III.", bold: true },

  // ── Bottom line ──────────────────────────────────────────────────────────
  { id: "cf_IV",       label: "Effect of Exchange Rate Changes on Cash & Cash Equivalents", hierarchy: "IV.", bold: true },
  { id: "cf_V",        label: "Net Increase / (Decrease) in Cash & Cash Equivalents (I+II+III+IV)", hierarchy: "V.", bold: true },
  { id: "cf_VI",       label: "Cash & Cash Equivalents at Beginning of Period",             hierarchy: "VI.", bold: true },
  { id: "cf_VII",      label: "Cash & Cash Equivalents at End of Period (V+VI)",            hierarchy: "VII.", bold: true },
];
