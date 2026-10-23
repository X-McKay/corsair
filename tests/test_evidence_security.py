"""Hard invariants fail before an audit or a successful verdict."""

import json
from pathlib import Path

import pytest

from corsair.adapters.artifacts.filesystem import ArtifactStore
from corsair.adapters.frameworks import framework
from corsair.adapters.frameworks.pytest_ import Pytest, ast_guard, read_coverage
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel
from corsair.domain.verification import Gate, Outcome, Submission
from corsair.runtime.matrix import load
from tests.fakes import JUNIT_PASS, FakeSandboxes, Script

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/path-traversal-fixture"
REFERENCE = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
PREFIX = "CONTROL_PAYLOAD = 1\nEXPLOIT_PAYLOAD = 2\n"


@pytest.mark.parametrize(
    "code",
    [
        "def outer():\n    CONTROL_PAYLOAD=1\n    EXPLOIT_PAYLOAD=2\n    def run_target(p): pass\n",
        PREFIX + "async def run_target(p): pass\n",
        PREFIX + "def run_target(p, **kw): pass\n",
        PREFIX + "def run_target(p=1): pass\n",
        PREFIX + "def run_target(p): pass\ndef run_target(p): pass\n",
        PREFIX + "def run_target(p): pass\nCONTROL_PAYLOAD=3\n",
        PREFIX + "def run_target(p): pass\ndel EXPLOIT_PAYLOAD\n",
        PREFIX + "def run_target(p):\n    if p == EXPLOIT_PAYLOAD: assert p\n",
        PREFIX + "def run_target(p): assert True\n",
        "from unittest import mock as m\n" + PREFIX + "def run_target(p): pass\n",
        PREFIX + "run_target = lambda p: None\n",
        PREFIX + "@staticmethod\ndef run_target(p): pass\n",
    ],
)
def test_unfair_or_ambiguous_probe_is_rejected(code):
    assert not ast_guard(code).passed


def test_positional_only_payload_is_supported():
    assert ast_guard(PREFIX + "def run_target(p, /): assert p > 0\n").passed


@pytest.mark.parametrize(
    "path",
    ["/other/documents.py", "/work/evil_documents.py", "other/documents.py", "/work/../work/documents.py"],
)
def test_coverage_cannot_bind_to_a_suffix_or_traversal(path):
    data = json.dumps({"files": {path: {"executed_lines": [4]}}}).encode()
    assert read_coverage(data, REFERENCE.hypothesis)[1] == ()


@pytest.mark.parametrize(
    "data",
    [
        b"null",
        b"[]",
        b"{}",
        b"{",
        b'{"files":null}',
        b'{"files":{"documents.py":{"executed_lines":[true]}}}',
        b'{"files":{"documents.py":{"executed_lines":["4"]}}}',
        b'{"files":{"documents.py":{"executed_lines":[-1]}}}',
    ],
)
def test_malformed_coverage_is_not_evidence(data):
    assert read_coverage(data, REFERENCE.hypothesis)[1] == ()


def test_duplicate_normalized_target_entries_are_ambiguous():
    data = json.dumps(
        {"files": {"documents.py": {"executed_lines": [4]}, "/work/documents.py": {"executed_lines": [4]}}}
    ).encode()
    assert read_coverage(data, REFERENCE.hypothesis)[1] == ()


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"outcome": "holds", "role": "invalid"},
        {"outcome": "violated", "role": "control", "raised_in_probe": False},
    ],
)
def test_invalid_driver_record_is_errored(record):
    files = {
        "/tmp/corsair/result.json": json.dumps(record).encode(),
        "/tmp/corsair/junit.xml": JUNIT_PASS.format(role="control").encode(),
    }
    assert Pytest().read(files, REFERENCE.hypothesis).outcome is Outcome.ERRORED


@pytest.mark.anyio
async def test_every_requested_line_is_required_before_audit(tmp_path):
    called = []

    async def audit(submission):
        called.append(submission)
        raise AssertionError("must not be invoked")

    fake = FakeSandboxes({("vulnerable", "control"): Script("holds", covered_lines=(4,))})
    sub = REFERENCE.model_copy(
        update={"hypothesis": REFERENCE.hypothesis.model_copy(update={"target_lines": (4, 5)})}
    )
    kernel = Kernel(
        fake,
        load()[0],
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path),
        auditor=audit,
        framework=framework(load()[0].framework),
    )
    result = await kernel.evaluate(sub)
    assert result.gate.stage is Gate.CONTROL_COVERAGE and not called


@pytest.mark.anyio
async def test_changed_source_is_not_reused_from_an_old_revision(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "documents.py").write_text("def read_document(p):\n    return p\n")
    request = tmp_path / "input.json"
    request.write_text(json.dumps({"source": "source", "finding": {"title": "t"}}))
    case = load_case(request)
    (source / "documents.py").write_text("def read_document(p):\n    return 0\n")
    fake = FakeSandboxes({})
    k = Kernel(
        fake,
        load()[0],
        case,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        framework=framework(load()[0].framework),
    )
    _, gate = k.build(case.revision, "vulnerable", "")
    assert gate.stage is Gate.INFRA and not fake.creates


@pytest.mark.parametrize(
    "data",
    [
        b'{"files":{"documents.py":{"executed_lines":[4]}},"files":{"documents.py":{"executed_lines":[4]}}}',
        b'{"files":{"documents.py":{"executed_lines":[],"executed_lines":[4]}}}',
        b'{"files":{"documents.py":{"executed_lines":[4]}},"extra":NaN}',
    ],
)
def test_duplicate_or_nonfinite_json_is_never_target_evidence(data):
    assert read_coverage(data, REFERENCE.hypothesis) == (None, ())
