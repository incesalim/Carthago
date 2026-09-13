/** Credit-stage balances and provision coverage from one audited bank sample. */
import { useText } from "@/i18n/use-text";
import type { StageLadder } from "@/app/lib/credit-risk";

const pct = (v: number, d = 1) => `${v.toFixed(d)}%`;
const trn = (bn: number) => `₺${(bn / 1000).toFixed(2)}trn`;
const bnf = (v: number) => `₺${Math.round(v).toLocaleString("en-US")}bn`;

export default function Waterline({ ladder }: { ladder: StageLadder | null }) {
  const tx = useText();
  if (!ladder)
    return (
      <p className="py-6 text-[14px] leading-relaxed text-muted-foreground">
        {tx(
          "The staging ladder awaits an audited quarter with at least five reporting banks.",
        )}
      </p>
    );
  const l = ladder;
  const s2OfProblem = (l.stage2Bn / l.problemBn) * 100;
  const s3OfProblem = (l.stage3Bn / l.problemBn) * 100;
  const stages = [
    {
      label: "Stage 2 — the watchlist",
      amount: l.stage2Bn,
      coverage: l.cov2,
      color: "bg-warning",
    },
    {
      label: "Stage 3",
      amount: l.stage3Bn,
      coverage: l.cov3,
      color: "bg-negative",
    },
  ];

  return (
    <div className="space-y-6" data-credit-stages>
      <div>
        <div className="mb-3 text-[13px] text-muted-foreground">
          {tx("The loan book · ")}
          {tx(l.period)}
          {tx(" audited · n=")}
          {tx(l.n)}
        </div>
        <div
          className="flex h-5 overflow-hidden rounded-sm"
          aria-label={tx("TFRS-9 staging · % of gross loans")}
        >
          <div
            className="h-full border-r-2 border-card bg-context"
            style={{ width: `${l.stage1Share}%` }}
          />
          <div
            className="h-full border-r-2 border-card bg-warning"
            style={{ width: `${l.stage2Share}%` }}
          />
          <div
            className="h-full bg-negative"
            style={{ width: `${l.stage3Share}%` }}
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[13px]">
          <span>
            <i className="mr-2 inline-block size-2.5 rounded-sm bg-context" />
            {tx("Stage 1 · performing · ")}
            <b className="font-semibold tabular-nums">
              {tx(pct(l.stage1Share))}
            </b>
          </span>
          <span>
            <i className="mr-2 inline-block size-2.5 rounded-sm bg-warning" />
            {tx("Stage 2")}{" "}
            <b className="font-semibold tabular-nums">
              {tx(pct(l.stage2Share))}
            </b>
          </span>
          <span>
            <i className="mr-2 inline-block size-2.5 rounded-sm bg-negative" />
            {tx("Stage 3")}{" "}
            <b className="font-semibold tabular-nums">
              {tx(pct(l.stage3Share))}
            </b>
          </span>
        </div>
        <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">
          {tx("The published NPL ratio includes Stage 3 only.")}
        </p>
      </div>
      <div className="border-t border-hair pt-5">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-[15px] font-semibold">
            {tx("Stage 2 + Stage 3 loans")}
          </h4>
          <span className="text-[17px] font-semibold tabular-nums">
            {tx(trn(l.problemBn))}{" "}
            <span className="text-[13px] font-normal text-muted-foreground">
              · {tx(pct(l.problemShare))}
              {tx(" of loans")}
            </span>
          </span>
        </div>
        <div
          className="mb-5 flex h-7 overflow-hidden rounded-sm"
          aria-label={tx("Stage 2 + Stage 3 loans")}
        >
          <div
            className="h-full border-r-2 border-card bg-warning"
            style={{ width: `${s2OfProblem}%` }}
          />
          <div
            className="h-full bg-negative"
            style={{ width: `${s3OfProblem}%` }}
          />
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          {stages.map((stage) => (
            <div key={stage.label}>
              <div className="flex items-start justify-between gap-3 text-[13px]">
                <span className="font-medium">
                  <i
                    className={`mr-2 inline-block size-2.5 rounded-sm ${stage.color}`}
                  />
                  {tx(stage.label)}
                </span>
                <b className="whitespace-nowrap font-semibold tabular-nums">
                  {tx(trn(stage.amount))}
                </b>
              </div>
              <div className="mt-3 flex justify-between gap-3 text-[13px] text-muted-foreground">
                <span>{tx("Provision coverage")}</span>
                <b className="font-semibold tabular-nums text-foreground">
                  {tx(pct(stage.coverage))}
                </b>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-foreground/10">
                <div
                  className={`h-full ${stage.color}`}
                  style={{ width: `${Math.min(stage.coverage, 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        <p className="mt-5 border-t border-hair pt-4 text-[13px] leading-relaxed text-muted-foreground">
          {tx("Provisions held: {0}, covering {1} of the problem book", {
            0: bnf(l.provisionsBn),
            1: pct(l.problemCov),
          })}
        </p>
      </div>
    </div>
  );
}
