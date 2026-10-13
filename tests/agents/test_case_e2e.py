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
    with pytest.raises(ValidationError, match="plain https URL, a file:// path or a path inside the checkout"):
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
    assert summary_line(refused).startswith("manual:abc: UNABLE_TO_RUN; stopped at admission: runtime undetermined")
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
    assert summary["labels"] == {"LIKELY_EXPLOITABLE": 0, "LIKELY_NOT_EXPLOITABLE": 0, "INCONCLUSIVE": 1,
                                 "UNABLE_TO_RUN": 1, "ERROR": 1}


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


def test_setup_containers_never_use_the_host_network_or_receive_proxy_credentials(monkeypatch):
    from corsair.investigation.docker import SETUP_NETWORK, registry_access
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    monkeypatch.delenv("https_proxy", raising=False)
    network, env, _ = registry_access(("HTTPS_PROXY", "https_proxy"))
    assert network == "bridge" and env == ("HTTPS_PROXY=http://proxy.internal:3128",)
    assert SETUP_NETWORK["egress"] == "unenforced"
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@proxy.internal:3128")
    with pytest.raises(ValueError, match="carries credentials") as refused:
        registry_access(("HTTPS_PROXY",))
    assert "secret" not in str(refused.value)


def test_the_sandbox_reads_the_baseline_file_from_the_capture_never_the_sandbox(tmp_path):
    from corsair.investigation.docker import captured_file
    tree, overlay = tmp_path / "tree", tmp_path / "overlay"
    (tree / "test").mkdir(parents=True)
    (tree / "test/a.test.js").write_text("it('a', () => expect(1).toBe(1));\n")
    (tree / "link.js").symlink_to(tmp_path / "outside.js")
    (tmp_path / "outside.js").write_text("secret")
    (overlay / "tests").mkdir(parents=True)
    (overlay / "tests/test_corsair_smoke.py").write_text("def test_environment_runs():\n    assert True\n")
    assert captured_file(tree, "test/a.test.js").startswith(b"it('a'")
    assert captured_file(tree, "tests/test_corsair_smoke.py", overlay).startswith(b"def test_environment_runs")
    assert captured_file(tree, "link.js") is None and captured_file(tree, "../outside.js") is None
    assert captured_file(tree, "missing.js") is None


@pytest.mark.parametrize("stopped_at, gate, flags, expected", [
    (None, {"execution": "completed", "finding": "reproduced"}, {}, "LIKELY_EXPLOITABLE"),
    (None, {"execution": "completed", "finding": "not_reproduced"}, {}, "LIKELY_NOT_EXPLOITABLE"),
    (None, {"execution": "completed", "finding": "refuted_in_scope"}, {}, "LIKELY_NOT_EXPLOITABLE"),
    (None, {"execution": "completed", "finding": "inconclusive"}, {}, "INCONCLUSIVE"),
    (None, {"execution": "failed", "finding": "inconclusive"}, {}, "ERROR"),
    (None, {"execution": "unknown", "finding": "inconclusive"}, {}, "ERROR"),
    (None, {"execution": "blocked", "finding": "inconclusive"}, {}, "UNABLE_TO_RUN"),
    (None, {"execution": "unsupported", "finding": "inconclusive"}, {}, "UNABLE_TO_RUN"),
    (None, None, {}, "ERROR"),
    ("admission", None, {}, "UNABLE_TO_RUN"),
    ("runtime", None, {}, "UNABLE_TO_RUN"),
    ("environment", None, {}, "UNABLE_TO_RUN"),
    ("environment", None, {"failed": True}, "ERROR"),
    ("planning", None, {}, "INCONCLUSIVE"),
    ("authoring", None, {"failed": True}, "ERROR"),
    ("environment", None, {"failed": True, "exhausted": True}, "INCONCLUSIVE"),
    ("authoring", None, {"failed": True, "exhausted": True}, "INCONCLUSIVE"),
    ("execution", None, {}, "ERROR"),
    ("admission", None, {"error": True}, "ERROR"),
])
def test_the_headline_label_tells_each_kind_of_outcome_apart(stopped_at, gate, flags, expected):
    from corsair.investigation.results import headline
    assert headline(stopped_at, gate, **flags) == expected


def test_a_crashed_run_is_recorded_as_error_where_it_crashed_with_its_traceback(clone, tmp_path, monkeypatch):
    import corsair.investigate as entry
    repo, baseline, candidate, _ = clone

    def crash(*args, **kwargs):
        raise OSError("docker daemon not reachable")
    monkeypatch.setattr(entry, "install", crash)
    stop = lambda: (_ for _ in ()).throw(AssertionError("no model may be built"))
    item = entry.investigate(request(repo, baseline, candidate), tmp_path / "ev", {NODE: CONFIG},
                             roots=(tmp_path / "sources",), models={stage: stop for stage in AGENT_STAGES})
    assert (item["label"], item["stopped_at"], item["crashed"]) == ("ERROR", "dependency setup", True)
    assert item["reason"] == "OSError: docker daemon not reachable"
    assert "Traceback" in (tmp_path / "ev/error.txt").read_text() and item["traceback"].endswith("error.txt")
    assert ": ERROR; crashed in dependency setup: OSError" in item["summary"]


def test_the_label_follows_the_assessments_standing_disposition(tmp_path):
    from types import SimpleNamespace
    from corsair.composition.direct import DirectRun
    from corsair.core.disposition import Disposition
    from corsair.investigation.results import record
    reproduced = Disposition(execution="completed", finding="reproduced", fix="verified")
    lowered = Disposition(execution="completed", finding="inconclusive", fix="not_verified")

    def run(proposal, admitted):
        assessment = SimpleNamespace(disposition=proposal if admitted else reproduced,
                                     admission=SimpleNamespace(admitted=admitted))
        return DirectRun(stopped_at=None, reason="complete", attempts=(),
                         gate=SimpleNamespace(permitted=reproduced), assessment=assessment)
    # The gate permits reproduced; the admitted assessment lowers it to inconclusive: the label follows the assessment.
    item = record("manual:x", tmp_path, run=run(lowered, True))
    assert (item["label"], item["label_basis"], item["gate"]["finding"]) == ("INCONCLUSIVE", "assessment_admitted",
                                                                              "reproduced")
    rejected = record("manual:x", tmp_path, run=run(lowered, False))
    assert (rejected["label"], rejected["label_basis"]) == ("LIKELY_EXPLOITABLE", "gate_assessment_rejected")
    gate_only = record("manual:x", tmp_path, run=DirectRun(stopped_at="assessment", reason="x", attempts=(),
                                                         gate=SimpleNamespace(permitted=reproduced)))
    assert (gate_only["label"], gate_only["label_basis"]) == ("INCONCLUSIVE", "gate")


def test_a_repository_committed_in_the_checkout_is_named_relative_to_it(clone, tmp_path):
    repo, baseline, candidate, _ = clone
    checkout = tmp_path / "sources"
    built = build(request(repo, baseline, candidate, repository="clone"), tmp_path / "rel", {NODE: CONFIG},
                  checkout=checkout)
    assert built.repository == "clone" and "execSync" in (built.trees["baseline"] / "lib/run.js").read_text()
    for escape in ("../clone", "/abs/clone", "~/clone", "a/../../clone"):
        with pytest.raises(ValidationError, match="inside the checkout"):
            request(repo, baseline, candidate, repository=escape)
    (checkout / "out").symlink_to(tmp_path)
    with pytest.raises(Refused, match="escapes the checkout"):
        build(request(repo, baseline, candidate, repository="out/elsewhere"), tmp_path / "esc", {NODE: CONFIG},
              checkout=checkout)
    # Without a fixed revision only the reported revision is acquired and runs (fix-free runs, Al 2026-10-13).
    fix_free = build(request(repo, baseline, None, repository="clone"), tmp_path / "nofix", {NODE: CONFIG},
                     checkout=checkout)
    assert set(fix_free.commits) == set(fix_free.trees) == set(fix_free.case.revision_sources) == {"baseline"}
    from corsair.investigation.results import record, summary_line
    assert "(no fix commit)" in summary_line(record("manual:x", tmp_path, investigation=fix_free, refused="x"))


def test_an_agent_stage_that_stops_on_its_budget_or_never_answers_is_inconclusive(tmp_path):
    from corsair.composition.direct import DirectRun, StageAttempt
    from corsair.investigation.results import record
    from pydantic_ai.exceptions import UsageLimitExceeded
    attempt = StageAttempt("environment", None, None, (), 1.0, UsageLimitExceeded("total_tokens_limit 48000"))
    item = record("manual:x", tmp_path, run=DirectRun(stopped_at="environment", attempts=(attempt,),
                                                      reason="environment budget exhausted: total_tokens_limit 48000"))
    assert (item["label"], item["stopped_at"]) == ("INCONCLUSIVE", "environment")
    from corsair.composition.direct import BudgetExhausted, StageLimits
    limits = StageLimits.model_construct()
    timed_out = StageAttempt("environment", None, None, (), 240.0, TimeoutError("stage timed out"), limits,
                             BudgetExhausted.model_construct(stage="environment", limit="timeout_seconds", cap=240,
                                                             limits=limits))
    assert record("manual:x", tmp_path, run=DirectRun(stopped_at="environment", attempts=(timed_out,),
                                                      reason="x"))["label"] == "ERROR"
    # A stage whose answer never validated ran and did not answer: INCONCLUSIVE, the last refusal beneath.
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    unanswered = UnexpectedModelBehavior("Exceeded maximum output retries (1)")
    unanswered.__cause__ = ValueError("planning answer was thinking only, no JSON")
    item = record("manual:x", tmp_path, run=DirectRun(stopped_at="planning", attempts=(
        StageAttempt("planning", None, None, (), 1.0, unanswered),), reason="planning failed"))
    assert (item["label"], item["last_refusal"]) == ("INCONCLUSIVE", "planning answer was thinking only, no JSON")
    malformed = StageAttempt("planning", None, None, (), 1.0, UnexpectedModelBehavior("Received empty model response"))
    assert record("manual:x", tmp_path, run=DirectRun(stopped_at="planning", attempts=(malformed,),
                                                      reason="x"))["label"] == "ERROR"
    crashed = StageAttempt("environment", None, None, (), 1.0, ConnectionError("provider unreachable"))
    assert record("manual:x", tmp_path, run=DirectRun(stopped_at="environment", attempts=(crashed,),
                                                      reason="x"))["label"] == "ERROR"


def test_the_sandbox_lists_the_captured_commits_files_for_the_smoke_rule(clone, tmp_path):
    from corsair.investigation.docker import captured_paths
    repo, baseline, candidate, _ = clone
    built = build(request(repo, baseline, candidate), tmp_path / "trees", {NODE: CONFIG}, roots=(tmp_path / "sources",))
    assert captured_paths(built.trees["baseline"]) == (".travis.yml", "lib/run.js", "package.json")
    (built.trees["baseline"] / "link.js").symlink_to("lib/run.js")
    assert "link.js" in captured_paths(built.trees["baseline"])
    import corsair.investigation.docker as route
    route.MAX_CAPTURED_PATHS, saved = 2, route.MAX_CAPTURED_PATHS
    try:
        assert captured_paths(built.trees["baseline"]) is None  # never a partial list
    finally:
        route.MAX_CAPTURED_PATHS = saved


def test_pov_files_reach_identification_and_an_oversized_ticket_is_refused(clone, tmp_path):
    repo, baseline, candidate, _ = clone
    pov = {"description": "Call run with a crafted name", "files": [{"path": "poc.sh", "content": "node -e 'x'"}]}
    text = request(repo, baseline, candidate, pov=pov).issue_text()
    assert "Proof of concept (untrusted, not executed)" in text and "File poc.sh:\nnode -e 'x'" in text
    ticket = {"provider": "github", "source": "acme/files", "id": "42", "url": "https://github.com/acme/files/issues/42",
              "revision": "1", "title": "lib/run.js", "body": "x" * 9000, "format": "markdown", "state": "open",
              "updated_at": "2026-10-13T00:00:00Z", "observed_at": "2026-10-13T00:00:00Z", "comments": []}
    with pytest.raises(Refused, match="does not fit the identification input"):
        build(request(repo, baseline, candidate, issue=ticket), tmp_path / "big", {NODE: CONFIG},
              roots=(tmp_path / "sources",))
