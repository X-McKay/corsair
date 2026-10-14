# Corsair UI

A read-only interface for Corsair v2 run records, eval runs, baselines and the runtime matrix. See the [local UI runbook](../docs/runbooks/local-ui.md) for the supported service command and evidence paths.

## Frontend development

Node.js 22.6 or later is required. Dependencies are pinned in `package-lock.json`.

```sh
cd ui
npm ci
npm test
npm run build
npm run dev
```

The development server binds to `127.0.0.1:5173` and proxies `/api` to the Corsair service at `127.0.0.1:8765`. The production service serves `ui/dist` itself, with no Node process needed at runtime. Deep links use native browser history and the service's bounded SPA fallback.

`npm run test:e2e` runs Playwright, across desktop, dark and mobile configurations, against the real local API over records the real scripted v2 producers write into a temporary root (`e2e/server.py`). Install Chromium with `npx playwright install chromium` or set `CORSAIR_UI_CHROMIUM`; the test server uses `uv run --locked python`, or `CORSAIR_UI_PYTHON` when provided. These tests exercise browser behavior and rendering; they do not qualify model accuracy or runtime execution.

## Structure and evidence boundaries

- `src/pages/`: overview, runs and run detail, evaluations and their detail (with the reference comparison), agents and baselines, runtime matrix, system.
- `src/components/`: shared presentational components and appearance control.
- `src/lib/`: native navigation/fetch hooks, typed response shapes and formatting.
- `e2e/`: browser integration tests owned by the UI boundary.

No launch, cancellation, credential or policy controls are present. Raw error text is withheld by the service. Report strings are rendered as text, never interpreted as HTML or links. Unknown measurements remain unavailable; mean values show observed-sample coverage. Clean attempts mean recorded evaluator success; a scripted run checks plumbing, not model quality. The comparison shown is the one `evals/run.py` makes, with changed identity listed first.

Selected source helpers were adapted from the requested reference; see [NOTICE.md](NOTICE.md).
