---
id: SPEC-0043
kind: spec
title: Authored tests stay out of the witness; per-stage tool budgets derived from the task
status: draft
updated: 2026-10-13
related: [PLAN-0047, PLAN-0039, SPEC-0028, SPEC-0031, SPEC-0033, SPEC-0035, SPEC-0038]
---

# Authored tests stay out of the witness; per-stage tool budgets derived from the task

## Goal and scope

Two failure modes from the first fully live chain runs with the operator witness (PLAN-0039, `test-authoring-v5`, three runs on RIG0):

1. The authoring agent wrote its own `sys.addaudithook` checks beside the operator witness (SPEC-0033). In one run the security test then compared unresolved paths, passed on the baseline and failed on the candidate (direction inverted); in another a module-level hook made the control fail on every development run. The environment evidence even listed "audit events recorded by the test itself" as a facility, and skill step 6 told the author to observe the witness.
2. The flat 10 tool-call cap ended one authoring run (7 writes, 2 runs, 1 read) and one assessment run (11 requests over 9 evidence items), and PR #40 found it tight for whole-repository identification (two correct JSPWiki runs used 10 of 10). A spent cap raised `UsageLimitExceeded` and the stage produced nothing.

Out of scope: gate, witness, planner prompt and planner contract changes; Java authored-test admission (no Java author exists yet).

## Boundaries and design

**Authored-test admission (authoring stage).** `agents/test_authoring/admission.py` is a deterministic Python AST check run by `write_test_file` on every write. It refuses constructs that install or reach interpreter observation (`sys.addaudithook`, `sys.audit`, `sys.monitoring`, `sys.settrace`/`setprofile`/`_getframe`/`call_tracing`, `threading` trace/profile setters, by module alias, member import or string name), imports that replace or reach below observed facilities (`ctypes`, `_testcapi`, `tracemalloc`, `trace`, `bdb`, `pdb`, `unittest.mock`, `mock`, `pytest_mock`, `builtins`, `_io`), `__builtins__`/`__import__`, the `mocker` fixture, and `setattr`/`delattr`/`setitem`/`delitem`/`patch` calls on file, process, network or import facilities (`builtins`, `io`, `os`, `pathlib`, `shutil`, `subprocess`, `socket`, `importlib`, any module's `open`) and on `sys.modules`, plus direct assignments, augmented assignments and deletions of those (`io.open = f`, `del os.system`, `sys.modules["x"] = m`); imported aliases are resolved first (`import socket as net`, `from os import path as p`). Input changes stay allowed: `monkeypatch.setenv`, `os.environ` items, `sys.argv`, working directory. A refused write returns a typed `RefusedWrite` (findings by line, reason, refusals left) and leaves the file's previous content; nothing runs. The operator-owned `AuthoringBudget.admission_refusals` (default 1, `CompositionBudget.admission_refusals`, within the durable ceiling) is how many refusals the author may act on; the next one withdraws write and run, and `finalize_authoring` returns `BlockedAuthoring(layer="admission")`, a layer only trusted code assigns (`ResultLayer`). The SPEC-0018 reviewed bytes, which observe opens themselves because they predate the witness, are admitted by their exact digest only (`REVIEWED_SELF_OBSERVING`), since they are the scripted control, never model output. Prompt `test-authoring-v6`: step 6 now says the operator probe observes the witness and lists what test code must never do; step 5 asks for the absence of the effect as the test sees it through its own fixtures. The E2E-0 environment evidence no longer lists a test-installed audit facility. This is structure, not proof: dynamic construction the AST cannot see remains possible, so the witness stays tamper-evident, not tamper-proof.

**Per-stage tool budgets.** `StageBudget` keeps the operator's ceilings and adds a derivation (`slack_tool_calls`, `tokens_per_request`). `stage_limits(stage, inputs, budget)` derives the caps each run enforces from its own input:

- tool calls = read windows + work calls + slack, capped by the ceiling. Read windows are the 80-line windows needed to read every readable input once (saved source for identification, planning and authoring; frozen evidence items for assessment). Authoring work calls are `dev_runs × (2 × planned test paths + 1) + admission_refusals` (two writes of each planned path and the run, per development run).
- requests = tool calls + output retries + 2 (the output request and one spare); tokens = requests × `tokens_per_request`; each capped by its ceiling.

Defaults (ceilings tools/requests/tokens, slack, tokens per request): identification 16/20/128k, 2, 8000; planning 16/20/160k, 2, 10000; authoring 28/32/262144, 2, 12000; assessment 28/32/262144, 3, 10000. On the E2E-0 fixture that gives identification 4 tools, planning 4, authoring 14, assessment 12 (was 4, 8, 10, 10). Whole-repository identification (SPEC-0038, not in the chain yet) derives its live-eval cap from the repository limits: reads the run byte budget allows at full read size (131072/16384 = 8) + 4 listing/search calls + 2 = 14.

A native `PrepareTools` capability (`agents/budget.py`) withdraws every function tool once `ctx.usage.tool_calls` reaches `ctx.usage_limits.tool_calls_limit`, so a stage at its cap returns its typed output from what it has instead of dying on the next call; the four chain agents and repository identification carry it (CONFIG_VERSION bumps; the environment agent is not in the chain and is unchanged). If a stage still ends on a cap, `exhaustion` turns the failure into a typed `BudgetExhausted(stage, limit, cap, limits)`: `UsageLimitExceeded` names its limit, `TimeoutError` is `timeout_seconds`, and only an `UnexpectedModelBehavior` after the tools were withdrawn (a call to a withdrawn tool or spent output retries) is `tool_calls_limit`; any other failure after the cap keeps its own classification. Whether the cap was reached is recorded separately on every attempt (`tool_cap_reached`). Every `StageAttempt` (and durable `AttemptRecord`) records its derived `StageLimits` and any exhaustion; the run reason names the cap and its derivation; the fixture E2E receipts and chain eval outcomes carry both. Direct and durable modes derive the same limits from the same pure function. Budgets stay configuration, never prompt text.

Alternatives not taken: raising the flat cap (no relation to the task, still dies); a model-facing "budget" output status (a cap is an observed fact, not a model claim); a tool-call counter in dependencies (PydanticAI already exposes `usage_limits` on `RunContext`).

## Acceptance and validation

Implementation: unit tests for every refused construct and admitted plain test; reviewed-digest admission; refused write keeps content and allows one correction; second refusal ends blocked at admission and overrules a patch draft; tools withdrawn at the cap with a patch still returned; derived limits on the fixture; tool-cap and request-cap exhaustion typed in direct and durable modes; ceilings enforced on durable admission. Scripted evals: authoring dataset gains two cases (refused then fixed; refused twice), chain dataset direct and durable, assessment dataset with derived per-case caps.

Live (separate): the profiled three-run fully live chain on RIG0 with the operator witness, compared against PLAN-0039's v5 rerun: per run, whether any authored write was refused, stage outcomes, tool calls against the derived caps, security-test direction, witness admission and gate verdict. One run is not qualification.

## Decisions and open questions

- The admission check is Python only; a Java author needs its own check before it is admitted.
- Planner prompts still describe the witness as audit events in `observable_witness`; the planner typed-witness work (SPEC-0040) owns that wording.
- Slack and per-request token figures come from PLAN-0039's measured usage and are operator configuration; re-derive them when a stage's tools change.
