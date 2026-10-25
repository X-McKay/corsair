# Development debugging

Debug the smallest failing boundary while preserving the same evidence and safety gates used in normal execution. This guide is for development failures; operator procedures and exact command semantics live in [troubleshooting](../operations/troubleshooting.md) and the [CLI reference](../reference/cli.md). Check current limits and known failures in [plans](../plans/README.md).

## Start with safe, attributable evidence

1. Record the command, code revision, relevant non-secret environment gates, run/workflow or operation ID, and whether the failure is local, Docker, Temporal, provider, policy, evidence, or cleanup related.
2. Reproduce with the smallest applicable command: `just check`, `just -- test ...`, `just -- test-docker ...`, or `just -- test-temporal ...`. Do not add a live provider merely to diagnose an offline failure.
3. Keep stdout result data separate from stderr diagnostics. Use normal logging or structured JSONL; logs are deliberately sanitized and omit prompts, payloads, source content, provider bodies, exception locals, and credentials.
4. Preserve immutable artifacts, intents, raw Docker receipts, and failed/unavailable evaluation rows. Never overwrite or delete them to make a rerun look clean.

A useful local diagnostic invocation is:

```bash
corsair doctor --settings /operator/settings.json --log-format json
```

`doctor` is read-only infrastructure diagnosis. It checks configured local directories, Docker reachability/image/runtime, Temporal namespace, and task-queue pollers; it neither starts services nor validates a model request, provider credentials, evidence, or future result. A poller warning is not readiness.

## Common failure boundaries

### Tooling or offline test failure

Enter the locked shell and run the individual gates:

```bash
nix develop
just sync
just check
just -- test -q -W error
```

Use formatter/type output to correct maintained files. Do not format `evals/fixtures` to resolve style noise: their source hashes and target line numbers are evidence inputs. Confirm a suspected unused symbol against Pydantic, ADK, Temporal, metadata, and wire-contract callers before removal.

### Docker daemon, image, runtime, or shared-path failure

Confirm the selected Docker SDK socket and daemon before native tests:

```bash
docker info
just images
```

On macOS, Docker Desktop or Colima supplies the Linux daemon. If the CLI context is not visible to the Python SDK, set `DOCKER_HOST` to the reviewed context socket as described in [setup](setup.md). Put `TMPDIR` and pytest `--basetemp` under a reviewed shared path when Colima cannot mount the default macOS temporary tree.

A missing daemon, image, runtime, mount, or shared path is infrastructure failure. Do not run the target on the host, mount a Docker socket into it, enable networking, grant privilege, weaken resource/cleanup limits, or substitute an arbitrary image tag to obtain a result.

### Temporal service, worker, cancellation, or result recovery

For local development, start the service and worker using the same operator-controlled settings:

```bash
temporal server start-dev --db-filename .state/temporal.db
corsair worker --settings /operator/settings.json
corsair doctor --settings /operator/settings.json
```

After a client interrupt, worker restart, or failed wait, inspect rather than assume the side effect completed:

```bash
corsair inspect RUN_ID --online --settings /operator/settings.json
corsair inspect RUN_ID --settings /operator/settings.json
```

An online inspection reports live Temporal state; the later offline read requires the immutable committed result. Ctrl-C detaches the client and does not cancel the workflow. Use the documented explicit cancellation path only when cancellation is intended, then inspect the result and receipts. Temporal history cannot reconstruct a lost local artifact store.

### Source admission, evidence, or cleanup failure

Source admission requires the configured local source root, descriptor-relative no-follow APIs, a bounded immutable snapshot, and expected digest matching where declared. Treat a denied path, symlink/replacement detection, absent capability, digest mismatch, malformed receipt, missing coverage, or unconfirmed cleanup as a failed gate—not a reason to add a pathname fallback.

Each native operation claims an immutable intent before Docker work. If an intent has no reconciled observation or a labelled sandbox might already exist, the operation is uncertain and must not be replayed automatically. Retain the identity and receipts; investigate the native condition with a new, explicitly authorized test only after understanding the uncertainty.

### Provider, structured-output, or live-evaluation failure

Provider credentials remain in the worker environment, never command arguments, files committed to the checkout, or an example. A `provider_policy_blocked`, temporary, permanent, malformed-output, or budget gate is an attributable outcome. Preserve its sanitized feedback and usage; do not disable TLS validation, change policy, silently select another provider, inflate frozen budgets, or write a decoder to force malformed output through a contract.

The required discipline: a round that reaches native `execution_error` remains `ERROR`, is recorded as such, and is never hidden as a successful safe result.

## Close the loop safely

After diagnosis, make the smallest justified change, rerun the originally failing gate and its affected consumers, then update the active plan with the cause, commands, outcome, remaining uncertainty, and cleanup state. Keep source, tests, prompt, configuration, and policy changes distinct in the record. Debugging must not turn a skipped discovery, unknown side effect, denied sandbox, or error observation into a security conclusion.
