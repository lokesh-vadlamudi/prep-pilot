#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";

const THRESHOLD = 95;

class GateError extends Error {}

function argumentsFor(argv) {
  const options = {
    root: process.cwd(),
    base: process.env.FRONTEND_COVERAGE_BASE || "HEAD",
    coverage: "coverage/coverage-final.json",
  };
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index]?.replace(/^--/, "");
    const value = argv[index + 1];
    if (!name || !(name in options) || value === undefined) {
      throw new GateError(`Unknown or incomplete option: ${argv[index] ?? "<missing>"}`);
    }
    options[name] = value;
  }
  options.root = realpathSync(resolve(options.root));
  options.coverage = isAbsolute(options.coverage)
    ? options.coverage : resolve(options.root, options.coverage);
  return options;
}

function git(root, args, encoding = "utf8") {
  try {
    return execFileSync("git", args, { cwd: root, encoding });
  } catch (error) {
    const detail = error.stderr?.toString().trim() || error.message;
    throw new GateError(`Git inspection failed: ${detail}`);
  }
}

function nulNames(value) {
  return value.toString().split("\0").filter(Boolean);
}

function productionSource(file) {
  const normalized = file.split(sep).join("/");
  return /^src\/.+\.tsx?$/.test(normalized)
    && !/\.(?:test|spec)\.tsx?$/.test(normalized)
    && !normalized.startsWith("src/test/")
    && !normalized.endsWith(".d.ts");
}

function repositoryContext(frontendRoot) {
  const repositoryRoot = git(frontendRoot, ["rev-parse", "--show-toplevel"]).trim();
  const prefix = relative(repositoryRoot, frontendRoot).split(sep).join("/");
  return { repositoryRoot, prefix, sourcePath: prefix ? `${prefix}/src` : "src" };
}

function changedLineNumbers(repositoryRoot, base, repositoryFile) {
  const patch = git(repositoryRoot, [
    "diff", "--unified=0", "--no-color", base, "--", repositoryFile,
  ]);
  const lines = new Set();
  for (const text of patch.split("\n")) {
    const match = text.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/);
    if (!match) continue;
    const start = Number(match[1]);
    const count = match[2] === undefined ? 1 : Number(match[2]);
    for (let line = start; line < start + count; line += 1) lines.add(line);
  }
  return lines;
}

function allFileLines(path) {
  const source = readFileSync(path, "utf8");
  const count = source === "" ? 0 : source.split(/\r?\n/).length - (source.endsWith("\n") ? 1 : 0);
  return new Set(Array.from({ length: count }, (_, index) => index + 1));
}

function touchedProductionFiles(frontendRoot, base) {
  const context = repositoryContext(frontendRoot);
  const tracked = nulNames(git(context.repositoryRoot, [
    "diff", "--name-only", "-z", "--diff-filter=ACMR", base, "--", context.sourcePath,
  ], "buffer"));
  const untracked = new Set(nulNames(git(context.repositoryRoot, [
    "ls-files", "--others", "--exclude-standard", "-z", "--", context.sourcePath,
  ], "buffer")));
  return [...new Set([...tracked, ...untracked])].map((repositoryFile) => {
    const absolute = resolve(context.repositoryRoot, repositoryFile);
    const file = relative(frontendRoot, absolute);
    const changed = untracked.has(repositoryFile)
      ? allFileLines(absolute)
      : changedLineNumbers(context.repositoryRoot, base, repositoryFile);
    return { absolute, file, changed };
  }).filter(({ absolute, file }) => existsSync(absolute) && productionSource(file));
}

function coverageEntries(report, frontendRoot) {
  const entries = new Map();
  for (const [key, value] of Object.entries(report)) {
    const declared = value?.path || key;
    const candidate = resolve(isAbsolute(declared) ? declared : resolve(frontendRoot, declared));
    const absolute = existsSync(candidate) ? realpathSync(candidate) : candidate;
    entries.set(absolute, value);
  }
  return entries;
}

function requireObject(value, label, file) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new GateError(`${file}: missing ${label} coverage data`);
  }
  return value;
}

function metric(counts, label, file) {
  const values = Object.values(requireObject(counts, label, file));
  const flattened = label === "branches" ? values.flat() : values;
  if (flattened.some((count) => typeof count !== "number")) {
    throw new GateError(`${file}: invalid ${label} coverage data`);
  }
  const covered = flattened.filter((count) => count > 0).length;
  return { covered, total: flattened.length, percent: flattened.length ? covered * 100 / flattened.length : 100 };
}

function lineMetric(data, file) {
  const statementMap = requireObject(data.statementMap, "line", file);
  const statements = requireObject(data.s, "statements", file);
  const counts = new Map();
  for (const [id, location] of Object.entries(statementMap)) {
    if (!location?.start?.line || typeof statements[id] !== "number") {
      throw new GateError(`${file}: incomplete line coverage data`);
    }
    const prior = counts.get(location.start.line);
    counts.set(location.start.line, prior === undefined ? statements[id] : Math.min(prior, statements[id]));
  }
  const values = [...counts.values()];
  const covered = values.filter((count) => count > 0).length;
  return { counts, covered, total: values.length, percent: values.length ? covered * 100 / values.length : 100 };
}

function evaluate(file, data) {
  if (!data) throw new GateError(`${file.file}: missing coverage for touched production file`);
  requireObject(data.fnMap, "function map", file.file);
  requireObject(data.branchMap, "branch map", file.file);
  const lines = lineMetric(data, file.file);
  const changedCounts = [...lines.counts].filter(([line]) => file.changed.has(line)).map(([, count]) => count);
  const changedCovered = changedCounts.filter((count) => count > 0).length;
  const changed = {
    covered: changedCovered,
    total: changedCounts.length,
    percent: changedCounts.length ? changedCovered * 100 / changedCounts.length : 100,
  };
  return {
    changed,
    lines,
    statements: metric(data.s, "statements", file.file),
    functions: metric(data.f, "functions", file.file),
    branches: metric(data.b, "branches", file.file),
  };
}

function percentage(metricValue) {
  return metricValue.percent.toFixed(2);
}

function resultLine(file, metrics) {
  return `${file}: changed executable lines ${percentage(metrics.changed)}%; `
    + `lines ${percentage(metrics.lines)}%; statements ${percentage(metrics.statements)}%; `
    + `functions ${percentage(metrics.functions)}%; branches ${percentage(metrics.branches)}%`;
}

function main() {
  const options = argumentsFor(process.argv.slice(2));
  if (!existsSync(options.coverage)) {
    throw new GateError(`Coverage file is missing: ${options.coverage}`);
  }
  let report;
  try {
    report = JSON.parse(readFileSync(options.coverage, "utf8"));
  } catch (error) {
    throw new GateError(`Coverage file is invalid: ${error.message}`);
  }
  const touched = touchedProductionFiles(options.root, options.base);
  const entries = coverageEntries(report, options.root);
  if (touched.length === 0) return console.log("No touched TS/TSX production files.");
  const failures = [];
  for (const file of touched) {
    const metrics = evaluate(file, entries.get(file.absolute));
    const line = resultLine(file.file.split(sep).join("/"), metrics);
    if (Object.values(metrics).some((value) => value.percent < THRESHOLD)) failures.push(line);
    else console.log(`PASS ${line}`);
  }
  if (failures.length) {
    throw new GateError(`Touched modules below ${THRESHOLD.toFixed(2)}%:\n${failures.join("\n")}`);
  }
}

try {
  main();
} catch (error) {
  console.error(`Frontend changed-coverage gate failed: ${error.message}`);
  process.exitCode = 1;
}
