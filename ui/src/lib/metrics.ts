export interface MetricGroup {
  id: string;
  agent: string;
  mode: string;
  set: string;
  dataset_sha256: string | null;
  model: unknown;
  identity_digest: string;
  runs: number;
  measured_runs: number;
  attempts: number | null;
  clean_attempts: number | null;
  task_failures: number | null;
  latency_seconds: number[];
  input_tokens: number[];
  output_tokens: number[];
  telemetry_attempts: number;
  assertions: Record<string, { passed: number; total: number }>;
  warnings: string[];
}
export interface MetricsData {
  groups: MetricGroup[];
  warnings: string[];
}
export const total = (values: number[]) => values.reduce((a, b) => a + b, 0);
export function mean(values: number[]) {
  return values.length ? total(values) / values.length : undefined;
}
export function median(values: number[]) {
  if (!values.length) return undefined;
  const sorted = [...values].sort((a, b) => a - b),
    i = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[i] : (sorted[i - 1] + sorted[i]) / 2;
}
export function rate(passed: number | null, total: number | null) {
  return passed != null && total != null && total > 0
    ? `${((100 * passed) / total).toFixed(1)}%`
    : "Unavailable";
}
export function histogram(values: number[]) {
  if (!values.length) return [];
  const min = Math.min(...values),
    max = Math.max(...values);
  if (min === max) return [{ min, max, count: values.length }];
  const count = Math.min(8, Math.max(2, Math.ceil(Math.sqrt(values.length)))),
    width = (max - min) / count;
  const bins = Array.from({ length: count }, (_, i) => ({
    min: min + i * width,
    max: min + (i + 1) * width,
    count: 0,
  }));
  for (const v of values)
    bins[Math.min(count - 1, Math.floor((v - min) / width))].count++;
  return bins;
}
