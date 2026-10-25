# Personal-use pilot runbook

Corsair is a security-sensitive, personal-use pilot. Run it only on a dedicated disposable Ubuntu/Debian host with Python 3.12+, `uv`, Docker, and a Temporal service. Do not admit third-party source on a workstation or server that holds credentials, production workloads, or Docker socket access intended for another trust boundary. Target containers must never receive host credentials or the Docker socket.

This runbook uses real Docker, Temporal, configured filesystem paths, and the native observer. It does not substitute mocked health or scripted model behavior for a production investigation.

## 1. Prepare the host and configuration

```bash
make sync
make check
make test
make images

mkdir -p .state
cp deploy/settings.example.json .state/settings.json
```

Edit `.state/settings.json` before use:

- set `source_root` to the narrowest absolute directory that contains sources you intend to admit;
- set an artifact root shared by the worker and every client that must inspect/reconcile results;
- retain the reviewed image and Docker runtime unless their change has its own qualification;
- make the Temporal address, namespace, and task queue match the service and worker you will run; and
- configure the model connector/names only. Put provider credentials in the worker environment, never in settings, a request, a report, or an artifact.

Rootless Docker is supported when the client points to its actual socket:

```bash
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
docker info
```

Image building is explicit and may use the network. Investigation containers do not: their runtime network policy remains disabled. If a rootless builder cannot resolve package DNS, repair the builder configuration or, during the trusted image build only, use:

```bash
docker build --network=host -f deploy/python/Dockerfile -t corsair-python:0.1 .
```

This is not a runtime exception and must not be copied into Docker execution settings. The image’s immutable resolved ID is recorded in each manifest; a changed tag/image creates a different run identity.

## 2. Establish the native reference path first

Before starting Temporal or configuring a model provider, run the public native reference. It confirms source admission, the configured Docker image/runtime, and trusted control/adversarial observation without making a model call or contacting Temporal.

```bash
uv run --locked corsair --format human verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json
```

For an automated pipeline, make JSON explicit and preserve its stdout purity:

```bash
set -o pipefail
uv run --locked corsair --format json verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json | python -m json.tool
```

The reference replay returns an observation, not a release-facing verdict. A healthy reference can return a demonstrated violation or a held property; it only establishes that the trusted native operation itself completed validly. Use `--fixed` to observe the request’s declared fixed source separately.

## 3. Start the durable workflow path

Run the local development server and worker in separate terminals. The dev server’s SQLite persistence is for local development only; choose shared durable storage and production Temporal persistence or Temporal Cloud before making stronger recovery promises.

```bash
# Terminal 1
temporal server start-dev --db-filename .state/temporal.db
```

```bash
# Terminal 2: credentials are available only here.
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json \
  --log-level INFO --log-file .state/worker.log
```

The worker uses the Temporal SDK worker context. On `SIGTERM`, it performs orderly SDK shutdown with a 45-second graceful-shutdown limit. Do not kill a worker and infer that an in-flight native operation was cleaned up; inspect Temporal and the committed artifacts.

From a third terminal, run the preflight and then submit work:

```bash
# Global output/log switches work before or after a command.
uv run --locked corsair doctor --format human --settings .state/settings.json

RUN_ID="case01-$(date +%s)"
uv run --locked --extra providers corsair investigate \
  evals/fixtures/case01/request.json --run-id "$RUN_ID" --wait \
  --format human --settings .state/settings.json
```

`doctor` reads actual local/remote state: settings, configured source/artifact directories, Docker reachability/image/runtime, and Temporal namespace/task-queue worker pollers. It does not build an image, create directories, start a service/worker, submit a workflow, call a model, or verify provider credentials. A successful doctor is operational readiness for these dependencies, not a security verdict or a model qualification.

## 4. Output, logs, and safe automation

Use `--format auto` for the default terminal-aware behavior, `--format human` for a compact Rich panel, or `--format json` for machine use. Human output includes reason, scope, control/adversarial outcomes, audit, usage, and artifact identity; it does not imply progress that the workflow has not reported.

```bash
# Terminal transcript without colour or spinner.
corsair inspect "$RUN_ID" --online --watch \
  --format human --no-color --no-animation --settings .state/settings.json

# Pipe-safe result. Logs go to stderr; this pipeline gets JSON only.
corsair --format json inspect "$RUN_ID" --online --settings .state/settings.json \
  | python -m json.tool
```

Operational logs are sent to stderr and may be mirrored as structured JSON Lines with `--log-file PATH`. Select `--log-format text|json` for stderr and `--log-level DEBUG|INFO|WARNING|ERROR` as needed. JSON logs contain a safe metadata allowlist only; prompts, source content, payloads, endpoint URLs, credentials, provider responses, and raw reasoning are not log fields. Raw SDK diagnostics are suppressed rather than forwarded because they can carry request data. Endpoint URLs and known credential values are redacted from exception output; with `--log-format json`, expected CLI errors are JSON Lines diagnostics rather than a plaintext second channel. Keep logs restricted because run IDs, timing, and local operational data are still sensitive.

| Exit | Operator interpretation |
| --- | --- |
| `0` | The command completed its stated healthy/success condition. |
| `1` | A completed health check, operation, or score reported an unhealthy/non-success outcome. Inspect its result. |
| `2` | Invocation, validation, settings, or local configuration prevented normal execution. Correct the input/configuration. |
| `130` | Ctrl-C stopped the local CLI. It did not implicitly cancel a remote workflow. |

## 5. Recover and inspect

A completed native operation can be reconciled from its immutable committed observation. An execution intent without that observation is uncertain. Never delete an intent to turn uncertainty into a pass or blindly rerun the operation; inspect owned container identifiers and retain the uncertainty.

```bash
# Read phase and round from the live investigation workflow.
corsair inspect "$RUN_ID" --online --settings .state/settings.json

# Wait for the actual final result; Ctrl-C detaches only this client.
corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json

# Read the immutable committed local/shared result after completion.
corsair inspect "$RUN_ID" --settings .state/settings.json

# Cancellation is explicit; then inspect the terminal result and cleanup receipts.
corsair cancel "$RUN_ID" --settings .state/settings.json
```

For an evaluation batch, online inspect reports actual complete/total child work, not a guessed percentage. `--watch` waits for its actual final batch result. Reusing a run ID with a different request is rejected; create a new run ID instead.

Host loss requires the artifact-store backup/shared filesystem as well as Temporal history. Native Temporal replay cannot restore an unrelated local filesystem. Investigation actions are bounded by the request's `max_elapsed_seconds`; the final result-recording operation has its own 90-second schedule-to-close window, including queueing, retry, and backoff. Final artifact recording is idempotently retried, while provider/model calls and native side effects use a single activity attempt, so unknown delivery is surfaced instead of silently retried.

## 6. Troubleshooting

### Docker is unavailable, image is missing, or the runtime is not configured

Start with the dependency report:

```bash
corsair doctor --settings .state/settings.json
```

If the daemon is unreachable, start it or set the correct rootless `DOCKER_HOST`, then confirm `docker info`. If the image is absent, rebuild the reviewed image with `make images` and inspect it:

```bash
docker image inspect corsair-python:0.1
```

If the configured runtime is absent, list daemon runtimes and align the reviewed setting with the daemon configuration:

```bash
docker info --format '{{json .Runtimes}}'
```

Do not work around any of these checks by mounting a socket, enabling target-container networking, removing resource limits, or substituting an unreviewed image.

### Source/artifact directory checks fail

Make `source_root` an absolute, narrowly scoped directory. Ensure the artifact root parent is writable and the exact same artifact root is available to clients and workers. Creating a directory does not make it durable—back it up or place it on shared storage before relying on recovery.

### Temporal is reachable but there are no worker pollers

Confirm all three configuration values agree between service and worker: `temporal_address`, `temporal_namespace`, and `task_queue`. Start the service and worker shown above, then rerun `doctor`. A server without a poller cannot execute a submitted workflow. `doctor` labels missing pollers as a warning but returns overall not-ready/exit `1`; treat it as a real operational block.

### A client disconnects, Ctrl-C is pressed, or `inspect` cannot find a result

Ctrl-C during `--wait`/`--watch` detaches only the client. Use online inspect to learn the live workflow state, and offline inspect after it completes. If Temporal is down, restore connectivity before concluding anything about a workflow. If the committed artifact is missing after host loss, restore the artifact store; Temporal history alone is insufficient.

## 7. Evaluation and qualification

Use native reference replay before changing driver/image logic. For prompt/model changes, run the isolated role evaluator on its frozen development set and then a finite whole-system dataset with repeats. Oracles remain under evaluator-owned fixture paths and never enter `PreparedCase`, agent packets, or Temporal child inputs. Source snapshots reject known sensitive/oracle filenames and symlinks; this is not a general secret detector for arbitrary source content. Source/evidence binding does not attest a hostile target interpreter or establish generic observation integrity.

```bash
make sync
make check
make test
make images
make test-docker
make test-temporal
make build
```

The original live security-producer request was provider-policy blocked. That result cannot certify full live-chain accuracy. Scripted ADK models are confined to labelled tests; they are not a production fallback. Do not evade policy, silently change providers, retry prohibited requests, strip safety checks, or describe blocked execution as an application fix.

Do not promote the small authored fixtures as a population accuracy benchmark. Store private reports in `.runs`; package only source, sanitized validation summaries, and frozen public fixtures. The pilot remains deliberately limited: other languages, dependency installation/build repair, arbitrary code-authored probes, stronger hostile-target evidence attestation, HTTP/cloud recipes, application-level exposure proof, automated risk approval, negative certificates/refutation, production persistence/deployment, shared object storage, dashboards, optimization frameworks, and Alpha ADK–Temporal turn-level integration are deferred.
