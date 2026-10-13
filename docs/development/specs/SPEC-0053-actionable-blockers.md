---
id: SPEC-0053
kind: spec
title: Early stops and actionable setup blockers
status: accepted
updated: 2026-10-13
related: [PLAN-0057, SPEC-0029, SPEC-0042]
---

# Early stops and actionable setup blockers

## Goal and scope

The user requests quick, decisive stops and guidance for unavailable images, dependencies and connectivity, plus other developer blockers. Implement the runtime handoff and isolated environment setup boundary first. These are real existing consumers; neither is wired into the full real-case chain yet (G12). Do not claim whole-system coverage.

Brainstorm: check input/source identity, readable declarations, runtime/framework support, prepared image, host/storage admission, policy/credential configuration before expensive work where evidence exists. During work distinguish dependency resolution, registry access/authentication, TLS, DNS/connectivity, build/discovery, quotas, provider limits, unknown delivery and cleanup. A useful stop contains a stable code, observation certainty, responsible owner, evidence reference and ordered next actions. Detailed exploration and uncovered boundaries belong in the operator runbook.

## Boundaries and design

Reuse typed runtime selection, Pydantic contracts, native tool failures, the execution receipt and setup ledger. Add a small shared diagnostic value for runtime and setup consumers, not a new scheduler, retry engine or agent. Runtime stops preserve allowed ranges, preferred suggestions, source declarations and per-image rejections; distinguish missing runtime/image support from missing framework qualification and an unprepared selected image. Never prescribe a nearby version.

Unsuccessful setup commands stop further dispatch except for the narrow invocation correction allowance below. Read-only source/output inspection and a blocked result remain possible. Unknown delivery is never resent. Budget exhaustion prevents more dispatch but does not invalidate already-complete successful evidence. Raw native output and operation identity stay in the private ledger; diagnostics reference the run and do not copy raw output, command credentials or URLs. Final blocked outputs get diagnostics only from trusted ledger data, never model-authored diagnostic fields.

Output signatures provide reported symptoms, not verified causes: HTTP 403 is not proof of policy denial; package-not-found is not proof of registry availability; TLS errors do not justify disabling verification. Transport/cleanup/storage uncertainty takes priority over text classification. Each guidance entry explains what to investigate and who owns the action; no automatic policy, image, pin, credential or budget changes. Existing native adapters' detailed receipts remain authoritative.

## Acceptance and validation

No model/sandbox input is produced on runtime stop. No second execution dispatch after terminal/unknown setup failures, and ready cannot be emitted after a halt or while an invocation correction is unresolved. Exercise missing runtime vs framework vs preparation vs malformed metadata, normal success, dependency/TLS/network/access signatures, unknown classification, budget, output limit, journal and cleanup failures. Diagnostics must not infer policy from a generic connection error or publish raw secrets. Compare frozen scripted environment eval baseline/candidate using make eval AGENT=environment; change prompt/config identity honestly. Run affected tests and make test-config. No live provider or runtime qualification claimed by host checks.

## Decisions and open questions

User direction authorizes implementation. Infrastructure, dependency, compilation and baseline assertion failures remain terminal; operator/developer fixes resume through a new attributable attempt. Minor invocation corrections are admitted as specified below. The environment agent is still allowed to inspect saved output. Later extend producer-specific diagnostics to source fetch, lifecycle, provider and composition boundaries after they are admitted; retain their current native error receipts meanwhile. Full graph integration remains under G12. See PLAN-0057 and the setup-blockers runbook.

## Bounded invocation correction (review revision)

The user asked to revisit the first-nonzero stop. A known terminal native command result with no execution, journal, output-limit or cleanup failure may offer `correction_available`. Only one reported invocation symptom is admitted: direct pytest (including `python -m pytest`) exit 4 reporting unrecognized arguments. Recognized dependency/network/access/TLS/storage blockers take precedence. Shell-wrapped commands and arbitrary build/test failures are not eligible. A native execution exception remains terminal even if it reports a missing executable.

The next command must explicitly cite the failed run and explain the correction. Pytest must retain its executable prefix and change arguments. The skill forbids changing test scope to conceal failure. Missing Maven is terminal: admitted Maven images already provide it, while switching to a repository wrapper may download an unqualified distribution and bypass the image requirement derived from the wrapper pin. No identical previously failed invocation, unrelated command or unsolicited correction is admitted. No automatic retry occurs. Operator-owned `max_corrections` defaults to two, can be reduced to zero, and is capped at two. Corrections also consume the existing total command budget. Exhausting the total command budget stops further dispatch. Once the correction allowance is spent, any subsequent failure is terminal; ordinary successful setup commands may continue. Source/output reads remain available.

A successful correction clears the pending failure, but `ready` still requires the normal successful recipe, build, discovery and single-test evidence. Failed receipts remain in the final result. An unresolved eligible failure prevents ready/unsupported even when earlier commands completed a recipe. A refused extra call that never dispatched does not invalidate complete successful evidence.

These symptom checks are not proof of side-effect freedom or live recovery quality: pytest can load repository plugins before reporting usage errors, and tools can emit misleading text. The agent must inspect evidence and stop if effects are uncertain. This is deliberately a small admission rule in the existing tool, not a repair agent, shell parser or generic retry framework. The next live environment evaluation must measure correction offers/attempts, recovery and over-refusal rates, extra calls/tokens/latency, and sandbox effects using held-out bad-discovery cases and terminal missing-toolchain cases. Frozen scripted cases only establish their existing trajectories; added native FunctionModel trajectory tests establish the new admission boundaries. G12 and live qualification remain unchanged.
