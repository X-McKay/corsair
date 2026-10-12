# Native issue-analysis fixture composition

Use this runbook for [SPEC-0015](../development/specs/SPEC-0015-native-issue-analysis-composition.md). [Qualification](../qualification/issue-analysis-temporal-fixture.md) records the fixed fixture envelope and actual failures. This uses the same native capability-equipped agent directly and durably, with registered fixture models and model network requests disabled. It does not select real providers or OpenShell tools.

## Offline checks

From the repository root with the locked Python 3.12 environment already installed:

```sh
PYTHONPATH="$PWD/src:$PWD" .venv/bin/python -m pytest \
  tests/temporal/test_issue_analysis_composition.py -q
```

This exercises direct capability transparency, typed result conversion, admitted model keys, a typed request carrying an operator budget (request, tool-call and total-token limits) under the workflow's ceiling with typed non-retryable refusals, and native usage-limit enforcement. It starts no service. Use the existing [Temporal development runbook](temporal-fixture.md#prerequisites-and-ownership) for verified CLI acquisition and explicit service ownership. The selected CLI 1.9.1 binary must match SHA256 `712217694cac9f786a72d4b6c876cd15f3dcf1bf31434d9fed6af25242a327a0`; do not use an implicit SDK download or a floating service.

## Explicit native composition

Choose a fresh ignored directory; refuse reused evidence and occupied ports. Freeze the relevant workflow, existing agent/prompt/contracts, fixture models/oracles/inputs, tests, dependency lock and runtime pins before execution. Start the verified native service in the dedicated foreground terminal you own:

```sh
TEMPORAL_BIN="$PWD/.tools/linux-amd64/temporal-1.9.1"
printf '%s  %s\n' '712217694cac9f786a72d4b6c876cd15f3dcf1bf31434d9fed6af25242a327a0' "$TEMPORAL_BIN" | sha256sum --check
TEMPORAL_RUN="$PWD/.runs/issue-analysis-temporal-001"
mkdir "$TEMPORAL_RUN"
"$TEMPORAL_BIN" server start-dev --headless --ip 127.0.0.1 \
  --port 17333 --http-port 17334 --metrics-port 17336 \
  --db-filename "$TEMPORAL_RUN/service.sqlite"
```

In a second terminal with that same explicitly owned service:

```sh
TEMPORAL_RUN="$PWD/.runs/issue-analysis-temporal-001"
PYTHONPATH="$PWD/src:$PWD" .venv/bin/python -m pytest \
  tests/temporal/test_issue_analysis_composition.py \
  tests/temporal/test_issue_analysis_native.py -q -x \
  --temporal-address 127.0.0.1:17333 \
  --temporal-evidence-dir "$TEMPORAL_RUN/histories" \
  --junitxml "$TEMPORAL_RUN/junit.xml"
```

The native plugin registers the selected test-owned agent and separate model/tool activities. Calls supply all declared workflow arguments explicitly so Temporal's native converter can apply the typed hints. Tests save/replay actual histories, compare direct/durable outputs and usage, exercise meaningful failure controls and capture local native spans with hosted sending/metrics disabled. Saved history/comparison/span exports use exclusive writes. There is no test-created service, network-model fallback or external payload resource.

Without an explicit address native checks skip, which supplies no native qualification. An explicitly unavailable endpoint fails. Retain every failed run and inspect original native state before another attempt; no blind retry of an unknown operation or reused evidence directory.

## Cleanup and interpretation

Stop the exact original owned service with Ctrl+C in its dedicated terminal and wait for that process to exit. Retain its immutable PID/start identity and exit status; confirm the original identity is absent and all three selected endpoints are closed. Do not use process-name matching or terminate unknown occupants. Keep SQLite, histories, local span summaries, source freeze, JUnit and failures private under `.runs/`.

Fixture token counts are estimates. Native same-version replay with no repeated positive execution spans does not qualify provider reasoning, production database durability, worker death/lost completion, cross-version replay, hosted telemetry or metrics. Real inference and OpenShell execution have independent admission/qualification records.
