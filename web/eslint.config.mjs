import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// eslint-config-next 16 ships native flat configs, so spread them directly.
// (Earlier we bridged the legacy eslintrc configs via FlatCompat; ESLint 10
// dropped the implicit @eslint/eslintrc dep and FlatCompat fails to validate
// the bridged config, so the native flat exports are the supported path now.)
const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [
      ".next/**",
      "out/**",
      "build/**",
      ".open-next/**",
      ".wrangler/**",
      "next-env.d.ts",
    ],
  },
];

export default eslintConfig;
