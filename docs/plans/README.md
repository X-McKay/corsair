# Current work and plans

This is the current work index. Current user guides start at the [documentation index](../index.md); records in [archive](archive/README.md) are evidence, not executable instructions for the current tree.

## Active work

- [ISSUE-0001: intake conflicting-report abstention](active/ISSUE-0001-intake-conflicting-reports.md) remains open after a false-supported candidate result.
- [PLAN-0004: Qwen intake route evaluation](archive/plans/PLAN-0004-intake-qwen-route-evaluation.md) records native tool/schema compatibility and both frozen cohorts, including the unresolved false-supported contradictory report.

- [PLAN-0002: improvement loop, rounds 1 to 4](active/PLAN-0002-improvement-loop-rounds-1-2.md) records the 55 parallel experiments merged, held or discarded on `feature/improvement-loop`, the round-3 organization pass, the round-4 response to the external review, the live diagnostics and the first live chain per runtime run at integration, and the decisions that need the project owner.
- [PLAN-0001: pilot plan and open decisions](active/PLAN-0001-pilot-plan-and-open-decisions.md) records what the pilot implements, the decisions taken for the pilot, the gates that have and have not run, and the items still awaiting the project owner.

## Decisions in force

The architecture decisions in [`docs/architecture/decisions/`](../architecture/decisions/0001-sdk-owned-durable-rounds.md) are the accepted design: SDK-owned durable rounds with one ADK episode per Temporal activity, canonical Pydantic contracts and narrow ports, immutable native evidence, and the payload-pair contract with a coverage-gated kernel and six labels. PLAN-0001 lists which of those the owner may still revisit.

## Record conventions

Put a bounded plan in `active/` with its goal, scope, decisions, commands, actual results and blockers. Keep failed and unrun checks. Move completed plans to `archive/plans/`; handoffs to `archive/handoffs/`; resolved issues to `archive/issues/`; historical reviews to `archive/reviews/`. Update this index and relative links in the same change. Work state must distinguish proposed, implemented and qualified behavior.

Do not commit raw `.runs/`, `.state/`, private diagnostics, credentials, model reasoning or unredacted evidence. A sanitized receipt must preserve unknown metrics as unknown and must not turn skipped discovery, denied execution or mocked dependencies into qualification. Publishing, deployment and issue closure remain subject to the user's current authorization.

- [PLAN-0003: intake-agent integration](archive/plans/PLAN-0003-intake-agent-integration.md) preserves current main while adding bounded agentic normalization, image selection and categorical workflow gates; provider-route and live-quality limits remain explicit.
