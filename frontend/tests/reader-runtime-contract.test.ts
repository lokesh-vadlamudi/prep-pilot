// @vitest-environment node
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import viteConfig from "../vite.config";

const readerStyles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

describe("reader development runtime contracts", () => {
  it("keeps the browser-visible authority through the local API proxy", () => {
    const config = typeof viteConfig === "function"
      ? viteConfig({ command: "serve", mode: "test", isSsrBuild: false, isPreview: false })
      : viteConfig;
    expect(config.server?.proxy?.["/api"]).toEqual(expect.objectContaining({
      target: "http://127.0.0.1:8899",
      changeOrigin: false,
    }));
  });

  it("fills the site with a dev-banner-safe reader overlay and resets chat geometry in the mobile stack", () => {
    expect(readerStyles).toMatch(/\.main > \.book-workspace\s*\{[^}]*animation:\s*none;/s);
    expect(readerStyles).toMatch(/\.book-workspace\s*\{[^}]*position:\s*fixed;[^}]*z-index:\s*90;[^}]*inset:\s*0;[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*var\(--book-chat-width,\s*420px\);[^}]*height:\s*100vh;[^}]*overflow-y:\s*auto;/s);
    expect(readerStyles).toMatch(/\.environment-dev \.book-workspace\s*\{[^}]*top:\s*34px;[^}]*height:\s*calc\(100vh - 34px\);[^}]*max-height:\s*calc\(100vh - 34px\);/s);
    expect(readerStyles).toMatch(/\.book-chat\s*\{[^}]*position:\s*sticky;[^}]*align-self:\s*start;[^}]*top:\s*0;[^}]*height:\s*100vh;[^}]*max-height:\s*100vh;[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/s);
    expect(readerStyles).toMatch(/\.environment-dev \.book-chat\s*\{[^}]*top:\s*0;[^}]*height:\s*calc\(100vh - 34px\);[^}]*max-height:\s*calc\(100vh - 34px\);/s);
    expect(readerStyles).toMatch(/\.chat-scroll\s*\{[^}]*flex:\s*1;[^}]*overflow-y:\s*auto;[^}]*min-height:\s*0;/s);
    expect(readerStyles).toMatch(/@media \(max-width: 900px\)[\s\S]*\.book-chat\s*\{[^}]*position:\s*static;[^}]*align-self:\s*stretch;[^}]*top:\s*auto;[^}]*height:\s*auto;[^}]*max-height:\s*none;[^}]*min-height:\s*360px;[^}]*overflow:\s*visible;/s);
  });
});
