# Analyst usefulness pilot plan

The pilot measures whether reproducible validation reports help InfoSec analysts reach accurate, well-supported dispositions with less review effort. It follows technical qualification and is not a prerequisite for the first implementation milestones.

Status: proposed pilot. Recruiting reviewers, contacting teams, accessing private cases, and changing real issues are not part of this document's execution.

## Questions

- Can an analyst understand the security hypothesis, validation scope, and limitations without reading the entire agent transcript?
- Can another analyst reproduce the observations from the supplied artifacts and commands?
- Does the report improve disposition accuracy or reduce time to a supported decision?
- Does it explain blocked, unsupported, and inconclusive cases well enough to identify the next responsible team?
- Does the cost per useful validation justify broader deployment?

## Case selection

Use a small reviewed cohort spanning the qualified Python and Java stacks, vulnerable/fixed pairs, genuine scoped refutations, incomplete reports, dependency/policy failures, and ambiguous cases that must remain inconclusive. Include real repository complexity and keep gold labels outside agent inputs.

Choose a pilot size based on reviewer availability and desired measurement precision. Report counts and uncertainty; a small exploratory cohort supports product decisions, not broad claims of a measured false-positive rate across all codebases.

Start with authorized fixtures and sanitized reports. Any private source, issue discussion, model endpoint, artifact retention, or telemetry destination follows the organization's existing access rules.

## Review procedure

1. Freeze case set, system version, model settings, report format, and grading rubric.
2. Give analysts the normal issue/source material for a baseline review, or the same material plus the generated report for an assisted review.
3. Randomize assignment or use counterbalanced matched cohorts. Avoid having an analyst review the same finding twice without accounting for learning effects.
4. Record active review time separately from system runtime, queue wait, and reproduction time.
5. Ask for a disposition, confidence, cited evidence, scope limitations, and next action.
6. Have an independent qualified reviewer adjudicate correctness against the available evidence. A majority vote alone is not ground truth.
7. Capture reproduction attempts in fresh environments, including failed attempts and environmental prerequisites.

No automatic issue closure occurs during the pilot. Analyst decisions and suggestions are pilot observations, not write instructions to external systems.

## Measures

| Measure | Definition |
| --- | --- |
| Supported disposition accuracy | Adjudicated correct dispositions with sufficient evidence divided by reviewed cases |
| Unsupported conclusive dispositions | Incorrectly declaring reproduction, refutation, or fix verification; report each class separately |
| Analyst agreement | Agreement on disposition and scope, with correctness reported independently |
| Review effort | Active analyst time to a supported decision; show distributions and denominators |
| Reproducibility | Successful fresh reproduction attempts divided by all attempted reproductions |
| Diagnostic usefulness | Correct identification of responsible component and actionable next step for operational failures |
| Report completeness | Required evidence, identities, commands, and limitations present and understandable |
| Cost per useful validation | Model/execution cost across the cohort divided by cases with adjudicated useful evidence |

Retain inconclusive and blocked cases in the overall cohort. Report whether they produced useful diagnostic evidence separately from security resolution. Do not count an inconclusive finding as a filtered false positive.

## Feedback rubric

Ask reviewers to score clarity of hypothesis, visibility of scope, adequacy of controls, trust in test validity, usefulness of reproduction instructions, handling of contradictory evidence, and clarity of next steps. Collect specific missing facts or confusing passages alongside scores.

Analyze by language, issue class, validation scope, and operational status when sample sizes permit. Report the case composition so averages do not hide a concentration of easy fixtures.

## Decision and output

Produce a pilot report containing cohort/configuration identities, baseline/assisted procedure, measures and coverage, adjudication disagreements, report examples, and a prioritized improvement list. Freeze practical success criteria with InfoSec before starting the pilot. Suggested criteria are improved review effort without worse disposition accuracy, no unsupported safe/fixed claims in mandatory cases, and reproducibility sufficient for analyst handoff.

If reports are accurate but difficult to use, improve the report format and evidence navigation. If they are clear but semantically wrong, address the relevant agent or test-validity gate before expansion. If environmental failures dominate, prioritize supported-toolchain and dependency coverage. Broader deployment depends on observed pilot results rather than a persuasive demonstration case.
