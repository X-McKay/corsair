import {
  ArrowRight,
  Boxes,
  FlaskConical,
  ShieldAlert,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import {
  type EvaluationList,
  type RunList,
  AGENTS,
  LABELS,
  evalStatus,
  labelCounts,
  latestByAgent,
} from "../lib/data";
import { integer } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";
import {
  Heading,
  Stats,
  Panel,
  EvalTable,
  RunTable,
  Empty,
  CopyCommand,
  Notice,
  LabelBadge,
} from "../components/evidence";

export function Overview({
  data,
  revision,
}: {
  data: EvaluationList;
  revision: number;
}) {
  const runs = useData<RunList>("/api/runs", revision);
  const records = runs.data?.runs ?? [];
  const counts = labelCounts(records);
  const live = latestByAgent(data.runs, "live");
  const attention = data.runs.filter(
    (run) => evalStatus(run) === "Needs attention",
  ).length;
  return (
    <>
      <Heading
        eyebrow="Corsair v2"
        title="Overview"
        description="Chain run records and per-agent eval runs, read from the configured record directories."
      />
      <Stats
        items={[
          {
            label: "Run records",
            value: runs.data ? integer(records.length) : "Unavailable",
            note: runs.error ? "Run storage unavailable" : "corsair-v2 run",
            icon: <ShieldAlert size={18} />,
          },
          {
            label: "Likely exploitable",
            value: runs.data
              ? integer(counts.LIKELY_EXPLOITABLE ?? 0)
              : "Unavailable",
            note: "Recorded verdicts",
            icon: <ShieldCheck size={18} />,
          },
          {
            label: "Eval runs",
            value: integer(data.runs.length),
            note: `${attention} need attention`,
            icon: <FlaskConical size={18} />,
          },
          {
            label: "Agents with a live run",
            value: `${live.size}/${AGENTS.length}`,
            note: "Six agents and the chain",
            icon: <Boxes size={18} />,
          },
        ]}
      />
      {!!records.length && (
        <div className="label-strip" aria-label="Run records by verdict">
          {[...LABELS, "incomplete", "cancelled"]
            .filter((key) => counts[key])
            .map((key) => (
              <span key={key}>
                {LABELS.includes(key as (typeof LABELS)[number]) ? (
                  <LabelBadge label={key} />
                ) : (
                  <b>{key}</b>
                )}{" "}
                {counts[key]}
              </span>
            ))}
        </div>
      )}
      <Panel
        title="Recent run records"
        aside={
          <Link to="/runs" className="text-link">
            View all <ArrowRight size={14} />
          </Link>
        }
      >
        {records.length ? (
          <RunTable runs={records.slice(0, 6)} />
        ) : runs.loading ? (
          <p className="panel-copy">Reading run records…</p>
        ) : (
          <Empty what="runs" />
        )}
      </Panel>
      <div className="overview-grid">
        <Panel
          title="Recent eval runs"
          aside={
            <Link to="/evaluations" className="text-link">
              View all <ArrowRight size={14} />
            </Link>
          }
        >
          {data.runs.length ? (
            <EvalTable runs={data.runs.slice(0, 6)} />
          ) : (
            <Empty />
          )}
        </Panel>
        <aside className="guide">
          <div className="guide-icon">
            <Terminal size={21} />
          </div>
          <div className="eyebrow">Command line</div>
          <h2>Measure a change</h2>
          <ol>
            <li>
              <b>Run the agent's eval</b>
              <span>Scripted by default; live with PROVIDER_CONFIG.</span>
            </li>
            <li>
              <b>Compare with its reference</b>
              <span>
                The promoted or committed baseline, else the previous run of
                the same set and mode.
              </span>
            </li>
            <li>
              <b>Run the chain</b>
              <span>Whole-chain verdicts against the evaluator's labels.</span>
            </li>
          </ol>
          <CopyCommand command="make eval AGENT=reviewer" />
          <Link to="/agents" className="text-link">
            Agents and baselines <ArrowRight size={14} />
          </Link>
        </aside>
      </div>
      <Notice>
        Scripted runs replay case oracles and check plumbing only. A verdict is
        the deterministic rule over recorded probe outcomes; it is not a claim
        about other revisions or environments.
      </Notice>
    </>
  );
}
