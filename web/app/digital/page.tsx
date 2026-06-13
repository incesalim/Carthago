/**
 * Digital Banking tab — TBB (Banks Association of Türkiye) quarterly digital,
 * internet & mobile banking statistics. Sector-wide (no per-bank breakdown):
 * customer adoption, transaction volumes & counts, and demographics of active
 * individual digital customers. Source: TBB "Dijital, İnternet ve Mobil
 * Bankacılık İstatistikleri" workbooks — see scripts/update_tbb_digital.py.
 *
 * All figures are sector totals. Customer counts are point-in-time at quarter
 * end; transaction figures are quarterly flows. "Active" follows TBB's
 * definition (logged in / transacted within the period).
 */
import {
  digitalSeries,
  quarterlyDeltas,
  SCALE_K_TO_M,
  SCALE_BN_TO_TRN,
  CHANNEL_USE,
  CHANNEL_USE_LABELS,
  ACTIVE_BY_CHANNEL,
  REGISTERED_BY_CHANNEL,
  APPLICATIONS,
  APPLICATION_LABELS,
  CHANNEL_LABELS,
  TRANSFER_VOLUME,
  TRANSFER_COUNT,
  BILL_COUNT,
  GENDER,
  GENDER_LABELS,
  AGE,
  AGE_LABELS,
} from "@/app/lib/digital";
import {
  acquisitionData,
  CHANNEL_LABELS as ACQ_CHANNEL_LABELS,
  METHOD_LABELS as ACQ_METHOD_LABELS,
} from "@/app/lib/acquisition";
import { latestPeriod } from "@/app/lib/metrics";
import { PageHeader } from "@/app/components/ui";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export default async function DigitalPage() {
  const [
    channelUse,
    activeByChannel,
    registeredByChannel,
    applications,
    transferVolume,
    transferCount,
    billCount,
    gender,
    age,
  ] = await Promise.all([
    digitalSeries(CHANNEL_USE, SCALE_K_TO_M),
    digitalSeries(ACTIVE_BY_CHANNEL, SCALE_K_TO_M),
    digitalSeries(REGISTERED_BY_CHANNEL, SCALE_K_TO_M),
    digitalSeries(APPLICATIONS, SCALE_K_TO_M),
    digitalSeries(TRANSFER_VOLUME, SCALE_BN_TO_TRN),
    digitalSeries(TRANSFER_COUNT, SCALE_K_TO_M),
    digitalSeries(BILL_COUNT, SCALE_K_TO_M),
    digitalSeries(GENDER, SCALE_K_TO_M),
    digitalSeries(AGE, SCALE_K_TO_M),
  ]);

  // Net new registered customers per quarter — the registered base is a stock;
  // its quarter-over-quarter change is the acquisition flow TBB doesn't report.
  const netAdds = quarterlyDeltas(registeredByChannel);

  // Remote-vs-branch acquisition (separate monthly TBB report) — individuals.
  const acq = await acquisitionData("individual");

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="TBB — Banks Association of Türkiye"
        title="Digital Banking"
        description="Sector-wide adoption, transaction volumes and demographics across internet & mobile banking — TBB quarterly digital-banking statistics."
        dataThrough={latestPeriod(activeByChannel, transferVolume, gender)}
      />

      <Section
        title="Adoption"
        subtitle="Active customers by channel. Mobile has all but replaced internet banking — most individuals now bank mobile-only."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={activeByChannel}
            seriesLabels={CHANNEL_LABELS}
            title="Active customers — mobile vs internet (millions)"
            yFormat="raw"
            decimals={0}
          />
          <TrendChart
            data={channelUse}
            seriesLabels={CHANNEL_USE_LABELS}
            title="Active individuals by channel usage (millions)"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>

      <Section
        title="Digital customer base"
        subtitle="The registered base and how it grows, plus the demand funnel feeding it. The base is TBB's quarter-end stock (registered and logged in at least once); net adds are its quarter-over-quarter change. Base counts are per-bank registrations summed across the sector — a customer registered at several banks counts several times — so read the trend and net adds, not the absolute level. Application counts are mobile only (internet is now under 1% of applications)."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={registeredByChannel}
            seriesLabels={CHANNEL_LABELS}
            title="Registered customer base by channel (millions)"
            yFormat="raw"
            decimals={0}
          />
          <TrendChart
            data={netAdds}
            seriesLabels={CHANNEL_LABELS}
            title="Net new registered customers per quarter (millions)"
            yFormat="raw"
            decimals={1}
            zeroLine
          />
        </div>
        <TrendChart
          data={applications}
          seriesLabels={APPLICATION_LABELS}
          title="Product applications via mobile per quarter (millions)"
          yFormat="raw"
          decimals={1}
          height={320}
        />
      </Section>

      <Section
        title="Customer acquisition — digital vs branch"
        subtitle="From TBB's separate monthly “Uzaktan ve Şubeden Müşteri Edinim” report: how many individuals each month became customers remotely — without visiting a branch — vs at a branch. “Remotely” combines the three branch-free finalisation methods (a video call with a representative, courier ID confirmation, and bulk payroll/corporate onboarding); “branch” is in-person. Remote-application intake (a funnel count, not finalised customers) is excluded. Series start May 2021 (the remote-ID regulation); definitions were refined in Jan 2023. Individuals only — merchant and legal-entity data exists from Jul 2024."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={acq.byChannel}
            seriesLabels={ACQ_CHANNEL_LABELS}
            title="New individual customers per month (thousands)"
            yFormat="raw"
            decimals={0}
          />
          <TrendChart
            data={acq.share}
            seriesLabels={ACQ_CHANNEL_LABELS}
            title="Share of new customers by channel (%)"
            yFormat="pct"
            decimals={0}
          />
        </div>
        <TrendChart
          data={acq.byMethod}
          seriesLabels={ACQ_METHOD_LABELS}
          title="New individual customers by acquisition method (thousands per month)"
          yFormat="raw"
          decimals={0}
          height={320}
        />
      </Section>

      <Section
        title="Transactions"
        subtitle="Quarterly money-transfer and bill-payment activity. Mobile dominates both value and volume."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={transferVolume}
            seriesLabels={CHANNEL_LABELS}
            title="Money-transfer volume per quarter (₺ trillion)"
            yFormat="raw"
            decimals={1}
          />
          <TrendChart
            data={transferCount}
            seriesLabels={CHANNEL_LABELS}
            title="Money-transfer count per quarter (millions)"
            yFormat="raw"
            decimals={0}
          />
        </div>
        <TrendChart
          data={billCount}
          seriesLabels={CHANNEL_LABELS}
          title="Bill-payment count per quarter (millions)"
          yFormat="raw"
          decimals={0}
          height={320}
        />
      </Section>

      <Section
        title="Who banks digitally"
        subtitle="Demographics of active individual digital customers (internet + mobile combined)."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={gender}
            seriesLabels={GENDER_LABELS}
            title="Active individuals by gender (millions)"
            yFormat="raw"
            decimals={0}
          />
          <TrendChart
            data={age}
            seriesLabels={AGE_LABELS}
            title="Active individuals by age group (millions)"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>
    </main>
  );
}
