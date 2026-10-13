---
id: HANDOFF-0121
kind: handoff
title: Unit-test implementation PR
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093]
---

# Unit-test implementation PR

## Verified state

The user explicitly requested PR publication and durable guidance against drifting from native unit tests. Feature branch: `codex/unit-test-first-validation`. Implementation commit 3b909da is integrated with main 2a3dcb2, including candidate-free investigations and the extracted preparation port. Resolve the final publication commit from this branch; this record is committed with that integration.

The PR adds the implementation recorded in [HANDOFF-0123](HANDOFF-0123-unit-test-observation.md), plus explicit ongoing-development guidance in the development guide, PR checklist and handoff skill. AGENTS and development/review/scaffold/base-image skills guide all languages, frameworks and CWEs through the same property and validity contracts. An integration boundary needs a property-based reason; a missing low-level recorder alone is insufficient. No new language or CWE dispatch was introduced.

The merge preserves both the native unit review path and main's optional-fix behavior. A composition regression exercises one reported revision without a candidate: independent unit review supports the finding and fix remains not_applicable. Preparation types come from main's port rather than being duplicated in composition.

Earlier open-PR review notes HANDOFF-0118/0119 remain unrelated local work and are excluded from this PR. No runtime deployment or live provider call occurred.

## Validation and blockers

The full offline suite after integrating main passed: **2064 passed, 6 skipped, 12 inherited warnings in 56.42 s**. Command selection matches make test-config, using the isolated Python environment with four pytest workers, loopback enabled and TERM=xterm/NO_COLOR unset for terminal tests. Log: `/tmp/corsair-unit-pr-tests.log`. Prior implementation attempts/failures and frozen scripted comparisons remain recorded in HANDOFF-0123. Repository workflow/link checks and diff whitespace checks are also run after these publication records. Live model semantic accuracy, additional runtime/CWE coverage and native old-history replay remain unqualified.

## Decisions and next steps

Continue using the shared unit-test contract for ongoing changes. Review the new PR and run live semantic calibration separately under existing provider configuration. No merge is authorized by PR submission. Publication does not upgrade runtime qualification.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0078, PLAN-0093 and HANDOFF-0121. Inspect the feature branch and PR checks. Preserve the unit-test-first direction across languages/frameworks/CWEs; use native framework seams, independent validity review and explicit integration limits. Address concrete review/CI findings, retain evidence and update records. Do not introduce a mandatory recorder or infer live qualification from offline tests.
```
