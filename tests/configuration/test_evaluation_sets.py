"""SPEC-0035/SPEC-0023 dataset guards: oracle gates track assess(), regeneration is exact, held-out cases stay sealed."""
import json
from pathlib import Path
import re

from corsair.core.disposition import assess
from evals.evidence_assessment import build
from evals.evidence_assessment.evaluate import CASES, HELD_OUT, case_digest, load

ROOT = Path(__file__).resolve().parents[2]


def test_every_oracle_gate_is_what_the_gates_permit():
    for case in load().cases:
        assert assess(case.inputs.evidence).permitted == case.metadata.gate, case.name


def test_builder_regenerates_the_committed_cases_byte_for_byte(tmp_path):
    build.write(tmp_path / "cases.yaml")
    assert (tmp_path / "cases.yaml").read_bytes() == CASES.read_bytes()


def test_held_out_cases_match_their_manifest():
    held_out = {case.name: case_digest(case) for case in load().cases if case.metadata.split == "held_out"}
    assert held_out and held_out == json.loads(HELD_OUT.read_text())


def test_development_records_never_cite_a_held_out_case():
    names = re.compile(r"\b(" + "|".join(map(re.escape, json.loads(HELD_OUT.read_text()))) + r")\b")
    cited = [str(path) for path in (ROOT / "docs/development").rglob("*") if path.is_file()
             and names.search(path.read_text(errors="replace"))]
    assert not cited
