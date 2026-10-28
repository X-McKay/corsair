# Recipe-free investigations implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. Preserve the dirty checkout and leave changes uncommitted.

**Goal:** Make new investigations accept issues and available images, then produce, audit and execute bounded sandbox test plans without recipes.

**Architecture:** Canonical v3 contracts and a separate Temporal workflow preserve historical wire names. ADK owns bounded role episodes; activities admit source/images and invoke a concrete Docker executor. Trusted receipts record process behavior, with security assessment unresolved.

**Tech Stack:** Pydantic, pinned Google ADK, Docker SDK, Temporal Python SDK.

**Spec:** [PLAN-0132](PLAN-0132-recipe-free-investigations.md), approved by “Please continue” on 2026-10-27.

## Global constraints

No host execution of target/test code; no pulls, builds, credentials, network or model-owned permissions. At most 16 test files, 32 KiB each, 128 KiB total; 8 commands, 64 argv entries each, 32 KiB combined argv. Existing root budgets remain authoritative. Historical schemas, fixtures and workflow/activity names stay stable. No commits or publication.

## Review focus

- Source/image/request identity changes must fail before model or execution.
- Malicious paths, archive entries and model reports cannot escape the sandbox or become trusted security evidence.
- Output floods, hangs and cancellation must bound memory/time and reconcile cleanup.
- Rejected audit must prevent execution; source copies must not be mistaken for proof of target exercise.
- Operational failures and missing role output must survive recording as explicit failures, never success or clearance.

### Task 1: Contracts and admission policy

Files: create `contracts/execution.py`, `policies/execution.py`, `tests/unit/test_execution_contracts.py`; export canonical models.
Interfaces: `ExecutionRequest`, `TestPlan`, `PlanAudit`, `ProcessObservation`, `ExecutionResult`, `PreparedExecution`, `ExecutionEpisode`, `ExecutionRoundInput`.
- [x] Write failing validation tests for relative file/cwd, byte/argv bounds, duplicate/conflicting files, image identity and no security verdict promotion.
- [x] Run `.venv/bin/python -m pytest -q tests/unit/test_execution_contracts.py`; expect missing module, then implement and pass.

### Task 2: Generic Docker execution

Files: create `adapters/sandboxing/execution.py`, `ports/execution.py`, `tests/unit/test_execution_sandbox.py`, `tests/integration/test_execution_sandbox.py`.
Interface: `DockerExecutor.execute(prepared, plan, operation_id, fixed=False, timeout_seconds=None) -> ProcessObservation`.
- [x] Write failing tests for safe archive materialization, bounded framed output, immutable operation replay refusal and real process receipts.
- [x] Implement fixed non-root/network-disabled/read-only container setup, bounded tmpfs, safe test archives, SDK exec streaming with deadlines, immutable container cleanup and receipt/artifact commitment.
- [x] Run unit tests and actual Docker tests, including timeout/flood/source-read-only checks; expect passing and explicit cleanup.

### Task 3: Native role episodes

Files: create producer/auditor `execution.py`, packaged execution instructions, `adapters/inference/execution.py`, `tests/unit/test_execution_agents.py`.
Interface: `run_execution_producer(round_input, settings, reader, model_override=None) -> ExecutionEpisode`; `run_execution_auditor(round_input, plan, settings, context, model_override=None) -> ExecutionEpisode`.
- [x] Write failing genuine ADK scripted tests for canonical output schemas, outcome-blind audit, required source reads and malformed output.
- [x] Implement one native episode per role using existing ADK accounting/runner, package resources and canonical output schemas. No custom loop or output repair.
- [x] Pass affected native/unit tests.

### Task 4: Durable activities and entrypoints

Files: create `steps/execution.py`, `workflows/execution.py`, `tests/workflow/test_execution.py`, `tests/integration/test_execution_chain.py`; modify API/CLI/worker composition.
Interfaces: `ExecutionActivities.registered()`, `ExecutionWorkflow` named `corsair.investigation.v3`, `start_execution(...)` and new-request dispatch in `start_investigation`.
- [x] Write failing admission/composition tests, audit veto and failure/recording tests.
- [x] Implement separately named activities for prepare, produce, audit, execute and record. Workflow performs no I/O; rounds obey root budgets/deadline. Fixed source reuses the same plan in a new container.
- [x] Make CLI `investigate` require v3; retain explicit historical verify/eval/API paths for archived diagnostics, not implicit old-request admission.
- [x] Run genuine ADK/Docker/Temporal composition and replay with synthetic fixtures.

### Task 5: Evaluation, documentation and delivery

Files: create frozen execution role fixtures/dataset and canonical `evaluation/execution.py`; update current guides/reference and plans. Keep legacy frozen assets unchanged.
- [x] Add deterministic categorical scoring for plan validity, audit decisions, source associations, inventory and operational failures; test scorer with fixed oracle-only inputs.
- [x] Persist intake evaluation rows incrementally so interruption remains explicit. Run synthetic live diagnostics with the user-selected endpoint; keep incomplete/failed attempts.
- [x] Review concrete boundaries with one fresh reviewer, fix important findings once with regressions, run `just check`, offline/native tests, final frozen diagnostics and `just build`; verify installed resources outside checkout.
- [x] Record exact results, unknown costs, failed/unrun gates and retained legacy boundaries; no broad qualification claim.


## Execution and qualification record (2026-10-27)

Implementation proceeded inline on `manus/just`, preserving pre-existing dirty work and leaving all changes uncommitted. Historical v1/v2 APIs/fixtures/workflow names remain explicit diagnostic compatibility; CLI `investigate` uses only v3. Reviewed execution images additionally require tar for bounded in-container materialization because Docker's archive API rejects tmpfs under a read-only root.

Independent review found four important boundary defects; each was reproduced by a failing regression and fixed: immutable uncertainty refusals, honest unknown-ownership cleanup, immutable admission comparison before side effects, and aggregate serialized envelope limits. Image drift, auditor coverage beyond four paths and pre-episode progress were regraded as important and fixed in the same pass. No review minors remain deferred. Broad hostile-source integrity, automatic vulnerability conclusions, patch effectiveness, exactly-once execution and host-loss continuation remain outside the accepted capability.

- Latest full offline suite: `nix develop --command env TERM=xterm-256color just -- test -q -W error` — **317 passed, 81 deselected**, including installed-wheel resource loading outside the checkout.
- Reviewed actual Docker/ADK/Temporal/replay selection initially passed **9**, with two additional generic-language smoke cases failing because default Node/Java tags were absent. Inventory correctly excluded them; no pull, retag or build occurred.
- Repeated with explicitly configured images already present: `CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 CORSAIR_TEST_NODE_IMAGE=corsair-node:evolution-20261025 CORSAIR_TEST_JAVA_IMAGE=corsair-java:evolution-20261025 .venv/bin/python -m pytest -q -W error -m 'not live' tests/integration/test_execution_chain.py tests/integration/test_execution_sandbox.py tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py tests/workflow/test_intake.py tests/replay/test_legacy_history.py` — **11 passed, 1 deselected** before the final CLI assertion addition. These include Python/Node/Java tool smoke tests, not general language/framework qualification.
- `nix develop --command just build` produced wheel and sdist. Both archives had **147 entries** and no private/cache/state/credential paths. Build reported the existing uv 0.13.4 versus build-system range warning; one concurrent Nix invocation also reported a busy evaluation-cache database, without preventing build.
- First and clarified live four-case role diagnostics both scored **2/4 exact** with unchanged frozen inputs/oracles. First producer returned invalid output; the clarified run had a model failure. Auditor reason mismatches remained failures even when rejection direction agreed. Both reports and resource/configuration identities remain private and distinct. Cost is unknown; no reliability or security qualification is promoted.
- The earlier eight-case intake live session ended without a final report and remains incomplete. Intake repeat, final reviewed role repeat and full live-chain attempt were denied by automatic approval review for exact external synthetic-payload authorization. Explicit requests are pending; no workaround was used. These gates remain unrun at the reviewed resource identity.
- Final quality/build/native commands are repeated after documentation and CLI assertions below; current Linux/CI and hostile-target gates remain unrun. No commit, push, PR, baseline promotion or deployment was performed.


### Final delivery checks

- Final CLI-inclusive native selection using the same explicit available Node/Java tags: **11 passed, 1 deselected in 26.29s**. The CLI `investigate --wait` and committed `inspect` both exercised the v3 path, alongside actual Docker, ADK, Temporal and replay. The first CLI test used the wrong local server address and failed; its one uniquely identified synthetic workflow was terminated, the fixture address corrected, and the full selection repeated successfully. No unrelated workflow was touched.
- Full offline suite remains **317 passed, 81 deselected**. Final Ruff, ty, documentation and package checks are repeated after this record update.
- The temporal result-envelope regression uses the actual pinned Pydantic data converter; the admitted aggregate remains below 1,000,000 bytes. Overflow preserves an immutable plan proposal and reports `RESULT_SIZE_LIMIT` before audit/execution.
- All review findings are fixed with regressions. No review findings are deferred. Live egress gates remain pending the explicit approval prompts; no final reviewed model-quality or full-live success claim is made.


### Approved live qualification continuation

After the final explanation of blocked synthetic-payload gates, the user replied “Please continue”. This authorizes the pending synthetic intake cohort, independent role cohort and full live-chain attempt at the already selected `https://llm.almckay.io/v1`. Fixtures, oracles, provider/model selection, resource identities and safety boundaries remain unchanged. Batches run sequentially to avoid competing requests distorting per-episode timeouts. Earlier denied, incomplete and failed runs remain retained; no baseline is promoted.


### Approved live results

All three previously blocked synthetic-payload gates ran after the user's “Please continue”; no egress approval remains pending for these completed runs. No product code, fixture or oracle changed during this continuation.

1. `OPENAI_API_KEY=not-required .venv/bin/python -m corsair.evaluation.intake evals/datasets/intake-capabilities.json --settings .state/intake-20261027/settings-openai.json --repeats 1 --seconds 60 --output .runs/intake-20261027/live-capabilities-approved.json` — complete **8/8 attempts**, **1/8 exact**, **2/8 classification**, **2 invalid outputs**, **0 false-supported**, **3 needs-input**. Supported-class recall **0/3**. Genuine ADK plus inspection Docker used frozen image inventories; this is not physical inventory admission qualification.
2. `OPENAI_API_KEY=not-required .venv/bin/python -m corsair.evaluation.execution evals/datasets/execution-roles.json --settings .state/intake-20261027/settings-execution.json --repeats 1 --seconds 60 --output .runs/recipe-free-20261027/roles-live-approved.json` — complete **4/4 attempts**, **3/4 exact**. Three auditor labels matched; producer returned MODEL_FAILED without a valid plan and reported 4,096 output tokens. Earlier two **2/4** reports remain preserved; no reliability improvement is promoted from a single repeat.
3. `OPENAI_API_KEY=not-required CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 CORSAIR_LIVE_CONFIG=.state/intake-20261027/settings-execution.json .venv/bin/python -m pytest -q -W error tests/integration/test_execution_live.py` — recording smoke test passed, actual investigation **INCOMPLETE**, round **OUTPUT_INVALID**. Neither auditor nor generated test execution was reached. Security remained UNRESOLVED. Do not describe this as a successful full live-chain reproduction.

The native OpenAI-compatible connector requires the existing explicit non-secret `not-required` sentinel for this unauthenticated endpoint; it is not a product credential fallback. Endpoint/model selection and output permissions were not changed. Exact resource/configuration identities, usage and artifact references remain in private reports; missing cost stays unknown.

The approved chain resource identity matched the reviewed current package. Dataset digests: intake `bb2137e8f159e0228bdf52f4052c64885c0951960dc3712c78ba2eb9139c2c55`; roles `100cc5e166976484654b0551259c819192c087216d8863b897129af658bca240`. Fixture hashes and labels were not changed. Model qualification remains open in [ISSUE-0015](ISSUE-0015-intake-v3-live-quality.md).
