"use client";

/**
 * The archive — every instrument we hold, keyed on the date it was DECIDED.
 *
 * Replaces the old two-column "raw feeds" card wall. Three things change:
 *
 *  - one table, not two lists: the regulators are one regime, not two feeds;
 *  - sorted and dated by the decision, with the publication lag shown, so a
 *    board decision from 2024 no longer reads as 2026 news;
 *  - non-instruments (the SSL certificate, the journal issue) stay VISIBLE but
 *    are marked, rather than being silently counted as regulation.
 *
 * The drawer is carried over intact: it renders the stored body_text, including
 * the release's own before/after parameter table. It is the only place on the
 * site where the rule appears in the regulator's own words, and every citation
 * in the brief above lands here.
 */
import { useEffect, useState } from "react";
import { sourceLabel, type NewsItem } from "@/app/lib/news";
import type { InstrumentKind } from "@/app/lib/regulation";

export interface ArchiveRow {
  item: NewsItem;
  kind: InstrumentKind;
  /** Decision date where the title carries one, else the publication date. */
  decidedAt: string;
  /** True when `decidedAt` is really just the scrape date. */
  decidedIsFallback: boolean;
  lagDays: number | null;
  decisionNo: number | null;
}

const KIND_LABEL: Record<InstrumentKind, string> = {
  rate: "Rate",
  rule: "Rule",
  board: "Board",
  other: "—",
  unclassified: "?",
};

const TABS = [
  { key: "instruments", label: "Rules & rates" },
  { key: "board", label: "Board decisions" },
  { key: "other", label: "Everything else" },
  { key: "all", label: "All" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function matches(row: ArchiveRow, tab: TabKey): boolean {
  if (tab === "all") return true;
  if (tab === "instruments") return row.kind === "rate" || row.kind === "rule";
  if (tab === "board") return row.kind === "board";
  return row.kind === "other" || row.kind === "unclassified";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function shortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso.slice(0, 10);
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1].slice(2)}`;
}

// ── the drawer (carried over — it renders the rule's own table) ──────────────

function isTableBlock(block: string): boolean {
  const lines = block.split("\n");
  return (
    lines.length >= 2 &&
    lines.every((l) => l.trim().startsWith("|")) &&
    /^\s*\|(\s*:?-+:?\s*\|)+\s*$/.test(lines[1])
  );
}

function isListBlock(block: string): boolean {
  const lines = block.split("\n");
  return lines.length > 0 && lines.every((l) => /^-\s+/.test(l.trim()));
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => c.trim().replace(/\\\|/g, "|"));
}

function MarkdownTable({ block }: { block: string }) {
  const lines = block.split("\n");
  const header = splitRow(lines[0]);
  const rows = lines.slice(2).map(splitRow);
  return (
    <div className="overflow-x-auto border-t-2 border-foreground">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {header.map((h, i) => (
              <th
                key={i}
                className={`border-b border-hair py-1.5 font-mono text-[9px] font-normal tracking-[0.07em] uppercase text-faint ${
                  i === 0 ? "text-left" : "pl-2 text-right"
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((c, ci) => (
                <td
                  key={ci}
                  className={`border-b border-hair py-1.5 text-[12.5px] text-foreground ${
                    ci === 0 ? "text-left" : "pl-2 text-right font-mono font-semibold tabular-nums"
                  }`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BodyContent({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="space-y-3 text-sm leading-relaxed text-foreground">
      {blocks.map((b, i) =>
        isTableBlock(b) ? (
          <MarkdownTable key={i} block={b} />
        ) : isListBlock(b) ? (
          <ul key={i} className="list-disc space-y-1 pl-5">
            {b.split("\n").map((l, j) => (
              <li key={j}>{l.trim().replace(/^-\s+/, "")}</li>
            ))}
          </ul>
        ) : (
          <p key={i}>{b}</p>
        ),
      )}
    </div>
  );
}

function Drawer({ row, onClose }: { row: ArchiveRow | null; onClose: () => void }) {
  useEffect(() => {
    if (!row) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [row, onClose]);

  const open = row !== null;
  const body = row?.item.body_text?.trim();

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        className={`fixed inset-0 z-30 bg-foreground/25 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={row?.item.title ?? "Instrument"}
        className={`fixed top-0 right-0 z-40 flex h-full w-full max-w-xl flex-col border-l border-border bg-card transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {row && (
          <>
            <header className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
              <div>
                <div className="font-mono text-[9px] tracking-[0.07em] uppercase text-faint">
                  {sourceLabel(row.item.source)} · decided {shortDate(row.decidedAt)}
                  {row.lagDays != null && row.lagDays > 0 && ` · published ${row.lagDays}d later`}
                  {row.decisionNo != null && ` · #${row.decisionNo}`}
                </div>
                <h2 className="mt-1 text-[15px] leading-snug font-semibold text-foreground">
                  {row.item.title}
                </h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="shrink-0 p-1 text-muted-foreground transition hover:text-foreground"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              {body ? (
                <BodyContent text={body} />
              ) : (
                <p className="text-sm text-muted-foreground italic">
                  No text cached for this instrument — open the original below.
                </p>
              )}
            </div>

            <footer className="border-t border-border px-6 py-3">
              <a href={row.item.url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-primary">
                Open the original at {sourceLabel(row.item.source)} ↗
              </a>
            </footer>
          </>
        )}
      </aside>
    </>
  );
}

// ── the table ───────────────────────────────────────────────────────────────

export default function Archive({ rows, held }: { rows: ArchiveRow[]; held: number }) {
  const [tab, setTab] = useState<TabKey>("instruments");
  const [open, setOpen] = useState<ArchiveRow | null>(null);

  const shown = rows.filter((r) => matches(r, tab));

  return (
    <section>
      <div className="mb-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-[13.5px] font-bold text-foreground">The archive</h3>
        <span className="ml-auto font-mono text-[8.5px] tracking-[0.07em] uppercase text-faint">
          {held.toLocaleString()} instruments held · keyed on the date decided, not the date scraped
        </span>
      </div>

      {/* Mono-caps with an ink underline — blue is a verb, and a filter navigates nowhere. */}
      <div className="flex flex-wrap gap-px">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`border-b-2 px-1.5 pt-0.5 pb-1 font-mono text-[9px] tracking-[0.07em] uppercase transition ${
              tab === t.key
                ? "border-foreground font-semibold text-foreground"
                : "border-transparent text-faint hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <table className="mt-2 w-full border-collapse">
        <thead>
          <tr>
            {["Instrument", "Decided", "Published", "Lag", "Type"].map((h, i) => (
              <th
                key={h}
                className={`border-b border-foreground pb-1.5 font-mono text-[8.5px] font-normal tracking-[0.07em] uppercase text-faint ${
                  i === 0 ? "text-left" : "pl-2 text-right"
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr
              key={`${r.item.source}-${r.item.external_id}`}
              onClick={() => setOpen(r)}
              className="cursor-pointer transition hover:bg-muted"
            >
              <td className={`border-b border-hair py-1.5 ${r.kind === "other" ? "opacity-55" : ""}`}>
                <span className="text-[12.5px] leading-snug font-medium text-foreground">{r.item.title}</span>
                {r.kind === "other" && (
                  <span className="ml-1.5 font-mono text-[8.5px] tracking-[0.05em] uppercase text-faint">
                    not an instrument
                  </span>
                )}
                {r.decidedIsFallback && r.kind === "board" && (
                  <span className="ml-1.5 font-mono text-[8.5px] tracking-[0.05em] uppercase text-faint">
                    no decision date in title
                  </span>
                )}
              </td>
              <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                {shortDate(r.decidedAt)}
              </td>
              <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] tabular-nums text-faint">
                {shortDate(r.item.published_at)}
              </td>
              <td
                className={`border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] font-semibold tabular-nums ${
                  (r.lagDays ?? 0) > 365 ? "text-negative" : "text-muted-foreground"
                }`}
              >
                {r.lagDays == null ? "—" : `${r.lagDays}d`}
              </td>
              <td className="border-b border-hair py-1.5 pl-2 text-right font-mono text-[11px] font-semibold text-foreground">
                {KIND_LABEL[r.kind]}
              </td>
            </tr>
          ))}
          {shown.length === 0 && (
            <tr>
              <td colSpan={5} className="py-3 text-[12px] text-muted-foreground italic">
                Nothing of this kind in the window.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <p className="mt-2 font-mono text-[8.5px] tracking-[0.05em] uppercase text-faint">
        {shown.length} shown · click any row to read the instrument in the regulator&apos;s own words
      </p>

      <Drawer row={open} onClose={() => setOpen(null)} />
    </section>
  );
}
