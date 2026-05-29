"use client";

/**
 * Raw TCMB + BDDK feeds with in-app content sidebar.
 *
 * Clicking a card opens a right-side drawer showing the stored body_text
 * (eager-loaded by the server page — TCMB/BDDK don't publish daily, so the
 * payload stays small). Falls back to the summary + an "open original"
 * link when no body was scraped. Each card carries a source pill and a
 * derived topical pill (see lib/newsTags).
 */
import { useEffect, useState } from "react";
import { sourceLabel, type NewsItem } from "@/app/lib/news";
import { sourceTag, topicTag, type Tag } from "@/app/lib/newsTags";

const SOURCE_DESCRIPTIONS: Record<"tcmb" | "bddk", string> = {
  tcmb: "Central Bank of Türkiye — monetary policy + market operations press releases (English).",
  bddk: "Banking Regulation and Supervision Agency — official announcements (Turkish).",
};

const SOURCE_BORDER: Record<string, string> = {
  tcmb: "border-l-[#1f4068]",
  bddk: "border-l-[#0f7b6c]",
};

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function Pill({ tag }: { tag: Tag }) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${tag.className}`}>
      {tag.label}
    </span>
  );
}

// A block is a Markdown pipe table when every line starts with "|" and the
// second line is a separator row (--- cells). Scrapers emit tables in this
// shape (see src/news/_htmltext.py).
function isTableBlock(block: string): boolean {
  const lines = block.split("\n");
  return (
    lines.length >= 2 &&
    lines.every((l) => l.trim().startsWith("|")) &&
    /^\s*\|(\s*:?-+:?\s*\|)+\s*$/.test(lines[1])
  );
}

// A block is a bullet list when every line starts with "- ".
function isListBlock(block: string): boolean {
  const lines = block.split("\n");
  return lines.length > 0 && lines.every((l) => /^-\s+/.test(l.trim()));
}

function MarkdownList({ block }: { block: string }) {
  const items = block.split("\n").map((l) => l.trim().replace(/^-\s+/, ""));
  return (
    <ul className="list-disc pl-5 space-y-1">
      {items.map((it, i) => (
        <li key={i}>{it}</li>
      ))}
    </ul>
  );
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
    <div className="overflow-x-auto rounded-md border border-neutral-200">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-neutral-50">
            {header.map((h, i) => (
              <th
                key={i}
                className={`px-3 py-2 font-semibold text-neutral-700 border-b border-neutral-200 ${
                  i === 0 ? "text-left" : "text-right tabular-nums"
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="border-b border-neutral-100 last:border-0">
              {r.map((c, ci) => (
                <td
                  key={ci}
                  className={`px-3 py-2 text-neutral-700 ${
                    ci === 0 ? "text-left" : "text-right tabular-nums"
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

// Render body_text: blank-line-separated blocks, each a table or a paragraph.
function BodyContent({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="space-y-3 text-sm text-neutral-700 leading-relaxed">
      {blocks.map((b, i) =>
        isTableBlock(b) ? (
          <MarkdownTable key={i} block={b} />
        ) : isListBlock(b) ? (
          <MarkdownList key={i} block={b} />
        ) : (
          <p key={i}>{b}</p>
        ),
      )}
    </div>
  );
}

function FeedCard({ item, onOpen }: { item: NewsItem; onOpen: (it: NewsItem) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className={`block w-full text-left rounded-md border border-neutral-200 border-l-4 ${SOURCE_BORDER[item.source] ?? ""} bg-white p-3 hover:bg-neutral-50 transition`}
    >
      <div className="flex items-baseline justify-between gap-2 text-[10px] text-neutral-500 uppercase tracking-wide mb-1">
        <span className="tabular-nums">{fmtDate(item.published_at)}</span>
        <span className="text-neutral-400">{sourceLabel(item.source)}</span>
      </div>
      <div className="text-sm text-neutral-900 leading-snug line-clamp-3">{item.title}</div>
      <div className="flex flex-wrap gap-1 mt-2">
        <Pill tag={sourceTag(item.source)} />
        <Pill tag={topicTag(item.title)} />
      </div>
    </button>
  );
}

function SourceColumn({
  source,
  items,
  onOpen,
}: {
  source: "tcmb" | "bddk";
  items: NewsItem[];
  onOpen: (it: NewsItem) => void;
}) {
  return (
    <section className="space-y-3">
      <header className="space-y-0.5">
        <h2 className="text-base font-semibold text-neutral-900">{sourceLabel(source)}</h2>
        <p className="text-xs text-neutral-500">{SOURCE_DESCRIPTIONS[source]}</p>
      </header>
      <div className="space-y-2">
        {items.length === 0 ? (
          <div className="text-xs text-neutral-500 italic">No items yet.</div>
        ) : (
          items.map((it) => (
            <FeedCard key={`${it.source}-${it.external_id}`} item={it} onOpen={onOpen} />
          ))
        )}
      </div>
    </section>
  );
}

function Drawer({ item, onClose }: { item: NewsItem | null; onClose: () => void }) {
  // Close on Escape; lock body scroll while open.
  useEffect(() => {
    if (!item) return;
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
  }, [item, onClose]);

  const open = item !== null;
  const hasBody = !!item?.body_text && item.body_text.trim().length > 0;

  return (
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        className={`fixed inset-0 z-30 bg-black/30 transition-opacity ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        aria-hidden="true"
      />
      {/* Panel */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={item?.title ?? "News detail"}
        className={`fixed right-0 top-0 z-40 h-full w-full max-w-xl bg-white shadow-2xl flex flex-col transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {item && (
          <>
            <header className="border-b border-neutral-200 px-6 py-4 flex items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-neutral-500 uppercase tracking-wide">
                  <span className="tabular-nums">{fmtDate(item.published_at)}</span>
                  <Pill tag={sourceTag(item.source)} />
                  <Pill tag={topicTag(item.title)} />
                </div>
                <h2 className="text-lg font-semibold text-neutral-900 leading-snug">{item.title}</h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="shrink-0 rounded-md p-1.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 transition"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              {hasBody ? (
                <BodyContent text={item.body_text as string} />
              ) : item.summary ? (
                <div className="space-y-3">
                  <p className="text-sm text-neutral-700 leading-relaxed">{item.summary}</p>
                  <p className="text-xs text-neutral-400 italic">
                    Full text not cached for this item — open the original for the complete release.
                  </p>
                </div>
              ) : (
                <p className="text-sm text-neutral-500 italic">
                  No content cached for this item. Open the original release below.
                </p>
              )}
            </div>

            <footer className="border-t border-neutral-200 px-6 py-3">
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-neutral-700 hover:text-neutral-900 underline-offset-2 hover:underline"
              >
                Open original at {sourceLabel(item.source)} ↗
              </a>
            </footer>
          </>
        )}
      </aside>
    </>
  );
}

export default function RawFeeds({ tcmb, bddk }: { tcmb: NewsItem[]; bddk: NewsItem[] }) {
  const [selected, setSelected] = useState<NewsItem | null>(null);

  return (
    <section className="space-y-3">
      <header className="space-y-0.5">
        <h2 className="text-base font-semibold text-neutral-900">Raw feeds</h2>
        <p className="text-xs text-neutral-500">
          Source items the briefing draws from. Click a card to read the content here.
        </p>
      </header>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SourceColumn source="tcmb" items={tcmb} onOpen={setSelected} />
        <SourceColumn source="bddk" items={bddk} onOpen={setSelected} />
      </div>
      <Drawer item={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
