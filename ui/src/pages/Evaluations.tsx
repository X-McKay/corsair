import { useState } from "react";
import { Search } from "lucide-react";
import { type EvaluationList, matches } from "../lib/data";
import { Heading, Panel, EvalTable, Empty } from "../components/evidence";
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
        eyebrow="corsair-eval-summary/v1"
        title="Evaluations"
        description="Each agent's isolated eval and the whole-chain eval: dimensions, dispositions, efficiency and release policy."
      />
      <div className="filter-bar">
        <label className="search">
          <Search size={17} />
          <input
            type="search"
            placeholder="Search agents, runs, sets or notes…"
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
          aria-label="Filter mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="">All modes</option>
          {[...new Set(data.runs.map((r) => r.mode ?? ""))]
            .filter(Boolean)
            .sort()
            .map((m) => (
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
        title="Eval runs"
        aside={
          <span className="muted" aria-live="polite">
            {filtered.length} {filtered.length === 1 ? "run" : "runs"}
          </span>
        }
      >
        {filtered.length ? (
          <EvalTable runs={filtered} />
        ) : (
          <Empty filtered={active} />
        )}
      </Panel>
      <p className="footnote">
        Efficiency statistics use observed samples only. While release gates
        are deferred, policy status never changes a run's exit code.
      </p>
    </>
  );
}
