"use client";

/**
 * Per-agent run controls — the form is generated from the agent's declared
 * inputs, so adding a dispatch input to the registry adds the field here and
 * its server-side validation at the same time. There is no second place to
 * update, which is the point.
 *
 * The confirm dialog names what the run PERSISTS. A D1 write is ~1000× the
 * price of a read and three of our tables rebuild wholesale; "are you sure"
 * without saying what happens is not a safeguard.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import type { AgentDef } from "@/app/lib/agents-registry";

const WRITES_WARNING: Record<AgentDef["writes"], string> = {
  artifacts: "Results come back as run artifacts. Nothing publishes.",
  d1: "⚠ This run WRITES TO D1 — billed rows, and it can publish.",
  none: "This run persists nothing.",
};

export default function AgentRunControls({
  agent,
  disabled,
}: {
  agent: AgentDef;
  disabled?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(agent.inputs.map((i) => [i.name, i.default ?? ""])),
  );

  const set = (name: string, v: string) => setValues((prev) => ({ ...prev, [name]: v }));

  async function run() {
    if (busy) return;
    const summary = agent.inputs
      .map((i) => `${i.name}=${values[i.name] || "(default)"}`)
      .join("  ");
    if (
      !window.confirm(
        `Run ${agent.name}?\n\n${summary}\n\n${WRITES_WARNING[agent.writes]}`,
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/admin/agents/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: agent.id, inputs: values }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        toast.success(`Dispatched ${agent.name}`, {
          description: "GitHub takes a few seconds to register the run.",
        });
        // The page renders run status on the server — re-render it rather than
        // holding a second, divergent copy of the same state on the client.
        setTimeout(() => router.refresh(), 3500);
      } else {
        toast.error(`Couldn't run ${agent.name}`, {
          description: body.error ?? `HTTP ${res.status}`,
        });
      }
    } catch {
      toast.error(`Couldn't run ${agent.name}`);
    } finally {
      setBusy(false);
    }
  }

  const field =
    "h-6 rounded border border-border bg-transparent px-1.5 font-mono text-[10px] text-foreground outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50";

  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-2 justify-self-end">
      {agent.inputs.map((input) => (
        <label key={input.name} className="flex flex-col gap-1" title={input.help}>
          <span className="font-mono text-[8.5px] uppercase tracking-[0.06em] text-muted-foreground">
            {input.label}
          </span>
          {input.type === "choice" ? (
            <select
              aria-label={input.label}
              value={values[input.name] ?? ""}
              onChange={(e) => set(input.name, e.target.value)}
              disabled={disabled || busy}
              className={field}
            >
              {input.options?.map((o) => (
                <option key={o} value={o}>
                  {o === "" ? "(default)" : o}
                </option>
              ))}
            </select>
          ) : input.type === "boolean" ? (
            <select
              aria-label={input.label}
              value={values[input.name] ?? "false"}
              onChange={(e) => set(input.name, e.target.value)}
              disabled={disabled || busy}
              className={field}
            >
              <option value="false">off</option>
              <option value="true">on</option>
            </select>
          ) : (
            <input
              type="text"
              aria-label={input.label}
              value={values[input.name] ?? ""}
              placeholder={input.placeholder}
              onChange={(e) => set(input.name, e.target.value)}
              disabled={disabled || busy}
              size={Math.max(8, (input.placeholder?.length ?? 10) - 1)}
              className={field}
            />
          )}
        </label>
      ))}
      <button
        type="button"
        onClick={() => void run()}
        disabled={disabled || busy}
        className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted-foreground underline decoration-border underline-offset-4 transition-colors hover:text-foreground hover:decoration-current disabled:opacity-40"
      >
        {busy ? "Dispatching…" : "Run"}
      </button>
    </div>
  );
}
