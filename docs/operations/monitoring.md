# Monitoring operations

Corsair has manual, evidence-oriented observation points. It does not expose a native HTTP health endpoint, push metrics to a monitoring backend, create dashboards, or run a scripted monitoring/scheduled remediation loop. Run the checks below deliberately from the repository root and retain the returned run IDs and committed receipts.

For command syntax and JSON output contracts, use the [CLI reference](../reference/cli.md). This guide describes what an operator can observe, not an automatic service-level objective.

## Before submitting work

Run the read-only preflight against the same settings that the worker and client will use:

```bash
uv run --locked corsair doctor --format human --settings .state/settings.json
```

`doctor` reports separate checks for `source_root`, `artifact_root`, Docker, Temporal, and `worker_pollers`. A `warn` for pollers makes the overall report not ready and exits `1`: both workflow and activity pollers must be present on the configured task queue. The report also shows installed SDK versions. It does **not** build the image, create the artifact root, submit work, send a prompt, verify credentials, test provider policy, or perform native evidence execution.

For a machine-readable transcript, stdout is JSON only; diagnostics remain on stderr:

```bash
set -o pipefail
uv run --locked corsair --format json doctor --settings .state/settings.json | python -m json.tool
```

A healthy doctor is a dependency preflight, not a security result or a model qualification. Do not replace it with a synthetic health response.

## While a workflow is open

Query actual workflow state rather than estimating progress:

```bash
uv run --locked corsair inspect "$RUN_ID" --online --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --online --watch --settings .state/settings.json
```

For an investigation, the native query returns its actual phase and round. For an evaluation batch, it returns actual completed and total child work. `--watch` requires `--online`; it waits for the workflow’s real final result and may be interrupted locally without cancelling work. It is not a heartbeating status service and must not be treated as proof that a security conclusion has been reached.

Use Docker only as a supplemental host observation. A currently retained Corsair container can be listed without modifying it:

```bash
docker ps -a --filter label=corsair.security=true
```

If one is present, preserve its immutable container ID and its `corsair.operation`/`corsair.role` labels for the incident record. Absence is not proof that an uncertain side effect never ran, particularly if the daemon was unavailable. Do not use broad prune or label-wide removal commands as a substitute for Corsair’s exact-ID cleanup confirmation.

## After completion

Read the committed result from the shared artifact root:

```bash
uv run --locked corsair inspect "$RUN_ID" --settings .state/settings.json
```

Offline inspection validates the immutable result receipt and does not contact Temporal. If it reports no committed result, use online inspection to learn whether the workflow is still live; do not rerun the same ID or delete an intent. The [disaster-recovery guide](disaster-recovery.md) covers the different case where the artifact root itself is lost.

List what the artifact root holds, newest first, and drill into one run's native receipts:

```bash
uv run --locked corsair runs --case case01 --limit 10 --settings .state/settings.json
uv run --locked corsair inspect "$RUN_ID" --evidence --settings .state/settings.json
```

`runs` admits only results committed under their own `result.<run_id>` name and counts unreadable or unbound records as `invalid_records`; a nonzero count is an integrity lead to investigate, not something to delete. `inspect --evidence` reports, per observation and role, the outcome, target execution, covered lines, native exit code, cleanup confirmation, container ID and image ID, plus whether the saved receipts still pass the trusted verifier (`receipts_admissible`). It never prints payloads or the prepared case. Use the container ID and labels from a receipt with `cleanup_confirmed: false` when following up with the Docker container listing above. See the [CLI reference](../reference/cli.md#runs) for every field.

The final result retains `execution_status`, disposition, reason, rounds, artifact identities, and a manifest. Check operational state first:

- `COMPLETED` means the workflow reached final recording; it is not automatically a supported finding.
- `BLOCKED` identifies an admission or preflight-class operational block.
- `ERROR` preserves a provider, native execution, or other operational failure.
- `CANCELLED` records a cancellation path; it does not itself prove container removal.

A round’s observation records control/adversarial outcomes, target execution, relevant coverage, native exit code, feedback, and `cleanup_confirmed`. Treat `INVALID`, `ERROR`, missing evidence, or `cleanup_confirmed: false` as operational facts to investigate, never as a negative security result.

## Provider, runtime, and usage attribution

The immutable manifest binds a run to the Docker image ID; selected producer/auditor model names; and request, configuration, prompt, output-schema, capability, and budget digests. It intentionally does not copy provider credentials or endpoint URLs into the run metadata. Round outputs and sanitized lifecycle logs may include model/tool call counts, reported token counts when the provider returned them, elapsed time, provider feedback gates, and whether usage is complete. Missing token metadata is unknown, not zero or an exact cost figure.

A provider feedback gate such as `provider_policy_blocked`, `provider_temporary`, or `provider_permanent` is operational evidence. Preserve the result and redacted gate; do not silently swap providers, remove policy checks, or replay an uncertain episode to obtain a different answer.

## Logs and retention

CLI logs go to stderr and can be mirrored as structured JSON Lines:

```bash
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json --log-level INFO --log-file .state/worker.log
```

The optional file mirror is metadata-only JSONL even if stderr uses text. Fields include safe identities, activity attempts, phase/round, durations, usage, status, image ID, and redacted error classification. Prompts, source content, payloads, credentials, provider response bodies, and raw reasoning are not log fields; raw SDK diagnostics are suppressed. Still restrict logs: run IDs, local paths, timing, and workflow metadata are sensitive operational data. Logs are not evidence artifacts and are not a replacement for `inspect` or the immutable artifact store.

No in-product retention job, alerting service, or automated backup is implemented. Operators must apply their own restricted storage and backup controls; see [disaster recovery](disaster-recovery.md) before promising recoverability.
