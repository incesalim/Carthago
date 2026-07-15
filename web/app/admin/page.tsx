/**
 * Admin control center — data/pipeline health + manual triggers + traffic.
 * Gated by requireAdmin() (Cloudflare Access JWT / ADMIN_PASSWORD). Safe-by-
 * default: until auth is configured this renders a Forbidden card.
 *
 * Built on "The Desk" (web/DESIGN.md): the six sources are the vitals band — the
 * one bold element — and everything else (coverage, pipeline, traffic, the deck)
 * carries under quiet section heads. No boxes, hairlines instead; blue is links
 * only; Fresh/Late/Stale read green/amber/red as data state, not accent.
 */
import type { Metadata } from "next";
import { AdminAuthError, requireAdmin } from "@/app/lib/admin-auth";
import { getHealthReport, type FreshnessStatus, type SourceHealth } from "@/app/lib/admin-health";
import { relativeFromHours } from "@/app/lib/format-time";
import { Card } from "@/app/components/ui";
import { Colophon, SecHead, Vitals } from "@/app/components/desk";
import CoverageMatrix from "./coverage/CoverageMatrix";
import LoginForm from "./LoginForm";
import PipelinePanel from "./PipelinePanel";
import PurgeCacheButton from "./PurgeCacheButton";
import TrafficPanel from "./TrafficPanel";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Admin",
  robots: { index: false, follow: false },
};

const nf = new Intl.NumberFormat("en-US");

const STATUS_STYLE: Record<FreshnessStatus, { dot: string; text: string; label: string }> = {
  fresh: { dot: "bg-positive", text: "text-positive", label: "Fresh" },
  late: { dot: "bg-warning", text: "text-warning", label: "Late" },
  stale: { dot: "bg-negative", text: "text-negative", label: "Stale" },
  unknown: { dot: "bg-faint", text: "text-faint", label: "No data" },
};

/** The band shows a date, not a clock: strip the time off an ISO/D1 timestamp
 *  (news/regulation carry a full `...T05:58:00+00:00`), leave period labels
 *  like "2026-05" or "2026Q1" untouched. */
function fmtValue(p: string | null): string {
  if (!p) return "—";
  const m = /^(\d{4}-\d{2}-\d{2})([ T]|$)/.exec(p);
  return m ? m[1] : p;
}

/** Audit freshness is validation health, not a clock — say so. */
function statusLabel(s: SourceHealth): string {
  if (s.key === "audit") {
    if (s.status === "fresh") return "Clean";
    if (s.status === "late") return "Failures";
  }
  return STATUS_STYLE[s.status].label;
}

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

/** One source as a vitals cell: period figure, status dot+word, one detail line. */
function HealthVital({ s }: { s: SourceHealth }) {
  const st = STATUS_STYLE[s.status];
  // A note carries the ground-truth line (e.g. "June not yet published · probed
  // today") — prefer it over "updated Nd ago", which is misleading for the
  // monthly bulletin whose ingest timestamp freezes between releases.
  const detail = s.note
    ? s.note
    : [
        s.rowCount != null ? `${nf.format(s.rowCount)} rows` : null,
        s.ageHours != null ? `updated ${relativeFromHours(s.ageHours)}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
  return (
    <div className="border-r border-hair px-4 py-3 last:border-r-0 max-sm:odd:pl-0 sm:first:pl-0">
      <div className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-muted-foreground">
        {s.label}
      </div>
      <div className="mt-1.5 font-mono text-[22px] font-semibold tracking-tight tabular-nums text-foreground">
        {fmtValue(s.latestPeriod)}
      </div>
      <div
        className={`mt-2 inline-flex items-center gap-1.5 font-mono text-[8.5px] uppercase tracking-[0.06em] ${st.text}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
        {statusLabel(s)}
      </div>
      {detail && <div className="mt-2 text-[9.5px] leading-snug text-faint">{detail}</div>}
    </div>
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
  const flagged = sources.filter((s) => s.status === "late" || s.status === "stale");
  const record =
    flagged.length === 0
      ? `internal · all ${sources.length} sources current`
      : `internal · ${flagged.map((s) => s.label.toLowerCase()).join(", ")} ${
          flagged.length === 1 ? "needs" : "need"
        } attention`;

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-8 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="text-[24px] font-bold tracking-tight text-foreground">Control center</h1>
          <p className="mt-1.5 font-mono text-[9.5px] uppercase tracking-[0.07em] text-muted-foreground">
            {record}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <form method="post" action="/api/admin/logout">
            <button
              type="submit"
              className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted-foreground underline decoration-border underline-offset-4 transition-colors hover:text-foreground hover:decoration-current"
            >
              Sign out
            </button>
          </form>
          <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
            read-only · computed on view
          </span>
        </div>
      </header>

      <section className="mt-7">
        <SecHead
          title="Data health"
          meta="freshness by source · schedule-aware, not age"
          action={<PurgeCacheButton />}
          className="mb-2"
        />
        <Vitals cols={6}>
          {sources.map((s) => (
            <HealthVital key={s.key} s={s} />
          ))}
        </Vitals>
      </section>

      <section className="mt-9">
        <CoverageMatrix />
      </section>

      <section className="mt-9">
        <PipelinePanel />
      </section>

      <section className="mt-9">
        <TrafficPanel />
      </section>

      <section className="mt-9">
        <SecHead
          title="Presentation"
          meta="board-style PDF of the sector Read"
          className="mb-3"
        />
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <a
            href="/api/presentation?print=1"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[13px] font-semibold text-primary hover:underline"
          >
            Generate PDF
          </a>
          <a
            href="/api/presentation"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[13px] font-semibold text-primary hover:underline"
          >
            Preview deck
          </a>
          <span className="text-[12px] text-faint">
            Figures come straight from the live dashboard — nothing to configure.
          </span>
        </div>
      </section>

      <Colophon>
        Internal control center · read-only D1 queries + GitHub Actions run status + Cloudflare Web
        Analytics · computed on view · BDDK freshness probed daily 16:00 Turkey · sign out top-right
      </Colophon>
    </main>
  );
}
