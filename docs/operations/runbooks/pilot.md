# Personal-use pilot runbook

This runbook brings up the Python pilot from the repository root. It is a bounded personal-use procedure, not a production deployment guide. Run only on a dedicated, disposable host/VM boundary that does not hold production workloads or credentials. Supported tooling platforms are Apple Silicon macOS and amd64 Linux; Docker target execution still requires a trusted Docker daemon (Docker Desktop or Colima Linux VM on macOS). Target containers must never receive host credentials or the Docker socket.

Read the [operations overview](../overview.md) for the data/evidence lifecycle, [troubleshooting](../troubleshooting.md) for failures, [disaster recovery](../disaster-recovery.md) before promising recoverability, and the packaged [risk assessment](../../../src/corsair/policies/risk.md) before admitting source.

## 1. Prepare the local toolchain and image

Enter the pinned Nix shell, synchronize locked Python dependencies, run the offline checks, and build the reviewed observer image:

```bash
nix develop
just sync
just check
just test
just images

mkdir -p .state
cp deploy/settings.example.json .state/settings.json
```

The Nix shell provides the pinned Python, uv, Just, Docker client, and Temporal CLI. `uv.lock` pins Python dependencies and the Nix lock pins tooling, but this is not a claim of a fully hermetic image or runtime. Do not run these commands from another directory; paths in this runbook are repository-root-relative.

On macOS, make the reviewed Docker context visible to the Python Docker SDK and keep temporary observer staging under the repository so the VM can share it:

```bash
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
docker info
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
```

On a rootless Linux daemon, point `DOCKER_HOST` to its actual socket instead, then run `docker info`. Do not relax container networking, mounts, resource limits, runtime selection, or cleanup policy to work around a daemon problem.

## 2. Set operator-owned configuration

Edit `.state/settings.json` before admitting any source. Use the settings template and [CLI reference](../../reference/cli.md) as the configuration authority rather than copying its schema into this runbook.

- Set `source_root` to the narrowest **absolute** local directory that contains source you have authorized for admission.
- Select an `artifact_root` reachable at the same path by the worker and every client that will inspect/reconcile results. A local default such as `.runs` is not durable across host loss.
- Keep the reviewed image and Docker runtime unless the change has separate qualification.
- Make the Temporal address, namespace, and task queue identical for the service, worker, and client.
- Select only the model connector and model names in settings. If an API base is needed, configure only a credential-free HTTP(S) endpoint; do not copy an actual endpoint into example or report text. Keep provider credentials in the worker environment; never put credentials or endpoint query strings in settings, requests, reports, or artifacts.

The producer sees only an immutable admitted snapshot and has `read_file`/`list_files`; it submits typed data payloads, not executable probes. The trusted observer creates its private fixture independently and runs the fixed recipe in fresh Docker containers.

## 3. Establish native reference execution

Before starting Temporal or a model-backed worker, run the native reference replay:

```bash
uv run --locked corsair --format human verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json
```

This verifies the admitted source/image/runtime path with trusted control and adversarial observation. It contacts neither Temporal nor a model and returns an observation, not a release-facing disposition. A healthy run still may demonstrate a violation; an invalid/native operational observation exits nonzero. To test the request’s declared fixed source separately, add `--fixed`.

## 4. Start the durable path

Use three terminals with the same settings and shared artifact root.

```bash
# Terminal 1 — local development persistence only.
temporal server start-dev --db-filename .state/temporal.db
```

```bash
# Terminal 2 — credentials are available only in this worker environment.
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json --log-level INFO --log-file .state/worker.log
```

```bash
# Terminal 3 — read-only dependency preflight, then one unique durable run.
uv run --locked corsair doctor --format human --settings .state/settings.json

RUN_ID="case01-$(date +%s)"
uv run --locked --extra providers corsair investigate \
  evals/fixtures/case01/request.json --run-id "$RUN_ID" --wait \
  --format human --settings .state/settings.json
```

`doctor` checks the real source/artifact directories, Docker daemon/image/runtime, Temporal namespace, and workflow/activity pollers. It does not start services, create directories, make model calls, verify provider credentials, or assert that an investigation will succeed. There is no HTTP health endpoint or scripted monitoring automation.

Without `--wait`, `investigate` returns after Temporal accepts the workflow. With `--wait`, Ctrl-C detaches only the local client; it does not cancel the remote workflow. The worker uses ordinary Temporal activities and a 45-second graceful shutdown, not an ADK–Temporal integration plugin.

## 5. Inspect, cancel, and preserve evidence

Use native workflow state while work is open, then read the immutable committed result:

```bash
uv run --locked corsair inspect "$RUN_ID" --online --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --settings .state/settings.json
```

If cancellation is intended, request it explicitly and inspect afterward:

```bash
uv run --locked corsair cancel "$RUN_ID" --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --settings .state/settings.json
```

Before each Docker role, Corsair atomically claims an immutable execution intent. If an intent already exists, cannot be claimed, or a labeled container is left behind, the operation is uncertain and is not automatically replayed. After native evidence is written and validated, Corsair commits its operation mapping; final result recording is separately idempotent/retried. Preserve run IDs, operation IDs, artifact references, and any container ID/labels. Do not delete intents, use broad Docker pruning, or rerun an uncertain probe.

Cleanup is confirmed only when the exact created container ID with matching operation/role labels was removed and independently observed absent. `cancel` initially reports `cleanup_confirmed: false`; a successful cancellation request is not proof of cleanup. If a container remains, follow [troubleshooting](../troubleshooting.md) rather than applying a generic cleanup command.

## 6. Read the result within pilot limits

Read `execution_status` before the security disposition. `COMPLETED` is an operational completion state; `BLOCKED`, `ERROR`, and `CANCELLED` are not findings. A failed reproduction remains `INCONCLUSIVE`, never a general negative certificate. The manifest and rounds bind evidence to the image ID, model names, configuration/prompt/schema/capability/budget digests, native receipts, and reported usage; they do not contain credentials or establish provider accuracy.

Qualification is intentionally narrow: native gates run on a dedicated rig, and their results make no production, hostile-target, or population-level accuracy claim. `UNABLE_TO_RUN`, `ERROR` and `INCONCLUSIVE` rows are retained as such; none is a negative finding.

For evolving work and decisions, use [current plans](../../plans/README.md). Keep `.runs`, `.state`, worker logs, artifacts, backups, and Temporal histories restricted: even with credential boundaries and redaction, they can contain source snapshots, request content, submissions, or other sensitive operational data.
