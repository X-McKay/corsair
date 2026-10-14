"""Split-v2 E2E-0 fixture over the SPEC-0018 source pair and declared environment.

Variant names and the reference plan stay here, in evaluator-owned code; agent inputs see only
the baseline revision's saved source and the operator's environment facts.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from evals.native_skills import load_skills

from corsair.adapters.pytest_runner import PytestRunnerConfig
from corsair.investigation.frameworks import harness
from corsair.agents.environment.frameworks import FRAMEWORKS
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.source.contracts import SourceFile
from corsair.agents.test_planning.contracts import BaselineTest, EnvironmentEvidence, WitnessFacility
from corsair.composition.direct import CapturedReviewSource, FixtureCase
from corsair.core.disposition import EnvironmentIdentity
from corsair.ports.test_runner import WitnessRequest
from evals.cases import load_set

from .reviewed import DISCOVER, FIXTURE, PREFIX, REVIEWED_TEST, ReviewedLocalExecution, ReviewedWorkspace

REPOSITORY = Path(__file__).resolve().parents[2]
ISSUE = ("The read_document function accepts a user supplied filename. Check whether ../outside.txt could be read "
         "outside the configured documents directory. Analyze this component only.")
# Operator-supplied existing test, the same bytes the planning and authoring datasets use.
BASELINE_TEST = ('from pathlib import Path\n\nimport documents\n\n\ndef test_reads_existing_document(tmp_path: Path):\n'
                 '    (tmp_path / "note.txt").write_text("hello")\n'
                 '    assert documents.read_document(tmp_path, "note.txt") == "hello"\n')
# Where each purpose's fresh workspace comes from, per fixture case; never visible to an agent. In the
# not-exploitable cases the issue reports the same traversal, but every revision is safe source: `fixed` rejects
# the path with ValueError, `contained` returns an empty result without opening it (the SPEC-0040 absence route).
CASES = {"exploitable": {"development": "vulnerable", "baseline": "vulnerable", "candidate": "fixed"},
         "not-exploitable": {"development": "fixed", "baseline": "fixed", "candidate": "fixed"},
         "not-exploitable-absent": {"development": "contained", "baseline": "contained", "candidate": "contained"}}
VARIANTS = CASES["exploitable"]
# The reviewed test each case's scripted author writes and the reviewed workspace admits, with the line numbers
# of its security assertions; `contained` raises nothing, so its test asserts only that the outside content is never returned, and the operator witness records the opens.
REVIEWED = {"not-exploitable-absent": (FIXTURE / "contained" / REVIEWED_TEST, [27])}


def reviewed_test(case: str = "exploitable") -> tuple[Path, list[int]]:
    return REVIEWED.get(case, (FIXTURE / REVIEWED_TEST, HISTORICAL_SECURITY_ASSERTION_LINES))


def _digest(value: str | bytes) -> str:
    return sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def fixture_case(case: str = "exploitable") -> FixtureCase:
    variants = CASES[case]
    sources = (SourceFile(path="documents.py", content=(FIXTURE / variants["baseline"] / "documents.py").read_text()),
               SourceFile(path="test_existing.py", content=BASELINE_TEST))
    environment = EnvironmentEvidence(
        language="Python", runtime="CPython 3.12", framework=f"pytest {pytest.__version__}",
        discovery_command=DISCOVER, approved_test_paths=("test_control.py", "test_exploit.py"),
        baseline_test=BaselineTest(test_id="test_existing.py::test_reads_existing_document", path="test_existing.py"),
        scratch_location="The per-test pytest tmp_path directory; fixtures must not be created elsewhere",
        observation_facilities=(
            "Native JUnit XML outcomes, failure locations and captured stdout per test",
            "Operator witness probe, not test code: calls, returns, raised exceptions and file opens attributed to "
            "the identified target function during each test's call phase"),
        assertion_facts=FRAMEWORKS["pytest"].assertion_facts,
        witness_facilities=(WitnessFacility(
            id="audit_open", kind="file_open",
            description="Python sys.addaudithook 'open' events recording each path the test process opens during the call"),))
    # A declaration of what both revisions share, not an observed image or inventory digest.
    identity = EnvironmentIdentity(
        image_digest=_digest(f"{sys.executable}\n{sys.version}"), recipe_sha256=_digest(json.dumps(PREFIX)),
        dependency_inventory_sha256=_digest((REPOSITORY / "uv.lock").read_bytes()),
        policy_revision="host-reviewed-bytes-only", limits_sha256=_digest("subprocess-timeout=60s"))
    return FixtureCase(issue=IssueAnalysisInput(fixture_id="path-traversal-e2e-split-v2", issue=ISSUE, scope="component",
                                                source_files=sources),
                       environment=environment, environment_identity=identity,
                       witness_envelope=WitnessRequest("documents.py", "read_document", "outside.txt"),
                       review_sources={revision: CapturedReviewSource(
                           source_sha256=_digest((FIXTURE / variants[revision] / "documents.py").read_bytes()),
                           files=(SourceFile(path="documents.py", content=(FIXTURE / variants[revision] / "documents.py").read_text()),
                                  SourceFile(path="test_existing.py", content=BASELINE_TEST)))
                           for revision in ("baseline", "candidate")},
                       revision_sources={revision: _digest((FIXTURE / variants[revision] / "documents.py").read_bytes())
                                         for revision in ("baseline", "candidate")})


def reviewed_runners(store, root: Path, case: str = "exploitable"):
    """A fresh private workspace per purpose; only the reviewed test bytes are admitted for execution."""
    def runner(purpose):
        workspace = root / purpose
        return harness("pytest").runner(ReviewedWorkspace(store, workspace, CASES[case][purpose], split_reviewed_tests(case)),
                                        ReviewedLocalExecution(workspace),
                            store, PytestRunnerConfig(PREFIX, ".corsair-junit.xml", str(workspace),
                                                      witness_record_path=".corsair-witness.json"))
    return runner


def _reads_then(paths, output, *, skills=()):
    """Read each path once from line 1, then call the output tool with ``output(info)``."""
    async def respond(messages, info):
        activation = load_skills(messages, info, skills)
        if activation is not None:
            return activation
        done = sum(isinstance(part, ToolReturnPart) and part.tool_name == "read_source" for message in messages for part in message.parts)
        if done < len(paths):
            return ModelResponse(parts=[ToolCallPart("read_source", {"path": paths[done], "start_line": 1},
                                                     tool_call_id=f"read-{done}")])
        value = output(info)
        if "plan" in value:
            from evals.test_planning.drafts import component_draft
            value = value | {"plan": component_draft(value["plan"])}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, value)])
    return FunctionModel(respond)


def target_end(case: str = "exploitable") -> int:
    """read_document runs from line 3 to the end of the case's baseline source."""
    return len((FIXTURE / CASES[case]["baseline"] / "documents.py").read_text().splitlines())


def scripted_identification(case: str = "exploitable") -> FunctionModel:
    end = target_end(case)
    return _reads_then(["documents.py"], lambda info: {
        "status": "ready", "scope": "component", "reason": None,
        "target": {"symbol": "read_document", "source": {"path": "documents.py", "start_line": 3, "end_line": end}}}, skills=("identify-issue",))


def historical_reference_plan(discovery: tuple[str, ...] = DISCOVER, case: str = "exploitable") -> dict:
    """The planning dataset's reference plan, its documents.py references spanning the case's identified target."""
    cases = load_set("test_planning", "development", "python")
    plan = next(c for c in cases if c.name == "path_traversal_unguarded").oracle["reference_plan"]
    end = target_end(case)

    def span(references):
        return [r | {"end_line": end} if r["path"] == "documents.py" else r for r in references]
    plan = plan | {"discovery_command": list(discovery), "citations": span(plan["citations"]),
                   **{test: plan[test] | {"source_references": span(plan[test]["source_references"])}
                      for test in ("control", "security")}}
    if case in REVIEWED:
        # Safe by absence: the planned safe behavior is that the outside file is never opened, however the call ends.
        plan["security"] = plan["security"] | {"required_behavior": (
            "The call never opens the outside file and never returns its content, however it ends")}
        plan["security_expectation"] = plan["security_expectation"] | {"safe_behavior": "no_file_open"}
    return plan


SPLIT_REFERENCES = Path(__file__).with_name("references-v2")


def split_reviewed_tests(case="exploitable"):
    variant = "contained" if case in REVIEWED else "default"
    manifest = json.loads((SPLIT_REFERENCES / "manifest.json").read_text())
    result = {}
    for role in ("control", "exploit"):
        source = SPLIT_REFERENCES / f"{variant}-{role}.py"
        if _digest(source.read_bytes()) != manifest[source.name]:
            raise ValueError("reviewed split fixture differs from frozen manifest")
        result[f"test_{role}.py"] = source
    return result


def reference_plan(discovery=DISCOVER, case="exploitable"):
    """Explicit split-v2 projection of the historical witness fixture plan."""
    plan = historical_reference_plan(discovery, case)
    for role, filename in (("control", "test_control.py"), ("security", "test_exploit.py")):
        spec = dict(plan[role])
        spec["test_path"] = filename
        spec["test_id"] = filename + "::" + spec["test_id"].split("::")[-1]
        spec.pop("witness", None)
        spec["observation"] = {
            "kind": "return_value", "property": ("Ordinary document contents" if role == "control" else "Outside content is never returned"),
            "seam": "Existing imported documents.read_document interface",
        }
        if role == "security":
            spec["required_behavior"] = "The existing production call must not return the readable outside sentinel; only the precise confinement ValueError may be accepted"
        plan[role] = spec
    return plan


def _scripted_probe(role, case="exploitable"):
    path = f"test_{role}.py"
    content = split_reviewed_tests(case)[path].read_text()
    import ast
    # Fixture preparation derives assertion anchors; this is not runtime admission policy.
    assertion_lines = [node.lineno for node in ast.walk(ast.parse(content)) if isinstance(node, ast.Assert)]
    steps = [ToolCallPart("read_source", {"path": "documents.py"}),
             ToolCallPart("read_source", {"path": "test_existing.py"}),
             ToolCallPart("write_test_file", {"path": path, "content": content})]
    async def respond(messages, info):
        activation = load_skills(messages, info, ("control-probe" if role == "control" else "exploit-probe", "native-probe-boundary"))
        if activation is not None:
            return activation
        done = sum(isinstance(part, ToolReturnPart) and part.tool_name in {"read_source", "write_test_file"} for message in messages for part in message.parts)
        if done < len(steps):
            step = steps[done]
            return ModelResponse(parts=[ToolCallPart(step.tool_name, step.args, tool_call_id=f"{role}-{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"draft": {
            "status": "drafted", "assertion_lines": assertion_lines,
            "limitations": ["Frozen split-v2 witness reference; drafting performs no execution"]}})])
    return FunctionModel(respond)


def scripted_control_authoring(case="exploitable"):
    return _scripted_probe("control", case)


def scripted_exploit_authoring(case="exploitable"):
    return _scripted_probe("exploit", case)


def scripted_planning(discovery: tuple[str, ...] = DISCOVER, case: str = "exploitable") -> FunctionModel:
    """The reference plan for the environment whose discovery command is ``discovery``."""
    return _reads_then(["documents.py", "test_existing.py"], lambda info: {"plan": reference_plan(discovery, case)}, skills=("plan-two-tests",))


# Assertion lines of test_security_rejects_outside_read in the reviewed bytes, as the authoring dataset records.
HISTORICAL_SECURITY_ASSERTION_LINES = [64, 65, 66]
SECURITY_ASSERTION_LINES = [9, 14, 15]


def scripted_authoring(case: str = "exploitable") -> FunctionModel:
    """Historical single-author fixture helper; unused by current split composition."""
    path, lines = reviewed_test(case)
    reviewed = path.read_text()
    steps = [ToolCallPart("read_source", {"path": "documents.py"}), ToolCallPart("read_source", {"path": "test_existing.py"}),
             ToolCallPart("write_test_file", {"path": REVIEWED_TEST, "content": reviewed}), ToolCallPart("run_tests", {})]

    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(steps):
            step = steps[done]
            return ModelResponse(parts=[ToolCallPart(step.tool_name, step.args, tool_call_id=f"author-{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": {
            "status": "patch", "security_assertion_lines": lines,
            "limitations": ["Development runs observe discovery and the control only"]}})])
    return FunctionModel(respond)


INVENTORY = re.compile(r"(?P<item>[a-z0-9][a-z0-9_.-]*) \(kind (?P<kind>\w+), (?:(?P<revision>baseline|candidate) run \d+, )?lines 1\.\.(?P<lines>\d+)\)")


def scripted_assessment(execution="completed", finding="inconclusive", fix="not_verified") -> FunctionModel:
    """Reads every inventory item once and proposes the given triple, citing each revision's witness item when
    one is listed (the assessor's grounding rule), else its first item, at line 1."""
    async def respond(messages, info):
        activation = load_skills(messages, info, ("assess-evidence",))
        if activation is not None:
            return activation
        prompt = next(part.content for message in messages for part in message.parts if part.part_kind == "user-prompt")
        items = [match.groupdict() for match in INVENTORY.finditer(prompt)]
        reads = [part.content for message in messages for part in message.parts
                 if isinstance(part, ToolReturnPart) and part.tool_name == "read_evidence"]
        for item in items:
            end = max((read.end_line for read in reads if read.item_id == item["item"]), default=0)
            if end < int(item["lines"]):
                return ModelResponse(parts=[ToolCallPart("read_evidence", {"item_id": item["item"], "start_line": end + 1})])
        pre_execution = prompt.startswith("Pre-execution")
        def anchor(item):
            return {"item_id": item["item"], "start_line": 1, "end_line": min(80, int(item["lines"]))}
        def frozen_text(item):
            lines = {line.number: line.text for read in reads if read.item_id == item["item"] for line in read.lines}
            return "\n".join(lines[number] for number in sorted(lines))
        def exact(item, start, end=None):
            return {"item_id":item["item"],"start_line":start,"end_line":start if end is None else end}
        def review(revision):
            import ast
            source = next(item for item in items if item["kind"] == "source" and item["revision"] == revision)
            source_definition = next(node for node in ast.parse(frozen_text(source)).body
                                     if isinstance(node,ast.FunctionDef) and node.name=="read_document")
            definition = exact(source,source_definition.lineno,source_definition.end_lineno)
            plan = next(item for item in items if item["item"] == "test-plan")
            issue = next(item for item in items if item["item"] == "reported-condition")
            def probe(role):
                spec = reference_plan()[role]
                test_name = spec["test_id"].split("::")[-1]
                matching = []
                for item in items:
                    if item["kind"] != "patch":
                        continue
                    tree = ast.parse(frozen_text(item))
                    for node in tree.body:
                        if isinstance(node,ast.FunctionDef) and node.name==test_name:
                            matching.append((item,tree,node))
                if len(matching)!=1:
                    raise ValueError("reviewed fixture requires one own patch defining each exact native probe")
                patch,tree,test = matching[0]
                imported = next(node for node in tree.body if isinstance(node,ast.Import)
                                and any(alias.name=="documents" for alias in node.names))
                call = next(node for node in ast.walk(test) if isinstance(node,ast.Call)
                            and isinstance(node.func,ast.Attribute) and node.func.attr=="read_document"
                            and isinstance(node.func.value,ast.Name) and node.func.value.id=="documents")
                actual_input = call.args[1].value
                expected_input = "document.txt" if role=="control" else "../outside.txt"
                if actual_input != expected_input:
                    raise ValueError("reviewed fixture call differs from the actual planned benign/adversarial input")
                call_site=exact(patch,call.lineno,call.end_lineno)
                import_site=exact(patch,imported.lineno,imported.end_lineno)
                assertions=[node for node in ast.walk(test) if isinstance(node,ast.Assert)]
                property_assertions=[node for node in assertions if role=="control"
                                     or not (isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Call)
                                             and isinstance(node.test.left.func,ast.Attribute)
                                             and node.test.left.func.attr=="read_text")]
                binding={"statement":"The exact own-file call imports the captured documents implementation",
                         "citations":[import_site,call_site,definition]}
                property_evidence={"statement":"The own-file literal input, prepared readable fixture and relevant property assertions match the stated condition",
                    "citations":[call_site,*[exact(patch,node.lineno,node.end_lineno) for node in property_assertions],anchor(plan),anchor(issue)]}
                return {"test_id":spec["test_id"],
                    "production_binding":{"called_symbol":"read_document","status":"production","call_site":call_site,
                                          "definition_site":definition,"evidence":binding},
                    "input_exercise":{"observed_input":actual_input,"status":"benign" if role=="control" else "reported_adversarial",
                                      "preconditions":"established","evidence":property_evidence},
                    "assertion":{"asserted_property":"Benign sentinel returned" if role=="control" else "Outside sentinel not returned; only the precise confinement ValueError is accepted",
                                 "status":"benign_behavior" if role=="control" else "security_property","evidence":property_evidence},
                    "dependencies":{"substitutions":[],"scope":"none","evidence":binding}}
            return {"revision":revision,"control":probe("control"),"exploit":probe("security")}

        def cite(revision):
            ordered = sorted((i for i in items if i["revision"] == revision), key=lambda i: i["kind"] != "witness")
            item = ordered[0]
            return {"item_id": item["item"], "start_line": 1, "end_line": 1}
        # A case without a fix commit lists no candidate items; cite only the revisions that ran.
        ran = [revision for revision in ("baseline", "candidate") if any(i["revision"] == revision for i in items)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "execution": "unknown" if pre_execution else execution, "finding": "inconclusive" if pre_execution else finding, "fix": "not_applicable" if pre_execution else fix,
            "application_observations": [
                {"statement": f"{revision.capitalize()} run evidence for the planned tests",
                 "citations": [cite(revision)]} for revision in ran] if not pre_execution else [],
            "sandbox_observations": [],
            "interpretation": {"statement": "Exact own-file source bindings and property assertions reviewed before execution" if pre_execution else "Native observations and frozen unit review support the scoped disposition",
                               "citations": [cite(revision) for revision in ran]},
            "limitations": ["Reviewed split-v2 component property only"],
            "validity_reviews": [review(revision) for revision in ran] if pre_execution else []})])
    return FunctionModel(respond)
