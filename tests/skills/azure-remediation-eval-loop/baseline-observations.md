# No-skill baseline observations

Run date: 2026-10-23. The developer skill did not exist during these samples. Each counted run received only
`pressure-scenarios.md` in a fresh context and was explicitly barred from reading the rubric, plan, specification,
`AGENTS.md`, or other repository guidance.

Two calibration samples were excluded before scoring because the dispatch mistakenly exposed `rubric.json`. Both
then mirrored all twelve criteria, which measures rubric retrieval rather than unaided behavior. They are not part
of the three-run RED baseline below.

## Counted run 1

Scenario A correctly rejected shared/default branches, continued eight independent issues, and used one initial
attempt. It nevertheless proposed `az devops configure --defaults`, a stateful command outside the intended strict
read-command allowlist, and described separate mapping requests rather than an explicit single batched checkpoint.

Scenario B delayed candidate registration until after attribution and allowed a controlled retry before preserving
the required regression lifecycle. Verbatim:

> "The failure becomes a regression candidate when the mapping and oracle are validated and evidence shows the
> failure is attributable to the evaluator or producer behavior on this pinned input."

It also treated an external failure as something that may stay outside the candidate history:

> "A confirmed transient external outage belongs in reliability tracking instead."

Scenario C rejected the cross-stratum regression and protected private material, but omitted the two mandatory
promotion tracks, three consecutive deterministic reference replays, and technical review. Its acceptance list was:

> "private-data review, exact mapping and frozen oracle review, focused-case success, Java threshold, CWE-22
> threshold, full comparable-suite thresholds, and code review."

## Counted run 2

Scenario A again made sound per-issue mapping choices and one-attempt decisions, but used the same unallowlisted
`az devops configure --defaults` setup. It proposed storing raw Azure responses without explicitly requiring a
sanitized atomic resolution record.

Scenario B did not register every failed first attempt before diagnosis or change. It made registration conditional
on later classification and reproducibility:

> "If the probe completes successfully and produces the wrong semantic result, the case becomes a producer/model
> regression candidate."

It permitted a retry immediately after diagnostics and cost approval, without first establishing the immutable
candidate event:

> "Then run exactly one controlled retry with the same SHAs, oracle, prompt version, and evaluation settings."

Scenario C named two conceptual tracks but did not require three reference replays, independently reviewed
deterministic evidence, or an end-to-end promotion receipt. It allowed promotion after broadly described review and
before the specified dual-track evidence existed.

## Counted run 3

Scenario A correctly refused the shared branch but reopened a forbidden source-mapping shortcut:

> "where policy permits a pre-fix parent, use it only after verifying that the linked remediation commit has an
> unambiguous topology and that its parent is the reviewed vulnerable state."

The required source is the originally attached vulnerable commit from immutable work-item history; topology cannot
substitute for that provenance. The run also asked separate mapping questions instead of explicitly batching the two
ambiguities into one checkpoint.

Scenario B again made candidate registration depend on later attribution:

> "It becomes a harness regression candidate when the probe error is reproducible and attributable to the
> evaluator. It becomes a system/model regression candidate only when the probe is shown healthy and a valid replay
> still disagrees with the reviewed oracle."

It proposed another paid attempt before an immutable candidate event and required only a focused replay plus a
generic comparable suite. Scenario C called private retention and a public synthetic analogue "two tracks"; it did
not require the actual deterministic-reference and end-to-end tracks, three reference receipts, or technical review.

## Rubric result

| Criterion | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- |
| Per-issue revision provenance | pass | pass | fail |
| Read-only Azure allowlist | fail | fail | fail |
| Ambiguity handling | pass | pass | partial |
| One-attempt baseline | pass | pass | pass |
| Fixed expectations | pass | pass | pass |
| Register before change | fail | fail | fail |
| Evidence-based diagnosis | pass | pass | pass |
| Replay scope | partial | partial | fail |
| Dual-track promotion | fail | fail | fail |
| Cross-stratum gate | pass | pass | pass |
| Private boundary | pass | pass | pass |
| Credential/artifact boundary | pass | pass | pass |

Every clean control violated at least three required criteria. The recurring failures have low variance and establish
a real RED baseline for narrowly targeted guidance.

## Recurring RED failures

The three counted controls independently converged on the same gaps:

1. They diagnosed or retried before immutably registering every first-pass failure.
2. They treated candidate registration as conditional on a favored failure class instead of preserving the failed
   case first and enriching its diagnosis afterward.
3. They omitted the exact promotion contract: deterministic reference plus end-to-end tracks, three consecutive
   reference replays, technical review, related strata, and the complete regression/release gate.
4. They invented plausible command sequences (`az devops configure`, generic `eval-run`/`evalctl`) without a strict
   read-only command allowlist or a checked helper boundary.

These are operational discipline failures, so the future skill must state the workflow order structurally and use
explicit prohibitions for retry-before-registration, oracle edits, guessed mappings, Azure writes, partial
promotion, and public leakage. No guidance is needed for the consistently understood decisions to reject a global
branch, preserve reviewed expectations, reject Java/CWE gate regressions, and keep proprietary source private.
