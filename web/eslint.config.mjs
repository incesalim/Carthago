import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

// eslint-config-next ships legacy (eslintrc) shareable configs, so bridge them
// into flat config via FlatCompat. The previous `import …/core-web-vitals`
// spread didn't resolve (ERR_MODULE_NOT_FOUND) and silently disabled linting.
const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [".next/**", "out/**", "build/**", ".open-next/**", "next-env.d.ts"],
  },
];

export default eslintConfig;
