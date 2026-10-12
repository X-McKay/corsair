---
id: PLAN-0014
kind: plan
title: Immutable local source and artifacts
status: complete
updated: 2026-10-11
related: [SPEC-0012, PLAN-0013, ISSUE-0006]
---

# Immutable local source and artifacts

## Objective and dependencies

Implement SPEC-0012 independently of the blocked native transfer boundary. Retain the existing runtime tuple and qualification claims. One exclusive local host artifact root and trusted complete bare Git source, no workload reach or provider/durable integration.

## Steps

- [x] Read source/evidence/native capabilities and define bounded storage/source scope while preserving transfer blocker.
- [x] Implement narrow artifact/source contracts, standard no-overwrite storage and bounded native Git capture; run smallest meaningful offline contracts and repository guards.
- [x] Freeze source; qualify two independent actual-host capture/restart/no-hook/resource/failure cases and exact identity cleanup. Retain every failure.
- [x] Review final diff, update report/CURRENT, append handoff, publish tracked stacked draft and verify exact-head offline CI.

## Validation and progress

Baseline123 offline checks passed. Parent raw/source/CI and five original cluster absence checked before edits; no live runtime remains. Git2.43.0 binary SHA2562a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668 inspected, native cat-file/ls-tree docs verified. Use raw blobs without filters/archive/checkout, supported Linux prlimit plus bounded pipe/deadline supervision. Final148 checks passed before source-v3 live work (94 guards/15 lifecycle/14 execution/25 artifact-source contracts). Native Git raw objects/tree and prlimit primary references inspected. Implemented vendor-free references/source manifest, standard atomic no-overwrite local objects and protected source journals; no generic transfer/archive/credential service.

Preparation failures retained: wrong initial CLI path (read-only), missing repository import path in freeze helper, then artifacts-host-001 config preflight failed before fixture/native capture. Correct explicit PYTHONPATH/set -e and new directories. Source-v1 artifacts-host-002/003 passed intermediate matrices and original fixture cleanup, excluded after final review added native fsck tree integrity and corrupted-tree contract. Final frozen source-v3 artifacts-host-006/007 passed in0.121/0.097s:4 source operations each,33 actual source children and18 fixture/reader/probe children each;102 total reaped. Exact binary/nested executable/raw attributes, duplicate inodes, symlink/oversized-source refusal, actual corrupt artifact refusal/no overwrite, fresh reader of3 objects, native hard AS512MiB/CPU10s and excess allocation refusal all passed. Original fixture device66312/inodes57430612/57430617 checked and absent; immutable private objects/receipts intentionally retained. Independent audit first mistook native absent-config exit1 for failure; corrected command-specific audit passed without source/raw changes. Actual source/hash/receipt/object/cleanup audits in ignored .runs/transfers-storage-resume/host-audit-006/007.json. See reviewed [qualification](../../qualification/local-source-artifacts.md).

Source-v2 matrices004/005 also passed and cleaned original fixtures; they remain intermediate after review retained exact temporary identity and conservative creation uncertainty in failure records. A premature CURRENT handoff link caused1 failed/147 passed guard result; set -e stopped dispatch, the pointer was corrected and148 passed before source-v3 qualification. Final Corsair review corrected tree integrity, executable type admission and temporary failure attribution before final freeze; no unresolved blocker within this exclusive local slice. Existing executable/native inputs unchanged; no cluster/gateway/transfer dispatch. Diff/records/handoff reviewed. Tracked stacked draft [PR11](https://github.com/X-McKay/corsair/pull/11) was published at 8efcd2e94ee7cfd0249b7b578e646e5f4ec91725; native [CI38182335624](https://github.com/X-McKay/corsair/actions/runs/38182335624) succeeded at that exact head with148 actual checks. Published head/CI were freshly verified during the following principles review.

## Decisions and next action

Native transfer ISSUE-0006 blocks dependent sandbox integration. Local host storage/capture has no gateway dependency and requires no cluster creation. Preserve logical immutable identities and uncertain filesystem publication, separately from actual disk power-loss durability and production concurrency. Local capture/storage is qualified only for this selected actual host. Native transfer remains blocked; next work is supported transfer admission resolution, then dependent adapter/fault qualification. Remote/source checkout/production concurrency and hard filesystem-I/O cancellation remain unqualified.

## Principles and organization review

The follow-up review is documentation-only; retry/reconciliation implementation is deferred by the user's current direction. Source remains eight small port/adapter modules, with no speculative agent/workflow folders, scheduler, transfer protocol or repair framework. Native Git/OpenShell and standard filesystem facilities do the underlying work. Local process/resource supervision and receipt bookkeeping have recorded concrete admission needs; they are not a shared execution framework.

Finding corrected: README and CURRENT duplicated detailed qualification/failure history and emphasized cumulative check counts. README now states product purpose and present support; CURRENT is a short active-gate/report index. Reports retain authoritative coverage and evidence, living plans/issues retain decisions and status, and old handoffs remain snapshots. The workflow guide now describes all adapter unit suites. Publication/CI closure above was stale and is corrected from actual GitHub state. No history or raw evidence was deleted.

Remaining boundary limitation: GitSource accepts ArtifactStore but imports the concrete local ArtifactStorageError for failure attribution, and exposes its failure receipt as a dictionary. This is sufficient for the currently qualified exclusive local backend, but it is not a complete portable typed failure contract. Before admitting another backend or an agent/durable consumer, define the smallest common failure contract preserving partial identity, publication/delivery uncertainty and cleanup; validate all affected consumers. Do not introduce a generic error framework or refactor qualified code solely for anticipated consumers.

Before resuming transfers, keep one concrete native operation and its input/output/authority/failure criteria in PLAN-0013. Assess a supported safe narrower contract as well as native control options; lack of CLI flags alone must not become a mandate to build custom reconciliation. Unknown mutation must remain unknown unless actual supported semantics establish safe reuse. Operator resource budgets are local controls with a recorded basis, never invented SLOs. Future changes must satisfy the existing native-first, no-silent-fallback and progressive-qualification rules.

Validation for this documentation-only review: UV_OFFLINE=true make test-config passed148 checks in4.56s; git diff --check passed. Final documentation diff reviewed against the linked reports and unchanged source. An initial combined patch had a stale workflow-guide line context and was refused atomically; git status confirmed no mutation before the corrected edit. No runtime or qualification-source changes; no live rerun needed or claimed.

The subsequent [execution-output composition](../../qualification/openshell-adapter-execution.md) passed on two fresh admitted OpenShell nodes under PLAN-0012: exact bounded completed stdout/stderr enters the unchanged LocalArtifacts adapter and a fresh host process reads it after original sandbox cleanup. This extends composition evidence only; source-to-sandbox staging, arbitrary workload files and ISSUE-0006 transfer admission remain separate.
