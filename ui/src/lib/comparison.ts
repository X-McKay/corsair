import type { Evaluation, Summary } from "./data.ts";

/** Descriptive comparisons of retained summaries, never paired-attempt inference. */
export function fraction(
  passed: number | undefined,
  total: number | undefined,
): number | null {
  return typeof passed === "number" &&
    typeof total === "number" &&
    Number.isFinite(passed) &&
    Number.isFinite(total) &&
    Number.isInteger(passed) &&
    Number.isInteger(total) &&
    total > 0 &&
    passed >= 0 &&
    passed <= total
    ? passed / total
    : null;
}
export function completion(summary: Summary): number | null {
  if (summary.report === "missing") return null;
  const failures = summary.task_failures,
    attempts = summary.attempts;
  if (typeof failures !== "number" || typeof attempts !== "number") return null;
  return fraction(attempts - failures, attempts);
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`)
      .join(",")}}`;
  return JSON.stringify(value) ?? "undefined";
}
export function identityDifferences(
  baseline: Evaluation,
  candidate: Evaluation,
) {
  const a = baseline.summary.identity,
    b = candidate.summary.identity;
  return [...new Set([...Object.keys(a), ...Object.keys(b)])]
    .sort()
    .filter((key) => canonical(a[key]) !== canonical(b[key]))
    .map((key) => ({ key, before: a[key], after: b[key] }));
}
export function comparisonBlockers(
  baseline: Evaluation,
  candidate: Evaluation,
): string[] {
  const blockers: string[] = [];
  if (baseline.agent === candidate.agent && baseline.run === candidate.run)
    blockers.push("Choose two different runs.");
  for (const [key, label] of [
    ["agent", "agent"],
    ["set", "case set"],
    ["mode", "provider mode"],
  ] as const) {
    if (!baseline[key] || !candidate[key])
      blockers.push(`The ${label} is missing from one or both runs.`);
    else if (baseline[key] !== candidate[key])
      blockers.push(`The runs use different ${label}s.`);
  }
  for (const run of [baseline, candidate]) {
    if (!["scripted", "live"].includes(run.mode)) {
      blockers.push(
        "A provider mode is unknown or unsupported; equal labels do not establish equivalent execution.",
      );
      break;
    }
  }
  // Native suite modes describe execution (for example scripted_fixture or
  // direct_local_provider). They are a separate dimension from the wrapper's
  // scripted/live provider mode and must never be compared to that label.
  const beforeExecution = baseline.summary.identity.mode;
  const afterExecution = candidate.summary.identity.mode;
  if (
    typeof beforeExecution === "string" &&
    beforeExecution.trim() &&
    typeof afterExecution === "string" &&
    afterExecution.trim() &&
    beforeExecution !== afterExecution
  )
    blockers.push("The runs have different recorded suite execution modes.");
  const a = baseline.summary.identity.dataset_sha256,
    b = candidate.summary.identity.dataset_sha256;
  if (typeof a !== "string" || !a.trim() || typeof b !== "string" || !b.trim())
    blockers.push(
      "A dataset digest is missing; matching case names cannot establish the same frozen dataset.",
    );
  else if (a !== b)
    blockers.push(
      "The frozen dataset changed. Outcome deltas would compare different inputs.",
    );
  if (
    baseline.summary.report === "missing" ||
    candidate.summary.report === "missing"
  )
    blockers.push(
      "A run has no retained report; its outcome and telemetry are unknown.",
    );
  return blockers;
}
export interface CaseComparison {
  name: string;
  before: number | null;
  after: number | null;
  delta: number | null;
  beforeCount: string;
  afterCount: string;
  change: "Improved" | "Regressed" | "Unchanged" | "Unknown";
}
function count(
  clean: number | undefined,
  attempts: number | undefined,
): string {
  return fraction(clean, attempts) === null
    ? "Unavailable"
    : `${clean}/${attempts}`;
}
export function compareCases(
  baseline: Evaluation,
  candidate: Evaluation,
): CaseComparison[] {
  const blocked = comparisonBlockers(baseline, candidate).length > 0;
  const a =
      baseline.summary.report === "missing"
        ? {}
        : (baseline.summary.cases ?? {}),
    b =
      candidate.summary.report === "missing"
        ? {}
        : (candidate.summary.cases ?? {});
  return [...new Set([...Object.keys(a), ...Object.keys(b)])]
    .sort()
    .map((name) => {
      const before = fraction(a[name]?.clean, a[name]?.attempts),
        after = fraction(b[name]?.clean, b[name]?.attempts);
      const delta =
        !blocked && before !== null && after !== null ? after - before : null;
      return {
        name,
        before,
        after,
        delta,
        beforeCount: count(a[name]?.clean, a[name]?.attempts),
        afterCount: count(b[name]?.clean, b[name]?.attempts),
        change:
          delta === null
            ? "Unknown"
            : Math.abs(delta) < 1e-12
              ? "Unchanged"
              : delta > 0
                ? "Improved"
                : "Regressed",
      };
    });
}
export function meanDifference(
  baseline: Summary,
  candidate: Summary,
  key: string,
): number | null {
  if (baseline.report === "missing" || candidate.report === "missing")
    return null;
  const a = baseline.efficiency_mean?.[key],
    b = candidate.efficiency_mean?.[key];
  return typeof a === "number" &&
    typeof b === "number" &&
    Number.isFinite(a) &&
    Number.isFinite(b)
    ? b - a
    : null;
}
