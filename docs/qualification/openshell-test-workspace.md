# OpenShell test workspace qualification

Scope: [SPEC-0032](../development/specs/SPEC-0032-openshell-test-workspace.md) adapter delivering the reviewed [SPEC-0018](../development/specs/SPEC-0018-native-two-test-fixture.md) pair (captured `documents.py` per variant plus the unchanged `test_documents.py` as the approved patch) into fresh OpenShell sandboxes and running it through the real `PytestRunner`. Fixture delivery and execution only: no model-authored patch, real repository, dependency setup, witness or security disposition is qualified.

## Run

2026-10-12 on RIG0, one fresh kind node, from a separate worktree at PR head `aca85a4` (main's checkout untouched; nothing committed or pushed there). Every command exited 0: `make test-config` (766 passed), `make kind-up` (152 s; Calico rolled out without retry), `make qualify-network` (3 passed), `make admission-artifacts`, `make admission-install`, `make qualify-admission` (1 passed), `make openshell-install`, `make toolchain-images` (cached layers; tag `corsair-python:292b60293b3845ef`, trusted control passed), `make toolchain-images-load` (`corsair-python@sha256:6be471eb…968d`), `make qualify-test-workspace` (149 s), `make kind-down` (no kind cluster and no `corsair-control-plane` container remain).

## Results

JUnit: 1 test, 0 failures, errors or skips (148.6 s). Four fresh sandboxes, two per variant. In every run: `failure_layer` null, cleanup confirmed, no Sandbox resource or boundary pod left, discovery exit 0 finding exactly `test_documents.py::test_benign_control` and `test_documents.py::test_security_rejects_outside_read`, execution completed, control passed.

| Variant | Run | Execution exit | Security | Elapsed |
| --- | --- | --- | --- | --- |
| vulnerable | 1 | 1 | failed: `AssertionError` at `test_documents.py:64` in `test_security_rejects_outside_read` ("security assertion: application opened the outside fixture") | 11.7 s |
| vulnerable | 2 | 1 | failed, same frame and message | 8.9 s |
| fixed | 1 | 0 | passed | 9.1 s |
| fixed | 2 | 0 | passed | 9.1 s |

Summary fields: outcome passed, application retries 0, native internal attempts unknown, witness absent (JUnit and captured output are workload claims), host staging empty. Gateway cleanup confirmed namespace, PV, private state and port-forward (exit -15). Nothing failed, so there were no reruns.

## Evidence and limits

Private evidence stays git-ignored on RIG0 under `/home/al/git/corsair-pr31/.runs/` (`test-workspace-20261012T233548/`, network and admission runs, command logs in `pr31-qual/`); TLS exports are not shared. One node only, not two; the upload's native internal retries remain unobserved; delivery is bounded to the fixture envelope and general source still waits on SPEC-0025 and ISSUE-0006.
