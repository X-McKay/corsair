"""The issue entry offline: an issue request becomes chain input from a local clone, the runner comes from the one
framework table keyed on the selected framework row, and a request that cannot start is recorded at admission before
any model request. No Docker, model or network: the clone is a throwaway git repository and the environment stage's
sandbox a host double."""
import asyncio
from hashlib import sha256
import json
import subprocess

import pytest
from pydantic import ValidationError

from corsair.adapters.jest_runner import JestRunner
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.agents.environment.contracts import Toolchain
from corsair.investigation.build import Refused, build, repository_of
from corsair.investigation.frameworks import HARNESSES, NoHarness, harness
from corsair.investigation.request import IssueRequest
from corsair.nodes.runtime.contracts import AxisCheck, Supported
from corsair.nodes.runtime.environment import framework_row
from corsair.nodes.runtime.matrix import load
from evals.case_e2e.case import case_request, entry, expected
from evals.fixture_e2e.case import (reviewed_runners, scripted_assessment, scripted_authoring, scripted_identification,
                                    scripted_planning)
from evals.fixture_e2e.run import AGENT_STAGES, record_run
from tests.agents.test_chain_environment_stage import (BASELINE, BUILD, DISCOVER, OK, ROW, Sandboxes, case as env_case,
                                                       catalog, environment_model, ready_draft)

NODE = "node-8.17.0-npm"
CONFIG = "sha256:" + "c" * 64
PACKAGE = '{"name": "demo", "engines": {"node": "%s"}, "devDependencies": {"jest": "^24.8.0"}}\n'
ISSUE = {"provider": "manual", "title": "Command injection in lib/run.js",
         "body": "lib/run.js passes its argument to a zip command. Check whether it reaches a shell."}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def clone(tmp_path):
    """Two commits of a tiny npm project: the baseline runs a shell, the candidate does not."""
    repo = tmp_path / "sources/clone"
    repo.mkdir(parents=True)
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


def request(repo, baseline, candidate, **changes):
    return IssueRequest.model_validate({"schema": "corsair-issue-request/v1", "issue": ISSUE,
                                        "repository": f"file://{repo}", "revision": baseline,
                                        "fixed_revision": candidate} | changes)


def test_an_issue_request_holds_the_issue_and_commits_and_nothing_an_operator_owns(clone):
    repo, baseline, candidate, _ = clone
    manual = request(repo, baseline, candidate)
    assert manual.label.startswith("manual:") and manual.issue_text().startswith("Command injection in lib/run.js\n\n")
    assert json.loads(manual.model_dump_json(by_alias=True))["schema"] == "corsair-issue-request/v1"
    ticket = {"provider": "github", "source": "acme/files", "id": "42", "url": "https://github.com/acme/files/issues/42",
              "revision": "1", "title": "t", "body": "b", "format": "markdown", "state": "open",
              "updated_at": "2026-10-13T00:00:00Z", "observed_at": "2026-10-13T00:00:00Z", "comments": []}
    github = request(repo, baseline, candidate, issue=ticket, repository=None)
    # A GitHub issue's request may leave the repository out: the issue's own repository is used and recorded so.
    assert github.label == "github:acme/files#42"
    assert repository_of(github) == ("https://github.com/acme/files", "ticket")
    for field, value in {"runtime": "node-8", "framework": "jest", "expected": "reproduced", "witness": "x",
                         "image": "node@sha256:" + "0" * 64}.items():
        with pytest.raises(ValidationError, match="Extra inputs"):
            request(repo, baseline, candidate, **{field: value})
    with pytest.raises(ValidationError, match="exact 40-hex commits"):
        request(repo, "main", candidate)
    with pytest.raises(ValidationError, match="plain https URL or a file:// path"):
        request(repo, baseline, candidate, repository="ssh://git@example.invalid/demo")


def test_an_issue_request_becomes_chain_input_with_the_runner_its_build_files_select(clone, tmp_path):
    repo, baseline, candidate, _ = clone
    built = build(request(repo, baseline, candidate), tmp_path / "trees", {NODE: CONFIG}, roots=(tmp_path / "sources",))
    assert (built.row, built.image, built.framework.name, built.harness.runner) == (NODE, CONFIG, "jest", JestRunner)
    assert built.bases == {"repository": "request", "scope": "default"}
    case = built.case
    # The Docker workspace digests the commit it copied; any other source is refused by the chain.
    assert case.revision_sources == {"baseline": sha256(baseline.encode()).hexdigest(),
                                     "candidate": sha256(candidate.encode()).hexdigest()}
    # Issue source is what the issue names; setup source is the revision's build and CI files.
    assert [f.path for f in case.issue.source_files] == ["lib/run.js"] and "execSync" in case.issue.source_files[0].content
    assert case.setup.commit == baseline and [f.path for f in case.setup.source_files] == [".travis.yml", "package.json"]
    assert sorted(case.runtime.files) == [".travis.yml", "package.json"] and case.issue.scope == "component"
    assert built.catalog.prepared == {NODE: f"local/corsair-{NODE}@{CONFIG}"}
    assert case.environment_identity.image_digest == "c" * 64 and case.witness_envelope is None
    # Each revision's tree is that commit's blobs, never the clone's worktree.
    assert "execFileSync" in (built.trees["candidate"] / "lib/run.js").read_text()
    assert "execSync" in (built.trees["baseline"] / "lib/run.js").read_text()


def test_a_request_that_cannot_start_is_refused_before_any_model(clone, tmp_path):
    repo, baseline, candidate, commit = clone
    roots = (tmp_path / "sources",)

    def refused(match, req, images={NODE: CONFIG}, allowed=roots):
        with pytest.raises(Refused, match=match):
            build(req, tmp_path / f"w{len(list(tmp_path.iterdir()))}", images, roots=allowed)
    refused("does not hold the candidate commit", request(repo, baseline, "f" * 40))
    refused("names no fixed revision", request(repo, baseline, None))
    refused("names no revision", request(repo, None, candidate))
    refused("not under an operator-allowed", request(repo, baseline, candidate), allowed=(tmp_path / "elsewhere",))
    refused("names no repository", request(repo, baseline, candidate, repository=None))
    refused("no repository acquisition", request(repo, baseline, candidate, repository="https://example.invalid/demo"))
    refused("names no file of the revision", request(
        repo, baseline, candidate, issue=ISSUE | {"title": "Command injection", "body": "zip reaches a shell"}))
    refused("not prepared|no prepared image|not_prepared", request(repo, baseline, candidate), images={})
    newer = commit(">=20", "module.exports = () => 0;\n")
    refused("runtime (unsupported|undetermined)", request(repo, newer, candidate))


def test_the_runner_is_the_selected_framework_rows_entry_in_one_table():
    matrix = load()
    jest = AxisCheck(kind="test_framework", name="jest", allowed=">=24", provided="24.8.0", satisfied=True)
    node = Supported(status="supported", image_id=NODE, image="x@sha256:" + "0" * 64, checks=(jest,), evidence="image-only")
    row = framework_row(node, matrix)
    assert (row.name, harness(row.name, route=True).runner) == ("jest", JestRunner)
    # Every entry is keyed by a framework row the matrix declares.
    assert set(HARNESSES) <= {f.name for f in matrix.frameworks}
    assert harness("pytest", route=True).witness_facilities[0].id == "audit_open"
    with pytest.raises(NoHarness, match="no harness entry for the minitest framework"):
        harness("minitest")
    with pytest.raises(ValueError, match="admitted 0 framework rows"):
        framework_row(node.model_copy(update={"checks": (jest.model_copy(update={"satisfied": False}),)}), matrix)


def test_a_toolchain_language_is_not_a_fixed_list():
    fields = {"toolchain_id": "x", "image": "i@sha256:" + "0" * 64, "runtime": "r", "tools": ()}
    for language in ("javascript", "ruby", "c++", "c#", "kotlin"):
        assert Toolchain.model_validate(fields | {"language": language}).language == language
    with pytest.raises(ValidationError):
        Toolchain.model_validate(fields | {"language": "Not A Language"})


@pytest.mark.parametrize("case, directory", [("CVE-2020-15123", "codecov-gcov-command-injection"),
                                             ("CVE-2020-7730", "bestzip-command-injection")])
def test_a_jest_case_is_an_issue_request_plus_an_expectation_the_request_never_carries(case, directory, tmp_path):
    found = entry(case)
    assert found.directory.name == directory and entry(directory) is not None
    req = case_request(found, tmp_path)
    serialized = req.model_dump_json(by_alias=True)
    assert req.issue.provider == "manual" and req.repository == f"file://{tmp_path.resolve()}/{case}/repo"
    assert (req.revision, req.fixed_revision) == (found.manifest.agent.baseline, found.manifest.agent.candidate)
    # The expected outcome stays outside the request, and the case id outside what any agent reads (it names only
    # the operator's clone directory).
    assert "expected" not in serialized and case not in req.issue_text()
    assert expected(found) == (found.manifest.evaluator.expected.chain if found.manifest.evaluator.expected else None)


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


def test_records_summary_lines_and_the_cohort_roll_up(tmp_path):
    from corsair.composition.direct import DirectRun
    from corsair.investigation.results import cohort_summary, markdown, record, summary_line, with_expected
    from evals.fixture_chain.evaluate import ChainOracle
    refused = record("manual:abc", tmp_path, refused="runtime undetermined: no engines")
    assert (refused["reached"], refused["reason"], refused["selected"], refused["usage"]) == (
        "admission", "runtime undetermined: no engines", None, {})
    assert summary_line(refused).startswith("manual:abc: stopped at admission: runtime undetermined")
    oracle = ChainOracle(stopped_at="planning", gate=None, assessment_admitted=None)
    stopped = record("manual:def", tmp_path, run=DirectRun(stopped_at="planning", reason="no witness recorder", attempts=()))
    planning = with_expected(stopped, "CVE-2", oracle)
    assert (planning["reached"], planning["matches_expected"], planning["baseline_basis"]) == ("planning", True, None)
    assert with_expected(refused, "CVE-1", oracle)["matches_expected"] is None
    done = record("manual:ghi", tmp_path, run=DirectRun(stopped_at=None, reason="complete", attempts=()))
    summary = cohort_summary([refused, planning, done])
    assert summary["by_language"]["not selected"]["admission"] == 3 and summary["total"]["runtime"] == 2
    assert summary["total"]["authoring"] == 1 and summary["total"]["complete"] == 1
    assert "| total | 3 | 2 | 2 | 2 | 2 | 1 | 1 | 1 | 1 |" in markdown(summary)


def test_a_cohort_records_a_case_that_cannot_start_before_any_model(tmp_path, monkeypatch):
    from evals.case_e2e import evaluate
    monkeypatch.setattr(evaluate, "cohort", lambda name: ("CVE-2020-15123",))
    stop = lambda: (_ for _ in ()).throw(AssertionError("no model may be built"))
    (tmp_path / "sources").mkdir()
    report, summary = asyncio.run(evaluate.evaluate(tmp_path / "run", "jest", tmp_path / "sources", {NODE: CONFIG},
                                                    models={stage: stop for stage in AGENT_STAGES}))
    line = json.loads((tmp_path / "run/cases.jsonl").read_text())
    assert line["reached"] == "admission" and line["case"] == "CVE-2020-15123" and line["case_language"] == "JavaScript"
    assert summary["total"]["admission"] == 1 and summary["total"]["runtime"] == 0
    assert report.cases[0].assertions["started"].value is False and not report.failures
    assert json.loads((tmp_path / "run/configuration.json").read_text())["dataset"] == "jest"
    # The eval wrapper's summary and comparison read the native report like any other suite's.
    from evals.run import summarize
    assert summarize(tmp_path / "run")["identity"]["dataset"] == "jest" and summarize(tmp_path / "run")["attempts"] == 1
