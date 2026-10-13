import test from "node:test";
import assert from "node:assert/strict";
import type { Evaluation } from "./data.ts";
import {
  fraction,
  completion,
  comparisonBlockers,
  identityDifferences,
  compareCases,
  meanDifference,
} from "./comparison.ts";
function run(id: string, identity: Record<string, unknown> = {}): Evaluation {
  return {
    agent: "planning",
    run: id,
    set: "development",
    mode: "live",
    summary: {
      identity: { dataset_sha256: "frozen", model: "old-model", ...identity },
      attempts: 4,
      clean_attempts: 2,
      task_failures: 1,
      cases: { example: { attempts: 4, clean: 2 } },
    },
  };
}
test("intended prompt/model changes are disclosed without blocking a fixed dataset", () => {
  const a = run("baseline", {
      prompt_version: "v1",
      budget: { tokens: 10, calls: 2 },
    }),
    b = run("candidate", {
      prompt_version: "v2",
      model: "new-model",
      budget: { calls: 2, tokens: 10 },
    });
  assert.deepEqual(comparisonBlockers(a, b), []);
  assert.deepEqual(
    identityDifferences(a, b).map((d) => d.key),
    ["model", "prompt_version"],
  );
});
test("unknown and changed dataset, mode, agent, set, missing report and same run block deltas", () => {
  const a = run("a");
  for (const b of [
    run("a"),
    run("b", { dataset_sha256: undefined }),
    run("b", { dataset_sha256: "changed" }),
    { ...run("b"), mode: "scripted" },
    { ...run("b"), agent: "authoring" },
    { ...run("b"), set: "heldout" },
    {
      ...run("b"),
      summary: { identity: { dataset_sha256: "frozen" }, report: "missing" },
    },
  ]) {
    assert.ok(comparisonBlockers(a, b).length > 0);
    assert.ok(compareCases(a, b).every((c) => c.delta === null));
  }
});
test("case rates account for unequal repeats and absent cases stay unknown", () => {
  const a = run("a"),
    b = run("b");
  b.summary.cases = {
    example: { attempts: 10, clean: 5 },
    new_case: { attempts: 1, clean: 1 },
  };
  assert.equal(
    compareCases(a, b).find((c) => c.name === "example")?.change,
    "Unchanged",
  );
  assert.equal(
    compareCases(a, b).find((c) => c.name === "new_case")?.change,
    "Unknown",
  );
  b.summary.cases.example.clean = 8;
  assert.equal(
    compareCases(a, b).find((c) => c.name === "example")?.change,
    "Improved",
  );
  b.summary.cases.example.clean = 2;
  assert.equal(
    compareCases(a, b).find((c) => c.name === "example")?.change,
    "Regressed",
  );
});
test("unknown, empty and malformed outcomes are not successes; measured zero is known", () => {
  assert.equal(fraction(0, 0), null);
  assert.equal(fraction(undefined, 2), null);
  assert.equal(fraction(3, 2), null);
  assert.equal(fraction(1.5, 2), null);
  assert.equal(fraction(0, 2), 0);
  assert.equal(completion(run("a").summary), 0.75);
  assert.equal(completion({ identity: {}, attempts: 2 }), null);
  assert.equal(
    meanDifference(
      { identity: {}, efficiency_mean: { tokens: 0 } },
      { identity: {}, efficiency_mean: { tokens: 0 } },
      "tokens",
    ),
    0,
  );
  assert.equal(
    meanDifference(
      { identity: {} },
      { identity: {}, efficiency_mean: { tokens: 0 } },
      "tokens",
    ),
    null,
  );
});

test("a missing report invalidates stale counts and means", () => {
  const a = run("a"),
    b = run("b");
  b.summary.report = "missing";
  assert.equal(completion(b.summary), null);
  assert.equal(compareCases(a, b)[0].after, null);
  assert.equal(
    meanDifference(
      { ...a.summary, efficiency_mean: { tokens: 1 } },
      { ...b.summary, efficiency_mean: { tokens: 2 } },
      "tokens",
    ),
    null,
  );
});

test("unknown wrapper modes and different native execution modes cannot establish comparability", () => {
  assert.ok(
    comparisonBlockers(
      { ...run("a"), mode: "unknown" },
      { ...run("b"), mode: "unknown" },
    ).length,
  );
  assert.ok(
    comparisonBlockers(
      run("a", { mode: "direct_local_provider" }),
      run("b", { mode: "temporal_local_provider" }),
    ).length,
  );
});

test("real native suite modes remain separate from wrapper provider modes", () => {
  for (const [wrapper, native] of [
    ["scripted", "scripted_fixture"],
    ["live", "direct_local_provider"],
  ]) {
    const before = { ...run("before", { mode: native }), mode: wrapper };
    const after = {
      ...run("after", { mode: native, prompt_version: "v2" }),
      mode: wrapper,
    };
    assert.deepEqual(comparisonBlockers(before, after), []);
    assert.equal(compareCases(before, after)[0].change, "Unchanged");
  }
});
