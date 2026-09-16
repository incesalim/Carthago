import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Why this config exists: the mobile-compatibility suite imports the real
// negotiate() from ../../mobile/src/api, whose tsconfig extends
// expo/tsconfig.base — resolvable only when mobile/node_modules is installed.
// The web CI job installs web dependencies only, so esbuild's per-file
// tsconfig discovery fails on that cross-package file ("Tsconfig not found").
// tsconfigRaw pins the transform options for every file instead; the values
// mirror web/tsconfig.json, which is what files under web/ were discovering
// anyway. The alias keeps the "@/..." imports explicit for the same reason —
// no dependence on implicit tsconfig-path behaviour.
export default defineConfig({
  esbuild: {
    tsconfigRaw: {
      compilerOptions: {
        target: "ES2017",
        jsx: "react-jsx",
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
});
