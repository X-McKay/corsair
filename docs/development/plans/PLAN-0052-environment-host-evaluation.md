---
id: PLAN-0052
kind: plan
title: Environment agent review and host evaluation
status: complete
updated: 2026-10-13
related: [SPEC-0029, SPEC-0044, PLAN-0048]
---

# Environment agent review and host evaluation

## Objective and dependencies

Review SPEC-0029 implementation and fill PLAN-0048 environment gap under SPEC-0048.
Base 6be1b5f55224cbf97dc03a89f8c8a29d79f19df4; branch codex/agent-environment-improvements.

## Steps

- [x] Review factory, skill, contracts, command tool and framework admission.
- [x] Implement frozen host-only development cases and explicit-provider suite.
- [x] Register command and correct missing-report comparisons.
- [x] Run native suite, affected tests and review; retain failures.

## Review findings and decisions

Production checks already refuse unobserved commands/ordering, unread citations, wrong toolchain,
unknown delivery, skipped baselines and invented failures. No prompt change is justified by a
scripted oracle echo; existing v1 remains. The unsupported requirement is source grounded but
semantic truth is model judgement (a historical test uses a contradictory3.13 claim against3.12
source); fresh held-out semantic checks should assess this. Discovery is a retained-output substring
claim, and baseline summaries are workload printed; actual discovery/execution needs native runner
receipts. Phase-policy enforcement, closure and fresh replay remain external unqualified boundaries.
This host fixture does not claim to resolve them. Registry/TLS layer correctness is curated, not
proof that arbitrary output is interpreted correctly. Source reads plus production finalizer ground
citations; no LLM judge added. Fixtures adapted from unit tests are synthetic, not benchmark captures.

## Validation and progress

First make attempt failed before report (missing Dataset name); next attempt12 task failures from
native SourceRead handling; next had unknown-output-tool accounting failures; initial expanded
suite14/16 failed because synthetic Java summary lacked native INFO prefixes. All retained locally.
Final same-set Make runs16/16 clean with12 assertions each; native metrics and comparisons filed
under .runs/evals/environment. No existing environment eval baseline; no promotion performed.
Affected tests initially61 passed/1 failed: old test expected environment registration refusal.
Updated obsolete assertion; final counts recorded below. Live provider, cluster, sandbox and durable
runs unrun. No credentials inspected and no live model calls made.

## Decisions and next action

Add independent held-out semantic cases and captured observations before prompt optimization.
Run explicit-provider measurement only with a supplied configuration and budget authorization.

Final checks: affected62 passed before two additional negative/telemetry checks; the expanded
focused suite result is in the commit validation. `make test-config`: first993 passed/1 failed
(template omission), corrected994 passed with one SDK deprecation warning. Additional tests
check wrong toolchain/framework/discovery and sparse metric coverage; final native suite has14
assertions per attempt. `ruff check --no-cache` and `git diff --check` passed. Missing current
and reference reports are explicit unknown/unavailable; summary includes each metric's observed
sample count and total attempts without imputing zeros for absent telemetry. These changes reuse
PR47 filing and preserve its mean keys. Typed frozen fixture validation and exact quoted-source
checks precede evaluation. No provider config selected; live-provider and runtime gates unrun.

Independent root review found policy-profile labels leaking expected outcomes to the prompt.
Corrected to one neutral policy identity; HostInput selects fixtures by an evaluator-only id,
then passes only EnvironmentInput to the production prompt/dependencies. Added prompt leakage
regression and intentionally renewed development manifest. No results across changed dataset
identity are directly comparable. Corrected set16/16 native attempts passed. Final focused
suite65 tests passed (one pre-existing SDK warning); workflow guard5 passed. Final Make output
includes per-metric sample coverage. Root provider action was blocked by auto-review; this lane
made zero provider requests and leaves live validation unrun.

Planning cross-review reproduced a semantic false positive: inverted required/prepared versions
passed source-read/quotation checks. Added evaluator-only curated requirement patterns for the
frozen unsupported case, requiring Python3.13 as required and3.12 as prepared. Negative regression
keeps the correct source citation and reads while inverting the authored requirement, and confirms
only the semantic assertion fails. This bounded wording check does not establish arbitrary-language
understanding. Manifest deliberately renewed; prior dataset results remain incomparable. Follow-up
Make run16/16 clean with 15 assertions each; focused 71 checks passed (one SDK warning). Root reports
full suite at prior6f35dd3 passed997 tests; follow-up changes only evaluator/fixtures/regression records.

Root final review: label shared metric means as per observed sample and label the suite synthetic in command metadata. Full offline suite at6f35dd3 passed997 checks; follow-up unsupported-requirement regression and affected checks passed71. No further provider dispatch was attempted after automatic approval review blocked external fixture transfer in the planning lane.


PR57 follow-up review corrections (2026-10-13, base `a1d44c3`): independently reproduced
that a compile-only build-blocked trajectory scored `required_commands=True` and a measured
zero `observed_commands` attribute disappeared from the shared summary. The evaluator now
requires the curated exact command prefix for every status, shortened only at the first
unknown-delivery observation or the operator command cap. Regression cases reject omitted
dependency setup, reversed commands, skipping the unknown command, commands after unknown
delivery, skipping the budget prefix and commands after the cap. The shared summary merges
explicit numeric `observed_*` attributes with native metrics once per attempt; metric entries
win when both exist, measured zero contributes to means/coverage, and absent values stay
unknown. The regression distinguishes a measured zero, a duplicate metric/attribute pair
and genuinely missing telemetry. CURRENT's old environment-eval-pending phrase is corrected.

Affected tests: `tests/agents/test_environment_evals.py`, `test_environment.py`,
`test_isolated_evals.py`:70 passed, one existing SDK warning. Same frozen set
`f6185b41494111fecd4178cc81874120b2bd2ba97c98f37df921ab9faa3fd939`,
`make eval AGENT=environment`:16/16 at
`.runs/evals/environment/20261013T100728Z-development-scripted`, compared with
`20261013T100037Z-development-scripted`16/16. Corrected measured command mean1.75
(previous summary2.0 excluded the two unsupported attempts' measured zeros); observed
output corrections0.0 with16/16 coverage (previously absent). Requests5.25, tool calls3.75,
input/output token estimates1016.25/162.25 unchanged. No provider or infrastructure action.
`make test-config`:1050 passed, one existing SDK warning, 50.33 seconds. Updated workflow guards5 passed; `git diff --check` passed. Broad `ruff check` found existing shared-runner F401 (unused field import) and E731 (comparison lambda), both outside this fix; evaluator/regression files lint passed. Final review retains synthetic-runtime limits
and no model prompt/config/skill or dataset change.


Provider-coverage review follow-up (2026-10-13): a new regression reproduced missing and
partial provider token totals being counted as complete samples. The shared summary now
excludes native and observed input/output token metrics when provider_usage_present is false,
while preserving genuine zero counters, known token observations and scripted estimates.
The regression failed before the fix and passes after it; 23 affected checks passed.
Unrecorded fixture commands now identify their exit 126 response as synthetic and appear in
the attempt receipt under unrecorded_commands. The README explicitly limits live scores to
curated argv adherence. No provider or infrastructure was invoked. The first attribution
edit missed the fallback insertion and failed one test; corrected before the passing suite.
Main f6a87d6 (PR58) merged cleanly. Frozen host-only Make remains 16/16.
Full offline make test-config: 1056 passed, one existing SDK warning (52.48 seconds).
Independent read-only follow-up: four targeted regressions passed, no blocker found.
Scripted evidence: .runs/evals/environment/20261013T102019Z-development-scripted.
