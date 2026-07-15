"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { SecHead } from "@/app/components/desk";
import CoverageDrawer, { type OpenCell } from "./CoverageDrawer";
import { STATUS_LABEL } from "./status";

// Local copy (don't import github.ts into the client bundle). The single-cell
// re-extract workflow — forces just the clicked (bank, period, kind, statement).
const REEXTRACT_WORKFLOW = "reextract-statement.yml";
type ConcreteKind = "unconsolidated" | "consolidated";
type Mode = ConcreteKind | "both";

const KIND_TAG: Record<string, string> = {
  consolidated: "cons",
  unconsolidated: "unco",
};

// Sidebar status word → tone (green/red/amber read state; blue/grey stay quiet).
const STATUS_TONE: Record<string, string> = {
  ok: "text-positive",
  manual: "text-info",
  error: "text-negative",
  missing: "text-warning",
  not_expected: "text-faint",
};

interface TypeRow {
  key: string;
  label: string;
  statement: string | null;
  is_core: number;
  has_validator: number;
  sort_order: number;
}
interface SummaryRow {
  statement_type: string;
  kind: string;
  status: string;
  n: number;
}
interface ProblemCell {
  statement_type: string;
  bank_ticker: string;
  period: string;
  kind: string;
  status: string; // 'error' | 'missing'
  checks_failed: number;
  pdf_present: number;
  is_manual: number;
  row_count: number;
}

// Status columns shown in the summary table, in priority order.
const COLS = ["ok", "manual", "error", "missing", "not_expected"] as const;
type Col = (typeof COLS)[number];
type Counts = Partial<Record<string, number>>;

// Cap the rendered problem list so a long missing tail (profile, repricing)
// can't blow up the DOM — the count badge still reflects the true total.
const LIST_CAP = 300;

const fmtPeriod = (p: string) => p.replace("20", "’");

// Desk segmented control — mono-caps, hairline box, no pills, no blue.
const SEG = "inline-flex overflow-hidden rounded-[6px] border border-border";
const segBtn = (active: boolean) =>
  `px-2.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.05em] transition-colors ${
    active ? "bg-foreground/[0.08] text-foreground" : "text-muted-foreground hover:text-foreground"
  }`;

function HealthBar({ rec }: { rec: Counts }) {
  const total = COLS.reduce((s, c) => s + (rec[c] ?? 0), 0) || 1;
  const seg = (c: Col, cls: string) => {
    const v = rec[c] ?? 0;
    return v > 0 ? <span className={cls} style={{ width: `${(v / total) * 100}%` }} /> : null;
  };
  return (
    <span
      className="flex h-[7px] w-full overflow-hidden rounded-[3px] bg-hair"
      title={COLS.filter((c) => rec[c]).map((c) => `${STATUS_LABEL[c]} ${rec[c]}`).join(" · ")}
    >
      {seg("ok", "bg-positive")}
      {seg("manual", "bg-data")}
      {seg("error", "bg-negative")}
      {seg("missing", "bg-warning")}
      {/* not_expected stays as the muted track */}
    </span>
  );
}

export default function CoverageMatrix() {
  const [types, setTypes] = useState<TypeRow[]>([]);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [problems, setProblems] = useState<ProblemCell[]>([]);
  const [loading, setLoading] = useState(true);

  const [mode, setMode] = useState<Mode>("both");
  const [selected, setSelected] = useState<string | "all">("all");
  const [show, setShow] = useState<"error" | "missing" | "both">("error");
  const [bankQuery, setBankQuery] = useState("");

  const [open, setOpen] = useState<OpenCell | null>(null);
  const [busy, setBusy] = useState(false);

  // One mount-only fetch: the whole spine aggregated server-side (counts + the
  // error/missing cell list). All filtering below is client-side.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/admin/coverage?summary=1", { cache: "no-store" });
        const b = (await res.json()) as {
          types?: TypeRow[];
          summary?: SummaryRow[];
          problems?: ProblemCell[];
        };
        if (cancelled) return;
        setTypes(b.types ?? []);
        setSummary(b.summary ?? []);
        setProblems(b.problems ?? []);
      } catch {
        if (!cancelled) toast.error("Failed to load coverage summary");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const inMode = (k: string) => mode === "both" || k === mode;

  // Per-lane status counts for the current kind mode.
  const byType = useMemo(() => {
    const m = new Map<string, Counts>();
    for (const r of summary) {
      if (!inMode(r.kind)) continue;
      const rec = m.get(r.statement_type) ?? {};
      rec[r.status] = (rec[r.status] ?? 0) + r.n;
      m.set(r.statement_type, rec);
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary, mode]);

  const ordered = useMemo(
    () => [...types].sort((a, b) => b.is_core - a.is_core || a.sort_order - b.sort_order),
    [types],
  );
  const coreTypes = ordered.filter((t) => t.is_core);
  const footTypes = ordered.filter((t) => !t.is_core);
  const labelOf = (key: string) => types.find((t) => t.key === key)?.label ?? key;

  const totals = useMemo(() => {
    let error = 0;
    let missing = 0;
    for (const rec of byType.values()) {
      error += rec.error ?? 0;
      missing += rec.missing ?? 0;
    }
    return { error, missing };
  }, [byType]);

  // Sidebar list: filter by kind mode, selected lane, status toggle, bank search.
  // Errors sort first, then by lane / bank / period.
  const visibleProblems = useMemo(() => {
    const terms = bankQuery.toLowerCase().split(/[\s,]+/).filter(Boolean);
    const filtered = problems.filter((p) => {
      if (!inMode(p.kind)) return false;
      if (selected !== "all" && p.statement_type !== selected) return false;
      if (show !== "both" && p.status !== show) return false;
      if (terms.length && !terms.some((t) => p.bank_ticker.toLowerCase().includes(t))) return false;
      return true;
    });
    filtered.sort((a, b) => {
      if (a.status !== b.status) return a.status === "error" ? -1 : 1;
      if (a.statement_type !== b.statement_type)
        return a.statement_type.localeCompare(b.statement_type);
      if (a.bank_ticker !== b.bank_ticker) return a.bank_ticker.localeCompare(b.bank_ticker);
      return a.period.localeCompare(b.period);
    });
    return filtered;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [problems, mode, selected, show, bankQuery]);

  const shown = visibleProblems.slice(0, LIST_CAP);
  const overflow = visibleProblems.length - shown.length;

  function openProblem(p: ProblemCell) {
    const t = types.find((x) => x.key === p.statement_type);
    setOpen({
      bank: p.bank_ticker,
      period: p.period,
      kind: p.kind,
      type: p.statement_type,
      typeLabel: t?.label ?? p.statement_type,
      status: p.status,
      pdfPresent: !!p.pdf_present,
      hasValidator: !!t?.has_validator,
      validationStatement: t?.statement ?? p.statement_type,
    });
  }

  async function reextract(bank: string, period: string, kind: string, statement: string) {
    if (busy) return;
    if (
      !window.confirm(
        `Re-extract this one cell — ${bank} ${period} ${kind}, ${statement}? ` +
          `Re-runs the extractor on the stored PDF and overwrites just this statement's ` +
          `rows (force — even if it currently passes). Other cells are untouched.`,
      )
    )
      return;
    setBusy(true);
    try {
      const res = await fetch("/api/admin/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow: REEXTRACT_WORKFLOW, bank, period, kind, statement }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        toast.success(`Triggered re-extract for ${bank} ${period} · ${statement}`, {
          description: "Coverage refreshes after the run completes.",
        });
        setOpen(null);
      } else {
        toast.error(`Couldn't trigger`, { description: body.error ?? `HTTP ${res.status}` });
      }
    } catch {
      toast.error("Couldn't trigger re-extraction");
    } finally {
      setBusy(false);
    }
  }

  function Cnt({ rec, col }: { rec: Counts; col: Col }) {
    const v = rec[col] ?? 0;
    const tone =
      v === 0
        ? "text-faint"
        : col === "error"
          ? "text-negative font-semibold"
          : col === "missing"
            ? "text-warning"
            : col === "ok"
              ? "text-positive"
              : "text-foreground";
    return <span className={tone}>{v === 0 ? "·" : v}</span>;
  }

  function laneRow(t: TypeRow) {
    const rec = byType.get(t.key) ?? {};
    const isSel = selected === t.key;
    const problemN = (rec.error ?? 0) + (rec.missing ?? 0);
    return (
      <tr
        key={t.key}
        onClick={() => setSelected(isSel ? "all" : t.key)}
        className={`cursor-pointer border-t border-hair ${
          isSel ? "bg-foreground/[0.05]" : "hover:bg-hair/60"
        }`}
      >
        <td className="whitespace-nowrap py-1.5 pr-3 font-medium text-foreground">
          {t.label}
          {t.has_validator ? <span className="ml-1 text-positive">✓</span> : null}
        </td>
        <td className="px-2 text-right font-mono tabular-nums">
          <Cnt rec={rec} col="ok" />
        </td>
        <td className="px-2 text-right font-mono tabular-nums">
          <Cnt rec={rec} col="manual" />
        </td>
        <td className="px-2 text-right font-mono tabular-nums">
          <Cnt rec={rec} col="error" />
        </td>
        <td className="px-2 text-right font-mono tabular-nums">
          <Cnt rec={rec} col="missing" />
        </td>
        <td className="px-2 text-right font-mono tabular-nums text-faint">
          <Cnt rec={rec} col="not_expected" />
        </td>
        <td className="w-28 px-2 py-1">
          <span className="flex items-center gap-1.5">
            <HealthBar rec={rec} />
            {problemN === 0 && (rec.ok ?? 0) + (rec.manual ?? 0) > 0 ? (
              <span className="text-positive">✓</span>
            ) : null}
          </span>
        </td>
      </tr>
    );
  }

  const th = "px-2 pb-1.5 text-right font-normal font-mono text-[8.5px] uppercase tracking-[0.06em] text-faint";
  const grp = "px-0 pt-4 pb-1 font-mono text-[8.5px] uppercase tracking-[0.07em] text-muted-foreground";

  const summaryTable = (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-foreground">
            <th className={`${th} pl-0 text-left`}>Statement</th>
            <th className={th}>OK</th>
            <th className={th}>Manual</th>
            <th className={th}>Error</th>
            <th className={th}>Missing</th>
            <th className={th}>N/A</th>
            <th className={`${th} text-left`}>Coverage</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td colSpan={7} className={grp}>
              Core statements
            </td>
          </tr>
          {coreTypes.map(laneRow)}
          {footTypes.length > 0 && (
            <tr>
              <td colSpan={7} className={grp}>
                Footnotes &amp; §4
              </td>
            </tr>
          )}
          {footTypes.map(laneRow)}
        </tbody>
      </table>
    </div>
  );

  const sidebar = (
    <aside className="flex w-full flex-col border-t border-hair pt-4 lg:w-80 lg:shrink-0 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
      <div className="pb-3">
        <div className="flex items-center justify-between">
          <p className="text-[12px] font-semibold text-foreground">
            Errors &amp; missing
            {selected !== "all" && (
              <span className="font-normal text-muted-foreground"> · {labelOf(selected)}</span>
            )}
          </p>
          {selected !== "all" && (
            <button
              type="button"
              onClick={() => setSelected("all")}
              className="font-mono text-[9px] uppercase tracking-[0.05em] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              all lanes
            </button>
          )}
        </div>

        {/* status toggle */}
        <div className={`mt-2 ${SEG}`}>
          {(["error", "missing", "both"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setShow(s)}
              className={`${segBtn(show === s)} ${s !== "error" ? "border-l border-border" : ""}`}
            >
              {s}
            </button>
          ))}
        </div>

        <input
          type="text"
          value={bankQuery}
          onChange={(e) => setBankQuery(e.target.value)}
          placeholder="filter bank — e.g. GARAN, AK"
          className="mt-2 h-7 w-full border-b border-border bg-transparent px-0.5 text-[11.5px] outline-none placeholder:text-faint focus:border-foreground"
        />
        <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.04em] text-faint">
          {visibleProblems.length} cell{visibleProblems.length === 1 ? "" : "s"}
          {overflow > 0 ? ` · first ${LIST_CAP}` : ""} · click to inspect / re-extract
        </p>
      </div>

      <div className="max-h-[28rem] overflow-y-auto">
        {shown.length === 0 ? (
          <p className="py-6 text-center text-[11px] text-muted-foreground">Nothing here — clean.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {shown.map((p) => (
              <li key={`${p.statement_type}|${p.bank_ticker}|${p.period}|${p.kind}`}>
                <button
                  type="button"
                  onClick={() => openProblem(p)}
                  className={`w-full rounded border px-2 py-1.5 text-left text-[11.5px] transition-colors hover:ring-1 hover:ring-ring ${
                    p.status === "error"
                      ? "border-negative/25 bg-negative/[0.06]"
                      : "border-warning/25 bg-warning/[0.06]"
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium text-foreground">{p.bank_ticker}</span>
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                      {fmtPeriod(p.period)} · {KIND_TAG[p.kind] ?? p.kind}
                    </span>
                  </span>
                  <span className="mt-0.5 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                    <span className="truncate">
                      {selected === "all" ? labelOf(p.statement_type) + " · " : ""}
                      {p.status === "error"
                        ? `${p.checks_failed} failed`
                        : p.pdf_present
                          ? "PDF ready"
                          : "no PDF"}
                    </span>
                    <span
                      className={`shrink-0 font-mono text-[9px] uppercase tracking-[0.05em] ${
                        STATUS_TONE[p.status] ?? "text-faint"
                      }`}
                    >
                      {STATUS_LABEL[p.status] ?? p.status}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );

  return (
    <>
      <SecHead
        title="Coverage"
        meta="audited §2/§4 · OK / manual / error / missing / n·a"
        action={
          <div className={SEG}>
            {(["unconsolidated", "consolidated", "both"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`${segBtn(mode === m)} ${m !== "unconsolidated" ? "border-l border-border" : ""}`}
              >
                {m}
              </button>
            ))}
          </div>
        }
        className="mb-2"
      />

      {loading ? (
        <p className="text-[12px] text-muted-foreground">Loading…</p>
      ) : types.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">
          No coverage data yet — populated by the next <code>refresh-audit.yml</code> run after
          migration 0008 applies.
        </p>
      ) : (
        <>
          <p className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.04em]">
            <span className="text-negative">
              <span className="font-semibold">{totals.error}</span> errors
            </span>
            <span className="text-warning">
              <span className="font-semibold">{totals.missing}</span> missing
            </span>
            <span className="text-faint">
              · click a lane to filter · {KIND_TAG[mode] ?? mode} · ✓ = has validator
            </span>
          </p>

          <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
            <div className="min-w-0 flex-1">{summaryTable}</div>
            {sidebar}
          </div>
        </>
      )}

      <CoverageDrawer
        key={open ? `${open.bank}|${open.period}|${open.kind}|${open.type}` : "none"}
        open={open}
        onClose={() => setOpen(null)}
        onReextract={reextract}
        reextractBusy={busy}
      />
    </>
  );
}
