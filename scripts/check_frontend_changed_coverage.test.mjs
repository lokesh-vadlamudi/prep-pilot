import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";

const checker = resolve(dirname(realpathSync(process.argv[1])), "check_frontend_changed_coverage.mjs");

function git(root, ...args) {
  execFileSync("git", args, { cwd: root, stdio: "ignore" });
}

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "frontend coverage gate "));
  mkdirSync(join(root, "src"));
  const source = join(root, "src", "flight plan.ts");
  const lines = Array.from({ length: 20 }, (_, index) => `export const value${index + 1} = ${index + 1};`);
  writeFileSync(source, `${lines.join("\n")}\n`);
  git(root, "init", "-q");
  git(root, "config", "user.email", "coverage@example.invalid");
  git(root, "config", "user.name", "Coverage Gate");
  git(root, "add", ".");
  git(root, "commit", "-qm", "baseline");
  lines[0] = "export const value1 = 101;";
  writeFileSync(source, `${lines.join("\n")}\n`);
  return { root, source, coverage: join(root, "coverage-final.json") };
}

function coverageFor(source, covered, changedCovered = true) {
  const statementMap = {};
  const fnMap = {};
  const branchMap = {};
  const s = {};
  const f = {};
  const b = {};
  for (let index = 0; index < 20; index += 1) {
    const line = index + 1;
    const location = { start: { line, column: 0 }, end: { line, column: 30 } };
    const count = index < covered && (line !== 1 || changedCovered) ? 1 : 0;
    statementMap[index] = location;
    fnMap[index] = { name: `value${line}`, decl: location, loc: location, line };
    branchMap[index] = { line, type: "if", locations: [location] };
    s[index] = count;
    f[index] = count;
    b[index] = [count];
  }
  return { [source]: { path: source, statementMap, fnMap, branchMap, s, f, b } };
}

function run(root, coverage) {
  return spawnSync(process.execPath, [
    checker, "--root", root, "--base", "HEAD", "--coverage", coverage,
  ], { cwd: root, encoding: "utf8" });
}

test("fails closed when the coverage report is missing", () => {
  const { root, coverage } = fixture();
  const result = run(root, coverage);
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, /coverage file.*missing/i);
});

test("fails closed when a touched module is absent from coverage", () => {
  const { root, coverage } = fixture();
  writeFileSync(coverage, "{}");
  const result = run(root, coverage);
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, /flight plan\.ts.*missing coverage/i);
});

test("fails closed when a module metric is absent", () => {
  const { root, source, coverage } = fixture();
  const report = coverageFor(source, 20);
  delete report[source].f;
  writeFileSync(coverage, JSON.stringify(report));
  const result = run(root, coverage);
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, /missing functions coverage data/i);
});

test("fails a touched module below 95 percent", () => {
  const { root, source, coverage } = fixture();
  writeFileSync(coverage, JSON.stringify(coverageFor(source, 18)));
  const result = run(root, coverage);
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, /below 95.*flight plan\.ts.*90\.00/is);
});

test("fails changed executable lines below 95 percent", () => {
  const { root, source, coverage } = fixture();
  writeFileSync(coverage, JSON.stringify(coverageFor(source, 20, false)));
  const result = run(root, coverage);
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, /changed executable lines.*0\.00/i);
});

test("passes exact 95 percent with a filename containing spaces", () => {
  const { root, source, coverage } = fixture();
  writeFileSync(coverage, JSON.stringify(coverageFor(source, 19)));
  const result = run(root, coverage);
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
  assert.match(result.stdout, /src\/flight plan\.ts/);
  assert.match(result.stdout, /95\.00/);
  assert.match(result.stdout, /changed executable lines 100\.00/);
});
