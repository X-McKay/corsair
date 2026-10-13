import { useState } from "react";
import { Search } from "lucide-react";
import { type EvaluationList, matches } from "../lib/data";
import { Heading, Panel, RunsTable, Empty } from "../components/evidence";
export function Evaluations({ data }: { data: EvaluationList }) {
  const [query, setQuery] = useState("");
  const [agent, setAgent] = useState("");
  const [mode, setMode] = useState("");
  const [status, setStatus] = useState("");
  const filtered = data.runs.filter((run) =>
    matches(run, query, agent, mode, status),
  );
  const active = !!(query || agent || mode || status);
  return (
    <>
      <Heading
        eyebrow="Measure · compare · improve"
        title="Evaluations"
        description="Inspect each run on its own terms: cases, assertions, telemetry and identity."
      />
      <div className="filter-bar">
        <label className="search">
          <Search size={17} />
          <input
            type="search"
            placeholder="Search agents, runs or models…"
            aria-label="Search evaluations"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          aria-label="Filter agent"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
        >
          <option value="">All agents</option>
          {[...new Set(data.runs.map((r) => r.agent))].sort().map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <select
          aria-label="Filter evidence mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="">All modes</option>
          {[...new Set(data.runs.map((r) => r.mode))].sort().map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
        <select
          aria-label="Filter status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          {["Clean", "Needs attention", "Incomplete"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        {active && (
          <button
            className="button subtle"
            onClick={() => {
              setQuery("");
              setAgent("");
              setMode("");
              setStatus("");
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      <Panel
        title="Run history"
        aside={
          <span className="muted" aria-live="polite">
            {filtered.length}{" "}
            {filtered.length === 1 ? "evaluation" : "evaluations"}
          </span>
        }
      >
        {filtered.length ? (
          <RunsTable runs={filtered} />
        ) : (
          <Empty filtered={active} />
        )}
      </Panel>
      <p className="footnote">
        Means reflect observed samples only. Open a run to check coverage before
        comparing measurements.
      </p>
    </>
  );
}
