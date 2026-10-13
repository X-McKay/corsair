import {
  ArrowRight,
  Boxes,
  FlaskConical,
  Terminal,
  Zap,
  AlertCircle,
} from "lucide-react";
import { type EvaluationList, runStatus } from "../lib/data";
import { OverviewMetrics } from "../components/OverviewMetrics";
import { integer } from "../lib/format";
import { Link } from "../lib/navigation";
import {
  Heading,
  Stats,
  Panel,
  RunsTable,
  Empty,
  CopyCommand,
  Notice,
} from "../components/evidence";
export function Overview({
  data,
  revision,
  retry,
}: {
  data: EvaluationList;
  revision: number;
  retry: () => void;
}) {
  const agents = new Set(data.runs.map((run) => run.agent));
  const live = data.runs.filter((run) => run.mode === "live").length;
  const attention = data.runs.filter(
    (run) => runStatus(run) === "Needs attention",
  ).length;
  return (
    <>
      <Heading
        eyebrow="Recorded evaluations"
        title="Overview"
        description="Recorded runs, outcomes, latency and token usage."
      />
      <Stats
        items={[
          {
            label: "Recorded evaluations",
            value: integer(data.runs.length),
            note: "In the configured results directory",
            icon: <FlaskConical size={18} />,
          },
          {
            label: "Agents evaluated",
            value: integer(agents.size),
            note: "Distinct recorded agent suites",
            icon: <Boxes size={18} />,
          },
          {
            label: "Live model runs",
            value: integer(live),
            note: "Provider mode, not execution proof",
            icon: <Zap size={18} />,
          },
          {
            label: "Need attention",
            value: integer(attention),
            note: "Task, assertion or command failures",
            icon: <AlertCircle size={18} />,
          },
        ]}
      />
      {!!data.runs.length && (
        <OverviewMetrics
          revision={revision}
          retry={retry}
          shownWarnings={data.warnings}
        />
      )}
      <div className="overview-grid">
        <Panel
          title="Recent evaluations"
          aside={
            <Link to="/evaluations" className="text-link">
              View all <ArrowRight size={14} />
            </Link>
          }
        >
          {data.runs.length ? (
            <RunsTable runs={data.runs.slice(0, 6)} />
          ) : (
            <Empty />
          )}
        </Panel>
        <aside className="guide">
          <div className="guide-icon">
            <Terminal size={21} />
          </div>
          <div className="eyebrow">Command line</div>
          <h2>Run an evaluation</h2>
          <ol>
            <li>
              <b>Record a baseline</b>
              <span>
                Run a frozen case set for one agent and save results to the
                configured shared directory.
              </span>
            </li>
            <li>
              <b>Update the agent</b>
              <span>Change the prompt, skill, tool or budget.</span>
            </li>
            <li>
              <b>Compare results</b>
              <span>Review assertions, usage and timing.</span>
            </li>
          </ol>
          <p>
            Set <code>CORSAIR_EVAL_RESULTS</code> on the evaluation host to the
            shared results directory mounted by this UI.
          </p>
          <CopyCommand command="make eval AGENT=planning" />
          <Link to="/runtime" className="text-link">
            Inspect runtime evidence <ArrowRight size={14} />
          </Link>
        </aside>
      </div>
      <Notice>
        Clean attempts passed the recorded evaluators. Scripted checks and live
        model runs do not, on their own, prove application behavior or sandbox
        readiness.
      </Notice>
    </>
  );
}
