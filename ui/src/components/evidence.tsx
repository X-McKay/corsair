import { useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleHelp,
  Copy,
  FlaskConical,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import {
  type Evaluation,
  type Ratio,
  type RunRow,
  evaluationPath,
  evalStatus,
  labelText,
  labelTone,
  ratioLabel,
  ratioTone,
  runPath,
} from "../lib/data";
import { duration, integer, timestamp } from "../lib/format";
import { Link } from "../lib/navigation";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Status({ run }: { run: Evaluation }) {
  const status = evalStatus(run);
  return (
    <Badge
      tone={
        status === "Clean"
          ? "success"
          : status === "Incomplete"
            ? "neutral"
            : "warning"
      }
    >
      <span className="status-dot" />
      {status}
    </Badge>
  );
}
export function Heading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div className={`notice ${tone}`}>
      <CircleHelp size={17} />
      <div>{children}</div>
    </div>
  );
}
export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  return (
    <div className="command">
      <code>{command}</code>
      <button
        className="icon-button"
        aria-label={`Copy ${command}`}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(command);
            setCopied(true);
            setError(false);
            setTimeout(() => setCopied(false), 2000);
          } catch {
            setError(true);
          }
        }}
      >
        {copied ? <Check size={16} /> : <Copy size={16} />}
      </button>
      <span className="sr-only" role="status">
        {copied
          ? "Command copied"
          : error
            ? "Copy unavailable. Select the command to copy it manually."
            : ""}
      </span>
    </div>
  );
}
export function State({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error?: string;
  retry: () => void;
}) {
  return (
    <div className="empty-state" role={error ? "alert" : "status"}>
      {loading ? (
        <RefreshCw size={26} className="spin" />
      ) : (
        <AlertCircle size={28} />
      )}
      <h2>{loading ? "Reading evidence…" : "Unable to load evidence"}</h2>
      <p>
        {loading
          ? "Loading records from the configured Corsair service."
          : error}
      </p>
      {error && (
        <>
          <p>
            Check that the Corsair UI service is running and the configured
            record directories are accessible.
          </p>
          <button className="button" onClick={retry}>
            <RefreshCw size={15} />
            Try again
          </button>
        </>
      )}
    </div>
  );
}
export function Empty({
  filtered = false,
  what = "evaluations",
}: {
  filtered?: boolean;
  what?: "evaluations" | "runs";
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <FlaskConical size={30} />
      </div>
      <h2>
        {filtered ? `No matching ${what}` : `No recorded ${what}`}
      </h2>
      <p>
        {filtered
          ? "Try another filter or search term."
          : what === "runs"
            ? "Investigate a case with the v2 chain; each run writes one record directory that appears here."
            : "Run an agent's isolated eval on the host; each run writes its summary, policy and comparison here."}
      </p>
      {!filtered && (
        <>
          <CopyCommand
            command={
              what === "runs"
                ? "uv run --locked corsair-v2 run --case <case>"
                : "make eval AGENT=chain"
            }
          />
          <small>
            {what === "runs"
              ? "Needs a provider config and Docker · writes .runs/v2/runs"
              : "Host-only · scripted by default · writes .runs/evals"}
          </small>
        </>
      )}
    </div>
  );
}
export function RatioBadge({ value }: { value: Ratio | null | undefined }) {
  return <Badge tone={ratioTone(value)}>{ratioLabel(value)}</Badge>;
}
export function LabelBadge({ label }: { label: string | null | undefined }) {
  return <Badge tone={labelTone(label)}>{labelText(label)}</Badge>;
}
export function CleanBar({ run }: { run: Evaluation }) {
  const attempts = run.overall?.attempts;
  const clean = run.overall?.clean_attempts;
  const known = attempts != null && attempts > 0 && clean != null;
  return (
    <div className="clean-cell">
      <progress
        className="bar"
        aria-hidden="true"
        max={known ? attempts : 1}
        value={known ? clean : 0}
      />
      <span>{known ? `${clean}/${attempts}` : "Unavailable"}</span>
    </div>
  );
}
export function EvalTable({ runs }: { runs: Evaluation[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Agent / run</th>
            <th>Set / mode</th>
            <th>Clean attempts</th>
            <th>p50 wall time</th>
            <th>Policy</th>
            <th>Status</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={`${run.agent}/${run.run}`}>
              <td>
                <Link to={evaluationPath(run)} className="row-title">
                  {run.agent}
                  <ArrowUpRight size={13} />
                </Link>
                <span className="row-subtitle" title={run.run}>
                  {run.run}
                </span>
              </td>
              <td>
                <Badge tone={run.mode === "live" ? "info" : "neutral"}>
                  {run.mode ?? "unknown"}
                </Badge>
                <span className="row-subtitle">
                  {run.set}
                  {run.language ? ` · ${run.language} only` : ""}
                </span>
              </td>
              <td>
                <CleanBar run={run} />
              </td>
              <td className="numeric">
                {duration(run.overall?.metrics.wall_s?.p50)}
              </td>
              <td>
                <PolicyBadge status={run.policy} />
              </td>
              <td>
                <Status run={run} />
              </td>
              <td>
                <Link to={evaluationPath(run)} className="row-arrow">
                  <ChevronRight size={18} />
                  <span className="sr-only">Inspect {run.run}</span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function PolicyBadge({ status }: { status: string | null | undefined }) {
  return (
    <Badge
      tone={
        status === "pass"
          ? "success"
          : status === "fail"
            ? "warning"
            : "neutral"
      }
    >
      {status ? status.replaceAll("_", " ") : "no policy"}
    </Badge>
  );
}
export function RunTable({
  runs,
  link = (run: RunRow) => runPath(run.id),
  expected,
}: {
  runs: RunRow[];
  link?: (run: RunRow) => string;
  expected?: (run: RunRow) => string | null;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Case / run</th>
            <th>Verdict</th>
            <th>Rule / reason</th>
            <th>Runtime</th>
            <th>Wall time</th>
            <th>Tokens</th>
            <th>Started</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <Link to={link(run)} className="row-title">
                  {run.case ?? "unknown case"}
                  <ArrowUpRight size={13} />
                </Link>
                <span className="row-subtitle" title={run.run}>
                  {run.run}
                </span>
              </td>
              <td>
                {run.label ? (
                  <LabelBadge label={run.label} />
                ) : (
                  <Badge>{run.state}</Badge>
                )}
                {expected && expected(run) && (
                  <span className="row-subtitle">
                    expected {labelText(expected(run))}
                  </span>
                )}
              </td>
              <td>
                <code>{run.rule ?? "-"}</code>
                <span className="row-subtitle">{run.reason ?? ""}</span>
              </td>
              <td>
                <span className="row-subtitle">{run.runtime_row ?? "none"}</span>
              </td>
              <td className="numeric">{duration(run.totals.wall_s)}</td>
              <td className="numeric">{integer(run.totals.tokens)}</td>
              <td>{timestamp(run.started)}</td>
              <td>
                <Link to={link(run)} className="row-arrow">
                  <ChevronRight size={18} />
                  <span className="sr-only">Inspect {run.run}</span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Stats({
  items,
}: {
  items: { label: string; value: ReactNode; note: string; icon: ReactNode }[];
}) {
  return (
    <div className="stats">
      {items.map((item) => (
        <div className="stat" key={item.label}>
          <div className="stat-label">
            {item.label}
            {item.icon}
          </div>
          <div className="stat-value">{item.value}</div>
          <div className="stat-note">{item.note}</div>
        </div>
      ))}
    </div>
  );
}
