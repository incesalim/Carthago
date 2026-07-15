/**
 * Capital tab — "The Desk" two-layer page.
 *
 * Layer 1 (the brief): the vitals band — CAR + buffer over the 12% regulatory
 * minimum, audited Tier-1 / CET1, equity growth vs asset growth (the capital
 * generation gap), RWA density and leverage — every note computed from the
 * same series the charts read.
 *
 * Layer 2 ("In depth"): the pre-Desk evidence — CAR by group, the headroom
 * sizing device, audited capital composition, the per-bank capital-adequacy
 * ranking, equity & leverage and risk density — carried over, restyled, not
 * removed.
 */
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
import { BANK_NAMES } from "@/app/lib/bank_names";
import BarByBank from "@/app/components/BarByBank";
import CapitalByBank from "./CapitalByBank";
import StepWaterfall from "./StepWaterfall";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { capitalInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  Ahead,
  ChartFoot,
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  Flags,
  Levels,
  Movers,
  SecHead,
  Standings,
  Transmission,
  Vital,
  Vitals,
  type Flag,
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
import { aheadSlots } from "@/app/lib/ahead-data";
import { GlobalRangeSelector } from "@/app/components/range-context";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Capital Adequacy (CAR)",
  description: "Capital adequacy of Türkiye's banking sector: CAR/SYR, Tier 1 and leverage by bank and ownership group, from BRSA data.",
  alternates: { canonical: "/capital" },
};

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
  // What lands next — derived from the record periods + TCMB's published calendar.
  const ahead = await aheadSlots();
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
  const CAR_MIN = 12;
  const carSector = carAll.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR);
  const carNow = carSector.at(-1)?.value ?? null;
  const buffer = carNow != null ? carNow - CAR_MIN : null;

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
  const qtrsToFloor = quartersToFloor(carNow, drift, CAR_MIN);
  const driftBasis = breakPeriod
    ? `post-step · ${post?.months ?? 0}m since ${monthLabel(breakPeriod, false)}`
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
  });

  // ---- what the buffer is made of -----------------------------------------
  // All three components are positive and sum to total capital by construction,
  // so this one legitimately draws as a stack (unlike /liquidity's reserves).
  const stack = capitalStack(capRatios);
  const stackNow = stack.at(-1) ?? null;
  const hybrids = stackNow ? stackNow.at1 + stackNow.t2 : null;
  const cet1Share = stackNow && stackNow.car > 0 ? (stackNow.cet1 / stackNow.car) * 100 : null;
  const thinCet1 = byBankCap.rows.filter((b) => b.cet1 != null && b.cet1 < CAR_MIN).length;
  // Compare like with like: the hybrid stack is AUDITED (Σ/Σ over the filings),
  // so it must be set against the AUDITED buffer — not the monthly bulletin's
  // CAR, which is a different basis (16.02% vs 16.34%) and would flatter it.
  const auditBuffer = stackNow ? stackNow.car - CAR_MIN : null;

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
      label: "RWA density", note: "rwa net ÷ gross",
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
        <>
          Capital adequacy moved <b>{step.delta.toFixed(2)}pp in a single month</b> — against a
          typical monthly move of {step.typical.toFixed(2)}pp
          {together ? (
            <>
              , and <b>every ownership group {sw.verb} together</b>
            </>
          ) : (
            <>
              , though <b>the groups did not all move with it</b>
            </>
          )}
          . This is a <b>step</b>, not a trend.
        </>
      ),
    });
    transmission.push({
      k: "Ex-step",
      v: signedPp(split.rest, 2).replace("pp", ""),
      unit: "pp",
      effect: (
        <>
          The 12-month change is {signedPp(split.total, 2)} = the step ({signedPp(split.step, 2)})
          plus everything else (<b>{signedPp(split.rest, 2)}</b>). Strip the step and the sector{" "}
          <b>{split.rest >= 0 ? "added" : "lost"} capital</b> over the rest of the year.
        </>
      ),
    });
  }
  if (auditBuffer != null && hybrids != null) {
    transmission.push({
      k: "The buffer",
      v: auditBuffer.toFixed(2),
      unit: `pp · audited ${auditQ}`,
      effect: (
        <>
          Over the 12% minimum. The AT1 + Tier-2 stack is <b>{hybrids.toFixed(2)}pp</b> —{" "}
          {hybrids > auditBuffer ? (
            <>
              <b>larger than the buffer itself</b>. Strip the instruments and the ratio is{" "}
              {fmtPct(stackNow?.cet1, 2)}, below the minimum it must meet.
            </>
          ) : (
            <>the cushion is more common equity than instruments.</>
          )}{" "}
          Both figures are audited — the monthly bulletin&rsquo;s CAR ({fmtPct(carNow, 2)}) is a
          different basis.
        </>
      ),
    });
  }
  if (drift != null && qtrsToFloor != null) {
    transmission.push({
      k: "Drift, sized",
      v: `${drift >= 0 ? "+" : "−"}${Math.abs(drift).toFixed(2)}`,
      unit: "pp/yr",
      effect: (
        <>
          Measured <b>{driftBasis}</b>. At this pace the buffer reaches the floor in{" "}
          <b>~{Math.round(qtrsToFloor)} quarters</b> — a sizing device, <b>not a forecast</b>, and
          not the 12-month average a step would poison.
        </>
      ),
    });
  }
  if (step?.isBreak) {
    transmission.push({
      k: "Attribution",
      v: "—",
      effect: (
        <>
          <b>We cannot source the step.</b>{" "}
          {rwaHeld ? (
            <>
              RWA density barely moved ({fmtPct(rwaNow)}), so it arrived through the{" "}
              <b>capital</b> numerator rather than the risk mix
            </>
          ) : (
            <>
              RWA density {rwaStepMove} {signedPp(rwaStepDelta ?? 0, 1)} through the same month, so
              the <b>risk mix</b> moved with it
            </>
          )}{" "}
          — but no rule in our window explains it. The page says so rather than guessing.{" "}
          <Go href="/regulation">/regulation</Go>
        </>
      ),
    });
  }

  // ---- flags ---------------------------------------------------------------
  const flags: Flag[] = [
    {
      code: "structural-break",
      active: !!step?.isBreak,
      body: (
        <>
          <b className="font-semibold">Structural break</b> — CAR moved{" "}
          {step ? step.delta.toFixed(2) : "—"}pp in one month ({monthLabel(step?.period ?? null)}),
          against a typical {step ? step.typical.toFixed(2) : "—"}pp. A 12-month “drift” that spans
          it is a step in disguise.
        </>
      ),
      rule: "|Δ1m| > 3 × mean(|Δ1m|, 13m)",
      clear: <>Trend — the largest monthly move is within 3× the typical one</>,
    },
    {
      code: "hybrid-buffer",
      active: hybrids != null && auditBuffer != null && hybrids > auditBuffer,
      body: (
        <>
          <b className="font-semibold">Hybrid-funded buffer</b> — AT1 + Tier-2 ={" "}
          {hybrids?.toFixed(2)}pp of RWA against a {auditBuffer?.toFixed(2)}pp buffer over the
          minimum (both audited {auditQ}). Strip them and the ratio is{" "}
          {fmtPct(stackNow?.cet1, 2)}, below the 12% it must meet.
        </>
      ),
      rule: "at1 + tier2 > car_audited − 12",
      clear: <>Buffer — more common equity than instruments</>,
    },
    {
      code: "thin-cet1",
      active: thinCet1 > byBankCap.rows.length * 0.25,
      body: (
        <>
          <b className="font-semibold">Thin common equity</b> — {thinCet1} of{" "}
          {byBankCap.rows.length} banks hold CET1 below the 12% total-capital minimum.
        </>
      ),
      rule: "count(cet1 < 12%) > 25% of banks",
      clear: <>Common equity — {thinCet1} banks below 12% CET1</>,
    },
    {
      code: "generation-gap",
      active: genGap != null && genGap < 0,
      body: (
        <>
          <b className="font-semibold">Capital generation gap</b> — equity {fmtPct(eqG)} vs assets{" "}
          {fmtPct(asG)} y/y: the balance sheet is outgrowing the capital that carries it.
        </>
      ),
      rule: "equity_yoy − assets_yoy < 0",
      clear:
        genGap != null ? (
          <>
            Capital generation — equity {fmtPct(eqG)} y/y, {signedPp(genGap, 1)} vs assets
          </>
        ) : (
          <>Capital generation — equity or asset growth not published this month</>
        ),
    },
    {
      code: "thin-buffer",
      active: buffer != null && buffer < 2,
      body: (
        <>
          <b className="font-semibold">Thin buffer</b> — {buffer?.toFixed(2)}pp over the 12%
          minimum.
        </>
      ),
      rule: "car − 12 < 2pp",
      clear: <>Buffer — {buffer?.toFixed(2)}pp over the 12% minimum</>,
    },
  ];
  const activeFlags = flags.filter((f) => f.active).length;

  // ---- standings: the thin end of the register -----------------------------
  const withCet1 = byBankCap.rows.filter((b) => b.cet1 != null && b.car != null);
  const standings: StandingsGroup[] = [
    {
      heading: `Thinnest common equity — CET1 · ${auditQ}`,
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

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Capital"
        record={
          <>
            Record <b className="font-normal text-foreground">{recMonth}</b> · vs {vsMonth}
          </>
        }
        right="every figure computed from source series"
      />

      {/* ── The vitals ─────────────────────────────────────────────────── */}
      <SecHead
        title="The vitals"
        meta="sector aggregate · monthly + audited quarterly"
        className="mb-2.5 mt-6"
      />
      <Vitals>
        <Vital
          label="Capital adequacy"
          value={carNow != null ? carNow.toFixed(1) : "—"}
          unit="%"
          series={carSector.slice(-13)}
          decimals={1}
          note={
            <>
              buffer{" "}
              <b
                className={
                  buffer != null && buffer >= 2
                    ? "font-semibold text-positive"
                    : "font-semibold text-negative"
                }
              >
                {buffer != null ? signedPp(buffer, 1) : "—"}
              </b>{" "}
              over the 12% min
              {drift != null && <> · drifting {signedPp(drift, 1)}/yr</>}
            </>
          }
        />
        <Vital
          label="Tier-1 (audited)"
          value={t1Now != null ? t1Now.toFixed(1) : "—"}
          unit="%"
          series={t1Series.slice(-8)}
          decimals={1}
          note={
            <>
              {t1Delta4q != null ? `${signedPp(t1Delta4q, 1)} over 4 audited qtrs` : `audited ${auditQ}`}
            </>
          }
        />
        <Vital
          label="CET1 (audited)"
          value={cet1Now != null ? cet1Now.toFixed(1) : "—"}
          unit="%"
          series={cet1Series.slice(-8)}
          decimals={1}
          note={<>audited {auditQ} · Σ capital ÷ Σ RWA</>}
        />
        <Vital
          label="Equity growth, y/y"
          value={eqG != null ? eqG.toFixed(1) : "—"}
          unit="%"
          series={equityYoYSec.slice(-13)}
          decimals={1}
          note={
            <>
              vs assets{" "}
              <b
                className={
                  genGap != null && genGap >= 0
                    ? "font-semibold text-positive"
                    : "font-semibold text-negative"
                }
              >
                {genGap != null ? signedPp(genGap, 1) : "—"}
              </b>{" "}
              generation gap <Go href="/profitability">/profitability</Go>
            </>
          }
        />
        <Vital
          label="RWA density"
          value={rwaNow != null ? rwaNow.toFixed(1) : "—"}
          unit="%"
          series={rwaSector.slice(-13)}
          decimals={1}
          note={<>{rwaDrift != null ? `${signedPp(rwaDrift, 1)} over 12m` : "—"} · RWA net / gross</>}
        />
        <Vital
          label="Liabilities / equity"
          value={levNow != null ? levNow.toFixed(0) : "—"}
          unit="%"
          series={levSector.slice(-13)}
          decimals={0}
          note={<>≈ {levX != null ? `${levX.toFixed(1)}×` : "—"} assets / equity</>}
        />
      </Vitals>

      {/* ── Movers | The step → the ratio ──────────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-[5fr_7fr]">
        <div>
          <SecHead title="Movers" meta={`${vsMonth} → ${monthLabel(carSector.at(-1)?.period, false)} · monthly`} className="mb-2.5" />
          <Movers
            from={vsMonth.toUpperCase()}
            to={monthLabel(carSector.at(-1)?.period, false).toUpperCase()}
            rows={moverRows}
          />
        </div>
        <div>
          <SecHead
            title={step?.isBreak ? "The step → the ratio" : "The ratio → the balance sheet"}
            meta="what actually happened · computed"
            className="mb-2.5"
          />
          <Transmission items={transmission} />
        </div>
      </div>

      {/* ── Flags | Standings | Ahead ──────────────────────────────────── */}
      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-3">
        <div>
          <SecHead
            title="Flags"
            meta={`rule-based — ${activeFlags} of ${flags.length}`}
            className="mb-2.5"
          />
          <Flags
            flags={flags}
            showCleared
            quietNote="The break test, the hybrid stack, common equity, generation and the buffer are all below threshold."
          />
        </div>
        <div>
          <SecHead title="Standings" meta={`audited ${auditQ}`} href="/banks" hrefLabel="by bank →" className="mb-2.5" />
          <Standings groups={standings} />
        </div>
        <div>
          <SecHead title="Ahead" meta="schedule — derived from the record periods + the tcmb calendar" className="mb-2.5" />
          <Ahead
            items={[
              ahead["bddk-monthly"] && {
                when: ahead["bddk-monthly"].when,
                what: <>BDDK monthly bulletin — {ahead["bddk-monthly"].record} CAR</>,
              },
              ahead["brsa-filings"] && {
                when: ahead["brsa-filings"].when,
                what: (
                  <>
                    BRSA {ahead["brsa-filings"].record} filings — CET1, Tier-1 and RWA per bank
                  </>
                ),
                href: "/actions",
              },
              ahead.mpc && {
                when: ahead.mpc.when,
                what: <>TCMB MPC — the rate that prices the AT1 stack</>,
              },
              ahead.fsr && {
                when: ahead.fsr.when,
                what: <>TCMB Financial Stability Report — the systemic read</>,
              },
              step?.isBreak && {
                when: "OPEN",
                what: (
                  <>
                    The {monthLabel(step?.period ?? null, false)} step is{" "}
                    <b className="font-semibold">unattributed</b> — no rule in our window
                  </>
                ),
                href: "/regulation",
              },
            ].filter((i) => !!i)}
          />
        </div>
      </div>

      {/* ── In depth — the evidence, on the brief's own grid ───────────── */}
      <Depth action={<GlobalRangeSelector />}>
        <Takeaway data={await withLlmHeadline("capital", read)} variant="desk" />

        {/* The step — what the page had been calling an "easing". */}
        <div>
          <SecHead
            title={step?.isBreak ? "The step" : "Capital adequacy"}
            meta={
              step?.isBreak
                ? `${monthLabel(step.period)} · every group · BDDK monthly bulletin`
                : "by ownership group · BDDK monthly bulletin"
            }
            className="mb-2.5"
          />
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
          <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={carAll}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                firstClaim(
                  [
                    step?.isBreak && together && !!sw,
                    `Every ownership group ${sw?.verb} together in ${monthLabel(step?.period ?? null, false)}`,
                  ],
                  [
                    step?.isBreak && !!sw,
                    `Capital adequacy ${sw?.verb} ${signedPp(step?.delta ?? 0, 1)} in ${monthLabel(step?.period ?? null, false)} — but not every group moved with it`,
                  ],
                ) ??
                seriesFinding(carSector, { noun: "Capital adequacy", decimals: 1 }) ??
                "Capital adequacy — by group"
              }
              description="capital adequacy (syr), %, monthly · by group · regulatory minimum 12%"
              source={
                <ChartFoot data={carAll} labels={BANK_TYPE_LABELS} decimals={1} deltaPeriods={12} />
              }
              yFormat="pct"
              decimals={1}
              height={280}
              annotations={
                step?.isBreak
                  ? [{ period: step.period, label: `${step.delta.toFixed(2)}pp` }]
                  : undefined
              }
            />
            {split && step?.isBreak ? (
              <StepWaterfall
                fromLabel={monthLabel(carSector.at(-13)?.period ?? null)}
                toLabel={monthLabel(carSector.at(-1)?.period ?? null)}
                from={split.from}
                to={split.to}
                step={split.step}
                rest={split.rest}
                stepLabel={`The ${monthLabel(step.period, false)} step`}
                title={`The year's ${split.total < 0 ? "decline" : "gain"} is the step — the rest of the year ${
                  split.rest >= 0 ? "added" : "lost"
                } capital`}
                description="12-month change in CAR, pp · the one-off isolated from everything else"
                source={
                  <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] text-faint">
                    <span>
                      12M <b className="font-semibold text-foreground">{signedPp(split.total, 2)}</b>
                    </span>
                    <span>
                      THE STEP{" "}
                      <b className="font-semibold text-foreground">{signedPp(split.step, 2)}</b>
                    </span>
                    <span>
                      EX-STEP{" "}
                      <b className="font-semibold text-foreground">{signedPp(split.rest, 2)}</b>
                    </span>
                    <span>
                      SIZED ON{" "}
                      <b className="font-semibold text-foreground">
                        {drift != null ? `${drift.toFixed(2)}pp/yr · ${driftBasis}` : "—"}
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
                title={`CAR by group · ${carByBank[0]?.period ?? ""}`}
                format="pct"
                decimals={1}
              />
            )}
          </div>
          {step?.isBreak && (
            <p className="mt-4 max-w-[96ch] text-[12px] leading-relaxed text-muted-foreground">
              <b className="font-semibold text-foreground">Not attributed.</b> The step is in the
              data, not in the explanation: no rule in our regulation window covers it, and RWA
              density{" "}
              {rwaHeld ? (
                <>
                  barely moved ({fmtPct(rwaNow)}), so it arrived through the capital numerator
                  rather than the risk mix
                </>
              ) : (
                <>
                  {rwaStepMove} {signedPp(rwaStepDelta ?? 0, 1)} in the same month, so the risk mix
                  moved with it
                </>
              )}
              . The buffer is therefore sized against the{" "}
              <b className="font-semibold text-foreground">{driftBasis}</b> slope — extrapolating a
              step would be arithmetic dressed as a forecast.
            </p>
          )}
        </div>

        {/* What the buffer is made of — a stack IS the right mark here. */}
        <div>
          <SecHead
            title="What the buffer is made of"
            meta={`audited §4 · Σ component ÷ Σ RWA · ${auditQ}`}
            className="mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <StackedArea
              plain
              data={stack as unknown as Record<string, string | number | null>[]}
              series={[
                { key: "cet1", label: "CET1" },
                { key: "at1", label: "AT1" },
                { key: "t2", label: "Tier-2" },
              ]}
              title={
                hybrids != null && buffer != null && hybrids > buffer
                  ? "The cushion over the minimum is instruments, not common equity"
                  : "Capital composition — CET1, AT1 and Tier-2"
              }
              description="capital stack, % of RWA, audited quarterly · sums to total capital"
              source={
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    CET1 <b className="font-semibold text-foreground">{fmtPct(stackNow?.cet1, 2)}</b>
                  </span>
                  <span>
                    AT1 <b className="font-semibold text-foreground">{fmtPct(stackNow?.at1, 2)}</b>
                  </span>
                  <span>
                    TIER-2 <b className="font-semibold text-foreground">{fmtPct(stackNow?.t2, 2)}</b>
                  </span>
                  <span>
                    CET1 SHARE{" "}
                    <b className="font-semibold text-foreground">
                      {fmtPct(cet1Share, 0)} of capital
                    </b>
                  </span>
                </div>
              }
              yFormat="pct"
              decimals={2}
              height={280}
            />
            <ChartRow data={capRatios} labels={AUDIT_CAPITAL_LABELS} deltaPeriods={4} deltaLabel="4q" fmt={(v) => `${v.toFixed(1)}%`}>
              <TrendChart
                plain
                data={capRatios}
                seriesLabels={AUDIT_CAPITAL_LABELS}
                title="CET1 / Tier-1 / total capital — the three ratios the filings print"
                description="audited quarterly, % of RWA · sector · Σ component ÷ Σ RWA"
                yFormat="pct"
                decimals={1}
                height={280}
                hero="CET1"
              />
            </ChartRow>
          </div>
        </div>

        <CapitalByBank period={byBankCap.period} rows={byBankCap.rows} />

        {/* Equity & leverage — the generation side. */}
        <div>
          <SecHead
            title="Equity &amp; leverage"
            meta="the generation side · level, growth, gearing"
            className="mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={equityYoYSec}
              seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity y/y" }}
              title={
                genGap == null
                  ? "Equity growth — sector"
                  : genGap >= 0
                    ? "Equity compounds faster than the balance sheet — generation is not the constraint"
                    : "The balance sheet is outgrowing its equity"
              }
              description="equity growth y/y, %, monthly · sector"
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
              height={280}
              zeroLine
            />
            <TrendChart
              plain
              data={lev}
              seriesLabels={BANK_TYPE_LABELS}
              // Both halves were typed: a direction AND a ranking, next to the very
              // series that decides them. `lev` is this chart's own data prop.
              title={
                firstClaim(
                  [
                    levTrend != null && levTrend !== VERBS.trend.flat && levTopLabel != null,
                    `Gearing keeps ${levTrend} — the ${levTopLabel} banks lean hardest`,
                  ],
                  [
                    levTopLabel != null,
                    `Gearing is flat — the ${levTopLabel} banks lean hardest`,
                  ],
                ) ?? "Liabilities ÷ equity — by group"
              }
              description="liabilities ÷ equity, %, monthly · by ownership group"
              source={
                <ChartFoot data={lev} labels={BANK_TYPE_LABELS} decimals={0} deltaPeriods={12} />
              }
              yFormat="pct"
              decimals={0}
              height={280}
            />
          </div>
          <div className="mt-6">
            <TrendChart
              plain
              data={equity}
              seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity" }}
              title="Total equity — the level the ratios are struck on"
              description="sector equity, ₺ trn, monthly"
              source="Source: BDDK monthly bulletin"
              yFormat="trn"
              decimals={2}
              height={260}
            />
          </div>
        </div>

        {/* Risk density — the denominator. */}
        <div>
          <SecHead
            title="Risk density"
            meta="what the RWA denominator is made of"
            className="mb-2.5"
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-9 lg:grid-cols-2">
            <TrendChart
              plain
              data={rwa}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                firstClaim(
                  [
                    step?.isBreak && rwaHeld && !!sw,
                    `Risk density barely moved through the step — the ${sw?.noun} came from capital, not the risk mix`,
                  ],
                  [
                    step?.isBreak && !rwaHeld && rwaStepDelta != null,
                    `Risk density ${rwaStepMove} ${signedPp(rwaStepDelta ?? 0, 1)} through the step — the risk mix moved with it`,
                  ],
                ) ?? "RWA net / gross — by group"
              }
              description="rwa net ÷ gross, %, monthly · lower = more low-weight exposure"
              source={
                <ChartFoot data={rwa} labels={BANK_TYPE_LABELS} decimals={1} deltaPeriods={12} />
              }
              yFormat="pct"
              decimals={1}
              height={280}
            />
            <TrendChart
              plain
              data={offBsDeriv}
              seriesLabels={BANK_TYPE_LABELS}
              // "a foreign-bank story" — true when written, and never re-checked.
              // Phrased so it reads for whichever group actually leads.
              title={
                claim(
                  derivTopLabel != null,
                  `The derivative book is concentrated in the ${derivTopLabel} banks`,
                ) ?? "Off-balance-sheet derivatives ÷ assets — by group"
              }
              description="off-balance-sheet derivatives ÷ total assets, %, monthly · by group"
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
              height={280}
            />
          </div>
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
