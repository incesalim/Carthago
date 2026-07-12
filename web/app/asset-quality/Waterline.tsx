/**
 * The waterline — /asset-quality's signature.
 *
 * The NPL ratio everyone quotes is Stage 3: the tip. Loans the banks themselves
 * classify as deteriorated are ~4x that, and three-quarters of the problem book
 * is the Stage-2 watchlist the ratio never shows.
 *
 * Two bars, because one cannot carry both facts:
 *   1. the whole book TO SCALE — so the reader sees how small the printed ratio is;
 *   2. the problem book MAGNIFIED — so Stage 2 vs Stage 3, and the coverage held
 *      against each, are legible at all.
 *
 * Coverage is drawn INSIDE each stage (the provisioned share of that stage's
 * carrying amount) rather than as a separate chart, because the asymmetry —
 * ~10% on the watchlist against ~62% on the NPL — is the point.
 *
 * Deliberately NOT shown: "₺Xtrn unprovisioned". It is arithmetically true and
 * rhetorically dishonest — Stage 2 is not impaired, so lower cover is expected,
 * not a shortfall the banks owe. The migration sizing beside this does that job.
 */
import type { StageLadder } from "@/app/lib/credit-risk";

const pct = (v: number, d = 1) => `${v.toFixed(d)}%`;
const trn = (bn: number) => `₺${(bn / 1000).toFixed(2)}trn`;
const bnf = (v: number) => `₺${Math.round(v).toLocaleString("en-US")}bn`;

export default function Waterline({ ladder }: { ladder: StageLadder | null }) {
  if (!ladder) {
    return (
      <p className="py-6 text-[12px] text-faint">
        The staging ladder awaits an audited quarter with at least five reporting banks.
      </p>
    );
  }
  const l = ladder;
  const s2OfProblem = (l.stage2Bn / l.problemBn) * 100;
  const s3OfProblem = (l.stage3Bn / l.problemBn) * 100;

  return (
    <div>
      {/* ── the whole book, to scale ─────────────────────────────────── */}
      <div className="mb-1.5 font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
        The loan book · {l.period} audited · n={l.n}
      </div>
      <div className="flex h-[30px] overflow-hidden">
        <div
          className="relative h-full border-r-2 border-card bg-context"
          style={{ width: `${l.stage1Share}%` }}
        >
          <span className="absolute left-2 top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[9.5px] font-semibold text-foreground">
            Stage 1 · performing · {pct(l.stage1Share)}
          </span>
        </div>
        <div className="h-full border-r-2 border-card bg-warning" style={{ width: `${l.stage2Share}%` }} />
        <div className="h-full bg-negative" style={{ width: `${l.stage3Share}%` }} />
      </div>

      {/* the tick marks STAGE 3 ALONE — that, and only that, is what the ratio prints */}
      <div className="relative h-4">
        <div
          className="absolute top-0 h-3.5 border-l border-negative"
          style={{ left: `${l.stage1Share + l.stage2Share}%` }}
        >
          <span className="absolute right-1.5 top-0 hidden w-40 whitespace-nowrap text-right font-mono text-[8.5px] font-semibold uppercase tracking-[0.05em] text-negative sm:block">
            the ratio prints only this →
          </span>
        </div>
      </div>
      <div className="mt-1 font-mono text-[8.5px] uppercase tracking-[0.05em] text-negative sm:hidden">
        the ratio prints only the {pct(l.stage3Share)} tip
      </div>

      {/* ── the problem book, magnified ──────────────────────────────── */}
      <div className="mt-6 border-t border-hair pt-3.5">
        <div className="mb-1.5 font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
          The problem book, magnified · {trn(l.problemBn)} · {pct(l.problemShare)} of loans
        </div>
        <div className="flex h-[46px] overflow-hidden">
          <div
            className="relative h-full border-r-2 border-card bg-warning"
            style={{ width: `${s2OfProblem}%` }}
          >
            {/* provisions held against this stage */}
            <div
              className="absolute inset-y-0 left-0 bg-foreground/40"
              style={{ width: `${l.cov2}%` }}
            />
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[10px] font-semibold text-white">
              Stage 2 — the watchlist
            </span>
          </div>
          <div className="relative h-full bg-negative" style={{ width: `${s3OfProblem}%` }}>
            <div
              className="absolute inset-y-0 left-0 bg-foreground/40"
              style={{ width: `${l.cov3}%` }}
            />
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[10px] font-semibold text-white">
              Stage 3
            </span>
          </div>
        </div>

        <div className="mt-2 flex text-[10.5px] text-muted-foreground">
          <span>
            <b className="font-mono font-semibold text-foreground">{trn(l.stage2Bn)}</b> Stage 2 ·{" "}
            <b className="font-mono font-semibold text-foreground">{pct(l.cov2)}</b> covered
          </span>
          <span className="ml-auto">
            <b className="font-mono font-semibold text-foreground">{trn(l.stage3Bn)}</b> Stage 3 ·{" "}
            <b className="font-mono font-semibold text-foreground">{pct(l.cov3)}</b> covered
          </span>
        </div>

        <div className="mt-2.5 font-mono text-[9px] leading-relaxed text-faint">
          <span className="mr-1 inline-block h-2 w-2.5 align-[-1px] bg-foreground/40" /> provisions
          held ({bnf(l.provisionsBn)} · {pct(l.problemCov)} of the problem book)
          <span className="mx-1.5">·</span>
          <span className="mr-1 inline-block h-2 w-2.5 align-[-1px] bg-warning" /> carrying amount
        </div>
      </div>
    </div>
  );
}
