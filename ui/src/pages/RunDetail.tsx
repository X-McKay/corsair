import { ArrowLeft, Clock3, Coins, ShieldAlert, Workflow } from "lucide-react";
import {
  type Probe,
  type RunDetail as Detail,
  attemptPath,
  displayIdentity,
  evaluationPath,
  labelText,
} from "../lib/data";
import { duration, integer, number, timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";
import {
  Badge,
  Heading,
  LabelBadge,
  Notice,
  Panel,
  State,
  Stats,
} from "../components/evidence";

const yes = (value: boolean | null | undefined) =>
  value == null ? "unknown" : value ? "yes" : "no";

function outcomeTone(outcome: string | null) {
  return outcome === "passed"
    ? "success"
    : outcome === "assertion_failed"
      ? "info"
      : outcome
        ? "warning"
        : "neutral";
}

function ProbeCell({ probe }: { probe: Probe | undefined }) {
  if (!probe) return <span className="muted">Not run</span>;
  const f = probe.facts;
  return (
    <div className="probe-cell">
      <Badge tone={outcomeTone(probe.outcome)}>
        {probe.outcome?.replaceAll("_", " ") ?? "unknown"}
      </Badge>
      <span className="row-subtitle">
        exit {f.exit_code ?? "?"} ({f.exit_class ?? "unknown"})
        {f.timed_out ? " · timed out" : ""}
      </span>
      <span className="row-subtitle">
        start {yes(f.start_marker)} · end {yes(f.end_marker)} · token{" "}
        {yes(f.token_in_output)} · check {f.check_marker ?? "unknown"}
      </span>
      <span className="row-subtitle">
        {duration(probe.duration_s)} · cleanup {yes(probe.cleanup_confirmed)}
      </span>
    </div>
  );
}

export function RunDetail({
  url,
  revision,
  retry,
}: {
  url: string;
  revision: number;
  retry: () => void;
}) {
  const state = useData<Detail>(url, revision);
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const d = state.data;
  const source = d.source;
  const f = d.finding_detail;
  const revisions = Object.keys(d.probes);
  return (
    <>
      {source.kind === "eval" ? (
        <Link
          to={evaluationPath({ agent: source.agent, run: source.eval_run })}
          className="back-link"
        >
          <ArrowLeft size={15} />
          Chain eval {source.eval_run}
        </Link>
      ) : (
        <Link to="/runs" className="back-link">
          <ArrowLeft size={15} />
          All runs
        </Link>
      )}
      <Heading
        eyebrow={`${d.mode ?? "unknown mode"} · ${d.state}`}
        title={f.title || d.case || "Run record"}
        description={d.run}
      >
        <LabelBadge label={d.label} />
      </Heading>
      {source.kind === "eval" && (
        <Notice
          tone={
            source.expected_label && source.expected_label !== d.label
              ? "warning"
              : "info"
          }
        >
          Chain eval attempt {source.receipt} for case{" "}
          <code>{source.case}</code>. The evaluator expected{" "}
          <b>{labelText(source.expected_label)}</b>; the attempt{" "}
          {source.passed ? "passed" : "did not pass"} its checks. The expected
          label is evaluator-only and never reached the chain.
        </Notice>
      )}
      <Stats
        items={[
          {
            label: "Rule",
            value: d.rule ?? "None",
            note: d.reason ?? "No terminal reason",
            icon: <ShieldAlert size={18} />,
          },
          {
            label: "Finding / fix",
            value: d.finding ?? "Unavailable",
            note: `fix ${d.fix ?? "unknown"}${d.fix_reason ? ` (${d.fix_reason})` : ""}`,
            icon: <Workflow size={18} />,
          },
          {
            label: "Wall time",
            value: duration(d.totals.wall_s),
            note: `${duration(d.totals.agent_wall_s)} in agent calls`,
            icon: <Clock3 size={18} />,
          },
          {
            label: "Tokens",
            value: integer(d.totals.tokens),
            note: `${integer(d.totals.agent_calls)} agent calls · ${integer(d.totals.requests)} requests`,
            icon: <Coins size={18} />,
          },
        ]}
      />
      {d.sensitivity === "unverified" && (
        <Notice tone="warning">
          <strong>Sensitivity unverified.</strong> How often a failed proof
          pair misses a real vulnerability is not yet measured for this
          language and class. It never changes the label.
        </Notice>
      )}
      {d.state !== "completed" && (
        <Notice tone="warning">
          This record has no verdict ({d.state}). Last started step:{" "}
          <code>{displayIdentity(d.provenance.last_started_step)}</code>. It
          does not prove that work is still running.
        </Notice>
      )}
      <div className="detail-grid">
        <Panel title="Finding">
          <dl className="identity">
            <div>
              <dt>Case</dt>
              <dd>
                <code>{d.case ?? "Unavailable"}</code>
              </dd>
            </div>
            <div>
              <dt>Location</dt>
              <dd>
                <code>
                  {f.file_path ?? "Unavailable"}
                  {f.start_line != null ? `:${f.start_line}` : ""}
                </code>
                {f.symbol && (
                  <span className="row-subtitle">symbol {f.symbol}</span>
                )}
              </dd>
            </div>
            <div>
              <dt>CWE</dt>
              <dd>{f.cwe ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Description</dt>
              <dd>{f.description ?? "Unavailable"}</dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Probe outcomes" aside={<Badge>decided pair</Badge>}>
          {revisions.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Revision</th>
                    <th>Control</th>
                    <th>Exploit</th>
                  </tr>
                </thead>
                <tbody>
                  {revisions.map((revision) => (
                    <tr key={revision}>
                      <td>
                        <b>{revision}</b>
                      </td>
                      <td>
                        <ProbeCell probe={d.probes[revision].control} />
                      </td>
                      <td>
                        <ProbeCell probe={d.probes[revision].exploit} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="panel-copy">
              No probe ran. The verdict came from an earlier stage (
              {d.reason ?? "unknown reason"}).
            </p>
          )}
        </Panel>
      </div>
      {!!d.attempts.length && (
        <Panel title="Exploit attempts">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Attempt</th>
                  <th>PoV on vulnerable</th>
                  <th>Review rounds</th>
                  <th>First review valid</th>
                  <th>Decided</th>
                </tr>
              </thead>
              <tbody>
                {d.attempts.map((a) => (
                  <tr key={a.number ?? 0}>
                    <td>
                      <b>{a.number ?? "?"}</b>
                      <code className="row-subtitle">
                        {a.patch_sha256?.slice(0, 12) ?? "no frozen pair"}
                      </code>
                    </td>
                    <td>
                      <Badge tone={outcomeTone(a.exploit_outcome)}>
                        {a.exploit_outcome?.replaceAll("_", " ") ?? "not run"}
                      </Badge>
                    </td>
                    <td className="numeric">{integer(a.review_rounds)}</td>
                    <td>
                      {Object.entries(a.first_review_valid)
                        .map(([role, ok]) => `${role} ${ok ? "yes" : "no"}`)
                        .join(" · ") || "Unavailable"}
                    </td>
                    <td>{a.decided ? <Badge tone="info">decided</Badge> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      {!!d.validity.length && (
        <Panel title="Outcome-blind review">
          {d.validity.map((pair, i) => (
            <div className="validity" key={i}>
              <h3>
                Pair <code>{pair.patch_sha256?.slice(0, 12)}</code> on{" "}
                {pair.revision}
              </h3>
              <div className="validity-roles">
                {Object.entries(pair.roles).map(([role, v]) => (
                  <div key={role}>
                    <b>{role}</b>{" "}
                    <Badge tone={v.valid ? "success" : "warning"}>
                      {v.valid ? "valid" : "invalid"}
                    </Badge>
                    <span className="row-subtitle">
                      real target {yes(v.calls_real_target)} · exercises{" "}
                      {yes(v.exercises_condition)} · assertion relevant{" "}
                      {yes(v.assertion_relevant)} · doubles only dependencies{" "}
                      {yes(v.doubles_only_dependencies)}
                    </span>
                    {!!v.defects.length && (
                      <ul>
                        {v.defects.map((defect, j) => (
                          <li key={j}>{defect}</li>
                        ))}
                      </ul>
                    )}
                    {!!v.citations.length && (
                      <span className="row-subtitle">
                        cites{" "}
                        {v.citations
                          .map(
                            (c) =>
                              `${c.path}:${c.start_line ?? "?"}${c.end_line != null && c.end_line !== c.start_line ? `-${c.end_line}` : ""}`,
                          )
                          .join(", ")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Panel>
      )}
      <Panel title="Agents">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Calls</th>
                <th>Requests</th>
                <th>Input / output tokens</th>
                <th>Tool calls</th>
                <th>Retries</th>
                <th>Seconds</th>
                <th>Statuses</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(d.agents).map(([name, a]) => (
                <tr key={name}>
                  <td>
                    <b>{name}</b>
                    <span className="row-subtitle">
                      {a.models.join(", ")} · {a.prompt_versions.join(", ")}
                    </span>
                  </td>
                  <td className="numeric">{integer(a.calls)}</td>
                  <td className="numeric">{integer(a.requests)}</td>
                  <td className="numeric">
                    {integer(a.input_tokens)} / {integer(a.output_tokens)}
                  </td>
                  <td className="numeric">{integer(a.tool_calls)}</td>
                  <td className="numeric">{integer(a.retries)}</td>
                  <td className="numeric">{number(a.wall_s, 2)}</td>
                  <td>
                    {Object.entries(a.statuses).map(([status, n]) => (
                      <Badge
                        key={status}
                        tone={status === "ok" ? "success" : "warning"}
                      >
                        {status} {n}
                      </Badge>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-copy">
          Agent seconds sum recorded calls, not elapsed run time. Missing
          telemetry is unknown. Provider error text is not shown here; read
          usage.json in the record.
        </p>
      </Panel>
      <div className="detail-grid">
        <Panel title="Stage timeline">
          {d.timings.length ? (
            <ol className="timeline">
              {d.timings.map((t, i) => (
                <li key={i} className={t.error ? "error" : ""}>
                  <code>{t.step}</code>
                  <span className="numeric">{duration(t.wall_s)}</span>
                  {t.error && <Badge tone="warning">error</Badge>}
                </li>
              ))}
            </ol>
          ) : (
            <p className="panel-copy">No stage timings were recorded.</p>
          )}
        </Panel>
        <Panel title="Provenance" aside={<Badge>{d.record}</Badge>}>
          <dl className="identity">
            <div>
              <dt>Started / finished</dt>
              <dd>
                {timestamp(d.started)} / {timestamp(d.finished)}
              </dd>
            </div>
            {Object.entries(d.provenance)
              .filter(([key]) => key !== "environments")
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>
                    <code>{displayIdentity(value)}</code>
                  </dd>
                </div>
              ))}
            {Object.entries(d.provenance.environments ?? {}).map(
              ([name, env]) => (
                <div key={name}>
                  <dt>{name} environment</dt>
                  <dd>
                    <code>{displayIdentity(env)}</code>
                  </dd>
                </div>
              ),
            )}
          </dl>
        </Panel>
      </div>
      {source.kind === "eval" && (
        <p className="footnote">
          Stored at{" "}
          <code>
            {source.agent}/{source.eval_run}/evidence/runs/{source.receipt}
          </code>
          .{" "}
          <Link
            to={attemptPath(source.agent, source.eval_run, source.receipt)}
            className="text-link"
          >
            Permalink
          </Link>
        </p>
      )}
    </>
  );
}
