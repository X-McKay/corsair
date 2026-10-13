import {
  ArrowDownLeft,
  ArrowUpRight,
  ArrowLeft,
  ChevronRight,
  Clock3,
  ShieldCheck,
} from "lucide-react";
import {
  type Evaluation,
  type Summary,
  displayIdentity,
  assertionResult,
  metric,
} from "../lib/data";
import { duration, integer, number, timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";
import {
  Badge,
  Status,
  Heading,
  Panel,
  Notice,
  State,
  Stats,
} from "../components/evidence";
export function Metrics({ summary }: { summary: Summary }) {
  const keys = Object.keys(summary.efficiency_mean ?? {});
  return keys.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Recorded metric</th>
            <th>Mean / observed sample</th>
            <th>Coverage</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const coverage = summary.efficiency_samples?.[key];
            return (
              <tr key={key}>
                <td>
                  <code>{key}</code>
                </td>
                <td className="numeric">
                  {key.includes("seconds")
                    ? duration(summary.efficiency_mean?.[key])
                    : number(summary.efficiency_mean?.[key], 3)}
                </td>
                <td>
                  {coverage
                    ? `${coverage.observed}/${coverage.attempts} attempts`
                    : "Unavailable"}
                  {coverage && coverage.observed < coverage.attempts && (
                    <Badge tone="warning">Partial</Badge>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="panel-copy">
      No efficiency measurements were retained for this run. Token usage and
      latency are unknown.
    </p>
  );
}
export function Detail({
  agent,
  run,
  revision,
  retry,
}: {
  agent: string;
  run: string;
  revision: number;
  retry: () => void;
}) {
  const state = useData<Evaluation>(
    `/api/evaluations/${encodeURIComponent(agent)}/${encodeURIComponent(run)}`,
    revision,
  );
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const data = state.data,
    s = data.summary;
  const cases = Object.entries(s.cases ?? {});
  const input = metric(s, "observed_input_tokens", "input_tokens");
  const output = metric(s, "observed_output_tokens", "output_tokens");
  const time = metric(s, "task_seconds");
  const coverage = (value: ReturnType<typeof metric>) =>
    value?.coverage
      ? `${value.coverage.observed}/${value.coverage.attempts} attempts observed`
      : "Coverage unavailable";
  return (
    <>
      <Link to="/evaluations" className="back-link">
        <ArrowLeft size={15} />
        All evaluations
      </Link>
      <Heading
        eyebrow={`${data.set} / ${data.mode}`}
        title={`${data.agent} evaluation`}
        description={data.run}
      >
        <Status run={data} />
      </Heading>
      <Stats
        items={[
          {
            label: "Clean attempts",
            value:
              s.attempts != null && s.clean_attempts != null
                ? `${s.clean_attempts} / ${s.attempts}`
                : "Unavailable",
            note: "Passed recorded evaluators",
            icon: <ShieldCheck size={18} />,
          },
          {
            label: "Mean input tokens",
            value: number(input?.value),
            note: coverage(input),
            icon: <ArrowDownLeft size={18} />,
          },
          {
            label: "Mean output tokens",
            value: number(output?.value),
            note: coverage(output),
            icon: <ArrowUpRight size={18} />,
          },
          {
            label: "Mean task time",
            value: duration(time?.value),
            note: coverage(time),
            icon: <Clock3 size={18} />,
          },
        ]}
      />
      <Notice>
        <strong>
          {data.mode === "scripted"
            ? "Scripted evidence."
            : data.mode === "live"
              ? "Live provider mode."
              : "Recorded provider mode."}
        </strong>{" "}
        {data.command?.suite_note ||
          "Read the recorded execution identity and individual assertions to understand what this suite actually checks."}{" "}
        Clean does not mean proven semantic accuracy.
      </Notice>
      <div className="detail-meta">
        <span>
          Started <b>{timestamp(data.command?.started)}</b>
        </span>
        <span>
          Task failures <b>{integer(s.task_failures)}</b>
        </span>
        <span>
          Command exit <b>{integer(data.command?.exit_code)}</b>
        </span>
        <span>
          Commit{" "}
          <code>
            {data.command?.git_commit?.slice(0, 12) || "Unavailable"}
            {data.command?.git_dirty ? " · dirty" : ""}
          </code>
        </span>
      </div>
      <Panel
        title="Cases"
        aside={
          <span className="muted">{cases.length} recorded case groups</span>
        }
      >
        {cases.length ? (
          <div className="case-list">
            {cases.map(([name, c]) => (
              <details className="case" key={name}>
                <summary>
                  <ChevronRight size={16} />
                  <span className="case-name">{name}</span>
                  <span className="muted">
                    {integer(c.clean)}/{integer(c.attempts)} clean
                  </span>
                  <Badge
                    tone={
                      c.attempts != null &&
                      c.attempts > 0 &&
                      c.clean === c.attempts
                        ? "success"
                        : "warning"
                    }
                  >
                    {c.attempts != null &&
                    c.attempts > 0 &&
                    c.clean === c.attempts
                      ? "Clean"
                      : "Inspect"}
                  </Badge>
                </summary>
                <div className="case-body">
                  <h3>Recorded failures</h3>
                  {Object.keys(c.failed_assertions ?? {}).length ? (
                    <ul>
                      {Object.entries(c.failed_assertions ?? {}).map(
                        ([key, count]) => (
                          <li key={key}>
                            <code>{key}</code> — {count} failed assertion
                            {count !== 1 ? "s" : ""}
                          </li>
                        ),
                      )}
                    </ul>
                  ) : (
                    <p>
                      {c.failed_assertions == null
                        ? "Assertion failure details are unavailable."
                        : "No assertion failures recorded."}
                    </p>
                  )}
                  <p>
                    Task failures: {c.task_failure_count ?? "Unavailable"}.
                    Error text is withheld by the read-only service.
                  </p>
                </div>
              </details>
            ))}
          </div>
        ) : (
          <p className="panel-copy">
            Case evidence is unavailable for this run.
          </p>
        )}
      </Panel>
      <div className="detail-grid">
        <Panel title="Assertion results">
          {Object.keys(s.assertions ?? {}).length ? (
            <div className="assertion-list">
              {Object.entries(s.assertions ?? {}).map(([key, value]) => (
                <div key={key}>
                  <code>{key}</code>
                  <Badge tone={assertionResult(value).tone}>
                    {assertionResult(value).label}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="panel-copy">No assertion counts were retained.</p>
          )}
        </Panel>
        <Panel title="Observed efficiency">
          <Metrics summary={s} />
        </Panel>
      </div>
      <Panel title="Run identity" aside={<Badge>Recorded configuration</Badge>}>
        <dl className="identity">
          {Object.entries(s.identity ?? {}).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>
                <code>{displayIdentity(value)}</code>
              </dd>
            </div>
          ))}
          {!Object.keys(s.identity ?? {}).length && (
            <p>No identity was retained.</p>
          )}
        </dl>
      </Panel>
      <Notice>
        <strong>Compare with care.</strong> This view does not declare runs
        comparable. Check dataset, evaluator and provider configuration,
        budgets, execution mode and measurement coverage before using the
        runner’s comparison report. Missing identity is unknown.
      </Notice>
    </>
  );
}
