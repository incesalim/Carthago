/**
 * Rates / Macro tab — placeholder.
 *
 * Old dashboard pulled live data from TCMB EVDS API for policy rate, FX,
 * inflation, sterilization volume etc. Cloudflare Workers can call EVDS too,
 * but we should cache results in D1 (or KV) to avoid hitting EVDS on every
 * request.
 */
export default function RatesPage() {
  return (
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Rates &amp; Macro</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Coming soon — TCMB EVDS series (policy rate, FX, inflation, CBRT sterilization).
      </p>
      <div className="rounded-lg border bg-white p-6 text-sm text-neutral-500">
        Implementation plan:
        <ul className="list-disc ml-5 mt-2 space-y-1">
          <li>Add a Worker scheduled cron that fetches latest EVDS series and writes to D1</li>
          <li>Or fetch on-the-fly with KV caching for 1 hour</li>
          <li>Then port the panels: policy/CBRT/FX/inflation/sterilization</li>
        </ul>
      </div>
    </main>
  );
}
