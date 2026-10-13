"""Live run 2 (2026-10-13) replayed on the host: real pytest, the real witness probe and the real gate.

The first test file is what the live author wrote; it re-reads the outside file after the call, which a read
never changes, so it cannot tell the revisions apart. The second is the shape the authoring skill now asks
for under the same no_file_open plan: catch around the planned call and assert on what it returned. Both are
repository-owned bytes here; model-authored code never runs on the host.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

import pytest

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.composition.evidence import run_evidence
from corsair.core.disposition import (AssessmentEvidence, EnvironmentIdentity, ExpectedFailure, ObservationPlan,
                                      assess)
from corsair.nodes.witness import witness_evidence
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import ApprovedPatch, PatchFile, PreparedWorkspace, WitnessRequest
from evals.fixture_e2e.reviewed import DISCOVER, FIXTURE, PREFIX, ReviewedLocalExecution

PATH = 'test_documents.py'
LIVE_RUN_2 = '''from pathlib import Path

import documents


def test_reads_benign_document(tmp_path: Path):
    (tmp_path / "allowed").mkdir()
    (tmp_path / "allowed" / "note.txt").write_text("hello")
    assert documents.read_document(tmp_path / "allowed", "note.txt") == "hello"


def test_rejects_path_traversal(tmp_path: Path):
    (tmp_path / "allowed").mkdir()
    (tmp_path / "outside.txt").write_text("outside")
    documents.read_document(tmp_path / "allowed", "../outside.txt")
    assert (tmp_path / "outside.txt").read_text() == "outside"
'''
RETURNED_VALUE = '''from pathlib import Path

import documents


def test_reads_benign_document(tmp_path: Path):
    (tmp_path / "allowed").mkdir()
    (tmp_path / "allowed" / "note.txt").write_text("hello")
    assert documents.read_document(tmp_path / "allowed", "note.txt") == "hello"


def test_rejects_path_traversal(tmp_path: Path):
    (tmp_path / "allowed").mkdir()
    (tmp_path / "outside.txt").write_text("outside")
    assert (tmp_path / "outside.txt").read_text() == "outside"
    try:
        returned = documents.read_document(tmp_path / "allowed", "../outside.txt")
    except Exception:
        returned = None
    assert returned != "outside"
'''
IDS = (f'{PATH}::test_reads_benign_document', f'{PATH}::test_rejects_path_traversal')
REQUEST = WitnessRequest('documents.py', 'read_document', 'outside.txt')
ENV = EnvironmentIdentity(**{key: sha256(key.encode()).hexdigest() for key in (
    'image_digest', 'recipe_sha256', 'dependency_inventory_sha256', 'limits_sha256')}, policy_revision='host')


@dataclass
class Workspace:
    """One fixture variant plus the given repository-owned test bytes in a private directory."""
    store: LocalArtifacts
    root: object
    variant: str
    tests: bytes

    def prepare(self, patch, operation):
        assert [(f.path, f.content) for f in patch.files] == [(PATH, self.tests)]
        source = (FIXTURE / self.variant / 'documents.py').read_bytes()
        self.root.mkdir(mode=0o700)
        (self.root / 'documents.py').write_bytes(source)
        (self.root / PATH).write_bytes(self.tests)
        handle = SandboxHandle(str(uuid4()), 'host', 'local', 'tests', str(operation))
        return PreparedWorkspace(handle, self.store.put(source), self.store.put(self.tests), patch.sha256)

    def release(self, workspace, operation):
        return 'confirmed'


def gate(tmp_path, tests: str, assertion_lines: tuple[int, ...]):
    content = tests.encode()
    patch = ApprovedPatch((PatchFile(PATH, content),), (PATH,))
    plan = ObservationPlan(control_test_id=IDS[0], security_test_id=IDS[1],
                           expected_failure=ExpectedFailure(exception_type='AssertionError', path=PATH,
                                                            function='test_rejects_path_traversal',
                                                            assertion_lines=assertion_lines),
                           expected_safe_behavior='no_file_open', frozen_patch_sha256=patch.sha256)
    (tmp_path / 'objects').mkdir(mode=0o700)
    runs = {}
    with LocalArtifacts(tmp_path / 'objects', max_bytes=1024 * 1024) as store:
        for revision, variant in (('baseline', 'vulnerable'), ('candidate', 'fixed')):
            root = (tmp_path / revision).resolve()
            runner = PytestRunner(Workspace(store, root, variant, content), ReviewedLocalExecution(root), store,
                                  PytestRunnerConfig(PREFIX, '.corsair-junit.xml', str(root),
                                                     witness_record_path=str(tmp_path / f'{revision}-witness.json')))
            observed = runner.run(patch, control_test_id=IDS[0], security_test_id=IDS[1], discovery_command=DISCOVER,
                                  operation=uuid4(), witness=REQUEST)
            # As the chain does: an absence is the planned safe behavior only on the candidate.
            found = witness_evidence(observed.witness, REQUEST, IDS[1], planned_safe_behavior=(
                'no_file_open' if revision == 'candidate' else None))
            assert found.reason == 'admitted', found.reason
            runs[revision] = run_evidence(observed, environment=ENV, witness=found.witness,
                                          sandbox_events=found.sandbox_events)
    return assess(AssessmentEvidence(plan=plan, baseline=(runs['baseline'],), candidate=(runs['candidate'],)))


def triple(result):
    return result.permitted.finding, result.permitted.fix


def codes(result):
    return {(item.code, item.revision) for item in result.limitations}


def test_the_live_run_2_security_test_cannot_distinguish_and_says_so(tmp_path):
    result = gate(tmp_path, LIVE_RUN_2, (16,))
    assert triple(result) == ('inconclusive', 'not_verified')
    # Before this change: witness_missing (the test's own re-read was counted off-stack) and unplanned_failure.
    assert {('security_passed_with_effect', 'baseline'), ('security_failed_with_safe_witness', 'candidate')} <= codes(result)
    assert not {code for code, _ in codes(result)} & {'witness_missing', 'unplanned_failure'}


def test_asserting_on_the_returned_value_reproduces_and_verifies(tmp_path):
    result = gate(tmp_path, RETURNED_VALUE, (20,))
    assert triple(result) == ('reproduced', 'verified'), result.limitations
    assert [run.classification for run in result.runs] == ['reproduces', 'safe']


@pytest.mark.parametrize('tests, line', [(LIVE_RUN_2, 16), (RETURNED_VALUE, 20)])
def test_the_assertion_lines_are_the_security_asserts(tests, line):
    assert tests.splitlines()[line - 1].lstrip().startswith('assert ')
