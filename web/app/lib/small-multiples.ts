/** Preserve the full observation grid, including explicit missing disclosures. */
export function groupSmallMultipleRows(
  rows: { period: string; bank_type_code: string; value: number | null }[],
  codes: string[],
) {
  return codes.map((code) => ({
    code,
    rows: rows.filter((row) => row.bank_type_code === code)
      .map(({ period, value }) => ({ period, value }))
      .sort((a, b) => a.period.localeCompare(b.period)),
  })).filter((group) => group.rows.length > 0);
}
