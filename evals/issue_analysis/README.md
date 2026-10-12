# Issue-analysis evaluation data

`cases.yaml` is the native Pydantic Evals dataset. `rubric.py` regenerates it from the existing fixtures and oracles; those original files remain in use by the current evaluation entry points. Rubrics and labels are evaluator-only and must never enter agent inputs.

`attempt_labels.yaml` records independent findings for individual retained outputs. `reported_failure_history` is coverage history, never per-output truth. An empty label tuple means independently reviewed and clean; do not create one merely because a finite assertion passed or a review did not mention an attempt.

## Retained output identity

For the labels identified on 2026-10-12, `output_sha256` hashes the retained native report case's `output` object serialized as UTF-8 JSON with Python `json.dumps(output, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"`. Do not normalize wording, reorder arrays, or hash the receipt/messages instead. The matching derived output files stay private. `attempt` is the actual receipt filename inside `run`; `skill_sha256` hashes exact frozen SKILL.md bytes and must agree with report metadata. Neither a current file nor a model alias can substitute for historical identity.

Local reinspection verified all 55 source-v12 frozen copies, all eight live010 completed receipts and their input digests, and the skill hash against report metadata. The private `.runs/issue-0007-reassessment-20261012/provenance.json` binds report, review, receipt, output, input and experiment metadata. Raw reports, inputs, source excerpts and messages remain private.

The legacy promptv4 entry now has an exact output hash and receipt name, but its run predates SKILL.md. It remains excluded: no skill identity may be invented or borrowed from a later run. Three live010 defect entries have both identities: omitted process read permission, an irrelevant citation, and an unnecessary caller exception-handling precondition. These are reviewed negative examples, not a balanced or exhaustive calibration set. Other attempts have no labels here; absence is unknown, not clean. Historical provider/contract failures remain in their original reports and have not yet been fully coded.

## Calibration limits

`calibration_ready` establishes the required output/skill identity fields only. It does not establish adequate class coverage, independent confirmation, full source provenance verification, or judge qualification. The three negative examples must not be used alone to select and confirm a judge. PLAN-0023 still requires individually reviewed positive examples, failure attribution, frozen thresholds/minimum denominators and disjoint exploratory/confirmation sets before candidate scoring.

Live010 used augmented inputs containing a saved dependency reference. The public `cases.yaml` currently contains the older inputs without that reference. A future calibration loader must pair each output with its exact retained input and receipt digest, not retrieve source by case name from the current dataset. Scoring the old output against different evidence would invalidate the comparison. These historical cases are exposed regression material, not fresh agent holdouts.
