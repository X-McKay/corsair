import { ArrowRight } from "lucide-react";
import { Badge, Notice, Panel } from "./evidence";
import { type Evaluation, displayIdentity } from "../lib/data";
import {
  compareCases,
  comparisonBlockers,
  completion,
  fraction,
  identityDifferences,
  meanDifference,
} from "../lib/comparison";
import { number, duration } from "../lib/format";
const percent = (value: number | null) =>
  value === null ? "Unavailable" : `${number(value * 100)}%`;
const delta = (value: number | null, suffix = "") =>
  value === null
    ? "Unavailable"
    : `${value > 0 ? "+" : ""}${number(value)}${suffix}`;
function Outcome({
  label,
  before,
  after,
  blocked,
}: {
  label: string;
  before: number | null;
  after: number | null;
  blocked: boolean;
}) {
  return (
    <div className="experiment-outcome">
      <span className="stat-label">{label}</span>
      <div className="experiment-outcome-values">
        <span>
          {percent(before)}
          <small>Baseline</small>
        </span>
        <ArrowRight size={17} />
        <span>
          {percent(after)}
          <small>Candidate</small>
        </span>
      </div>
      <p>
        {blocked
          ? "Comparison unavailable"
          : before === null || after === null
            ? "Change unavailable"
            : `${delta((after - before) * 100, " pp")} recorded change`}
      </p>
    </div>
  );
}
export function ExperimentReview({
  baseline,
  candidate,
}: {
  baseline: Evaluation;
  candidate: Evaluation;
}) {
  // A missing report makes retained counts/means unusable, even if stale fields remain.
  baseline =
    baseline.summary.report === "missing"
      ? {
          ...baseline,
          summary: { identity: baseline.summary.identity, report: "missing" },
        }
      : baseline;
  candidate =
    candidate.summary.report === "missing"
      ? {
          ...candidate,
          summary: { identity: candidate.summary.identity, report: "missing" },
        }
      : candidate;
  const blockers = comparisonBlockers(baseline, candidate),
    blocked = blockers.length > 0;
  const changes = identityDifferences(baseline, candidate),
    cases = compareCases(baseline, candidate);
  const metrics = [
    ...new Set([
      ...Object.keys(baseline.summary.efficiency_mean ?? {}),
      ...Object.keys(candidate.summary.efficiency_mean ?? {}),
    ]),
  ].sort();
  const coverage = (run: Evaluation, key: string) => {
    const c = run.summary.efficiency_samples?.[key];
    return c
      ? `${c.observed}/${c.attempts} observed${c.observed < c.attempts ? " · partial" : ""}`
      : "Coverage unavailable";
  };
  return (
    <>
      {blocked ? (
        <Notice tone="warning">
          <strong>These runs cannot support an outcome comparison.</strong>
          <ul>
            {blockers.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          Individual values remain visible; improvement and regression labels
          are withheld.
        </Notice>
      ) : (
        <Notice>
          <strong>
            Same recorded agent, case set, provider mode and dataset digest.
          </strong>{" "}
          Changes below are descriptive, not a paired experiment or proof of
          causation. Evaluator identity, effective provider settings and
          concurrency are not fully retained by the current summary format.
        </Notice>
      )}
      <div className="experiment-outcomes">
        <Outcome
          label="Evaluator success"
          before={fraction(
            baseline.summary.clean_attempts,
            baseline.summary.attempts,
          )}
          after={fraction(
            candidate.summary.clean_attempts,
            candidate.summary.attempts,
          )}
          blocked={blocked}
        />
        <Outcome
          label="Task completion"
          before={completion(baseline.summary)}
          after={completion(candidate.summary)}
          blocked={blocked}
        />
        <div className="experiment-outcome">
          <span className="stat-label">Case-level changes</span>
          <div className="experiment-case-totals">
            <span>
              <b>
                {blocked
                  ? "—"
                  : cases.filter((c) => c.change === "Improved").length}
              </b>{" "}
              improved
            </span>
            <span>
              <b>
                {blocked
                  ? "—"
                  : cases.filter((c) => c.change === "Regressed").length}
              </b>{" "}
              regressed
            </span>
          </div>
          <p>
            {blocked
              ? "Unavailable for incompatible runs"
              : `${cases.filter((c) => c.change === "Unknown").length} cases lack comparable counts`}
          </p>
        </div>
      </div>
      <Panel
        title="What changed"
        aside={<Badge>{changes.length} recorded identity differences</Badge>}
      >
        {changes.length ? (
          <div className="table-scroll">
            <table className="experiment-table">
              <thead>
                <tr>
                  <th>Identity field</th>
                  <th>Baseline</th>
                  <th>Candidate</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((change) => (
                  <tr key={change.key}>
                    <td>
                      <code>{change.key}</code>
                    </td>
                    <td>
                      <code>{displayIdentity(change.before)}</code>
                    </td>
                    <td>
                      <code>{displayIdentity(change.after)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="panel-copy">
            No differences in retained identity fields. This does not establish
            identical effective settings or evaluators.
          </p>
        )}
        <p className="experiment-panel-note">
          A changed prompt or model can be the intended experiment. Review
          changed configuration and execution identities before attributing
          outcomes to any one variable. Missing fields are unavailable, not
          equal.
        </p>
      </Panel>
      <Panel title="Cases" aside={<Badge>Recorded success rates</Badge>}>
        {cases.length ? (
          <div className="table-scroll">
            <table className="experiment-table">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Baseline clean</th>
                  <th>Candidate clean</th>
                  <th>Change</th>
                  <th>Assessment</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr key={c.name}>
                    <td className="experiment-case-name">{c.name}</td>
                    <td>
                      {c.beforeCount}
                      <span className="row-subtitle">{percent(c.before)}</span>
                    </td>
                    <td>
                      {c.afterCount}
                      <span className="row-subtitle">{percent(c.after)}</span>
                    </td>
                    <td>
                      {delta(c.delta === null ? null : c.delta * 100, " pp")}
                    </td>
                    <td>
                      <Badge
                        tone={
                          c.change === "Regressed"
                            ? "warning"
                            : c.change === "Improved"
                              ? "success"
                              : "neutral"
                        }
                      >
                        {c.change}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="panel-copy">Neither run retained per-case counts.</p>
        )}
        <p className="experiment-panel-note">
          Clean means every recorded evaluator passed. Rates account for
          different attempt counts; repeats are not paired. A case absent from
          either run has an unknown change. These labels do not establish
          semantic accuracy or application execution.
        </p>
      </Panel>
      <Panel title="Efficiency" aside={<Badge>Mean per observed sample</Badge>}>
        {metrics.length ? (
          <div className="table-scroll">
            <table className="experiment-table">
              <thead>
                <tr>
                  <th>Recorded metric</th>
                  <th>Baseline</th>
                  <th>Candidate</th>
                  <th>Candidate − baseline</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((key) => {
                  const format = key.includes("seconds") ? duration : number;
                  return (
                    <tr key={key}>
                      <td>
                        <code>{key}</code>
                      </td>
                      <td>
                        {format(baseline.summary.efficiency_mean?.[key])}
                        <span className="row-subtitle">
                          {coverage(baseline, key)}
                        </span>
                      </td>
                      <td>
                        {format(candidate.summary.efficiency_mean?.[key])}
                        <span className="row-subtitle">
                          {coverage(candidate, key)}
                        </span>
                      </td>
                      <td>
                        {blocked
                          ? "Unavailable"
                          : delta(
                              meanDifference(
                                baseline.summary,
                                candidate.summary,
                                key,
                              ),
                              key.includes("seconds") ? " s" : "",
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
            No efficiency measurements were retained. Token usage and latency
            are unknown.
          </p>
        )}
        <p className="experiment-panel-note">
          Means use only observed samples and may omit failed attempts.
          Different or missing coverage can explain a change; summary means
          cannot reconstruct token totals or latency distributions.
        </p>
      </Panel>
    </>
  );
}
