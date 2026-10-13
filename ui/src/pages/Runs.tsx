import { Workflow } from "lucide-react";
import { Badge, Heading, Notice, State } from "../components/evidence";
import { type WorkflowRuns } from "../lib/data";
import { timestamp } from "../lib/format";
import { useData } from "../lib/useData";

export function Runs({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<WorkflowRuns>("/api/runs", revision);
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const data = state.data;
  return (
    <>
      <Heading
        eyebrow="Temporal executions"
        title="Runs"
        description="Corsair investigation workflows in the configured Temporal namespace."
      />
      {data.status !== "available" ? (
        <div
          className="empty-state"
          role={data.status === "unavailable" ? "alert" : undefined}
        >
          <Workflow size={28} />
          <h2>
            {data.status === "not_configured"
              ? "Temporal is not configured"
              : "Unable to read workflows"}
          </h2>
          <p>{data.detail}</p>
          <button className="button" onClick={retry}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <Notice>{data.detail}</Notice>
          {data.runs.length ? (
            <section className="panel">
              <div className="table-scroll">
                <table className="workflow-table">
                  <thead>
                    <tr>
                      <th>Workflow / execution</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Finished</th>
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
                          <span>
                            {run.workflow_type ===
                            "corsair.fixture.Investigation"
                              ? "Fixture investigation"
                              : "Investigation"}
                          </span>
                          <code className="row-subtitle">
                            {run.workflow_type}
                          </code>
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <div className="empty-state">
              <Workflow size={28} />
              <h2>No Corsair workflows returned</h2>
              <p>
                The configured namespace has no visible investigation or fixture
                investigation workflows.
              </p>
            </div>
          )}
          {data.limited && (
            <Notice tone="warning">
              The workflow list is limited. Additional executions may exist in
              Temporal.
            </Notice>
          )}
        </>
      )}
      <Notice>
        Workflow status describes orchestration, not security correctness.
        Native workflow records do not include agent token usage or evaluator
        accuracy. Saved evaluation reports are shown separately under
        Evaluations and Agents.
      </Notice>
    </>
  );
}
