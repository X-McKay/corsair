---
id: PLAN-0114
kind: plan
title: Discuss private local storage retention and staged cleanup
status: implemented
updated: 2026-10-25
---

# Local storage retention

The user requested continuing local cleanup and discussion of what .runs, .work and .state contain, what is needed and what to keep. This plan is proposed, not authorization to delete private evidence, keys, databases or environments. No saved data has been moved or deleted. Earlier working-tree changes and stash remain intact.

A metadata-only inventory found about2.1GiB allocated: .runs94MiB, .work1.81GiB, .state186MiB. Logical .work categories are973.69MiB completed-test temporary trees,332.59MiB dependency cache,317.25MiB validated task virtualenv and7.05MiB other files. Hardlinks/filesystem allocation mean these are not promises of reclaimed bytes.

Keep recent run stores and their complete blobs/operations/report chains, especially the open safe-case investigation. Keep selected final/failure receipts, small checkpoints and actual Temporal databases currently under task scratch. Older .runs cohorts are legacy evidence to keep/archive only after an owner decision. The large .state/temporal-local item is a Temporal binary/compressed download, not a database; .state/ollama folders contain tiny but sensitive configuration/certificates/private keys and scripts whose current use is unconfirmed. Do not infer inactivity from timestamps. Private settings/keys/trace contents were not opened.

Recommended first phase: explicitly select completed-test temp trees for removal, preserve final summaries and relevant failed-run evidence, and leave run stores, all .state, the validated environment/cache and actual databases alone. Next, recreate and validate one standard .venv before retiring the dated task environment; do not rename virtualenvs. Only then discuss cache retirement, legacy private archives and whether old provider/Temporal tools are still used. Do not introduce a custom garbage collector, broad clean-all command or automatic evidence pruning.

Implemented reversible housekeeping: added .work/ to root .gitignore (the other two private roots were already ignored), and repaired .dockerignore's stale trusted-driver allowlist to adapters/sandboxing/driver.py while preserving default-deny build context. The image rebuilt and7 native Docker tests passed with0 skips. No model calls, provider/configuration changes, credential migrations, data deletion or commits/pushes were performed.

The detailed user-facing retention proposal and sanitized housekeeping receipt are under outputs/local-storage-review-20261025. The preceding eval/test layout cleanup remains qualified at133 native non-live tests,103 offline tests, identical134 collected IDs and29 unchanged eval files. See [HANDOFF-0146](../handoffs/HANDOFF-0146-local-storage-review.md) and [recovery guidance](../../../operations/disaster-recovery.md) before any state migration.


## Final implementation result

The approved consolidation is implemented and native/regression-qualified locally: explicit worker composition, shared lexical source normalization, native ADK model types, maintained documentation/import/privacy gates, canonical root environment, verified state/history migration and retained-data cleanup. Full150-test suite passed before and after cleanup (170.87s and152.43s), with0 skips/errors;119 offline tests passed. Old fixtures/labels/receipts and runtime/dependency pins were preserved.12 passed-test temp trees,2 duplicate environments and the old task cache were retired after receipts/validation; .work allocation is about253MiB versus1.81GiB initially. All run stores, failed diagnostics, private database rollback snapshots and legacy TLS/provider state remain retained.

Original live role diagnostics passed3/3 and6/6. Final expanded candidate producer scored5/9 (four string-candidate oracle mismatches,0 provider errors) and auditor12/12; candidate promotion/human-held-out accuracy is not qualified. The distinct actual live batch remained2/3 with ISSUE-0010 open; ISSUE-0011 records new exact-match/semantic-equivalence uncertainty. Current Linux revision gate is unrun. See HANDOFF-0147 and the qualification/candidate receipts. No commit/push was made.

Earlier proposed/no-deletion statements above record its initial review stage; this closure records the later explicit approval and actual cleanup. Historical failures were not rewritten or discarded.
