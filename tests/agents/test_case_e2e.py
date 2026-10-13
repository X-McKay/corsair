"""The benchmark case command offline: chain input from a manifest and a local clone, the runner chosen from the
selected framework row, and the generalized run record for a case with build files and setup source. No Docker,
model or network: the clone is a throwaway git repository and the environment stage's sandbox a host double."""
import asyncio
from hashlib import sha256
import json
import subprocess

import pytest

from corsair.adapters.jest_runner import JestRunner
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.nodes.runtime.contracts import AxisCheck, Supported
from corsair.nodes.runtime.environment import framework_row
from corsair.nodes.runtime.matrix import load
from evals.benchmark.cases import BenchmarkEntry, CaseManifest, load as load_cases
from evals.case_e2e.case import CaseRefused, build_case, entry
from evals.case_e2e.frameworks import harness
from evals.fixture_e2e.case import (reviewed_runners, scripted_assessment, scripted_authoring, scripted_identification,
                                    scripted_planning)
from evals.fixture_e2e.run import AGENT_STAGES, record_run
from tests.agents.test_chain_environment_stage import (BASELINE, BUILD, DISCOVER, OK, ROW, Sandboxes, case as env_case,
                                                       catalog, environment_model, ready_draft)

NODE = "node-8.17.0-npm"
CONFIG = "sha256:" + "c" * 64
PACKAGE = '{"name": "demo", "engines": {"node": "%s"}, "devDependencies": {"jest": "^24.8.0"}}\n'


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def clone(tmp_path):
    """Two commits of a tiny npm project: the baseline runs a shell, the candidate does not."""
    repo = tmp_path / "clone"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / "lib").mkdir()
    (repo / ".travis.yml").write_text("language: node_js\nnode_js:\n- 8\n")

    def commit(engines, source):
        (repo / "package.json").write_text(PACKAGE % engines)
        (repo / "lib/run.js").write_text(source)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "c")
        return git(repo, "rev-parse", "HEAD")
    baseline = commit(">=8", "module.exports = d => require('child_process').execSync('zip ' + d);\n")
    candidate = commit(">=8", "module.exports = d => require('child_process').execFileSync('zip', [d]);\n")
    return repo, baseline, candidate, commit


def manifest_entry(baseline, candidate, **agent):
    manifest = CaseManifest.model_validate({
        "agent": {"issue": "run.js passes its argument to a zip command. Check whether it reaches a shell.",
                  "scope": "component", "repository": "https://example.invalid/demo", "baseline": baseline,
                  "candidate": candidate, "language": "JavaScript", "build_system": "npm / Jest",
                  "source_paths": ["lib/run.js"], "setup_paths": ["package.json", ".travis.yml"]} | agent,
        "evaluator": {"case_id": "demo", "cwe": None, "fix_reference": None, "issue_reviewed": False,
                      "reference_test": None, "expected": None, "split": None, "admission": "not_admitted",
                      "blocking": ["G10"]}})
    some = next(e for e in load_cases() if e.manifest)
    return BenchmarkEntry(some.inventory, some.directory, manifest)


def test_a_case_becomes_chain_input_with_the_runner_its_build_files_select(clone, tmp_path):
    repo, baseline, candidate, _ = clone
    built = build_case(manifest_entry(baseline, candidate), repo, tmp_path / "trees", {NODE: CONFIG}, 600)
    assert (built.row, built.image, built.framework.name, built.harness.runner) == (NODE, CONFIG, "jest", JestRunner)
    case = built.case
    # The Docker workspace digests the commit it copied; any other source is refused by the chain.
    assert case.revision_sources == {"baseline": sha256(baseline.encode()).hexdigest(),
                                     "candidate": sha256(candidate.encode()).hexdigest()}
    assert [f.path for f in case.issue.source_files] == ["lib/run.js"] and "execSync" in case.issue.source_files[0].content
    assert case.setup.commit == baseline and [f.path for f in case.setup.source_files] == ["package.json", ".travis.yml"]
    assert sorted(case.runtime.files) == [".travis.yml", "package.json"] and case.runtime.language == "javascript"
    assert built.catalog.prepared == {NODE: f"local/corsair-{NODE}@{CONFIG}"}
    assert case.environment_identity.image_digest == "c" * 64 and case.witness_envelope is None
    # Each revision's tree is that commit's blobs, never the clone's worktree.
    assert "execFileSync" in (built.trees["candidate"] / "lib/run.js").read_text()
    assert "execSync" in (built.trees["baseline"] / "lib/run.js").read_text()


def test_a_case_without_a_selected_runtime_or_its_files_is_refused_before_any_model(clone, tmp_path):
    repo, baseline, candidate, commit = clone
    with pytest.raises(CaseRefused, match="does not hold the candidate commit"):
        build_case(manifest_entry(baseline, "f" * 40), repo, tmp_path / "a", {NODE: CONFIG}, 600)
    with pytest.raises(CaseRefused, match="lists no source_paths or setup_paths"):
        build_case(manifest_entry(baseline, candidate, source_paths=[]), repo, tmp_path / "b", {NODE: CONFIG}, 600)
    with pytest.raises(CaseRefused, match="setup file missing.json is not a regular file"):
        build_case(manifest_entry(baseline, candidate, setup_paths=["missing.json"]), repo, tmp_path / "c",
                   {NODE: CONFIG}, 600)
    with pytest.raises(CaseRefused, match="not_prepared|no prepared image|not prepared"):
        build_case(manifest_entry(baseline, candidate), repo, tmp_path / "d", {}, 600)
    newer = commit(">=20", "module.exports = () => 0;\n")
    with pytest.raises(CaseRefused, match="runtime (unsupported|undetermined)"):
        build_case(manifest_entry(newer, candidate), repo, tmp_path / "e", {NODE: CONFIG}, 600)


def test_the_runner_is_the_selected_framework_rows_and_only_one():
    matrix = load()
    jest = AxisCheck(kind="test_framework", name="jest", allowed=">=24", provided="24.8.0", satisfied=True)
    node = Supported(status="supported", image_id=NODE, image="x@sha256:" + "0" * 64, checks=(jest,), evidence="image-only")
    row = framework_row(node, matrix)
    assert (row.name, row.runner, harness(row).runner) == ("jest", "src/corsair/adapters/jest_runner.py", JestRunner)
    # pytest's row exists but has no case harness yet: refused rather than run through another framework's runner.
    pytest_check = jest.model_copy(update={"name": "pytest"})
    python = node.model_copy(update={"image_id": "cpython-3.12-pytest", "checks": (pytest_check,)})
    with pytest.raises(ValueError, match="no case harness for the pytest runner"):
        harness(framework_row(python, matrix))
    with pytest.raises(ValueError, match="admitted 0 framework rows"):
        framework_row(node.model_copy(update={"checks": (jest.model_copy(update={"satisfied": False}),)}), matrix)


@pytest.mark.parametrize("case, rows", [("codecov-gcov-command-injection", "CVE-2020-15123"),
                                        ("CVE-2020-7730", "bestzip-command-injection")])
def test_the_jest_case_manifests_resolve_by_directory_or_case_id(case, rows):
    found = entry(case)
    assert {found.inventory.case_id, found.directory.name} == {case, rows}
    assert found.manifest.agent.source_paths and found.manifest.agent.setup_paths


def test_a_case_run_records_the_environment_stage_and_its_ports(tmp_path):
    """record_run over a case with build files and setup source: the environment stage runs on the operator's
    preparation port and the configuration names every stage's identity and the prepared images."""
    (tmp_path / "artifacts").mkdir(mode=0o700)
    (tmp_path / "work").mkdir()
    (tmp_path / "e2e").mkdir()
    scripted = {"environment": lambda: environment_model([BUILD, DISCOVER, BASELINE], ready_draft()),
                "identification": scripted_identification, "planning": scripted_planning,
                "authoring": scripted_authoring, "assessment": scripted_assessment}
    sandboxes = Sandboxes(OK)
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as store:
        run = asyncio.run(record_run(tmp_path / "e2e", (), None, env_case(), reviewed_runners(store, tmp_path / "work"),
                                     {"route": "test"}, stages=AGENT_STAGES, scripted=scripted, catalog=catalog(),
                                     preparation=sandboxes))
    assert (run.stopped_at, run.reason) == (None, "complete") and [t.toolchain_id for t in sandboxes.prepared] == [ROW]
    configuration = json.loads((tmp_path / "e2e/configuration.json").read_text())
    assert list(configuration["versions"]) == list(AGENT_STAGES) and configuration["prepared_images"] == dict(catalog().prepared)
    assert configuration["setup"]["commit"] == env_case().setup.commit and configuration["runtime_inputs"] == ["pyproject.toml"]
    assert (tmp_path / "e2e/attempt-0-environment.json").exists()
    with pytest.raises(ValueError, match=r"stages \['environment'\] are neither live nor scripted"):
        asyncio.run(record_run(tmp_path / "other", (), None, env_case(), None, {}, stages=AGENT_STAGES))


def test_an_environment_framework_other_than_the_selected_one_stops_the_run(tmp_path):
    """The runner is picked from the selection before the chain; the environment stage cannot report another framework."""
    from corsair.composition.direct import StageModels, run_direct
    (tmp_path / "artifacts").mkdir(mode=0o700)
    (tmp_path / "work").mkdir()
    models = StageModels(identification=scripted_identification(), planning=scripted_planning(),
                         authoring=scripted_authoring(), assessment=scripted_assessment(),
                         environment=environment_model([BUILD, DISCOVER, BASELINE], ready_draft(framework="jest")))
    with LocalArtifacts(tmp_path / "artifacts", max_bytes=1024 * 1024) as store:
        run = asyncio.run(run_direct(env_case(), models, reviewed_runners(store, tmp_path / "work"), catalog=catalog(),
                                     preparation=Sandboxes(OK)))
    # The agent's own admission refuses a framework its outputs do not show; check_ready refuses one the selection
    # did not admit. Either way no ready environment, and so no runner, follows.
    assert run.stopped_at == "environment" and run.environment is None and run.executions == ()


def test_result_lines_and_the_cohort_roll_up(tmp_path):
    from corsair.composition.direct import DirectRun
    from evals.case_e2e.results import cohort_summary, markdown, result_line
    from evals.fixture_chain.evaluate import ChainOracle
    refused = result_line("CVE-1", "JavaScript", None, tmp_path, refused="runtime undetermined: no engines")
    assert (refused["reached"], refused["reason"], refused["selected"], refused["usage"]) == (
        "case", "runtime undetermined: no engines", None, {})
    stopped = DirectRun(stopped_at="planning", reason="plan unsupported: no witness recorder", attempts=())
    oracle = ChainOracle(stopped_at="planning", gate=None, assessment_admitted=None)
    planning = result_line("CVE-2", "JavaScript", oracle, tmp_path, run=stopped)
    assert (planning["reached"], planning["matches_expected"], planning["baseline_basis"]) == ("planning", True, None)
    done = result_line("CVE-3", "Python", None, tmp_path, run=DirectRun(stopped_at=None, reason="complete", attempts=()))
    summary = cohort_summary([refused, planning, done])
    assert summary["by_language"]["JavaScript"]["case"] == 2 and summary["by_language"]["JavaScript"]["runtime"] == 1
    assert summary["by_language"]["JavaScript"]["authoring"] == 0 and summary["total"]["complete"] == 1
    assert "| total | 3 | 2 | 2 | 2 | 2 | 1 | 1 | 1 | 1 |" in markdown(summary)


def test_a_cohort_records_a_case_that_cannot_start_before_any_model(tmp_path, monkeypatch):
    from evals.case_e2e import evaluate
    monkeypatch.setattr(evaluate, "cohort", lambda name: ("CVE-2020-15123",))
    stop = lambda: (_ for _ in ()).throw(AssertionError("no model may be built"))
    report, summary = asyncio.run(evaluate.evaluate(tmp_path / "run", "jest", tmp_path / "no-sources", {NODE: CONFIG},
                                                    models={stage: stop for stage in AGENT_STAGES}))
    line = json.loads((tmp_path / "run/results.jsonl").read_text())
    assert line["reached"] == "case" and "does not hold the baseline commit" in line["reason"]
    assert summary["total"]["case"] == 1 and summary["total"]["runtime"] == 0
    assert report.cases[0].assertions["started"].value is False and not report.failures
    assert json.loads((tmp_path / "run/configuration.json").read_text())["dataset"] == "jest"
    # The eval wrapper's summary and comparison read the native report like any other suite's.
    from evals.run import summarize
    assert summarize(tmp_path / "run")["identity"]["dataset"] == "jest" and summarize(tmp_path / "run")["attempts"] == 1
