import { SectorReport, SectorHeader, SectorContents, SectorMetrics, SectorSection, SectorDirectory, SectorFooter, SectorOpening, SectorGrid, SectorPanel } from "@/app/components/sector-report";
/** Capital adequacy, audited composition, bank comparisons and balance-sheet risk. */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  ratioCar,
  ratioRwaDensity,
  ratioOffBsDerivatives,
  totalEquity,
  equityYoY,
  totalAssetsYoY,
  leverage,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { sectorCapitalRatios, perBankCapital, AUDIT_CAPITAL_LABELS } from "@/app/lib/audit-ratios";
import { CAR_TARGET, CAR_LEGAL_MIN } from "@/app/lib/capital-thresholds";
import { BANK_NAMES } from "@/app/lib/bank_names";
import BarByBank from "@/app/components/BarByBank";
import CapitalByBank from "./CapitalByBank";
import StepWaterfall from "./StepWaterfall";
import SectorTrend from "@/app/components/SectorTrend";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { capitalInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  CadenceBand,
  ChartFoot,
  Levels,
  Movers,
  SecHead,
  Standings,
  Transmission,
  Vital,
  Vitals,
  type MoverRow,
  type StandingsGroup,
  type TransmissionItem,
} from "@/app/components/desk";
import { deltaByGroup, lastVal, leaderOf, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { VERBS, bandsFor, claim, direction, firstClaim } from "@/app/lib/prose";
import {
  capitalStack,
  decompose12m,
  detectStep,
  everyGroupMoved,
  postStepDrift,
  quartersToFloor,
  stepWords,
} from "@/app/lib/capital";
import { GlobalRangeSelector } from "@/app/components/range-context";

export const dynamic = "force-dynamic";

const pageMetadata: Metadata = {
  title: "Turkish Banks — Capital Adequacy (CAR)",
  description: "Capital adequacy of Türkiye's banking sector: CAR/SYR, Tier 1 and leverage by bank and ownership group, from BRSA data.",
  alternates: { canonical: "/capital" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

/** Route link styled for use inside a computed note. */
const Go = ({ href, children }: { href: string; children: ReactNode }) => (
  <Link href={href} className="font-semibold text-primary">
    {children}
  </Link>
);

/** '2026Q1' → 'Q1 2026' for the audited-quarter notes. */
function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
  return m ? `Q${m[2]} ${m[1]}` : p ?? "—";
}

export default async function CapitalPage() {
  const tx = await getText();
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    carAll, carByBank, equity, equityYoYSec, lev,
    rwa, offBsDeriv, capRatios, assetsYoYSec, byBankCap,
  ] = await Promise.all([
    ratioCar(PRIMARY_BANK_TYPES),
    latestPerBank(ratioCar, groups),
    totalEquity(sector),
    equityYoY(sector),
    leverage(PRIMARY_BANK_TYPES),
    ratioRwaDensity(PRIMARY_BANK_TYPES),
    ratioOffBsDerivatives(PRIMARY_BANK_TYPES),
    sectorCapitalRatios(),
    totalAssetsYoY(sector),
    perBankCapital(),
  ]);

  // ---- the step, not the drift --------------------------------------------
  // Capital adequacy did not ease — it STEPPED: −2.92pp between Dec 2025 and Jan
  // 2026, in every ownership group, the largest one-month move on record. The
  // old headroom device extrapolated a 12-month average that straddles that
  // discontinuity. So: detect the break from the series (rule, not a hand-picked
  // date), split the year into the step and everything else, and size the buffer
  // against the slope measured AFTER the break.
  const carSector = carAll.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const carNow = carSector.at(-1)?.value ?? null;
  const buffer = carNow != null ? carNow - CAR_TARGET : null;

  const step = detectStep(carSector, { window: 13, k: 3 });
  const breakPeriod = step?.isBreak ? step.period : null;
  const split = decompose12m(carSector, breakPeriod);
  const post = postStepDrift(carSector, breakPeriod);

  // The two levels the step sits between — the month before it, and the month
  // it landed. (Not the latest value: that is a third number entirely.)
  const stepIdx = breakPeriod ? carSector.findIndex((r) => r.period === breakPeriod) : -1;
  const beforeStep = stepIdx > 0 ? (carSector[stepIdx - 1].value ?? null) : null;
  const afterStep = stepIdx > 0 ? (carSector[stepIdx].value ?? null) : null;
  // Drift used for sizing: post-step when there IS a break, else the plain 12m.
  const drift = post?.perYear ?? split?.total ?? null;
  const qtrsToFloor = quartersToFloor(carNow, drift, CAR_TARGET);
  const driftBasis = breakPeriod
    ? tx("post-step · {0}m since {1}", {0: post?.months ?? 0, 1: monthLabel(breakPeriod, false)})
    : "12-month drift";

  const eqG = equityYoYSec.at(-1)?.value ?? null;
  const asG = assetsYoYSec.at(-1)?.value ?? null;
  const genGap = eqG != null && asG != null ? eqG - asG : null;

  // ---- vitals — computed from the series above ------------------------------
  const t1Series = capRatios.filter((r) => r.bank_type_code === "TIER1");
  const cet1Series = capRatios.filter((r) => r.bank_type_code === "CET1");
  const rwaSector = rwa.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const levSector = lev.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);

  const t1Now = lastVal(t1Series);
  const cet1Now = lastVal(cet1Series);
  const rwaNow = lastVal(rwaSector);
  const levNow = lastVal(levSector);

  const t1Ago = valAgo(t1Series, 4); // 4 audited quarters ≈ a year
  const t1Delta4q = t1Now != null && t1Ago != null ? t1Now - t1Ago : null;
  const rwaAgo = valAgo(rwaSector, 12);
  const rwaDrift = rwaNow != null && rwaAgo != null ? rwaNow - rwaAgo : null;
  const levX = levNow != null ? 1 + levNow / 100 : null; // assets/equity = 1 + L/E

  // Two chart titles used to TYPE a direction and a ranking ("Gearing keeps
  // climbing — the state banks lean hardest"; "a foreign-bank story") next to the
  // series that settles them. Both are the charts' own `data` props.
  const groupOnly = [BANK_TYPES.SECTOR];
  const levTop = leaderOf(lev, { exclude: groupOnly });
  const levTopLabel = levTop ? (BANK_TYPE_LABELS[levTop.code] ?? "").toLowerCase() : null;
  const levTrend = direction(
    deltaByGroup(lev, 12).get(BANK_TYPES.SECTOR) ?? null,
    VERBS.trend,
    bandsFor(levNow ?? 900),
  );
  const derivTop = leaderOf(offBsDeriv, { exclude: groupOnly });
  const derivTopLabel = derivTop ? (BANK_TYPE_LABELS[derivTop.code] ?? "").toLowerCase() : null;

  const recMonth = monthLabel(carSector.at(-1)?.period);
  const vsMonth = monthLabel(carSector.at(-2)?.period, false);
  const auditQ = quarterLabel(cet1Series.at(-1)?.period);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = capitalInsights({
    car: carSector,
    cet1: cet1Series,
    equityYoY: equityYoYSec,
    leverage: levSector,
    assetsYoY: assetsYoYSec,
  }, tx.locale);

  // ---- what the buffer is made of -----------------------------------------
  // All three components are positive and sum to total capital by construction,
  // so this one legitimately draws as a stack (unlike /liquidity's reserves).
  const stack = capitalStack(capRatios);
  const stackNow = stack.at(-1) ?? null;
  const hybrids = stackNow ? stackNow.at1 + stackNow.t2 : null;
  const cet1Share = stackNow && stackNow.car > 0 ? (stackNow.cet1 / stackNow.car) * 100 : null;
  // Compare like with like: the hybrid stack is AUDITED (Σ/Σ over the filings),
  // so it must be set against the AUDITED buffer — not the monthly bulletin's
  // CAR, which is a different basis (16.02% vs 16.34%) and would flatter it.
  const auditBuffer = stackNow ? stackNow.car - CAR_TARGET : null;

  const fmtPct = (v: number | null | undefined, d = 1) =>
    v == null ? "—" : `${v.toFixed(d)}%`;

  // ---- movers: the MONTHLY record (the stack is audited quarterly) ---------
  const mv = (s: { value: number | null }[]) => ({
    prev: s.at(-2)?.value ?? null,
    curr: s.at(-1)?.value ?? null,
  });
  const moverRows: MoverRow[] = [
    { label: "Capital adequacy", ...mv(carSector), fmt: (v) => `${v.toFixed(2)}%`, good: "up" },
    {
      label: "Risk-weighted asset density", note: "rwa net ÷ gross",
      ...mv(rwaSector), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "neutral",
    },
    {
      label: "Liabilities / equity", note: "gearing",
      ...mv(levSector), fmt: (v) => `${v.toFixed(0)}%`, deltaDecimals: 0, good: "down",
    },
    {
      label: "Equity growth, y/y", note: "the generation side",
      ...mv(equityYoYSec), fmt: (v) => `${v.toFixed(1)}%`, deltaDecimals: 1, good: "up",
    },
  ];

  // ---- the step → the ratio ------------------------------------------------
  //
  // detectStep() picks by |Δ| and returns a SIGNED delta, so every word below
  // that names a direction has to be read off it — and whether the groups really
  // moved together is a question carAll can answer, not one to remember.
  const sw = step ? stepWords(step) : null;
  const together =
    step && sw ? everyGroupMoved(carAll, step.period, sw.dir, [BANK_TYPES.SECTOR]) : false;

  // "RWA density barely moved" is asserted in three places to argue the step came
  // through the CAPITAL numerator rather than the risk mix. It is a testable claim
  // about a series this page already holds — so test it.
  const rwaClean = rwaSector.filter((r) => r.value != null);
  const rwaStepIdx = step ? rwaClean.findIndex((r) => r.period === step.period) : -1;
  const rwaStepDelta =
    rwaStepIdx > 0 ? rwaClean[rwaStepIdx].value! - rwaClean[rwaStepIdx - 1].value! : null;
  const rwaStepMove = direction(rwaStepDelta, VERBS.move, bandsFor(rwaNow ?? 100));
  const rwaHeld = rwaStepMove === VERBS.move.flat;

  const transmission: TransmissionItem[] = [];
  if (step?.isBreak && split && sw) {
    transmission.push({
      k: monthLabel(step.period),
      v: step.delta.toFixed(2),
      unit: "pp",
      effect: (
        <>{tx(together
          ? "Capital adequacy changed {0}pp in one month, versus a typical monthly move of {1}pp. Every ownership group moved in the same direction. This is a level shift, not a trend."
          : "Capital adequacy changed {0}pp in one month, versus a typical monthly move of {1}pp. Ownership groups did not all move in the same direction. This is a level shift, not a trend.",
        {0: step.delta.toFixed(2), 1: step.typical.toFixed(2)})}</>
      ),
    });
    transmission.push({
      k: "Ex-step",
      v: signedPp(split.rest, 2).replace("pp", ""),
      unit: "pp",
      effect: (
        <>{tx(split.rest >= 0
          ? "The 12-month change is {0}: {1} from the level shift and {2} from the other months. Excluding the shift, the sector capital ratio increased over the rest of the year."
          : "The 12-month change is {0}: {1} from the level shift and {2} from the other months. Excluding the shift, the sector capital ratio decreased over the rest of the year.",
        {0: signedPp(split.total, 2), 1: signedPp(split.step, 2), 2: signedPp(split.rest, 2)})}</>
      ),
    });
  }
  if (auditBuffer != null && hybrids != null) {
    transmission.push({
      k: "Reserve position",
      v: auditBuffer.toFixed(2),
      unit: tx("pp · audited {0}", {0: auditQ}),
      effect: (
        <>{tx(hybrids > auditBuffer
          ? "The audited buffer above BDDK's {0}% target is {1}pp; the statutory floor is {2}%. AT1 and Tier-2 total {3}pp, more than the buffer itself. Without those instruments, total capital falls to {4}. The monthly bulletin's {5} CAR uses a different basis."
          : "The audited buffer above BDDK's {0}% target is {1}pp; the statutory floor is {2}%. AT1 and Tier-2 total {3}pp, so common equity is larger than the instrument-funded part of the cushion. The monthly bulletin's {5} CAR uses a different basis.",
        {0: CAR_TARGET, 1: auditBuffer.toFixed(2), 2: CAR_LEGAL_MIN, 3: hybrids.toFixed(2), 4: fmtPct(stackNow?.cet1, 2), 5: fmtPct(carNow, 2)})}</>
      ),
    });
  }
  if (drift != null && qtrsToFloor != null) {
    transmission.push({
      k: "Drift, sized",
      v: `${drift >= 0 ? "+" : "−"}${Math.abs(drift).toFixed(2)}`,
      unit: "pp/yr",
      effect: (
        <>{tx("Measured on a {0} basis. At this pace the buffer reaches the target in about {1} quarters. This is a sizing exercise, not a forecast; the level shift is excluded from the run rate.",
        {0: driftBasis, 1: Math.round(qtrsToFloor)})}</>
      ),
    });
  }
  if (step?.isBreak) {
    transmission.push({
      k: "Attribution",
      v: "—",
      effect: (
        <>
          {tx(rwaHeld
            ? "The level shift cannot be attributed from the available data. RWA density barely moved ({0}), pointing to the capital numerator rather than the risk mix; no regulation in the available window explains the change."
            : "The level shift cannot be attributed from the available data. RWA density moved {0} in the same month, so the risk mix moved as well; no regulation in the available window explains the change.",
          {0: rwaHeld ? fmtPct(rwaNow) : signedPp(rwaStepDelta ?? 0, 1)})}{" "}
          <Go href="/regulation">{tx("/regulation")}</Go>
        </>
      ),
    });
  }



  // ---- standings: the thin end of the register -----------------------------
  const withCet1 = byBankCap.rows.filter((b) => b.cet1 != null && b.car != null);
  const standings: StandingsGroup[] = [
    {
      heading: tx("Thinnest common equity — CET1 · {0}", {0: auditQ}),
      rows: [...withCet1]
        .sort((a, b) => (a.cet1 as number) - (b.cet1 as number))
        .slice(0, 3)
        .map((b, i) => ({
          rank: i + 1,
          name: BANK_NAMES[b.bank_ticker] ?? b.bank_ticker,
          value: fmtPct(b.cet1, 2),
          tone: "dn" as const,
        })),
    },
    {
      heading: "Most of the ratio bought — CAR − CET1",
      rows: [...withCet1]
        .sort(
          (a, b) =>
            ((b.car as number) - (b.cet1 as number)) - ((a.car as number) - (a.cet1 as number)),
        )
        .slice(0, 3)
        .map((b, i) => ({
          rank: i + 1,
          name: BANK_NAMES[b.bank_ticker] ?? b.bank_ticker,
          value: `${((b.car as number) - (b.cet1 as number)).toFixed(1)}pp`,
        })),
    },
  ];

  const sectorAssessment = await withLlmHeadline("capital", read, tx.locale);

  return (
    <SectorReport>
<SectorHeader sector="capital" record={<>{tx("Record ")}<b className="font-normal text-foreground">{tx(recMonth)}</b>{tx(" · vs ")}{tx(vsMonth)}
          </>} observations={[
          {
            cadence: "monthly",
            role: "current",
            asOf: carSector.at(-1)?.period,
            window: "13m context",
            basis: "BDDK published sector ratios",
          },
          {
            cadence: "quarterly",
            role: "audited",
            asOf: auditQ,
            basis: "sum of reporting banks' BRSA filings",
          },
        ]} />
<SectorContents sections={[{id: "overview", label: "Key indicators"}, {id: "adequacy", label: "Capital adequacy"}, {id: "composition", label: "Capital composition"}, {id: "banks", label: "Capital by bank"}, {id: "leverage", label: "Equity and leverage"}, {id: "risk-weights", label: "Risk-weighted assets"}]} controls={<GlobalRangeSelector compact />} />
<SectorOpening>
<SectorMetrics><Vital
          label={tx("Capital adequacy")}
          value={carNow != null ? carNow.toFixed(1) : "—"}
          unit="%"
          series={carSector.slice(-13)}
          decimals={1}
          note={
            <>{buffer != null
              ? tx("CAR is {0}pp above the 12% target{1}.",
                { 0: buffer.toFixed(1), 1: drift != null ? tx("; annualized drift is {0}", { 0: signedPp(drift, 1) }) : "" })
              : tx("The current CAR buffer is unavailable.")}</>
          }
        />
<Vital
          label={tx("Equity growth, y/y")}
          value={eqG != null ? eqG.toFixed(1) : "—"}
          unit="%"
          series={equityYoYSec.slice(-13)}
          decimals={1}
          note={
            <>{genGap != null ? (
              <b className={genGap >= 0 ? "font-semibold text-positive" : "font-semibold text-negative"}>
                {tx(
                  genGap >= 0
                    ? "Equity growth is {0}pp above asset growth."
                    : "Equity growth is {0}pp below asset growth.",
                  { 0: Math.abs(genGap).toFixed(1) },
                )}
              </b>
            ) : tx("Asset-growth comparison is unavailable.")} {" "}
              <Go href="/profitability">{tx("Profitability detail")}</Go>
            </>
          }
        />
<Vital
          label={tx("Risk-weighted asset density")}
          value={rwaNow != null ? rwaNow.toFixed(1) : "—"}
          unit="%"
          series={rwaSector.slice(-13)}
          decimals={1}
          note={<>{tx(rwaDrift != null ? tx("{0} over 12m", { 0: signedPp(rwaDrift, 1) }) : "—")}{tx(" · RWA net / gross")}</>}
        />
<Vital
          label={tx("Liabilities / equity")}
          value={levNow != null ? levNow.toFixed(0) : "—"}
          unit={levNow != null ? "%" : undefined}
          series={levSector.slice(-13)}
          decimals={0}
          note={levX != null
            ? <>≈ {tx(`${levX.toFixed(1)}×`)}{tx(" assets / equity")}</>
            : <>{tx("The current bulletin does not provide this ratio.")}</>}
        /></SectorMetrics>
<Takeaway data={sectorAssessment} variant="report-summary" />
</SectorOpening>
<SectorSection id="adequacy" title={tx("Capital adequacy")} description={tx("Published sector ratios, changes over time and bank-group comparisons.")}>
<SectorTrend mode="groups" references={[{ value: CAR_TARGET, label: tx("BDDK target") }, { value: CAR_LEGAL_MIN, label: tx("Statutory minimum") }]}

          data={carAll}
          seriesLabels={BANK_TYPE_LABELS}
          title={tx("Capital adequacy by bank group")}
          description={<><span className="block">{tx(firstClaim(
              [
                step?.isBreak && together && !!sw,
                tx("Every ownership group {0} together in {1}", { 0: sw?.verb, 1: monthLabel(step?.period ?? null, false) }),
              ],
              [
                step?.isBreak && !!sw,
                tx("Capital adequacy {0} {1} in {2} — but not every group moved with it", { 0: sw?.verb, 1: signedPp(step?.delta ?? 0, 1), 2: monthLabel(step?.period ?? null, false) }),
              ],
            ) ??
              seriesFinding(carSector, { noun: "Capital adequacy", decimals: 1 }, tx.locale) ??
              "Capital adequacy — by group")}</span><span className="mt-1 block">{tx("capital adequacy (syr), %, monthly · by group · target ratio 12%")}</span></>}
          source={
            <ChartFoot data={carAll} labels={BANK_TYPE_LABELS} decimals={1} deltaPeriods={12} />
          }
          yFormat="pct"
          decimals={1}
          deltaPeriods={12}
          deltaLabel="12m"
          height={320}

          referencePeriod={step?.isBreak ? step.period : undefined}
          referenceLabel={step?.isBreak ? `${step.delta.toFixed(2)}pp` : undefined}
        />
<Takeaway data={sectorAssessment} variant="report-details" />

<SectorGrid ratio="wide-left">
<div className="min-w-0 space-y-5">{split && step?.isBreak ? (
              <StepWaterfall
                fromLabel={monthLabel(carSector.at(-13)?.period ?? null)}
                toLabel={monthLabel(carSector.at(-1)?.period ?? null)}
                from={split.from}
                to={split.to}
                step={split.step}
                rest={split.rest}
                stepLabel={tx("The {0} step", { 0: monthLabel(step.period, false) })}
                title={tx("Capital adequacy — change over 12 months")}
                description={<>
                  <span className="block">{tx("12-month change in the capital adequacy ratio, percentage points.")}</span>
                  <span className="mt-2 block">{tx("The ratio changed by {0} over 12 months. The change in {1} was {2}; the remaining months contributed {3}.", { 0: signedPp(split.total, 2), 1: monthLabel(step.period, false), 2: signedPp(split.step, 2), 3: signedPp(split.rest, 2) })}</span>
                </>}
                source={
                  <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[13px] text-faint">
                    <span>
                      12M <b className="font-semibold text-foreground">{tx(signedPp(split.total, 2))}</b>
                    </span>
                    <span>{tx("THE STEP")}{" "}
                      <b className="font-semibold text-foreground">{tx(signedPp(split.step, 2))}</b>
                    </span>
                    <span>{tx("EX-STEP")}{" "}
                      <b className="font-semibold text-foreground">{tx(signedPp(split.rest, 2))}</b>
                    </span>
                    <span>{tx("SIZED ON")}{" "}
                      <b className="font-semibold text-foreground">
                        {tx(drift != null ? `${drift.toFixed(2)}pp/yr · ${driftBasis}` : "—")}
                      </b>
                    </span>
                  </div>
                }
                height={280}
              />
            ) : (
              <BarByBank
                data={carByBank}
                labels={BANK_TYPE_LABELS}
                title={tx("CAR by group · {0}", { 0: carByBank[0]?.period ?? "" })}
                format="pct"
                decimals={1}
              />
            )}
{step?.isBreak && split && (
            <Levels
              items={[
                {
                  k: monthLabel(carSector[stepIdx - 1]?.period ?? null),
                  v: fmtPct(beforeStep, 2),
                },
                { k: monthLabel(step.period), v: fmtPct(afterStep, 2) },
                { k: "The step", v: `${step.delta.toFixed(2)}pp` },
                {
                  k: monthLabel(carSector.at(-1)?.period ?? null),
                  v: fmtPct(split.to, 2),
                },
              ]}
            />
          )}
{step?.isBreak && (
            <p className="mt-4 max-w-[96ch] text-[13px] leading-relaxed text-muted-foreground">
              <b className="font-semibold text-foreground">{tx("Not attributed.")}</b>{tx(" The step is in the data, not in the explanation: no rule in our regulation window covers it, and RWA density")}{" "}
              {rwaHeld ? (
                <>{tx("barely moved (")}{tx(fmtPct(rwaNow))}{tx("), so it arrived through the capital numerator rather than the risk mix")}</>
              ) : (
                <>
                  {tx(rwaStepMove)} {tx(signedPp(rwaStepDelta ?? 0, 1))}{tx(" in the same month, so the risk mix moved with it")}</>
              )}{tx(". The buffer is therefore sized against the")}{" "}
              <b className="font-semibold text-foreground">{tx(driftBasis)}</b>{tx(" slope — extrapolating a step would be arithmetic dressed as a forecast.")}</p>
          )}</div><SectorPanel>
<div>
          <SecHead title={tx("Period changes")} meta={tx("{0} → {1} · monthly", { 0: vsMonth, 1: monthLabel(carSector.at(-1)?.period, false) })} className="mb-2.5" />
          <Movers
            from={vsMonth.toUpperCase()}
            to={monthLabel(carSector.at(-1)?.period, false).toUpperCase()}
            rows={moverRows}
          />
        </div>
</SectorPanel>
</SectorGrid>
<SectorPanel>
<div>
          <SecHead
            title={tx(step?.isBreak ? "Changes in capital adequacy" : "Capital and balance-sheet growth")}
            meta={tx("Capital ratios and balance-sheet changes")}
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
</SectorPanel>
</SectorSection>
<SectorSection id="composition" title={tx("Capital composition")} description={tx("audited §4 · Σ component ÷ Σ RWA · {0}", { 0: auditQ })}>
<SectorPanel>
<CadenceBand
        title={tx("Audited capital composition")}
        observation={{
          cadence: "quarterly",
          role: "audited",
          asOf: auditQ,
          basis: "sum of reporting banks' capital and RWA",
        }}
      >
        <Vitals cols={2} rule="hair">
          <Vital
            label={tx("Tier-1 (audited)")}
            value={t1Now != null ? t1Now.toFixed(1) : "—"}
            unit="%"
            series={t1Series.slice(-8)}
            decimals={1}
            note={
              <>
                {tx(t1Delta4q != null ? tx("{0} over 4 audited qtrs", { 0: signedPp(t1Delta4q, 1) }) : tx("audited {0}", { 0: auditQ }))}
              </>
            }
          />
          <Vital
            label={tx("CET1 (audited)")}
            value={cet1Now != null ? cet1Now.toFixed(1) : "—"}
            unit="%"
            series={cet1Series.slice(-8)}
            decimals={1}
            note={<>{tx("audited ")}{tx(auditQ)}{tx(" · Σ capital ÷ Σ RWA")}</>}
          />
        </Vitals>
      </CadenceBand>
</SectorPanel>
<SectorGrid ratio="balanced">
<StackedArea
              plain
              data={stack as unknown as Record<string, string | number | null>[]}
              series={[
                { key: "cet1", label: "CET1" },
                { key: "at1", label: "AT1" },
                { key: "t2", label: "Tier-2" },
              ]}
              title={
                // auditBuffer, NOT buffer: this chart is the audited stack, and the
                // hybrid-buffer flag above tests the same claim on the audited basis.
                // Against the bulletin's CAR (a different basis — 16.34 vs 16.07) the
                // title said composition was fine while the flag said it was not.
                tx(hybrids != null && auditBuffer != null && hybrids > auditBuffer
                  ? "The buffer above the BDDK target is supported by AT1 and Tier 2 instruments"
                  : "Capital composition — CET1, AT1 and Tier-2")
              }
              description={tx("capital stack, % of RWA, audited quarterly · sums to total capital")}
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>{tx("CET1 ")}<b className="font-semibold text-foreground">{tx(fmtPct(stackNow?.cet1, 2))}</b>
                  </span>
                  <span>{tx("AT1 ")}<b className="font-semibold text-foreground">{tx(fmtPct(stackNow?.at1, 2))}</b>
                  </span>
                  <span>{tx("TIER-2 ")}<b className="font-semibold text-foreground">{tx(fmtPct(stackNow?.t2, 2))}</b>
                  </span>
                  <span>{tx("CET1 SHARE")}{" "}
                    <b className="font-semibold text-foreground">
                      {tx(fmtPct(cet1Share, 0))}{tx(" of capital")}</b>
                  </span>
                </div>
              }
              yFormat="pct"
              decimals={2}
              height={280}
            />
<SectorTrend mode="trend" deltaBasis="published" deltaFromFullHistory deltaPeriods={4} deltaLabel="4q" source={tx("Source: BRSA quarterly filings (§4)")}

                data={capRatios}
                seriesLabels={AUDIT_CAPITAL_LABELS}
                title={tx("CET1, Tier 1 and total capital ratios")}
                description={tx("audited quarterly, % of RWA · sector · Σ component ÷ Σ RWA")}
                yFormat="pct"
                decimals={1}
                height={320}
                hero="CET1"
              />
</SectorGrid>
</SectorSection>
<SectorSection id="banks" title={tx("Capital by bank")} description={tx("Bank-level capital ratios from quarterly financial statements.")}>
<SectorPanel>
<div>
          <SecHead title={tx("Bank comparisons")} meta={tx("audited {0}", { 0: auditQ })} href="/banks" hrefLabel={tx("by bank →")} className="mb-2.5" />
          <Standings groups={standings} />
        </div>
</SectorPanel>
<SectorPanel>
<CapitalByBank period={byBankCap.period} rows={byBankCap.rows} />
</SectorPanel>
</SectorSection>
<SectorSection id="leverage" title={tx("Equity and leverage")} description={tx("Equity levels, annual growth and leverage")}>
<SectorGrid ratio="balanced">
<SectorTrend mode="trend" hero="EQUITY"

              data={[...equityYoYSec.map(row => ({ ...row, bank_type_code: "EQUITY" })), ...assetsYoYSec.map(row => ({ ...row, bank_type_code: "ASSETS" }))]}
              seriesLabels={{ EQUITY: "Equity y/y", ASSETS: "Asset growth, y/y" }}
              title={tx("Equity and asset growth")}
              description={<><span className="block">{tx(genGap == null
                  ? "Equity growth — sector"
                  : genGap >= 0
                    ? "Equity compounds faster than the balance sheet — generation is not the constraint"
                    : "The balance sheet is outgrowing its equity")}</span><span className="mt-1 block">{tx("equity growth y/y, %, monthly · sector")}</span></>}
              source={
                <ChartFoot
                  data={equityYoYSec}
                  labels={{ [BANK_TYPES.SECTOR]: "Equity y/y" }}
                  decimals={1}
                  deltaPeriods={12}
                />
              }
              yFormat="pct"
              decimals={1}
              height={320}
              zeroLine
            />
<SectorTrend mode="trend"

              data={equity}
              seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity" }}
              title={tx("Total sector equity")}
              description={tx("sector equity, ₺ trn, monthly")}
              source={tx("Source: BDDK monthly bulletin")}
              yFormat="trn"
              decimals={2}
              height={320}
            />
</SectorGrid>
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={lev}
              seriesLabels={BANK_TYPE_LABELS}
              // Both halves were typed: a direction AND a ranking, next to the very
              // series that decides them. `lev` is this chart's own data prop.
              title={tx("Liabilities relative to equity")}
              description={<><span className="block">{tx(firstClaim(
                  [
                    levTrend != null && levTrend !== VERBS.trend.flat && levTopLabel != null,
                    tx("Gearing keeps {0} — the {1} banks lean hardest", { 0: levTrend, 1: levTopLabel }),
                  ],
                  [
                    levTopLabel != null,
                    tx("Gearing is flat — the {0} banks lean hardest", { 0: levTopLabel }),
                  ],
                ) ?? "Liabilities ÷ equity — by group")}</span><span className="mt-1 block">{tx("liabilities ÷ equity, %, monthly · by ownership group")}</span></>}
              source={
                <ChartFoot data={lev} labels={BANK_TYPE_LABELS} decimals={0} deltaPeriods={12} />
              }
              yFormat="pct"
              decimals={0}
              height={320}
               />
</SectorSection>
<SectorSection id="risk-weights" title={tx("Risk-weighted assets")} description={tx("Risk-weighted assets and off-balance-sheet exposures")}>
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={rwa}
              seriesLabels={BANK_TYPE_LABELS}
              title={tx("Risk-weighted asset density")}
              description={<><span className="block">{tx(firstClaim(
                  [
                    step?.isBreak && rwaHeld && !!sw,
                    tx("Risk density barely moved through the step — the {0} came from capital, not the risk mix", { 0: sw?.noun }),
                  ],
                  [
                    step?.isBreak && !rwaHeld && rwaStepDelta != null,
                    tx("Risk density {0} {1} through the step — the risk mix moved with it", { 0: rwaStepMove, 1: signedPp(rwaStepDelta ?? 0, 1) }),
                  ],
                ) ?? "RWA net / gross — by group")}</span><span className="mt-1 block">{tx("rwa net ÷ gross, %, monthly · lower = more low-weight exposure")}</span></>}
              source={
                <ChartFoot data={rwa} labels={BANK_TYPE_LABELS} decimals={1} deltaPeriods={12} />
              }
              yFormat="pct"
              decimals={1}
              height={320}
               />
<SectorTrend deltaPeriods={12} deltaLabel="12m" mode="groups"

              data={offBsDeriv}
              seriesLabels={BANK_TYPE_LABELS}
              // "a foreign-bank story" — true when written, and never re-checked.
              // Phrased so it reads for whichever group actually leads.
              title={tx("Off-balance-sheet derivatives relative to assets")}
              description={<><span className="block">{tx(claim(
                  derivTopLabel != null,
                  tx("The derivative book is concentrated in the {0} banks", { 0: derivTopLabel }),
                ) ?? "Off-balance-sheet derivatives ÷ assets — by group")}</span><span className="mt-1 block">{tx("off-balance-sheet derivatives ÷ total assets, %, monthly · by group")}</span></>}
              source={
                <ChartFoot
                  data={offBsDeriv}
                  labels={BANK_TYPE_LABELS}
                  decimals={1}
                  deltaPeriods={12}
                />
              }
              yFormat="pct"
              decimals={1}
              height={320}
               />
</SectorSection>

<SectorDirectory sector="capital" />
<SectorFooter />
    </SectorReport>
  );
}
