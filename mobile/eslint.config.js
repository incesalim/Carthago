// Flat config. `eslint-config-expo` carries the React / React Native / import
// and @typescript-eslint rules that match the Metro bundler's resolution, so
// the base is taken as-is rather than re-declaring rules whose plugins it
// already registers (a rule added in a config object that does not itself
// declare the plugin is a hard ESLint error, not a warning).
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", ".expo/*", "node_modules/*", "expo-env.d.ts"],
  },
]);
