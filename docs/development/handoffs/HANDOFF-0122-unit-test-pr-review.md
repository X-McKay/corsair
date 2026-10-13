---
id: HANDOFF-0122
kind: handoff
title: Unit-test PR review improvements
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093]
---

# Unit-test PR review improvements

## Verified state

Reviewed PR #130 at 8239073514dc5f3e58379831d8abf952403cfae9 on codex/unit-test-first-validation; CI was green. User requested improvements and simplification with skills/tools and shared language/framework/CWE contracts. Two independent review lanes inspected evidence and agent guidance; root reviewed composition and runner identities. Resolve this follow-up's final source from the branch rather than this base SHA.

Fixed findings:

- Incomplete source, patch or plan excerpts could receive an affirmative review bound to the entire source/patch. Evidence now explicitly records completeness, and affirmative review requires complete tool-read coverage of all patch files, full plan and reported condition, plus cited source. Truncated diagnostic output remains bounded. Negative/unknown conclusions remain available without pretending omitted code was reviewed.
- The isolated authoring evaluator used legacy witness restrictions even for unit observations, incorrectly rejecting native dependency doubles. It now applies the same mode as production authoring.
- Shared observation mapping split test ids using pytest syntax. Native failure function names now come through the runner grammar boundary, including method/subtest ids. This corrects identity mapping; it does not qualify new language authoring or runtimes.

Simplifications: removed unused pre-injected validity records from composition; normal unit runs no longer raise/catch an exception to avoid instrumentation. Shared authoring guidance is property-based rather than Python/pytest/Minitest recipes; legacy witness invariants are conditional. Planning can read relevant helpers/dependencies within the existing source inventory and budgets. Skill procedures remain loaded by native PydanticAI Capability with restricted tools. No new agent, tool framework, provider wrapper or CWE dispatch was added.

Earlier unrelated HANDOFF-0118/0119 files and their CURRENT pointer remain local and excluded from the PR.

## Validation and blockers

- Focused planning/authoring/evaluator checks: 259 passed; native runner grammar checks: 9 passed.
- Focused assessment/composition checks: 55 passed before the final identity helper integration; final full suite covers integration.
- Frozen scripted comparisons: planning 12/12 and authoring20/20 unchanged. Evidence `/tmp/corsair-pr130-planning-review`, `/tmp/corsair-pr130-authoring-review`; assessment54/54 unchanged. Final full suite:2086passed,6skipped,12inherited warnings in56.16s (`/tmp/corsair-pr130-review-full.log`).
- Initial restricted-socket checks stalled and were interrupted; host loopback-enabled retries passed. During parallel edits, interim assessment runs had four call-signature transition failures, then four scripted pagination access failures; corrected pagination consumes typed tool results and reads every window. These were test/integration failures, not live investigation evidence.
- Existing baseline failures and qualification boundaries remain in HANDOFF-0123/0121. Live model semantic accuracy, runtime expansion and old-history replay remain unrun. Byte-compatible legacy frozen fixture checks are retained.

The user further required certainty that both probes execute. Design, AGENTS and agent skills now explicitly name the benign control probe and exploit probe (security safety regression); each must exercise the real path on every investigated revision. The exploit probe asserts safe behavior. Existing native gate enforcement was retained and missing/skipped-either-probe regressions added: final gate/workflow subset30passed. All three frozen scripted evaluations were rerun after these skill/schema descriptions:12/12,20/20,54/54 with zero failures (`/tmp/corsair-pr130-{planning,authoring,assessment}-probes`). These additions are after the full-suite run and do not claim new live execution coverage.

## Decisions and next steps

Maintain one validity-producing composition path through independent assessment. Native tool reads establish what evidence was available to the reviewer, not proof its semantic judgment is correct. Run live semantic calibration separately; do not add mandatory low-level recorders to compensate for absent review evidence. Review updated PR CI before merging; no merge authorized.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, PLAN-0093, SPEC-0078 and HANDOFF-0122. Inspect PR130 source and checks. Preserve shared unit-test observations, independent evidence review and native skills/tools. Address concrete remaining findings, keep language syntax at runner/adapter boundaries and do not add per-CWE verdict logic. Preserve qualification limits and unrelated local review notes. Update records and validation after changes.
```
