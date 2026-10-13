export interface Summary {
  identity: Record<string, unknown>;
  report?: string;
  attempts?: number;
  clean_attempts?: number;
  task_failures?: number;
  assertions?: Record<string, { passed: number; total: number }>;
  cases?: Record<
    string,
    {
      attempts?: number;
      clean?: number;
      failed_assertions?: Record<string, number>;
      task_failure_count?: number;
    }
  >;
  efficiency_samples?: Record<string, { observed: number; attempts: number }>;
  efficiency_mean?: Record<string, number>;
}
export interface Evaluation {
  agent: string;
  run: string;
  set: string;
  mode: string;
  command?: {
    git_commit?: string;
    git_dirty?: boolean;
    started?: string;
    ended?: string;
    exit_code?: number;
    suite_note?: string;
  };
  summary: Summary;
}
export interface EvaluationList {
  runs: Evaluation[];
  warnings: string[];
}
export interface RuntimeRow {
  id: string;
  language: string;
  runtime: { name: string; version: string };
  tools: Record<string, string>;
  base_image: string;
  image_source: string;
  qualification: {
    evidence: string;
    note: string;
    report: string;
    records: string[];
  };
  frameworks?: {
    name: string;
    versions: string;
    qualification: { evidence: string };
  }[];
}
export interface RuntimeData {
  rows: RuntimeRow[];
  limitations: string[];
}
export type RunStatus = "Clean" | "Needs attention" | "Incomplete";
export function runStatus(run: Evaluation): RunStatus {
  if (run.command?.exit_code != null && run.command.exit_code !== 0)
    return "Needs attention";
  const s = run.summary;
  if (
    s.report === "missing" ||
    !s.attempts ||
    s.clean_attempts == null ||
    s.task_failures == null
  )
    return "Incomplete";
  return s.clean_attempts === s.attempts && s.task_failures === 0
    ? "Clean"
    : "Needs attention";
}
export function matches(
  run: Evaluation,
  query: string,
  agent: string,
  mode: string,
  status: string,
) {
  return (
    (!agent || run.agent === agent) &&
    (!mode || run.mode === mode) &&
    (!status || runStatus(run) === status) &&
    [
      run.agent,
      run.run,
      run.set,
      run.mode,
      JSON.stringify(run.summary.identity),
    ]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase())
  );
}
export function metric(summary: Summary, ...keys: string[]) {
  for (const key of keys) {
    const value = summary.efficiency_mean?.[key];
    if (typeof value === "number" && Number.isFinite(value))
      return { key, value, coverage: summary.efficiency_samples?.[key] };
  }
  return undefined;
}
export function evaluationPath(run: Pick<Evaluation, "agent" | "run">) {
  return `/evaluations/${encodeURIComponent(run.agent)}/${encodeURIComponent(run.run)}`;
}
export function displayIdentity(value: unknown): string {
  return value == null
    ? "Unavailable"
    : typeof value === "string"
      ? value
      : JSON.stringify(value);
}

export function assertionResult(value: { passed?: number; total?: number }): {
  label: string;
  tone: string;
} {
  if (
    value.total == null ||
    value.total <= 0 ||
    value.passed == null ||
    value.passed < 0 ||
    value.passed > value.total
  )
    return { label: "Unavailable", tone: "neutral" };
  return {
    label: `${value.passed}/${value.total}`,
    tone: value.passed === value.total ? "success" : "warning",
  };
}
