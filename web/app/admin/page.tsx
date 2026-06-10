/**
 * Admin control center — data/pipeline health + manual triggers + traffic.
 * Gated by requireAdmin() (Cloudflare Access JWT). Safe-by-default: until Access
 * is configured the header is absent and this renders a Forbidden card.
 */
import { AdminAuthError, requireAdmin } from "@/app/lib/admin-auth";
import { getHealthReport, type FreshnessStatus, type SourceHealth } from "@/app/lib/admin-health";
import { relativeFromHours } from "@/app/lib/format-time";
import {
  Badge,
  Button,
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
import LoginForm from "./LoginForm";
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
        <h1 className="text-lg font-semibold text-foreground">Admin not configured</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Set an <code className="rounded bg-muted px-1">ADMIN_PASSWORD</code> secret on the
          Worker to enable the password login (or <code className="rounded bg-muted px-1">ADMIN_DEV_BYPASS=1</code>{" "}
          for local dev). See <code className="rounded bg-muted px-1">docs/ADMIN.md</code>.
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

export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  try {
    await requireAdmin();
  } catch (e) {
    if (e instanceof AdminAuthError && e.mode === "login") {
      const sp = await searchParams;
      return <LoginForm error={sp?.error === "config" ? "config" : sp?.error ? "wrong" : undefined} />;
    }
    return <Forbidden />;
  }

  const { sources, extraction, validation } = await getHealthReport();
  const extractionTone =
    extraction.failed === 0 ? "positive" : extraction.failed > 10 ? "negative" : "warning";

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Internal"
        title="Control center"
        description="Pipeline health, manual refresh triggers, and site traffic — all in one place."
      >
        <form method="post" action="/api/admin/logout">
          <Button type="submit" variant="outline" size="sm">
            Sign out
          </Button>
        </form>
      </PageHeader>

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

      {validation.banks.length > 0 && (
        <Section
          title="Structural validation"
          description="Internal-sum identity checks per bank (TL+FC=Total, parent=Σchildren, TOTAL=Σromans) — written at extraction time"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Stat
              label="Banks with failing partitions"
              value={nf.format(validation.banks.filter((b) => b.failed_partitions > 0).length)}
              tone={validation.totalFailedPartitions === 0 ? "positive" : "warning"}
            />
            <Stat
              label="Failing (bank, quarter) partitions"
              value={nf.format(validation.totalFailedPartitions)}
              tone={validation.totalFailedPartitions === 0 ? "positive" : "warning"}
              badge={
                validation.totalFailedPartitions === 0 ? (
                  <Badge variant="positive">all identities hold</Badge>
                ) : (
                  <Badge variant="warning">needs attention</Badge>
                )
              }
            />
          </div>
          {validation.totalFailedPartitions > 0 && (
            <Card className="mt-3 overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Bank</TableHead>
                    <TableHead className="text-right">Partitions</TableHead>
                    <TableHead className="text-right">Failing partitions</TableHead>
                    <TableHead className="text-right">Failed checks</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {validation.banks
                    .filter((b) => b.failed_partitions > 0)
                    .map((b) => (
                      <TableRow key={b.bank_ticker}>
                        <TableCell className="font-medium">{b.bank_ticker}</TableCell>
                        <TableCell className="text-right">{nf.format(b.partitions)}</TableCell>
                        <TableCell className="text-right">{nf.format(b.failed_partitions)}</TableCell>
                        <TableCell className="text-right">{nf.format(b.checks_failed)}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </Section>
      )}

      <PipelinePanel />

      <TrafficPanel />
    </main>
  );
}
