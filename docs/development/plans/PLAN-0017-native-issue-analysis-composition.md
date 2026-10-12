---
id: PLAN-0017
kind: plan
title: Native issue-analysis fixture composition
status: complete
updated: 2026-10-12
related: [SPEC-0015, PLAN-0015, PLAN-0016]
---

# Native issue-analysis fixture composition

## Objective and dependencies

Implement [SPEC-0015](../specs/SPEC-0015-native-issue-analysis-composition.md), the independent priority 1A direct/native-durable fixture composition. Existing fixture foundations are admitted within their reports; no real provider or OpenShell dependency is used. Root assigned exclusive verified CLI, loopback ports 17333/17334/17336 and private SQLite/evidence ownership. Pydantic agent owns the coordinated optional native durability factory seam; this agent will not edit that factory or shared configuration.

## Steps

- [x] Inspect branch/source/HANDOFF-0024, verify IDs unused, and research selected native integration/telemetry APIs.
- [x] Coordinate native capability injection with the factory owner, implement one small workflow base and fixture-only concrete binding.
- [x] Run smallest meaningful direct/conversion/negative checks before service creation.
- [x] Freeze selected inputs; run actual direct/durable fixture matrix, negative cases, local native telemetry and history replay on owned native service.
- [x] Confirm original process cleanup, review owned diff/evidence, update report/runbook and deliver root handoff.

## Validation and progress

Evidence root: `.runs/four-priorities-20261012/temporal-agent` (ignored). Root owns shared dependency/configuration/Git and final integrated records; the factory owner supplied the coordinated optional native durability seam and stable final prompt-v3 one-based inclusive line/range metadata. Current Python 3.12.13/PydanticAI 2.55.0/Temporal SDK 1.34.0 and verified CLI 1.9.1/service 1.32.0 were used without an install by this agent.

- Research inspected public native capability, plugin registration/converter/failure rules, concrete workflow requirement and supported local replay-safe LogfirePlugin. Context7 discovery succeeded; immutable web raw retrieval returned a cache miss, so retained selected v2.55.0 documentation and installed selected-version source supplied exact API evidence.
- Two initial offline collections failed for incorrect SimpleSpanProcessor import and inherited decorated-run definition. Correcting native API uses produced five passes/six explicit native skips. Offline suite was renamed to `test_issue_analysis_composition.py` before freeze to avoid a basename import collision with existing agent tests. Combined existing agent/new offline checks passed 31 / 0.45s before the coordinated prompt-v2 update; this is retained and not represented as the final factory baseline.
- Native001: 3 positive timeouts, 8 passes / 91.92s. Two arguments for a three-argument native run caused Temporal argument-count matching to drop typed hints; dict inputs failed workflow tasks before model execution. Native plugin source confirmed the selected converter was correct. The three negative cases passed their intended native causes and local failure spans. PID 1513807/start 51642975 exited zero; original identity absent and all endpoints closed. Database/diagnostic histories retained; pending positives are not claimed complete.
- Corrected all-three-argument invocation and actual native span names. Root review requested separate direct/durable model/tool counts and durable workflow trace attribution; implemented that stronger acceptance without new production helpers. Factory owner then declared prompt-v2/factory bytes stable. Prompt-v2 offline selection: `PYTHONPATH="$PWD/src:$PWD" .venv/bin/python -m pytest tests/temporal/test_issue_analysis_composition.py tests/temporal/test_issue_analysis_native.py -q` passed five / 0.35s with six explicit skips; no service qualification was inferred.
- Native002: fresh source/dependency/runtime freeze, actual verified loopback service and `pytest ... -q -x --temporal-address 127.0.0.1:17333 --temporal-evidence-dir .../native002/histories --junitxml .../native002/junit.xml` passed **11 / 2.45s**, no failures/skips, command exit zero. Six actual terminal histories (three Completed, three Failed) replayed. Positive outputs/counts match directly/durably; per-mode local model/tool spans and native workflow/activity trace attribution pass, and positive replay adds no spans. Three negative controls preserve the intended native exception and actual ERROR context. Every scheduled activity has attempt cap one.
- Native002 manifest SHA256 `9ec9ef89fda59a50f9e1ecd8e52d71c78af241fe641389222e033c459d5f8fef` contains 17 inputs; each frozen/current hash matched after the run. Original PID 1549989/start 51679839 exited zero, `/proc` absent, all ports 17333/17334/17336 closed. Service lifetime 4.535s; exact binary SHA checked before launch. No service remains running.
- [Qualification report](../../qualification/issue-analysis-temporal-fixture.md) retains selected scope, usage/spans, failures, freeze and cleanup. [Runbook](../../runbooks/issue-analysis-temporal-fixture.md) gives native commands and identity cleanup. Raw artifacts remain private. Root raw-evidence/source review passed all 17 hashes, 11-case JUnit, six histories, three comparisons and original process absence. Development-record guards passed four / 0.03s after final docs; root integrated `make test-config` passed 239 / 5.59s with one existing native loop warning, and final direct deterministic prompt-v3 Evals rerun exited zero. Root owns shared handoff/publication. Subsequent actual provider live003 selected zero-based source lines because tool metadata did not specify indexing. Root authorized explicit one-based inclusive schema/docs and prompt-v3 inventory metadata under unchanged authority/retries. Native002 remains the historical prompt-v2 result. Factory owner declared final prompt-v3 bytes stable; own offline selection passed five / 0.37s with six explicit native skips, then fresh Native003 passed **11 / 2.56s**, no failures/skips. The same six actual histories/replays/per-mode spans passed. Manifest SHA256 `b2300edcfbbc27a34cdeee647f69c448f052f0c2fa781201128b7fa3ebe794b1` contains 17 matching frozen/current inputs, including factory SHA256 `e8b665253e2c47418dba34cb9e23b4476803f3a95b3703b9ed9f31dc17321f7b`. Original PID 1582230/start 51708332 exited zero, absent, all assigned endpoints closed; lifetime 4.635s. No more live run is required without a concrete change/failure finding.

## Decisions and next action

Use one existing factory with narrow optional `TemporalDurability[FixtureDependencies]` injection, fixed Instrumentation/tools/validators. Fixture registry/oracles stay host/test-owned. Domain contracts import no vendor objects; native workflow payload contains typed domain output and primitive usage only. Activity retries are explicitly one in this slice and correction retries zero, so fixture activity retries cannot amplify unknown requests. Native plugin/converter/activity registration and replay replace custom wrappers.

Implementation and scoped final prompt-v3 native checks are complete. Root raw review passed; owned source/report/runbook/plan are stable. Root owns the integrated documentation handoff/publication. Real reasoning/providers, OpenShell tool execution, production Temporal, crash/mid-activity recovery and cross-version replay remain unqualified in this lane. Native fixture token estimates and local replay-safe traces are qualified only for the saved pinned runs; queue/RPC/internal retry/metric delivery and complete negative-run usage remain unknown. Do not broaden this result into a full Milestone 3 or security-fix conclusion.
