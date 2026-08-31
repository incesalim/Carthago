/**
 * MarketShareSection — competitive dynamics on /cross-bank.
 *
 * The scorecard ranks banks by RATIO; this answers "who is biggest, and who is
 * moving" — an asset-size league with quarter-over-quarter rank moves and each
 * bank's share of assets / loans / deposits, plus the sector HHI. Shares are of
 * the banks reporting that quarter (~98% of sector); see market-share.ts.
 *
 * Server component — pure presentation off leagueTable()/hhiSeries(). Boxes out,
 * hairlines in (DESIGN.md rule 1): the three HHI figures read as a vitals strip
 * and the league as a plain ruled table.
 */
import { useText } from "@/i18n/use-text";
import { bankDisplayName } from "@/app/lib/bank_names";
import { nf } from "@/app/lib/chart-format";
import { SecHead } from "@/app/components/desk";
import type { LeagueEntry, HhiPoint } from "@/app/lib/market-share";
import { ScrollX } from "@/app/components/ui/scroll-x";

const pct = (v: number | null, d = 2): string => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);

/** Signed pp share shift, tone-coloured (who is TAKING share). */
function ShareShift({ pp }: { pp: number | null }) {
  const tx = useText();
  if (pp == null) return <span className="text-faint">—</span>;
  if (Math.abs(pp) < 0.005) return <span className="text-faint">{tx("0.00pp")}</span>;
  return (
    <span className={pp > 0 ? "text-positive" : "text-negative"}>
      {tx(pp > 0 ? "+" : "−")}
      {tx(Math.abs(pp).toFixed(2))}{tx("pp")}</span>
  );
}

/** US-DOJ concentration bands on the 0–10 000 HHI scale. */
function hhiBand(h: number | null): string {
  if (h == null) return "—";
  if (h < 1500) return "unconcentrated";
  if (h <= 2500) return "moderately concentrated";
  return "concentrated";
}

/** Quarter-over-quarter rank move: ▲ climbed, ▼ fell, — flat/new. */
function RankMove({ change }: { change: number | null }) {
  const tx = useText();
  if (change == null || change === 0) return <span className="text-faint">—</span>;
  const up = change > 0;
  return (
    <span className={up ? "text-positive" : "text-negative"}>
      {tx(up ? "▲" : "▼")}
      {tx(Math.abs(change))}
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
  const tx = useText();
  if (league.length === 0) return null;
  const q = /Q([1-4])$/.exec(period)?.[1];
  const year = period.slice(0, 4);

  const head =
    "border-b border-foreground pb-1.5 font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] text-faint";
  const cell = "border-b border-hair py-1.5 font-mono text-[11.5px] tabular-nums";

  return (
    <section>
      <SecHead
        title={tx("Market share & concentration")}
        meta={tx("asset league · Q{0} {1} · share of the {2} banks reporting", {0: q, 1: year, 2: league.length})}
        className="border-b border-hair pb-1.5"
      />

      {hhi && (
        <div className="mt-3 grid grid-cols-1 border-y border-hair sm:grid-cols-3">
          {(
            [
              ["Assets HHI", hhi.assets_hhi],
              ["Loans HHI", hhi.loans_hhi],
              ["Deposits HHI", hhi.deposits_hhi],
            ] as const
          ).map(([label, v]) => (
            <div key={label} className="border-r border-hair px-4 py-2.5 last:border-r-0 sm:first:pl-0">
              <div className="text-[10.5px] text-muted-foreground">{tx(label)}</div>
              <div className="mt-0.5 font-mono text-[18px] font-semibold tabular-nums text-foreground">
                {tx(v != null ? nf(v, 0) : "—")}
              </div>
              <div className="mt-0.5 text-[9.5px] text-faint">{tx(hhiBand(v))}</div>
            </div>
          ))}
        </div>
      )}

      <ScrollX className="mt-3" label={tx("Market share league table — scrolls horizontally")}>
        <table className="w-full min-w-[720px] border-collapse text-foreground">
          <thead>
            <tr>
              <th className={`${head} w-8 text-left`}>#</th>
              <th className={`${head} text-left`}>{tx("Bank")}</th>
              <th className={`${head} text-right`}>{tx("Assets share")}</th>
              <th className={`${head} text-right`}>{tx("Loans share")}</th>
              <th className={`${head} text-right`}>{tx("Δ loans y/y")}</th>
              <th className={`${head} text-right`}>{tx("Deposits share")}</th>
              <th className={`${head} text-right`}>{tx("Δ deposits y/y")}</th>
              <th className={`${head} text-right`}>{tx("Δ rank q/q")}</th>
            </tr>
          </thead>
          <tbody>
            {league.map((e) => (
              <tr key={e.bank_ticker}>
                <td className={`${cell} text-left text-faint`}>{tx(e.rank)}</td>
                <td className="border-b border-hair py-1.5 text-[12.5px] font-medium text-foreground">
                  {tx(bankDisplayName(e.bank_ticker))}
                </td>
                <td className={`${cell} text-right`}>{tx(pct(e.assets_share))}</td>
                <td className={`${cell} text-right`}>{tx(pct(e.loans_share))}</td>
                <td className={`${cell} text-right`}>
                  <ShareShift pp={e.loans_share_yoy_pp} />
                </td>
                <td className={`${cell} text-right`}>{tx(pct(e.deposits_share))}</td>
                <td className={`${cell} text-right`}>
                  <ShareShift pp={e.deposits_share_yoy_pp} />
                </td>
                <td className={`${cell} text-right`}>
                  <RankMove change={e.rank_change} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollX>

      <p className="mt-2.5 font-mono text-[8.5px] leading-relaxed tracking-[0.04em] text-faint">{tx("Δ y/y columns show who is TAKING share (pp vs four quarters ago). HHI = Σ share² × 10,000, banded on the US-DOJ scale. Shares are of the reporting banks, not the whole sector.")}</p>
    </section>
  );
}
