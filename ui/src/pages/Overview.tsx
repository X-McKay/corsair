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
        eyebrow="Your evaluation workspace"
        title="See how your agents perform."
        description="Trace every result to its evidence. Find the next improvement."
      />
      <Stats
        items={[
          {
            label: "Recorded evaluations",
            value: integer(data.runs.length),
            note: "In this local workspace",
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
          <div className="eyebrow">The improvement loop</div>
          <h2>
            One change.
            <br />
            Measurable progress.
          </h2>
          <ol>
            <li>
              <b>Establish a baseline</b>
              <span>Run a frozen case set for one agent.</span>
            </li>
            <li>
              <b>Make a focused change</b>
              <span>Refine a prompt, skill, tool or budget.</span>
            </li>
            <li>
              <b>Check the evidence</b>
              <span>Review assertions, usage and timing.</span>
            </li>
          </ol>
          <CopyCommand command="make eval AGENT=planning" />
          <Link to="/runtime" className="text-link">
            Inspect runtime evidence <ArrowRight size={14} />
          </Link>
        </aside>
      </div>
      <Notice>
        <strong>Evidence before conclusions.</strong> Clean attempts passed the
        recorded evaluators. Scripted checks and live model runs do not, on
        their own, prove application behavior or sandbox readiness.
      </Notice>
    </>
  );
}
