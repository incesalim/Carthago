import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Only what the suite can't do without: the "@/..." alias. Vitest resolves no
// tsconfig paths itself, so any test that reaches a component whose SOURCE
// value-imports "@/..." (Vitals → @/app/lib/format-time) fails with "Cannot
// find package '@/…'" unless the alias is declared here. Everything else stays
// at defaults — deliberately no tsconfigRaw: per-file tsconfig discovery is
// fine for files under web/, and the 2026-09-16 cross-package failure was
// about ../mobile's expo-extends tsconfig, not this alias
// (docs/knowledge/2026-09-16-vitest-cross-package-tsconfig.md).
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
});
