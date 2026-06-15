/**
 * Minimal GitHub Actions client for the admin panel: list recent workflow runs
 * and dispatch an allow-listed workflow. Auth via the GITHUB_DISPATCH_TOKEN
 * secret (a fine-grained PAT with Actions: read+write on the repo).
 *
 * When the token is absent, callers get GitHubNotConfigured so the UI can show
 * a "set GITHUB_DISPATCH_TOKEN" empty state instead of erroring.
 */
import { getEnv } from "./cf-env";

export const REPO = "incesalim/turkish-banking-sector";
const API = "https://api.github.com";

export interface WorkflowDef {
  file: string;
  label: string;
  description: string;
}

/** Allow-list of dispatchable workflows (also used to label runs). */
export const WORKFLOWS: WorkflowDef[] = [
  {
    file: "refresh-bddk-bulletins.yml",
    label: "BDDK bulletins",
    description: "Monthly + weekly bulletins → D1",
  },
  {
    file: "refresh-data.yml",
    label: "Full refresh",
    description: "Monthly + weekly + EVDS → D1",
  },
  {
    file: "refresh-evds-daily.yml",
    label: "EVDS (daily)",
    description: "TCMB rates / FX → D1",
  },
  {
    file: "acquire-audit.yml",
    label: "Acquire audit PDFs",
    description: "Discover + download new audit PDFs → R2 (no extraction)",
  },
  {
    file: "refresh-audit.yml",
    label: "Extract audit reports",
    description: "Extract audit PDFs from R2 → bank_audit_* → D1 (manual)",
  },
  {
    file: "refresh-news-daily.yml",
    label: "News (daily)",
    description: "KAP / TCMB / BDDK announcements → D1",
  },
  {
    file: "summarize-regulations.yml",
    label: "Regulation summaries",
    description: "Weekly LLM regulation briefing → D1",
  },
];

const ALLOWED = new Set(WORKFLOWS.map((w) => w.file));

/** The audit workflow accepts a per-bank `bank` dispatch input. */
export const AUDIT_WORKFLOW = "refresh-audit.yml";

/**
 * Targeted single-cell re-extract (the coverage-matrix per-cell button). Takes
 * statement + banks + periods + kind + force; not in WORKFLOWS because it needs
 * a statement (it's not a blind "trigger" like the others), but it IS dispatchable.
 */
export const REEXTRACT_WORKFLOW = "reextract-statement.yml";

/** Statement-type keys the coverage matrix uses (registry keys) — validated
 *  server-side before being forwarded as the `statement` dispatch input. */
export const STATEMENT_TYPES = new Set<string>([
  "balance_sheet_assets", "balance_sheet_liabilities", "profit_loss",
  "other_comprehensive_income", "equity_change", "cash_flow", "off_balance",
  "credit_quality", "stages", "loans_by_sector", "npl_movement",
  "capital", "liquidity", "profile",
]);

/**
 * Tickers the audit pipeline knows about — mirrors the keys of
 * data/banks/audit_report_urls.json (which isn't bundled into the Worker).
 * Used both to populate the admin panel's bank picker and to validate the
 * `bank` dispatch input server-side. Keep in sync when banks are added.
 */
export const AUDIT_BANKS = [
  "AKBNK", "YKBNK", "HALKB", "VAKBN", "ICBCT", "QNBFB", "SKBNK", "ALBRK",
  "KLNMA", "ISCTR", "TSKB", "ZIRAAT", "DENIZ", "TEB", "ING", "FIBA",
  "BURGAN", "ODEA", "ATBANK", "KUVEYT", "TFKB", "VAKIFK", "ZIRAATK", "EMLAK",
  "EXIM", "AKTIF", "PASHA", "HSBC", "ANADOLU", "ALNTF", "GARAN",
] as const;

export interface WorkflowRun {
  id: number;
  name: string;
  workflowFile: string;
  status: string | null; // queued | in_progress | completed
  conclusion: string | null; // success | failure | cancelled | …
  event: string;
  createdAt: string;
  updatedAt: string;
  url: string;
}

export class GitHubNotConfigured extends Error {
  constructor() {
    super("GITHUB_DISPATCH_TOKEN not set");
    this.name = "GitHubNotConfigured";
  }
}

async function token(): Promise<string> {
  const t = (await getEnv()).GITHUB_DISPATCH_TOKEN;
  if (!t) throw new GitHubNotConfigured();
  return t;
}

function ghHeaders(t: string): Record<string, string> {
  return {
    Authorization: `Bearer ${t}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "bddk-admin-panel",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

interface RawRun {
  id: number;
  name: string;
  path?: string;
  status: string | null;
  conclusion: string | null;
  event: string;
  created_at: string;
  run_started_at?: string;
  updated_at: string;
  html_url: string;
}

export async function listRuns(perPage = 25): Promise<WorkflowRun[]> {
  const res = await fetch(`${API}/repos/${REPO}/actions/runs?per_page=${perPage}`, {
    headers: ghHeaders(await token()),
  });
  if (!res.ok) {
    throw new Error(`GitHub API ${res.status}: ${(await res.text().catch(() => "")).slice(0, 200)}`);
  }
  const data = (await res.json()) as { workflow_runs?: RawRun[] };
  return (data.workflow_runs ?? []).map((r) => ({
    id: r.id,
    name: r.name,
    workflowFile: (r.path ?? "").split("/").pop() ?? "",
    status: r.status,
    conclusion: r.conclusion,
    event: r.event,
    createdAt: r.run_started_at ?? r.created_at,
    updatedAt: r.updated_at,
    url: r.html_url,
  }));
}

export async function dispatchWorkflow(
  file: string,
  opts: { ref?: string; inputs?: Record<string, string> } = {},
): Promise<void> {
  if (!ALLOWED.has(file)) throw new Error(`workflow not allowed: ${file}`);
  const { ref = "master", inputs } = opts;
  const body = inputs && Object.keys(inputs).length ? { ref, inputs } : { ref };
  const res = await fetch(`${API}/repos/${REPO}/actions/workflows/${file}/dispatches`, {
    method: "POST",
    headers: { ...ghHeaders(await token()), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status !== 204) {
    throw new Error(
      `dispatch failed ${res.status}: ${(await res.text().catch(() => "")).slice(0, 300)}`,
    );
  }
}
