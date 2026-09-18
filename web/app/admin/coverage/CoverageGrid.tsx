"use client";

/**
 * Dense bank × period grid for ONE lane — the spatial view the lane-summary
 * counts can't give: which quarter broke, which bank is a stripe of red, where
 * a validator change moved a whole column. Backed by the long-existing
 * ?type=&kind= endpoint (coverageGrid) and the STATUS_CELL glyphs that were
 * written for exactly this and never wired up.
 *
 * Grid mode forces a concrete kind (consolidated / unconsolidated): the "both"
 * mode has no honest single-cell rendering. GridTable is the pure table; the
 * default export is the fetching wrapper.
 */
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { STATUS_CELL } from "./status";
import type { CoverageCell } from "@/app/lib/coverage";

interface Props {
  type: string;
  typeLabel: string;
  kind: "consolidated" | "unconsolidated";
  onOpen: (cell: CoverageCell) => void;
}

const KIND_TAG: Record<string, string> = { consolidated: "cons", unconsolidated: "unco" };
const fmtPeriod = (p: string) => p.replace("20", "’");

/** The grid itself, pure — fixture-testable without the fetch. */
export function GridTable({
  banks,
  periods,
  cells,
  onOpen,
}: {
  banks: string[];
  periods: string[];
  cells: CoverageCell[];
  onOpen: (cell: CoverageCell) => void;
}) {
  const byKey = new Map(cells.map((c) => [`${c.bank_ticker}|${c.period}`, c]));
  const th = "px-1.5 pb-1 text-right font-normal font-mono text-[8.5px] uppercase tracking-[0.06em] text-faint";

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-foreground">
            <th className={`${th} pl-0 text-left`}>Bank</th>
            {periods.map((p) => (
              <th key={p} className={th}>
                {fmtPeriod(p)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {banks.map((bank) => (
            <tr key={bank} className="border-t border-hair">
              <td className="whitespace-nowrap py-1 pr-3 font-mono tabular-nums text-foreground">{bank}</td>
              {periods.map((p) => {
                const cell = byKey.get(`${bank}|${p}`);
                if (!cell) {
                  return (
                    <td key={p} className="px-1.5 text-center text-faint">
                      <span aria-hidden>·</span>
                    </td>
                  );
                }
                const sc = STATUS_CELL[cell.status] ?? STATUS_CELL.not_expected;
                return (
                  <td key={p} className="px-0.5 py-0.5 text-center">
                    <button
                      type="button"
                      onClick={() => onOpen(cell)}
                      title={`${bank} ${p} · ${KIND_TAG[cell.kind] ?? cell.kind} — ${cell.status}${cell.checks_failed ? ` (${cell.checks_failed} failed)` : ""}${cell.row_count ? ` · ${cell.row_count} rows` : ""}`}
                      className={`inline-flex h-5 w-7 items-center justify-center rounded-[3px] font-mono text-[10px] font-semibold ${sc.cls}`}
                    >
                      <span aria-hidden>{sc.glyph || "·"}</span>
                      <span className="sr-only">{cell.status}</span>
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.04em] text-faint">
        ✓ ok · ✎ manual · ! error · · missing · blank n/a · click a cell to inspect
      </p>
    </div>
  );
}

export default function CoverageGrid({ type, typeLabel, kind, onOpen }: Props) {  const [data, setData] = useState<{ banks: string[]; periods: string[]; cells: CoverageCell[] } | null>(null);
  const [loading, setLoading] = useState(true);
  // Key-guarded fetch (DocumentCorpusPanel pattern): a slow response for an
  // older (type, kind) must never overwrite the current one.
  const key = `${type}|${kind}`;
  const held = useRef(key);

  useEffect(() => {
    held.current = key;
    const controller = new AbortController();
    // setLoading flips synchronously at fetch-on-mount start — the intended
    // pattern; the result setters all sit behind `await` and the key guard.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    void (async () => {
      try {
        const res = await fetch(
          `/api/admin/coverage?type=${encodeURIComponent(type)}&kind=${kind}`,
          { cache: "no-store", signal: controller.signal },
        );
        const b = (await res.json()) as { grid?: typeof data };
        if (held.current === key) setData(b.grid ?? { banks: [], periods: [], cells: [] });
      } catch (err) {
        if ((err as Error).name !== "AbortError" && held.current === key) {
          toast.error("Failed to load lane grid");
          setData({ banks: [], periods: [], cells: [] });
        }
      } finally {
        if (held.current === key) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [type, kind, key]);

  if (loading && !data) return <p className="text-[12px] text-muted-foreground">Loading grid…</p>;

  const banks = data?.banks ?? [];
  const periods = data?.periods ?? [];

  if (banks.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground">
        No cells for {typeLabel} · {KIND_TAG[kind]} — the lane has no stored coverage yet.
      </p>
    );
  }

  return <GridTable banks={banks} periods={periods} cells={data?.cells ?? []} onOpen={onOpen} />;
}
