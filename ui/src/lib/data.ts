/** Shapes of the read-only API (src/corsair/web/server.py), which projects v2 records:
 * run records `corsair-v2-run/1` and eval runs `corsair-eval-summary/v1`. Null is unknown, never zero. */

export const LABELS = [
  "LIKELY_EXPLOITABLE",
  "LIKELY_NOT_EXPLOITABLE",
  "INCONCLUSIVE",
  "UNABLE_TO_RUN",
  "ERROR",
] as const;
export const AGENTS = [
  "grounding",
  "investigator",
  "builder",
  "control_prober",
  "exploit_prober",
  "reviewer",
  "chain",
] as const;
export const METRICS = [
  "wall_s",
  "requests",
  "tool_calls",
  "input_tokens",
  "output_tokens",
  "tokens",
  "retries",
] as const;

export interface Ratio {
  passed: number;
  total: number;
}
export interface Stats {
  observed: number;
  mean: number | null;
  p50: number | null;
  p90: number | null;
  total: number | null;
}
export interface Dispositions {
  runs: number | null;
  decisive: number | null;
  decisive_rate: number | null;
  decisive_correct: number | null;
  accuracy_by_expected_label: Record<string, Ratio>;
  abstentions: Record<
    string,
    {
      count: number | null;
      rate: number | null;
      by_terminal_reason: Record<string, number>;
    }
  >;
}
export interface Rollup {
  cases: number | null;
  attempts: number | null;
  clean_attempts: number | null;
  task_failures: number | null;
  status_unreported: number | null;
  completion: {
    attempted: number | null;
    completed: number | null;
    task_failures: number | null;
    evaluator_failures: number | null;
    unknown_failures: number | null;
    rate: number | null;
  } | null;
  dimensions: Record<string, Ratio>;
  dispositions: Dispositions | null;
  statuses: Record<string, number>;
  metrics: Record<string, Stats>;
  revisions: Stats | null;
  accepted_within_limit: Ratio | null;
  parameters?: Record<string, unknown>;
}
export interface Command {
  git_commit: string | null;
  git_dirty: boolean | null;
  started: string | null;
  ended: string | null;
  exit_code: number | null;
  note: string | null;
}
export interface Evaluation {
  agent: string;
  run: string;
  set: string | null;
  language: string | null;
  mode: string | null;
  identity: Record<string, unknown>;
  report: "present" | "missing";
  overall: Rollup | null;
  policy?: string | null;
  command: Command;
}
export interface Attempt {
  case: string | null;
  language: string | null;
  kind: string | null;
  receipt: string | null;
  status: string | null;
  passed: boolean | null;
  dimensions: Record<string, boolean>;
  failed_assertions: string[];
  failed: boolean;
  failure_kind: string | null;
  wall_s: number | null;
  tokens: number | null;
  requests: number | null;
  tool_calls: number | null;
  retries: number | null;
  revisions: number | null;
  label: string | null;
  expected_label: string | null;
  terminal_reason: string | null;
  record?: boolean;
}
export interface Policy {
  status: string | null;
  deferred: boolean | null;
  in_scope: boolean | null;
  entries: Record<
    string,
    { status: string | null; value: number | null; limit: number | null }
  >;
  missing_provenance: string[];
}
export interface Reference {
  run: string;
  kind: string;
  language: string | null;
  identity: Record<string, unknown>;
  overall: Rollup | null;
  by_language: Record<string, Rollup | null>;
}
export interface EvaluationDetail extends Omit<Evaluation, "policy"> {
  by_language: Record<string, Rollup | null>;
  by_kind: Record<string, Rollup | null>;
  attempts: Attempt[];
  attempts_limited: boolean;
  policy: Policy | null;
  reference: Reference | null;
}
export interface EvaluationList {
  runs: Evaluation[];
  warnings: string[];
}
export interface Baseline {
  agent: string;
  set: string;
  mode: string;
  source: "committed" | "promoted";
  run: string;
  policy_status?: string | null;
  committed?: string | null;
  overall?: Rollup | null;
}

export interface Totals {
  agent_calls: number | null;
  requests: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tokens: number | null;
  tool_calls: number | null;
  retries: number | null;
  agent_wall_s: number | null;
  wall_s: number | null;
}
export interface RunRow {
  id: string;
  run: string;
  case: string | null;
  mode: string | null;
  label: string | null;
  rule: string | null;
  reason: string | null;
  finding: string | null;
  fix: string | null;
  sensitivity: string | null;
  state: "completed" | "cancelled" | "incomplete";
  started: string | null;
  finished: string | null;
  runtime_row: string | null;
  models: string[];
  totals: Totals;
}
export interface ProbeFacts {
  exit_code: number | null;
  exit_class: string | null;
  timed_out: boolean | null;
  start_marker: boolean | null;
  end_marker: boolean | null;
  token_in_output: boolean | null;
  check_marker: string | null;
}
export interface Probe {
  outcome: string | null;
  duration_s: number | null;
  patch_sha256: string | null;
  image_digest: string | null;
  tree_sha256: string | null;
  cleanup_confirmed: boolean | null;
  facts: ProbeFacts;
}
export interface RoleValidity {
  valid: boolean | null;
  calls_real_target: boolean | null;
  exercises_condition: boolean | null;
  assertion_relevant: boolean | null;
  doubles_only_dependencies: boolean | null;
  defects: string[];
  citations: {
    path: string | null;
    start_line: number | null;
    end_line: number | null;
  }[];
}
export interface AgentTotals {
  calls: number | null;
  requests: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tool_calls: number | null;
  retries: number | null;
  wall_s: number | null;
  models: string[];
  prompt_versions: string[];
  steps: string[];
  statuses: Record<string, number>;
}
export interface Call {
  step: string | null;
  agent: string | null;
  model: string | null;
  status: string | null;
  prompt_version: string | null;
  wall_s: number | null;
  requests: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tool_calls: number | null;
  retries: number | null;
}
export interface RunDetail extends RunRow {
  record: string;
  provenance: Record<string, unknown> & {
    environments?: Record<string, Record<string, string | null>>;
  };
  finding_detail: {
    title: string | null;
    description: string | null;
    file_path: string | null;
    symbol: string | null;
    cwe: string | null;
    start_line: number | null;
  };
  fix_reason: string | null;
  probes: Record<string, Record<string, Probe>>;
  review: {
    rounds: number | null;
    authors: Record<string, Record<string, unknown>>;
  } | null;
  attempts: {
    number: number | null;
    patch_sha256: string | null;
    exploit_outcome: string | null;
    review_rounds: number | null;
    decided: boolean | null;
    first_review_valid: Record<string, boolean>;
  }[];
  validity: {
    patch_sha256: string | null;
    revision: string | null;
    roles: Record<string, RoleValidity>;
  }[];
  agents: Record<string, AgentTotals>;
  timings: { step: string | null; wall_s: number | null; error: boolean | null }[];
  calls: Call[] | null;
  source:
    | { kind: "run" }
    | {
        kind: "eval";
        agent: string;
        eval_run: string;
        receipt: string;
        case: string | null;
        expected_label: string | null;
        passed: boolean | null;
      };
}
export interface RunList {
  runs: RunRow[];
  warnings: string[];
}

export interface RuntimeRow {
  id: string;
  language: string;
  image: string;
  base_image: string | null;
  image_source: string | null;
  framework: string;
  skill: string;
  detect: { file: string; contains: string | null }[];
  run_template: string[];
  exit_codes: Record<string, string>;
  test_dir: string;
  evidence: "canary-only" | "image-only" | "live";
  build_network_hosts: string[];
  syntax_check: string[] | null;
  note: string;
}
export interface RuntimeData {
  schema: string;
  sha256: string;
  rows: RuntimeRow[];
  limitations: string[];
}
export interface SystemData {
  checked_at: string;
  ready: boolean;
  sources: {
    id: string;
    status: "available" | "unavailable";
    detail: string;
  }[];
  services: {
    id: string;
    status: "available" | "unavailable" | "not_configured";
    detail: string;
  }[];
}
export interface WorkflowRuns {
  status: "available" | "unavailable" | "not_configured";
  detail: string;
  limited: boolean;
  runs: {
    id: string;
    run_id: string;
    workflow_type: string;
    status: string;
    started: string | null;
    ended?: string;
    record?: string;
  }[];
}

/** Agent-eval status from its own counts: a missing report or count is unknown, never clean. */
export type EvalStatus = "Clean" | "Needs attention" | "Incomplete";
export function evalStatus(run: Evaluation): EvalStatus {
  const o = run.overall;
  if (run.command.exit_code != null && run.command.exit_code !== 0)
    return "Needs attention";
  if (
    run.report === "missing" ||
    !o ||
    !o.attempts ||
    o.clean_attempts == null ||
    o.task_failures == null
  )
    return "Incomplete";
  if (o.clean_attempts !== o.attempts || o.task_failures !== 0)
    return "Needs attention";
  return run.command.exit_code === 0 ? "Clean" : "Incomplete";
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
    (!status || evalStatus(run) === status) &&
    [run.agent, run.run, run.set, run.language, run.mode, run.command.note]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase())
  );
}
/** passed/total as a fraction, or null when nothing was evaluated. */
export function rate(value: Ratio | null | undefined): number | null {
  return value && value.total > 0 ? value.passed / value.total : null;
}
export function ratioLabel(value: Ratio | null | undefined): string {
  return value && value.total > 0
    ? `${value.passed}/${value.total}`
    : "Unavailable";
}
export function ratioTone(value: Ratio | null | undefined): string {
  return !value || value.total <= 0
    ? "neutral"
    : value.passed === value.total
      ? "success"
      : "warning";
}
/** Exploitable is the finding to act on; not-exploitable is the costliest label to get wrong; abstentions are neutral. */
export function labelTone(label: string | null | undefined): string {
  return label === "LIKELY_EXPLOITABLE"
    ? "danger"
    : label === "LIKELY_NOT_EXPLOITABLE"
      ? "success"
      : label === "ERROR"
        ? "warning"
        : "neutral";
}
export function labelText(label: string | null | undefined): string {
  return label ? label.replaceAll("_", " ").toLowerCase() : "no verdict";
}
export function evaluationPath(run: Pick<Evaluation, "agent" | "run">) {
  return `/evaluations/${encodeURIComponent(run.agent)}/${encodeURIComponent(run.run)}`;
}
export function attemptPath(agent: string, run: string, receipt: string) {
  return `${evaluationPath({ agent, run })}/attempts/${encodeURIComponent(receipt)}`;
}
export function runPath(id: string) {
  return `/runs/${encodeURIComponent(id)}`;
}
export function displayIdentity(value: unknown): string {
  return value == null
    ? "Unavailable"
    : typeof value === "string"
      ? value
      : JSON.stringify(value);
}
/** The latest run per agent and mode, from a newest-first list. */
export function latestByAgent(
  runs: Evaluation[],
  mode: string,
): Map<string, Evaluation> {
  const latest = new Map<string, Evaluation>();
  for (const run of runs)
    if (run.mode === mode && !run.language && !latest.has(run.agent))
      latest.set(run.agent, run);
  return latest;
}
/** Run records counted by label; a record without a verdict counts under its state. */
export function labelCounts(runs: RunRow[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const run of runs) {
    const key = run.label ?? run.state;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}
