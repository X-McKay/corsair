# Post-PR21 native qualification checkpoint

2026-10-12, source `afb75f3984f5a1453bd5dd57ba569ca12a1ab96d`, under [PLAN-0022](../development/plans/PLAN-0022-native-feature-adoption.md). This checkpoint renews the scripted native Temporal scope and exercises one fresh OpenShell node. It does **not** renew the complete historical two-node OpenShell matrix, admit JSPWiki execution, resolve ISSUE-0006/ISSUE-0007, or establish production readiness.

## Native Temporal

The pinned CLI1.9.1/service ran33 checks in6.39s with zero failures/errors/skips:19 offline, six native foundation and eight native issue-analysis cases. Twenty terminal histories were saved and replayed. Typed request/budget/model-key refusals, native activity retry limits, direct/durable output and usage agreement, and local trace attribution passed. A separate original pending parent/child resumed after graceful service restart using the same private SQLite, preserving both history prefixes, completing once and replaying. Both owned service processes exited0 after identity-checked SIGINT; their identities were absent and loopback ports17333/17334/17336 closed. The969 sandbox-import warnings remain retained.

The [foundation report](temporal-fixture-foundation.md) and [issue-analysis report](issue-analysis-temporal-fixture.md) record scope and measurements. This is scripted fixture qualification with newly recorded histories, not pre-PR21 history migration, crash recovery or real-provider durability.

## One fresh OpenShell canary

Root alone owned runtime mutations. Fresh node UID `03936973-0627-4b8e-b64d-3c3119ee6fdd` and container CID `89185888acdeae13f67cf755ce5dd4b80e32c8eacb0e35702ec31a5066ff3f74` were bound to the pinned kind/runtime inputs. A115-input runtime source freeze was retained before dispatch and reread afterward. Toolchain images were loaded by original immutable receipts; loading is not Java-project runtime qualification.

| Actual check | Result | Scope |
| --- | --- | --- |
| Storage and kernel admission | 1 passed /100.37s | Original PVC remount, native hard Landlock/seccomp/socket/DNS probes, original namespace/PV cleanup |
| CNI admission | 3 passed /160.18s | Actual ingress selection/rollback and egress deny/narrow allow |
| Native lifecycle | 1 passed /117.26s | Three actual SDK cycles; native execution and fixed trusted transfer controls |
| Lifecycle adapter | 1 passed /121.87s | Three actual create/Ready/delete cycles, forged-ID refusal, host intents/results and original resource cleanup |

Both lifecycle slices separately passed mandatory real gateway TLS/authentication, identity/configuration and access-isolation controls. Each used its own newly installed gateway because fixture teardown removes the gateway namespace, storage, private credentials/state and original forward. Zero JUnit failures/errors/skips occurred in these selected matrices. Expected negative-control diagnostics remain in native receipts.

Raw native create requests explicitly carry `SANDBOX_RESTART_POLICY_NEVER`, and actual sandboxes reach Ready. Adapter intent receipts bind operator limits; raw `wait_ready` and `wait_deleted` calls use300 and60 seconds. A helper returning the right enum or a rendered policy alone would not establish these observations. Independent Sol audits inspect native requests/results, original identities, refusals, cleanup and frozen source. Native SDK internal polls/retries remain unknown.

Private evidence is `.runs/post-pr21-qualification-20261012/`: `runtime-source-v1.json`, retained runtime bytes, `node-001-*` receipts/JUnit/logs and `runtime-review/` audits. Raw private diagnostics and runtime state stay outside Git. Before cluster deletion, native inventory showed no sandboxes/PVCs/PVs or qualification namespaces. Identity-checked `kind-down` exited0; a separate native inspection confirmed the original CID absent, owner/kubeconfig/gateway private state absent, and the three unrelated preexisting stopped container identities still present. The first read-only inventory audit incorrectly used running containers only; correcting it to `docker ps -a` required no repeated mutation. No owned runtime remains.

## Remaining scope

The one-node canary is not a replacement for the historical two-fresh-node evidence. Other changed consumers still need fresh source-bound qualification: recovery/OOM/gateway restart, readiness, policy/toolchains, adapter execution and its output/receipt/transport cases, fixed uploads/source execution, bounded untrusted files and test-report composition. Keep their older reports historical until the corresponding matrices are rerun. A successful lifecycle canary does not admit a larger source transfer, nonempty test patch or historical dependency cache.

The [JSPWiki draft](../../benchmarks/cases/jspwiki-forwarding/README.md) has separate exact local source captures and independently reviewed two-test bytes. Its native build/discovery/assertions remain unrun. The next case gate is a concrete confined historical dependency/build/source/test/report recipe; the existing synthetic Java cache and five-file empty-patch source fixture do not supply that admission.

Offline preflight passed363/6.23s. A later restricted-process run stopped progressing at the mocked provider transport test; its partial log was retained and only its verified PID/start identity was terminated (SIGINT then SIGTERM). The exact offline suite passed on the native host363/6.16s under a60s outer bound. The stalled process was confirmed absent; no live inference was dispatched, no test was weakened, and an unrelated older process was left untouched. The25 source/artifact unit checks separately passed/1.17s before actual source capture.
