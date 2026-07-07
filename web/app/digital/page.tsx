/**
 * Digital Banking tab — TBB (Banks Association of Türkiye) quarterly digital,
 * internet & mobile banking statistics, plus TKBB (Participation Banks
 * Association) equivalents for participation banks. Sector-wide (no per-bank
 * breakdown): customer adoption, transaction volumes & counts, demographics,
 * and participation-vs-banks comparisons. Sources: TBB "Dijital, İnternet ve
 * Mobil Bankacılık İstatistikleri" workbooks (scripts/update_tbb_digital.py)
 * and TKBB Veri Peteği Turboard dashboards (scripts/update_tkbb_digital.py).
 *
 * All figures are sector totals. Customer counts are point-in-time at quarter
 * end; transaction figures are quarterly flows. "Active" follows each
 * association's own definition (logged in / transacted within the period).
 */
import type { Metadata } from "next";
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
import {
  tkbbSeries,
  participationShare,
  mobileOnlyShare,
  tkbbVolumeByChannel,
  tkbbAcquisitionLevels,
  remoteShareComparison,
  ACTIVE_TOTAL,
  COMPARISON_LABELS,
  ACQ_SERIES_LABELS as TKBB_ACQ_LABELS,
  SCALE_PERSONS_TO_M,
} from "@/app/lib/tkbb";
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
const MOBILE_FILL = { light: "#2F6BED", dark: "#5B86F7" };
const INTERNET_FILL = { light: "#15AABF", dark: "#2BD4CC" };

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Digital & Mobile Banking",
  description: "Digital, internet and mobile banking adoption in Türkiye — active users and remote vs branch acquisition from TBB data.",
  alternates: { canonical: "/digital" },
};

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

  // Participation banks (TKBB Veri Peteği) — quarterly digital + monthly acquisition.
  const [tkbbActive, tkbbShare, mobileShareCmp, tkbbVolume, tkbbAcq, remoteShareCmp] =
    await Promise.all([
      tkbbSeries(ACTIVE_TOTAL, SCALE_PERSONS_TO_M),
      participationShare(),
      mobileOnlyShare(),
      tkbbVolumeByChannel(),
      tkbbAcquisitionLevels(),
      remoteShareComparison(acq.byChannel),
    ]);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="TBB & TKBB — banking associations"
        title="Digital Banking"
        description="Sector-wide adoption, transaction volumes and demographics across internet & mobile banking — TBB quarterly statistics for banks, plus TKBB Veri Peteği data for participation banks."
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
        title="Participation banks — digital adoption"
        description="The participation-bank side of digital banking, from TKBB's Veri Peteği (quarterly since 2020). Counts are per-association: a customer of both a deposit bank and a participation bank appears in both TBB's and TKBB's figures, and each association applies its own “active” definition — read the shares as trends, not an exact census. TKBB reports all customer types combined (individual + corporate); the comparisons use TBB's matching all-customer basis."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={tkbbActive}
            seriesLabels={{ participation: "Active digital customers" }}
            title="Active digital customers — participation banks (millions)"
            yFormat="raw"
            decimals={1}
          />
          <TrendChart
            data={tkbbShare}
            seriesLabels={{ share: "Participation share" }}
            title="Participation banks' share of active digital customers (%)"
            yFormat="raw"
            decimals={1}
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={mobileShareCmp}
            seriesLabels={COMPARISON_LABELS}
            title="Mobile-only share of active digital customers (%)"
            yFormat="raw"
            decimals={1}
          />
          <StackedArea
            data={pivotWide(tkbbVolume)}
            series={seriesOf(CHANNEL_LABELS)}
            title="Participation banks' digital transaction volume (₺ trillion / quarter)"
            decimals={1}
            colorKeys
          />
        </div>
      </Section>

      <Section
        title="Participation banks — customer acquisition"
        description="From TKBB's monthly “Uzaktan Müşteri Edinim” dashboard: participation-bank customers acquired remotely vs at a branch, as trailing 3-month sums. The public source exposes only a rolling 12-month window, which we accumulate — history builds forward from mid-2025. TKBB counts all customer types; the TBB comparison line is individuals only, so the levels aren't strictly comparable — the trend and the gap are the signal."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={tkbbAcq}
            seriesLabels={TKBB_ACQ_LABELS}
            title="New participation-bank customers, trailing 3 months (thousands)"
            yFormat="raw"
            decimals={0}
          />
          <TrendChart
            data={remoteShareCmp}
            seriesLabels={COMPARISON_LABELS}
            title="Acquired remotely — share of new customers (%)"
            yFormat="raw"
            decimals={0}
          />
        </div>
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
