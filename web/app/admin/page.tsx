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
  type BadgeProps,
  type StatProps,
} from "@/app/components/ui";
import CoverageMatrix from "./coverage/CoverageMatrix";
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

  const { sources } = await getHealthReport();

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

      <CoverageMatrix />

      <PipelinePanel />

      <TrafficPanel />
    </main>
  );
}
