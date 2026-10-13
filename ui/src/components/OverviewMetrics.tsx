import { useState } from "react";
import { Distribution } from "./Distribution";
import { Notice, State } from "./evidence";
import { useData } from "../lib/useData";
import { type MetricsData, distributionScale, total } from "../lib/metrics";
import { integer } from "../lib/format";
import "../pages/metrics.css";

export function OverviewMetrics({
  revision,
  retry,
  shownWarnings,
}: {
  revision: number;
  retry: () => void;
  shownWarnings: string[];
}) {
  const state = useData<MetricsData>("/api/metrics", revision);
  const [selected, setSelected] = useState("");
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const modes = [...new Set(state.data.groups.map((g) => g.mode))].sort();
  const mode = modes.includes(selected)
    ? selected
    : modes.includes("live")
      ? "live"
      : modes[0];
  const groups = state.data.groups.filter((g) => g.mode === mode);
  const latencies = groups.flatMap((g) => g.latency_seconds),
    tokens = groups.flatMap((g) => g.total_tokens);
  const attempts =
    groups.length &&
    groups.every((g) => g.attempts != null && g.measured_runs === g.runs)
      ? total(groups.map((g) => g.attempts!))
      : null;
  return (
    <section aria-label="Workspace resource distributions">
      {state.data.warnings
        .filter((w) => !shownWarnings.includes(w))
        .map((w, i) => (
          <Notice tone="warning" key={i}>
            {w}
          </Notice>
        ))}
      {[...new Set(groups.flatMap((g) => g.warnings))]
        .filter(
          (w) =>
            !shownWarnings.includes(w) && !state.data!.warnings.includes(w),
        )
        .map((w) => (
          <Notice key={w} tone="warning">
            {w}
          </Notice>
        ))}
      <div className="distribution-mode">
        <h2>Resource distributions</h2>
        {modes.length > 1 ? (
          <select
            aria-label="Overview distribution mode"
            value={mode}
            onChange={(e) => setSelected(e.target.value)}
          >
            {modes.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        ) : (
          <span>{mode ?? "No recorded mode"}</span>
        )}
        <span>
          {tokens.length ? integer(total(tokens)) : "Unavailable"} total
          observed tokens · {tokens.length} measured attempts
        </span>
      </div>
      <div className="overview-distributions">
        <div className="panel">
          <Distribution
            title="Task latency"
            values={latencies}
            attempts={attempts}
            time
            scale={distributionScale([latencies])}
          />
        </div>
        <div className="panel">
          <Distribution
            title="Total tokens"
            values={tokens}
            attempts={attempts}
            scale={distributionScale([tokens])}
          />
        </div>
      </div>
      <p className="metrics-caption">
        Resource usage across recorded cohorts in this mode; not a common
        accuracy benchmark.{" "}
        {mode === "scripted"
          ? "Scripted token counts are fixture estimates. "
          : ""}
        Only observed samples are included; failed attempts may lack telemetry.
        Bars and frequency line use the same counts.
      </p>
    </section>
  );
}
