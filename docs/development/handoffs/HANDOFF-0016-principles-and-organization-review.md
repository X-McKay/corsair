---
id: HANDOFF-0016
kind: handoff
title: Principles and organization review
status: recorded
updated: 2026-10-11
related: [PLAN-0014, PLAN-0013, ISSUE-0006, SPEC-0012]
---

# Principles and organization review

## Verified state

Branch codex/immutable-source-artifacts started clean at 8efcd2e94ee7cfd0249b7b578e646e5f4ec91725. Native GitHub inspection confirmed open draft PR11 at that head, stacked above codex/openshell-execution-adapter, and successful exact-head CI38182335624. Retained actual CI output shows148 passed. This handoff accompanies documentation-only corrections; resolve its published commit with git log -1 --format=%H -- docs/development/handoffs/HANDOFF-0016-principles-and-organization-review.md and verify current PR/CI rather than assuming publication from the snapshot.

Reviewed AGENTS, development/review/handoff skills, architecture, recovery contracts, active source and transfer/source records. The implementation is still eight port/adapter modules (861 lines), with no agent/durable integration or generic scheduler/repair/transfer framework. README and CURRENT have been simplified into entry points; detailed failures, identities, budgets and qualification facts remain in their reports and historical handoffs. PLAN-0014 records findings and corrects its stale publication closure. Runtime, policies, pins, tests and qualification source are unchanged.

## Validation and blockers

UV_OFFLINE=true make test-config passed148 checks in4.56s; git diff --check passed. PLAN-0014 records the review findings and a refused patch-context attempt that made no changes. No cluster, install, transfer or new host qualification was dispatched. Existing source-v3 local evidence and historical runtime qualification keep their original envelopes; this review creates no new live qualification claim. HANDOFF-0015 and the qualification reports preserve raw-evidence availability, failed/unknown attempts and cleanup history.

ISSUE-0006/PLAN-0013 remain blocked. The local ArtifactStore seam currently retains backend-specific failure attribution through a concrete local error and dictionary receipt; normalize a narrow typed failure contract before another backend or agent/durable consumer is admitted. This is a portability limitation, not a claim that current local qualification failed. Production concurrency/storage crashes, live worker/controller/transport fault recovery, full Milestone2 and PydanticAI/Temporal remain unqualified.

## Decisions and next steps

User requested principles review before moving on to retry/reconciliation. Do not treat this handoff as authorization to start that implementation now. Keep native capability reuse, one bounded objective and operator-owned resource controls. Keep detailed evidence in reports, current gate/navigation in CURRENT, decisions in plans/issues and historical facts in append-only handoffs. No new tracker, generic retry engine, speculative package scaffolding or unsupported transport is justified.

When transfer work resumes, first establish the minimum useful native operation and its supported retry/extraction semantics, including an explicitly safe narrower contract if feasible. Unknown mutation is not blindly replayed. A concrete native capability gap and measured need must precede bespoke code. Mandatory fresh-node storage/kernel/CNI/gateway admission remains required before live transfer work; no policy/TLS/pin/kernel weakening. Existing authorization permits tracked draft publication, not merges, external issue closure or messaging.

## Continuation prompt

Read AGENTS.md, README.md, CURRENT.md, the Corsair development/review/handoff skills and this handoff. Inspect branch/status and verify publication/CI. Read PLAN-0014's principles review and the linked qualification reports; source-v3 executable bytes and qualification limits remain unchanged. The user paused retry/reconciliation implementation for this review. Preserve that scope unless subsequent direction resumes it. If resumed, read SPEC-0011/PLAN-0013/ISSUE-0006 and investigate the smallest supported native transfer contract before wrapping or dispatch. No generic retry/reconciliation framework, blind replay or unbounded extraction. Use appropriate offline checks, current-node mandatory admission for live work, attributable evidence and identity-checked cleanup. Update existing records where possible, append a handoff for substantial work and publish only tracked authorized changes; never commit .runs/.state/credentials/raw logs.
