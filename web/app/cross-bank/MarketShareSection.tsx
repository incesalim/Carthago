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
import { Section, Stat } from "@/app/components/ui";
import { bankDisplayName } from "@/app/lib/bank_names";
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

const hhiInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

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
          <Stat label="Assets HHI" value={hhi.assets_hhi != null ? hhiInt.format(hhi.assets_hhi) : "—"} hint={hhiBand(hhi.assets_hhi)} />
          <Stat label="Loans HHI" value={hhi.loans_hhi != null ? hhiInt.format(hhi.loans_hhi) : "—"} hint={hhiBand(hhi.loans_hhi)} />
          <Stat label="Deposits HHI" value={hhi.deposits_hhi != null ? hhiInt.format(hhi.deposits_hhi) : "—"} hint={hhiBand(hhi.deposits_hhi)} />
        </div>
      )}

      <div className="overflow-x-auto rounded-[10px] border border-border bg-card">
        <table className="w-full text-xs">
          <thead className="text-muted-foreground">
            <tr className="border-b bg-muted">
              <th className="py-2 pl-3 pr-2 text-left font-medium">#</th>
              <th className="py-2 pr-3 text-left font-medium">Bank</th>
              <th className="py-2 pr-3 text-right font-medium">Assets share</th>
              <th className="py-2 pr-3 text-right font-medium">Loans share</th>
              <th className="py-2 pr-3 text-right font-medium">Δ loans y/y</th>
              <th className="py-2 pr-3 text-right font-medium">Deposits share</th>
              <th className="py-2 pr-3 text-right font-medium">Δ deposits y/y</th>
              <th className="py-2 pr-3 text-right font-medium">Δ rank q/q</th>
            </tr>
          </thead>
          <tbody>
            {league.map((e) => (
              <tr key={e.bank_ticker} className="border-b border-border">
                <td className="py-1.5 pl-3 pr-2 tabular-nums text-muted-foreground">{e.rank}</td>
                <td className="py-1.5 pr-3 font-medium text-foreground">{bankDisplayName(e.bank_ticker)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{pct(e.assets_share)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{pct(e.loans_share)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  <ShareShift pp={e.loans_share_yoy_pp} />
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{pct(e.deposits_share)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  <ShareShift pp={e.deposits_share_yoy_pp} />
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  <RankMove change={e.rank_change} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
