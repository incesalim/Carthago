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
  pivotWide,
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
import { PageHeader, Section } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import BopFlowChart from "@/app/components/BopFlowChart";

// Build a StackedArea/BopFlowChart `series` list from a {code: label} map,
// preserving order (= stack/legend order).
const seriesOf = (labels: Record<string, string>) =>
  Object.entries(labels).map(([key, label]) => ({ key, label }));

// Theme palette[0]/[1] (light/dark) so the mobile/internet grouped bars match
// the mobile/internet lines elsewhere on the page.
const MOBILE_FILL = { light: "#7a0d2e", dark: "#f0608a" };
const INTERNET_FILL = { light: "#1f4068", dark: "#6f9fe0" };

export const dynamic = "force-dynamic";

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
        rangeSelector
        dataThrough={latestPeriod(activeByChannel, transferVolume, gender)}
      />

      <Section
        title="Adoption"
        description="Active customers by channel. Mobile has all but replaced internet banking — most individuals now bank mobile-only."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={activeByChannel}
            seriesLabels={CHANNEL_LABELS}
            title="Active customers — mobile vs internet (millions)"
            yFormat="raw"
            decimals={0}
          />
          <StackedArea
            data={pivotWide(channelUse)}
            series={seriesOf(CHANNEL_USE_LABELS)}
            title="Active individuals by channel usage (% of total)"
            decimals={1}
            percentStack
            colorKeys
          />
        </div>
      </Section>

      <Section
        title="Digital customer base"
        description="The registered base and how it grows, plus the demand funnel feeding it. The base is TBB's quarter-end stock (registered and logged in at least once); net adds are its quarter-over-quarter change. Base counts are per-bank registrations summed across the sector — a customer registered at several banks counts several times — so read the trend and net adds, not the absolute level. Application counts are mobile only (internet is now under 1% of applications)."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={registeredByChannel}
            seriesLabels={CHANNEL_LABELS}
            title="Registered customer base by channel (millions)"
            yFormat="raw"
            decimals={0}
          />
          <ChartCard title="Net new registered customers per quarter (millions)">
            <BopFlowChart
              data={pivotWide(netAdds, "x")}
              bars={[
                { key: "mobile", label: CHANNEL_LABELS.mobile, fill: MOBILE_FILL },
                { key: "internet", label: CHANNEL_LABELS.internet, fill: INTERNET_FILL },
              ]}
              grouped
              decimals={1}
            />
          </ChartCard>
        </div>
        <StackedArea
          data={pivotWide(applications)}
          series={seriesOf(APPLICATION_LABELS)}
          title="Product applications via mobile per quarter (millions)"
          decimals={1}
          height={320}
          colorKeys
        />
      </Section>

      <Section
        title="Customer acquisition — digital vs branch"
        description="From TBB's separate monthly “Uzaktan ve Şubeden Müşteri Edinim” report: how many individuals became customers remotely — without visiting a branch — vs at a branch. “Remotely” combines the three branch-free finalisation methods (a video call with a representative, courier ID confirmation, and bulk payroll/corporate onboarding); “branch” is in-person. Remote-application intake (a funnel count, not finalised customers) is excluded. Each point is a trailing 3-month sum (the month plus the prior two), smoothing the monthly noise while keeping monthly cadence; the first two months (May–Jun 2021) have no full window. The remote-ID regulation began May 2021 and definitions were refined in Jan 2023. Individuals only — merchant and legal-entity data exists from Jul 2024."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={acq.byChannel}
            seriesLabels={ACQ_CHANNEL_LABELS}
            title="New individual customers, trailing 3 months (thousands)"
            yFormat="raw"
            decimals={0}
          />
          <StackedArea
            data={pivotWide(acq.byChannel)}
            series={seriesOf(ACQ_CHANNEL_LABELS)}
            title="Share of new customers by channel (%)"
            decimals={0}
            percentStack
            colorKeys
          />
        </div>
        <StackedArea
          data={pivotWide(acq.byMethod)}
          series={seriesOf(ACQ_METHOD_LABELS)}
          title="New individual customers by acquisition method (thousands, trailing 3 months)"
          decimals={0}
          height={320}
          colorKeys
        />
      </Section>

      <Section
        title="Transactions"
        description="Quarterly money-transfer and bill-payment activity. Mobile dominates both value and volume."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={pivotWide(transferVolume)}
            series={seriesOf(CHANNEL_LABELS)}
            title="Money-transfer volume per quarter (₺ trillion)"
            decimals={1}
            colorKeys
          />
          <StackedArea
            data={pivotWide(transferCount)}
            series={seriesOf(CHANNEL_LABELS)}
            title="Money-transfer count per quarter (millions)"
            decimals={0}
            colorKeys
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
        description="Demographics of active individual digital customers (internet + mobile combined)."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={pivotWide(gender)}
            series={seriesOf(GENDER_LABELS)}
            title="Active individuals by gender (% of total)"
            decimals={1}
            percentStack
            colorKeys
          />
          <StackedArea
            data={pivotWide(age)}
            series={seriesOf(AGE_LABELS)}
            title="Active individuals by age group (millions)"
            decimals={1}
            colorKeys
          />
        </div>
      </Section>
    </main>
  );
}
