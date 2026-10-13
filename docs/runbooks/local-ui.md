# Corsair results UI

The Corsair UI reads saved evaluation reports, native Temporal investigation status and the operator runtime matrix. The System page checks actual source access and configured Temporal/OpenShell services. It does not launch work or change configuration. It adapts the InfoSec Harness UI patterns for Corsair's own evidence contracts; see [SPEC-0069](../development/specs/SPEC-0069-local-results-ui.md).

## Start

Use Node 22 or newer, npm, Python 3.12 and the repository's uv environment:

```sh
make ui-install
make ui-build
make ui
```

Open http://127.0.0.1:8765. This serves the production build and same-origin read-only API from a loopback listener. Stop with Ctrl-C. Rebuild after changing UI source. A missing results directory is reported as unavailable; a readable directory without saved evaluations is empty. Worktrees have separate ignored `.runs` directories. Generate an evaluation or explicitly select existing storage.

Generate a scripted host evaluation in another terminal to populate real local results:

```sh
make eval AGENT=identification
```

Visible pages refresh every 30 seconds after a request completes; Refresh also reads the sources immediately. Scripted results measure the fixture/evaluation plumbing, not live model quality. Live-provider evals remain explicit CLI actions under their existing configuration and budgets.

For an alternate port or results checkout, use the server directly from the UI checkout:

```sh
PYTHONPATH=src:. uv run --locked python -m corsair.web --root /absolute/path/to/corsair --port 8766
```

`--root` supplies checkout defaults. Separate `--results`, `--assets` and `--runtime-matrix` paths select existing operator-owned sources independently; their environment equivalents are `CORSAIR_UI_RESULTS`, `CORSAIR_UI_ASSETS`, `CORSAIR_UI_RUNTIME_MATRIX`. The local stdlib listener stays loopback-only. Kubernetes uses the production Gunicorn entrypoint described below.

## Metrics

Open **Agents** (`/agents`; `/metrics` remains an alias) for aggregate recorded runs/attempts and a separate card per agent. Filter by agent or mode and choose a recorded cohort inside each card. Evaluator success and task completion remain distinct from accuracy, which is not defined by current summaries. Expand the recorded-checks section for assertion rates, observed input/output totals and identity details.

Each card shows latency and total-token histograms with smooth frequency lines through the same bin counts. Cards share axis scales; no fitted probability density is implied. Total tokens are sampled only when input and output usage were observed on the same native attempt. Live samples require explicit provider usage coverage. Missing telemetry is unavailable; measured zero is retained. The overview shows aggregate resource distributions for one provider mode at a time, keeping scripted estimates separate from live usage. Incomplete outcome counts make the coverage denominator unknown.

The service reads at most 500 run summaries, 100 native reports and 20,000 case samples per metrics request; each JSON file is bounded to 4 MiB. Warnings identify missing, inconsistent, omitted or truncated evidence. Groups reflect recorded identities, not proof that every effective setting is known. No general semantic accuracy is invented: individual recorded correctness checks and their pass rates remain visible.

## Compare recorded runs

Open **Experiments** (`/experiments`) and select a baseline and candidate. Selection does not promote a baseline or launch work. The view shows outcome rates, retained identity differences, case-level changes and recorded efficiency means with coverage. Different or missing core identities prevent outcome deltas. Native execution mode is a separate field from wrapper provider mode.

Comparisons describe saved observations: repeated attempts are not paired, partial measurements may omit failures, and current summaries do not retain every evaluator or effective provider setting. Prompt/model changes can be intentional variables, but displayed differences do not prove causality or general accuracy.

## Interpret results

- All checks passed means the saved evaluator assertions passed; it is not a general accuracy or security claim.
- Unknown telemetry stays unknown. Zero represents an observed zero only. Means show measurement coverage; failed attempts may have incomplete telemetry in current native reports.
- Different agents, datasets, provider settings and execution modes are not one comparable accuracy population.
- Host authoring and environment results use static or synthetic observations. They do not prove generated tests or setup commands executed.
- Runtime image-only evidence is distinct from live qualification and from successful execution of a particular repository.
- The server returns selected summary facts only. It does not serve raw inputs, transcripts, source artifacts, arbitrary files or credentials. Untrusted labels are rendered as plain text.

## Validate

```sh
make ui-check
# Once per environment, install the test browser:
cd ui && npx playwright install chromium
cd ..
make ui-test
```

API tests run with `make test-config`. Browser fixtures are synthetic local saved-result records, kept separate from actual run evidence. No browser test calls a model or starts a sandbox.

## Troubleshooting

A missing build needs `make ui-build`. A port-in-use error needs a different `--port` or stopping the listener you started. A missing or unreadable results directory returns 503 with mount/permission guidance. A readable empty directory means no retained reports were found there; check that the producer uses the same storage. Malformed, oversized or unreadable records are reported as unavailable, not successful. The server rejects unexpected Host/Origin values and unsupported methods; use its printed loopback URL locally or the exact configured public origin in deployment.


## Kubernetes deployment

Build from this checkout. The image contains compiled frontend assets and application code/dependencies only. No saved runs, test fixtures, source credentials or model credentials are copied. UI Python dependencies are locked separately in the `ui` group; the existing runtime contracts currently import the native agent SDK, so it is included even though the viewer never invokes a model.

```sh
docker build -f deploy/ui/Dockerfile -t corsair-ui:review .
```

Use `deploy/ui/render.py` to produce resources for an **existing** namespace and results PVC. Set `UI_IMAGE` to the built image available to your cluster (prefer an immutable digest), `CORSAIR_NAMESPACE` to that namespace, `CORSAIR_RESULTS_CLAIM` to the actual producer claim and `UI_ORIGIN` to the exact browser origin. These are operator selections, not defaults that create sample storage.

```sh
PYTHONPATH=src:. uv run --locked python -m deploy.ui.render \
  --image "$UI_IMAGE" --namespace "$CORSAIR_NAMESPACE" \
  --results-claim "$CORSAIR_RESULTS_CLAIM" --public-origin "$UI_ORIGIN" \
  > /tmp/corsair-ui.yaml
kubectl --context "$CORSAIR_CONTEXT" apply -f /tmp/corsair-ui.yaml
```

The renderer includes the actual validated runtime matrix from this checkout; use `--runtime-matrix` to select an operator-maintained file. A content annotation rolls the pod after a matrix change. It creates a ConfigMap, Deployment and internal ClusterIP Service, **no new PVC, namespace, Ingress or worker**. The image must be published/loaded separately; render success does not establish availability to a node. For local access choose `UI_ORIGIN=http://localhost:8765`, then:

```sh
kubectl --context "$CORSAIR_CONTEXT" -n "$CORSAIR_NAMESPACE" \
  port-forward service/corsair-ui 8765:8765
```

Open http://localhost:8765. For shared remote access, use the cluster's authenticated TLS ingress, set `UI_ORIGIN` to its exact HTTPS origin and preserve Host. The application does not implement login; do not make this internal service public without the operator's authentication boundary. Origin validation prevents cross-origin browser access; it is not user authentication. Forwarded headers do not select the trusted origin.

### Results storage

The UI mounts the selected claim at `/data` read-only and reads `/data/evals/<agent>/<run>/summary.json` and `evidence/report.json`. The producer must mount the **same claim** and write its evals subdirectory:

```sh
CORSAIR_EVAL_RESULTS=/data/evals make eval AGENT=identification
```

`CORSAIR_EVAL_RESULTS` also applies to `make eval-baseline`; `python -m evals.run --results` overrides it. A host producer must use the corresponding host-mounted path; the UI does not synchronize host `.runs` folders into Kubernetes. Existing records can be placed on that shared storage by the operator using their normal storage workflow. Do not mount unrelated private workspaces. Reports remain files; no second run database or automatic migration is introduced.

The container runs as UID/GID10001. Ensure it can traverse/read the results directory and files through existing storage permissions. No automatic chown or permissive init container is used. PVC access mode and node placement must support both producer and reader; use storage appropriate to the deployment topology. The root filesystem, runtime matrix and results mounts are read-only; only a bounded memory-backed `/tmp` is writable.

`/api/live` checks the serving process. `/api/ready` returns 200 only when results can be enumerated, the matrix validates and built assets can be read; otherwise 503. Readiness does not require optional external service probes: evaluation inspection remains useful if Temporal/OpenShell is down. `/api/status` reports those states separately. Missing mounts are never reported as zero runs or successful checks.

### Service connections

Pass native endpoints explicitly to the renderer; it does not guess service names:

- `--temporal-address` selects the native Temporal frontend `host:port`; `--temporal-namespace` defaults to `default`.
- `--temporal-tls-secret` optionally selects an existing TLS Secret in the same namespace.
- `--openshell-endpoint` and `--openshell-tls-secret` select the native gateway `host:port` and its required client identity together. Do not use an `https://` URL: TLS is selected by the certificate configuration.

TLS Secrets use keys `ca.crt`, `tls.crt`, `tls.key`. They are mounted read-only, never embedded in generated YAML or the image. Use credentials scoped by the service's own authorization to read namespace/visibility or health only. No model, GitHub, Azure or workload credentials are needed. The service does not load local CLI credential profiles or run kubectl/openshell commands.

For an existing configuration management system, equivalent container environment variables are:

| Setting | Purpose |
| --- | --- |
| `CORSAIR_UI_PUBLIC_ORIGIN` | Required exact http(s) browser origin |
| `CORSAIR_UI_RESULTS` | Existing results directory; image default `/data/evals` |
| `CORSAIR_UI_ASSETS` | Built assets; image default `/app/ui/dist` |
| `CORSAIR_UI_RUNTIME_MATRIX` | Matrix file; image default `/config/runtime-matrix.yaml` |
| `CORSAIR_UI_TEMPORAL_ADDRESS` | Native Temporal frontend address |
| `CORSAIR_UI_TEMPORAL_NAMESPACE` | Namespace, default `default` |
| `CORSAIR_UI_TEMPORAL_TLS_CA/CERT/KEY` | Absolute mounted TLS file paths; pair CERT and KEY |
| `CORSAIR_UI_OPENSHELL_ENDPOINT` | Native OpenShell gateway `host:port` (no URL scheme) |
| `CORSAIR_UI_OPENSHELL_TLS_CA/CERT/KEY` | Absolute mounted TLS file paths, all required |

The Temporal adapter also supports a custom CA without a client certificate by setting only its CA variable. TLS certificate verification is never disabled. Service probes use native SDK deadlines without retries. They expose safe guidance rather than raw credential/transport exception text; use service logs for detailed diagnosis. An absent endpoint is **Not configured**, a failed call is **Unavailable**, and an actual successful call is **Reachable**.

**Runs** shows up to 100 native parent `corsair.chain.Investigation` and `corsair.fixture.Investigation` executions in the selected namespace, with workflow/execution IDs, type, native status and timestamps. Fixture investigations are labeled. Visibility retention and the single-page limit bound this list; it is not an archival inventory. The service needs DescribeNamespace and ListWorkflowExecutions access. Inputs, results, history and child workflow payloads are not retrieved. Workflow telemetry is not invented: token/accuracy distributions remain on the evaluation pages where actual native reports exist.

**Runtime** displays operator registration and retained qualification, not a registry pull or live sandbox check. **System** shows source checks plus native namespace/gateway health. A reachable gateway does not establish image availability, worker availability, admission or successful work.

### Deployment verification

After deploying, check `/api/ready`, System and Runs using the configured origin. Write a new evaluation into the producer's shared volume, then confirm the same run ID, status and measured samples in Evaluations/Agents after refresh. Disconnect a test data mount or use an unreachable test endpoint in an isolated deployment to confirm visible failure states. Do not interpret rendered manifests, offline SDK tests or a local container smoke as live cluster qualification.


A reproducible production-image smoke uses an isolated directory containing one actual scripted evaluation:

```sh
CORSAIR_EVAL_RESULTS=/tmp/corsair-ui-smoke/evals make eval AGENT=identification
python deploy/ui/smoke.py --image corsair-ui:review \
  --results /tmp/corsair-ui-smoke/evals --runtime-matrix deploy/runtime-matrix.yaml
```

Use a fresh directory for each invocation. The helper compares API counts and sample distributions to that producer report, verifies missing-storage 503 behavior, and removes only its own containers by immutable ID. CI runs the same build/smoke. This is scripted producer/container integration, not live model or deployed service qualification.
