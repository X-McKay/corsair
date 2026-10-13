import { Cable, Database } from "lucide-react";
import { Badge, Heading, Notice, State } from "../components/evidence";
import { type SystemData } from "../lib/data";
import { timestamp } from "../lib/format";
import { useData } from "../lib/useData";

const labels: Record<string, string> = {
  evaluations: "Evaluation records",
  runtime: "Runtime matrix",
  assets: "Application assets",
  temporal: "Temporal",
  openshell: "OpenShell",
};

export function System({
  revision,
  retry,
}: {
  revision: number;
  retry: () => void;
}) {
  const state = useData<SystemData>("/api/status", revision);
  if (!state.data)
    return <State loading={state.loading} error={state.error} retry={retry} />;
  const data = state.data;
  return (
    <>
      <Heading
        eyebrow="Configured connections"
        title="System"
        description="Data source access and connectivity to configured Corsair services."
      />
      <div className="system-summary">
        <Badge tone={data.ready ? "success" : "warning"}>
          {data.ready
            ? "Data sources available"
            : "Data source attention required"}
        </Badge>
        <span className="muted">Checked {timestamp(data.checked_at)}</span>
      </div>
      <h2 className="system-section-title">Data sources</h2>
      <div className="runtime-grid">
        {data.sources.map((source) => (
          <article className="panel runtime-card" key={source.id}>
            <div className="runtime-heading">
              <Database size={22} aria-hidden="true" />
              <Badge
                tone={source.status === "available" ? "success" : "warning"}
              >
                {source.status === "available" ? "Available" : "Unavailable"}
              </Badge>
            </div>
            <h2>{labels[source.id] || source.id}</h2>
            <p className="system-detail">{source.detail}</p>
          </article>
        ))}
      </div>
      <h2 className="system-section-title">Services</h2>
      <div className="runtime-grid">
        {data.services.map((service) => (
          <article className="panel runtime-card" key={service.id}>
            <div className="runtime-heading">
              <Cable size={22} aria-hidden="true" />
              <Badge
                tone={
                  service.status === "available"
                    ? "success"
                    : service.status === "unavailable"
                      ? "warning"
                      : "neutral"
                }
              >
                {service.status === "available"
                  ? "Reachable"
                  : service.status === "unavailable"
                    ? "Unavailable"
                    : "Not configured"}
              </Badge>
            </div>
            <h2>{labels[service.id] || service.id}</h2>
            <p className="system-detail">{service.detail}</p>
          </article>
        ))}
      </div>
      <Notice>
        Service connectivity does not establish worker availability, workflow
        completion, image availability or sandbox qualification. Evaluation
        pages display saved reports from the configured data source; they do not
        query running workflows.
      </Notice>
    </>
  );
}
