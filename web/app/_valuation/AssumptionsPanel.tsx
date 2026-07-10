"use client";

/**
 * The editable scenario controls. All sliders work in display units (percent,
 * years, ×) and convert to the fraction-based Assumptions on change. Two derived
 * read-outs — the CAPM cost of equity and the sustainable growth rate — update
 * live so the user can see the warranted-P/B inputs as they move the levers.
 */
import { RangeInput } from "./RangeInput";
import { costOfEquity, sustainableGrowth, type Assumptions, type CoeInputs } from "@/app/lib/valuation";

export interface AssumptionsPanelProps {
  a: Assumptions;
  update: (patch: Partial<Assumptions>) => void;
  updateCoe: (patch: Partial<CoeInputs>) => void;
  betaNote?: string | null;
  betaEstimated?: boolean;
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="space-y-3">
      <legend className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

function Derived({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-md bg-accent/50 px-2.5 py-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

export function AssumptionsPanel({ a, update, updateCoe, betaNote, betaEstimated }: AssumptionsPanelProps) {
  const coe = costOfEquity(a.coe);
  const g = sustainableGrowth(a.roe0, a.payout);
  const pct = (v: number, d = 1) => `${v.toFixed(d)}%`;

  return (
    <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
      <Group title="Cost of equity (nominal TRY)">
        <RangeInput
          label="Risk-free rate (rf)"
          value={a.coe.rf * 100}
          min={0}
          max={80}
          step={0.5}
          suffix="%"
          onChange={(v) => updateCoe({ rf: v / 100 })}
          hint="CBRT funding-rate proxy (EVDS TP.APIFON4)"
        />
        <RangeInput
          label="Equity risk premium (ERP)"
          value={a.coe.erp * 100}
          min={0}
          max={15}
          step={0.25}
          suffix="%"
          onChange={(v) => updateCoe({ erp: v / 100 })}
        />
        <RangeInput
          label="Beta (β)"
          value={a.coe.beta}
          min={0}
          max={2.5}
          step={0.05}
          decimals={2}
          onChange={(v) => updateCoe({ beta: v })}
          hint={betaEstimated === false ? (betaNote ?? undefined) : "Weekly returns vs XU100"}
        />
        <RangeInput
          label="Extra country premium (CRP)"
          value={(a.coe.crp ?? 0) * 100}
          min={0}
          max={15}
          step={0.25}
          suffix="%"
          onChange={(v) => updateCoe({ crp: v / 100 })}
        />
        <Derived label="Cost of equity = rf + β·ERP + CRP" value={pct(coe * 100)} />
      </Group>

      <Group title="Payout & growth">
        <RangeInput
          label="Starting ROE (TTM)"
          value={a.roe0 * 100}
          min={0}
          max={60}
          step={0.5}
          suffix="%"
          onChange={(v) => update({ roe0: v / 100 })}
        />
        <RangeInput
          label="Dividend payout"
          value={a.payout * 100}
          min={0}
          max={100}
          step={1}
          suffix="%"
          onChange={(v) => update({ payout: v / 100 })}
        />
        <Derived label="Sustainable growth g = ROE·(1−payout)" value={pct(g * 100)} />
      </Group>

      <Group title="Residual income (5-yr fade + terminal)">
        <RangeInput
          label="Forecast horizon"
          value={a.horizon}
          min={1}
          max={10}
          step={1}
          decimals={0}
          suffix=" yr"
          onChange={(v) => update({ horizon: Math.round(v) })}
        />
        <RangeInput
          label="Terminal ROE (fade to)"
          value={a.roeFadeTo * 100}
          min={0}
          max={50}
          step={0.5}
          suffix="%"
          onChange={(v) => update({ roeFadeTo: v / 100 })}
        />
        <RangeInput
          label="Terminal growth (g_T)"
          value={a.terminalGrowth * 100}
          min={0}
          max={40}
          step={0.5}
          suffix="%"
          onChange={(v) => update({ terminalGrowth: v / 100 })}
        />
        <RangeInput
          label="Persistence (ω)"
          value={a.persistence}
          min={0}
          max={1}
          step={0.05}
          decimals={2}
          onChange={(v) => update({ persistence: v })}
          hint="0 = Gordon terminal · >0 = abnormal earnings decay"
        />
      </Group>

      <Group title="Dividend discount model">
        <RangeInput
          label="Stage-1 length"
          value={a.ddmStage1Years}
          min={1}
          max={10}
          step={1}
          decimals={0}
          suffix=" yr"
          onChange={(v) => update({ ddmStage1Years: Math.round(v) })}
        />
        <RangeInput
          label="Stage-1 dividend growth"
          value={a.ddmStage1Growth * 100}
          min={0}
          max={50}
          step={0.5}
          suffix="%"
          onChange={(v) => update({ ddmStage1Growth: v / 100 })}
          hint="Reverts to terminal growth in stage 2"
        />
      </Group>
    </div>
  );
}
