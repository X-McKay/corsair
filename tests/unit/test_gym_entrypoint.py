"""Gym runner pure parts: identity, tiers, task queues, content-addressed images, selection.

No Docker, Temporal or model is involved; the runner's service path is covered by
tests/integration/test_gym_runner.py.
"""

import json
import re
from pathlib import Path

import pytest

from corsair.contracts import validate_root_identity
from corsair.entrypoints import gym
from corsair.entrypoints.requests import load_investigation_request
from corsair.evaluation.datasets import load_dataset
from corsair.settings import TRANSPORT_FIELDS, ModelSettings, Settings
from corsair.steps.manifest import build_manifest

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "evals/datasets"
LANGUAGES = ("python", "javascript", "ruby", "java", "perl", "c")


# Identity


@pytest.mark.parametrize(
    "update",
    [
        {"temporal_address": "127.0.0.1:40123"},
        {"temporal_namespace": "corsair-gym"},
        {"task_queue": "gym-main-abcdef1"},
        {"artifact_root": "/elsewhere/.runs"},
        {"source_root": "/elsewhere"},
    ],
)
def test_identity_ignores_where_a_run_connects_and_stores(update):
    assert set(update) <= set(TRANSPORT_FIELDS)
    assert Settings(**update).identity == Settings().identity


@pytest.mark.parametrize(
    "update",
    [
        {"images": {"python.secret_disclosure/1": "corsair-python:1234567"}},
        {"image": "corsair-python:1234567"},
        {"memory_limit": "1g"},
        {"negative_threshold": 3},
        {"max_concurrent_activities": 8},
        {"models": ModelSettings(producer="other-model")},
    ],
)
def test_identity_still_changes_with_behaviour(update):
    assert Settings(**update).identity != Settings().identity


def test_the_manifest_config_digest_is_the_transport_free_identity():
    request = load_investigation_request(ROOT / "evals/fixtures/case01/request.json")
    local = Settings()
    gym_run = Settings(temporal_namespace="corsair-gym", task_queue="gym-x-1234567")

    first = build_manifest(request, local, "sha256:image")
    second = build_manifest(request, gym_run, "sha256:image")

    assert first.config_digest == second.config_digest == local.identity


# Tiers


def test_a_tier_name_resolves_to_its_gym_manifest_and_a_path_is_accepted(tmp_path):
    assert gym.resolve_tier("tier0", ROOT) == DATASETS / "gym-tier0.json"
    manifest = tmp_path / "custom.json"
    manifest.write_text("{}")
    assert gym.resolve_tier(str(manifest), ROOT) == manifest
    with pytest.raises(ValueError, match="no gym tier"):
        gym.resolve_tier("tier9", ROOT)


def _entries(name: str) -> list[dict]:
    return json.loads((DATASETS / f"{name}.json").read_text())["entries"]


def test_tier0_copies_one_case_per_language_verbatim():
    tier0 = _entries("gym-tier0")
    sources = {
        entry["case_id"]: entry
        for name in (
            "chain-python",
            "chain-javascript",
            "chain-ruby",
            "chain-java",
            "chain-perl",
            "chain-c",
        )
        for entry in _entries(name)
    }
    assert [entry["case_id"] for entry in tier0][0] == "chain-python-cmdi-b"
    assert all(entry == sources[entry["case_id"]] for entry in tier0)
    _, requests, _ = load_dataset(DATASETS / "gym-tier0.json")
    languages = [request.case.recipe.kind.split(".")[0] for request in requests]
    assert sorted(languages) == sorted(LANGUAGES)


def test_tier1_is_every_runnable_composed_case_verbatim():
    names = (
        "dev",
        "safety",
        "adversarial",
        "chain-python",
        "chain-javascript",
        "chain-ruby",
        "chain-java",
        "chain-perl",
        "chain-c",
    )
    expected = [entry for name in names for entry in _entries(name)]
    assert _entries("gym-tier1") == expected
    assert len(expected) == 15
    assert not (DATASETS / "gym-tier2.json").exists()


# Task queue and run identity


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("gym/wp3-runner", "gym-gym-wp3-runner-abcdef1"),
        ("Feature/Some_Thing!", "gym-feature-some-thing-abcdef1"),
        ("HEAD", "gym-head-abcdef1"),
    ],
)
def test_the_task_queue_is_per_branch_and_commit(branch, expected):
    assert gym.gym_task_queue(branch, "abcdef1234567890") == expected


def test_a_long_branch_still_yields_a_bounded_queue():
    queue = gym.gym_task_queue("x" * 300, "abcdef1234567890")
    assert len(queue) <= 80
    assert queue.endswith("-abcdef1")


def test_run_ids_are_valid_root_identities():
    run_id = gym.new_run_id(DATASETS / "gym-tier1.json")
    assert run_id.startswith("gym-tier1-")
    assert validate_root_identity(run_id) == run_id
    long = gym.new_run_id(Path("x" * 200 + ".json"))
    assert validate_root_identity(long) == long


def test_git_revision_reads_this_checkout():
    branch, commit = gym.git_revision(ROOT)
    assert branch
    assert re.fullmatch(r"[0-9a-f]{40}", commit)


# Content-addressed images


def _image_tree(root: Path, language: str = "python", driver: bytes = b"print(1)\n") -> None:
    (root / "deploy" / language).mkdir(parents=True, exist_ok=True)
    (root / "deploy" / language / "Dockerfile").write_text("FROM scratch\n")
    drivers = root / "src/corsair/adapters/sandboxing/drivers" / language
    drivers.mkdir(parents=True, exist_ok=True)
    (drivers / "driver.py").write_bytes(driver)


def test_an_image_tag_is_seven_hex_and_deterministic(tmp_path):
    _image_tree(tmp_path)
    tag = gym.image_tag(tmp_path, "python")
    assert re.fullmatch(r"[0-9a-f]{7}", tag)
    assert gym.image_tag(tmp_path, "python") == tag


def test_an_uncommitted_driver_edit_or_new_file_changes_the_tag(tmp_path):
    _image_tree(tmp_path)
    before = gym.image_tag(tmp_path, "python")
    _image_tree(tmp_path, driver=b"print(2)\n")
    edited = gym.image_tag(tmp_path, "python")
    assert edited != before
    (tmp_path / "deploy/python/extra.txt").write_text("x")
    assert gym.image_tag(tmp_path, "python") not in {before, edited}


def test_generated_bytecode_does_not_change_the_tag(tmp_path):
    _image_tree(tmp_path)
    before = gym.image_tag(tmp_path, "python")
    cache = tmp_path / "src/corsair/adapters/sandboxing/drivers/python/__pycache__"
    cache.mkdir()
    (cache / "driver.cpython-312.pyc").write_bytes(b"\x00bytecode")
    assert gym.image_tag(tmp_path, "python") == before


def test_languages_get_distinct_tags_and_a_missing_language_is_refused(tmp_path):
    _image_tree(tmp_path, "python")
    _image_tree(tmp_path, "ruby")
    assert gym.image_tag(tmp_path, "python") != gym.image_tag(tmp_path, "ruby")
    with pytest.raises(ValueError, match="perl"):
        gym.image_tag(tmp_path, "perl")


def test_gym_images_map_every_configured_kind_to_its_content_tag():
    images = gym.gym_images(ROOT, Settings())
    assert set(images) == set(Settings().images)
    for kind, ref in images.items():
        language = kind.split(".")[0]
        assert ref == f"corsair-{language}:{gym.image_tag(ROOT, language)}"


def test_gym_settings_override_transport_and_images_only():
    base = Settings(memory_limit="768m")
    images = gym.gym_images(ROOT, base)
    derived = gym.gym_settings(
        base, temporal_address="127.0.0.1:40001", task_queue="gym-x-1234567", images=images
    )
    assert derived.temporal_namespace == gym.GYM_NAMESPACE == "corsair-gym"
    assert derived.task_queue == "gym-x-1234567"
    assert derived.temporal_address == "127.0.0.1:40001"
    assert derived.images == images
    assert derived.image == images["python.secret_disclosure/1"]
    assert derived.memory_limit == "768m"
    again = gym.gym_settings(
        base, temporal_address="127.0.0.1:40002", task_queue="gym-y-7654321", images=images
    )
    assert again.identity == derived.identity != base.identity


# Selection


def test_cases_and_languages_filter_the_manifest_in_memory():
    _, requests, _ = load_dataset(DATASETS / "gym-tier0.json")
    by_case = gym.select_requests(requests, cases=("ruby-pathtraversal",), languages=())
    assert [request.case.case_id for request in by_case] == ["ruby-pathtraversal"]
    by_language = gym.select_requests(requests, cases=(), languages=("c", "perl"))
    assert [request.case.case_id for request in by_language] == ["perl-xss-b", "c-intoverflow-a"]
    assert gym.select_requests(requests, cases=(), languages=()) == requests


def test_an_unknown_case_or_an_empty_selection_is_refused():
    _, requests, _ = load_dataset(DATASETS / "gym-tier0.json")
    with pytest.raises(ValueError, match="not in the tier"):
        gym.select_requests(requests, cases=("absent",), languages=())
    with pytest.raises(ValueError, match="no case"):
        gym.select_requests(requests, cases=("ruby-pathtraversal",), languages=("c",))


def test_more_concurrency_than_worker_activity_slots_is_refused():
    with pytest.raises(ValueError, match="max_concurrent_activities"):
        gym.check_concurrency(Settings(max_concurrent_activities=2), 3)
    gym.check_concurrency(Settings(max_concurrent_activities=4), 4)
