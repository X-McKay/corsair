---
id: PLAN-0020
kind: plan
title: Native two-test fixture semantics
status: complete
updated: 2026-10-12
related: [SPEC-0018, PLAN-0019, ISSUE-0007]
---

# Native two-test fixture semantics

## Objective and dependencies

User requests continued use of the multilingual corpus and verification that test code is drafted AND executed. Root/Sol audit verifies50 distinct candidates, ten per Java/Maven, Python, JavaScript, Perl and Ruby; all unqualified, all vulnerable references unset, ten fixed references missing, thirty supplied-oracle claims. CSV and JSON agree. No ready-made qualified test pair exists. Primary fixes for Cookiecutter, GitPython, JSPWiki and Plexus were inspected read-only; repository build/runtime compatibility and two-test execution remain unqualified. Keep candidate metadata unchanged.

## Steps

- [x] Review current source/records and benchmark inventory; identify absence of actual finding-specific drafting/execution.
- [x] Draft a minimal native pytest pair over the already-reviewed synthetic source variants, with genuine file-open witnesses and no mocked sink.
- [x] Independent code/assertion review, native collection, freeze and three fresh runs of each variant; retain expected assertion failures separately from infrastructure failures.
- [x] Audit exact source/test hashes, outcomes and workspace cleanup; publish scoped report/current/handoff after relevant offline guards.

## Validation and progress

Private evidence root `.runs/benchmark-admission-20261012/`. This bounded slice establishes manually authored fixture semantics only. Real benchmark candidates and model-authored drafts need their own source/runtime/admission review; ISSUE-0007 continues to block real-provider graph integration. Use no custom runner or schema/report framework.

Initial offline records check failed1/4 because the new records omitted mandatory template sections; corrected before workload execution. No runtime pass was inferred.

## Decisions and next action

Complete the frozen native two-test run and retain all outcomes before a fixture-only qualification claim.

Independent pre-execution source review passed. Six fresh native discovery/execution runs completed: exactly2 tests each, control6/6, vulnerable security3 expected assertion failures with actual outside-open/returned sentinel witnesses, fixed security3/3 with precise ValueError/no outside open. No skips/errors. Five frozen inputs/copies matched; identical test bytes in all runs. Native JUnit sum0.199s, command sum1.363421s. All six original workspace device/inode identities checked before deletion; absence confirmed. [Qualification](../../qualification/native-two-test-fixture.md) and fixture README retain recipe/limits. No model calls, downloads executed, OpenShell deployment or general runner added.
