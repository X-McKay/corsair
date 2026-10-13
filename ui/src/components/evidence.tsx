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
  type Summary,
  evaluationPath,
  metric,
  runStatus,
} from "../lib/data";
import { duration } from "../lib/format";
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
  const status = runStatus(run);
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
      <h2>{loading ? "Reading local evidence…" : "Unable to load evidence"}</h2>
      <p>
        {loading ? "Loading recorded evaluations from this workspace." : error}
      </p>
      {error && (
        <>
          <p>
            Check that the Corsair UI service is running and the configured
            evidence directory is accessible.
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
export function Empty({ filtered = false }: { filtered?: boolean }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <FlaskConical size={30} />
      </div>
      <h2>
        {filtered
          ? "No matching evaluations"
          : "No recorded evaluations"}
      </h2>
      <p>
        {filtered
          ? "Try another agent, evidence mode, or search term."
          : "Run an isolated agent evaluation to see its assertions, timing and recorded token usage here."}
      </p>
      {!filtered && (
        <>
          <CopyCommand command="make eval AGENT=identification" />
          <small>Host-only · Scripted by default · No model calls</small>
        </>
      )}
    </div>
  );
}
export function CleanBar({ summary }: { summary: Summary }) {
  const { attempts, clean_attempts } = summary;
  const known =
    typeof attempts === "number" &&
    attempts > 0 &&
    typeof clean_attempts === "number";
  return (
    <div className="clean-cell">
      <progress
        className="bar"
        aria-hidden="true"
        max={known ? attempts : 1}
        value={known ? clean_attempts : 0}
      />
      <span>{known ? `${clean_attempts}/${attempts}` : "Unavailable"}</span>
    </div>
  );
}
export function RunsTable({ runs }: { runs: Evaluation[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Agent / run</th>
            <th>Evidence mode</th>
            <th>Clean attempts</th>
            <th>Mean task time</th>
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
                  {run.mode}
                </Badge>
                <span className="row-subtitle">{run.set}</span>
              </td>
              <td>
                <CleanBar summary={run.summary} />
              </td>
              <td className="numeric">
                {duration(metric(run.summary, "task_seconds")?.value)}
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
