---
id: ISSUE-0008
kind: issue
title: Product entry refuses investigations without a candidate fix
status: open
updated: 2026-10-13
related: [PLAN-0087, PLAN-0079, SPEC-0040]
---

# Product entry refuses investigations without a candidate fix

## Observed and expected behavior

`IssueRequest.fixed_revision` is optional, but `investigation.build` refuses its absence before source acquisition. Direct composition also unconditionally executes baseline and candidate and constructs both gate runs. The campaign therefore cannot yet execute an independent negative baseline or an unpaired topic through the full product entry. A paired run whose revisions happen to behave alike is not an independent negative-baseline evaluation.

Expected: a request without a candidate should investigate the baseline, retain the same two finding-specific tests and evidence gates, and make no fix claim. An adequately supported result may have fix `not_applicable`; absent or insufficient evidence must remain inconclusive/unknown rather than become a negative finding. A request with a candidate must retain current behavior.

## Reproduction and evidence

Historical local reproduction source `5b20133708910828ae419ecc78897b67301413ee` (not a main qualification). Publication-base main `e84a2bb` still contains the same explicit refusal in `investigation/build.py`; verify pending work before implementing it again. Load a development issue request, remove `fixed_revision`, validate it as `IssueRequest`, and call `build(request, work, {})`. Native result: `the request names no fixed revision (a vulnerable-only run is not built yet)`. Reproduced before image lookup, Docker or inference. The private receipt is not required to reproduce the schema/build contradiction from current source. No raw local evidence is published here.

The Perl readiness lane independently observed the same refusal for its neutral baseline-only request; its paired request instead stopped at missing TAP product harness. These are separate shared-product and language-specific blockers.

## Attempts and diagnosis

The existing request and disposition types already express absence of a candidate, but the entry/composition glue does not. `src/corsair/investigation/build.py` requires both commits; `src/corsair/composition/direct.py` executes both names and unconditionally creates candidate gate evidence; summary formatting also assumes a candidate revision. Review durable composition and all result consumers before changing this shared boundary. No application or policy change was attempted in this readiness wave.

## Resolution criteria and next action

Implement one bounded optional-candidate slice using the existing contracts and ports. Check positive baseline-only, scoped negative baseline-only, failed control, missing witness, refusal and unchanged paired behavior. Prove only baseline source/setup/execution is requested when no candidate exists, no candidate or fix evidence is fabricated, and `not_applicable` cannot hide a failed finding investigation. Preserve honest mode support if durable parity is deferred. Compare affected isolated assessment/composition regressions, then one positive and one negative Docker product-entry attempt. Keep label/oracle metadata evaluator-owned and all failed planned slots in the campaign denominator. This blocks standalone-negative execution, not independent runtime readiness or positive-pair diagnosis.
