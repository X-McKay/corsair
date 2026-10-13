# Local results UI

The Corsair UI inspects existing host evaluation results and the operator runtime matrix. It does not launch work or change configuration. It adapts the InfoSec Harness UI patterns for Corsair's own evidence contracts; see [SPEC-0069](../development/specs/SPEC-0069-local-results-ui.md).

## Start

Use Node 22 or newer, npm, Python 3.12 and the repository's uv environment:

```sh
make ui-install
make ui-build
make ui
```

Open http://127.0.0.1:8765. This serves the production build and same-origin read-only API from a loopback listener. Stop with Ctrl-C. Rebuild after changing UI source. The initial screen is empty if this checkout has no saved evaluations; worktrees have separate ignored `.runs` directories.

Generate a scripted host evaluation in another terminal to populate real local results:

```sh
make eval AGENT=identification
```

Refresh the UI after a run finishes. Scripted results measure the fixture/evaluation plumbing, not live model quality. Live-provider evals remain explicit CLI actions under their existing configuration and budgets.

For an alternate port or results checkout, use the server directly from the UI checkout:

```sh
PYTHONPATH=src:. uv run --locked python -m corsair.web --root /absolute/path/to/corsair --port 8766
```

The selected root must contain the runtime matrix and built UI; do not point it at an untrusted directory. There is no remote bind option. This is a local inspection tool, not an authenticated production service. Do not expose it through a tunnel or reverse proxy as a multi-user app.

## Metrics

Open Metrics for aggregate recorded runs/attempts and per-agent cohort tables. Select an agent or evidence mode, then a cohort, to view evaluator success, task completion, observed token totals and latency/input/output histograms. Histograms use individual native report samples, with sample counts and coverage. Live token samples require an explicit provider-usage receipt; failed-attempt telemetry is currently unavailable and remains in the denominator.

The service reads at most 500 run summaries, 100 native reports and 20,000 case samples per metrics request; each JSON file is bounded to 4 MiB. Warnings identify missing, inconsistent, omitted or truncated evidence. Groups reflect recorded identities, not proof that every effective setting is known. No general semantic accuracy is invented: individual recorded correctness checks and their pass rates remain visible.

## Interpret results

- All checks passed means the saved evaluator assertions passed; it is not a general accuracy or security claim.
- Unknown telemetry stays unknown. Zero represents an observed zero only. Means show measurement coverage; failed attempts may have incomplete telemetry in current native reports.
- Different agents, datasets, provider settings and execution modes are not one comparable accuracy population.
- Host authoring and environment results use static or synthetic observations. They do not prove generated tests or setup commands executed.
- Runtime image-only evidence is distinct from live qualification and from successful execution of a particular repository.
- The server returns selected summary facts only. It does not serve raw inputs, transcripts, source artifacts, arbitrary files or credentials. Untrusted labels are rendered as plain text.

## Validate

```sh
make ui-check
# Once per environment, install the test browser:
cd ui && npx playwright install chromium
cd ..
make ui-test
```

API tests run with `make test-config`. Browser fixtures are synthetic local saved-result records, kept separate from actual run evidence. No browser test calls a model or starts a sandbox.

## Troubleshooting

A missing build needs `make ui-build`. A port-in-use error needs a different `--port` or stopping the listener you started. Empty results usually mean evaluations were saved in another checkout; inspect `.runs/evals` in the selected root. Malformed, oversized or unreadable records are reported as unavailable, not successful. The server rejects unexpected Host/Origin values and unsupported methods; use its printed loopback URL rather than an external hostname.
