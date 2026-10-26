# Troubleshooting operations

Start with the immutable evidence and the exact run ID. Do not change settings, delete intents, reuse a run ID, or rerun a native operation merely to obtain a different outcome. The [CLI reference](../reference/cli.md) is authoritative for flags and output; [disaster recovery](disaster-recovery.md) handles host loss and restoration.

## Docker, image, or runtime is not ready

Run the real dependency check first:

```bash
uv run --locked corsair doctor --settings .state/settings.json
docker info
docker image inspect corsair-python:0.1
docker info --format '{{json .Runtimes}}'
```

If Docker cannot be reached, start or repair the trusted daemon/VM, or point the client at its actual rootless socket. On macOS, obtain `DOCKER_HOST` from the trusted Docker context as described in [development setup](../development/setup.md). If the configured image is absent, rebuild the reviewed image with `just images`. If the configured runtime is absent, repair Docker’s runtime configuration or restore the reviewed setting.

Do not make a check pass by mounting the Docker socket in the target container, enabling its network, removing resource limits, selecting an arbitrary image tag, or replacing Docker execution with host-process execution. Those are different security boundaries, not troubleshooting fixes.

## Source or artifact-root preflight fails

`doctor` requires a readable source root and a writable artifact-root parent, but does not create either. Configure `source_root` as the narrowest absolute directory containing source approved for admission. Ensure the worker and all result-reading clients use the exact same `artifact_root`; opening an artifact store may create its `blobs` and `operations` directories, but that does not make the storage durable.

If source admission later fails, correct the source selection or its no-follow/immutable-snapshot constraints rather than broadening the root. Source snapshots are local-only; no remote SCM adapter or fallback checkout is implemented. If the artifact root is unavailable, do not substitute an empty directory and interpret it as an empty history—restore or reconnect to the intended shared store.

## Temporal is reachable but work is not progressing

A reachable namespace without both workflow and activity pollers is not ready. Verify that the service, worker, and client agree on all three operator-owned values: `temporal_address`, `temporal_namespace`, and `task_queue`.

```bash
# Local development service only.
temporal server start-dev --db-filename .state/temporal.db

# Separate terminal; provider credentials stay in this worker environment.
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json --log-level INFO --log-file .state/worker.log

uv run --locked corsair doctor --settings .state/settings.json
```

Then query the workflow, not a guessed progress percentage:

```bash
uv run --locked corsair inspect "$RUN_ID" --online --settings .state/settings.json
```

`inspect --online --watch` is valid only with `--online`. A watch or `investigate --wait` interrupted by Ctrl-C leaves the remote workflow running; it does not need a duplicate submission. Restart the worker if required, then inspect the original run ID.

## A result is missing, uncertain, or cannot be read

Use online inspection first when the workflow may still be open:

```bash
uv run --locked corsair inspect "$RUN_ID" --online --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
```

Once final recording completes, retrieve the immutable receipt from the shared store:

```bash
uv run --locked corsair inspect "$RUN_ID" --settings .state/settings.json
```

An offline “No committed result” message means there is no committed result mapping at that artifact root; it does not mean no side effect happened. Native execution first atomically claims `intent.<operation-id>`. If that claim already exists, cannot be read, or a labeled container remains, the operation is uncertain and is deliberately not replayed. Preserve the run ID, operation ID, artifact references, and any Docker container ID/labels. Do not delete the intent or start the same work under a new ID until the incident is assessed.

## Cancellation or cleanup is unconfirmed

`corsair cancel "$RUN_ID"` reports only `cancellation_requested` and `cleanup_confirmed: false`. Follow it with online inspection and, if a result was recorded, offline inspection. The evidence verifier reports cleanup only after it validates the container labels on the exact created immutable ID, removes that exact ID, and confirms that exact ID no longer exists.

If a container remains, record rather than broadly remove it:

```bash
docker ps -a --filter label=corsair.security=true
docker inspect "$CONTAINER_ID"
```

Compare the actual ID and labels to the run’s operation/role before taking any host-level action. Corsair has no separate cleanup command and does not certify a manually removed or label-wide-pruned container as clean. Keep the run operationally unresolved and follow local incident controls; do not rerun the operation automatically.

## Provider feedback or native observation reports an error

Inspect the final result’s rounds, feedback gate, usage metadata, and manifest before changing any provider setting. Provider failures are classified as redacted operational feedback, including policy blocks, temporary failures, and permanent failures. Credentials and raw provider responses are intentionally unavailable to the CLI result/log stream. Do not put them into a report to debug the issue, bypass policy, or silently select another provider.

For a native `ERROR` or `INVALID` observation, preserve the raw evidence artifact and Docker receipt. A native error does not establish a safe application, an unsupported finding, or a failed fix; the result stays `ERROR` and is never relabelled.

## Exit status is not the security verdict

| Exit | Meaning | Operator action |
| --- | --- | --- |
| `0` | The command met its own healthy/success condition. | Read the returned result/receipt; this is not automatically a supported finding. |
| `1` | A completed check, replay, investigation, evaluation, or score is unhealthy/non-success. | Preserve and inspect the reported operational state. |
| `2` | Invocation, input, settings, or local configuration prevented normal execution. | Correct the local invocation/configuration; no conclusion was established. |
| `130` | The local CLI was interrupted. | Inspect the original remote workflow; it was not implicitly cancelled. |

For currently active work and known limits, consult [plans](../plans/README.md). The pilot is not a production/hostile-target qualification and has no automatic remediation mechanism.
