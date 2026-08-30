import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Node can expose an undefined experimental localStorage unless a backing file
// is configured. Keep this oracle inside the test harness, without CLI flags.
const stored = new Map<string, string>();
const testStorage: Storage = {
  get length() { return stored.size; },
  clear: () => stored.clear(),
  getItem: (key) => stored.get(key) ?? null,
  key: (index) => [...stored.keys()][index] ?? null,
  removeItem: (key) => { stored.delete(key); },
  setItem: (key, value) => { stored.set(key, String(value)); },
};
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: testStorage,
  writable: true,
});

afterEach(() => cleanup());
