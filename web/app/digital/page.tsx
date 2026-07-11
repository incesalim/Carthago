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
import { Section } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo, type Pt } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import TrendChart, { type TrendPoint } from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import BopFlowChart from "@/app/components/BopFlowChart";

// Build a StackedArea/BopFlowChart `series` list from a {code: label} map,
// preserving order (= stack/legend order).
const seriesOf = (labels: Record<string, string>) =>
  Object.entries(labels).map(([key, label]) => ({ key, label }));

// One series code as a % of the per-period sum across all codes → Pt series.
// Used for the mobile-only share of active individuals and the remote share
// of new customers — same arithmetic the percent-stacked charts render.
function codeShare(points: TrendPoint[], code: string): Pt[] {
  const byPeriod = new Map<string, Record<string, number>>();
  for (const p of points) {
    if (p.value == null) continue;
    let e = byPeriod.get(p.period);
    if (!e) byPeriod.set(p.period, (e = {}));
    e[p.bank_type_code] = (e[p.bank_type_code] ?? 0) + p.value;
  }
  const out: Pt[] = [];
  for (const [period, e] of [...byPeriod.entries()].sort()) {
    const total = Object.values(e).reduce((s, v) => s + v, 0);
    if (total > 0) out.push({ period, value: (100 * (e[code] ?? 0)) / total });
  }
  return out;
}

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

  // ---- the brief's computed vitals -----------------------------------------
  // Quarterly series (TBB/TKBB, 'YYYY-MM' quarter-ends): y/y = 4 periods back.
  // Monthly acquisition series: y/y = 12 periods back.
  const mobileActive = activeByChannel.filter((r) => r.bank_type_code === "mobile");
  const internetActive = activeByChannel.filter((r) => r.bank_type_code === "internet");
  const mobNow = lastVal(mobileActive);
  const mobAgo = valAgo(mobileActive, 4);
  const mobYoY = mobNow != null && mobAgo != null && mobAgo > 0 ? (mobNow / mobAgo - 1) * 100 : null;
  const intNow = lastVal(internetActive);

  const mobileOnlyTbb = codeShare(channelUse, "mobile_only");
  const moNow = lastVal(mobileOnlyTbb);
  const moAgo = valAgo(mobileOnlyTbb, 4);
  const moDelta = moNow != null && moAgo != null ? moNow - moAgo : null;

  const netAddsMobile = netAdds
    .filter((r) => r.bank_type_code === "mobile")
    .sort((a, b) => a.period.localeCompare(b.period));
  const netNow = lastVal(netAddsMobile);
  const netAgo = valAgo(netAddsMobile, 4);

  const remoteShareTbb = codeShare(acq.byChannel, "digital");
  const remNow = lastVal(remoteShareTbb);
  const remAgo = valAgo(remoteShareTbb, 12);
  const remDelta = remNow != null && remAgo != null ? remNow - remAgo : null;

  const partNow = lastVal(tkbbShare);
  const partAgo = valAgo(tkbbShare, 4);
  const partDelta = partNow != null && partAgo != null ? partNow - partAgo : null;

  const mobileVol = transferVolume.filter((r) => r.bank_type_code === "mobile");
  const volNow = lastVal(mobileVol);
  const volAgo = valAgo(mobileVol, 4);
  const volYoY = volNow != null && volAgo != null && volAgo > 0 ? (volNow / volAgo - 1) * 100 : null;

  const qLatest = latestPeriod(activeByChannel, transferVolume, gender);
  const acqLatest = acq.byChannel.at(-1)?.period;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Digital Banking"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(qLatest)}</b> quarter-end
            (TBB/TKBB) · acquisition monthly to {monthLabel(acqLatest)}
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="adoption · funnel · acquisition · participation"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={6}>
        <Vital
          label="Active mobile customers"
          value={mobNow != null ? mobNow.toFixed(0) : "—"}
          unit="m"
          series={mobileActive.slice(-9)}
          format="raw"
          decimals={0}
          note={
            mobYoY != null ? (
              <>
                +{mobYoY.toFixed(0)}% y/y · internet at{" "}
                {intNow != null ? intNow.toFixed(0) : "—"}m
              </>
            ) : (
              "sector total, quarter-end"
            )
          }
        />
        <Vital
          label="Mobile-only share"
          value={moNow != null ? moNow.toFixed(1) : "—"}
          unit="%"
          series={mobileOnlyTbb.slice(-9)}
          decimals={1}
          note={
            moDelta != null
              ? `${signedPp(moDelta, 1)} y/y — of active digital individuals`
              : "of active digital individuals"
          }
        />
        <Vital
          label="Net adds, quarter"
          value={netNow != null ? netNow.toFixed(1) : "—"}
          unit="m"
          series={netAddsMobile.slice(-9)}
          format="raw"
          decimals={1}
          note={
            netAgo != null
              ? `mobile registered-base delta — vs ${netAgo.toFixed(1)}m a year ago`
              : "mobile registered-base delta"
          }
        />
        <Vital
          label="Acquired remotely"
          value={remNow != null ? remNow.toFixed(0) : "—"}
          unit="%"
          series={remoteShareTbb.slice(-13)}
          decimals={0}
          note={
            remDelta != null
              ? `${signedPp(remDelta, 1)} over 12m — share of new individual customers, trailing 3m`
              : "share of new individual customers, trailing 3m"
          }
        />
        <Vital
          label="Participation share"
          value={partNow != null ? partNow.toFixed(1) : "—"}
          unit="%"
          series={tkbbShare.slice(-9)}
          decimals={1}
          note={
            partDelta != null
              ? `${signedPp(partDelta, 1)} y/y — of all active digital customers (TKBB vs TBB)`
              : "of all active digital customers (TKBB vs TBB)"
          }
        />
        <Vital
          label="Mobile transfers"
          value={volNow != null ? volNow.toFixed(1) : "—"}
          unit="₺trn"
          series={mobileVol.slice(-9)}
          format="raw"
          decimals={1}
          note={
            volYoY != null
              ? `+${volYoY.toFixed(0)}% y/y — money-transfer volume per quarter`
              : "money-transfer volume per quarter"
          }
        />
      </Vitals>

      <Depth action={<GlobalRangeSelector />}>
        <Section
          index="01"
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
          index="02"
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
          <ChartRow
            data={applications}
            labels={APPLICATION_LABELS}
            deltaPeriods={4}
            deltaLabel="4q"
            fmt={(v) => `${v.toFixed(1)}m`}
          >
            <StackedArea
              data={pivotWide(applications)}
              series={seriesOf(APPLICATION_LABELS)}
              title="Product applications via mobile per quarter (millions)"
              decimals={1}
              height={320}
              colorKeys
            />
          </ChartRow>
        </Section>

        <Section
          index="03"
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
          <ChartRow
            data={acq.byMethod}
            labels={ACQ_METHOD_LABELS}
            deltaPeriods={12}
            deltaLabel="12m"
            fmt={(v) => `${v.toFixed(0)}k`}
          >
            <StackedArea
              data={pivotWide(acq.byMethod)}
              series={seriesOf(ACQ_METHOD_LABELS)}
              title="New individual customers by acquisition method (thousands, trailing 3 months)"
              decimals={0}
              height={320}
              colorKeys
            />
          </ChartRow>
        </Section>

        <Section
          index="04"
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
          <ChartRow
            data={billCount}
            labels={CHANNEL_LABELS}
            deltaPeriods={4}
            deltaLabel="4q"
            fmt={(v) => `${v.toFixed(0)}m`}
          >
            <TrendChart
              data={billCount}
              seriesLabels={CHANNEL_LABELS}
              title="Bill-payment count per quarter (millions)"
              yFormat="raw"
              decimals={0}
              height={320}
            />
          </ChartRow>
        </Section>

        <Section
          index="05"
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
          index="06"
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
          index="07"
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
      </Depth>

      <Colophon>
        Compiled, not written — every figure computed from TBB &amp; TKBB source
        series (quarterly digital statistics · monthly acquisition reports); each
        association applies its own definitions. No forecasts. Analytical
        information, not investment advice.
      </Colophon>
    </main>
  );
}
