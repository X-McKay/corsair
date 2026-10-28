"""The installed wheel, not checkout-relative files, is the deployment artifact."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path


def test_built_wheel_includes_agent_metadata_instructions_and_risk(tmp_path):
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path / "dist")],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next((tmp_path / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert not any(name.startswith("tests/") for name in archive.namelist())
        assert "corsair/cli.py" not in archive.namelist()
        assert not any(
            name.startswith(("corsair/runtime/", "corsair/tools/", "corsair/policy/"))
            for name in archive.namelist()
        )
    installed = tmp_path / "installed"
    subprocess.run(
        ["uv", "venv", str(installed), "--python", sys.executable],
        check=True,
        capture_output=True,
        text=True,
    )
    python = installed / "bin/python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    child = subprocess.run(
        [
            str(python),
            "-c",
            """
from importlib.resources import files
from pathlib import Path
import corsair
from corsair.adapters.scm.requests import normalize_request_sources
from corsair.adapters.temporal.client import connect, wait_for_result
from corsair.agents.resources import (
    load_agent_spec,
    load_runtime_skills,
    mechanical_tools_digest,
    prompt_text,
    runtime_skill_digest,
)
from corsair.entrypoints.terminal import Terminal
from corsair.observability.logging import LifecycleLoggingInterceptor
from corsair.entrypoints.cli import parser
from corsair.entrypoints.api import start_investigation, start_evaluation, start_issue_investigation
from corsair.contracts import IssueInvestigationRequest, IssueInvestigationResult
from corsair.workflows.pipeline import IssueInvestigationWorkflow
from corsair.entrypoints.requests import load_investigation_request
from corsair.ports.inference import InferencePort
from corsair.contracts.agents import Submission
from corsair.contracts import AssessmentOutcome, JavaRecipe, JavaScriptRecipe
assert Path(corsair.__file__).is_relative_to(Path('installed').resolve()), corsair.__file__
for role in ('producer', 'auditor', 'intake'):
    assert load_agent_spec(role).name == role
    assert len(prompt_text(role)) > 100
    assert len(runtime_skill_digest(role)) == 64
assert [skill.name for skill in load_runtime_skills('intake')] == ['image-selection']
assert files('corsair.agents.intake').joinpath('skills/image-selection/SKILL.md').is_file()
assert files('corsair.agents.intake.tools').joinpath('compare_images.py').is_file()
from corsair.agents.intake.contracts import IntakeProposal as RoleIntakeProposal
from corsair.contracts import IntakeProposal
from corsair.entrypoints.api import start_intake
assert RoleIntakeProposal is IntakeProposal
assert callable(start_intake)
from corsair.contracts import ExecutionRequest, ExecutionResult, TestPlan, PlanAudit
from corsair.agents.producer.contracts import TestPlan as RoleTestPlan
from corsair.agents.auditor.contracts import PlanAudit as RolePlanAudit
from corsair.adapters.inference.execution import execution_resources_digest
from corsair.entrypoints.api import start_execution
assert RoleTestPlan is TestPlan and RolePlanAudit is PlanAudit
assert len(execution_resources_digest()) == 64
assert callable(start_execution)
assert 'recipe' not in ExecutionRequest.model_fields
assert ExecutionResult(run_id='installed',case_id='installed').security_assessment == 'UNRESOLVED'
for role in ('producer','auditor'):
    assert files('corsair.agents.'+role).joinpath('execution.json').is_file()
    assert files('corsair.agents.'+role+'.instructions').joinpath('execution.md').is_file()
assert files('corsair.adapters.sandboxing').joinpath('inspection_reader.py').is_file()
assert [skill.name for skill in load_runtime_skills('producer')] == ['source-grounding']
assert [skill.name for skill in load_runtime_skills('auditor')] == ['semantic-review']
assert files('corsair.agents.producer').joinpath('skills/source-grounding/SKILL.md').is_file()
assert files('corsair.agents.auditor').joinpath('skills/semantic-review/SKILL.md').is_file()
assert load_agent_spec('producer').mechanical_tools == ['preview_invocation', 'relative_path']
assert len(mechanical_tools_digest()) == 64
for name in ('preview_invocation', 'relative_path'):
    assert files('corsair.agents.producer.tools').joinpath(name + '.py').is_file()
assert 'pilot risk' in files('corsair.policies').joinpath('risk.md').read_text().lower()
assert files('corsair.adapters.sandboxing').joinpath('driver.py').is_file()
assert files('corsair.adapters.sandboxing').joinpath('node/driver.mjs').is_file()
assert files('corsair.adapters.sandboxing').joinpath('node/probe.test.mjs').is_file()
assert files('corsair.adapters.sandboxing').joinpath('java/Driver.java').is_file()
assert files('corsair.adapters.sandboxing').joinpath('java/SecretDisclosureProbe.java').is_file()
assert JavaScriptRecipe(module_file='reader.mjs', function='read').kind.startswith('javascript.')
java_recipe = JavaRecipe(module_file='Gate.java', class_name='Gate', function='read')
assert java_recipe.kind.startswith('java.')
assert AssessmentOutcome.NOT_DEMONSTRATED.value == 'NOT_DEMONSTRATED'
assert parser().parse_args(['report', 'report.json']).command == 'report'
assert callable(load_investigation_request)
assert callable(start_issue_investigation)
assert IssueInvestigationRequest.model_fields["intake"]
assert IssueInvestigationResult.model_fields["stop_reason"]
assert callable(IssueInvestigationWorkflow.run)
assert callable(normalize_request_sources)
print('Installed-wheel resources verified outside checkout')
""",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert "Installed-wheel resources" in child.stdout
    console = subprocess.run(
        [str(installed / "bin/corsair"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert console.returncode == 0, console.stdout + console.stderr
    assert "investigate" in console.stdout
    assert "doctor" in console.stdout and "--format" in console.stdout
    report = tmp_path / "report.json"
    report.write_text('{"summary": {"attempts": 1, "passed": 1}}')
    command = subprocess.run(
        [str(installed / "bin/corsair"), "report", str(report), "--format", "json"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert command.returncode == 0, command.stderr
    assert '"passed": 1' in command.stdout
    assert "\x1b" not in command.stdout
