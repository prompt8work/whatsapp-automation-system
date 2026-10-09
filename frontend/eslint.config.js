// Lint + LAYER RULES for the dashboard (docs/ARCHITECTURE.md §9.2).
//
// Inside a feature:   pages -> components / api / model     components -> model
//                     api   -> model                         model      -> (nothing in the feature)
// Across features:    only through the other feature's index.ts  (no "@/features/x/...").
// shared/ never imports features/ or app/.
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const noDeepFeatureImports = {
  group: ["@/features/*/*"],
  message: "Import another feature only through its index.ts (e.g. '@/features/inbox').",
};
const noApp = { group: ["@/app", "@/app/*"], message: "Only main.tsx may import app/." };

/** Build a no-restricted-imports rule for one layer. */
const layer = (...forbidden) => [
  "error",
  {
    patterns: [
      noDeepFeatureImports,
      noApp,
      ...forbidden.map((dir) => ({
        // relative import into a sibling layer folder of the same feature: "../api/...", "../../pages"
        regex: `^\\.{1,2}/(\\.\\./)*${dir}(/|$)`,
        message: `This layer must not import from ${dir}/ (see eslint.config.js header).`,
      })),
    ],
  },
];

export default defineConfig([
  globalIgnores(["dist", "coverage", "src/shared/api/schema.d.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    plugins: { "react-hooks": reactHooks },
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  { files: ["src/features/*/pages/**"], rules: { "no-restricted-imports": layer("pages") } },
  {
    files: ["src/features/*/components/**"],
    rules: { "no-restricted-imports": layer("api", "pages") },
  },
  {
    files: ["src/features/*/api/**"],
    rules: { "no-restricted-imports": layer("components", "pages") },
  },
  {
    files: ["src/features/*/model/**"],
    rules: { "no-restricted-imports": layer("api", "components", "pages") },
  },
  {
    files: ["src/shared/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            noApp,
            { group: ["@/features", "@/features/*"], message: "shared/ must not import features/." },
          ],
        },
      ],
    },
  },
]);
