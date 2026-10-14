import test from "node:test";
import assert from "node:assert/strict";
import {
  evalStatus,
  matches,
  evaluationPath,
  attemptPath,
  rate,
  ratioLabel,
  labelTone,
  latestByAgent,
  labelCounts,
  type Evaluation,
  type Rollup,
  type RunRow,
} from "./data.ts";

const overall = (attempts: number, clean: number): Rollup => ({
  cases: attempts,
  attempts,
  clean_attempts: clean,
  task_failures: 0,
  status_unreported: 0,
  completion: null,
  dimensions: {},
  dispositions: null,
  statuses: {},
  metrics: {},
  revisions: null,
  accepted_within_limit: null,
});
const run: Evaluation = {
  agent: "reviewer",
  run: "20261014T120000Z-development-scripted",
  set: "development",
  language: null,
  mode: "scripted",
  identity: {},
  report: "present",
  overall: overall(2, 2),
  command: {
    git_commit: "a",
    git_dirty: false,
    started: null,
    ended: null,
    exit_code: 0,
    note: "after prompt change",
  },
};

test("a missing report or count is unknown, not clean", () => {
  assert.equal(evalStatus({ ...run, report: "missing", overall: null }), "Incomplete");
  assert.equal(
    evalStatus({ ...run, overall: { ...overall(2, 2), clean_attempts: null } }),
    "Incomplete",
  );
  assert.equal(evalStatus(run), "Clean");
  assert.equal(evalStatus({ ...run, overall: overall(2, 1) }), "Needs attention");
  assert.equal(
    evalStatus({ ...run, command: { ...run.command, exit_code: 1 } }),
    "Needs attention",
  );
  assert.equal(
    evalStatus({ ...run, command: { ...run.command, exit_code: null } }),
    "Incomplete",
  );
});

test("filters search the note and match agent, mode and status", () => {
  assert.ok(matches(run, "prompt change", "reviewer", "scripted", "Clean"));
  assert.ok(!matches(run, "", "builder", "", ""));
  assert.ok(!matches(run, "", "", "live", ""));
});

test("rates are unknown without evaluated attempts", () => {
  assert.equal(rate({ passed: 0, total: 0 }), null);
  assert.equal(rate(null), null);
  assert.equal(rate({ passed: 1, total: 4 }), 0.25);
  assert.equal(ratioLabel({ passed: 0, total: 0 }), "Unavailable");
});

test("paths encode identifiers", () => {
  assert.equal(
    evaluationPath({ agent: "chain", run: "a b" }),
    "/evaluations/chain/a%20b",
  );
  assert.equal(attemptPath("chain", "r", "0001"), "/evaluations/chain/r/attempts/0001");
});

test("labels and latest runs", () => {
  assert.equal(labelTone("LIKELY_EXPLOITABLE"), "danger");
  assert.equal(labelTone(null), "neutral");
  const live = { ...run, mode: "live", run: "b" };
  const narrowed = { ...run, run: "c", language: "java" };
  const latest = latestByAgent([narrowed, live, run], "scripted");
  assert.equal(latest.get("reviewer")?.run, run.run);
  const row = { label: null, state: "incomplete" } as RunRow;
  assert.deepEqual(
    labelCounts([row, { ...row, label: "ERROR", state: "completed" }]),
    { incomplete: 1, ERROR: 1 },
  );
});
