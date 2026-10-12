# Bounded test-observation report consumer

[Scope](../development/specs/SPEC-0017-bounded-test-report-consumer.md) and [plan](../development/plans/PLAN-0019-bounded-test-report-consumer.md) define one finite UTF8 JSON consumer. It accepts an operator-selected immutable stdout artifact only when a matching host execution receipt acknowledges terminal completion, worker cleanup and retained receipt storage. Exact bytes, operation, sandbox handle and source/test identities are bound independently of workload claims.

The schema has exactly two named claims, control and security, and no finding/fix disposition. Unknown fields, duplicate JSON keys, unsupported versions, malformed/oversized bytes and identity mismatches are refused. A skipped/failed control remains visible and cannot prove an application fix. Digest agreement establishes byte integrity, not that an untrusted runner performed the test it claims.

Host checks use actual LocalArtifacts with simulated host execution receipts:26 passed in0.32s, including a distinct process rereading persisted original artifact bytes and operator metadata. Initial native-case collection failed because the serialized receipt helper was imported from the wrong module; corrected collection found one case in0.06s. These attempts are retained privately under `.runs/four-priorities-20261012/root`.

The independent live case uses an inert literal JSON producer inside OpenShell, native exits0 and1, existing execution/immutable artifact adapters and this consumer. It runs under the OpenShell lane's exclusive cluster ownership with a separate evidence root from receipt-recovery checks. The selected OpenShell0.1.3/Agent Sandbox1.0.6/runtime tuple, TLS, policy, kernel requirements and native readiness default remain unchanged. Host execution retains the 4096-byte, 2-second native, 20-second host, 512MiB, one-CPU, glibc2.39/two-arena envelope.

| Fresh node | Mandatory admission / CNI | Literal producer / consumer | Cleanup |
| --- | --- | --- | --- |
| 001 | 1 pass/102.86s; 3 passes/155.46s | 1 pass/98.48s; two377-byte reports, exits0/1 | Original sandbox, tasks, workers, gateway/forward/private files/PVC/PV and cluster confirmed absent |
| 002 | 1 pass/102.26s; 3 passes/159.46s | 1 pass/94.93s; two377-byte reports, exits0/1 | Original sandbox, tasks, workers, gateway/forward/private files/PVC/PV and cluster confirmed absent |

Both passing report cases used the same corrected source-v3:77 frozen runtime/fixture/policy/dependency inputs, manifest SHA256 `f911e0c79356bbc5af0bc6fa594ba7ad384cd75f79be5a0d72ad7c92aee9f219`. The native report fixture import is the sole difference from the retained v2 manifest used by the independent first-node receipt matrix. Subsequent docs/test-selection edits are not represented as these frozen runtime bytes. Original node001 container was `3cbe091291319af580d624d3716f17e8476ceecd41b7133cbdf5e97593cea7f3`; its final inventory was empty and native inspect confirmed that exact container absent.

Failures remain attributable: the first standalone launcher omitted the repository UV cache and failed before pytest; the next reached six read-only preflight queries and failed missing gateway fixture registration before any report execution. Registering the native gateway fixture corrected the test selection. `node-001/report-003` is the actual passing attempt; neither earlier destination was overwritten. Original owned gateway identity was retained across the preparation failures. A later root-independent cleanup-audit assertion expected uppercase text, whereas the native absence error was lowercase; the actual original-container absence receipt, failed audit and correction remain retained.

Private evidence is `.runs/four-priorities-20261012/openshell-agent/node-001/report-003` and `node-002/report` under the same lane. Root independently checked original operation/sandbox identity, exact stdout bytes/hash/artifact size, source/test digests, native exits, typed claims and absent original worker PIDs. The actual immutable artifact was reread after sandbox deletion. SDK-method counts are retained; internal SDK/RPC retries remain unknown, and application retries are zero.

This qualifies no application tests, real discovery, agent assessment, security reproduction, fix verification, arbitrary files or archive extraction. The only admitted content is the fixed literal workload claim and its independently checked host binding; a matching digest is not evidence of test semantics.

Original node002 container was `3ff4ee0ae5272305622fded4426df8044aab05823277b3c80d171886af95241d`; its empty final inventory and native exact-container absence were independently audited. Both JUnit results have zero failures/skips. The two-node bounded composition is qualified within the stated literal-claim envelope.

Final review removed the new case’s shared `execution_artifacts` marker: that old target otherwise selected two function-scoped gateway cases into one evidence root. Explicit-file live runs above were unaffected. After this selector-only correction, the old target collects exactly its original one case, and the explicit report file collects one case with both native gateway fixtures registered. `Makefile` also adds the five offline Temporal composition checks. These two post-live selector differences are recorded separately from the exact77-input freeze; no runtime logic changed and no live rerun was needed.

After fresh mandatory admission, CNI qualification and a separately installed owned gateway, select only this file with a new evidence directory:

```bash
test -n "$CORSAIR_QUAL_RUN" && test ! -e "$CORSAIR_QUAL_RUN" && \
UV_CACHE_DIR="$PWD/.cache/uv" uv run --locked python -m pytest \
  tests/qualification/test_test_report.py \
  --kubeconfig .state/kind/kubeconfig --context kind-corsair \
  --network-evidence "$CORSAIR_NETWORK_RUN" \
  --evidence-dir "$CORSAIR_QUAL_RUN" --junitxml "$CORSAIR_QUAL_RUN/junit.xml"
```

Never reuse an evidence root or a gateway namespace cleaned by an earlier function-scoped case.

## Test-pair audit (2026-10-12)

Independent Sol/root review confirmed that the current producer stores inert source/test identities and prints literal claims with selected exits. It does not draft tests, perform pytest/JUnit discovery, call a target application or verify security assertions. Infrastructure toolchain roundtrips are also distinct from finding-specific tests. The consumer intentionally retains failed/skipped claims without a finding/fix disposition; no semantic validity follows from admission.

The next application boundary must implement the [investigation contract](../investigation-contract.md#the-two-tests): one reviewed frozen two-test patch on immutable vulnerable/fixed component fixtures. Native collection must discover exactly the intended benign control and security regression. Both invoke the real implementation and have bounded observable witnesses. The control passes on both revisions; the security regression asserts safe behavior, fails for the expected security assertion on the vulnerable baseline and passes on the corrected revision. Preserve fresh individual outcomes, source/test identities and application versus sandbox observations. Skips, setup/build failures, failed controls, incomplete delivery and boundary denials cannot verify safety. Agent-authored test drafting and its independent semantic review remain unimplemented/unqualified; this audit does not promote literal report claims to execution evidence.
