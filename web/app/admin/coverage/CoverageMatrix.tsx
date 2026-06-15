"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge, Section } from "@/app/components/ui";
import CoverageDrawer, { type OpenCell } from "./CoverageDrawer";
import { STATUS_CELL, STATUS_LABEL, STATUS_VARIANT, STATUSES } from "./status";

const AUDIT_WORKFLOW = "refresh-audit.yml";
type ConcreteKind = "unconsolidated" | "consolidated";
type Mode = ConcreteKind | "both";

const KIND_TAG: Record<ConcreteKind, string> = {
  consolidated: "cons",
  unconsolidated: "unco",
};

interface TypeRow {
  key: string;
  label: string;
  statement: string | null;
  is_core: number;
  has_validator: number;
  sort_order: number;
}
interface Cell {
  bank_ticker: string;
  period: string;
  kind: string;
  status: string;
  row_count: number;
  checks_failed: number;
  is_manual: number;
  pdf_present: number;
}
interface Grid {
  banks: string[];
  periods: string[];
  cells: Cell[];
}

const fmtPeriod = (p: string) => p.replace("20", "’");

export default function CoverageMatrix() {
  const [types, setTypes] = useState<TypeRow[]>([]);
  const [type, setType] = useState<string>("");
  const [mode, setMode] = useState<Mode>("unconsolidated");
  // Keyed by type|mode so a fetched grid only shows for its selection — avoids a
  // synchronous loading reset in the effect (a lint error in this repo).
  const [loaded, setLoaded] = useState<{ key: string; grid: Grid } | null>(null);
  const [open, setOpen] = useState<OpenCell | null>(null);
  const [busy, setBusy] = useState(false);

  // Filters. fromP/toP are "" when unbounded (earliest / latest) so no effect is
  // needed to seed them off the loaded grid.
  const [bankQuery, setBankQuery] = useState("");
  const [fromP, setFromP] = useState("");
  const [toP, setToP] = useState("");

  // Grid fetch is event-driven (selection handlers + a mount-only initial load),
  // not a reactive effect — fetching in response to state changes from an effect
  // trips react-hooks/set-state-in-effect. fetchGrid is stable ([] deps).
  const fetchGrid = useCallback(async (t: string, m: Mode) => {
    if (!t) return;
    const key = `${t}|${m}`;
    try {
      const res = await fetch(
        `/api/admin/coverage?type=${encodeURIComponent(t)}&kind=${m}`,
        { cache: "no-store" },
      );
      const b = (await res.json()) as { grid?: Grid };
      setLoaded({ key, grid: b.grid ?? { banks: [], periods: [], cells: [] } });
    } catch {
      toast.error("Failed to load coverage grid");
    }
  }, []);

  // Initial load: the type registry + the first core type's grid (mount only).
  useEffect(() => {
    fetch("/api/admin/coverage", { cache: "no-store" })
      .then((r) => r.json())
      .then((b: { types?: TypeRow[] }) => {
        const t = b.types ?? [];
        setTypes(t);
        const first = (t.find((x) => x.is_core) ?? t[0])?.key;
        if (first) {
          setType(first);
          void fetchGrid(first, "unconsolidated");
        }
      })
      .catch(() => toast.error("Failed to load coverage types"));
  }, [fetchGrid]);

  const selectType = (t: string) => {
    setType(t);
    void fetchGrid(t, mode);
  };
  const selectMode = (m: Mode) => {
    setMode(m);
    void fetchGrid(type, m);
  };

  const grid = loaded && loaded.key === `${type}|${mode}` ? loaded.grid : null;
  const loading = type !== "" && grid == null;

  const lookup = useMemo(() => {
    const m = new Map<string, Cell>();
    grid?.cells.forEach((c) => m.set(`${c.bank_ticker}|${c.period}|${c.kind}`, c));
    return m;
  }, [grid]);

  const activeType = types.find((t) => t.key === type);
  const kindsToShow: ConcreteKind[] =
    mode === "both" ? ["consolidated", "unconsolidated"] : [mode];

  // --- Filters ---------------------------------------------------------------
  const visibleBanks = useMemo(() => {
    const terms = bankQuery
      .toLowerCase()
      .split(/[\s,]+/)
      .filter(Boolean);
    const banks = grid?.banks ?? [];
    if (terms.length === 0) return banks;
    return banks.filter((b) => terms.some((t) => b.toLowerCase().includes(t)));
  }, [grid, bankQuery]);

  const visiblePeriods = useMemo(() => {
    return (grid?.periods ?? []).filter(
      (p) => (!fromP || p >= fromP) && (!toP || p <= toP),
    );
  }, [grid, fromP, toP]);

  // Status tally over the currently-visible cells (legend counts react to filters).
  const tally = useMemo(() => {
    const t: Record<string, number> = {};
    if (!grid) return t;
    const bankSet = new Set(visibleBanks);
    const periodSet = new Set(visiblePeriods);
    grid.cells.forEach((c) => {
      if (bankSet.has(c.bank_ticker) && periodSet.has(c.period)) {
        t[c.status] = (t[c.status] ?? 0) + 1;
      }
    });
    return t;
  }, [grid, visibleBanks, visiblePeriods]);

  async function reextract(bank: string, period: string) {
    if (busy) return;
    if (
      !window.confirm(
        `Re-extract ${bank} ${period}? Re-runs the extractor on the stored PDF and replaces the rows.`,
      )
    )
      return;
    setBusy(true);
    try {
      const res = await fetch("/api/admin/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow: AUDIT_WORKFLOW, bank, period }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        toast.success(`Triggered re-extract for ${bank} ${period}`, {
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

  const core = types.filter((t) => t.is_core);
  const footnote = types.filter((t) => !t.is_core);
  const allPeriods = grid?.periods ?? [];

  function cellButton(bank: string, period: string, k: ConcreteKind) {
    const c = lookup.get(`${bank}|${period}|${k}`);
    const status = c?.status ?? "not_expected";
    const sc = STATUS_CELL[status] ?? STATUS_CELL.not_expected;
    const title = c
      ? `${STATUS_LABEL[status]} — ${c.row_count} rows${
          c.checks_failed ? `, ${c.checks_failed} failed` : ""
        }${c.is_manual ? ", manual" : ""}`
      : "no data";
    return (
      <button
        type="button"
        title={title}
        disabled={!c}
        onClick={() =>
          c &&
          setOpen({
            bank,
            period,
            kind: k,
            type,
            typeLabel: activeType?.label ?? type,
            status,
            pdfPresent: !!c.pdf_present,
            hasValidator: !!activeType?.has_validator,
            validationStatement: activeType?.statement ?? type,
          })
        }
        className={`flex h-5 w-6 items-center justify-center rounded ${sc.cls} ${
          c ? "cursor-pointer hover:ring-1 hover:ring-ring" : "opacity-40"
        }`}
      >
        {sc.glyph}
      </button>
    );
  }

  return (
    <Section
      title="Coverage matrix"
      description="Per statement type × bank × period: what we have, what's missing, what failed validation"
      contentClassName=""
      actions={
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          {(["unconsolidated", "consolidated", "both"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => selectMode(m)}
              className={`px-2.5 py-1 text-xs ${
                mode === m ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      }
    >
      {/* Type selector */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {[...core, ...footnote].map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => selectType(t.key)}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
              t.key === type
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
            title={t.is_core ? "Core (gates extraction success)" : "Footnote / §4"}
          >
            {t.label}
            {t.has_validator ? " ✓" : ""}
          </button>
        ))}
      </div>

      {/* Filters: bank search + period range */}
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-[11px]">
        <label className="inline-flex items-center gap-1.5">
          <span className="text-muted-foreground">Bank</span>
          <input
            type="text"
            value={bankQuery}
            onChange={(e) => setBankQuery(e.target.value)}
            placeholder="e.g. GARAN, AK"
            className="h-6 w-40 rounded border border-border bg-background px-2 text-[11px] outline-none focus:ring-1 focus:ring-ring"
          />
        </label>
        <label className="inline-flex items-center gap-1.5">
          <span className="text-muted-foreground">From</span>
          <select
            value={fromP}
            onChange={(e) => setFromP(e.target.value)}
            className="h-6 rounded border border-border bg-background px-1 text-[11px] outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">earliest</option>
            {allPeriods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-flex items-center gap-1.5">
          <span className="text-muted-foreground">To</span>
          <select
            value={toP}
            onChange={(e) => setToP(e.target.value)}
            className="h-6 rounded border border-border bg-background px-1 text-[11px] outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">latest</option>
            {allPeriods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        {(bankQuery || fromP || toP) && (
          <button
            type="button"
            onClick={() => {
              setBankQuery("");
              setFromP("");
              setToP("");
            }}
            className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            clear
          </button>
        )}
        {grid && (
          <span className="text-muted-foreground">
            {visibleBanks.length}/{grid.banks.length} banks · {visiblePeriods.length}/
            {allPeriods.length} periods
          </span>
        )}
      </div>

      {/* Legend */}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        {STATUSES.filter((s) => tally[s]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1">
            <Badge variant={STATUS_VARIANT[s]}>{STATUS_LABEL[s]}</Badge>
            {tally[s]}
          </span>
        ))}
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : !grid || grid.banks.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No coverage data yet — populated by the next <code>refresh-audit.yml</code> run after
          migration 0008 applies.
        </p>
      ) : visibleBanks.length === 0 || visiblePeriods.length === 0 ? (
        <p className="text-xs text-muted-foreground">No banks or periods match the current filters.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="border-collapse text-[11px]">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-muted/60 px-2 py-1 text-left font-medium">
                  Bank
                </th>
                {visiblePeriods.map((p) => (
                  <th key={p} className="px-1 py-1 text-center font-medium text-muted-foreground">
                    {fmtPeriod(p)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleBanks.map((bank) =>
                kindsToShow.map((k, i) => (
                  <tr
                    key={`${bank}|${k}`}
                    className={
                      i === 0 ? "border-t-2 border-border" : "border-t border-dashed border-border/40"
                    }
                  >
                    <td className="sticky left-0 z-10 whitespace-nowrap bg-background px-2 py-0.5 font-medium">
                      {mode === "both" ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className={i === 0 ? "" : "opacity-0"}>{bank}</span>
                          <span className="text-[10px] font-normal text-muted-foreground">
                            {KIND_TAG[k]}
                          </span>
                        </span>
                      ) : (
                        bank
                      )}
                    </td>
                    {visiblePeriods.map((period) => (
                      <td key={period} className="p-0.5 text-center">
                        {cellButton(bank, period, k)}
                      </td>
                    ))}
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}

      <CoverageDrawer
        key={open ? `${open.bank}|${open.period}|${open.kind}|${open.type}` : "none"}
        open={open}
        onClose={() => setOpen(null)}
        onReextract={reextract}
        reextractBusy={busy}
      />
    </Section>
  );
}
