import { useState } from "react";
import { Activity, Clock3, FlaskConical, Layers } from "lucide-react";
import {
  Heading,
  Panel,
  Notice,
  State,
  Stats,
  Badge,
} from "../components/evidence";
import { useData } from "../lib/useData";
import { displayIdentity } from "../lib/data";
import { duration, integer, number } from "../lib/format";
import {
  type MetricGroup,
  type MetricsData,
  total,
  mean,
  median,
  rate,
  histogram,
} from "../lib/metrics";
import "./metrics.css";

function Distribution({
  title,
  values,
  attempts,
  time = false,
}: {
  title: string;
  values: number[];
  attempts: number | null;
  time?: boolean;
}) {
  const bins = histogram(values),
    max = Math.max(1, ...bins.map((b) => b.count));
  const format = time ? duration : number;
  return (
    <Panel title={title} aside={<Badge>{values.length} samples</Badge>}>
      {values.length ? (
        <>
          <div className="distribution-summary">
            <span>
              Median <b>{format(median(values))}</b>
            </span>
            <span>
              Mean <b>{format(mean(values))}</b>
            </span>
            <span>
              Max <b>{format(Math.max(...values))}</b>
            </span>
          </div>
          <svg
            className="histogram"
            viewBox="0 0 480 172"
            role="img"
            aria-label={`${title}: ${values.length} observed samples`}
          >
            <title>
              {title} distribution, {values.length} observed samples
            </title>
            <line x1="25" y1="142" x2="465" y2="142" className="chart-axis" />
            {bins.map((bin, i) => {
              const width = 420 / bins.length,
                x = 35 + i * width,
                height = (110 * bin.count) / max;
              return (
                <g key={i}>
                  <rect
                    x={x + 3}
                    y={142 - height}
                    width={width - 6}
                    height={height}
                    rx="3"
                    className="chart-bar"
                  >
                    <title>{`${format(bin.min)}–${format(bin.max)}: ${bin.count} samples`}</title>
                  </rect>
                  <text
                    x={x + width / 2}
                    y={Math.max(20, 135 - height)}
                    textAnchor="middle"
                    className="chart-label"
                  >
                    {bin.count}
                  </text>
                </g>
              );
            })}
            <text x="35" y="165" className="chart-label">
              {format(bins[0].min)}
            </text>
            <text x="455" y="165" textAnchor="end" className="chart-label">
              {format(bins[bins.length - 1].max)}
            </text>
          </svg>
          <details className="distribution-data">
            <summary>View distribution data</summary>
            <table>
              <thead>
                <tr>
                  <th>Range</th>
                  <th>Samples</th>
                </tr>
              </thead>
              <tbody>
                {bins.map((b, i) => (
                  <tr key={i}>
                    <td>
                      {format(b.min)} – {format(b.max)}
                    </td>
                    <td>{b.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      ) : (
        <p className="panel-copy">
          No observed samples. This distribution is unknown, not zero.
        </p>
      )}
      <p className="distribution-note">
        {values.length}/{attempts ?? "unknown"} attempted tasks measured. Failed
        attempts may lack telemetry.{" "}
        {time
          ? "Native task duration; excludes CLI startup."
          : "Native reported tokens; partial or missing usage is excluded."}
      </p>
    </Panel>
  );
}
function Cohort({ group }: { group: MetricGroup }) {
  return (
    <>
      <div className="cohort-heading">
        <div>
          <h2>
            {group.agent} <Badge>{group.mode}</Badge>
          </h2>
          <p>
            {group.set} · {displayIdentity(group.model)}
          </p>
        </div>
        <span className="muted">
          {group.runs} recorded run{group.runs === 1 ? "" : "s"}
        </span>
      </div>
      <Stats
        items={[
          {
            label: "Evaluator success",
            value: rate(group.clean_attempts, group.attempts),
            note: `${group.clean_attempts ?? "Unknown"} / ${group.attempts ?? "unknown"} attempts passed all recorded checks`,
            icon: <FlaskConical size={18} />,
          },
          {
            label: "Task completion",
            value: rate(
              group.attempts != null && group.task_failures != null
                ? group.attempts - group.task_failures
                : null,
              group.attempts,
            ),
            note: "Completion is separate from correctness",
            icon: <Activity size={18} />,
          },
          {
            label: "Observed input tokens",
            value: group.input_tokens.length
              ? integer(total(group.input_tokens))
              : "Unavailable",
            note: `Sum over ${group.input_tokens.length} measured attempts`,
            icon: <Layers size={18} />,
          },
          {
            label: "Observed output tokens",
            value: group.output_tokens.length
              ? integer(total(group.output_tokens))
              : "Unavailable",
            note: `Sum over ${group.output_tokens.length} measured attempts`,
            icon: <Clock3 size={18} />,
          },
        ]}
      />
      <Notice>
        <strong>
          {group.mode === "scripted"
            ? "Scripted cohort."
            : group.mode === "live" ? "Live-model cohort." : "Unknown model mode."}
        </strong>{" "}
        {group.mode === "scripted" && "Token counts in scripted runs are fixture estimates. "}
        These distributions use individual native report samples, not averages
        of runs. Model calls do not establish application execution.{" "}
        {group.measured_runs}/{group.runs} runs have complete outcome counts.
      </Notice>
      {group.warnings.map((w, i) => (
        <Notice key={i} tone="warning">
          {w}
        </Notice>
      ))}
      <div className="distribution-grid">
        <Distribution
          title="Task latency"
          values={group.latency_seconds}
          attempts={group.attempts}
          time
        />
        <Distribution
          title="Input tokens"
          values={group.input_tokens}
          attempts={group.attempts}
        />
        <Distribution
          title="Output tokens"
          values={group.output_tokens}
          attempts={group.attempts}
        />
      </div>
      <Panel
        title="Correctness and accuracy evidence"
        aside={<Badge>Per recorded assertion</Badge>}
      >
        <p className="panel-copy">
          A general accuracy score is not separately defined by this report.
          Review each assertion's meaning: contract checks and structural checks
          are not semantic accuracy. Confirm agent improvements on fresh
          held-out cases and relevant execution evidence.
        </p>
        {Object.keys(group.assertions).length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Recorded check</th>
                  <th>Passed / evaluated</th>
                  <th>Pass rate</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(group.assertions).map(([name, a]) => (
                  <tr key={name}>
                    <td>
                      <code>{name}</code>
                    </td>
                    <td>
                      {a.passed} / {a.total}
                    </td>
                    <td>{rate(a.passed, a.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="panel-copy">Assertion evidence is unavailable.</p>
        )}
      </Panel>
      <details className="cohort-identity">
        <summary>Comparison identity</summary>
        <dl className="identity">
          <div>
            <dt>Dataset digest</dt>
            <dd>
              <code>{group.dataset_sha256 || "Unavailable"}</code>
            </dd>
          </div>
          <div>
            <dt>Identity digest</dt>
            <dd>
              <code>{group.identity_digest}</code>
            </dd>
          </div>
        </dl>
        <p>
          Groups keep recorded agent, model, dataset, mode, settings and summary
          identity separate. Missing dataset or model identity keeps runs
          separate. Unrecorded settings remain unknown.
        </p>
      </details>
    </>
  );
}
export function Metrics({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<MetricsData>("/api/metrics", revision);
  const [agent, setAgent] = useState(""),
    [mode, setMode] = useState(""),
    [selected, setSelected] = useState("");
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const groups = state.data.groups.filter(
    (g) => (!agent || g.agent === agent) && (!mode || g.mode === mode),
  );
  const current = groups.find((g) => g.id === selected) ?? groups.find((g) => g.latency_seconds.length || g.input_tokens.length || g.output_tokens.length) ?? groups[0];
  const runs = total(groups.map((g) => g.runs)),
    measured = total(groups.map((g) => g.measured_runs));
  const attempts = groups.flatMap((g) =>
    g.attempts == null ? [] : [g.attempts],
  );
  return (
    <>
      <Heading
        eyebrow="Observe · understand · improve"
        title="Agent metrics"
        description="Aggregate activity, then inspect a recorded cohort's outcomes and distributions."
      />
      {state.data.warnings.map((w, i) => (
        <Notice key={i} tone="warning">
          {w}
        </Notice>
      ))}
      <div className="filter-bar">
        <select
          aria-label="Metrics agent"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
        >
          <option value="">All agents</option>
          {[...new Set(state.data.groups.map((g) => g.agent))]
            .sort()
            .map((a) => (
              <option key={a}>{a}</option>
            ))}
        </select>
        <select
          aria-label="Metrics evidence mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="">All modes</option>
          {[...new Set(state.data.groups.map((g) => g.mode))]
            .sort()
            .map((m) => (
              <option key={m}>{m}</option>
            ))}
        </select>
      </div>
      <Stats
        items={[
          {
            label: "Recorded runs",
            value: integer(runs),
            note: "Across visible agent cohorts",
            icon: <Layers size={18} />,
          },
          {
            label: "Recorded attempts",
            value: attempts.length ? integer(total(attempts)) : "Unavailable",
            note: `Outcome-count coverage: ${measured}/${runs} runs`,
            icon: <Activity size={18} />,
          },
          {
            label: "Distinct agents",
            value: new Set(groups.map((g) => g.agent)).size,
            note: "No cross-agent accuracy average",
            icon: <FlaskConical size={18} />,
          },
          {
            label: "Recorded cohorts",
            value: groups.length,
            note: "Grouped by recorded identity",
            icon: <Clock3 size={18} />,
          },
        ]}
      />
      {groups.length ? (
        <>
          <Panel
            title="Per-agent performance"
            aside={<Badge>Select a cohort</Badge>}
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Agent / cohort</th>
                    <th>Runs</th>
                    <th>Evaluator success</th>
                    <th>Mean latency</th>
                    <th>Mean input / output tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map((g) => (
                    <tr
                      key={g.id}
                      className={g.id === current?.id ? "selected-cohort" : ""}
                    >
                      <td>
                        <button
                          className="cohort-select"
                          aria-pressed={g.id === current?.id}
                          onClick={() => setSelected(g.id)}
                        >
                          {g.agent}
                        </button>
                        <span className="row-subtitle">
                          {g.mode} · {g.set} · {g.identity_digest.slice(0, 8)}
                        </span>
                      </td>
                      <td>{g.runs}</td>
                      <td>
                        {rate(g.clean_attempts, g.attempts)}
                        <span className="row-subtitle">
                          {g.clean_attempts ?? "?"}/{g.attempts ?? "?"} attempts
                        </span>
                      </td>
                      <td>
                        {duration(mean(g.latency_seconds))}
                        <span className="row-subtitle">
                          {g.latency_seconds.length} samples
                        </span>
                      </td>
                      <td>
                        {number(mean(g.input_tokens))} /{" "}
                        {number(mean(g.output_tokens))}
                        <span className="row-subtitle">
                          {g.input_tokens.length} / {g.output_tokens.length}{" "}
                          samples
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          {current && <Cohort group={current} />}
        </>
      ) : (
        <div className="empty-state">
          <h2>No metrics for this selection</h2>
          <p>
            Run an evaluation with the CLI, then refresh. Distributions require
            its native report.json as well as summary.json.
          </p>
        </div>
      )}
    </>
  );
}
