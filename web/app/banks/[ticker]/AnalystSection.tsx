/**
 * The analyst's read — the comparability badge plus the latest generated memo.
 *
 * Self-contained on purpose (the page is 1,800 lines): it runs its own
 * queries, and the whole analyst_notes/analyst_signals read follows the
 * read-headlines pattern — UNCACHED direct read, try/catch, silent fallback —
 * because those tables do not exist in D1 until the 2026-08-01 write freeze
 * lifts (migration 0037 is authored, unapplied). The badge, by contrast, is
 * built entirely from tables that are already live (bank_audit_opinion + the
 * sweep-established reporting unit), so it renders for every bank today.
 */
import { SecHead } from "@/app/components/desk";
import { classifyBasisLead } from "@/app/lib/analyst/sections";
import { cachedAll, getDB } from "@/app/lib/db";

interface OpinionRow {
  period: string;
  opinion_type: string | null;
  report_kind: string | null;
  auditor: string | null;
  basis_text: string | null;
}

interface NoteRow {
  period: string;
  kind: string;
  title: string;
  body: string;
  model: string | null;
  generated_at: string;
  fact_check_passed: number;
}

interface SignalRow {
  signal_type: string;
  severity: string;
}

// Mirror of src/analyst/extract_basis_metadata.SWEEP_HORIZON: every filing up
// to and including 2026Q1 is thousand-TL, established by the 550-filing sweep.
// Later periods read the pushed analyst_basis_metadata (absent → unknown).
const SWEEP_HORIZON = "2026Q1";

const ASSURANCE: Record<string, string> = {
  review: "limited review",
  audit: "full audit",
};

async function latestNote(ticker: string): Promise<NoteRow | null> {
  try {
    const db = await getDB();
    const row = await db
      .prepare(
        "SELECT period, kind, title, body, model, generated_at, fact_check_passed " +
          "FROM v_latest_analyst_note WHERE bank_ticker = ?",
      )
      .bind(ticker)
      .first<NoteRow>();
    return row ?? null;
  } catch {
    return null; // table not migrated yet — the freeze; render "pending"
  }
}

async function signalsFor(ticker: string, period: string, kind: string): Promise<SignalRow[]> {
  try {
    const db = await getDB();
    const { results } = await db
      .prepare(
        "SELECT signal_type, severity FROM analyst_signals " +
          "WHERE bank_ticker = ? AND period = ? AND kind = ? ORDER BY severity",
      )
      .bind(ticker, period, kind)
      .all<SignalRow>();
    return results;
  } catch {
    return [];
  }
}

/** Minimal markdown-ish renderer for the memo body — headings, bullets,
 *  paragraphs. No raw HTML ever reaches this (the body is LLM text that
 *  passed the figure guard; rendering stays text-only by construction). */
function MemoBody({ body }: { body: string }) {
  const blocks = body.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="space-y-2.5">
      {blocks.map((b, i) => {
        if (b.startsWith("# ")) return null; // headline is rendered separately
        if (b.startsWith("## ")) {
          return (
            <h4 key={i} className="pt-1 text-[11px] font-bold uppercase tracking-[0.05em] text-foreground">
              {b.slice(3)}
            </h4>
          );
        }
        if (b.split("\n").every((l) => l.trim().startsWith("|"))) {
          const rows = b
            .split("\n")
            .map((l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()))
            .filter((cells) => !cells.every((c) => /^:?-{2,}:?$/.test(c)));
          return (
            <div key={i} className="overflow-x-auto">
              <table className="w-full border-collapse text-[11px]">
                <tbody>
                  {rows.map((cells, ri) => (
                    <tr key={ri} className="border-b border-hair">
                      {cells.map((c, ci) => (
                        <td key={ci} className={`py-1 pr-3 align-top ${ri === 0 ? "font-semibold text-foreground" : "font-mono text-[10.5px] text-muted-foreground"}`}>
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
        if (/^[-*] /m.test(b)) {
          return (
            <ul key={i} className="list-disc space-y-1 pl-4 text-[12px] leading-relaxed text-muted-foreground">
              {b.split(/\n/).map((li, j) => (
                <li key={j}>{li.replace(/^[-*] /, "")}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="text-[12px] leading-relaxed text-muted-foreground">
            {b}
          </p>
        );
      })}
    </div>
  );
}

export default async function AnalystSection({
  ticker,
  kind,
}: {
  ticker: string;
  kind: string;
}) {
  const opinions = await cachedAll<OpinionRow>(
    "SELECT period, opinion_type, report_kind, auditor, basis_text " +
      "FROM bank_audit_opinion WHERE bank_ticker = ? AND kind = ? ORDER BY period",
    [ticker, kind],
  );
  if (opinions.length === 0) return null;

  const latest = opinions[opinions.length - 1];
  let streak = 0;
  for (let i = opinions.length - 1; i >= 0; i--) {
    if (opinions[i].opinion_type === "qualified") streak++;
    else break;
  }
  const lead = latest.basis_text
    ? latest.basis_text.slice(0, 600).replace(/\s+/g, " ").trim()
    : null;
  const category = classifyBasisLead(lead);
  const unit = latest.period <= SWEEP_HORIZON ? "thousand TL" : "unit pending";

  const badge = [
    latest.period,
    ASSURANCE[latest.report_kind ?? ""] ?? latest.report_kind ?? "assurance n/a",
    kind,
    "BRSA basis",
    unit,
    latest.opinion_type === "qualified"
      ? `Qualified${category === "free_provision" ? " — free provision" : ""}${latest.auditor ? ` (${latest.auditor})` : ""}${streak > 1 ? ` · ${streak} quarters running` : ""}`
      : `${latest.opinion_type ?? "opinion n/a"}${latest.auditor ? ` (${latest.auditor})` : ""}`,
  ].join(" · ");

  const [note, signals] = await Promise.all([
    latestNote(ticker),
    signalsFor(ticker, latest.period, kind),
  ]);

  return (
    <section className="mt-8">
      <SecHead title="The analyst's read" meta="grounded on stored rows · figures machine-checked" className="mb-2" />
      <p className="mb-3 font-mono text-[9.5px] uppercase tracking-[0.06em] text-faint">{badge}</p>

      {latest.opinion_type === "qualified" && lead && (
        <details className="mb-3 border-b border-hair pb-2.5">
          <summary className="cursor-pointer text-[11.5px] font-semibold text-primary">
            What the auditor said — basis for the qualified opinion
          </summary>
          <p className="mt-1.5 text-[11.5px] italic leading-relaxed text-muted-foreground">“{lead}…”</p>
        </details>
      )}

      {signals.length > 0 && (
        <p className="mb-3 text-[11px] text-muted-foreground">
          {signals.length} comparability signal{signals.length === 1 ? "" : "s"} this quarter:{" "}
          <span className="font-mono text-[10px]">
            {signals.map((s) => `${s.signal_type} [${s.severity}]`).join(" · ")}
          </span>
        </p>
      )}

      {note && note.fact_check_passed === 1 ? (
        <>
          <h3 className="mb-2 text-[13.5px] font-bold leading-snug text-foreground">{note.title}</h3>
          <MemoBody body={note.body} />
          <p className="mt-2.5 font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
            {note.period} · {note.kind} · {note.model ?? "model n/a"} · generated {note.generated_at.slice(0, 10)} · every figure verified against stored rows
          </p>
        </>
      ) : (
        <p className="text-[11.5px] text-muted-foreground">
          Analysis pending — memos are generated in CI (<span className="font-mono text-[10.5px]">analyst-daily.yml</span>) and
          publish here when the D1 write freeze lifts. The badge above is live data.
        </p>
      )}
    </section>
  );
}
