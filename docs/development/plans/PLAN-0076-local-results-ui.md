---
id: PLAN-0076
kind: plan
title: Local Corsair results interface
status: complete
updated: 2026-10-13
related: [SPEC-0069, SPEC-0044, IDEA-0009]
---

# Local Corsair results interface

## Objective and dependencies

Implement SPEC-0069 in managed worktree corsair-ui on branch codex/corsair-ui, starting from main e760f05. User authorized parallel development and selected inspection of existing results. Reference source: infosec-harness UI at 52aa2ac. No existing Corsair web API; use a narrow local read-only projection over current evidence formats.

## Steps

- [x] Build bounded read-only API and static server; validate filesystem and HTTP boundaries.
- [x] Adapt frontend presentation with real Corsair evaluation/runtime contracts and provenance.
- [x] Wire Make commands, documentation and CI checks.
- [x] Validate browser behavior and visual quality against real local API; run affected offline suite.
- [x] Review, resolve findings, update current index and handoff.

## Validation and progress

Initial inspection: harness UI has routes backed by Temporal/API contracts that Corsair does not implement. Selected patterns and helpers will be adapted instead of exposing unsupported actions. Backend and frontend agents work in parallel with an explicit JSON contract; root owns integration and browser validation. No live model or sandbox calls authorized by or necessary for this scope.

## Decisions and next action

Keep React/TypeScript/Vite for familiar frontend development and use stdlib Python HTTP for local inspection only. Avoid another router/query framework unless needed. Do not implement IDEA-0008 release gates or change agent/evaluation semantics. Implemented the read-only UI, native-sample metrics, reference neutral/violet styling, loopback API and CI. Ready for PR review; no production deployment or model/sandbox qualification.


Final implementation evidence (2026-10-13):

- Two implementation subagents owned API and frontend independently; root owned integration, metrics view, browser validation and records. Backend also reviewed frontend metric claims.
- API boundary: 37 focused tests passed. Native per-attempt metrics preserve0 and omit live tokens without explicit usage coverage; cohorts hash recorded identities and isolate missing identities. Caps500summaries/100reports/20k samples are reported.
- Frontend: production TypeScript/Vite build and9 unit tests passed; selected helpers and contrast audit retain upstream attribution. No remote assets or telemetry.
- Browser:34passed,5 intentionally skipped duplicate mobile contrast checks. Real local API and production assets exercised in desktop/dark/mobile projects. First contrast harness invocation incorrectly passed a page wrapper to page.evaluate (10failures); corrected harness exposed3light-theme sidebar count contrast failures, fixed and rerun green. A real dark-theme inherited text/background issue was caught visually and fixed. No failures hidden.
- Existing scripted identification eval generated16/16clean attempts; observed in UI with actual native-token/latency distributions. These are scripted fixtures, not live performance/accuracy. Screenshot retained locally outside Git.
- Dev server API proxy health smoke passed after explicit target Host rewrite; production listener remains same-origin loopback only.
- Initial full make test-config:1782passed in108.58s. Final expanded suite result recorded in publication handoff. No live inference, Temporal server or sandbox workloads launched.

The user explicitly expanded scope to aggregate/per-agent metrics and distributions, and requested the reference app aesthetic. Both are included. The read-only launch restriction remains.

## Approved design iteration

User approved the interactive operations, per-agent and experiment mock-ups, then requested one card per agent with stats and histogram frequency-line overlays. Implement using real saved evidence only. One card per recorded agent selects an identity cohort; never merge different settings/modes into a score. Add a read-only run comparison view with explicit missing/incompatible evidence, aggregate overview distributions, same neutral/violet theme, and native per-case total-token samples only when both input/output are observed. Preserve inspection-only scope.

- [x] Implement approved cards, overview charts and recorded-run comparison.
- [x] Check histogram math, cohort changes, missing/zero metrics, comparisons, browser layouts and contrast.
- [x] Run offline guards, review and record final source/checks.

Approved design implementation evidence (2026-10-13):

- Merged main 184e609 into the UI branch (merge 65169e7) before final qualification. Existing primary-checkout edits remain untouched.
- One independent card per recorded agent, with cohort selection, evaluator success/task completion, explicit undefined accuracy, latency and paired total-token distributions. Shared bins and frequency lines preserve counts; observed zero stays zero and incomplete denominators stay unknown.
- Overview resource distributions separate scripted/live modes. Experiments compares explicit saved runs, blocks incompatible datasets/agents/sets/modes, and exposes recorded identity changes and incomplete telemetry. No automatic baseline or promotion.
- Review fixed native-suite versus wrapper-mode comparison (scripted_fixture/direct_local_provider are distinct from scripted/live). Server tolerates client cancellation without a second error response.
- Final make ui-build:17 frontend unit tests and TypeScript/Vite production build passed. Final make ui-test:42 passed,6 deliberately skipped duplicate mobile contrast checks in4.2s, including desktop/dark/mobile layouts and a populated experiment comparison.
- First iteration browser run:37passed,5failed,6skipped. Failures came from a duplicated warning strict locator and an outdated comparison-heading assertion. Deduplicated warnings and corrected the assertion; retained cancellation trace led to a server fix. Final suite passed.
- Final UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config after main merge:1831passed in112.39s, including43 focused web-server tests. Earlier pre-main-merge integration:1793passed in109.96s.
- Actual saved scripted identification report inspected in production preview at127.0.0.1:8765/agents:1run,16attempts,16observed latency/token samples. No new live inference, Temporal server or sandbox workload. Screenshots/logs remain outside Git. Final record guards and publication are recorded in HANDOFF-0101.


## Descriptive copy revision (2026-10-13)

Replaced slogans and promotional headings across overview, agents, evaluations, experiments, empty states and the sidebar with descriptive labels and instructions. The earlier mockup was updated separately outside Git, including “Did the change help?” → “Run comparison.” Metric definitions, coverage caveats and error guidance remain. No data, API, execution or styling changes. Existing browser assertions now use the revised headings; no redundant copy-only tests added.

Validation: make ui-build passed17 unit tests and the production build; make ui-test passed42 checks with6 deliberately skipped duplicate mobile contrast checks. Revised Agents copy inspected in the production preview after restarting its stopped local server. Review found no behavior changes or unsupported new claims. Final make test-config:1831passed in111.98s; final development record guards:5passed. git diff --check and mockup JavaScript syntax check passed.


## Aladdin-inspired appearance (2026-10-13)

User requested the BlackRock Aladdin palette and aesthetic. Inspected the official public reference https://www.blackrock.com/aladdin: black/white and gray surfaces, teal rgb(0,207,186), blue rgb(0,94,184), square buttons and strong sans-serif headings. Applied these visual cues using local Arial/Helvetica fallbacks, black selected navigation with teal marker, square-edged cards/controls, teal distributions and blue live-mode badges. Light-mode small text uses darker teal for contrast; dark mode uses charcoal surfaces and bright teal. Corsair branding, factual copy and existing layouts/metric semantics remain. No external fonts, copied logos, dependency changes or behavioral changes. The earlier mockup received matching tokens outside Git.

Validation: make ui-build passed17 UI unit tests and production compilation. First two unrestricted parallel browser runs each had41passed/1failed/6skipped: Chromium Page.captureScreenshot failed in different desktop tests, with no application assertion failure. Repeated with CORSAIR_UI_PYTHON=<worktree>/.venv/bin/python npx playwright test --workers=2:42passed/6 intentionally skipped duplicate mobile contrast checks in9.7s. All light/dark contrast tests passed; production Agents preview and saved dark screenshot inspected. Logs retained in /tmp/corsair-ui-aladdin-*.log. Final make test-config:1831passed in115.43s. Record guards:5passed; git diff --check and mockup JavaScript syntax check passed. Review also adjusted outcome-column width and metric typography so textual unknown values fit without splitting.


## Approved UI finalization (2026-10-13)

After user approval, checked PR #107 at1c0e937. Automated review finding4261412039 remained valid: complete passing counts without command.exit_code could appear Clean. Clean now requires recorded exit_code0; absent command/exit stays Incomplete, and known command or evaluator failures stay Needs attention. Added regression cases including status filtering. make ui-check:18tests and production build passed; make ui-test:42passed,6 deliberately skipped duplicate mobile contrast checks in9.7s.

Remote UI job38444867282 failed waiting5s for the runtime-page h1; no browser artifact had been retained, so the root cause is not established. Browser assertions now have a bounded15s wait within the existing30s test timeout, default workers are capped at2 (also addresses prior local screenshot pressure), and CI retains synthetic-fixture screenshots/traces for7days on failure using a commit-pinned official action. No automatic retry or weakened assertions added. This improves timing tolerance and diagnostics; only the next remote run can establish current CI status.

Final local checks for this revision: make test-config1831passed in110.37s; development record guards5passed; git diff --check passed. No live model or sandbox calls.


## Kubernetes integration (2026-10-13)

User requested real data/service connections without placeholders and selected deployment alongside Corsair in Kubernetes. Audit found production pages already use saved native records, but loopback-only serving, combined checkout roots and silent missing-directory handling prevented reliable deployment. No existing general application API/worker chart exists; use existing native Temporal visibility and filesystem report contracts, not invented endpoints. The earlier illustrative design file is not application data.

- [x] Separate configured data/assets/matrix roots, surface missing storage and implement common local/production route boundary.
- [x] Native read-only service checks and parent investigation visibility; no raw workflow payloads.
- [x] Production container and internal Kubernetes resources with explicit existing PVC and origin.
- [x] Verify actual eval producer output through deployed-style mounts/server, source failures, UI routes and full offline guards.
- [x] Review, document operator configuration and remaining live gates; update PR and handoff.

Pinned production WSGI server chosen because stdlib HTTP is only a development server; reuse its narrow application routes without another web framework. Gunicorn official docs/release notes and PyPI inspected:26.2.1 appears in upstream release material but is not installable from current PyPI; pin available 26.2.0. An initial uv lock at26.2.1 failed before installation; corrected to the published release. The separate `ui` dependency group includes the server, matrix validation and required native SDK dependencies. Existing eager agent-package imports require PydanticAI; the viewer does not invoke models or evaluations.


Implementation and review evidence:

- Common read-only Application serves local HTTP and production WSGI. Explicit results/assets/matrix roots, actionable 503 for missing storage, process liveness and data-source readiness are separate. ConfigMap symlinks are resolved only for the operator-selected matrix; evidence/assets keep descriptor-based link refusal.
- Native Temporal namespace and parent-investigation visibility plus OpenShell health checks use explicit endpoint/TLS config. Fixed workflow types, 100-row limit, 2s native deadlines, no retries/payload/history retrieval. Missing endpoints remain not_configured. A real loopback Temporal refusal was observed at the transport layer in 0.08s; this is not a successful service qualification.
- UI Runs/System pages, 30s visible-tab refresh, 15s request timeout and safe backend error detail. Same approved styling. 18 frontend unit tests/build and 64 browser tests passed,8 duplicate mobile contrast checks skipped; production Agents/System visually inspected against the actual newly generated identification report.
- New producer env configuration verified with an actual scripted identification run, 16/16 clean attempts, in /tmp/corsair-ui-connected-results. A regression runs the real producer from another cwd with relative configured output and verifies report counts/latencies through Evidence.
- Independent review found relative producer output could split native reports from summaries and renderer OpenShell HTTPS URLs did not match native SDK host:port targets. Both corrected and regression-checked. Explicit empty producer env is refused. 85 combined web/service/deployment/producer tests passed.
- Container testing caught missing eager-import PydanticAI dependencies and Gunicorn's default control socket on a read-only filesystem. Added the existing pinned native SDK dependency and disabled the unnecessary control socket; no agent behavior changed. Final image sha256:8d8805a11b516277d93093adae0a464af5f6eb4579d9b0033652e9582cbeef52 built successfully. Final smoke compared real counts and exact native latency/input/output/paired-token distributions, served production assets, checked nonroot/no baked records, and verified absent storage 503. Owned containers 0108deb2aca0 and ab8aae41b1cd were removed by immutable IDs with absence confirmed. Raw logs/results stay outside Git.
- CI now builds the same production image and runs the smoke against a freshly generated scripted eval. Kubernetes renderer uses existing explicit PVC/namespace/image/origin and optional existing TLS Secrets; 18 focused renderer checks passed. A client dry-run attempted API discovery and was blocked; no cluster mutation performed. No target deployment, successful native service connection, remote auth or live model/workload qualified.
- First full offline integration check: 1862passed/1failed due to using unsupported plan status 'active'. Changed it to 'in_progress'; final suite recorded below. Initial dependency resolution failed on unavailable Gunicorn 26.2.1; official PyPI available 26.2.0 pinned. Initial renderer subprocess test lacked its documented PYTHONPATH; corrected module invocation. No failed check is counted as a pass.

Final integration validation: `UV_CACHE_DIR=/tmp/corsair-provider-uv-cache make test-config` passed **1873 tests in 109.54s**. Final development-record checks and publication are performed with this revision; remote CI must be checked at its published head. Target-cluster live gates remain unqualified as scoped above.


Publication follow-up: dbd4b94 pushed to PR107. Remote UI run38448429354 passed frontend/browser checks, built the production image, generated the actual16-attempt report and matched its API/native distributions, then failed the immediate post-stop cleanup confirmation. The log does not establish whether Docker diagnostic wording or removal timing caused that assertion. Replaced diagnostic-text matching with up to5seconds of successful read-only container-list queries filtered by the exact owned ID; no blind stop/delete retries. Failure still leaves cleanup explicitly unconfirmed. Final local smoke and remote rerun are checked before reporting completion.
