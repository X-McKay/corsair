# Corsair evaluation workspace

A local, read-only interface for recorded agent evaluations and the operator runtime matrix. See the [local UI runbook](../docs/runbooks/local-ui.md) for the supported service command and evidence paths.

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

`npm run test:e2e` runs Playwright against a temporary real local API with explicitly synthetic saved-report fixtures, across desktop, dark and mobile configurations. Install Chromium with `npx playwright install chromium`; the test server uses `uv run --locked python`, or `CORSAIR_UI_PYTHON` when provided. These tests exercise browser behavior and rendering; they do not qualify model accuracy or runtime execution.

## Structure and evidence boundaries

- `src/pages/`: overview, searchable history, evaluation detail, per-agent cards, recorded-run experiment comparisons and runtime evidence.
- `src/components/`: shared presentational components and appearance control.
- `src/lib/`: native navigation/fetch hooks, typed response shapes and formatting.
- `e2e/`: browser integration tests owned by the UI boundary.

No launch, cancellation, credential or policy controls are present. Raw error text is withheld by the service. Report strings are rendered as text, never interpreted as HTML or links. Unknown measurements remain unavailable; mean values show observed-sample coverage. Clean attempts mean recorded evaluator success, not application execution or semantic accuracy. Runs are not declared comparable by this UI: existing identity fields do not establish the complete comparison boundary proposed in IDEA-0009.

Selected source helpers were adapted from the requested reference; see [NOTICE.md](NOTICE.md).
