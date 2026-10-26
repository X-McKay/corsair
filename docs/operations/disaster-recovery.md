# Disaster recovery

Corsair can reconcile immutable records that remain available; it cannot make an uncertain side effect certain, reconstruct an unrelated lost artifact filesystem from Temporal history, or migrate state with an application-provided tool. Treat recovery as a restricted operational procedure, not a way to obtain a clean result.

The [CLI reference](../reference/cli.md) defines inspection/cancellation commands. See [monitoring](monitoring.md) for routine observation and [troubleshooting](troubleshooting.md) for dependency faults.

## First preserve the incident identity

Record the run ID, Temporal namespace/task queue, artifact-root location, observed phase/round, known operation IDs, immutable container IDs/labels, and the time of the event. Do not record secrets, source contents, raw provider responses, or private fixtures in a ticket or log. Do not reuse the run ID: native workflow start rejects duplicate identities.

Before deciding whether work can continue, distinguish these cases.

| Event | What survives | What not to infer |
| --- | --- | --- |
| Client Ctrl-C or disconnect | The Temporal workflow may still be open. | The workflow was not cancelled and no cleanup conclusion follows. |
| Worker restart | Temporal history and any reachable shared artifacts remain. A worker can poll again. | An in-flight model/Docker side effect completed, did not run, or is safe to repeat. |
| Explicit cancellation | A Temporal cancellation request was sent. | Docker cleanup is complete; the CLI response starts with `cleanup_confirmed: false`. |
| Artifact-store/host loss | Temporal history may remain, but local artifact blobs and operation mappings may be gone. | Offline inspection, evidence reconciliation, or result retrieval can be reconstructed from history alone. |

## Client disconnect or worker restart

A local wait is only observation. Reconnect to Temporal and query the original workflow:

```bash
uv run --locked corsair inspect "$RUN_ID" --online --settings .state/settings.json
```

If a worker was restarted, start it again with the same settings and access to the same artifact root. Then query the original run; do not submit another workflow as a substitute for resumption:

```bash
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json --log-level INFO --log-file .state/worker.log
uv run --locked corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
```

The worker uses normal Temporal replay and a 45-second graceful-shutdown bound. Producer, auditor, and Docker evidence activities are configured for one attempt, so a lost/incomplete activity is surfaced rather than silently retried. Before native execution, Corsair atomically claims an immutable intent; a claim with no committed observation stays uncertain. A remaining labeled container likewise blocks replay. Preserve that uncertainty even if the restarted workflow or daemon no longer visibly has a running container.

If final result recording completed, retrieve it only from the shared artifact root:

```bash
uv run --locked corsair inspect "$RUN_ID" --settings .state/settings.json
```

Final result recording is the limited exception: its immutable mapping is idempotently retried up to three times within a separate 90-second schedule-to-close window. That retry protects final receipt publication, not model or Docker side effects.

## Intended cancellation

Request cancellation explicitly, then observe the original workflow and any recorded result:

```bash
uv run --locked corsair cancel "$RUN_ID" --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --settings .state/settings.json
```

A cancellation that reaches the workflow while its final `record` activity is pending completes that record and returns it rather than closing without `result.{run_id}`; earlier cancellations record a `CANCELLED` result. The latter commands may report that a workflow/result is unavailable; preserve that fact rather than replacing it with a rerun. For a native operation, cleanup is valid only when its raw receipt shows cleanup of the exact immutable container ID with matching Corsair operation/role labels and subsequent absence of that ID. A cancellation request or broad host cleanup is not equivalent evidence.

If a retained container must be examined, record its exact identity before any host-level action:

```bash
docker ps -a --filter label=corsair.security=true
docker inspect "$CONTAINER_ID"
```

Corsair supplies no manual-cleanup or replay command. A host operator’s manual action must remain a separately recorded incident action; it does not turn an affected run into `cleanup_confirmed` or justify a repeated probe.

## Artifact host or storage loss

The filesystem store contains immutable blobs plus immutable hashed operation mappings. Worker and clients must share it for offline inspection and reconciliation. Temporal history does not contain a substitute copy of that store, and local development Temporal SQLite persistence does not make a local artifact directory durable.

1. Stop submitting new work against the affected artifact root. Do not point a client at an empty replacement root and interpret the resulting missing receipt as a clean run.
2. Preserve reachable Temporal history and host/Docker diagnostics, but treat them as incomplete for evidence recovery.
3. Restore an operator-managed, consistent backup of the **entire** artifact-root tree, including both `blobs` and `operations`, to trusted storage. Configure worker and clients to access that restored root consistently.
4. Use offline `inspect` to validate a committed result and online `inspect` to determine any remaining workflow state. A missing intent/observation after restoration remains unavailable or uncertain; do not synthesize mappings or rerun its operation automatically.
5. Document the restored snapshot provenance and any unavailable runs. Requalify operational dependencies with `doctor` before admitting new work.

There is no application-supported artifact migration, cross-store merge, reindex, or Temporal-history-to-artifact reconstruction tool. Any infrastructure relocation or backup restore is an operator-controlled storage procedure and needs its own validation; do not claim that changing `artifact_root` migrated evidence.

## Backups and confidentiality

Back up the artifact store and Temporal persistence separately if recovery is required. Restrict backups, snapshots, exported histories, database files, worker logs, and recovery media. Although credentials are prohibited from settings and workflow inputs and logs redact known sensitive values, artifacts and histories can contain operator-supplied request data, admitted source snapshots, submissions, source excerpts, evidence metadata, and operational identifiers. Treat them as potentially secret-bearing. Encrypt and control access under the host’s policy; do not commit backups, `.runs`, `.state`, raw diagnostics, or history exports to source control.

A backup is a recoverability control, not proof of production readiness or evidence validity. Current work and decisions are listed in [plans](../plans/README.md).
