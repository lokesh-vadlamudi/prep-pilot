/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend on :8899.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5177,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8899",
        // FastAPI compares Origin with Host on mutating requests. Preserve the
        // browser-visible Vite authority instead of rewriting it to :8899.
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json"],
      reportsDirectory: "coverage",
      clean: true,
      cleanOnRerun: true,
      reportOnFailure: true,
    },
  },
});
