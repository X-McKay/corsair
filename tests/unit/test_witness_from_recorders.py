"""SPEC-0073: without a per-case envelope, the operator's recorders for the selected framework bind the witness
request to the admitted identification target and the plan's subject; offline."""
from types import SimpleNamespace

import pytest

from corsair.agents.test_planning.contracts import PlannedWitness, WitnessFacility
from corsair.composition.evidence import witness_request
from corsair.investigation.frameworks import harness
from corsair.ports.test_runner import WitnessRequest

# Only the admitted identification's status and target reach the request.
READY = SimpleNamespace(status="ready", target=SimpleNamespace(symbol="read_doc", source=SimpleNamespace(path="app.py")))
AUDIT = harness("pytest").witness_facilities


def planned(**changes):
    return PlannedWitness.model_validate({"facility": "audit_open", "effect": "file_open", "subject": "outside.txt",
                                          "expectation": "absent"} | changes)


def test_the_tables_recorder_binds_the_identified_target_and_the_planned_subject():
    assert witness_request(READY, None, planned(), AUDIT) == WitnessRequest("app.py", "read_doc", "outside.txt")


@pytest.mark.parametrize("witness, recorders, reason", [
    (planned(), (), "approved no witness envelope"),
    (planned(facility="other"), AUDIT, "names no operator recorder"),
    (planned(subject="nested/outside.txt"), AUDIT, "not a plain file name"),
])
def test_a_request_the_rules_do_not_cover_is_refused(witness, recorders, reason):
    with pytest.raises(ValueError, match=reason):
        witness_request(READY, None, witness, recorders)


def test_a_recorder_kind_the_probe_does_not_record_is_refused():
    spawn = (WitnessFacility(id="spawn", kind="process_start", description="Recorded process starts"),)
    with pytest.raises(ValueError, match="not recorded by the operator probe"):
        witness_request(READY, None, planned(facility="spawn", effect="process_start", subject="zip"), spawn)


def test_an_operator_envelope_still_wins_and_still_binds_its_own_target():
    envelope = WitnessRequest("app.py", "read_doc", "outside.txt")
    assert witness_request(READY, envelope, planned(), AUDIT) is envelope
    with pytest.raises(ValueError, match="outside the operator witness envelope"):
        witness_request(READY, WitnessRequest("other.py", "read_doc", "outside.txt"), planned(), AUDIT)
