"use client";

import { useEffect, useState } from "react";
import { Badge, Button } from "@/app/components/ui";
import { relativeFromIso } from "@/app/lib/format-time";
import { STATUS_LABEL, STATUS_VARIANT } from "./status";

export interface OpenCell {
  bank: string;
  period: string;
  kind: string;
  type: string; // statement_type key
  typeLabel: string;
  status: string;
  pdfPresent: boolean;
  hasValidator: boolean;
  validationStatement: string | null; // which validation row to surface
}

interface Detail {
  extraction: {
    note: string | null;
    success: number;
    rows_bs_assets: number | null;
    rows_bs_liabilities: number | null;
    rows_off_balance: number | null;
    rows_profit_loss: number | null;
    extracted_at: string | null;
  } | null;
  validation: {
    statement: string;
    checks_failed: number;
    checks_passed: number;
    failed_detail: string | null;
  }[];
  coverage: { statement_type: string; status: string; row_count: number; is_manual: number; pdf_present: number }[];
}

interface FailRow {
  check?: string;
  node?: string;
  expected?: number;
  actual?: number;
  diff?: number;
}

function parseFailures(json: string | null): FailRow[] {
  if (!json) return [];
  try {
    const v = JSON.parse(json);
    return Array.isArray(v) ? (v as FailRow[]) : [];
  } catch {
    return [];
  }
}

const nf = new Intl.NumberFormat("en-US");

export default function CoverageDrawer({
  open,
  onClose,
  onReextract,
  reextractBusy,
}: {
  open: OpenCell | null;
  onClose: () => void;
  onReextract: (bank: string, period: string, kind: string, statement: string) => void;
  reextractBusy: boolean;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);

  // The parent remounts this component (key=cell) whenever the cell changes, so
  // `open` is fixed for this instance — a mount-only fetch is correct and keeps
  // setState out of a reactive effect (react-hooks/set-state-in-effect).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const cell = `${open.bank}|${open.period}|${open.kind}`;
    const empty: Detail = { extraction: null, validation: [], coverage: [] };
    void (async () => {
      try {
        const res = await fetch(`/api/admin/coverage?cell=${encodeURIComponent(cell)}`, {
          cache: "no-store",
        });
        const b = (await res.json()) as { detail?: Detail };
        if (!cancelled) setDetail(b.detail ?? empty);
      } catch {
        if (!cancelled) setDetail(empty);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loading = open != null && detail == null;

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const ex = detail?.extraction;
  const valRow = detail?.validation.find(
    (v) => v.statement === (open.validationStatement ?? open.type),
  );
  const failures = parseFailures(valRow?.failed_detail ?? null);
  // A missing cell with a PDF is one of two things, told apart by whether the
  // partition has ANY extraction row: never-extracted (acquired, ready to ingest)
  // vs extracted-but-this-statement-empty (likely a scanned-image page → manual).
  const missingWithPdf = open.status === "missing" && open.pdfPresent && !loading;
  const acquiredNotExtracted = missingWithPdf && ex == null;
  const likelyScanned = missingWithPdf && ex != null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <div className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-border bg-background shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border p-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">
              {open.bank} · {open.period} · {open.kind}
            </p>
            <p className="truncate text-xs text-muted-foreground">{open.typeLabel}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={STATUS_VARIANT[open.status] ?? "secondary"}>
              {STATUS_LABEL[open.status] ?? open.status}
            </Badge>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close drawer">
              ✕
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-4 p-4 text-sm">
          {acquiredNotExtracted && (
            <div className="rounded-md border border-info/40 bg-info/10 p-3 text-xs text-info">
              PDF acquired into R2 but this partition hasn&apos;t been extracted yet —
              click <strong>Re-extract</strong> below to ingest it.
            </div>
          )}

          {likelyScanned && (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
              The partition is extracted but this statement has no rows — a likely
              scanned-image page. Hand-transcribe it into{" "}
              <code>data/manual_statements.json</code> and run{" "}
              <code>audit_correct.py overlay-statement</code>.
            </div>
          )}

          {open.status === "missing" && !open.pdfPresent && (
            <div className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              No PDF for this partition in R2 — nothing to extract yet.
            </div>
          )}

          {loading && <p className="text-xs text-muted-foreground">Loading…</p>}

          {ex && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Extraction</p>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <dt className="text-muted-foreground">success</dt>
                <dd>{ex.success ? "yes" : "no"}</dd>
                <dt className="text-muted-foreground">assets / liab</dt>
                <dd>
                  {ex.rows_bs_assets ?? "—"} / {ex.rows_bs_liabilities ?? "—"}
                </dd>
                <dt className="text-muted-foreground">P&L / off-bs</dt>
                <dd>
                  {ex.rows_profit_loss ?? "—"} / {ex.rows_off_balance ?? "—"}
                </dd>
                <dt className="text-muted-foreground">extracted</dt>
                <dd>{ex.extracted_at ? relativeFromIso(ex.extracted_at) : "—"}</dd>
              </dl>
              {ex.note && <p className="mt-2 text-xs text-muted-foreground">Note: {ex.note}</p>}
            </div>
          )}

          {!open.hasValidator && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Validation</p>
              {/* Say it, rather than rendering nothing and letting an absent block
                  read as a clean one. This lane has no structural validator, so
                  its "ok" asserts only that a row exists — nothing about whether
                  the values are right. */}
              <p className="text-xs text-warning">
                Not validated — this lane has no structural validator. “ok” means the
                row is present, not that its values were checked.
              </p>
            </div>
          )}

          {open.hasValidator && valRow && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                Validation — {valRow.checks_passed} passed, {valRow.checks_failed} failed
              </p>
              {valRow.checks_passed === 0 && valRow.checks_failed === 0 && (
                <p className="mb-1 text-xs text-warning">
                  Every check skipped — nothing about this cell was actually verified.
                </p>
              )}
              {failures.length === 0 ? (
                <p className="text-xs text-positive">All identity checks foot.</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {failures.map((f, i) => (
                    <li
                      key={i}
                      className="rounded border border-negative/30 bg-negative/5 px-2 py-1 text-xs"
                    >
                      <span className="font-medium">{f.node ?? f.check}</span>
                      {f.expected != null && f.actual != null && (
                        <span className="text-muted-foreground">
                          {" "}
                          — expected {nf.format(f.expected)}, got {nf.format(f.actual)}
                          {f.diff != null ? ` (Δ ${nf.format(f.diff)})` : ""}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="mt-auto border-t border-border p-4">
          <Button
            className="w-full"
            size="sm"
            disabled={reextractBusy || !open.pdfPresent}
            onClick={() => onReextract(open.bank, open.period, open.kind, open.type)}
          >
            {reextractBusy ? "Triggering…" : `Force re-extract this cell`}
          </Button>
          <p className="mt-1 text-center text-[11px] text-muted-foreground">
            {open.pdfPresent
              ? `Re-extracts only ${open.typeLabel} (${open.kind}) for ${open.bank} ${open.period}, overwriting it even if it passes.`
              : "No PDF in R2 to re-extract."}
          </p>
        </div>
      </div>
    </div>
  );
}
