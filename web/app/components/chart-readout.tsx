"use client";

import { useText } from "@/i18n/use-text";

/** Series identity stays outside the SVG, where names and units can wrap safely. */
export function ChartReadout({ entries, active, pinned, onHover, onPin }: {
  entries: { key: string; name: string; value: string; color: string; asOf?: string; lagged?: boolean }[];
  active: string | null;
  pinned: string | null;
  onHover: (key: string | null) => void;
  onPin: (key: string) => void;
}) {
  const tx = useText();
  return <div data-chart-readout className="mb-3 flex flex-wrap gap-x-7 gap-y-3" role="group" aria-label={tx("Latest values")}>
    {entries.map(entry => <button key={entry.key} type="button" aria-pressed={pinned === entry.key}
      title={entry.asOf ? tx(entry.asOf) : undefined}
      onClick={() => onPin(entry.key)}
      onMouseEnter={() => onHover(entry.key)} onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(entry.key)} onBlur={() => onHover(null)}
      className="min-w-0 cursor-pointer text-left focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
      style={{ opacity: active && active !== entry.key ? 0.45 : 1 }}>
      <span className="flex items-center gap-2 text-[12px] leading-5 text-muted-foreground">
        <span aria-hidden="true" className="h-0.5 w-4 shrink-0" style={{ background: entry.color }} />
        {entry.name}
      </span>
      <span className="ml-6 block font-mono text-[16px] font-medium leading-6 text-foreground">{entry.value}</span>
      {entry.lagged && <span className="ml-6 block text-[11px] text-muted-foreground">{tx(entry.asOf)}</span>}
    </button>)}
  </div>;
}
