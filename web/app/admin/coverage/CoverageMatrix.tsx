"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge, Section } from "@/app/components/ui";
import CoverageDrawer, { type OpenCell } from "./CoverageDrawer";
import { STATUS_CELL, STATUS_LABEL, STATUS_VARIANT, STATUSES } from "./status";

const AUDIT_WORKFLOW = "refresh-audit.yml";
type Kind = "unconsolidated" | "consolidated";

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

export default function CoverageMatrix() {
  const [types, setTypes] = useState<TypeRow[]>([]);
  const [type, setType] = useState<string>("");
  const [kind, setKind] = useState<Kind>("unconsolidated");
  // Keyed by type|kind so a fetched grid only shows for its selection — avoids a
  // synchronous loading reset in the effect (a lint error in this repo).
  const [loaded, setLoaded] = useState<{ key: string; grid: Grid } | null>(null);
  const [open, setOpen] = useState<OpenCell | null>(null);
  const [busy, setBusy] = useState(false);

  // Grid fetch is event-driven (selection handlers + a mount-only initial load),
  // not a reactive effect — fetching in response to state changes from an effect
  // trips react-hooks/set-state-in-effect. fetchGrid is stable ([] deps).
  const fetchGrid = useCallback(async (t: string, k: Kind) => {
    if (!t) return;
    const key = `${t}|${k}`;
    try {
      const res = await fetch(
        `/api/admin/coverage?type=${encodeURIComponent(t)}&kind=${k}`,
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
    void fetchGrid(t, kind);
  };
  const selectKind = (k: Kind) => {
    setKind(k);
    void fetchGrid(type, k);
  };

  const grid = loaded && loaded.key === `${type}|${kind}` ? loaded.grid : null;
  const loading = type !== "" && grid == null;

  const lookup = useMemo(() => {
    const m = new Map<string, Cell>();
    grid?.cells.forEach((c) => m.set(`${c.bank_ticker}|${c.period}`, c));
    return m;
  }, [grid]);

  const activeType = types.find((t) => t.key === type);

  // Status tally for the active grid (legend counts).
  const tally = useMemo(() => {
    const t: Record<string, number> = {};
    grid?.cells.forEach((c) => (t[c.status] = (t[c.status] ?? 0) + 1));
    return t;
  }, [grid]);

  async function reextract(bank: string, period: string) {
    if (busy) return;
    // The audit workflow currently re-runs the bank's latest period; per-period
    // targeting (for ${period}) lands in the period-targeted follow-up.
    if (!window.confirm(`Re-extract ${bank} now? (Re-runs the latest period, not ${period} specifically.)`))
      return;
    setBusy(true);
    try {
      const res = await fetch("/api/admin/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow: AUDIT_WORKFLOW, bank }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        toast.success(`Triggered re-extract for ${bank}`, {
          description: "Period-targeted re-extraction lands in a follow-up.",
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

  return (
    <Section
      title="Coverage matrix"
      description="Per statement type × bank × period: what we have, what's missing, what failed validation"
      actions={
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          {(["unconsolidated", "consolidated"] as Kind[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => selectKind(k)}
              className={`px-2.5 py-1 text-xs ${
                kind === k ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground"
              }`}
            >
              {k}
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
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="border-collapse text-[11px]">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-muted/60 px-2 py-1 text-left font-medium">
                  Bank
                </th>
                {grid.periods.map((p) => (
                  <th key={p} className="px-1 py-1 text-center font-medium text-muted-foreground">
                    {p.replace("20", "’")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.banks.map((bank) => (
                <tr key={bank} className="border-t border-border/60">
                  <td className="sticky left-0 z-10 bg-background px-2 py-0.5 font-medium">
                    {bank}
                  </td>
                  {grid.periods.map((period) => {
                    const c = lookup.get(`${bank}|${period}`);
                    const status = c?.status ?? "not_expected";
                    const sc = STATUS_CELL[status] ?? STATUS_CELL.not_expected;
                    const title = c
                      ? `${STATUS_LABEL[status]} — ${c.row_count} rows${
                          c.checks_failed ? `, ${c.checks_failed} failed` : ""
                        }${c.is_manual ? ", manual" : ""}`
                      : "no data";
                    return (
                      <td key={period} className="p-0.5 text-center">
                        <button
                          type="button"
                          title={title}
                          disabled={!c}
                          onClick={() =>
                            c &&
                            setOpen({
                              bank,
                              period,
                              kind,
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
                      </td>
                    );
                  })}
                </tr>
              ))}
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
