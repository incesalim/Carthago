"use client";

/**
 * The /valuation client surface. Owns all interactivity: a bank selector, the
 * Base/Bull/Bear preset pills, and the editable assumptions — every change flows
 * into a single useMemo(runValuation) that recomputes the fair value live in the
 * browser with no network round-trip. Also renders the cross-bank P/B-vs-ROE
 * scatter and a justified-vs-actual ranking, recomputed client-side under a
 * scenario toggle. Seeds arrive pre-fetched from the server page.
 */
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, Button, ChartCard, Section, Stat } from "@/app/components/ui";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import { nf } from "@/app/lib/chart-format";
import {
  costOfEquity,
  justifiedPB,
  regressPbOnRoe,
  runValuation,
  sustainableGrowth,
  type Assumptions,
  type CoeInputs,
} from "@/app/lib/valuation";
import { buildPresets, SCENARIO_LABELS, type PresetSeed, type ScenarioKey } from "@/app/lib/valuation-presets";
import type { ValuationSeed } from "@/app/lib/valuation-data";
import { AssumptionsPanel } from "./AssumptionsPanel";
import { ResidualIncomeTable } from "./ResidualIncomeTable";
import { PbRoeScatter } from "./PbRoeScatter";

const isValuable = (s: ValuationSeed): boolean =>
  s.b0 != null && s.b0 > 0 && s.roe0 != null && s.shares != null && s.shares > 0;

const toPresetSeed = (s: ValuationSeed): PresetSeed => ({
  b0: s.b0!,
  roe0: s.roe0!,
  shares: s.shares!,
  beta: s.beta,
  rf: s.rf,
  payout: s.payoutTTM,
});

const tl = (v: number | null) => (v == null ? "—" : `₺${nf(v, 2)}`);
const mult = (v: number | null) => (v == null ? "n/a" : `${nf(v, 2)}×`);
const pct1 = (v: number | null) => (v == null ? "—" : `${nf(v, 1)}%`);
const upsideOf = (fair: number | null, price: number | null): number | null =>
  fair != null && price != null && price > 0 ? (fair / price - 1) * 100 : null;
const signed = (v: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${nf(v, 1)}%`);
const tone = (v: number | null): "positive" | "negative" | "neutral" =>
  v == null ? "neutral" : v >= 0 ? "positive" : "negative";

type PresetState = ScenarioKey | "custom";
type SortKey = "ticker" | "roe" | "coe" | "jpb" | "pb" | "upside";

// A valid placeholder so runValuation never sees an undefined coe before the
// empty-state guard (hooks must run unconditionally, so we can't early-return
// ahead of the useMemo). Only used when no bank is valuable; never displayed.
const FALLBACK_ASSUMPTIONS: Assumptions = {
  b0: 0,
  roe0: 0,
  shares: 0,
  coe: { rf: 0.4, erp: 0.055, beta: 1, crp: 0 },
  payout: 0.35,
  horizon: 5,
  roeFadeTo: 0.22,
  terminalGrowth: 0.2,
  persistence: 0,
  ddmStage1Years: 5,
  ddmStage1Growth: 0.24,
};

export default function ValuationView({ seeds }: { seeds: ValuationSeed[] }) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);

  const valuable = useMemo(() => seeds.filter(isValuable), [seeds]);
  const peerPoints = useMemo(
    () =>
      seeds
        .filter((s) => s.roe0 != null && s.pb != null && s.pb > 0)
        .map((s) => ({ ticker: s.ticker, roe: s.roe0!, pb: s.pb! })),
    [seeds],
  );
  const regression = useMemo(() => regressPbOnRoe(peerPoints), [peerPoints]);

  const [ticker, setTicker] = useState(valuable[0]?.ticker ?? "");
  const seed = valuable.find((s) => s.ticker === ticker) ?? valuable[0];
  const [preset, setPreset] = useState<PresetState>("base");
  const [assumptions, setAssumptions] = useState<Assumptions>(() =>
    seed ? buildPresets(toPresetSeed(seed)).base : FALLBACK_ASSUMPTIONS,
  );

  const result = useMemo(() => runValuation(assumptions), [assumptions]);

  // --- handlers (no effects: re-seed inline on selection) -------------------
  const selectTicker = (tk: string) => {
    const s = valuable.find((x) => x.ticker === tk);
    if (!s) return;
    setTicker(tk);
    setAssumptions(buildPresets(toPresetSeed(s)).base);
    setPreset("base");
  };
  const applyPreset = (key: ScenarioKey) => {
    if (!seed) return;
    setAssumptions(buildPresets(toPresetSeed(seed))[key]);
    setPreset(key);
  };
  const update = (patch: Partial<Assumptions>) => {
    setAssumptions((a) => ({ ...a, ...patch }));
    setPreset("custom");
  };
  const updateCoe = (patch: Partial<CoeInputs>) => {
    setAssumptions((a) => ({ ...a, coe: { ...a.coe, ...patch } }));
    setPreset("custom");
  };

  // --- peer ranking (client-side, under a scenario toggle) ------------------
  const [peerScenario, setPeerScenario] = useState<ScenarioKey>("base");
  const [sortKey, setSortKey] = useState<SortKey>("upside");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const ranking = useMemo(() => {
    const rows = seeds
      .filter((s) => s.roe0 != null && s.pb != null && s.pb > 0)
      .map((s) => {
        const p = buildPresets({ b0: 1, roe0: s.roe0!, shares: 1, beta: s.beta, rf: s.rf, payout: s.payoutTTM })[
          peerScenario
        ];
        const coe = costOfEquity(p.coe);
        const g = sustainableGrowth(s.roe0!, p.payout);
        const jpb = justifiedPB(s.roe0!, g, coe);
        const upside = jpb != null && s.pb! > 0 ? (jpb / s.pb! - 1) * 100 : null;
        return { ticker: s.ticker, name: s.name, roe: s.roe0!, coe, jpb, pb: s.pb!, upside };
      });
    const nv = (v: number | null) => (v == null ? Number.NEGATIVE_INFINITY : v);
    rows.sort((a, b) => {
      let cmp: number;
      if (sortKey === "ticker") cmp = a.ticker.localeCompare(b.ticker);
      else cmp = nv(a[sortKey] as number | null) - nv(b[sortKey] as number | null);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [seeds, peerScenario, sortKey, sortDir]);

  const sortBy = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "ticker" ? "asc" : "desc");
    }
  };

  // --- ROE path chart data --------------------------------------------------
  const roePath = useMemo(() => {
    const pts = [{ year: "Now", roe: assumptions.roe0 * 100 }];
    for (const y of result.path) pts.push({ year: `Y${y.year}`, roe: y.roe * 100 });
    return pts;
  }, [assumptions.roe0, result.path]);

  if (valuable.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No listed bank has both audited fundamentals and BIST market data yet, so there is nothing to value.
      </p>
    );
  }

  const perShareRI = result.perShareRI;
  const perShareDDM = result.perShareDDM;
  const price = seed?.price ?? null;
  const upsideRI = upsideOf(perShareRI, price);
  const upsideDDM = upsideOf(perShareDDM, price);

  return (
    <div className="space-y-8">
      {/* Bank selector + market snapshot */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Bank</span>
          <select
            value={seed?.ticker ?? ""}
            onChange={(e) => selectTicker(e.target.value)}
            className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {valuable.map((s) => (
              <option key={s.ticker} value={s.ticker}>
                {s.name} ({s.ticker})
              </option>
            ))}
          </select>
        </label>
        {seed && (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
            <span className="text-muted-foreground">
              Price <span className="font-semibold text-foreground tabular-nums">{tl(price)}</span>
            </span>
            <span className="text-muted-foreground">
              P/B <span className="font-semibold text-foreground tabular-nums">{mult(seed.pb)}</span>
            </span>
            <span className="text-muted-foreground">
              P/E <span className="font-semibold text-foreground tabular-nums">{mult(seed.pe)}</span>
            </span>
            {seed.isLive ? (
              <Badge variant="info">Live price</Badge>
            ) : (
              <Badge variant="secondary">Last close</Badge>
            )}
            {seed.period && <span className="text-xs text-muted-foreground">Fundamentals {seed.period}</span>}
          </div>
        )}
      </div>

      {/* Assumptions */}
      <Section
        title="Scenario assumptions"
        description="Pick a preset, then edit any lever — the valuation recomputes instantly."
        actions={
          <Pills
            options={(["base", "bull", "bear"] as ScenarioKey[]).map((k) => ({ key: k, label: SCENARIO_LABELS[k] }))}
            active={preset}
            onSelect={(k) => applyPreset(k as ScenarioKey)}
            extra={preset === "custom" ? "Custom" : undefined}
          />
        }
      >
        {seed && (
          <AssumptionsPanel
            a={assumptions}
            update={update}
            updateCoe={updateCoe}
            betaNote={seed.betaNote}
            betaEstimated={seed.betaEstimated}
          />
        )}
      </Section>

      {/* Outputs */}
      <Section title="Intrinsic valuation" description="Residual-income and dividend-discount fair value vs the market.">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
          <Stat label="Fair value / share (RI)" value={tl(perShareRI)} hint={`vs price ${tl(price)}`} />
          <Stat label="Upside / downside (RI)" value={signed(upsideRI)} tone={tone(upsideRI)} />
          <Stat label="DDM / share" value={tl(perShareDDM)} hint={`upside ${signed(upsideDDM)}`} />
          <Stat
            label="Justified P/B"
            value={mult(result.justifiedPB)}
            hint={`actual ${mult(seed?.pb ?? null)} · terminal ROE`}
          />
          <Stat label="Implied P/B (RI)" value={mult(result.impliedPB)} hint="fair value ÷ book" />
          <Stat label="Cost of equity" value={pct1(result.coe * 100)} hint={`g = ${pct1(result.sustainableGrowth * 100)}`} />
        </div>

        {result.warnings.length > 0 && (
          <div className="mt-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            {result.warnings.map((w) => (
              <div key={w}>⚠ {w}</div>
            ))}
          </div>
        )}

        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <ChartCard title="ROE fade vs cost of equity" description="The value driver is the spread of ROE over COE.">
            <div style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={roePath} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
                  <XAxis dataKey="year" tick={{ fontSize: 11, fill: t.axis }} axisLine={{ stroke: t.grid }} tickLine={{ stroke: t.grid }} />
                  <YAxis
                    tick={{ fontSize: 11, fill: t.axis }}
                    tickFormatter={(v) => `${nf(Number(v), 0)}%`}
                    axisLine={{ stroke: t.grid }}
                    tickLine={{ stroke: t.grid }}
                  />
                  <Tooltip {...tt} formatter={(v) => [`${nf(Number(v), 1)}%`, "ROE"]} />
                  <ReferenceLine
                    y={result.coe * 100}
                    stroke={t.reference}
                    strokeDasharray="5 4"
                    label={{ value: `COE ${nf(result.coe * 100, 1)}%`, fontSize: 10, fill: t.axis, position: "insideTopRight" }}
                  />
                  <Line type="monotone" dataKey="roe" stroke={t.palette[0]} strokeWidth={2} dot isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          <ChartCard title="Residual income build-up" description="Σ PV of (ROE − COE)·book + terminal, added to book.">
            {seed && <ResidualIncomeTable result={result} b0={seed.b0!} />}
          </ChartCard>
        </div>

        <Methodology />
      </Section>

      {/* Peer comparison */}
      <Section
        title="Versus peers"
        description="Relative value across the listed banks at the latest reported quarter."
        actions={
          <Pills
            options={(["base", "bull", "bear"] as ScenarioKey[]).map((k) => ({ key: k, label: SCENARIO_LABELS[k] }))}
            active={peerScenario}
            onSelect={(k) => setPeerScenario(k as ScenarioKey)}
          />
        }
      >
        <PbRoeScatter points={peerPoints} regression={regression} selected={seed?.ticker} onSelect={selectTicker} />

        <div className="mt-5 overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-accent/40 text-left">
                <Th label="Bank" onClick={() => sortBy("ticker")} active={sortKey === "ticker"} dir={sortDir} />
                <Th label="ROE" onClick={() => sortBy("roe")} active={sortKey === "roe"} dir={sortDir} right />
                <Th label="COE" onClick={() => sortBy("coe")} active={sortKey === "coe"} dir={sortDir} right />
                <Th label="Justified P/B" onClick={() => sortBy("jpb")} active={sortKey === "jpb"} dir={sortDir} right />
                <Th label="Actual P/B" onClick={() => sortBy("pb")} active={sortKey === "pb"} dir={sortDir} right />
                <Th label="Upside" onClick={() => sortBy("upside")} active={sortKey === "upside"} dir={sortDir} right />
              </tr>
            </thead>
            <tbody>
              {ranking.map((r) => (
                <tr
                  key={r.ticker}
                  onClick={() => selectTicker(r.ticker)}
                  className={
                    "cursor-pointer border-b border-border/60 last:border-0 hover:bg-accent/40 " +
                    (r.ticker === seed?.ticker ? "bg-accent/30" : "")
                  }
                >
                  <td className="px-3 py-2">
                    <span className="font-medium text-foreground">{r.ticker}</span>{" "}
                    <span className="text-xs text-muted-foreground">{r.name}</span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct1(r.roe * 100)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct1(r.coe * 100)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{mult(r.jpb)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{mult(r.pb)}</td>
                  <td
                    className={
                      "px-3 py-2 text-right font-medium tabular-nums " +
                      (r.upside == null ? "" : r.upside >= 0 ? "text-positive" : "text-negative")
                    }
                  >
                    {signed(r.upside)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Justified P/B = (ROE − g) / (COE − g), using each bank&apos;s current ROE, the selected scenario&apos;s cost of
          equity (own β and rf), and sustainable g. Upside = justified ÷ actual P/B − 1.
        </p>
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local presentational helpers
// ---------------------------------------------------------------------------

function Pills({
  options,
  active,
  onSelect,
  extra,
}: {
  options: { key: string; label: string }[];
  active: string;
  onSelect: (key: string) => void;
  extra?: string;
}) {
  return (
    <div className="flex items-center gap-1">
      {options.map((o) => (
        <Button
          key={o.key}
          variant={active === o.key ? "default" : "outline"}
          size="sm"
          onClick={() => onSelect(o.key)}
        >
          {o.label}
        </Button>
      ))}
      {extra && (
        <Badge variant="secondary" className="ml-1">
          {extra}
        </Badge>
      )}
    </div>
  );
}

function Th({
  label,
  onClick,
  active,
  dir,
  right,
}: {
  label: string;
  onClick: () => void;
  active: boolean;
  dir: "asc" | "desc";
  right?: boolean;
}) {
  return (
    <th className={"px-3 py-2 " + (right ? "text-right" : "text-left")}>
      <button
        type="button"
        onClick={onClick}
        className={"inline-flex items-center gap-1 font-medium " + (active ? "text-foreground" : "text-muted-foreground hover:text-foreground")}
      >
        {label}
        {active && <span aria-hidden>{dir === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}

function Methodology() {
  return (
    <details className="mt-5 rounded-lg border border-border bg-accent/20 p-4 text-xs text-muted-foreground">
      <summary className="cursor-pointer font-medium text-foreground">Methodology &amp; caveats</summary>
      <div className="mt-3 space-y-2 leading-relaxed">
        <p>
          <strong className="text-foreground">Why not DCF.</strong> Bank leverage is set by capital regulation, not
          policy, so free-cash-flow/DCF is inappropriate. We use equity-side models.
        </p>
        <p>
          <strong className="text-foreground">Cost of equity (CAPM, nominal TRY):</strong> COE = rf + β·ERP + CRP, with
          β from weekly returns vs XU100 and rf a CBRT funding-rate proxy.
        </p>
        <p>
          <strong className="text-foreground">Residual income:</strong> V₀ = B₀ + Σ PV[(ROEₜ − COE)·Bₜ₋₁] + PV(terminal),
          with ROE fading linearly to the terminal level and a Gordon (ω = 0) or decaying (ω &gt; 0) terminal spread.
        </p>
        <p>
          <strong className="text-foreground">DDM:</strong> two-stage Gordon on projected dividends (payout × net income),
          stage-1 growth reverting to terminal growth. <strong className="text-foreground">Justified P/B</strong> = (ROE −
          g)/(COE − g), g = ROE·(1 − payout).
        </p>
        <p>
          <strong className="text-foreground">TAS-29 caveat.</strong> Turkish banks&apos; book equity and earnings are
          hyperinflation-restated (and the standard has been toggled across periods), which distorts reported ROE and book
          value. The model is fully nominal; the durable value driver is the real spread (ROE − COE). Treat absolute fair
          values as indicative and lean on the cross-peer comparison.
        </p>
      </div>
    </details>
  );
}
