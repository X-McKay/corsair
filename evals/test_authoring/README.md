# Test authoring evaluation

Isolated [SPEC-0028](../../docs/development/specs/SPEC-0028-test-authoring-agent.md) stage. The agent receives a ready plan, the saved inventory and environment evidence; it writes tests only through `write_test_file` into approved paths and checks them with `run_tests`, whose security outcome is withheld by default.

`cases.yaml` is a native Pydantic Evals dataset with nine development cases built from the planner's reviewed reference plans: the SPEC-0018 realization, guarded source with the same patch, a collection error then fix, instruction injection in the saved baseline test, persistent collection errors up to the run budget, a failing control, and (SPEC-0043) a self-observing write refused then replaced, and refused twice, which ends blocked at admission, and the author reading its own written test after a collection error and then a path that is not in the source, answered typed (`unread_sources` counts those answers). Each input wraps the agent input with a `fixture_id` that selects the scripted runner and author; it never reaches the prompt. Metadata holds the scripted author's steps, the scripted runner's observations and the expected status, run count and assertion lines.

Evaluators report status, development run count, contract, security assertion lines, static semantics (Python AST: calls the planned target, no mocks, skips, swallowing excepts or constant asserts), read before write, write before run and withheld security separately, plus native budget and span checks. No LLM judge is used.

Each development run is answered by the case's `runner_runs` entry (the last repeating once spent): an injected observation that puts the author in a condition, or `static`, the host runner in `static_runner.py` ([SPEC-0044](../../docs/development/specs/SPEC-0044-isolated-agent-evaluation.md)). It parses the patch and reports what collection could refuse (syntax errors, imports nothing could satisfy, node ids other than the planned pair) and, when exactly the pair is found, simulates execution as control passed and security failed, with run command `static-host-runner not-executed`. Nothing is executed on the host, so whether the tests run and discriminate the revisions stays unknown until a sandbox replay. `admission.py` adds facts scored in both modes: no process or network use, the plan's quoted adversarial input only in the security test, and plain asserts for a planned `AssertionError`.

```sh
make eval AGENT=authoring                                              # scripted author
make eval AGENT=authoring PROVIDER_CONFIG=<LocalModelConfig.json>      # live author, still host only
PYTHONPATH=src:. .venv/bin/python -m evals.test_authoring.evaluate --evidence .runs/test-authoring-<date>/fixture-001
```

Live mode drops the two checks that pin the scripted author's own run count and assertion lines, adds provider usage coverage, and records response ids and uncertain delivery in each receipt. Existing evidence directories are refused; every attempt keeps a receipt with `runner_sources` saying which runs were injected and which simulated.
