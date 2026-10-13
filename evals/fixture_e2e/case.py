"""The E2E-0 fixture: the SPEC-0018 path-traversal pair, hand-supplied environment evidence and scripted stages.

Variant names and the reference plan stay here, in evaluator-owned code; agent inputs see only
the baseline revision's saved source and the operator's environment facts.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

import pytest
import yaml
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.source.contracts import SourceFile
from corsair.agents.test_planning.contracts import BaselineTest, EnvironmentEvidence
from corsair.composition.direct import FixtureCase
from corsair.core.disposition import EnvironmentIdentity

from .reviewed import DISCOVER, FIXTURE, PREFIX, REVIEWED_TEST, ReviewedLocalExecution, ReviewedWorkspace

REPOSITORY = Path(__file__).resolve().parents[2]
ISSUE = ("The read_document function accepts a user supplied filename. Check whether ../outside.txt could be read "
         "outside the configured documents directory. Analyze this component only.")
# Operator-supplied existing test, the same bytes the planning and authoring datasets use.
BASELINE_TEST = ('from pathlib import Path\n\nimport documents\n\n\ndef test_reads_existing_document(tmp_path: Path):\n'
                 '    (tmp_path / "note.txt").write_text("hello")\n'
                 '    assert documents.read_document(tmp_path, "note.txt") == "hello"\n')
# Where each purpose's fresh workspace comes from; never visible to an agent.
VARIANTS = {"development": "vulnerable", "baseline": "vulnerable", "candidate": "fixed"}


def _digest(value: str | bytes) -> str:
    return sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def fixture_case() -> FixtureCase:
    sources = (SourceFile(path="documents.py", content=(FIXTURE / "vulnerable" / "documents.py").read_text()),
               SourceFile(path="test_existing.py", content=BASELINE_TEST))
    environment = EnvironmentEvidence(
        language="Python", runtime="CPython 3.12", framework=f"pytest {pytest.__version__}",
        discovery_command=DISCOVER, approved_test_paths=(REVIEWED_TEST,),
        baseline_test=BaselineTest(test_id="test_existing.py::test_reads_existing_document", path="test_existing.py"),
        scratch_location="The per-test pytest tmp_path directory; fixtures must not be created elsewhere",
        observation_facilities=(
            "Python sys.addaudithook 'open' audit events recorded by the test itself inside the test process",
            "Native JUnit XML outcomes, failure locations and captured stdout per test",
            "Operator witness probe, not test code: calls, returns, raised exceptions and file opens attributed to "
            "the identified target function during each test's call phase"))
    # A declaration of what both revisions share, not an observed image or inventory digest.
    identity = EnvironmentIdentity(
        image_digest=_digest(f"{sys.executable}\n{sys.version}"), recipe_sha256=_digest(json.dumps(PREFIX)),
        dependency_inventory_sha256=_digest((REPOSITORY / "uv.lock").read_bytes()),
        policy_revision="host-reviewed-bytes-only", limits_sha256=_digest("subprocess-timeout=60s"))
    return FixtureCase(issue=IssueAnalysisInput(fixture_id="path-traversal-e2e-v1", issue=ISSUE, scope="component",
                                                source_files=sources),
                       environment=environment, environment_identity=identity,
                       revision_sources={revision: _digest((FIXTURE / VARIANTS[revision] / "documents.py").read_bytes())
                                         for revision in ("baseline", "candidate")})


def reviewed_runners(store, root: Path):
    """A fresh private workspace per purpose; only the reviewed test bytes are admitted for execution."""
    def runner(purpose):
        workspace = root / purpose
        return PytestRunner(ReviewedWorkspace(store, workspace, VARIANTS[purpose]), ReviewedLocalExecution(workspace),
                            store, PytestRunnerConfig(PREFIX, ".corsair-junit.xml", str(workspace),
                                                      witness_record_path=".corsair-witness.json"))
    return runner


def _reads_then(paths, output):
    """Read each path once from line 1, then call the output tool with ``output(info)``."""
    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(paths):
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": paths[done], "start_line": 1},
                                                     tool_call_id=f"read-{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output(info))])
    return FunctionModel(respond)


def scripted_identification() -> FunctionModel:
    return _reads_then(["documents.py"], lambda info: {
        "status": "ready", "scope": "component", "reason": None,
        "target": {"symbol": "read_document", "source": {"path": "documents.py", "start_line": 3, "end_line": 4}}})


def reference_plan() -> dict:
    cases = yaml.safe_load((REPOSITORY / "evals/test_planning/cases.yaml").read_text())["cases"]
    plan = next(c for c in cases if c["name"] == "path_traversal_unguarded")["metadata"]["reference_plan"]
    return plan | {"discovery_command": list(DISCOVER)}


def scripted_planning() -> FunctionModel:
    return _reads_then(["documents.py", "test_existing.py"], lambda info: {"plan": reference_plan()})


# Assertion lines of test_security_rejects_outside_read in the reviewed bytes, as the authoring dataset records.
SECURITY_ASSERTION_LINES = [64, 65, 66]


def scripted_authoring() -> FunctionModel:
    """Writes the reviewed SPEC-0018 bytes, runs them once, and returns the patch draft."""
    reviewed = (FIXTURE / REVIEWED_TEST).read_text()
    steps = [ToolCallPart("read_source", {"path": "documents.py"}), ToolCallPart("read_source", {"path": "test_existing.py"}),
             ToolCallPart("write_test_file", {"path": REVIEWED_TEST, "content": reviewed}), ToolCallPart("run_tests", {})]

    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(steps):
            step = steps[done]
            return ModelResponse(parts=[ToolCallPart(step.tool_name, step.args, tool_call_id=f"author-{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": {
            "status": "patch", "security_assertion_lines": SECURITY_ASSERTION_LINES,
            "limitations": ["Development runs observe discovery and the control only"]}})])
    return FunctionModel(respond)


INVENTORY = re.compile(r"(?P<item>[a-z0-9][a-z0-9_.-]*) \(kind (?P<kind>\w+), (?:(?P<revision>baseline|candidate) run \d+, )?lines 1\.\.(?P<lines>\d+)\)")


def scripted_assessment(execution="completed", finding="inconclusive", fix="not_verified") -> FunctionModel:
    """Reads every inventory item once and proposes the given triple, citing each revision's first item line."""
    async def respond(messages, info):
        prompt = next(part.content for message in messages for part in message.parts if part.part_kind == "user-prompt")
        items = [match.groupdict() for match in INVENTORY.finditer(prompt)]
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(items):
            return ModelResponse(parts=[ToolCallPart("read_evidence", {"item_id": items[done]["item"]},
                                                     tool_call_id=f"evidence-{done}")])

        def cite(revision):
            item = next(i for i in items if i["revision"] == revision)
            return {"item_id": item["item"], "start_line": 1, "end_line": 1}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "execution": execution, "finding": finding, "fix": fix,
            "application_observations": [
                {"statement": "Baseline run evidence for the planned tests", "citations": [cite("baseline")]},
                {"statement": "Candidate run evidence for the planned tests", "citations": [cite("candidate")]}],
            "sandbox_observations": [],
            "interpretation": {"statement": "No witness captured outside the test process supports a conclusion",
                               "citations": [cite("baseline"), cite("candidate")]},
            "limitations": ["The planned witness was not captured outside the test process"]})])
    return FunctionModel(respond)
