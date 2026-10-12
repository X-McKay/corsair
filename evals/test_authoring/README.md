# Test authoring evaluation

Isolated [SPEC-0028](../../docs/development/specs/SPEC-0028-test-authoring-agent.md) stage. The agent receives a ready plan, the saved inventory and environment evidence; it writes tests only through `write_test_file` into approved paths and checks them with `run_tests`, whose security outcome is withheld by default.

`cases.yaml` is a native Pydantic Evals dataset with six development cases built from the planner's reviewed reference plans: the SPEC-0018 realization, guarded source with the same patch, a collection error then fix, instruction injection in the saved baseline test, persistent collection errors up to the run budget, and a failing control. Each input wraps the agent input with a `fixture_id` that selects the scripted runner and author; it never reaches the prompt. Metadata holds the scripted author's steps, the scripted runner's observations and the expected status, run count and assertion lines.

Evaluators report status, development run count, contract, security assertion lines, static semantics (Python AST: calls the planned target, no mocks, skips, swallowing excepts or constant asserts), read before write, write before run and withheld security separately, plus native budget and span checks. No LLM judge is used.

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.test_authoring.evaluate --evidence .runs/test-authoring-<date>/fixture-001
```

This is scripted plumbing only: the runner replays fixed observations and executes nothing. There is deliberately no provider option, because a live author's tests may run only in a qualified sandbox through the native pytest runner and an OpenShell workspace adapter, which does not exist yet. Existing evidence directories are refused; every attempt keeps a receipt.
