# Native Temporal fixture development

This runbook exercises [SPEC-0013](../development/specs/SPEC-0013-temporal-fixture-foundation.md). It uses an explicitly owned local development service and trusted inert fixtures. It does not deploy production Temporal or connect OpenShell/models. [Qualification](../qualification/temporal-fixture-foundation.md) records actual coverage and failures.

## Prerequisites and ownership

Use Python 3.12 and the repository locked dependencies: Temporal SDK 1.34.0, PydanticAI/Evals 2.55.0. Root-selected stable CLI 1.9.1 embeds service 1.32.0. Obtain the Linux amd64 archive and its checksum from the [official immutable release](https://github.com/temporalio/cli/releases/tag/v1.9.1), verify the archive **before extracting**, and supply the verified binary explicitly. The selected archive SHA256 is `09a0326a51db84d02735e53542b9ebd8c4758daf47482a9ab0abce15844e60d5`; extracted binary SHA256 is `712217694cac9f786a72d4b6c876cd15f3dcf1bf31434d9fed6af25242a327a0`. Never implicitly download a floating server from test startup.

Reserve exclusive loopback ports and a fresh ignored evidence directory. The example selects 17333/gRPC, 17334/HTTP and 17336/metrics, with the UI disabled. Refuse an occupied port; do not stop an unknown process. Only the operator managing the original service process controls its SQLite database. Keep the database and native histories private under `.runs/`; no workload credentials are required.

From the repository root, verify the selected binary, then start it in a dedicated terminal whose original foreground process you own:

```sh
TEMPORAL_BIN="$PWD/.tools/linux-amd64/temporal-1.9.1"
printf '%s  %s\n' '712217694cac9f786a72d4b6c876cd15f3dcf1bf31434d9fed6af25242a327a0' "$TEMPORAL_BIN" | sha256sum --check
"$TEMPORAL_BIN" --version
TEMPORAL_RUN="$PWD/.runs/temporal-fixture-001"
mkdir "$TEMPORAL_RUN"
"$TEMPORAL_BIN" server start-dev --headless --ip 127.0.0.1 \
  --port 17333 --http-port 17334 --metrics-port 17336 \
  --db-filename "$TEMPORAL_RUN/service.sqlite"
```

The SDK/tests do not start services. `start-dev` is the upstream development configuration; SQLite persistence across this process restart is a bounded local check, separate from production deployment/database guarantees. Do not alter SQLite pragmas, dynamic configuration, policies or authentication to obtain a passing result.

## Component checks and native matrix

Offline fixture checks allocate no service:

```sh
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  uv run --locked python -m pytest tests/temporal/test_fixture_contracts.py
```

In a second terminal, while the explicitly owned service is running:

```sh
TEMPORAL_RUN="$PWD/.runs/temporal-fixture-001"
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  uv run --locked python -m pytest tests/temporal \
  --temporal-address 127.0.0.1:17333 \
  --temporal-evidence-dir "$TEMPORAL_RUN/histories" \
  --junitxml "$TEMPORAL_RUN/junit.xml"
```

Without `--temporal-address`, native service checks skip and establish no qualification. An explicitly selected unavailable endpoint fails. No time-skipping server, mocked transport or automatic fallback replaces it. These checks record native failure/retry outcomes, cancellation, graceful worker replacement and replay of actual histories.

## Persistent-service process restart

Choose a unique workflow identity and retain it across both probe processes:

```sh
TEMPORAL_RUN="$PWD/.runs/temporal-fixture-001"
TEMPORAL_ID='corsair-persistent-fixture-001'
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  uv run --locked python -m tests.temporal.checkpoint prepare \
  --address 127.0.0.1:17333 --identity "$TEMPORAL_ID" \
  --evidence-dir "$TEMPORAL_RUN/persistent"
```

Preparation ends its Worker and leaves the child waiting after a completed preparation activity. Stop the original service in its dedicated terminal with Ctrl+C; wait for that original process to exit and confirm its endpoints are closed. Retain its PID/start identity, exit status and SQLite bytes. Restart the same verified native command with the **same database path**, then run a separate Python process:

```sh
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  uv run --locked python -m tests.temporal.checkpoint resume \
  --address 127.0.0.1:17333 --identity "$TEMPORAL_ID" \
  --evidence-dir "$TEMPORAL_RUN/persistent"
```

Resume requires the original child history/run, sends one release signal, observes one completion, and exports/replays both final histories. A failed/unknown probe is retained; inspect original native state before another operation instead of blindly rerunning `prepare`. Service restarts are graceful process restarts, not host crashes or storage-fault tests.

## Cleanup and evidence

Stop the exact original owned foreground service and wait for it to exit. Confirm the original PID/start identity is absent and all three selected endpoints are closed; do not use process-name matching or kill unknown occupants. Keep the private database, source freeze, command/error logs, JUnit and histories for review. Tests create no sandboxes or external fixture resources, so their payload cleanup is `not_required`; service process cleanup must still be independently confirmed.

Tracing/exporters, server crashes, worker death during activities, actual external unknown dispatch, resource cleanup, production service/database configuration and cross-version replay remain separate gates.
