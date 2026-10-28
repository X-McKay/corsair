# Intake evaluator

Canonical executable scoring is in [`corsair.evaluation.intake`](../../src/corsair/evaluation/intake.py). The [candidate dataset](../datasets/intake-capabilities.json) has eight initially authored cases, including equivalent issue variants with different frozen available-image inventories. It is not a human-reviewed held-out baseline.

Inputs and evaluator-only oracles have declared hashes. Source digests bind the admitted repository independently. Scoring compares fixed categories, required/permitted sets, associated source locations and the acceptable subset of the supplied image inventory. An absent image cannot be recommended. Compatible available-image cases exercise supported classification; unsupported labels do not suppress a false-supported result.

The historical recipe-bound cohort at `evals/datasets/intake.json` retains its original hashes and labels. Its service case deliberately imports unavailable Flask. The single fixture-specific `unresolved-import` typing override admits that expected missing dependency diagnostic; the rest of the fixture and all implementation code remain type checked. The target dependency is never installed or imported on the host. Fixture bytes and declared hashes are unchanged.

Reports retain invalid output, abstention and operational failures. Schema validity is not semantic correctness; image resolution is not tooling conformance; deterministic scores do not measure complete free-text fidelity. See [intake operation and evaluation](../../docs/agents/intake.md).


## Scanner and JSON structure cohort

[`intake-json.json`](../datasets/intake-json.json) is a separate 32-case authored cohort. Revision 2 covers scanner-shaped SARIF, Semgrep, Bandit, GitLab SAST, Checkov and Trivy reports alongside GitHub/Jira envelopes, arrays, renamed fields, strings, Unicode, duplicate/conflicting reports, empty results and hostile metadata. Function, configuration and dependency reports use synthetic source and identifiers. These are representative excerpts informed by primary documentation, not genuine scanner exports or version-complete scanner schema qualification. The source families are related; format variants do not constitute independent held-out families.

Optional evaluator-only `issue_titles` checks exact supplied titles and `description_fragments` checks case-insensitive literal preservation of selected details. `normalization_correct` contributes to exact matching only where these expectations are supplied. These lexical checks cannot establish complete semantic fidelity or prove that no unrelated detail was added. Native canonical issue copying remains separately enforced by production validation.

`paths` remains the required path set; optional `permitted_paths` can allow retaining or withholding an explicitly reported shared location in ambiguous multi-issue controls. Omission preserves the original exact-path scorer. Associated path/symbol expectations remain available for unambiguous findings. Oracles, format/family metadata and scorer expectations never enter model or workflow inputs.

All 64 revision-1 attempts failed normalized source admission before a model call; that setup failure and exact bytes remain privately retained. Revision 2 uses per-case repository paths and has independent hashes. See [PLAN-0135](../../docs/plans/active/PLAN-0135-intake-json-robustness.md) for actual checks and results; neither corpus is promoted.
