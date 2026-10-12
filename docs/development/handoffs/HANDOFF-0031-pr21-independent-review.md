---
id: HANDOFF-0031
kind: handoff
title: PR21 independent review and merge blockers
status: recorded
updated: 2026-10-12
related: [HANDOFF-0030, PLAN-0018, ISSUE-0007]
---

# PR21 independent review and merge blockers

## Verified state

Reviewed [PR21](https://github.com/X-McKay/corsair/pull/21) at immutable head `8300800ef49463b1b615e2fe83045f6f95bfa8d5` against clean main `a13e08526169a3cc3358cdab09ef024914a632a8`. The user explicitly requested Sol fan-out and authorized posting relevant developer critiques. Three independent Sol lanes covered agent/provider/evaluations, Temporal, and OpenShell. Root independently reproduced actionable findings and published [the review comment](https://github.com/X-McKay/corsair/pull/21#issuecomment-6128102850). The PR was not merged or edited.

Main's implementation remains the HANDOFF-0030 typed skills/source-tool checkpoint; its Development guards38275256121 passed. This continuation changes records only. Resolve its published revision with `git log -1 -- docs/development/handoffs/HANDOFF-0031-pr21-independent-review.md`. ISSUE-0007 remains blocked; corpus executions remain zero. No unrelated working files were changed.

## Validation and blockers

The exact PR head was fetched to `refs/review/pr-21` and archived to `/tmp/corsair-pr21-8300800`, leaving main untouched. The lock/dependency files match the baseline. The offline guard suite using the repository's pinned environment passed286/5.90s with one existing event-loop deprecation warning. Private review/reproduction evidence is under ignored `.runs/pr-0021-review-20261012/`; it is not committed.

GitHub reports CONFLICTING/DIRTY with no checks exposed for this head. Native `git merge-tree` against main confirms eight conflicts in current records, agent/provider, evaluations and tests. Reconciliation must preserve main's native skill/toolset, numbered source-read and typed output-function changes rather than restoring the PR's older base. Both handoff filenames survive a merge but declare HANDOFF-0030; the existing record guard reproduced the duplicate-ID refusal. The developer must allocate a unique ID at integration time and update references.

The new workflow result incorrectly treats any nonzero usage field as complete input/output token reporting. Root reproduced the complete offline direct workflow with an input-only native RequestUsage: usage_reported=True, input_tokens=7, output_tokens=0, requests=1. Missing output telemetry should not become a measured zero. The review requests explicit reporting evidence or conservative unknown accounting plus partial-usage tests. No numeric budget ceiling bypass was found; disclosed durable type coercion was distinguished from a blocking exploit. No additional confirmed OpenShell/provider defect was found.

No live provider, Temporal service or OpenShell qualification was run for this PR review. Its disclosed live qualification gaps remain unqualified. The full local passing suite is evidence for the PR head alone, not for the unresolved combined source. Review posting succeeded and returned the linked comment URL; no uncertain delivery or duplicate post remains.

## Decisions and next steps

PR21 is not ready to merge at the reviewed head. Await the developer's reconciled update; review the new exact diff, reproduce the usage fix and unique record IDs, and run affected checks/CI against the combined source. Changed durable payloads/names and OpenShell recipe behavior still need the separately declared live qualification before those scopes can be called qualified. Do not silently rerun live infrastructure or merge merely because the old head's286 offline checks pass.

The ongoing implementation objective and authorization remain in HANDOFF-0030/PLAN-0018: native skills/tools/contracts, semantic consistency work and periodic tracked publication; no policy, TLS, immutable pin, kernel or oracle boundary may be weakened. This review did not alter those gates.

## Continuation prompt

```text
Read AGENTS.md, README.md, CURRENT.md and the Corsair development/review/handoff skills. Read HANDOFF-0030 for implementation state and HANDOFF-0031 plus the linked PR21 comment for review findings. Verify local/remote/source state. If reviewing PR21 again, pin its new head, inspect how it preserves current main's skill/tool/output contracts, reproduce partial-usage accounting and duplicate-record fixes, and check exact-head CI. User authorized posting relevant critiques, not an automatic merge in this review request. Keep existing semantic/runtime gates explicit. Otherwise resume PLAN-0018/ISSUE-0007's next bounded semantic-grounding work. Preserve evidence, run proportionate checks, update records and append a new handoff before stopping.
```
