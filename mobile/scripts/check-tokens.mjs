/**
 * Token-drift gate: src/theme/tokens.ts must still match web/app/globals.css.
 *
 * The palette lives in two places because React Native cannot read a CSS custom
 * property. Two copies of a colour system drift silently — a hex nudged on the
 * website is invisible here until someone opens both apps side by side, which
 * nobody does. This re-reads the CSS and fails on any divergence.
 *
 * It checks the tokens that carry MEANING (ink, surfaces, rules, the data
 * tones, the chart ramp). It deliberately does not check the tokens the phone
 * has no use for — `--popover`, `--ring`, `--input`, the heatmap ramp — because
 * a gate that fails on things the app doesn't render gets switched off.
 *
 * Run: npm run check:tokens   (wired into CI alongside lint + tsc)
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const CSS = join(here, "..", "..", "web", "app", "globals.css");
const TOKENS = join(here, "..", "src", "theme", "tokens.ts");

/** CSS custom property → the key used in tokens.ts. */
const MAP = {
  "--background": "background",
  "--card": "card",
  "--foreground": "foreground",
  "--muted-foreground": "mutedForeground",
  "--faint": "faint",
  "--muted": "muted",
  "--border": "border",
  "--hair": "hair",
  "--primary": "primary",
  "--primary-foreground": "primaryForeground",
  "--data": "data",
  "--context": "context",
  "--positive": "positive",
  "--negative": "negative",
  "--warning": "warning",
};

const CHART_KEYS = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5", "--chart-6"];

const css = readFileSync(CSS, "utf8");
const ts = readFileSync(TOKENS, "utf8");

/**
 * Pull one block's declarations. `:root` is the light theme; `.dark` overrides
 * it. Both are matched from the start of the selector to the first closing
 * brace at column 0, which is how globals.css is formatted.
 */
function block(selector) {
  const re = new RegExp(`${selector}\\s*\\{([\\s\\S]*?)\\n\\}`, "m");
  const m = re.exec(css);
  if (!m) throw new Error(`Could not find the '${selector}' block in globals.css`);
  const out = {};
  for (const line of m[1].split("\n")) {
    const d = /^\s*(--[\w-]+)\s*:\s*([^;]+);/.exec(line);
    if (d) out[d[1]] = d[2].trim();
  }
  return out;
}

/** Read one exported palette object out of tokens.ts. */
function palette(name) {
  const re = new RegExp(`export const ${name}: Palette = \\{([\\s\\S]*?)\\n\\};`, "m");
  const m = re.exec(ts);
  if (!m) throw new Error(`Could not find 'export const ${name}' in tokens.ts`);
  const out = {};
  for (const line of m[1].split("\n")) {
    const d = /^\s*(\w+)\s*:\s*"(#[0-9A-Fa-f]{3,8})"/.exec(line);
    if (d) out[d[1]] = d[2].toUpperCase();
  }
  const chart = /chart:\s*\[([^\]]+)\]/.exec(m[1]);
  out.__chart = chart
    ? [...chart[1].matchAll(/"(#[0-9A-Fa-f]{3,8})"/g)].map((c) => c[1].toUpperCase())
    : [];
  return out;
}

const problems = [];

for (const [themeName, selector, tokenName] of [
  ["light", ":root", "light"],
  ["dark", "\\.dark", "dark"],
]) {
  const declared = block(selector);
  const ported = palette(tokenName);

  for (const [cssVar, key] of Object.entries(MAP)) {
    const raw = declared[cssVar];
    if (!raw) {
      problems.push(`${themeName}: ${cssVar} is no longer declared in globals.css`);
      continue;
    }
    // `--card-foreground: var(--foreground)` and friends are indirections the
    // phone resolves by hand; only direct hexes are comparable.
    if (!raw.startsWith("#")) continue;
    const want = raw.toUpperCase();
    const got = ported[key];
    if (got !== want) {
      problems.push(`${themeName}: ${cssVar} is ${want} in globals.css but ${key} is ${got ?? "missing"} in tokens.ts`);
    }
  }

  const wantChart = CHART_KEYS.map((k) => declared[k]?.toUpperCase()).filter(Boolean);
  const gotChart = ported.__chart;
  if (wantChart.join(",") !== gotChart.join(",")) {
    problems.push(
      `${themeName}: chart ramp differs\n  globals.css: ${wantChart.join(", ")}\n  tokens.ts:   ${gotChart.join(", ")}`,
    );
  }
}

if (problems.length > 0) {
  console.error("Theme tokens have drifted from web/app/globals.css:\n");
  for (const p of problems) console.error(`  • ${p}`);
  console.error("\nUpdate mobile/src/theme/tokens.ts to match, or update globals.css.");
  process.exit(1);
}

console.log("Theme tokens match web/app/globals.css.");
