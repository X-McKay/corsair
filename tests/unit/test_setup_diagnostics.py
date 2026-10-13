"""Failure attribution and actionable guidance over real port receipt shapes (no native execution)."""
from dataclasses import replace
import pytest
from corsair.agents.environment.diagnostics import setup_blocker
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle

BASE = ExecutionReceipt(operation="op", handle=SandboxHandle(id="id", name="name", workspace="w", owner="owner", creation_operation="create"),
                        started_at="now", elapsed_seconds=1, delivery="acknowledged", completion="terminal_observed", reason="terminal", native_exit=1)

@pytest.mark.parametrize("output,code", [
    (b"ERROR: No matching distribution found for missing-package==7.1", "dependency_resolution"),
    (b"Could not find artifact example:missing:jar:1.0", "dependency_resolution"),
    (b"PKIX path building failed", "tls_trust"),
    (b"403 Forbidden https://user:SECRET@private.example/path?token=SECRET", "registry_access"),
    (b"Could not resolve host: registry.example", "connectivity"),
    (b"Connection timed out", "connectivity"),
    (b"No space left on device", "storage_capacity"),
    (b"compilation error", "setup_command_failed"),
])
def test_reported_symptom_keeps_private_details_in_referenced_receipt(output, code):
    diagnostic = setup_blocker(replace(BASE, stderr=output), 3, None)
    assert diagnostic.code == code and diagnostic.evidence and diagnostic.actions
    assert diagnostic.certainty in ("reported", "unknown")
    assert "SECRET" not in diagnostic.model_dump_json() and "private.example" not in diagnostic.render()
    assert "policy_denied" not in diagnostic.code


def test_success_text_does_not_create_failure_and_transport_overrides_package_text():
    text = b"No matching distribution found"
    assert setup_blocker(replace(BASE, native_exit=0, stderr=text), 1, None) is None
    uncertain = replace(BASE, delivery="unknown", completion="unknown", stderr=text)
    assert setup_blocker(uncertain, 1, "stream lost").code == "execution_unknown"
    assert "Do not resend" in setup_blocker(uncertain, 1, "stream lost").render()

@pytest.mark.parametrize("change,code", [
    ({"storage_error": "journal failed", "native_exit": 0}, "receipt_storage"),
    ({"worker_cleanup": "unconfirmed"}, "cleanup_unconfirmed"),
    ({"failure_layer": "output_budget", "completion": "unknown"}, "output_limit"),
    ({"delivery": "not_dispatched", "completion": "unknown"}, "execution_not_dispatched"),
    ({"native_exit": None}, "execution_failure"),
])
def test_native_boundary_facts_take_precedence(change, code):
    assert setup_blocker(replace(BASE, **change), 1, None).code == code
