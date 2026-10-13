import test from "node:test";
import assert from "node:assert/strict";
import {
  metric,
  assertionResult,
  runStatus,
  matches,
  evaluationPath,
  type Evaluation,
} from "./data.ts";
const run: Evaluation = {
  agent: "planning",
  run: "2026-run",
  mode: "scripted",
  set: "development",
  summary: {
    identity: { model: "fixture" },
    attempts: 2,
    clean_attempts: 2,
    task_failures: 0,
  },
};
test("report absence and missing counts are unknown, not clean", () => {
  assert.equal(
    runStatus({ ...run, summary: { identity: {}, report: "missing" } }),
    "Incomplete",
  );
  assert.equal(
    runStatus({
      ...run,
      summary: { identity: {}, attempts: 2, clean_attempts: 2 },
    }),
    "Incomplete",
  );
  assert.equal(runStatus(run), "Clean");
  assert.equal(
    runStatus({ ...run, command: { exit_code: 1 } }),
    "Needs attention",
  );
});
test("measured zero is retained while absent telemetry is unknown", () => {
  assert.equal(metric(run.summary, "observed_input_tokens"), undefined);
  assert.equal(
    metric(
      { ...run.summary, efficiency_mean: { observed_input_tokens: 0 } },
      "observed_input_tokens",
    )?.value,
    0,
  );
});
test("filters combine and search model identity", () => {
  assert.equal(matches(run, "FIXTURE", "planning", "scripted", "Clean"), true);
  assert.equal(matches(run, "", "authoring", "", ""), false);
  assert.equal(matches(run, "", "", "live", ""), false);
});
test("run links encode data as segments", () => {
  assert.equal(
    evaluationPath({ agent: "a/b", run: "<script>" }),
    "/evaluations/a%2Fb/%3Cscript%3E",
  );
});

test("zero or absent assertion observations never imply a pass", () => {
  assert.deepEqual(assertionResult({ passed: 0, total: 0 }), {
    label: "Unavailable",
    tone: "neutral",
  });
  assert.equal(assertionResult({}).label, "Unavailable");
  assert.equal(assertionResult({ passed: 1, total: 0 }).tone, "neutral");
  assert.equal(assertionResult({ passed: 0, total: 2 }).tone, "warning");
  assert.equal(assertionResult({ passed: 2, total: 2 }).tone, "success");
});
