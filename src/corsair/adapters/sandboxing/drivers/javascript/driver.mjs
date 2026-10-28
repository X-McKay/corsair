#!/usr/bin/env node
// Trusted in-image driver for the JavaScript prototype-pollution recipe.
//
// Like driver.py, this program is intentionally not an agent tool. It receives an
// operator-created, JSON-only job, writes a fixed `node:test` test, runs it under the
// Node test runner with the JUnit reporter and V8 line coverage (NODE_V8_COVERAGE), and
// emits exactly one strict JSON record on stdout. Target stdout/stderr are discarded;
// the driver never prints target return values, the model payload, or the covered file
// content.
//
// Threat limit: the target is arbitrary CommonJS running in a constrained container.
// The record is evidence of the fixed driver assertion under that isolation boundary,
// not a proof against a hostile interpreter/kernel/daemon or a build dependency.
"use strict";

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

// JUnit is parsed with a tiny tolerant reader below; no XML dependency is added.

const JOB_PATH = "/input/job.json";
const WORK = "/work";
const JUNIT = path.join(WORK, "junit.xml");
const COVERAGE_DIR = path.join(WORK, "cov");
const OBSERVATION = path.join(WORK, "observation.json");
const TEST = path.join(WORK, "test_recipe.mjs");
// The container's own cgroup v2 CPU accounting (Docker's private cgroup namespace).
const CPU_STAT = "/sys/fs/cgroup/cpu.stat";

// The fixed test the driver writes. It reads the same job JSON, binds the recipe
// callable (loadTarget), invokes it with the operator-fixed arguments plus the model payload as the final
// positional argument, and asserts that invoking it added no enumerable property to
// Object.prototype. `JSON.parse` keeps a `__proto__` payload key as an own property, so
// a vulnerable merge pollutes the prototype and the adversarial assertion fails.
const TEST_SOURCE = String.raw`
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const JOB = JSON.parse(fs.readFileSync("/input/job.json", "utf8"));

function modulePath() {
  const raw = JOB.recipe.module_file;
  const parts = raw.split("/");
  if (path.posix.isAbsolute(raw) || parts.includes("..") || parts.includes(".")) {
    throw new Error("invalid trusted recipe module path");
  }
  return path.join("/source", ...parts);
}

// The callable, by one code-owned rule (contracts/recipes/javascript.py): the exact
// marker "module.exports" binds the module export itself; any other value is the name
// of an export property ("default" binds require(module_file).default). Nothing is
// bound by a function's .name; a non-function is the callable-not-found error below.
function loadTarget() {
  const mod = require(modulePath());
  const name = JOB.recipe.function;
  const fn = name === "module.exports" ? mod : mod && mod[name];
  if (typeof fn !== "function") {
    throw new Error("recipe function is absent or not callable");
  }
  return fn;
}

// A clean Object.prototype has no enumerable properties, so a for-in over a fresh
// object yields nothing. Any enumerable property reachable this way is pollution.
function prototypePolluted() {
  const marker = {};
  for (const key in marker) {
    if (key !== undefined) return true;
  }
  return false;
}

function writeObservation(kind) {
  fs.writeFileSync("/work/observation.json", JSON.stringify({ kind }));
}

function invoke() {
  const fn = loadTarget();
  const args = JOB.recipe.fixed_arguments.slice();
  args.push(JOB.payload);
  return fn(...args);
}

test("operator_owned_recipe_assertions", () => {
  if (JOB.role === "control") {
    invoke();
    const bad = prototypePolluted();
    writeObservation(bad ? "invalid_control" : "held");
    assert.strictEqual(bad, false, "control input polluted Object.prototype");
    return;
  }
  invoke();
  const polluted = prototypePolluted();
  // "disclosure" is the kernel's positive-observation marker reused here for the
  // observed insecure condition (prototype pollution); see verification._validate_raw.
  writeObservation(polluted ? "disclosure" : "held");
  assert.strictEqual(polluted, false, "adversarial input polluted Object.prototype");
});
`;

function emit(record) {
  process.stdout.write(JSON.stringify(record) + "\n");
}

function safeJob(value) {
  const required = [
    "schema_version",
    "operation_id",
    "role",
    "source_digest",
    "submission_digest",
    "recipe",
    "payload",
  ].sort();
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("job must be an object");
  }
  const keys = Object.keys(value).sort();
  if (keys.length !== required.length || !keys.every((k, i) => k === required[i])) {
    throw new Error("job has an unsupported schema");
  }
  if (value.schema_version !== "corsair.driver-job/1") {
    throw new Error("job has an unsupported schema");
  }
  if (value.role !== "control" && value.role !== "adversarial") {
    throw new Error("unsupported role");
  }
  if (value.recipe === null || typeof value.recipe !== "object") {
    throw new Error("recipe must be an object");
  }
  return value;
}

// Tolerant, dependency-free JUnit reader: the Node junit reporter emits one
// <testsuites> with a single <testcase> that carries a child <failure>/<error>/<skipped>
// for a non-passing test. Mirror driver.py::_junit_status exactly.
function junitStatus(exitCode) {
  let xml;
  try {
    xml = fs.readFileSync(JUNIT, "utf8");
  } catch {
    return ["MISSING", { tests: 0, failures: 0, errors: 0, skipped: 0 }];
  }
  const cases = xml.match(/<testcase\b[\s\S]*?(\/>|<\/testcase>)/g) || [];
  if (cases.length !== 1) {
    return ["INVALID", { tests: cases.length, failures: 0, errors: 0, skipped: 0 }];
  }
  const body = cases[0];
  const count = (tag) => (body.match(new RegExp("<" + tag + "\\b", "g")) || []).length;
  const failures = count("failure");
  const errors = count("error");
  const skipped = count("skipped");
  const counts = { tests: 1, failures, errors, skipped };
  if (exitCode === 0 && !failures && !errors && !skipped) return ["PASS", counts];
  if (exitCode !== 0 && failures === 1 && !errors && !skipped) return ["FAILURE", counts];
  if (exitCode !== 0 && errors === 1 && !failures && !skipped) return ["ERROR", counts];
  return ["INVALID", counts];
}

// Map V8 coverage ranges to executed physical line numbers of the target module.
// Inner ranges (smaller span) override outer ones, so a count==0 branch suppresses its
// lines even inside a covered function. No network, no dependency.
function coverageLines(moduleFile) {
  let source;
  const targetPath = path.join("/source", ...moduleFile.split("/"));
  try {
    source = fs.readFileSync(targetPath, "utf8");
  } catch {
    return [];
  }
  let script;
  try {
    for (const name of fs.readdirSync(COVERAGE_DIR)) {
      const doc = JSON.parse(fs.readFileSync(path.join(COVERAGE_DIR, name), "utf8"));
      for (const entry of doc.result || []) {
        if (typeof entry.url === "string" && entry.url.endsWith(moduleFile)) {
          script = entry;
        }
      }
    }
  } catch {
    return [];
  }
  if (!script) return [];
  const len = source.length;
  const counts = new Array(len).fill(undefined);
  const ranges = [];
  for (const fn of script.functions || []) {
    for (const r of fn.ranges || []) ranges.push(r);
  }
  ranges.sort((a, b) => b.endOffset - b.startOffset - (a.endOffset - a.startOffset));
  for (const r of ranges) {
    for (let i = r.startOffset; i < r.endOffset && i < len; i++) counts[i] = r.count;
  }
  // Precompute the 1-based line of each character offset.
  const lineOf = new Array(len + 1).fill(1);
  let line = 1;
  for (let i = 0; i < len; i++) {
    lineOf[i] = line;
    if (source[i] === "\n") line += 1;
  }
  lineOf[len] = line;
  const lines = new Set();
  for (let i = 0; i < len; i++) {
    if (typeof counts[i] === "number" && counts[i] > 0) lines.add(lineOf[i]);
  }
  return [...lines].sort((a, b) => a - b);
}

// The cgroup v2 `usage_usec` CPU total, or null when the file or field is absent.
function cgroupCpuUsec() {
  let text;
  try {
    text = fs.readFileSync(CPU_STAT, "ascii");
  } catch {
    return null;
  }
  for (const line of text.split("\n")) {
    const [key, value] = line.split(" ");
    if (key === "usage_usec") return /^[0-9]+$/.test(value || "") ? Number(value) : null;
  }
  return null;
}

function main() {
  let job;
  try {
    job = safeJob(JSON.parse(fs.readFileSync(JOB_PATH, "utf8")));
  } catch {
    // No secret-bearing input is present, but do not reflect a possibly tainted value.
    emit({ schema_version: "corsair.driver/1", driver_error: "invalid job" });
    return 2;
  }

  fs.mkdirSync(WORK, { recursive: true });
  fs.mkdirSync(COVERAGE_DIR, { recursive: true });
  fs.writeFileSync(TEST, TEST_SOURCE, "utf8");

  // The fixed, complete child environment. NODE_V8_COVERAGE is set only for the child
  // test process, not for this driver; DockerSandbox owns the wall-clock deadline.
  const childEnv = {
    PATH: process.env.PATH || "",
    HOME: "/tmp",
    NODE_V8_COVERAGE: COVERAGE_DIR,
  };
  const started = process.hrtime.bigint();
  const result = spawnSync(
    process.execPath,
    [
      "--test",
      "--test-reporter=junit",
      "--test-reporter-destination=" + JUNIT,
      TEST,
    ],
    {
      cwd: WORK,
      env: childEnv,
      stdio: ["ignore", "ignore", "ignore"],
    },
  );
  const exitCode = typeof result.status === "number" ? result.status : 2;
  const wallUsec = Number((process.hrtime.bigint() - started) / 1000n);

  const [status0, junit] = junitStatus(exitCode);
  let status = status0;
  let observed = null;
  try {
    observed = JSON.parse(fs.readFileSync(OBSERVATION, "utf8")).kind;
  } catch {
    observed = null;
  }

  let outcome;
  if (status === "PASS" && observed === "held") {
    outcome = "PROPERTY_HELD";
  } else if (status === "FAILURE" && observed === "disclosure" && job.role === "adversarial") {
    outcome = "VIOLATION";
  } else if (status === "FAILURE" && observed === "invalid_control") {
    outcome = "INVALID";
    status = "INVALID";
  } else {
    outcome = "ERROR";
    status = "ERROR";
  }

  const moduleFile = (job.recipe && job.recipe.module_file) || "";
  const record = {
    schema_version: "corsair.driver/1",
    operation_id: job.operation_id,
    role: job.role,
    source_digest: job.source_digest,
    submission_digest: job.submission_digest,
    native_exit_code: exitCode,
    junit: { status, ...junit },
    outcome,
    observation_kind: observed,
    target_executed: ["held", "disclosure", "invalid_control"].includes(observed),
    covered_lines: coverageLines(moduleFile),
    coverage_file: moduleFile,
  };
  // Efficiency telemetry only: the verifier never admits an outcome from it.
  record.wall_usec = wallUsec;
  const cpuUsec = cgroupCpuUsec();
  if (cpuUsec !== null) record.cpu_usec = cpuUsec;
  emit(record);
  // Deliberately the child's native status, not a boolean success inversion.
  return exitCode;
}

process.exit(main());
