"""Gym runner pure parts: identity, tiers, task queues, content-addressed images, selection,
the shared run store and run metadata.

No Docker, Temporal or model is involved; the runner's service path is covered by
tests/integration/test_gym_runner.py.
"""

import json
import re
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import RunContext, validate_root_identity
from corsair.entrypoints import gym
from corsair.entrypoints.requests import load_investigation_request
from corsair.evaluation.datasets import load_dataset
from corsair.evaluation.gym.scoring import SCORECARD_FILE, read_scorecard, write_scorecard
from corsair.settings import TRANSPORT_FIELDS, ModelSettings, Settings
from corsair.steps.manifest import build_manifest
from tests.unit.evaluation.test_gym_gate import BASELINE
from tests.unit.test_gym_cli import _card

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
    tier1 = _entries("gym-tier1")
    assert tier1[: len(expected)] == expected
    assert len(expected) == 15
    # Rows frozen into tier1 through reviewed intake follow the composed cases.
    assert [entry["case_id"] for entry in tier1[len(expected) :]] == [
        "ih-python-codeinjection-a",
        "sbj-javascript-deep-override",
        "sbj-javascript-mixin-deep",
        "sbj-javascript-viking04-merge",
        "sbj-javascript-aurelia-path",
        "sbj-javascript-safe-flat",
    ]


def test_tier2_is_the_held_out_tier_outside_the_candidate_protocol():
    """tier2 resolves by name for the orchestrator and auditor, but the candidate protocol
    (``gym verify``) never runs it, and it shares no case with tier0 or tier1."""
    assert gym.resolve_tier("tier2", ROOT) == DATASETS / "gym-tier2.json"
    assert "tier2" not in gym.VERIFY_TIERS
    tier2 = _entries("gym-tier2")
    assert tier2 and {entry["split"] for entry in tier2} == {"held_out"}
    lower = {entry["case_id"] for name in ("gym-tier0", "gym-tier1") for entry in _entries(name)}
    assert not lower & {entry["case_id"] for entry in tier2}
    _, requests, _ = load_dataset(DATASETS / "gym-tier2.json")
    assert {request.case.recipe.kind for request in requests} == {
        "javascript.prototype_pollution/1"
    }


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


# The shared run store


def _git(cwd: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *arguments], check=True, capture_output=True)


def _repository_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "README").write_text("x\n")
    _git(main, "add", "README")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x")
    worktree = main / ".worktrees/gym/exp"
    _git(main, "worktree", "add", "-q", "-b", "gym/exp", str(worktree))
    return main, worktree


def test_every_worktree_resolves_the_main_checkouts_gym_root(tmp_path):
    main, worktree = _repository_with_worktree(tmp_path)
    expected = main.resolve() / ".runs/gym"

    assert gym.shared_gym_root(main) == gym.shared_gym_root(worktree) == expected
    paths = gym.gym_paths(worktree, Settings())
    assert paths == gym.gym_paths(main, Settings())
    assert (paths.store, paths.runs, paths.reference) == (
        expected / "store",
        expected / "runs",
        expected / "reference",
    )


def test_settings_naming_an_artifact_root_keep_it_as_the_store(tmp_path):
    paths = gym.gym_paths(tmp_path / "not-a-checkout", Settings(artifact_root=str(tmp_path / "a")))
    assert paths.store == tmp_path / "a"
    assert paths.runs == tmp_path / "a/gym/runs"


def test_a_run_reads_back_from_its_recorded_store(tmp_path):
    run_dir, store = tmp_path / "run", tmp_path / "elsewhere"
    explicit = Settings(artifact_root=str(tmp_path / "configured"))
    assert gym.run_store(run_dir, tmp_path, explicit) == tmp_path / "configured"
    store.mkdir()
    run_dir.mkdir()
    (run_dir / gym.RUN_FILE).write_text(json.dumps({"store": str(store)}))
    assert gym.run_store(run_dir, tmp_path, explicit) == store


def _publish(root: str, worker: int) -> int:
    """One process's writes: shared blobs and a shared operation, plus its own operations."""
    store = ArtifactStore(root)
    for index in range(200):
        ref = store.put(f"shared blob {index}".encode())
        store.commit(f"shared.{index}", ref)
        store.commit(f"own.{worker}.{index}", store.put(f"own {worker} {index}".encode()))
    return worker


def test_concurrent_runs_from_two_processes_share_one_store_safely(tmp_path):
    root = tmp_path / "store"
    with ProcessPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(_publish, [str(root)] * 2, [1, 2])) == [1, 2]

    store = ArtifactStore(root)
    assert len(list(store.blobs.iterdir())) == 600
    assert len(list(store.operations.iterdir())) == 600
    expected = {f"shared.{index}": f"shared blob {index}" for index in range(200)}
    for worker in (1, 2):
        expected |= {f"own.{worker}.{index}": f"own {worker} {index}" for index in range(200)}
    for operation, content in expected.items():
        ref = store.reconcile(operation)
        assert ref is not None and store.get(ref) == content.encode()
    assert not list(store.blobs.glob(".write-*")) and not list(store.operations.glob(".write-*"))
    with pytest.raises(ValueError, match="identity conflict"):
        store.commit("shared.0", store.put(b"a different result"))


# Run metadata


def test_the_invocation_keeps_arguments_but_not_endpoints_or_the_program_path():
    argv = ["/x/.venv/bin/corsair", "gym", "run", "tier0", "--temporal-address", "https://h:1/x"]
    assert gym.safe_invocation(argv) == (
        "corsair",
        "gym",
        "run",
        "tier0",
        "--temporal-address",
        "[endpoint]",
    )
    assert gym.safe_invocation([]) == ()


def test_the_tier_name_is_the_manifest_stem_without_its_prefix():
    assert gym.tier_name(DATASETS / "gym-tier1.json") == "tier1"
    assert gym.tier_name(Path("custom.json")) == "custom"


def test_a_run_listing_takes_the_recorded_context_when_the_scorecard_names_none(tmp_path):

    run_dir = tmp_path / "runs" / "gym-tier0-20261027t010807-479fc5"
    card = read_scorecard(_card(run_dir / SCORECARD_FILE, BASELINE, run_id="report"))
    write_scorecard(
        run_dir / SCORECARD_FILE, card.model_copy(update={"run": RunContext(run_id="report")})
    )
    recorded = RunContext(run_id=run_dir.name, git_branch="gym/loop", git_commit="c" * 40)
    (run_dir / gym.RUN_FILE).write_text(json.dumps({"run": recorded.model_dump(mode="json")}))

    summary = gym.run_summary(run_dir)

    assert (summary["run_id"], summary["git_commit"], summary["tier"]) == (
        run_dir.name,
        "c" * 40,
        "tier0",
    )
