# Reviewed native two-test fixture

This manually drafted, evaluator-only fixture executes the same two tests against the existing synthetic issue-analysis source variants. It is not one of the50 real-project candidates and is not model-authored test qualification. Variant names, expected results and witnesses stay outside future agent-visible inputs.

`test_documents.py` uses native pytest and Python file-open audit events, without mocking the target or sink. `documents.py` is the actual target under test. Each test creates fresh allowed/outside sentinel files under pytest scratch. The control must read the allowed file. The security regression asserts rejection before the outside file is opened; only the reviewed confinement ValueError is accepted. Audit events are meaningful for these two reviewed Python implementations, not independent OS attestation for arbitrary untrusted code.

Use the locked Python3.12/pytest9.0.2 environment. Copy one source variant and the unchanged test into a fresh private workspace; freeze and verify both byte hashes. In that workspace, with absolute interpreter and evidence paths:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
  /absolute/corsair/.venv/bin/python -m pytest -c /dev/null --noconftest \
  --import-mode=importlib -p no:cacheprovider test_documents.py --collect-only -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" \
  /absolute/corsair/.venv/bin/python -m pytest -c /dev/null --noconftest \
  --import-mode=importlib -p no:cacheprovider test_documents.py -q \
  --basetemp "$PWD/scratch" --junitxml /absolute/new-evidence/junit.xml \
  -o junit_logging=all -o junit_log_passing_tests=true
```

Collection must discover exactly `test_benign_control` and `test_security_rejects_outside_read`. Execution exits1 for vulnerable with one **specific outside-open security assertion failure**, and0 for fixed with two passes. Errors, skips, unrelated failures and missing witnesses are not expected outcomes. Capture command/stdout/stderr/exit/time, native JUnit, input hashes and workspace identity. Repeat three times with fresh workspaces, then identity-check cleanup. Preserve immutable source/test copies and receipts outside Git.

This explicitly local, reviewed scratch-only qualification starts no network, service, model or OpenShell runtime. Never reuse it as permission to run downloaded benchmark workloads on the host. See [qualification](../../../docs/qualification/native-two-test-fixture.md) and [SPEC-0018](../../../docs/development/specs/SPEC-0018-native-two-test-fixture.md).
