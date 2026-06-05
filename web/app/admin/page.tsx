/**
 * Admin control center — data/pipeline health + manual triggers + traffic.
 * Gated by requireAdmin() (Cloudflare Access JWT). Safe-by-default: until Access
 * is configured the header is absent and this renders a Forbidden card.
 */
import { requireAdmin } from "@/app/lib/admin-auth";
import { getHealthReport, type FreshnessStatus, type SourceHealth } from "@/app/lib/admin-health";
import { relativeFromHours } from "@/app/lib/format-time";
import {
  Badge,
  Card,
  PageHeader,
  Section,
  Stat,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  type BadgeProps,
  type StatProps,
} from "@/app/components/ui";
import PipelinePanel from "./PipelinePanel";
import TrafficPanel from "./TrafficPanel";

export const dynamic = "force-dynamic";

const nf = new Intl.NumberFormat("en-US");

const STATUS_STYLE: Record<
  FreshnessStatus,
  { tone: StatProps["tone"]; variant: BadgeProps["variant"]; label: string }
> = {
  fresh: { tone: "positive", variant: "positive", label: "Fresh" },
  late: { tone: "warning", variant: "warning", label: "Late" },
  stale: { tone: "negative", variant: "negative", label: "Stale" },
  unknown: { tone: "neutral", variant: "secondary", label: "No data" },
};

function Forbidden() {
  return (
    <main className="mx-auto max-w-md px-4 py-24">
      <Card className="p-8 text-center">
        <h1 className="text-lg font-semibold text-foreground">Admin access required</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This page is gated by Cloudflare Access. Sign in with an authorised account, or
          set <code className="rounded bg-muted px-1">ADMIN_DEV_BYPASS=1</code> for local dev.
        </p>
      </Card>
    </main>
  );
}

function SourceCard({ s }: { s: SourceHealth }) {
  const style = STATUS_STYLE[s.status];
  const bits = [
    `updated ${relativeFromHours(s.ageHours)}`,
    s.rowCount != null ? `${nf.format(s.rowCount)} rows` : null,
    s.note,
  ].filter(Boolean);
  return (
    <Stat
      label={s.label}
      value={s.latestPeriod ?? "—"}
      tone={style.tone}
      badge={<Badge variant={style.variant}>{style.label}</Badge>}
      hint={bits.join(" · ")}
    />
  );
}

export default async function AdminPage() {
  try {
    await requireAdmin();
  } catch {
    return <Forbidden />;
  }

  const { sources, extraction } = await getHealthReport();
  const extractionTone =
    extraction.failed === 0 ? "positive" : extraction.failed > 10 ? "negative" : "warning";

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Internal"
        title="Control center"
        description="Pipeline health, manual refresh triggers, and site traffic — all in one place."
      />

      <Section title="Data health" description="Freshness per source, against expected refresh cadence">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sources.map((s) => (
            <SourceCard key={s.key} s={s} />
          ))}
        </div>
      </Section>

      <Section
        title="Audit extraction"
        description="PDF → table extraction success across all quarterly reports"
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="PDFs extracted" value={nf.format(extraction.total)} />
          <Stat label="Succeeded" value={nf.format(extraction.success)} tone="positive" />
          <Stat
            label="Failed / partial"
            value={nf.format(extraction.failed)}
            tone={extractionTone}
            badge={
              extraction.failed === 0 ? (
                <Badge variant="positive">all clean</Badge>
              ) : (
                <Badge variant="warning">needs attention</Badge>
              )
            }
          />
        </div>

        {extraction.failures.length > 0 && (
          <Card className="mt-3 overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bank</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Note</TableHead>
                  <TableHead className="text-right">When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {extraction.failures.map((f) => (
                  <TableRow key={`${f.bank_ticker}-${f.period}-${f.kind}`}>
                    <TableCell className="font-medium">{f.bank_ticker}</TableCell>
                    <TableCell>{f.period}</TableCell>
                    <TableCell className="text-muted-foreground">{f.kind}</TableCell>
                    <TableCell className="max-w-[24rem] truncate text-muted-foreground" title={f.note ?? ""}>
                      {f.note ?? "—"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-right text-muted-foreground">
                      {f.extracted_at ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </Section>

      <PipelinePanel />

      <TrafficPanel />
    </main>
  );
}
