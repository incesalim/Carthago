"use client";

/**
 * Purge the dashboard's KV page/data cache so a just-refreshed source shows up
 * in the graphs immediately (D1 reads are otherwise cached ~12h). Loops the
 * batched, cursor-paginated /api/admin/purge-cache endpoint until it reports
 * done, surfacing a running entry count via a single toast.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/app/components/ui";

interface PurgeResponse {
  deleted?: number;
  cursor?: string | null;
  done?: boolean;
  error?: string;
}

export default function PurgeCacheButton() {
  const [busy, setBusy] = useState(false);

  async function purge() {
    if (busy) return;
    if (
      !window.confirm(
        "Purge the dashboard cache?\n\nPages will re-read D1 on the next view, so a just-refreshed bulletin/EVDS week shows up immediately. Safe — this only clears a cache.",
      )
    ) {
      return;
    }
    setBusy(true);
    const id = toast.loading("Purging cache…");
    let cursor: string | null = null;
    let total = 0;
    try {
      // Cap rounds as a safety backstop (500 × 200 = 100k keys).
      for (let i = 0; i < 200; i++) {
        const res = await fetch("/api/admin/purge-cache", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cursor ? { cursor } : {}),
        });
        const body = (await res.json().catch(() => ({}))) as PurgeResponse;
        if (!res.ok) {
          toast.error("Cache purge failed", {
            id,
            description: body.error ?? `HTTP ${res.status}`,
          });
          return;
        }
        total += body.deleted ?? 0;
        if (body.done || !body.cursor) {
          toast.success(`Cache purged — ${total} ${total === 1 ? "entry" : "entries"} cleared`, {
            id,
            description: "Reload a page to see the latest data.",
          });
          return;
        }
        cursor = body.cursor;
        toast.loading(`Purging cache… ${total} entries`, { id });
      }
      toast.success(`Cache purge: ${total} entries cleared (hit the round cap)`, { id });
    } catch {
      toast.error("Cache purge failed", { id });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => void purge()}
      disabled={busy}
      title="Clear the dashboard's KV cache so a just-refreshed source appears in the graphs without waiting for the 12h cache window."
    >
      {busy ? "Purging…" : "Purge cache"}
    </Button>
  );
}
