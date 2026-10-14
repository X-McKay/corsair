import { Boxes, ChevronRight } from "lucide-react";
import { type RuntimeData } from "../lib/data";
import { useData } from "../lib/useData";
import { Badge, Heading, Notice, State } from "../components/evidence";

const TONE: Record<string, string> = {
  live: "success",
  "image-only": "info",
  "canary-only": "warning",
};

export function Runtime({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<RuntimeData>("/api/runtime", revision);
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const data = state.data;
  return (
    <>
      <Heading
        eyebrow="Operator-owned configuration"
        title="Runtime matrix"
        description="One row per image and test framework: how trusted code selects a runtime and runs one test."
      />
      <div className="detail-meta">
        <span>
          Schema <code>{data.schema}</code>
        </span>
        <span>
          sha256 <code>{data.sha256.slice(0, 16)}</code>
        </span>
        <span className="muted">
          A run record's matrix_sha256 names the matrix it selected from.
        </span>
      </div>
      <div className="runtime-grid">
        {data.rows.map((row) => (
          <article className="panel runtime-card" key={row.id}>
            <div className="runtime-heading">
              <div className="runtime-icon">
                <Boxes size={23} />
              </div>
              <Badge tone={TONE[row.evidence] ?? "neutral"}>
                {row.evidence}
              </Badge>
            </div>
            <div className="eyebrow">{row.language}</div>
            <h2>
              {row.framework} <span>{row.skill}</span>
            </h2>
            <p className="mono muted">{row.id}</p>
            <div className="frameworks">
              {row.detect.map((d, i) => (
                <div key={i}>
                  <strong>detect</strong>
                  <code>
                    {d.file}
                    {d.contains ? ` ∋ ${d.contains}` : ""}
                  </code>
                </div>
              ))}
            </div>
            <details>
              <summary>
                Image, run template and exit codes <ChevronRight size={15} />
              </summary>
              <div className="runtime-evidence">
                <p>{row.note}</p>
                <dl>
                  <dt>Image</dt>
                  <dd>
                    <code>{row.image}</code>
                  </dd>
                  <dt>Base image</dt>
                  <dd>
                    <code>{row.base_image ?? "Unavailable"}</code>
                  </dd>
                  <dt>Image source</dt>
                  <dd>
                    <code>{row.image_source ?? "Unavailable"}</code>
                  </dd>
                  <dt>Run template</dt>
                  <dd>
                    <code>{row.run_template.join(" ")}</code>
                  </dd>
                  <dt>Exit codes</dt>
                  <dd>
                    {Object.entries(row.exit_codes)
                      .map(([code, cls]) => `${code} ${cls}`)
                      .join(", ")}
                  </dd>
                  <dt>Build network</dt>
                  <dd>{row.build_network_hosts.join(", ") || "None"}</dd>
                  <dt>Syntax check</dt>
                  <dd>
                    <code>{row.syntax_check?.join(" ") ?? "None"}</code>
                  </dd>
                </dl>
              </div>
            </details>
          </article>
        ))}
      </div>
      {!data.rows.length && (
        <div className="empty-state">
          <Boxes size={28} />
          <h2>No registered runtimes</h2>
        </div>
      )}
      {data.limitations.map((text, i) => (
        <Notice key={i}>{text}</Notice>
      ))}
    </>
  );
}
