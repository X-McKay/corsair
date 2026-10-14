import { useState } from "react";
import { Search, Workflow } from "lucide-react";
import {
  Badge,
  Empty,
  Heading,
  Notice,
  Panel,
  RunTable,
  State,
} from "../components/evidence";
import {
  type RunList,
  type WorkflowRuns,
  LABELS,
  labelText,
  runPath,
} from "../lib/data";
import { timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";

export function Runs({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<RunList>("/api/runs", revision);
  const [query, setQuery] = useState("");
  const [label, setLabel] = useState("");
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const data = state.data;
  const filtered = data.runs.filter(
    (run) =>
      (!label || (run.label ?? run.state) === label) &&
      [run.run, run.case, run.rule, run.reason, run.runtime_row, ...run.models]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const active = !!(query || label);
  return (
    <>
      <Heading
        eyebrow="corsair-v2-run/1"
        title="Runs"
        description="One record per chain run: verdict, probe outcomes, review, cost and provenance."
      />
      {data.warnings.map((warning, i) => (
        <Notice key={i} tone="warning">
          {warning}
        </Notice>
      ))}
      <div className="filter-bar">
        <label className="search">
          <Search size={17} />
          <input
            type="search"
            placeholder="Search cases, runs, rules or runtimes…"
            aria-label="Search runs"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          aria-label="Filter verdict"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        >
          <option value="">All verdicts</option>
          {LABELS.map((value) => (
            <option key={value} value={value}>
              {labelText(value)}
            </option>
          ))}
          <option value="incomplete">incomplete record</option>
          <option value="cancelled">cancelled</option>
        </select>
        {active && (
          <button
            className="button subtle"
            onClick={() => {
              setQuery("");
              setLabel("");
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      <Panel
        title="Run records"
        aside={
          <span className="muted" aria-live="polite">
            {filtered.length} {filtered.length === 1 ? "run" : "runs"}
          </span>
        }
      >
        {filtered.length ? (
          <RunTable runs={filtered} />
        ) : (
          <Empty what="runs" filtered={active} />
        )}
      </Panel>
      <Notice>
        An incomplete record proves only that the run did not write its
        verdict, never that a process or workflow is still running.
      </Notice>
      <Workflows revision={revision} retry={retry} />
    </>
  );
}

function Workflows({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<WorkflowRuns>("/api/workflows", revision);
  const data = state.data;
  return (
    <Panel
      title="Temporal executions"
      aside={<code className="muted">corsair.v2.Investigation</code>}
    >
      {!data ? (
        <p className="panel-copy" role={state.error ? "alert" : "status"}>
          {state.error ?? "Reading workflow visibility…"}
        </p>
      ) : data.status !== "available" ? (
        <div className="panel-copy">
          <p role={data.status === "unavailable" ? "alert" : undefined}>
            <Workflow size={15} /> {data.detail}
          </p>
          {data.status === "unavailable" && (
            <button className="button" onClick={retry}>
              Try again
            </button>
          )}
        </div>
      ) : data.runs.length ? (
        <>
          <div className="table-scroll">
            <table className="workflow-table">
              <thead>
                <tr>
                  <th>Workflow / execution</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Finished</th>
                  <th>Record</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => (
                  <tr key={`${run.id}/${run.run_id}`}>
                    <td>
                      <strong className="workflow-id">{run.id}</strong>
                      <code className="row-subtitle">{run.run_id}</code>
                    </td>
                    <td>
                      <Badge
                        tone={
                          run.status === "COMPLETED"
                            ? "success"
                            : [
                                  "FAILED",
                                  "TIMED_OUT",
                                  "TERMINATED",
                                  "CANCELED",
                                ].includes(run.status)
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {run.status.replaceAll("_", " ")}
                      </Badge>
                    </td>
                    <td>{timestamp(run.started)}</td>
                    <td>{timestamp(run.ended)}</td>
                    <td>
                      {run.record ? (
                        <Link to={runPath(run.record)} className="text-link">
                          Run record
                        </Link>
                      ) : (
                        <span className="muted">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.limited && (
            <Notice tone="warning">
              The workflow list is limited. Additional executions may exist in
              Temporal.
            </Notice>
          )}
          <p className="panel-copy">{data.detail}</p>
        </>
      ) : (
        <p className="panel-copy">
          The configured namespace has no visible v2 investigation workflows.
        </p>
      )}
    </Panel>
  );
}
