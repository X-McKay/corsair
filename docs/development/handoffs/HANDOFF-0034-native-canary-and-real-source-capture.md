---
id: HANDOFF-0034
kind: handoff
title: Native canary and real source capture
status: recorded
updated: 2026-10-12
related: [PLAN-0021, PLAN-0022, ISSUE-0006, ISSUE-0007]
---

# Native canary and real source capture

## Verified state

Started on clean local/remote main `afb75f3984f5a1453bd5dd57ba569ca12a1ab96d`. PR21 is already merged; HANDOFF-0033 retains the prior review/provider history. This checkpoint adds reports and an evaluator-only JSPWiki test draft, without changing runtime/agent/core implementation. The115-input runtime freeze still matches source and retained copies. Resolve the commit carrying this handoff using Git; its future SHA is not asserted here.

The user approved independent runtime requalification and first real-case preparation alongside blocked ISSUE-0007. Root alone owned native service/cluster mutations. Sol lanes independently researched source/dependencies, drafted/reviewed tests and audited native evidence. Root reviewed the final artifacts and raw identities. Use the [native checkpoint](../../qualification/post-pr21-native-canary.md) and [benchmark synopsis](../../benchmark-admission-progress.md), not this handoff alone, to locate actual evidence.

Native Temporal is freshly qualified for the scripted fixture scope at the merged source. One fresh OpenShell node passed mandatory admission and both lifecycle canaries. This is not complete two-node renewal of all affected OpenShell matrices or production readiness. All50 real cases remain unqualified with zero executions. ISSUE-0007 still blocks real-provider semantic/consistency qualification and dependent agent composition; no inference was dispatched in this checkpoint. ISSUE-0006 remains blocked for broader transfers/reconciliation.

## Validation and blockers

- Full offline preflight:363 passed/6.23s. Later native-host rerun:363/6.16s under60s outer bound; one existing event-loop warning. An intermediate restricted-process run stalled in mocked provider transport; its partial log remains retained. Only original PID2917909/start54696201 was signaled (SIGINT then SIGTERM) and confirmed absent. An unrelated older process was preserved.
- Final record/link checks:4 passed/0.04s through the existing venv. A direct `uv run` attempt first failed before pytest because its default external cache was read-only; the log is retained and no dependency changed. Authored changes pass the whitespace check; the complete staged check reports six inherited trailing-whitespace lines in exact upstream LICENSE/NOTICE bytes, deliberately preserved for provenance. Independent source/test/runtime audits found no blocker within the stated scope.
- Native Temporal:33 passed/6.39s, zero failures/errors/skips,20 terminal histories saved/replayed, typed budget/model-key refusals before scheduling, direct/durable fixture usage and traces checked. Separate same-SQLite original parent/child resume after service restart passed/0.414s; exact pending event prefixes preserved and completed once. Owned PIDs2862181/start54626772 and2864454/start54631628 exited0; identities absent and17333/17334/17336 closed. The969 sandbox-import warnings remain visible. Old-history migration, crashes and real-provider durability remain unqualified.
- OpenShell node UID `03936973-0627-4b8e-b64d-3c3119ee6fdd`: storage/kernel1/100.37s, CNI3/160.18s, native lifecycle1/117.26s, adapter lifecycle1/121.87s, no JUnit failures/errors/skips. Each lifecycle slice ran three real cycles and fresh mandatory gateway controls. Raw create requests send NEVER; adapter waits/host intents bind300/60 seconds. Separate harness cleanup uses90 seconds. Independent audits preserve expected native NOT_FOUND observations and forged-ID refusals.
- Final native inventory: no sandboxes/PVCs/PVs or qualification namespaces. Identity-checked kind-down exited0; original CID `89185888acdeae13f67cf755ce5dd4b80e32c8eacb0e35702ec31a5066ff3f74` independently absent. Owner/kubeconfig/gateway private state absent; no owned runtime remains. All three preexisting unrelated stopped container identities remain. The first read-only post-cleanup audit used running-only inventory; correcting to `docker ps -a` repeated no mutation.
- JSPWiki: new complete private bare acquisition at exact fix `88d89d6523802c044cfcb7930cba40d8eeb21da2` and parent `f140a2a4371735ad24d04a1d78c6e1d9ceaed76f`; strict native object checks passed. Initial DNS failure is retained separately. Existing GitSource/LocalArtifacts captured both full trees once in6.052/6.168s under2048-file/4MiB-file/20MiB-total/60s-wall/512MiB/30s-CPU limits. Fresh independent store readback and root audit verified both manifests and all3447 file references;25 affected unit tests passed/1.17s. No checkout/build/project code was executed.
- [Native two-test draft](../../../benchmarks/cases/jspwiki-forwarding/README.md): SHA256 `6ebf62443a54fc98b0d3f3680d4aa0fde239888db10bc8b5158026faa369b95d`, independently reviewed with exact Stripes mock source and upstream source identities. Apache LICENSE/NOTICE bytes are preserved. Tests observe real servlet dispatcher choice, not target execution/file disclosure. Compilation, native discovery and assertions are unrun. Keep evaluator-only labels/tests outside blind agent inputs; current agent source tools do not load this directory.

All private evidence is under `.runs/post-pr21-qualification-20261012/`. Key entries: `runtime-source-v1.json`, `temporal-001`, `temporal-restart-001`, `node-001-*`, `runtime-review/*audit.md`, `source-admission/jspwiki/capture-001`, complete-bare acquisition receipts, and `test-draft/`. Source manifest hashes and actual artifact paths are in the reviewed case README and private capture result. No private logs/state/credentials are intended for publication.

## Decisions and next steps

Keep PLAN-0022's broad live step open. Other changed OpenShell consumers still need source-bound renewal on two fresh nodes, including recovery/OOM, policy/toolchains, execution/output/receipt/transport and fixed source/file/report recipes. The one-node lifecycle canary establishes actual acceptance of the changed wire fields; it does not renew those scopes automatically.

For PLAN-0021, source acquisition/local capture and reviewed draft bytes are complete. Next select and review one concrete confined dependency-preparation/source/test/report route for the unchanged JSPWiki reactor. The existing Java17/Maven image cache contains only different synthetic dependencies; historical parent/BOM/plugin/transitive closure and Java17 compatibility remain unknown. The full captured tree is larger than the previously qualified five-file upload, and the approved test patch is nonempty. The private `concrete-recipe-proposal.md` describes alternatives, not an admitted design. Do not execute Maven/plugins on the host, silently extend synthetic admission, modify upstream POM pins, weaken policy/TLS/kernel requirements or add live dependency-network fallback.

Use native Maven resolution and JUnit APIs after the concrete recipe passes review/admission. A proposed separate JUnit Platform1.4.0 Launcher.discover probe is retained privately; it requires its own pinned launcher/classpath and confinement because discovery loads classes. It has not been compiled/run. Then execute exactly the same two tests three times per revision, retaining native XML, non-null forward-target witnesses, budgets and identity cleanup. Failed control/setup, skipped discovery, incomplete report, denial or unknown execution is never proof of a fix. Preserve all failed/uncertain attempts and add no generic repair runner or scheduler.

Existing authorization includes implementation/testing and periodic tracked commits/pushes. No new permission is required for those tasks. Keep root as the runtime owner and Sol lanes independent. ISSUE-0007's earlier anchored reviewer failures/unknown weights identity remain unchanged; the native provider must be requalified before real-model composition.

## Continuation prompt

```text
Read AGENTS.md, README.md, docs/development/CURRENT.md, Corsair development/review/handoff skills, HANDOFF-0034, PLAN-0021/0022 and ISSUE-0006/0007. Verify branch, remote/source state and retained raw evidence; preserve unrelated work. Review the exact captured JSPWiki source and frozen evaluator-only two-test draft. Choose one bounded native dependency/build/source/test/report recipe and close its admission gaps without host project execution or policy/pin weakening. Fresh storage/kernel/CNI/gateway admission is mandatory before any new workload. Do not treat the one-node lifecycle canary or synthetic Java cache as general admission. Native discover and execute both tests three times per source only after the concrete gate passes; retain witnesses/failures/budgets and identity cleanup. Continue independent affected runtime requalification as useful, with one owner. ISSUE-0007 still blocks real-provider integration. Run proportionate checks, independently review, update reports/plans/CURRENT and append a new handoff before stopping; commit/push tracked work within existing authorization.
```
