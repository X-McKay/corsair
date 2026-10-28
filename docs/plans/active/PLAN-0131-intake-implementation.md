# Intake implementation plan

Goal: implement the approved [intake design](PLAN-0130-intake-agent-design.md), restricted to currently available images.

Architecture: canonical Pydantic contracts, one native ADK episode, trusted Docker inspection and inventory, pure admission, and ordinary Temporal activities. Intake v2 removes recipe bindings. The separately reviewed expanded investigation migration is specified in [PLAN-0132](PLAN-0132-recipe-free-investigations.md). Execute inline using the executing-plans and test-driven-development skills.

## Constraints and review focus

Preserve the pre-existing dirty working tree; no commits or publication. Package resources load outside the checkout. No target code execution, image pull, repository build, registry lookup, or credentials in containers. Unavailable services and uncertain cleanup remain errors. Oracle data never enters agent/workflow inputs.

Review focus: invented images, unsupported capability claims, untrusted JSON overriding source, cleanup after cancellation, and operational errors mistaken for supported decisions.

## Tasks

### Task 1 Contracts and admission

- [ ] Write and run failing tests for bounded JSON, canonical normalization, inventory membership, unknown/unsupported/supported precedence.
- [ ] Add `contracts/intake.py`, `policies/intake.py`, exports and narrow settings. Interfaces: `IntakeRequest`, `IntakeProposal`, `IntakeResult`, `ImageInventory`; `classify_intake` returns categorical admission.
- [ ] Pass the affected unit tests and record results.

### Task 2 Trusted adapters and inspection

- [ ] Write failing tests for fixed-host GitHub fetch, configured-only inventory, immutable identity checks, bounded read-only inspection and verified cleanup.
- [ ] Implement `adapters/scm/github.py`, `adapters/sandboxing/images.py`, `inspection.py`, `inspection_reader.py`, and `deploy/intake/Dockerfile`. Reuse source snapshot admission.
- [ ] Pass unit/security tests; run real Docker conformance when available.

### Task 3 Native agent and durable composition

- [ ] Write failing native factory/runner and workflow/CLI tests.
- [ ] Add role-local `agents/intake/`, native ADK integration, `steps/intake.py`, `workflows/intake.py`, CLI/API/worker composition, with explicit input/source/inventory identity and budgets.
- [ ] Verify native ADK, Temporal and installed-resource consumers. Keep existing producer/auditor behavior.

### Task 4 Frozen scoring and delivery

- [ ] Write failing deterministic scoring tests and add installed `evaluation/intake.py` plus frozen candidate fixtures/dataset and evaluator description.
- [ ] Cover paired available/absent image inventories, unknown information and false-supported decisions with exact expected categories.
- [ ] Update docs, run `just check`, offline suite, affected native/full-chain gates, independent review, final frozen diagnostic and build/wheel resource validation.

## Execution record

Implementation authorized by the user on 2026-10-27. Working in place on `manus/just` because the approved design depends on the existing uncommitted implementation. New work will remain uncommitted. Native and live gates require actual prerequisites; unavailable gates will remain explicit.


### Results before expanded investigation migration

- Full native offline suite with pinned Nix tooling and `TERM=xterm-256color`: 278 passed, 75 deselected before the final intake-v2 changes. The default dumb terminal caused one existing color assertion; the configured terminal passed.
- Latest intake-v2 unit/security checks: 29 passed. Ruff and ty passed after recipe removal.
- Earlier real Docker/Temporal chain: 4 passed, 1 failed. Isolation, scripted native composition, replay and preparation heartbeat passed; the hosted-vLLM live model failed schema completion.
- Live endpoint: user-selected `llm.almckay.io`, available model Qwen3.6-35B-A3B-NVFP4. Hosted-vLLM native tool completion failed nested-object schema output; no repair was added. Native OpenAI-compatible output succeeded in a single-case diagnostic. Full recipe-free cohort and final native composition remain pending.
- Original frozen recipe-bound cohort and failed private diagnostics are preserved. Recipe-free capabilities use a new candidate cohort, not relabeled original oracles. Missing model cost remains unknown.
- Independent implementation review identified heartbeat/cancellation, source-location association and scoring issues; fixes and regressions are present. Final quality/build/resource gates remain pending after the expanded scope.


### Final intake-v2 native checks (2026-10-27)

- `nix develop --command just check`: passed Ruff lint/format, Just format, ty with warnings failing, and local documentation links.
- `nix develop --command env TERM=xterm-256color just -- test -q -W error`: 281 passed, 75 deselected, including installed-wheel resource loading outside the checkout.
- `CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 .venv/bin/python -m pytest -q -W error -m 'not live' tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py tests/workflow/test_intake.py`: 4 passed, 1 deselected.
- `nix develop --command just build`: sdist and wheel built. The builder reported uv 0.13.4 differs from its build-system requirement range; build still succeeded. Wheel inspection found 133 entries and no private state, caches or credential directories.
- A real-Just regression exposed duplicated/interpolated dataset arguments in the new `eval-intake` task. Replaced interpolation with literal positional forwarding; the full offline suite includes the regression.
- Live recipe-free synthetic-cohort evaluation is running under the user-selected native OpenAI-compatible route. Automatic approval initially denied potential source export; after inspecting all payloads as synthetic fixtures, the reviewed retry was approved. No real target repository is sent by this evaluation.


Intake-v2 implementation is present and included in the final v3 consumer checks. Final combined delivery suite recorded 317 offline passes and 11 real Docker/Temporal/replay passes (one live test deselected), with intake coverage included. The original unbounded live capabilities run ended without a report; a distinct bounded repeat awaits exact synthetic-payload egress approval after automatic review denial. This is not a live-model intake accuracy qualification.


The user approved the live continuation on 2026-10-27. The bounded eight-case capabilities run completed with 1/8 exact passes, 2/8 correct classifications, two invalid outputs and zero false-supported decisions. No fixture or oracle changed. Intake model quality remains unqualified; [ISSUE-0015](ISSUE-0015-intake-v3-live-quality.md) records the gap and [PLAN-0133](PLAN-0133-recipe-free-implementation.md) retains exact commands and distinct native/live boundaries.
