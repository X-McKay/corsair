"""Real-Docker replay of mismatching producer proposals on the frozen case01 request."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import ProducerDecision, ProducerOutput, Submission
from corsair.evaluation.replay import replay_candidates
from corsair.settings import Settings
from tests.integration import test_docker
from tests.integration.test_docker import _assert_cleanup, _docker_client
from tests.unit.test_replay import DATASET, ROOT, UNLISTED, _report

pytestmark = pytest.mark.docker
# The Docker suite's session-unique operation ids and leaked-sandbox sweep.
session_operation = test_docker.session_operation

FROZEN = ROOT / "evals/fixtures/case01/submission.json"


def _proposal(**payloads: object) -> ProducerOutput:
    frozen = Submission.model_validate_json(FROZEN.read_bytes())
    submission = frozen.model_copy(update=payloads)
    return ProducerOutput(decision=ProducerDecision(kind="proposal", submission=submission))


async def test_real_docker_replay_separates_demonstrating_from_non_demonstrating_candidates(
    tmp_path: Path, session_operation: Callable[[str], str]
) -> None:
    client = _docker_client()
    settings = Settings(source_root=str(ROOT), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    report = _report(
        settings,
        store,
        _proposal(),  # the frozen reference pair: an exact match, never replayed
        _proposal(exploit_payload=UNLISTED),  # an unlisted equivalent traversal
        _proposal(exploit_payload="hello.txt"),  # a benign "exploit"
    )
    oracle_before = (ROOT / "evals/fixtures/case01/producer-oracle.json").read_bytes()
    replay_id = session_operation("replay-case01")

    replayed = await replay_candidates(
        report, DATASET, settings, store, DockerSandbox(settings, store=store), replay_id=replay_id
    )

    exact, unlisted, benign = (row["replay"] for row in replayed["rows"])
    assert [row["match_kind"] for row in replayed["rows"]] == [
        "exact_match",
        "candidate_exact_mismatch",
        "candidate_exact_mismatch",
    ]
    assert [row["status"] for row in replayed["rows"]] == ["pass", "fail", "fail"]
    assert exact is None
    assert unlisted["status"] == "demonstrated", json.dumps(unlisted)
    assert (unlisted["control"], unlisted["adversarial"], unlisted["covered"]) == (
        "PROPERTY_HELD",
        "VIOLATION",
        True,
    )
    assert benign["status"] == "not_demonstrated", json.dumps(benign)
    assert (benign["control"], benign["adversarial"], benign["covered"]) == (
        "PROPERTY_HELD",
        "PROPERTY_HELD",
        True,
    )
    for entry in (unlisted, benign):
        assert entry["cleanup_confirmed"] is True
        assert entry["operation_id"].startswith(f"{replay_id}.c")
        _assert_cleanup(client, entry["operation_id"])
    assert replayed["summary"]["replay"] == {
        "demonstrated": 1,
        "not_demonstrated": 1,
        "unavailable": 0,
        "not_replayed": 1,
    }
    assert (ROOT / "evals/fixtures/case01/producer-oracle.json").read_bytes() == oracle_before
