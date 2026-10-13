import { useState } from "react";
import { Activity, Clock3, FlaskConical, Layers } from "lucide-react";
import { Heading, Notice, State, Stats, Badge } from "../components/evidence";
import { Distribution } from "../components/Distribution";
import { useData } from "../lib/useData";
import { displayIdentity } from "../lib/data";
import { integer } from "../lib/format";
import {
  type MetricGroup,
  type MetricsData,
  total,
  median,
  rate,
  distributionScale,
} from "../lib/metrics";
import "./metrics.css";

function Evidence({ group }: { group: MetricGroup }) {
  return (
    <details className="agent-evidence">
      <summary>Recorded checks, usage and cohort identity</summary>
      <p>
        A general accuracy score is not defined by this report. Contract and
        structural checks are not semantic accuracy. Model calls do not
        establish application execution.
      </p>
      <dl className="agent-usage">
        <div>
          <dt>Observed input tokens</dt>
          <dd>
            {group.input_tokens.length
              ? integer(total(group.input_tokens))
              : "Unavailable"}{" "}
            <small>({group.input_tokens.length} samples)</small>
          </dd>
        </div>
        <div>
          <dt>Observed output tokens</dt>
          <dd>
            {group.output_tokens.length
              ? integer(total(group.output_tokens))
              : "Unavailable"}{" "}
            <small>({group.output_tokens.length} samples)</small>
          </dd>
        </div>
      </dl>
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
        <p>Assertion evidence is unavailable.</p>
      )}
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
        {group.measured_runs}/{group.runs} runs have complete outcome counts.
        Groups separate recorded settings; unrecorded settings remain unknown.
        Failed attempts may lack telemetry. Total-token samples require both
        input and output usage from the same attempt.
      </p>
    </details>
  );
}
function AgentCard({
  group,
  cohorts,
  choose,
  latencyScale,
  tokenScale,
}: {
  group: MetricGroup;
  cohorts: MetricGroup[];
  choose: (id: string) => void;
  latencyScale: { max: number; peak: number };
  tokenScale: { max: number; peak: number };
}) {
  return (
    <article className="agent-card" aria-label={`${group.agent} performance`}>
      <header className="agent-card-heading">
        <div>
          <h2>
            {group.agent} <Badge>{group.mode}</Badge>
          </h2>
          <p>
            {group.runs} recorded run{group.runs === 1 ? "" : "s"} ·{" "}
            {group.attempts ?? "Unknown"} attempts ·{" "}
            {group.task_failures ?? "unknown"} task failures
          </p>
        </div>
        {cohorts.length > 1 && (
          <label className="cohort-picker">
            Recorded cohort
            <select
              aria-label={`${group.agent} cohort`}
              value={group.id}
              onChange={(e) => choose(e.target.value)}
            >
              {cohorts.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.mode} · {g.set} · {displayIdentity(g.model)} ·{" "}
                  {g.identity_digest.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>
      <p className="agent-cohort-label">
        {group.set} · {displayIdentity(group.model)} ·{" "}
        {group.identity_digest.slice(0, 8)}
        {group.mode === "scripted"
          ? " · Scripted token estimates"
          : group.mode === "live"
            ? " · Live-model observations"
            : " · Model mode unknown"}
      </p>
      <div className="agent-card-body">
        <div className="agent-outcomes">
          <div className="agent-stat">
            <span>Evaluator success</span>
            <strong>{rate(group.clean_attempts, group.attempts)}</strong>
            <small>
              {group.clean_attempts ?? "?"}/{group.attempts ?? "?"} passed all
              checks
            </small>
          </div>
          <div className="agent-stat">
            <span>Task completion</span>
            <strong>
              {rate(
                group.attempts != null && group.task_failures != null
                  ? group.attempts - group.task_failures
                  : null,
                group.attempts,
              )}
            </strong>
            <small>Separate from correctness</small>
          </div>
          <div className="agent-stat accuracy-status">
            <span>Accuracy</span>
            <strong>Not defined</strong>
            <small>See recorded checks below</small>
          </div>
        </div>
        <Distribution
          title="Task latency"
          values={group.latency_seconds}
          attempts={group.measured_runs === group.runs ? group.attempts : null}
          time
          scale={latencyScale}
        />
        <Distribution
          title="Total tokens"
          values={group.total_tokens}
          attempts={group.measured_runs === group.runs ? group.attempts : null}
          scale={tokenScale}
        />
      </div>
      {group.warnings.map((w, i) => (
        <Notice key={i} tone="warning">
          {w}
        </Notice>
      ))}
      <Evidence group={group} />
    </article>
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
    [rank, setRank] = useState("agent");
  const [selected, setSelected] = useState<Record<string, string>>({});
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const groups = state.data.groups.filter(
    (g) => (!agent || g.agent === agent) && (!mode || g.mode === mode),
  );
  const names = [...new Set(groups.map((g) => g.agent))].sort();
  const cards = names.map((name) => {
    const cohorts = groups.filter((g) => g.agent === name);
    return {
      cohorts,
      group:
        cohorts.find((g) => g.id === selected[name]) ??
        cohorts.find(
          (g) => g.latency_seconds.length || g.total_tokens.length,
        ) ??
        cohorts[0],
    };
  });
  cards.sort((a, b) =>
    rank === "agent"
      ? a.group.agent.localeCompare(b.group.agent)
      : (median(
          rank === "latency" ? b.group.latency_seconds : b.group.total_tokens,
        ) ?? -1) -
        (median(
          rank === "latency" ? a.group.latency_seconds : a.group.total_tokens,
        ) ?? -1),
  );
  const latencyScale = distributionScale(
      cards.map((c) => c.group.latency_seconds),
    ),
    tokenScale = distributionScale(cards.map((c) => c.group.total_tokens));
  const runs = total(groups.map((g) => g.runs)),
    measured = total(groups.map((g) => g.measured_runs));
  const attempts = groups.flatMap((g) =>
    g.attempts == null ? [] : [g.attempts],
  );
  return (
    <>
      <Heading
        eyebrow="Observe · understand · improve"
        title="Agents"
        description="Every agent's outcomes, latency and token distributions in one place."
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
        <select
          aria-label="Rank agents by"
          value={rank}
          onChange={(e) => setRank(e.target.value)}
        >
          <option value="agent">Agent name</option>
          <option value="latency">Median latency</option>
          <option value="tokens">Median tokens</option>
        </select>
      </div>
      <Stats
        items={[
          {
            label: "Recorded runs",
            value: integer(runs),
            note: "Across filtered cohorts",
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
            value: names.length,
            note: "One card per recorded agent",
            icon: <FlaskConical size={18} />,
          },
          {
            label: "Recorded cohorts",
            value: groups.length,
            note: "Select a cohort within each agent",
            icon: <Clock3 size={18} />,
          },
        ]}
      />
      {cards.length ? (
        <>
          <p className="metrics-caption">
            Each card shows one recorded cohort. Shared chart scales compare
            resource use; different agent tasks and cohorts are not a common
            accuracy benchmark. Bars and line share bin counts.
          </p>
          <div className="agent-cards">
            {cards.map(({ group, cohorts }) => (
              <AgentCard
                key={group.agent}
                group={group}
                cohorts={cohorts}
                choose={(id) =>
                  setSelected((prev) => ({ ...prev, [group.agent]: id }))
                }
                latencyScale={latencyScale}
                tokenScale={tokenScale}
              />
            ))}
          </div>
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
