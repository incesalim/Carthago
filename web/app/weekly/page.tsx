/**
 * Weekly Trends tab — placeholder.
 *
 * Weekly data lives in weekly_series (700k rows). Porting all the
 * 4w/13w/YoY transforms is the next thing to do here.
 */
export default function WeeklyPage() {
  return (
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Weekly Trends</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Coming soon — weekly_series data + 4w / 13w / YoY growth transforms.
      </p>
      <div className="rounded-lg border bg-white p-6 text-sm text-neutral-500">
        This tab will show weekly bank-comparison charts (loans, deposits, NPL)
        with annualized 4-week and 13-week growth rates from the
        <code className="mx-1 px-1 bg-neutral-100 rounded">weekly_series</code>
        table.
      </div>
    </main>
  );
}
