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
  total_tokens: number[];
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
export function histogram(values: number[], domainMax?: number) {
  if (!values.length) return [];
  const min = domainMax == null ? Math.min(...values) : 0,
    max =
      domainMax == null ? Math.max(...values) : Math.max(domainMax, ...values);
  if (min === max) return [{ min, max, count: values.length }];
  const count =
      domainMax == null
        ? Math.min(8, Math.max(2, Math.ceil(Math.sqrt(values.length))))
        : 8,
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

// Nearest-rank p95; unknown rather than zero for an unmeasured distribution.
export function percentile(values: number[], fraction: number) {
  if (!values.length) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[
    Math.max(
      0,
      Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1),
    )
  ];
}
export function distributionScale(series: number[][]) {
  const max = Math.max(1, ...series.flat());
  const peak = Math.max(
    1,
    ...series.flatMap((values) =>
      histogram(values, max).map((bin) => bin.count),
    ),
  );
  return { max, peak };
}
export function frequencyPath(points: { x: number; y: number }[]) {
  if (!points.length) return "";
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1],
      b = points[i],
      mid = (a.x + b.x) / 2;
    path += ` C ${mid} ${a.y}, ${mid} ${b.y}, ${b.x} ${b.y}`;
  }
  return path;
}
