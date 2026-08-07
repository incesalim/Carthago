/**
 * Filing-season panel — per-bank publication state for the in-window quarter.
 * Answers "who has published, who hasn't, and in what form" one level above the
 * coverage matrix: a bank can have RELEASED results (KAP filing, Excel on IR)
 * while its BRSA audit PDF — the thing the pipeline ingests — is still pending.
 *
 * Desk rules: hairlines not boxes, mono microtype for states, blue = links only
 * (the KAP evidence link), status colours read as data state.
 */
import { SecHead } from "@/app/components/desk";
import type { BankFiling, FilingSeasonReport, KindState } from "@/app/lib/filing-season";

const KIND_SHORT: Record<string, string> = {
  unconsolidated: "unco",
  consolidated: "cons",
};

const KIND_STATE_STYLE: Record<KindState, string> = {
  extracted: "text-positive",
  failed: "text-negative",
  acquired: "text-warning",
  none: "text-faint",
};

const KIND_STATE_WORD: Record<KindState, string> = {
  extracted: "extracted",
  failed: "extraction failed",
  acquired: "PDF in R2, not extracted",
  none: "no PDF",
};

function KindChips({ bank }: { bank: BankFiling }) {
  return (
    <span className="inline-flex items-center gap-2">
      {bank.kinds.map(({ kind, state }) => (
        <span
          key={kind}
          title={`${kind}: ${KIND_STATE_WORD[state]}`}
          className={`font-mono text-[8.5px] uppercase tracking-[0.06em] ${KIND_STATE_STYLE[state]}`}
        >
          {KIND_SHORT[kind] ?? kind}
          {state === "failed" ? " ✕" : state === "extracted" ? " ✓" : ""}
        </span>
      ))}
    </span>
  );
}

function BankRow({ bank }: { bank: BankFiling }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-hair py-1.5 last:border-b-0">
      <div className="flex items-baseline gap-2">
        <span className="text-[12.5px] text-foreground">{bank.name}</span>
        <span className="font-mono text-[9px] uppercase tracking-[0.06em] text-faint">
          {bank.ticker}
        </span>
      </div>
      <div className="flex items-baseline gap-4">
        {bank.resultsAt && (
          <span className="text-[10.5px] text-muted-foreground">
            results on{" "}
            {bank.resultsUrl ? (
              <a
                href={bank.resultsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                KAP · {bank.resultsAt.slice(0, 10)}
              </a>
            ) : (
              <>KAP · {bank.resultsAt.slice(0, 10)}</>
            )}
          </span>
        )}
        <KindChips bank={bank} />
      </div>
    </div>
  );
}

function Group({
  title,
  hint,
  banks,
  compact = false,
}: {
  title: string;
  hint?: string;
  banks: BankFiling[];
  compact?: boolean;
}) {
  if (banks.length === 0) return null;
  return (
    <div className="mt-4 first:mt-0">
      <div className="flex items-baseline gap-2">
        <h3 className="font-mono text-[9px] uppercase tracking-[0.07em] text-muted-foreground">
          {title}
        </h3>
        <span className="font-mono text-[9px] tabular-nums text-faint">{banks.length}</span>
      </div>
      {hint && <p className="mt-0.5 text-[9.5px] leading-snug text-faint">{hint}</p>}
      {compact ? (
        <p className="mt-1.5 font-mono text-[9.5px] uppercase leading-relaxed tracking-[0.05em] text-muted-foreground">
          {banks.map((b) => b.ticker).join(" · ")}
        </p>
      ) : (
        <div className="mt-1">
          {banks.map((b) => (
            <BankRow key={b.ticker} bank={b} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FilingSeason({ report }: { report: FilingSeasonReport }) {
  const { window: w, banks, counts } = report;
  if (banks.length === 0) return null;

  const group = (s: BankFiling["status"]) => banks.filter((b) => b.status === s);
  const meta = `${w.period} · window ${w.opensISO} → ${w.closesISO}${
    w.open ? ` · day ${w.dayOfWindow}` : " · closed — off-window filings arrive via manual dispatch"
  }`;
  const summary = [
    `${counts.extracted} extracted`,
    counts.partial > 0 ? `${counts.partial} partial` : null,
    counts.acquired > 0 ? `${counts.acquired} acquired` : null,
    counts.results_only > 0 ? `${counts.results_only} results-only` : null,
    `${counts.none} no signal`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      <SecHead title="Filing season" meta={meta} className="mb-1.5" />
      <p className="mb-2 font-mono text-[9.5px] uppercase tracking-[0.06em] tabular-nums text-muted-foreground">
        {summary}
      </p>

      <Group
        title="Results out · audit report pending"
        hint="An independent KAP results filing exists for the period, but no BRSA PDF has been acquired — usually the report is not on the bank's IR site yet, or its URL is missing from data/banks/audit_report_urls.json."
        banks={group("results_only")}
      />
      <Group
        title="Report acquired · extraction pending or failed"
        banks={[...group("acquired"), ...group("partial")]}
      />
      <Group
        title="No signal yet"
        hint="No KAP results filing seen and no PDF acquired. Absence of evidence, not proof the bank has not published — unlisted banks may never emit a KAP signal."
        banks={group("none")}
        compact
      />
      <Group title="Extracted" banks={group("extracted")} compact />
    </div>
  );
}
