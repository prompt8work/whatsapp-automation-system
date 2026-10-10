/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    // Local dev: same-origin /api like production (where Vercel rewrites /api to the backend).
    // API_PROXY_TARGET=http://localhost:8010 npm run dev   if port 8000 is busy.
    proxy: { "/api": process.env.API_PROXY_TARGET ?? "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
