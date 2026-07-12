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
import { bankDisplayName } from "@/app/lib/bank_names";
import { nf } from "@/app/lib/chart-format";
import { SecHead } from "@/app/components/desk";
import type { LeagueEntry, HhiPoint } from "@/app/lib/market-share";

const pct = (v: number | null, d = 2): string => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);

/** Signed pp share shift, tone-coloured (who is TAKING share). */
function ShareShift({ pp }: { pp: number | null }) {
  if (pp == null) return <span className="text-faint">—</span>;
  if (Math.abs(pp) < 0.005) return <span className="text-faint">0.00pp</span>;
  return (
    <span className={pp > 0 ? "text-positive" : "text-negative"}>
      {pp > 0 ? "+" : "−"}
      {Math.abs(pp).toFixed(2)}pp
    </span>
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
  if (change == null || change === 0) return <span className="text-faint">—</span>;
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

  const head =
    "border-b border-foreground pb-1.5 font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] text-faint";
  const cell = "border-b border-hair py-1.5 font-mono text-[11.5px] tabular-nums";

  return (
    <section>
      <SecHead
        title="Market share &amp; concentration"
        meta={`asset league · Q${q} ${year} · share of the ${league.length} banks reporting`}
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
              <div className="text-[10.5px] text-muted-foreground">{label}</div>
              <div className="mt-0.5 font-mono text-[18px] font-semibold tabular-nums text-foreground">
                {v != null ? nf(v, 0) : "—"}
              </div>
              <div className="mt-0.5 text-[9.5px] text-faint">{hhiBand(v)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-foreground">
          <thead>
            <tr>
              <th className={`${head} w-8 text-left`}>#</th>
              <th className={`${head} text-left`}>Bank</th>
              <th className={`${head} text-right`}>Assets share</th>
              <th className={`${head} text-right`}>Loans share</th>
              <th className={`${head} text-right`}>Δ loans y/y</th>
              <th className={`${head} text-right`}>Deposits share</th>
              <th className={`${head} text-right`}>Δ deposits y/y</th>
              <th className={`${head} text-right`}>Δ rank q/q</th>
            </tr>
          </thead>
          <tbody>
            {league.map((e) => (
              <tr key={e.bank_ticker}>
                <td className={`${cell} text-left text-faint`}>{e.rank}</td>
                <td className="border-b border-hair py-1.5 text-[12.5px] font-medium text-foreground">
                  {bankDisplayName(e.bank_ticker)}
                </td>
                <td className={`${cell} text-right`}>{pct(e.assets_share)}</td>
                <td className={`${cell} text-right`}>{pct(e.loans_share)}</td>
                <td className={`${cell} text-right`}>
                  <ShareShift pp={e.loans_share_yoy_pp} />
                </td>
                <td className={`${cell} text-right`}>{pct(e.deposits_share)}</td>
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
      </div>

      <p className="mt-2.5 font-mono text-[8.5px] leading-relaxed tracking-[0.04em] text-faint">
        Δ y/y columns show who is TAKING share (pp vs four quarters ago). HHI = Σ share² × 10,000,
        banded on the US-DOJ scale. Shares are of the reporting banks, not the whole sector.
      </p>
    </section>
  );
}
