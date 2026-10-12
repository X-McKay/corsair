# Native two-test fixture qualification

Date2026-10-12; [SPEC-0018](../development/specs/SPEC-0018-native-two-test-fixture.md), [PLAN-0020](../development/plans/PLAN-0020-native-two-test-fixture.md). This is manually drafted and independently reviewed native pytest code over the existing repository-owned synthetic path-traversal pair. It establishes a local fixture baseline for test semantics; it does not qualify model-authored drafts, any of the50 real-project candidates, OpenShell application execution or the complete investigation graph.

## Draft and execution evidence

The [single test artifact](../../benchmarks/fixtures/path-traversal/test_documents.py) has exactly two collected tests. Both invoke the real imported target. The control checks expected allowed content and its native Python open event. The security test first confirms outside scratch-file readability, then checks application confinement without mocking file access. Only the reviewed ValueError is accepted; absence of the outside open and of a return value is required. The outside sentinel is inside operator-owned scratch, never a host/private target.

Root drafted; Sol reviewed source and assertion semantics before execution. Five input files were frozen before dispatch and checked afterward: both source variants, the shared tests, pyproject and uv.lock. Python3.12.13 and pytest9.0.2 were observed. Six fresh workspaces each ran native collection followed by execution in separate pytest processes. Every source/test copy stayed byte-identical to its frozen input. Private `.runs/benchmark-admission-20261012/` retains commands, stdout/stderr, native JUnit, per-run receipts, source copies and summary; no raw evidence is published.

| Variant | Fresh runs | Control | Security safety assertion | Observed application effect |
| --- | --- | --- | --- | --- |
| Vulnerable | 3 | 3 passes | 3 expected failures, native exit1 | Outside fixture open and returned sentinel digest |
| Fixed | 3 | 3 passes | 3 passes, native exit0 | Confinement ValueError, no outside open or returned value |

Exactly2 tests discovered each time;12 individual outcomes total:9 passes and3 expected security failures, zero errors/skips. Summed native JUnit time0.199s; discovery plus execution command elapsed1.363421s. Timing is one tiny local sample, not a service SLO. All six original workspace device/inode identities were checked before cleanup, and absence was confirmed afterward. No service, cluster or external process persists.

Frozen SHA256 identities:

- Shared tests: `c9ce06213661ad5f9b97ac64ee7ade81895d7566e090d72837cecc7ff9f07673`.
- Vulnerable source: `c1cb3fcbf58038ebfee89ab28d1d310f88e92b0fd4951151d98c99259ca4d40d`.
- Fixed source: `87ef8e4536ced850e63035cff042c0e988efedc8993463a5005ddc346eaa9b7d`.
- Five-input manifest: `f75f6c904f6e2a0de7e5148f53d48cccdc3599c3dcf287a1973a0b18c769be6b`.

## Limits and retained failures

Native Python audit events are sufficient witnesses for these reviewed Path.read_text implementations; they are not complete OS telemetry or tamper-proof evidence for arbitrary repository code. No symlink/race/concurrency, deployed routing, stale-report rejection, arbitrary test-authoring robustness or sandbox-interference qualification follows. The two variants are source-byte identities, not asserted upstream vulnerable/fixed commits. The model semantic gate remains blocked under ISSUE-0007.

Initial record guards failed1/4 because new spec/plan template sections were missing; corrected guards passed4/0.03s before fixture dispatch. All expected vulnerable assertion failures remain retained. No runtime candidate was silently retried or source modified to obtain expected results. Use the [native recipe](../../benchmarks/fixtures/path-traversal/README.md); a future application disposition needs equivalent evidence for its own real source, reviewed test artifact and admitted runtime.

## Host pytest patch regression

On2026-10-12, PR1 was reconciled against merged foundation main `e2ea65888acb49a0839e463176d88db9eeda977e`. Python3.12.13/pytest9.0.3 ran the unchanged source variants and identical two-test artifact above in six new workspaces, three per source. Native discovery found exactly2 each time; controls6/6 passed, vulnerable security3/3 failed as expected with outside-open evidence, fixed security3/3 passed. No errors/skips; all six original workspace device/inode checks and subsequent absence checks passed. Private `.runs/pr-review-20261012/pytest-pair/` retains the new five-input freeze, separate discovery/execution outputs, JUnit, receipts and summary. Full offline suite passed255/5.80s with one existing event-loop deprecation warning. This host runner regression does not change the original pytest9.0.2 evidence or qualify real cases/OpenShell application execution.
