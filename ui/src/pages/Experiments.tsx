import { useState } from "react";
import {
  ArrowLeftRight,
  ArrowRight,
  FlaskConical,
  GitCompareArrows,
} from "lucide-react";
import { Badge, Heading, Notice, State, Status } from "../components/evidence";
import { ExperimentReview } from "../components/ExperimentReview";
import {
  type Evaluation,
  type EvaluationList,
  evaluationPath,
} from "../lib/data";
import { timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
import { useData } from "../lib/useData";
import "./experiments.css";
const keyOf = (run: Evaluation) => `${run.agent}/${run.run}`;
function RunSelection({
  label,
  value,
  onChange,
  runs,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  runs: Evaluation[];
}) {
  const selected = runs.find((run) => keyOf(run) === value);
  return (
    <section className="experiment-selection">
      <label>
        <span className="eyebrow">{label}</span>
        <select
          aria-label={`${label} run`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose a recorded run</option>
          {runs.map((run) => (
            <option key={keyOf(run)} value={keyOf(run)}>
              {run.agent} · {run.run}
            </option>
          ))}
        </select>
      </label>
      {selected ? (
        <>
          <div className="experiment-run-meta">
            <Badge>{selected.mode}</Badge>
            <Badge>{selected.set}</Badge>
            <Status run={selected} />
          </div>
          <p className="experiment-run-time">
            {timestamp(selected.command?.started)}
          </p>
          <Link className="text-link" to={evaluationPath(selected)}>
            Inspect original run <ArrowRight size={13} />
          </Link>
        </>
      ) : (
        <p className="experiment-run-time">
          No run selected.
        </p>
      )}
    </section>
  );
}
export function Experiments({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<EvaluationList>("/api/evaluations", revision);
  const [baselineId, setBaseline] = useState(""),
    [candidateId, setCandidate] = useState("");
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const runs = state.data.runs,
    baseline = runs.find((r) => keyOf(r) === baselineId),
    candidate = runs.find((r) => keyOf(r) === candidateId);
  return (
    <>
      <Heading
        eyebrow="Run comparison"
        title="Experiments"
        description="Compare outcomes, latency, token usage and configuration between two recorded runs."
      >
        <Badge>
          <GitCompareArrows size={13} />
          Read-only comparison
        </Badge>
      </Heading>
      {state.data.warnings.map((warning, i) => (
        <Notice tone="warning" key={i}>
          {warning}
        </Notice>
      ))}
      <div className="experiment-picker">
        <RunSelection
          label="Baseline"
          value={baseline?.agent ? baselineId : ""}
          onChange={setBaseline}
          runs={runs}
        />
        <button
          className="icon-button experiment-swap"
          aria-label="Swap baseline and candidate"
          disabled={!baseline || !candidate}
          onClick={() => {
            setBaseline(candidateId);
            setCandidate(baselineId);
          }}
        >
          <ArrowLeftRight size={19} />
        </button>
        <RunSelection
          label="Candidate"
          value={candidate?.agent ? candidateId : ""}
          onChange={setCandidate}
          runs={runs}
        />
      </div>
      <p className="experiment-selection-note">
        Selections are local to this view. No baseline is promoted and no
        evaluation is launched.
      </p>
      {baseline && candidate ? (
        <ExperimentReview baseline={baseline} candidate={candidate} />
      ) : (
        <div className="panel empty-state">
          <div className="empty-icon">
            <FlaskConical size={29} />
          </div>
          <h2>
            {runs.length < 2
              ? "At least two recorded runs are required"
              : "Select a baseline and candidate"}
          </h2>
          <p>
            {runs.length < 2
              ? "Run evaluations for the same agent, frozen dataset and provider mode."
              : "Outcome comparisons require the same agent, frozen dataset and provider mode. Recorded configuration differences are listed separately."}
          </p>
          {runs.length > 0 && (
            <Link to="/evaluations" className="text-link">
              Inspect recorded evaluations <ArrowRight size={14} />
            </Link>
          )}
        </div>
      )}
    </>
  );
}
