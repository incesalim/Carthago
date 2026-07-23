"use client";

/**
 * The interactive product-shelf grid: banks (rows) × the selected block's
 * attributes (columns). Four states encoded by BOTH shape and colour so the grid
 * stays legible for colour-blind viewers and in both themes:
 *   ● Has it (green)  ◑ Partial (green)  · No (faint)  ○ Unverified (amber)
 * Click a cell → the bank's own evidence; click a bank → its shelf profile.
 * Amber = "about us, not the bank" so the honest gaps read as gaps, not absence.
 */
import * as React from "react";
import { cn } from "@/app/lib/cn";
import type { CellValue, ProductBenchmark, ProductBank } from "@/app/lib/products";

const STATE_LABEL: Record<CellValue, string> = {
  yes: "Has it",
  partial: "Partial",
  no: "No",
  unknown: "Unverified",
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

function Glyph({ v, className }: { v: CellValue; className?: string }) {
  const box = cn("inline-grid place-items-center", className);
  if (v === "yes")
    return <span className={box}><span className="size-[15px] rounded-full bg-positive" /></span>;
  if (v === "partial")
    return (
      <span className={box}>
        <span
          className="size-[15px] rounded-full border-[1.5px] border-positive"
          style={{ background: "linear-gradient(90deg, var(--positive) 0 50%, transparent 50% 100%)" }}
        />
      </span>
    );
  if (v === "no")
    return <span className={box}><span className="size-[3px] rounded-full bg-faint" /></span>;
  // unknown — amber hollow ring (about us)
  return (
    <span className={box}>
      <span className="size-[15px] rounded-full border-[1.6px] border-[#b07a18] dark:border-[#d6a23e]" />
    </span>
  );
}

type Detail =
  | { kind: "cell"; ticker: string; code: string }
  | { kind: "bank"; ticker: string }
  | null;

export default function ProductMatrix({ data }: { data: ProductBenchmark }) {
  const [block, setBlock] = React.useState(data.blocks[0]?.id ?? "A");
  const [cluster, setCluster] = React.useState<string>("all");
  const [q, setQ] = React.useState("");
  const [detail, setDetail] = React.useState<Detail>(null);

  const bankByTicker = React.useMemo(
    () => Object.fromEntries(data.banks.map((b) => [b.ticker, b])),
    [data.banks],
  );
  const attrByCode = React.useMemo(
    () => Object.fromEntries(data.attrs.map((a) => [a.code, a])),
    [data.attrs],
  );

  const banks = React.useMemo(() => {
    const query = q.trim().toLowerCase();
    return data.banks.filter((b) => {
      if (cluster !== "all" && b.cluster !== cluster) return false;
      if (query && !b.ticker.toLowerCase().includes(query) && !b.name.toLowerCase().includes(query))
        return false;
      return true;
    });
  }, [data.banks, cluster, q]);

  const cols = React.useMemo(
    () => data.attrs.filter((a) => a.block === block),
    [data.attrs, block],
  );
  const blockName = data.blocks.find((x) => x.id === block)?.name ?? "";

  const close = () => setDetail(null);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative">
      {/* controls */}
      <div className="sticky top-0 z-20 -mx-1 mb-4 space-y-2 bg-background/85 px-1 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="flex flex-wrap gap-1.5">
          {data.blocks.map((b) => (
            <Chip key={b.id} active={b.id === block} onClick={() => setBlock(b.id)}>
              {b.id} · {b.name}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={cluster === "all"} onClick={() => setCluster("all")}>all</Chip>
          {data.clusters.map((c) => (
            <Chip key={c} active={cluster === c} onClick={() => setCluster(c)}>{c}</Chip>
          ))}
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="find a bank…"
            className="ml-auto min-w-32 flex-1 rounded-full border border-border bg-card px-3 py-1 font-mono text-[12px] text-foreground outline-none placeholder:text-faint focus:border-foreground/40 sm:max-w-48"
          />
        </div>
        <Legend />
      </div>

      {/* matrix */}
      <div className="overflow-x-auto rounded-md border border-border bg-card">
        <table className="w-full border-separate border-spacing-0 font-mono">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-10 min-w-[128px] border-b border-r border-border bg-card px-3 py-2 text-left text-[9.5px] font-medium uppercase tracking-[0.1em] text-faint">
                bank
              </th>
              {cols.map((a) => (
                <th
                  key={a.code}
                  title={`${a.label}  ·  ${a.enough ? `penetration ${pct(a.pen ?? 0)}` : "evidence too thin"}`}
                  className="border-b border-r border-border bg-card px-1 py-1.5 align-bottom text-center text-[11px] font-semibold text-muted-foreground"
                >
                  {a.code}
                  {a.distinctive && <span className="text-[#b07a18] dark:text-[#d6a23e]"> ◆</span>}
                  <span className="mt-0.5 block text-[9px] font-normal text-faint">
                    {a.enough ? pct(a.pen ?? 0) : "—"}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {banks.map((b) => (
              <tr key={b.ticker} className="group">
                <td
                  onClick={() => setDetail({ kind: "bank", ticker: b.ticker })}
                  className="sticky left-0 z-[5] min-w-[128px] cursor-pointer border-b border-r border-border bg-card px-3 py-1.5 group-hover:bg-accent"
                >
                  <div className="text-[12.5px] font-semibold tracking-[0.02em] text-foreground">{b.ticker}</div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[9.5px] text-faint">
                    <span className="inline-block h-1 w-8 overflow-hidden rounded-full bg-border">
                      <span className="block h-full bg-positive" style={{ width: pct(b.shelf) }} />
                    </span>
                    {pct(b.shelf)}
                  </div>
                </td>
                {cols.map((a) => {
                  const cell = b.cells[a.code];
                  const v = cell?.v ?? "unknown";
                  return (
                    <td
                      key={a.code}
                      onClick={() => setDetail({ kind: "cell", ticker: b.ticker, code: a.code })}
                      className="h-[30px] cursor-pointer border-b border-r border-border text-center transition-colors hover:bg-accent"
                    >
                      <Glyph v={v} className="mx-auto size-6" />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 font-mono text-[11px] text-muted-foreground">
        {banks.length} banks · block {block} — {blockName} ({cols.length} attributes)
      </p>

      {/* detail */}
      {detail && (
        <>
          <div className="fixed inset-0 z-40 bg-foreground/30" onClick={close} aria-hidden />
          <aside className="fixed inset-y-0 right-0 z-50 flex w-[min(430px,92vw)] flex-col border-l border-border bg-card shadow-2xl">
            {detail.kind === "cell" ? (
              <CellDetail data={data} bank={bankByTicker[detail.ticker]} code={detail.code} attr={attrByCode[detail.code]} onClose={close} />
            ) : (
              <BankDetail bank={bankByTicker[detail.ticker]} onClose={close} />
            )}
          </aside>
        </>
      )}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "whitespace-nowrap rounded-full border px-2.5 py-1 font-mono text-[11.5px] tracking-[0.02em] transition-colors",
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border bg-card text-muted-foreground hover:border-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5"><Glyph v="yes" className="size-4" /> Has it</span>
      <span className="inline-flex items-center gap-1.5"><Glyph v="partial" className="size-4" /> Partial</span>
      <span className="inline-flex items-center gap-1.5"><Glyph v="no" className="size-4" /> No</span>
      <span className="inline-flex items-center gap-1.5">
        <Glyph v="unknown" className="size-4" /> Unverified <em className="text-[#b07a18] not-italic dark:text-[#d6a23e]">(about us)</em>
      </span>
      <span className="text-faint">◆ discriminating attribute</span>
    </div>
  );
}

function RailHeader({ kicker, title, onClose }: { kicker: React.ReactNode; title: React.ReactNode; onClose: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border px-5 pb-3.5 pt-4">
      <div>
        <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">{kicker}</div>
        <h3 className="mt-0.5 text-[19px] font-bold tracking-tight text-foreground">{title}</h3>
      </div>
      <button type="button" aria-label="close" onClick={onClose} className="-mr-1 text-[22px] leading-none text-muted-foreground hover:text-foreground">
        ×
      </button>
    </div>
  );
}

function CellDetail({
  data, bank, code, attr, onClose,
}: {
  data: ProductBenchmark;
  bank: ProductBank;
  code: string;
  attr: ProductBenchmark["attrs"][number];
  onClose: () => void;
}) {
  const cell = bank.cells[code];
  const v = cell?.v ?? "unknown";
  return (
    <>
      <RailHeader
        kicker={`${bank.name} · ${code} · ${attr.blockName}`}
        title={<>{attr.label}{attr.distinctive && <span className="text-[#b07a18] dark:text-[#d6a23e]"> ◆</span>}</>}
        onClose={onClose}
      />
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="my-1 flex items-center gap-3 rounded-lg border border-border bg-background px-3.5 py-3">
          <Glyph v={v} className="size-7" />
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              {v === "unknown" ? "about us" : "about the bank"}
            </div>
            <div className={cn("text-[16px] font-bold tracking-tight", v === "unknown" ? "text-[#b07a18] dark:text-[#d6a23e]" : v === "no" ? "text-muted-foreground" : "text-positive")}>
              {STATE_LABEL[v]}
            </div>
          </div>
        </div>
        {cell?.url && (
          <a
            href={cell.url}
            target="_blank"
            rel="noopener"
            className="mt-4 inline-flex items-center gap-1.5 break-all rounded-full border border-border px-3.5 py-2 font-mono text-[12px] text-primary hover:border-primary"
          >
            evidence →
          </a>
        )}
        {v === "unknown" && (
          <div className="mt-4 rounded-md border border-[#b07a18]/40 bg-[#b07a18]/10 px-3 py-2.5 text-[12.5px] leading-relaxed text-[#b07a18] dark:border-[#d6a23e]/40 dark:text-[#d6a23e]">
            This is <b>unverified</b> — we could not confirm it, so it is left open. It does not mean the bank lacks the product; it is a gap about us.
          </div>
        )}
        <div className="mt-4 font-mono text-[12px] text-muted-foreground">
          {attr.enough ? (
            <>Sector penetration: <b className="text-foreground">{pct(attr.pen ?? 0)}</b> ({attr.yes} has · {attr.partial} partial · {attr.no} no · {attr.unknown} unverified)</>
          ) : (
            <>Not enough banks verified (denominator &lt; {data.minVer}); penetration not computed.</>
          )}
        </div>
      </div>
    </>
  );
}

function BankDetail({ bank, onClose }: { bank: ProductBank; onClose: () => void }) {
  const tot = bank.yes + bank.no + bank.partial + bank.unknown || 1;
  const seg = (n: number, color: string) => (n ? <span style={{ width: `${(n / tot) * 100}%`, background: color }} /> : null);
  return (
    <>
      <RailHeader kicker={`${bank.cluster} · ${bank.ticker}`} title={bank.name} onClose={onClose} />
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="flex h-2.5 overflow-hidden rounded-full border border-border [&>span]:h-full">
          {seg(bank.yes, "var(--positive)")}
          {seg(bank.partial, "color-mix(in srgb, var(--positive) 55%, transparent)")}
          {seg(bank.no, "var(--border)")}
          {seg(bank.unknown, "#b07a18")}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3.5 font-mono text-[11px] text-muted-foreground">
          <span><b className="text-foreground">{bank.yes}</b> has</span>
          <span><b className="text-foreground">{bank.partial}</b> partial</span>
          <span><b className="text-foreground">{bank.no}</b> no</span>
          <span className="text-[#b07a18] dark:text-[#d6a23e]"><b>{bank.unknown}</b> unverified</span>
        </div>
        <div className="mt-4 flex gap-6">
          <Metric label="Verified shelf" value={pct(bank.shelf)} tone="pos" />
          <Metric label="Evidence coverage" value={pct(bank.coverage)} tone={bank.coverage < 0.65 ? "warn" : "ink"} />
        </div>
        {bank.shelfNotes && (
          <p className="mt-4 text-[14px] leading-relaxed text-muted-foreground">{bank.shelfNotes}</p>
        )}
        {bank.distinctive.length > 0 && (
          <>
            <div className="mt-5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">What sets its shelf apart</div>
            <ul className="mt-1.5 flex flex-col gap-2">
              {bank.distinctive.map((d, i) => (
                <li key={i} className="relative pl-4 text-[13.5px] leading-relaxed text-muted-foreground before:absolute before:left-0 before:text-positive before:content-['▪']">
                  {d}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "pos" | "warn" | "ink" }) {
  return (
    <div>
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{label}</div>
      <div className={cn("font-mono text-[26px] font-semibold", tone === "pos" ? "text-positive" : tone === "warn" ? "text-[#b07a18] dark:text-[#d6a23e]" : "text-foreground")}>
        {value}
      </div>
    </div>
  );
}
