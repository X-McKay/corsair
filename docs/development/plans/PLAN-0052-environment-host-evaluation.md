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
Base6be1b5f55224cbf97dc03a89f8c8a29d79f19df4; branch codex/agent-environment-improvements.

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
