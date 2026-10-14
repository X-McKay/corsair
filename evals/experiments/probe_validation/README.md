# Probe validation experiments

This directory contains evaluator-only prototypes. It adds no production agent, policy, recorder or mutation engine.

`rubric-v1.json` and its digest freeze the interpretation rules and the exact seven development plus three transfer input identities before prototype model outputs. Expected labels never enter author or reviewer prompts. `scoring.classify` counts a declared review decision against the independent fixture label; rationale adequacy and successful source reads remain separate checks. An unsupported answer is an abstention, not a correct diagnostic rejection. Contract failures, provider/budget failures and evaluator defects are separate. Planner status and curated anchors are structural checks only, never semantic proof. Compare model, prompt, schema, input, rubric and budget identities; retain earlier measurements unchanged.

The native calibration reuses the existing reviewed SQL construction fixture and recording database dependency. The same two-test patch executes unchanged against each safe and unsafe source in a fresh native pytest process. The existing meaningful pair keeps control healthy and fails only the unsafe security case. Two deliberate negative controls copy the implementation into the test or replace the security assertion with a constant; both pass on both sources, demonstrating their missing sensitivity. There is no database and no new low-level recorder.

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.experiments.probe_validation.calibration --evidence .runs/probe-calibration-001
```

Only fixed repository-owned fixture bytes execute. This tool accepts no model-authored patch. Native reports and source/patch hashes are retained under the new evidence directory. Calibration results and variant identities stay outside author/reviewer inputs.

This demonstrates assertion sensitivity at one query-construction seam, not general test validity, production binding of the control, database behavior, all-CWE coverage or model-review accuracy. A distinguishing pair can still have an invalid control or copied logic. Source review, both executed probe outcomes and the claim's scope remain separate requirements. The prototypes are experiments, not a release gate or an adopted production design.

For a separate shared-rubric comparison, `structured_decision` projects current structured review facts onto the compact experiment's decisions. Production binding plus the correct role-specific inputs/assertions and retained dependency scope supports approval. An explicit copied/replaced target, different or wrong-role input, unrelated/vacuous or wrong-role assertion, or replacement of the entry point/security logic is an invalid decision. Explicit defects take precedence over other unresolved checks. Unknown facts yield unsupported; `preconditions=missing` also yields unsupported because that schema does not distinguish an absent fixture from missing evidence establishing it. A missing review stays missing. Historical blanket booleans are not accepted by this projection. Record projected comparison results as a new rubric-tagged artifact alongside, never over, the original structured evaluator scores. The projection compares declared facts; it does not establish the correctness of the agent's explanations.
