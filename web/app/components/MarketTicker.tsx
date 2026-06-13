"use client";

/**
 * Live "flowing data" strip — a scrolling ticker of BIST indices, FX, and
 * commodities (Brent, gold). Server-rendered with initial values, then polls
 * /api/market-ticker every 60s so the numbers stay fresh without a reload.
 * ~15-min delayed during market hours; last close otherwise.
 */
import { useEffect, useState } from "react";
import type { TickerItem } from "@/app/lib/market-ticker";

const nfPct = (v: number) =>
  `${v >= 0 ? "+" : ""}${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}%`;

function Item({ it }: { it: TickerItem }) {
  const up = it.changePct != null && it.changePct >= 0;
  const tone =
    it.changePct == null ? "text-muted-foreground" : up ? "text-positive" : "text-negative";
  return (
    <span className="inline-flex items-center gap-1.5 px-4">
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {it.label}
      </span>
      <span className="text-sm font-semibold tabular-nums text-foreground">{it.value}</span>
      {it.changePct != null && (
        <span className={`text-xs font-medium tabular-nums ${tone}`}>
          {up ? "▲" : "▼"} {nfPct(it.changePct)}
        </span>
      )}
      <span aria-hidden className="text-border">·</span>
    </span>
  );
}

export default function MarketTicker({ items: initial }: { items: TickerItem[] }) {
  const [items, setItems] = useState<TickerItem[]>(initial);

  useEffect(() => {
    const tick = async () => {
      try {
        const res = await fetch("/api/market-ticker", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as { items?: TickerItem[] };
        if (Array.isArray(data.items) && data.items.length) setItems(data.items);
      } catch {
        /* keep the last good values */
      }
    };
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);

  if (!items.length) return null;

  return (
    <div className="bddk-ticker-wrap relative overflow-hidden rounded-lg border border-border bg-card">
      {/* edge fades */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-card to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-card to-transparent" />
      <div className="bddk-ticker-track flex w-max py-2">
        {/* Two copies for a seamless -50% loop. */}
        {[0, 1].map((copy) => (
          <div key={copy} className="flex shrink-0" aria-hidden={copy === 1}>
            {items.map((it, i) => (
              <Item key={`${copy}-${it.label}-${i}`} it={it} />
            ))}
          </div>
        ))}
      </div>
      <style>{`
        @keyframes bddkTickerScroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
        .bddk-ticker-track { animation: bddkTickerScroll 45s linear infinite; }
        .bddk-ticker-wrap:hover .bddk-ticker-track { animation-play-state: paused; }
        @media (prefers-reduced-motion: reduce) { .bddk-ticker-track { animation: none; } }
      `}</style>
    </div>
  );
}
