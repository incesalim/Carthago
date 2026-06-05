/**
 * Traffic panel — Cloudflare Web Analytics summary (async server component).
 * Renders a graceful "not configured" state until the analytics creds are set.
 */
import { getTrafficSummary } from "@/app/lib/cf-analytics";
import { Badge, Card, Section, Stat, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/app/components/ui";

const nf = new Intl.NumberFormat("en-US");

export default async function TrafficPanel() {
  const t = await getTrafficSummary(7);

  if (!t.configured) {
    return (
      <Section title="Traffic" description="Cloudflare Web Analytics — last 7 days">
        <Card className="p-5 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Web Analytics not configured.</p>
          <p className="mt-1">
            Enable Cloudflare Web Analytics for the site, then set{" "}
            <code className="rounded bg-muted px-1">CF_ANALYTICS_TOKEN</code>,{" "}
            <code className="rounded bg-muted px-1">CF_ANALYTICS_SITE_TAG</code> and{" "}
            <code className="rounded bg-muted px-1">CF_ACCOUNT_TAG</code> to light this up.
          </p>
        </Card>
      </Section>
    );
  }

  if (t.error) {
    return (
      <Section title="Traffic" description="Cloudflare Web Analytics — last 7 days">
        <Card className="p-5 text-sm">
          <Badge variant="warning">Analytics error</Badge>
          <p className="mt-2 text-muted-foreground">{t.error}</p>
        </Card>
      </Section>
    );
  }

  return (
    <Section title="Traffic" description={`Cloudflare Web Analytics — last ${t.rangeDays} days`}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Stat label="Page views" value={nf.format(t.pageViews)} />
        <Stat label="Visits" value={nf.format(t.visits)} />
        <Stat
          label="Busiest day"
          value={
            t.daily.length
              ? t.daily.reduce((a, b) => (b.views > a.views ? b : a)).date
              : "—"
          }
          hint={
            t.daily.length
              ? `${nf.format(t.daily.reduce((a, b) => (b.views > a.views ? b : a)).views)} views`
              : undefined
          }
        />
      </div>
      {t.topPaths.length > 0 && (
        <Card className="mt-3 overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Top path</TableHead>
                <TableHead className="text-right">Views</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {t.topPaths.map((p) => (
                <TableRow key={p.path}>
                  <TableCell className="font-medium">{p.path}</TableCell>
                  <TableCell className="text-right tabular-nums">{nf.format(p.views)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </Section>
  );
}
