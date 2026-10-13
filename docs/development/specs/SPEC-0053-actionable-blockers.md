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

Every unsuccessful setup command is terminal for further command dispatch in that attempt. Read-only source/output inspection and a blocked result remain possible. Unknown delivery is never resent. Budget exhaustion prevents more dispatch but does not invalidate already-complete successful evidence. Raw native output and operation identity stay in the private ledger; diagnostics reference the run and do not copy raw output, command credentials or URLs. Final blocked outputs get diagnostics only from trusted ledger data, never model-authored diagnostic fields.

Output signatures provide reported symptoms, not verified causes: HTTP 403 is not proof of policy denial; package-not-found is not proof of registry availability; TLS errors do not justify disabling verification. Transport/cleanup/storage uncertainty takes priority over text classification. Each guidance entry explains what to investigate and who owns the action; no automatic policy, image, pin, credential or budget changes. Existing native adapters' detailed receipts remain authoritative.

## Acceptance and validation

No model/sandbox input is produced on runtime stop. No second execution dispatch after failed/unknown setup, and ready cannot be emitted after a halt. Exercise missing runtime vs framework vs preparation vs malformed metadata, normal success, dependency/TLS/network/access signatures, unknown classification, budget, output limit, journal and cleanup failures. Diagnostics must not infer policy from a generic connection error or publish raw secrets. Compare frozen scripted environment eval baseline/candidate using make eval AGENT=environment; change prompt/config identity honestly. Run affected tests and make test-config. No live provider or runtime qualification claimed by host checks.

## Decisions and open questions

User direction authorizes implementation. Stop the setup attempt after any nonzero command: fixes are operator/developer-owned and resume uses a new attributable attempt. The environment agent is still allowed to inspect saved output. Later extend producer-specific diagnostics to source fetch, lifecycle, provider and composition boundaries after they are admitted; retain their current native error receipts meanwhile. Full graph integration remains under G12. See PLAN-0057 and the setup-blockers runbook.

Review follow-up: fail-fast on every dispatched nonzero setup command is intentional under the user request, including wrong-wrapper or discovery-probe guesses. Its live over-refusal/recovery cost is unmeasured; frozen scripted trajectories cannot establish it. The next live environment evaluation must measure these cases before claiming operational quality. A refused budget call that never dispatched does not invalidate complete ready evidence.
