---
id: SPEC-0044
kind: spec
title: Isolated per-agent evaluation on the host
status: draft
updated: 2026-10-13
related: [SPEC-0022, SPEC-0023, SPEC-0024, SPEC-0028, SPEC-0029, SPEC-0030, SPEC-0035, PLAN-0039, PLAN-0048]
---

# Isolated per-agent evaluation on the host

## Goal and scope

The user's direction (2026-10-13): every agent can be evaluated and improved in isolation, running the Python outside the kind cluster, OpenShell and containers, so a prompt, skill, budget or contract change is assessed and benchmarked quickly, and workstreams change agents without depending on or conflicting with each other. A follow-up asked for one command per agent that runs its suite and files the results so runs can be compared over time.

An isolated eval loop for an agent has five parts:

1. a frozen eval set of typed stage inputs with evaluator-only oracles (development, plus held-out sets where prompts are tuned against development);
2. one command that runs it, scripted (no model) or live against an explicit `LocalModelConfig`;
3. a recorded baseline: a promoted run whose versions, model, case-set digest and scores later runs are compared with;
4. metrics a change can move: per-assertion and per-case pass rates, failed tasks, and efficiency (requests, tool calls, tokens, development runs, corrections, latency);
5. no cluster dependency: everything the stage would call outside the process is a typed port answered by a fixture, a recorded observation or a deterministic host double.

This spec covers the command and results layout, and the authoring agent's host eval, which was the one agent with no live loop. The environment agent's eval is planned in PLAN-0048 and specified when built. Excluded: new agent prompts or skills, changes to agent factories, tools or contracts, an LLM judge, and any claim that a host eval qualifies an agent.

## Boundaries and design

**One command.** `make eval AGENT=<identification|planning|authoring|assessment|chain> [SET=…] [PROVIDER_CONFIG=…] [REPEAT=…] [NOTE=…]` runs `python -m evals.run`, which runs that agent's existing suite CLI in a subprocess with the repository `PYTHONPATH` and an evidence directory it chooses. Make is already the repository's entry point (`make test-config`, the qualify targets); a `justfile` would add a second runner for one recipe. Each suite keeps its own CLI, dataset, evaluators and native `report.json`; the wrapper adds no evaluation logic. Unknown agents are refused; `environment` is refused with a pointer to the plan.

**Results layout** (ignored `.runs/`, never committed):

```
.runs/evals/<agent>/
  index.jsonl                      one line per run: id, set, mode, exit code, commit, dirty, versions, clean/attempts, note
  baseline-<set>-<mode>.json       the promoted run for this set and mode
  <UTC stamp>-<set>-<mode>/
    command.json                   argv, git commit and dirty state, note, exit code, start and end
    evidence/                      the suite's configuration.json, report.json and per-attempt receipts
    summary.json                   identity (prompt, config, skill digest, model, dataset digest, mode, runner, budget),
                                   per-assertion and per-case pass counts, task failures, efficiency means
    comparison.md                  identity changes, then assertion, case and efficiency tables against the reference
```

The reference is the promoted baseline for the same set and mode, else the previous run with the same set and mode. A changed dataset digest is printed as not directly comparable. Baselines are promoted by a person (`make eval-baseline AGENT=… RUN=…`), never chosen automatically. A failed suite still gets a summary; a missing report is recorded as missing, not zero. Held-out runs keep held-out case names inside `.runs` and `evals/`; records under `docs/development/` cite only aggregates, as SPEC-0023 requires.

**Authoring host eval: write-only.** The user asked (2026-10-13) for authoring evals that write but do not execute code. The first authoring eval is exactly that: the live author writes its tests through the real tools, and they are judged as written, by static and admission checks and agreement with the plan, never by running them. Execution-based scoring is a later layer that runs only in the sandbox (PLAN-0048 step 6). The known live failure modes are covered as follows: tests that check nothing by `static_semantics` (an executed assertion, no constant asserts, no skips, mocks or swallowing excepts, calls the planned target); a broken control partly by static discovery (parse errors, imports nothing provides, wrong or extra ids) and by the planned input appearing only in the security test, while a control that fails at runtime stays unknown until the sandbox layer; author-written audit, trace or monitoring hooks by the `author_witness_hooks` score per attempt, a count rather than an assertion because the reviewed realization in today's cases still installs one and the refusal rule belongs to the authoring stage.

**Authoring host eval.** Repository policy keeps model-written tests out of the host: they run only in the qualified sandbox (SPEC-0028, SPEC-0032). The host eval therefore never executes them. The stage's `TestRunner` port is answered per development run by the case's `runner_runs` entry, the last entry repeating once they are spent:

- an injected observation (collection error, or discovery with a given control/security outcome), so a case can put the author in a condition (failing control, persistent collection error) whatever it wrote; or
- `static`: `evals/test_authoring/static_runner.py` parses each patch file and reports what collection could refuse without running anything: a syntax error, an absolute import that is neither stdlib, the test framework nor saved source, or node ids other than exactly the two planned ones (pytest's default rules for explicitly named files). When exactly the planned pair is found, execution is simulated: control passed, security failed (withheld from the author by default), and the run command is `static-host-runner not-executed`, so the authored patch and every receipt say it was not executed. Non-Python files are refused rather than guessed.

The agent factory, tools, finalisation and prompt are the real ones (`create_test_authoring_agent`), so a prompt or budget change from another workstream runs unchanged. Live mode adds `--provider-config` and `--repeat`, receipts with provider usage, response ids and uncertain-delivery flags, and `ProviderUsageCoverage`.

Scored dimensions (each reported separately): status; contract (approved paths, planned ids, discovery command); static semantics (existing `static_checks`); admission facts from `evals/test_authoring/admission.py`: no process, raw network or foreign-function use, the plan's quoted adversarial input present in the security test and absent from the control, and, when the plan expects `AssertionError`, every claimed security line a plain `assert` (the authoring-v5 decision); trajectory (read before write, write before run, security outcome withheld); native request and tool budgets, spans and unknown tools. Scripted mode also pins the scripted author's run count and assertion lines; live mode drops those two because a live author may legitimately differ. The audit-hook rule belongs to the authoring stage's own admission check (the "author stays out of the witness" work, PLAN-0047 on its own branch) and is not duplicated in the eval.

What the host eval cannot see is stated, not inferred: whether the tests import and run, whether the control passes, and whether the security test fails on the vulnerable revision and passes on the fixed one. Those stay `unknown` until a patch is replayed in the sandbox (PLAN-0048 step 6), where the frozen authored bytes, not the model, are executed.

## Acceptance and validation

- Every scripted suite runs through `make eval` with no cluster and files `summary.json` and `comparison.md`; a second run compares with the first, and a promoted run becomes the reference.
- The authoring scripted suite still passes every assertion with static runs replacing the canned "discovered" observations.
- Static runner checks: discovers the reviewed pair; reports a syntax error, an unresolvable import, a renamed test and an extra test as collection errors; refuses a Java file.
- Admission facts accept the reviewed realization and flag a swapped adversarial input, a `pytest.raises`-only security line and process use.
- Live mode is exercised on RIG0 against llm.almckay.io and its result recorded as a baseline measurement, not qualification.

## Decisions and open questions

- Make, not just: one runner already exists.
- Static simulation over no feedback: without a reported run the authoring finaliser can never accept a patch, so a host eval would measure nothing. Simulating only execution, after a deterministic static discovery, keeps the author's real loop and leaves every execution claim unknown.
- Open: a third-party test dependency the environment installs is reported as unresolvable today; when environment evidence lists installed packages, the static runner should take them as available.
- Open: Java authoring needs a static discovery over JUnit sources before its host eval can run.
