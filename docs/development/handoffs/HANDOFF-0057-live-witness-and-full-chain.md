---
id: HANDOFF-0057
kind: handoff
title: Live witness gate, credential placeholder delivery and fully live chain rerun
status: recorded
updated: 2026-10-13
related: [PLAN-0039, PLAN-0034, PLAN-0033, PLAN-0035, SPEC-0025, SPEC-0033, HANDOFF-0052]
---

# Live witness gate, credential placeholder delivery and fully live chain rerun

## Verified state

Branch `claude/live-witness-full-chain-6z24yc` from main `334aa03`. Delivered: the credential placeholder gate binds its gate-owned provider profile to one unresolvable endpoint, waits for provider readiness and asserts the upstream placeholder form (`tests/qualification/test_credential_placeholder.py`); PLAN-0039 with the live results. No product code, prompt, gate or contract change.

Live on RIG0 (details and evidence paths in PLAN-0039): the SPEC-0033 witness gate passed (reproduced / verified with admitted witnesses on the reviewed pair); the credential placeholder is now observed in the exec environment as `openshell:resolve:env:v{revision}_CORSAIR_QUAL_FAKE_TOKEN` with the raw value absent from every readable scope; the fully live chain with the PLAN-0035 stage profiles reached the gate 1/3, kept the planned security-test direction, and had both witnesses admitted live, but the gate could not use the baseline (`pytest.raises` failure type versus the planned `AssertionError`).

Not qualified: egress substitution and private repository fetch (SPEC-0025), the live agents, any benchmark case. The witness is tamper-evident, not tamper-proof.

## Validation and blockers

`make test-config` 853 passed on RIG0 at `334aa03`. Live: `make qualify-witness` 1 passed; `make qualify-fixture-e2e` 3 runs without profiles (planning timed out 3/3; the profiles were omitted by mistake) and 3 runs with profiles (1/3 to the gate); `make qualify-credential-placeholder` 1 passed at `3efa446`. Every gate confirmed cleanup. Evidence stays under `.runs/` in `/home/al/git/corsair-live-e2e` on RIG0 (not committed).

Blocking the fully live chain: (1) agents reading the test file they are meant to create end the stage (`TOOL_RETRIES = 0`); (2) planned exception type versus authored assertion style. Blocking benchmark cases: SPEC-0025 egress substitution and in-sandbox fetch, the storage quota route, SPEC-0026 dependency fetch, toolchain images beyond Python and Java.

## Decisions and next steps

The RIG0 worktree is on local branch `live-witness-20261013` (= `334aa03`) with `live-cred-20261013` at `3efa446`; nothing committed there. The OpenShell gateway is uninstalled (last gate's teardown); the kind cluster is up and free. RIG0 layout (user, 2026-10-13): no new sibling worktrees under `/home/al/git`; new worktrees go under `/home/al/git/corsair/.worktrees/<branch>` (git-ignored) and run evidence under `/home/al/git/corsair/.runs`. Once this PR merges, move `/home/al/git/corsair-live-e2e/.runs` content into `/home/al/git/corsair/.runs` and remove that worktree with `git worktree remove`; its `.state/` (kind kubeconfig and owner records) must be restaged into the new location first, since the qualification fixtures read it from the running worktree. Next: the user decides item (2); planner and source-tool owners take item (1); then rerun the profiled live chain.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0039, PLAN-0035, SPEC-0031 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. After the planned-exception decision and the planner/source-tool fixes are on main, reinstall the gateway on RIG0 (make openshell-install with the recorded admission evidence) and run make qualify-fixture-e2e with CORSAIR_E2E_RUNS=3 and CORSAIR_STAGE_PROFILES=evals/fixture_e2e/stage-profiles.json once, recording per-run stage outcomes, security-test direction, witness admission and gate verdicts. Do not claim SPEC-0025 private fetch until egress substitution is observed. Run make test-config, preserve evidence under .runs/, update PLAN-0039/CURRENT.md and write a new handoff.
```
