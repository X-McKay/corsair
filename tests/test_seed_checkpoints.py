"""Proposal effects are absent; progressive evidence survives unsuccessful runs."""
import json

import pytest
from pydantic_ai.models.test import TestModel

from corsair.artifacts import write_json
from corsair.kernel import Gate, GateVerdict
from corsair.producer import SKILLS_DIR, investigate
from corsair.seed import optimize_skills_from_trace, propose_seed
from tests.fakes import FakeSandboxes
from tests.test_kernel import CASE, HAPPY, REFERENCE, ROW
from tests.test_producer_auditor import make_kernel, scripted
from corsair.case import load_case

pytestmark = pytest.mark.anyio

SEED = {"target_file": "app.py", "git_diff": "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x=1\n+x=2\n",
        "vulnerability_class": "boundary", "hint_prompt": "Check the boundary."}


async def test_seed_returns_one_file_diff_without_applying(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("x=1\n")
    proposal = await propose_seed(TestModel(custom_output_args=SEED), "app.py", source.read_text(), "boundary")
    assert proposal.git_diff == SEED["git_diff"] and source.read_text() == "x=1\n"


@pytest.mark.parametrize("update", [{"target_file": "other.py"},
                                    {"git_diff": SEED["git_diff"] + "--- a/other.py\n+++ b/other.py\n"},
                                    {"git_diff": "--- a/app.py\n+++ b/app.py\n"}])
async def test_seed_rejects_target_substitution_and_malformed_patch(update):
    with pytest.raises(ValueError):
        await propose_seed(TestModel(custom_output_args=SEED | update), "app.py", "x=1\n", "boundary")


async def test_short_or_failed_trace_has_no_optimizer_call():
    assert await optimize_skills_from_trace(None, "ERROR", [], SKILLS_DIR) is None
    assert await optimize_skills_from_trace(None, "LIKELY_EXPLOITABLE", [], SKILLS_DIR) is None


async def test_optimizer_proposes_existing_skill_without_editing_it():
    path = SKILLS_DIR / "differential-probing.md"
    before = path.read_bytes()
    rejection = GateVerdict(passed=False, stage=Gate.CONTROL_COVERAGE, reason="target missed")
    output = {"skill_file": path.name, "rationale": "Reach the real seam.",
              "markdown_append_block": "Call the real seam.\nCheck every claimed line.\nKeep payloads data."}
    proposal = await optimize_skills_from_trace(TestModel(custom_output_args=output), "LIKELY_EXPLOITABLE",
                                               [rejection, rejection], SKILLS_DIR)
    assert proposal.skill_file == path.name and path.read_bytes() == before


async def test_checkpoints_run_after_each_evaluation_and_outputs_are_artifacts(tmp_path):
    fake = FakeSandboxes(dict(HAPPY))
    observed = []
    model = scripted([[('bash', {'command': 'ls'})], [('submit', {'submission': REFERENCE.model_dump(mode='json')})],
                      ['Verified.']])
    run = await investigate(load_case(CASE), ROW, model=model, kernel=make_kernel(fake, tmp_path), backend=fake,
                            checkpoint=observed.append)
    assert tuple(observed) == run.evaluations
    assert len(run.observations) == 1 and run.observations[0]['duration_s'] >= 0
    assert run.observations[0]['stdout']['sha256']


@pytest.mark.parametrize("limits", [{"max_submissions": 0}, {"max_bash_calls": -1}, {"request_limit": 0},
                                    {"negative_threshold": 0}, {"total_tokens_limit": 0}])
async def test_invalid_budget_stops_before_creating_resources(tmp_path, limits):
    fake = FakeSandboxes({})
    with pytest.raises(ValueError):
        await investigate(load_case(CASE), ROW, model=None, kernel=make_kernel(fake, tmp_path), backend=fake, **limits)
    assert not fake.creates


def test_atomic_json_writer_leaves_no_partial_files(tmp_path):
    path = tmp_path / "nested" / "checkpoint.json"
    write_json(path, {"state": "running"})
    write_json(path, {"state": "finished"})
    assert json.loads(path.read_text()) == {"state": "finished"}
    assert list(path.parent.iterdir()) == [path]
