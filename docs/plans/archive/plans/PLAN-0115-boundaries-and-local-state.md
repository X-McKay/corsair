---
id: PLAN-0115
kind: plan
title: Tighten code boundaries, local state lifecycle and maintained quality/evaluation gates
status: implemented
updated: 2026-10-25
---

# Approved consolidation

User explicitly authorized all structural-review recommendations: ignore private/generated files; establish a validated canonical .venv; place ongoing persistence under .state; keep .work disposable or explicitly retained; make worker adapter composition explicit; remove backward dependencies; add maintained documentation/import checks; strengthen evaluation baselines. Preserve current manus/just work, original-main stash, frozen v1 diagnostics, actual run evidence and unclear legacy provider/TLS ownership. No commit/push/deployment is requested here.

Parent owns ignore rules, root environment migration, exact task database backup/integrity/ownership, state documentation, orchestration and final qualification/package. Independent owners cover (1) code composition/type/request ownership and affected tests, (2) maintained doc/import/quality gates, (3) expanded small diagnostic dataset plus baseline-versus-qualification organization. New authored evals are explicitly candidate diagnostics, not falsely human-labelled held-out or population baselines. No unsupported new backend/scheduler/garbage collector, role permission change, prompt/oracle leak, TLS bypass or repair layer.

Checkpoint current source/config/docs/evals before changes. Verify exact database ownership via lsof and use SQLite backup API with integrity checks into .state/temporal/history; preserve originals until validated and do not silently turn historical runs into an active service. Recreate .venv using pinned Nix/uv in place, backing up the old directory only for rollback (never run a relocated environment). Keep old validated task environment until root checks pass. Completed passed-test temporary copies can be retired after receipts and evidence are preserved; retain failure-specific paths, .runs stores, keys and active settings.

Required sequence: implement, isolated/frozen and real native end-to-end validation, final code/data cleanup, retest, fresh source/wheel packaging. Track all failed/unrun results and observable timing. Final model eval uses the existing explicitly configured user endpoint with no new credentials or silent provider substitution. Local Linux target checks and human held-out promotion remain unqualified unless actual evidence is obtained.


## Final implementation result

The approved consolidation is implemented and native/regression-qualified locally: explicit worker composition, shared lexical source normalization, native ADK model types, maintained documentation/import/privacy gates, canonical root environment, verified state/history migration and retained-data cleanup. Full150-test suite passed before and after cleanup (170.87s and152.43s), with0 skips/errors;119 offline tests passed. Old fixtures/labels/receipts and runtime/dependency pins were preserved.12 passed-test temp trees,2 duplicate environments and the old task cache were retired after receipts/validation; .work allocation is about253MiB versus1.81GiB initially. All run stores, failed diagnostics, private database rollback snapshots and legacy TLS/provider state remain retained.

Original live role diagnostics passed3/3 and6/6. Final expanded candidate producer scored5/9 (four string-candidate oracle mismatches,0 provider errors) and auditor12/12; candidate promotion/human-held-out accuracy is not qualified. The distinct actual live batch remained2/3 with ISSUE-0010 open; ISSUE-0011 records new exact-match/semantic-equivalence uncertainty. Current Linux revision gate is unrun. See HANDOFF-0147 and the qualification/candidate receipts. No commit/push was made.
