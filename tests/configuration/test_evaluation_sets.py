"""SPEC-0035/SPEC-0023 dataset guards: oracle gates track assess(), regeneration is exact."""
from corsair.core.disposition import assess
from evals.cases import EVALS
from evals.evidence_assessment import build
from evals.evidence_assessment.evaluate import load


def test_every_oracle_gate_is_what_the_gates_permit():
    for case in load().cases:
        assert assess(case.inputs.evidence).permitted == case.metadata.gate, case.name


def test_builder_regenerates_the_committed_cases_byte_for_byte(tmp_path):
    cases = build.write(tmp_path)
    for case in cases:
        for part in ("input", "oracle", "case"):
            relative = f"evidence_assessment/python/{case.metadata.split}/{case.name}/{part}.json"
            assert (tmp_path / relative).read_bytes() == (EVALS / relative).read_bytes(), relative
