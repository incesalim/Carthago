"use client";

/**
 * The residual-income build-up, year by year, ending in the intrinsic-value
 * reconciliation: opening book + Σ PV(explicit RI) + PV(terminal) = fair value.
 * Money columns are thousand-TL inputs shown as ₺ bn; ROE as a percent.
 */
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/app/components/ui";
import { nf } from "@/app/lib/chart-format";
import type { ValuationResult } from "@/app/lib/valuation";

const bn = (thousandTL: number) => `₺${nf(thousandTL / 1e6, 1)}`;
const pct = (frac: number) => `${nf(frac * 100, 1)}%`;

export function ResidualIncomeTable({ result, b0 }: { result: ValuationResult; b0: number }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Year</TableHead>
            <TableHead className="text-right">Begin book</TableHead>
            <TableHead className="text-right">ROE</TableHead>
            <TableHead className="text-right">Net income</TableHead>
            <TableHead className="text-right">Dividend</TableHead>
            <TableHead className="text-right">End book</TableHead>
            <TableHead className="text-right">Residual income</TableHead>
            <TableHead className="text-right">PV</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result.path.map((y) => (
            <TableRow key={y.year}>
              <TableCell className="font-medium">Y{y.year}</TableCell>
              <TableCell className="text-right tabular-nums">{bn(y.beginBook)}</TableCell>
              <TableCell className="text-right tabular-nums">{pct(y.roe)}</TableCell>
              <TableCell className="text-right tabular-nums">{bn(y.netIncome)}</TableCell>
              <TableCell className="text-right tabular-nums">{bn(y.dividend)}</TableCell>
              <TableCell className="text-right tabular-nums">{bn(y.endBook)}</TableCell>
              <TableCell className="text-right tabular-nums">{bn(y.residualIncome)}</TableCell>
              <TableCell className="text-right tabular-nums">{bn(y.pvResidualIncome)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <dl className="mt-3 space-y-1 text-sm">
        <Recon label="Opening book value (B₀)" value={bn(b0)} />
        <Recon label="+ Σ PV of explicit residual income" value={bn(result.sumPvExplicit)} />
        <Recon
          label={`+ PV of terminal value${result.terminalValueRI === 0 ? " (omitted)" : ""}`}
          value={bn(result.pvTerminalRI)}
        />
        <Recon label="= Intrinsic equity value" value={bn(result.fairValueRI)} strong />
      </dl>
      <p className="mt-1 text-xs text-muted-foreground">All amounts ₺ bn. Per-share fair value uses shares outstanding.</p>
    </div>
  );
}

function Recon({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div
      className={
        "flex items-center justify-between " +
        (strong ? "border-t border-border pt-1.5 font-semibold text-foreground" : "text-muted-foreground")
      }
    >
      <dt>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}
