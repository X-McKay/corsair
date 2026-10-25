# Personal-use pilot runbook

Run on a dedicated disposable Ubuntu/Debian host with Python 3.12+, `uv`, Docker and Temporal CLI/service. Do not admit third-party source on a host containing credentials or production workloads. Rootless Docker is supported; export its actual socket, e.g. `DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock`. Do not mount that socket into target containers.

## Install and verify

```bash
make sync check test
make images
make test-docker
make test-temporal
make build
```

Image building is explicit and may use the network. Investigation containers do not. If a rootless builder cannot resolve package DNS, fix the builder configuration or use `docker build --network=host -f deploy/python/Dockerfile -t corsair-python:0.1 .` during trusted image build only. This never changes the runtime's `network_mode=none` policy. The image's resolved immutable Docker ID is recorded in each manifest; changed tags create new run identities.

```bash
mkdir -p .state
cp deploy/settings.example.json .state/settings.json
# Set source_root to the smallest permitted absolute root and model configuration.
temporal server start-dev --db-filename .state/temporal.db
# Separate terminal:
uv run --locked --extra providers corsair worker --settings .state/settings.json
# Separate terminal:
uv run --locked --extra providers corsair investigate \
  evals/fixtures/case01/request.json --settings .state/settings.json --wait
```

The example Gemini model is an operator-editable example, not a verified production recommendation. Provider support and security policies may block legitimate verification requests. Do not silently change providers, retry prohibited requests, strip safety checks or report blocked execution as an application fix. LiteLLM's supported MCP dependency extra is included because its ordinary tool conversion currently imports that package; this does not enable MCP tools in Corsair.

## Recover and inspect

`corsair inspect RUN_ID --online` queries the Temporal phase/round. Without `--online`, it reads a committed result from the shared artifact store. Reusing a run ID with a new request is rejected; create a new run ID rather than silently applying old evidence. Cancel with `corsair cancel RUN_ID`; inspect the final cancellation result and resource receipts before asserting cleanup.

A completed native operation can be reconciled from its immutable committed observation. An execution intent without that observation is uncertain. Do not delete the intent to obtain a pass or blindly rerun the operation; inspect owned container IDs and retain uncertainty. Host loss requires the artifact store backup/shared filesystem as well as Temporal history. Native Temporal's replay does not restore an unrelated local filesystem.

All provider/model operations and native side effects use one Temporal activity attempt. Provider-timeout/temporary failures are surfaced; operators may authorize a new finite run, but Corsair does not pretend unknown delivery is safely retryable. Final artifact recording alone is idempotent and retried.

## Evaluation

Use native reference replay before changing driver/image logic. For prompt/model changes, run the isolated role evaluator on its frozen dev set, then the finite whole-system dataset with repeats. Oracles stay under evaluator-owned fixture paths and never enter `PreparedCase`, agent packets or Temporal child inputs. Source snapshots reject known sensitive/oracle filenames and symlinks; that is not a general secret detector for arbitrary source content.

Do not promote the tiny authored fixture corpus as a low-error-rate benchmark. Add human-labelled held-out families and recipes before team use. Unknown usage/cost remains null. Store private reports in `.runs`; package only source, sanitized validation summaries and frozen public fixtures.

## Deliberately deferred

Other languages; dependency installation/build repair; arbitrary code-authored probes; stronger hostile-target evidence attestation; HTTP/cloud recipes; application-level exposure proof; automated risk approval; negative certificates/refutation; production persistence/deployment; shared object storage; dashboards; optimization frameworks; and Alpha ADK–Temporal turn-level integration.
