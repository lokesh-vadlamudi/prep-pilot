/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend on :8899.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5177,
    proxy: {
      "/api": "http://127.0.0.1:8899",
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
