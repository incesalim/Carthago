/**
 * Traffic panel — Cloudflare Web Analytics summary (async server component).
 * Renders a graceful "not configured" state until the analytics creds are set.
 */
import { getTrafficSummary } from "@/app/lib/cf-analytics";
import { SecHead } from "@/app/components/desk";

const nf = new Intl.NumberFormat("en-US");

function Fig({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="border-r border-hair px-4 py-3 last:border-r-0 max-sm:odd:pl-0 sm:first:pl-0">
      <div className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1.5 font-mono text-[22px] font-semibold tracking-tight tabular-nums text-foreground">
        {value}
      </div>
      {note && <div className="mt-2 text-[9.5px] leading-snug text-faint">{note}</div>}
    </div>
  );
}

export default async function TrafficPanel() {
  const t = await getTrafficSummary(7);

  if (!t.configured) {
    return (
      <>
        <SecHead title="Traffic" meta="cloudflare web analytics · last 7 days" className="mb-3" />
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Web Analytics not configured.</span> Enable
          Cloudflare Web Analytics for the site, then set{" "}
          <code className="rounded bg-muted px-1 font-mono text-[11px]">CF_ANALYTICS_TOKEN</code>,{" "}
          <code className="rounded bg-muted px-1 font-mono text-[11px]">CF_ANALYTICS_SITE_TAG</code>{" "}
          and <code className="rounded bg-muted px-1 font-mono text-[11px]">CF_ACCOUNT_TAG</code> to
          light this up.
        </p>
      </>
    );
  }

  if (t.error) {
    return (
      <>
        <SecHead title="Traffic" meta="cloudflare web analytics · last 7 days" className="mb-3" />
        <p className="text-[12.5px] text-muted-foreground">
          <span className="font-mono text-[9px] uppercase tracking-[0.06em] text-warning">
            Analytics error
          </span>{" "}
          — {t.error}
        </p>
      </>
    );
  }

  const busiest = t.daily.length ? t.daily.reduce((a, b) => (b.views > a.views ? b : a)) : null;

  return (
    <>
      <SecHead
        title="Traffic"
        meta={`cloudflare web analytics · last ${t.rangeDays} days`}
        className="mb-2"
      />
      <div className="grid grid-cols-2 border-y border-b-hair border-t-2 border-t-foreground sm:grid-cols-3">
        <Fig label="Page views" value={nf.format(t.pageViews)} />
        <Fig label="Visits" value={nf.format(t.visits)} note="unique sessions" />
        <Fig
          label="Busiest day"
          value={busiest ? busiest.date : "—"}
          note={busiest ? `${nf.format(busiest.views)} views` : undefined}
        />
      </div>
      {t.topPaths.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-foreground text-left font-mono text-[8.5px] uppercase tracking-[0.06em] text-faint">
                <th className="pb-1.5 pr-3 font-normal">Top path</th>
                <th className="pb-1.5 pl-3 text-right font-normal">Views</th>
              </tr>
            </thead>
            <tbody>
              {t.topPaths.map((p) => (
                <tr key={p.path} className="border-b border-hair">
                  <td className="py-1.5 pr-3 font-medium text-foreground">{p.path}</td>
                  <td className="py-1.5 pl-3 text-right font-mono tabular-nums text-foreground">
                    {nf.format(p.views)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
