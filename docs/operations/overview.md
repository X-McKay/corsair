# Operations overview

Corsair is a personal-use security pilot, operated through a local CLI, a native Temporal worker, a Docker daemon, and a shared immutable artifact root. Google ADK runs bounded producer and auditor episodes inside ordinary Temporal activities; Temporal owns durable rounds, budgets, cancellation, and final result recording. This is not an HTTP service: there is no application health endpoint, dashboard, remote-SCM checkout, or scripted monitoring automation.

Use this page for the operational model. The changing command surface and output contracts remain in the [CLI reference](../reference/cli.md); environment and platform prerequisites are in [development setup](../development/setup.md). Current implementation and qualification work is tracked in [plans](../plans/README.md).

## Operator-owned boundaries

The operator supplies the settings JSON, including the local source-admission root, artifact root, Docker image/runtime, Temporal address/namespace/task queue, and model selection. Keep provider credentials only in the worker environment. Do not place credentials, endpoint query strings, or credentials embedded in URLs in settings, requests, artifacts, or logs.

The supported development shell is Apple Silicon macOS or amd64 Linux. On macOS, Docker runs through a trusted Docker Desktop or Colima Linux VM; the shell itself does not start a daemon. Both the worker and every client that must read results need the same `artifact_root`. A local artifact directory on one host is not a durability boundary.

The producer can read only an admitted immutable source snapshot using its `read_file` and `list_files` tools. It proposes data-only `Submission` payloads; it cannot author probes, change the recipe, or choose a host path. The trusted observer—not either model—executes the fixed control and adversarial inputs in fresh Docker containers.

## Operational lifecycle

1. **Preflight the real dependencies.** `corsair doctor --settings .state/settings.json` checks a readable source root, a writable artifact-root parent, Docker daemon/image/runtime, Temporal namespace, and workflow/activity pollers. It creates nothing, calls no model, checks no provider credential, and does not prove a future investigation will succeed.
2. **Establish native execution.** Run `corsair verify REQUEST SUBMISSION` before a durable investigation after changing admission, image, driver, or runtime behavior. This uses Docker and the trusted observer but no model or Temporal request. Its observation is not a release-facing disposition.
3. **Start durable work.** A worker runs the registered investigation/evaluation workflows and ordinary activities. `investigate` starts a unique Temporal workflow; `--wait` observes it but Ctrl-C detaches only the local CLI. `inspect RUN_ID --online` queries the live workflow’s actual phase and round, while offline `inspect RUN_ID` reads a committed result from the artifact root.
4. **Preserve evidence before interpreting it.** Final results, source snapshots, manifests, raw Docker receipts, evidence bundles, and operation mappings are immutable content-addressed records. A final result is available offline only after its result mapping is committed.

For copyable pilot commands, see the [pilot runbook](runbooks/pilot.md). For manual state observation, see [monitoring](monitoring.md); for faults and recovery limits, use [troubleshooting](troubleshooting.md) and [disaster recovery](disaster-recovery.md).

## Evidence and side-effect lifecycle

Before a Docker role begins, the verifier publishes an immutable `intent.<operation-id>` record with the source, submission, configuration, recipe, image, budget, and fixed-source identities. It claims that intent atomically. A failed or pre-existing claim means the side effect may already have happened: the operation remains uncertain and is not automatically replayed. Likewise, a leftover container with the expected `corsair.security`, operation, and role labels is an unknown operation, not permission to run a new one.

After a role completes, the verifier validates the trusted driver output against the Docker exit code, source/submission digests, coverage, image identity, and cleanup receipt. It writes the referenced immutable blobs first and commits the operation mapping only afterward. A committed observation can therefore be reconciled by identity; an intent with no committed observation cannot be converted into a pass by deleting records or retrying the same operation.

Each Docker container has a created immutable ID and operation/role labels. Cleanup is confirmed only when Corsair verifies those labels on that exact ID, removes that exact container, and independently observes that ID as absent. A cancellation request, an empty broad `docker ps` listing, or a client disconnect is not cleanup confirmation.

Temporal gives producer, auditor, and native-evidence activities one attempt. It does not silently repeat provider calls or Docker side effects when delivery is uncertain. Final result recording is different: its immutable, idempotent mapping may retry up to three times within its separate 90-second schedule-to-close window.

## Interpreting the current result

Read `execution_status` before reading a security disposition. `COMPLETED` means the workflow completed its operational path; it does not by itself mean a finding was supported. `BLOCKED`, `ERROR`, and `CANCELLED` retain distinct operational meanings and must not be relabelled as a security conclusion. The underlying observation can report `PROPERTY_HELD`, `VIOLATION`, `INVALID`, or `ERROR`; a failed reproduction remains `INCONCLUSIVE`, not a negative certificate.

Each manifest records the immutable Docker image ID, selected producer/auditor model names, and digests for the request, configuration, prompts, schemas, capability metadata, and budgets. Round outputs retain observed usage and any redacted provider feedback gate. This metadata supports attribution; it does not record provider credentials or certify model availability, accuracy, cost, or a provider’s future policy.

Live qualification is deliberately limited. Native gates run on a dedicated rig with Docker, Temporal and a configured provider; their results are recorded in [current plans](../plans/README.md) and do not establish production readiness, hostile-target safety, or population-level accuracy. An `ERROR`, `UNABLE_TO_RUN` or `INCONCLUSIVE` row stays as recorded; it is never a negative finding. Review the packaged [risk assessment](../../src/corsair/policies/risk.md) before admitting source outside a disposable sandbox.
