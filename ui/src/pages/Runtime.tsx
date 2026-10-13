import { Boxes, ChevronRight } from "lucide-react";
import { type RuntimeData } from "../lib/data";
import { useData } from "../lib/useData";
import { Badge, Heading, Notice, State } from "../components/evidence";
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
  return (
    <>
      <Heading
        eyebrow="Operator-owned configuration"
        title="Runtime readiness"
        description="Registered images and the evidence behind their supported frameworks."
      />
      <Notice>
        <strong>Registration is not current availability.</strong> This is the
        checked-in runtime matrix, not a live cluster or image registry probe.
        Image-only evidence does not qualify OpenShell execution.
      </Notice>
      <div className="runtime-grid">
        {state.data.rows.map((row) => (
          <article className="panel runtime-card" key={row.id}>
            <div className="runtime-heading">
              <div className="runtime-icon">
                <Boxes size={23} />
              </div>
              <Badge
                tone={
                  row.qualification.evidence === "live" ? "success" : "warning"
                }
              >
                {row.qualification.evidence === "live"
                  ? "Live evidence"
                  : "Image-only"}
              </Badge>
            </div>
            <div className="eyebrow">{row.language}</div>
            <h2>
              {row.runtime.name} <span>{row.runtime.version}</span>
            </h2>
            <p className="mono muted">{row.id}</p>
            <div className="frameworks">
              {row.frameworks?.map((f) => (
                <div key={`${f.name}/${f.versions}`}>
                  <strong>{f.name}</strong>
                  <code>{f.versions}</code>
                  <Badge
                    tone={
                      f.qualification.evidence === "live"
                        ? "success"
                        : "warning"
                    }
                  >
                    {f.qualification.evidence}
                  </Badge>
                </div>
              ))}
              {!row.frameworks?.length && (
                <p className="muted">No registered framework range.</p>
              )}
            </div>
            <details>
              <summary>
                Evidence & image identity <ChevronRight size={15} />
              </summary>
              <div className="runtime-evidence">
                <p>{row.qualification.note}</p>
                <dl>
                  <dt>Base image</dt>
                  <dd>
                    <code>{row.base_image}</code>
                  </dd>
                  <dt>Image source</dt>
                  <dd>
                    <code>{row.image_source}</code>
                  </dd>
                  <dt>Qualification record</dt>
                  <dd>
                    <code>{row.qualification.report}</code>
                  </dd>
                  <dt>Tools</dt>
                  <dd>
                    {Object.entries(row.tools)
                      .map(([name, version]) => `${name} ${version}`)
                      .join(", ") || "None recorded"}
                  </dd>
                </dl>
              </div>
            </details>
          </article>
        ))}
      </div>
      {!state.data.rows.length && (
        <div className="empty-state">
          <Boxes size={28} />
          <h2>No registered runtimes</h2>
          <p>
            Add a qualified image and framework range to the operator-owned
            runtime matrix.
          </p>
        </div>
      )}
      {state.data.limitations.map((text, i) => (
        <Notice key={i}>{text}</Notice>
      ))}
    </>
  );
}
