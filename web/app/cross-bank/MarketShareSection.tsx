/**
 * MarketShareSection — competitive-dynamics block on /cross-bank.
 *
 * The heatmap ranks banks by RATIO; this answers "who's biggest and who's
 * moving" — an asset-size league table with quarter-over-quarter rank moves and
 * each bank's share of assets / loans / deposits, plus the sector HHI. Shares
 * are of the banks reporting that quarter (~98% of sector); see market-share.ts.
 *
 * Server component — pure presentation off leagueTable()/hhiSeries() output.
 */
import {
  Section,
  Stat,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCellNum,
} from "@/app/components/ui";
import { bankDisplayName } from "@/app/lib/bank_names";
import { nf } from "@/app/lib/chart-format";
import type { LeagueEntry, HhiPoint } from "@/app/lib/market-share";

const pct = (v: number | null, d = 2): string => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);

/** Signed pp share shift, tone-coloured (the strategist column: who is taking share). */
function ShareShift({ pp }: { pp: number | null }) {
  if (pp == null) return <span className="text-muted-foreground">—</span>;
  if (Math.abs(pp) < 0.005) return <span className="text-muted-foreground">0.00pp</span>;
  return (
    <span className={pp > 0 ? "text-positive" : "text-negative"}>
      {pp > 0 ? "+" : ""}
      {pp.toFixed(2)}pp
    </span>
  );
}

/** US-DOJ concentration bands on the 0–10 000 HHI scale. */
function hhiBand(h: number | null): string {
  if (h == null) return "—";
  if (h < 1500) return "Unconcentrated";
  if (h <= 2500) return "Moderately concentrated";
  return "Concentrated";
}

/** Quarter-over-quarter rank move: ▲ climbed, ▼ fell, — flat/new. */
function RankMove({ change }: { change: number | null }) {
  if (change == null || change === 0) return <span className="text-muted-foreground">—</span>;
  const up = change > 0;
  return (
    <span className={up ? "text-positive" : "text-negative"}>
      {up ? "▲" : "▼"}
      {Math.abs(change)}
    </span>
  );
}

export default function MarketShareSection({
  league,
  hhi,
  period,
}: {
  league: LeagueEntry[];
  hhi: HhiPoint | null;
  period: string;
}) {
  if (league.length === 0) return null;
  const q = /Q([1-4])$/.exec(period)?.[1];
  const year = period.slice(0, 4);

  return (
    <Section
      title="Market share & concentration"
      description={`Asset-size league table · Q${q} ${year} · share of the ${league.length} banks reporting this quarter (~98% of sector). Δ y/y columns show who is TAKING share (pp vs 4 quarters ago). HHI = Σ share² (0–10 000).`}
      contentClassName=""
    >
      {hhi && (
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Stat label="Assets HHI" value={hhi.assets_hhi != null ? nf(hhi.assets_hhi, 0) : "—"} hint={hhiBand(hhi.assets_hhi)} />
          <Stat label="Loans HHI" value={hhi.loans_hhi != null ? nf(hhi.loans_hhi, 0) : "—"} hint={hhiBand(hhi.loans_hhi)} />
          <Stat label="Deposits HHI" value={hhi.deposits_hhi != null ? nf(hhi.deposits_hhi, 0) : "—"} hint={hhiBand(hhi.deposits_hhi)} />
        </div>
      )}

      <Table className="text-xs" wrapperClassName="rounded-[10px] border border-border bg-card">
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead>#</TableHead>
            <TableHead>Bank</TableHead>
            <TableHead className="text-right">Assets share</TableHead>
            <TableHead className="text-right">Loans share</TableHead>
            <TableHead className="text-right">Δ loans y/y</TableHead>
            <TableHead className="text-right">Deposits share</TableHead>
            <TableHead className="text-right">Δ deposits y/y</TableHead>
            <TableHead className="text-right">Δ rank q/q</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {league.map((e) => (
            <TableRow key={e.bank_ticker}>
              <TableCell className="py-1.5 tabular-nums text-muted-foreground">{e.rank}</TableCell>
              <TableCell className="py-1.5 font-medium text-foreground">{bankDisplayName(e.bank_ticker)}</TableCell>
              <TableCellNum className="py-1.5">{pct(e.assets_share)}</TableCellNum>
              <TableCellNum className="py-1.5">{pct(e.loans_share)}</TableCellNum>
              <TableCellNum className="py-1.5">
                <ShareShift pp={e.loans_share_yoy_pp} />
              </TableCellNum>
              <TableCellNum className="py-1.5">{pct(e.deposits_share)}</TableCellNum>
              <TableCellNum className="py-1.5">
                <ShareShift pp={e.deposits_share_yoy_pp} />
              </TableCellNum>
              <TableCellNum className="py-1.5">
                <RankMove change={e.rank_change} />
              </TableCellNum>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Section>
  );
}
