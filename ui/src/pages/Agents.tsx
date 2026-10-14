import { ArrowUpRight } from "lucide-react";
import {
  type Baseline,
  type Evaluation,
  type EvaluationList,
  AGENTS,
  evaluationPath,
  latestByAgent,
} from "../lib/data";
import { duration, number, percent, timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";
import {
  Badge,
  CopyCommand,
  Heading,
  Notice,
  PolicyBadge,
  RatioBadge,
  Status,
} from "../components/evidence";
import "./metrics.css";

const ROLE: Record<string, string> = {
  grounding: "Placeholder; the Investigator does not read it until baselined",
  investigator: "Identifies the target and plans the probe pair",
  builder: "Builds the environment once; a trusted replay reuses its recipe",
  control_prober: "Writes the benign control test",
  exploit_prober: "Writes the proof-of-vulnerability test",
  reviewer: "Outcome-blind review of the frozen pair",
  chain: "The whole chain against evaluator labels",
};

function RunSummary({ run, title }: { run?: Evaluation; title: string }) {
  if (!run)
    return (
      <div className="agent-stat">
        <span>{title}</span>
        <strong>None</strong>
        <small>No whole-set run recorded</small>
      </div>
    );
  const o = run.overall;
  return (
    <div className="agent-stat">
      <span>{title}</span>
      <strong>
        <Link to={evaluationPath(run)} className="row-title">
          {o?.attempts != null ? `${o.clean_attempts}/${o.attempts}` : "Incomplete"}
          <ArrowUpRight size={13} />
        </Link>
      </strong>
      <small>
        {timestamp(run.command.started)} · <Status run={run} />
      </small>
      <small>
        {o?.dispositions
          ? `decisive ${percent(o.dispositions.decisive_rate)} · `
          : ""}
        p50 {duration(o?.metrics.wall_s?.p50)} · mean tokens{" "}
        {number(o?.metrics.tokens?.mean, 0)}
      </small>
    </div>
  );
}

export function Agents({
  data,
  revision,
}: {
  data: EvaluationList;
  revision: number;
}) {
  const baselines = useData<{ baselines: Baseline[] }>(
    "/api/baselines",
    revision,
  );
  const scripted = latestByAgent(data.runs, "scripted");
  const live = latestByAgent(data.runs, "live");
  return (
    <>
      <Heading
        eyebrow="Isolated evaluation"
        title="Agents"
        description="The latest whole-set scripted and live run of each agent and of the chain, and their baselines."
      />
      <Notice>
        Every agent is evaluated alone on the host with its frozen sets. A
        baseline is a live run a person chose; committed baselines live beside
        the agent's cases.
      </Notice>
      <div className="agent-cards">
        {AGENTS.map((agent) => {
          const own = (baselines.data?.baselines ?? []).filter(
            (b) => b.agent === agent,
          );
          const dims = live.get(agent)?.overall?.dimensions ?? {};
          return (
            <article className="agent-card" key={agent}>
              <div className="agent-card-heading">
                <div>
                  <h2>{agent}</h2>
                  <p>{ROLE[agent]}</p>
                </div>
                {own.some((b) => b.source === "committed") ? (
                  <Badge tone="success">Committed baseline</Badge>
                ) : (
                  <Badge tone="warning">No committed baseline</Badge>
                )}
              </div>
              <div className="agent-card-body agent-card-runs">
                <RunSummary title="Latest live run" run={live.get(agent)} />
                <RunSummary title="Latest scripted run" run={scripted.get(agent)} />
                <div className="agent-stat">
                  <span>Baselines</span>
                  {own.length ? (
                    own.map((b) => (
                      <small key={`${b.source}/${b.set}/${b.mode}`}>
                        {b.source} {b.set}/{b.mode}:{" "}
                        <code>{b.run}</code>{" "}
                        {b.source === "committed" && (
                          <PolicyBadge status={b.policy_status} />
                        )}
                      </small>
                    ))
                  ) : (
                    <small>
                      {baselines.error ? "Unavailable" : "None recorded"}
                    </small>
                  )}
                </div>
              </div>
              {!!Object.keys(dims).length && (
                <div className="agent-dimensions">
                  {Object.entries(dims).map(([name, value]) => (
                    <span key={name}>
                      {name} <RatioBadge value={value} />
                    </span>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
      <h2 className="system-section-title">Commit a baseline</h2>
      <CopyCommand command="make baseline-commit AGENT=<agent> RUN=<live run id>" />
      <p className="footnote">
        Only a whole-set live run from a clean checkout qualifies. Language-
        narrowed runs are shown under Evaluations but never as an agent's
        latest run.
      </p>
    </>
  );
}
