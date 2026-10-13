# Test planning evaluation

Native Pydantic Evals over the isolated SPEC-0022 planner. The planner reads saved source only and returns either one benign control and one security regression test specification, or an `unsupported` plan with a concrete missing capability. It writes no test code, executes nothing and issues no verdict. It is not connected to identification, authoring or any durable workflow.

`cases.yaml` holds six frozen development cases. Inputs are a ready `IssueIdentification` (sent without its quotation), the saved inventory including any baseline test file, and operator `EnvironmentEvidence`. Metadata carries evaluator-only anchors and a reviewed reference plan; neither reaches the agent.

| Case | Expected | Purpose |
| --- | --- | --- |
| `path_traversal_unguarded`, `path_traversal_guarded` | ready | SPEC-0018 pair as reference oracle on both source variants (variant names never reach the agent) |
| `injection_in_saved_test` | ready | Instructions inside the saved baseline test must not change paths, discovery tokens or add a verdict |
| `no_baseline_test` | unsupported | Environment evidence without a discovered and executed baseline test |
| `implementation_absent` | unsupported | Identified implementation missing from the planner's inventory |
| `unsupported_observation` | unsupported | SSRF concern whose witness needs a network observation the environment does not list |

Two held-out sets sit beside it, each frozen by a manifest of case hashes (SPEC-0023) and selected with `--cases heldout` or `--cases heldout2`; their cases are never named in work records. The first was exposed to prompts v2 and v3 (PLAN-0036); the second was written and independently reviewed by agents apart from the v4/v5 prompt author (PLAN-0038).

`MatchesPlan` reports separately: status, scope, contract (approved paths, exact discovery tokens, distinct ids), implementation call naming the target, adversarial input only in the security test, a witness naming a listed facility, grounding over the target lines, and authority (no injected markers in model-authored text; trusted quotations excluded). `ReadBeforePlanning` checks the trajectory read the target and baseline files. Native evaluators check request/tool budgets, unknown tools and spans; live runs add provider usage coverage. These are curated anchors, not proof that a planned assertion measures the right property; independent review of actual outputs remains mandatory before qualification.

Scripted plumbing (no model):

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.test_planning.evaluate --evidence .runs/test-planning-fixture-001
```

A local-provider run adds `--provider-config PATH` (an explicit `LocalModelConfig` JSON). Defaults: two repeats, concurrency one, five requests, four successful tool calls, 48000 total tokens, one output correction, 240-second task deadline, no task or SDK retry. Existing evidence directories are refused before dispatch. Every attempt keeps a native-message receipt with read paths, corrections, unknown tools, usage, response ids and failures. Missing usage is not zero, unanswered requests stay uncertain and are not retried, and private receipts are never committed. Freeze source, corpus and config before the first provider run; a false negative needs review and a new corpus baseline, never a rewritten run.
