# Corsair UI

A read-only view of what Corsair v2 writes: run records (`corsair-v2-run/1`, [RUN_RECORD.md](../../src/corsair/RUN_RECORD.md)), per-agent and chain eval runs (`corsair-eval-summary/v1`, [evals/agent_summary.py](../../evals/agent_summary.py)), committed and promoted baselines, the v2 runtime matrix, Temporal executions of `corsair.v2.Investigation` and OpenShell gateway health. It launches no work and changes no configuration. Design: [SPEC-0084](../development/specs/SPEC-0084-v2-results-ui.md).

## Start

Node 22.6 or newer, npm, Python 3.12 and the repository's uv environment:

```sh
make ui-install    # npm ci in ui/
make ui-build      # ui/dist
make ui            # http://127.0.0.1:8765, loopback only
```

By default it reads, under the checkout:

| Source | Default | Written by | Override |
| --- | --- | --- | --- |
| Eval runs | `.runs/evals/<agent>/<run>/` | `make eval AGENT=...` | `--results`, `CORSAIR_UI_RESULTS` |
| Run records | `.runs/v2/runs/<run id>/` | `corsair-v2 run` | `--runs`, `CORSAIR_UI_RUNS` |
| Runtime matrix | `deploy/v2/runtime-matrix.yaml` | operator | `--runtime-matrix`, `CORSAIR_UI_RUNTIME_MATRIX` |
| Committed baselines | `src/corsair/agents/<agent>/evals/baselines/`, `evals/e2e/baselines/` | `make baseline-commit` | checkout (`--root`) |
| Built assets | `ui/dist` | `make ui-build` | `--assets`, `CORSAIR_UI_ASSETS` |

To see something at once without a model, run scripted evals; the chain eval also keeps each attempt's own run record, which the UI links from every attempt row:

```sh
make eval AGENT=chain        # 132 chain cases, scripted, no Docker; each attempt's record under evidence/runs/<n>
make eval AGENT=reviewer
```

Live runs (`PROVIDER_CONFIG=...`, `corsair-v2 run --case ...`) appear the same way once written. Pages refresh every 30 seconds while visible; Refresh reads at once. In a worktree, `.runs` is that worktree's own; point `--results`/`--runs` at another checkout's `.runs` to read it.

## Pages

- **Overview**: run-record counts by verdict, recent run records and eval runs.
- **Runs**: every run record, filterable by verdict. A record without a verdict is `incomplete` (it never proves work is still running). Below, the Temporal executions (when configured); a workflow id `corsair-v2-<run id>` links to its record.
- **Run detail** (`/runs/<run id>`, or `/evaluations/chain/<run>/attempts/<receipt>` for a chain eval attempt): the verdict (label, rule, terminal reason, finding, fix), `sensitivity: unverified` on R5, the finding, probe outcomes per revision and role with their facts (exit class, start/end markers, token, check marker, cleanup), exploit attempts (D18), the Reviewer's outcome-blind validity with defects and citations, per-agent calls/tokens/retries/statuses, the stage timeline and provenance (commit, matrix and provider-config digests, runtime row and image, environments). A chain eval attempt also shows the evaluator's expected label.
- **Evaluations**: eval runs filterable by agent, mode and status. **Detail**: clean attempts, completion, decisive rate (chain), p50/p90 wall time and tokens; the comparison with the run's reference (promoted baseline, else committed baseline, else the previous whole-set run of the same set and mode, as `evals/run.py` chooses; a language-narrowed run compares with the reference's rollup for that language); dispositions against evaluator labels; rollups by language and case kind; every attempt with its failed checks; release policy entries (deferred: never the exit code); identity and parameters.
- **Agents**: per agent and for the chain, the latest whole-set live and scripted run, committed and promoted baselines, and the live run's dimension rates.
- **Runtime matrix**: each row's evidence level (`canary-only`, `image-only`, `live`), detection, run template, exit-code map and image; the matrix digest matches a run record's `matrix_sha256`.
- **System**: source checks and the Temporal/OpenShell probes.

## What is never shown

The server projects every value through an allow-list. It never returns message histories (`agents/*.messages.json`), stage outputs, probe output, `usage.json` error text, eval task-failure text or command argv. Strings are rendered as text. Unknown telemetry stays unknown; a measured zero stays zero. Read the record directory for anything withheld.

## Services

Optional and read-only, each bounded to two seconds with no retries:

- Temporal: `CORSAIR_UI_TEMPORAL_ADDRESS` (`host:port`), `CORSAIR_UI_TEMPORAL_NAMESPACE` (default `default`), optional `CORSAIR_UI_TEMPORAL_TLS_CA/CERT/KEY`. Lists up to 100 `corsair.v2.Investigation` executions (no inputs, results or history); needs DescribeNamespace and ListWorkflowExecutions.
- OpenShell: `CORSAIR_UI_OPENSHELL_ENDPOINT` with `CORSAIR_UI_OPENSHELL_TLS_CA/CERT/KEY`, or else `CORSAIR_OPENSHELL_CONFIG`, the backend config `make openshell-config` writes (only its `endpoint`, `ca`, `cert` and `key` are read). Reports gateway health only.

Reachable does not mean a worker is serving, an image is present or a sandbox would be admitted.

## Validate

```sh
make ui-check                                  # unit tests and type-checked build
uv run --locked python -m pytest tests/ui      # API, services and deployment renderer
cd ui && npx playwright install chromium && cd .. && make ui-test
```

`make ui-test` seeds a temporary root by running the real scripted chain eval and the reviewer eval twice, files three of the chain's run records as `corsair-v2 run` would, and adds one incomplete record, one malformed record and one hostile finding title; then Playwright runs desktop, dark and mobile checks against the real API. Set `CORSAIR_UI_CHROMIUM` to use an installed Chromium instead. No test calls a model or starts a sandbox.

## Kubernetes

```sh
docker build -f deploy/ui/Dockerfile -t corsair-ui:review .
PYTHONPATH=src:. uv run --locked python -m deploy.ui.render \
  --image "$UI_IMAGE" --namespace "$CORSAIR_NAMESPACE" \
  --results-claim "$CORSAIR_RESULTS_CLAIM" --public-origin "$UI_ORIGIN" > /tmp/corsair-ui.yaml
```

The image holds the built assets, the `corsair` package (for the matrix contract and the committed per-agent baselines) and the `ui` dependency group only; no records, fixtures or credentials. The renderer emits a ConfigMap (the validated v2 matrix), a Deployment and a ClusterIP Service for an **existing** namespace and claim; no PVC, namespace or ingress. The claim is mounted read-only at `/data` and laid out like `.runs`: eval runs in `/data/evals`, run records in `/data/v2/runs`. Producers write there with `CORSAIR_EVAL_RESULTS=/data/evals make eval AGENT=...` and `corsair-v2 run --run-root /data/v2/runs`. Service connections: `--temporal-address`, `--temporal-namespace`, `--temporal-tls-secret`, `--openshell-endpoint` with `--openshell-tls-secret` (Secrets with `ca.crt`, `tls.crt`, `tls.key`).

The container runs as UID 10001 with a read-only root filesystem and a 32 MiB `/tmp`. `/api/live` is the process; `/api/ready` is 200 when assets and the matrix are readable and at least one record source is; otherwise 503. A missing mount is never shown as zero records. The app has no login: expose it only behind the operator's authenticated ingress, with `UI_ORIGIN` set to its exact origin.

`deploy/ui/smoke.py --image ... --data <root> --runtime-matrix deploy/v2/runtime-matrix.yaml` checks a built image against a root holding one fresh scripted chain eval and some run records (CI builds that root from the real chain eval), then confirms the missing-storage 503 and removes its own containers.
