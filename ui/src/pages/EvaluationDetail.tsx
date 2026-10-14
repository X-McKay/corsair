import { useState } from "react";
import { ArrowLeft, ArrowUpRight, Clock3, Coins, Gauge, ShieldCheck } from "lucide-react";
import {
  type EvaluationDetail,
  type Rollup,
  LABELS,
  METRICS,
  attemptPath,
  displayIdentity,
  labelText,
  rate,
  ratioLabel,
} from "../lib/data";
import { duration, integer, number, percent, timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";
import {
  Badge,
  Heading,
  LabelBadge,
  Notice,
  Panel,
  PolicyBadge,
  RatioBadge,
  State,
  Stats,
  Status,
} from "../components/evidence";

const metricValue = (metric: string, value: number | null | undefined) =>
  metric === "wall_s" ? duration(value) : number(value, 2);

function Rollups({
  title,
  groups,
}: {
  title: string;
  groups: Record<string, Rollup | null>;
}) {
  const names = Object.keys(groups);
  const dimensions = [
    ...new Set(names.flatMap((n) => Object.keys(groups[n]?.dimensions ?? {}))),
  ].sort();
  const labelled = names.some((n) => groups[n]?.dispositions);
  if (!names.length) return null;
  return (
    <Panel title={title}>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Group</th>
              <th>Clean</th>
              {labelled && <th>Decisive</th>}
              {dimensions.map((d) => (
                <th key={d}>{d}</th>
              ))}
              <th>p50 wall</th>
            </tr>
          </thead>
          <tbody>
            {names.map((name) => {
              const r = groups[name];
              return (
                <tr key={name}>
                  <td>
                    <b>{name}</b>
                    <span className="row-subtitle">
                      {integer(r?.cases)} cases
                    </span>
                  </td>
                  <td>
                    <RatioBadge
                      value={
                        r?.attempts != null && r.clean_attempts != null
                          ? { passed: r.clean_attempts, total: r.attempts }
                          : null
                      }
                    />
                  </td>
                  {labelled && (
                    <td className="numeric">
                      {percent(r?.dispositions?.decisive_rate)}
                    </td>
                  )}
                  {dimensions.map((d) => (
                    <td key={d}>
                      {r?.dimensions[d] ? (
                        <RatioBadge value={r.dimensions[d]} />
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  ))}
                  <td className="numeric">
                    {duration(r?.metrics.wall_s?.p50)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Comparison({ data }: { data: EvaluationDetail }) {
  const ref = data.reference;
  if (!ref)
    return (
      <Panel title="Comparison">
        <p className="panel-copy">
          No promoted baseline, committed baseline or earlier run of this set
          and mode; nothing to compare.
        </p>
      </Panel>
    );
  // A language-narrowed run compares against the reference's rollup for that language (evals/run.py).
  const before =
    data.language && ref.language !== data.language
      ? (ref.by_language[data.language] ?? null)
      : ref.overall;
  const now = data.overall;
  const dims = [
    ...new Set([
      ...Object.keys(before?.dimensions ?? {}),
      ...Object.keys(now?.dimensions ?? {}),
    ]),
  ].sort();
  const changed = Object.keys({ ...ref.identity, ...data.identity })
    .filter(
      (key) =>
        !["git_commit", "git_dirty", "language", "repeat"].includes(key) &&
        JSON.stringify(ref.identity[key]) !== JSON.stringify(data.identity[key]),
    )
    .sort();
  return (
    <Panel
      title="Comparison"
      aside={
        <span className="muted">
          with {ref.kind} <code>{ref.run}</code>
          {data.language && ref.language !== data.language
            ? `, its ${data.language} rollup`
            : ""}
        </span>
      }
    >
      {!!changed.length && (
        <Notice tone="warning">
          Changed identity: {changed.join(", ")}.{" "}
          {changed.includes("dataset_sha256")
            ? "The case set changed, so scores are not directly comparable."
            : "Differences may come from these changes."}
        </Notice>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Measure</th>
              <th>Before</th>
              <th>Now</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Clean attempts</td>
              <td>
                {before?.attempts != null
                  ? `${before.clean_attempts}/${before.attempts}`
                  : "Unavailable"}
              </td>
              <td>
                {now?.attempts != null
                  ? `${now.clean_attempts}/${now.attempts}`
                  : "Unavailable"}
              </td>
            </tr>
            {dims.map((d) => {
              const a = before?.dimensions[d];
              const b = now?.dimensions[d];
              const delta = (rate(b) ?? 0) - (rate(a) ?? 0);
              return (
                <tr key={d}>
                  <td>{d}</td>
                  <td>{ratioLabel(a)}</td>
                  <td>
                    {ratioLabel(b)}{" "}
                    {rate(a) != null && rate(b) != null && delta !== 0 && (
                      <Badge tone={delta > 0 ? "success" : "warning"}>
                        {delta > 0 ? "+" : ""}
                        {(delta * 100).toFixed(1)} pts
                      </Badge>
                    )}
                  </td>
                </tr>
              );
            })}
            {before?.dispositions && now?.dispositions && (
              <tr>
                <td>Decisive rate</td>
                <td>{percent(before.dispositions.decisive_rate)}</td>
                <td>{percent(now.dispositions.decisive_rate)}</td>
              </tr>
            )}
            {METRICS.map((m) => (
              <tr key={m}>
                <td>
                  {m} <span className="muted">mean / p90</span>
                </td>
                <td>
                  {metricValue(m, before?.metrics[m]?.mean)} /{" "}
                  {metricValue(m, before?.metrics[m]?.p90)}
                </td>
                <td>
                  {metricValue(m, now?.metrics[m]?.mean)} /{" "}
                  {metricValue(m, now?.metrics[m]?.p90)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
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
  const state = useData<EvaluationDetail>(
    `/api/evaluations/${encodeURIComponent(agent)}/${encodeURIComponent(run)}`,
    revision,
  );
  const [failedOnly, setFailedOnly] = useState(false);
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const data = state.data;
  const o = data.overall;
  const dispositions = o?.dispositions;
  const rows = data.attempts.filter((a) => !failedOnly || !a.passed);
  const chain = data.agent === "chain";
  return (
    <>
      <Link to="/evaluations" className="back-link">
        <ArrowLeft size={15} />
        All evaluations
      </Link>
      <Heading
        eyebrow={`${data.set}${data.language ? ` · ${data.language} only` : ""} / ${data.mode}`}
        title={`${data.agent} evaluation`}
        description={data.run}
      >
        <Status run={{ ...data, policy: data.policy?.status }} />
      </Heading>
      <Stats
        items={[
          {
            label: "Clean attempts",
            value:
              o?.attempts != null && o.clean_attempts != null
                ? `${o.clean_attempts} / ${o.attempts}`
                : "Unavailable",
            note: `${integer(o?.cases)} cases · ${integer(o?.task_failures)} task failures`,
            icon: <ShieldCheck size={18} />,
          },
          chain
            ? {
                label: "Decisive",
                value: percent(dispositions?.decisive_rate),
                note: `${integer(dispositions?.decisive_correct)} of ${integer(dispositions?.decisive)} decisive labels correct`,
                icon: <Gauge size={18} />,
              }
            : {
                label: "Completion",
                value: percent(o?.completion?.rate),
                note: `${integer(o?.completion?.evaluator_failures)} evaluator failures`,
                icon: <Gauge size={18} />,
              },
          {
            label: "Wall time p50 / p90",
            value: `${duration(o?.metrics.wall_s?.p50)} / ${duration(o?.metrics.wall_s?.p90)}`,
            note: `${o?.metrics.wall_s?.observed ?? 0}/${integer(o?.attempts)} observed`,
            icon: <Clock3 size={18} />,
          },
          {
            label: "Mean tokens",
            value: number(o?.metrics.tokens?.mean, 0),
            note: `${o?.metrics.tokens?.observed ?? 0}/${integer(o?.attempts)} observed`,
            icon: <Coins size={18} />,
          },
        ]}
      />
      <Notice>
        <strong>
          {data.mode === "scripted"
            ? "Scripted run."
            : data.mode === "live"
              ? "Live run."
              : "Recorded run."}
        </strong>{" "}
        {data.mode === "scripted"
          ? "The case oracle was replayed through the agent's own stage; this checks plumbing and contracts, not model quality."
          : "Live model calls; compare only against runs with the same set, mode and identity."}
      </Notice>
      <div className="detail-meta">
        <span>
          Started <b>{timestamp(data.command.started)}</b>
        </span>
        <span>
          Command exit <b>{integer(data.command.exit_code)}</b>
        </span>
        <span>
          Commit{" "}
          <code>
            {data.command.git_commit?.slice(0, 12) || "Unavailable"}
            {data.command.git_dirty ? " · dirty" : ""}
          </code>
        </span>
        {data.command.note && (
          <span>
            Note <b>{data.command.note}</b>
          </span>
        )}
      </div>
      <Comparison data={data} />
      {dispositions && (
        <Panel title="Dispositions" aside={<Badge>against evaluator labels</Badge>}>
          <div className="dispositions">
            <div>
              <h3>Accuracy by expected label</h3>
              {LABELS.filter((l) => dispositions.accuracy_by_expected_label[l]).map(
                (label) => (
                  <div className="disposition-row" key={label}>
                    <LabelBadge label={label} />
                    <RatioBadge
                      value={dispositions.accuracy_by_expected_label[label]}
                    />
                  </div>
                ),
              )}
            </div>
            <div>
              <h3>Abstentions by terminal reason</h3>
              {Object.entries(dispositions.abstentions).map(([label, a]) => (
                <div className="disposition-row" key={label}>
                  <LabelBadge label={label} />
                  <span>
                    {integer(a.count)} ({percent(a.rate)})
                  </span>
                  <span className="row-subtitle">
                    {Object.entries(a.by_terminal_reason)
                      .map(([reason, n]) => `${reason} ${n}`)
                      .join(" · ") || "none"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Panel>
      )}
      <Rollups title="By language" groups={data.by_language} />
      <Rollups title="By case kind" groups={data.by_kind} />
      <Panel
        title="Attempts"
        aside={
          <label className="toggle">
            <input
              type="checkbox"
              checked={failedOnly}
              onChange={(e) => setFailedOnly(e.target.checked)}
            />{" "}
            Not clean only
          </label>
        }
      >
        {rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Result</th>
                  {chain && <th>Verdict / expected</th>}
                  <th>Failed checks</th>
                  <th>Wall</th>
                  <th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a, i) => (
                  <tr key={`${a.case}/${a.receipt ?? i}`}>
                    <td>
                      {chain && a.record && a.receipt ? (
                        <Link
                          to={attemptPath(data.agent, data.run, a.receipt)}
                          className="row-title"
                        >
                          {a.case}
                          <ArrowUpRight size={13} />
                        </Link>
                      ) : (
                        <b>{a.case}</b>
                      )}
                      <span className="row-subtitle">
                        {a.language} · {a.kind}
                        {a.receipt ? ` · receipt ${a.receipt}` : ""}
                      </span>
                    </td>
                    <td>
                      <Badge
                        tone={
                          a.passed ? "success" : a.passed === false ? "warning" : "neutral"
                        }
                      >
                        {a.passed ? "clean" : a.failed ? `${a.failure_kind ?? "unattributed"} failure` : "not clean"}
                      </Badge>
                      {a.status && a.status !== "ok" && (
                        <span className="row-subtitle">status {a.status}</span>
                      )}
                    </td>
                    {chain && (
                      <td>
                        <LabelBadge label={a.label} />
                        <span className="row-subtitle">
                          expected {labelText(a.expected_label)}
                          {a.terminal_reason ? ` · ${a.terminal_reason}` : ""}
                        </span>
                      </td>
                    )}
                    <td>
                      {a.failed_assertions.length ? (
                        a.failed_assertions.map((name) => (
                          <code key={name} className="chip">
                            {name}
                          </code>
                        ))
                      ) : (
                        <span className="muted">none</span>
                      )}
                    </td>
                    <td className="numeric">{duration(a.wall_s)}</td>
                    <td className="numeric">{integer(a.tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="panel-copy">
            {data.attempts.length
              ? "Every attempt is clean."
              : "No attempt rows were retained for this run."}
          </p>
        )}
        {data.attempts_limited && (
          <Notice tone="warning">Only the first 2000 attempts are shown.</Notice>
        )}
        <p className="panel-copy">
          Failure text can carry case inputs and exceptions, so only its kind is
          shown; read the run's evidence directory for detail.
        </p>
      </Panel>
      {data.policy && (
        <Panel
          title="Release policy"
          aside={<PolicyBadge status={data.policy.status} />}
        >
          {Object.keys(data.policy.entries).length ? (
            <div className="assertion-list">
              {Object.entries(data.policy.entries).map(([name, e]) => (
                <div key={name}>
                  <code>{name}</code>
                  <span className="muted">
                    {e.value ?? "unknown"} vs {e.limit ?? "not set"}
                  </span>
                  <PolicyBadge status={e.status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="panel-copy">
              {data.policy.in_scope === false
                ? "This set and mode are outside the agent's release policy."
                : "No policy entries."}
            </p>
          )}
          {!!data.policy.missing_provenance.length && (
            <Notice tone="warning">
              Missing provenance: {data.policy.missing_provenance.join(", ")}.
            </Notice>
          )}
          <p className="panel-copy">
            Gates are deferred: the policy is reported and never sets the exit
            code.
          </p>
        </Panel>
      )}
      <Panel title="Run identity" aside={<Badge>Recorded configuration</Badge>}>
        <dl className="identity">
          {Object.entries(data.identity).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>
                <code>{displayIdentity(value)}</code>
              </dd>
            </div>
          ))}
          {Object.entries(o?.parameters ?? {}).map(([key, value]) => (
            <div key={`parameter-${key}`}>
              <dt>parameter {key}</dt>
              <dd>
                <code>{displayIdentity(value)}</code>
              </dd>
            </div>
          ))}
        </dl>
      </Panel>
    </>
  );
}
