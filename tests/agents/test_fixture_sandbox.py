"""E2E-0 over the OpenShell test workspace with fake sandbox ports: each purpose gets a fresh sandbox."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell_workspace import WorkspaceConfig
from corsair.composition.direct import StageModels, run_direct
from corsair.ports.artifacts import SourceFile, SourceSnapshot
from corsair.ports.execution import ExecutionReceipt
from evals.fixture_e2e import run as cli
from evals.fixture_e2e.case import (FIXTURE, scripted_assessment, scripted_authoring, scripted_identification,
                                    scripted_planning)
from evals.fixture_e2e.sandbox import DISCOVER, PYTHON, sandbox_case, sandbox_runners
from tests.unit.test_test_workspace import Lifecycle, Upload, Verifier

CONTROL = "test_documents.py::test_benign_control"
SECURITY = "test_documents.py::test_security_rejects_outside_read"
LIMITS = {"memory": "512Mi", "timeout_seconds": 120}


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


@pytest.fixture
def store(tmp_path):
    (tmp_path / "objects").mkdir(mode=0o700)
    with LocalArtifacts(tmp_path / "objects", max_bytes=1024 * 1024) as artifacts:
        yield artifacts


class Sandboxes(Lifecycle):
    """Deleting the sandbox removes its filesystem, so each prepare sees an absent root."""
    def __init__(self, root):
        super().__init__()
        self.root = root

    def delete(self, handle, operation):
        super().delete(handle, operation)
        shutil.rmtree(self.root, ignore_errors=True)


class SandboxRun:
    """Test-only stand-in for in-sandbox execution: the operator argv with interpreter and scratch localized."""
    def __init__(self, root, scratch):
        self.root, self.scratch, self.commands = root, scratch, []

    def execute(self, handle, command, operation):
        self.commands.append(command)
        argv = [sys.executable if t == PYTHON else str(self.scratch) if t == "/tmp/corsair-scratch" else t
                for t in command]
        argv = [t.replace("/tmp/corsair-junit.xml", str(self.scratch.parent / "junit.xml")) for t in argv]
        started = time.monotonic()
        done = subprocess.run(argv, cwd=self.root, env={"PATH": os.environ["PATH"]}, capture_output=True, timeout=60)
        return ExecutionReceipt(str(operation), handle, "local", time.monotonic() - started, "acknowledged",
                                "terminal_observed", "terminal", stdout=done.stdout, stderr=done.stderr,
                                native_exit=done.returncode, worker_cleanup="confirmed")


def snapshots(store):
    def capture(variant):
        source = (FIXTURE / variant / "documents.py").read_bytes()
        entry = SourceFile("documents.py", "100644", "0" * 40, store.put(source))
        return SourceSnapshot("1" * 40, "2" * 40, (entry,), store.put(f"manifest {variant}".encode()))
    return {variant: capture(variant) for variant in ("vulnerable", "fixed")}


def sandbox(store, tmp_path):
    staging, remote = tmp_path / "staging", tmp_path / "remote"
    staging.mkdir(mode=0o700); remote.mkdir(mode=0o700)
    config = WorkspaceConfig(staging, str(remote), "workspace", PYTHON)
    lifecycle, execution = Sandboxes(Path(config.remote_root)), SandboxRun(config.remote_root, tmp_path / "scratch")
    captured = snapshots(store)
    runners = sandbox_runners(lifecycle, Verifier(), execution, Upload(), store, captured, config)
    return sandbox_case(captured, "sha256:" + "a" * 64, LIMITS), runners, lifecycle, execution


def stages(**overrides):
    values = dict(identification=scripted_identification(), planning=scripted_planning(DISCOVER),
                  authoring=scripted_authoring(), assessment=scripted_assessment())
    return StageModels(**(values | overrides))


def test_scripted_chain_runs_every_purpose_in_a_fresh_sandbox(store, tmp_path):
    case, runners, lifecycle, execution = sandbox(store, tmp_path)
    run = asyncio.run(run_direct(case, stages(), runners))
    assert (run.stopped_at, run.reason) == (None, "complete")
    assert [c[0] for c in lifecycle.calls].count("create") == 3 == [c[0] for c in lifecycle.calls].count("delete")
    baseline, candidate = run.executions
    assert baseline.observed.workspace.source.sha256 == case.revision_sources["baseline"]
    assert candidate.observed.workspace.source.sha256 == case.revision_sources["candidate"]
    assert [c.outcome for c in baseline.observed.execution.cases] == ["passed", "failed"]
    assert [c.outcome for c in candidate.observed.execution.cases] == ["passed", "passed"]
    assert all(e.observed.cleanup == "confirmed" for e in run.executions)
    assert (run.gate.permitted.execution, run.gate.permitted.finding, run.gate.permitted.fix) == (
        "completed", "inconclusive", "not_verified")
    assert all(command[:len(DISCOVER)] == DISCOVER for command in execution.commands if "--collect-only" in command)


def test_model_authored_test_bytes_reach_the_sandbox_not_the_host(store, tmp_path):
    """Unlike the reviewed host workspace, an author's own test is delivered and run in the sandbox."""
    case, runners, lifecycle, execution = sandbox(store, tmp_path)
    own = ("import documents\n\n\ndef test_benign_control():\n    assert documents\n\n\n"
           "def test_security_rejects_outside_read():\n    assert documents\n")
    steps = [ToolCallPart("write_test_file", {"path": "test_documents.py", "content": own}), ToolCallPart("run_tests", {})]

    async def respond(messages, info):
        done = sum(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if done < len(steps):
            return ModelResponse(parts=[ToolCallPart(steps[done].tool_name, steps[done].args, tool_call_id=f"s{done}")])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": {
            "status": "blocked", "layer": "unknown", "reason": "stop after one development run"}})])
    run = asyncio.run(run_direct(case, stages(authoring=FunctionModel(respond)), runners))
    assert run.stopped_at == "authoring" and run.reason.startswith("authoring blocked at unknown"), run.reason
    assert [c[0] for c in lifecycle.calls] == ["create", "wait_ready", "delete"]
    assert any("--collect-only" in command for command in execution.commands)


def test_record_run_keeps_the_sandbox_route_and_environment(store, tmp_path):
    case, runners, _, _ = sandbox(store, tmp_path)
    evidence = tmp_path / "evidence"; evidence.mkdir(mode=0o700)
    run = asyncio.run(cli.record_run(evidence, (), None, case, runners, {"route": "openshell_test_workspace"}))
    configuration = json.loads((evidence / "configuration.json").read_text())
    assert configuration["runner"] == {"route": "openshell_test_workspace"}
    assert configuration["environment"]["discovery_command"] == list(DISCOVER)
    assert configuration["revision_sources"] == case.revision_sources
    assert [e["purpose"] for e in json.loads((evidence / "native-runs.json").read_text())] == [
        "development", "baseline", "candidate"]
    assert cli.summary(run)["gate"] == {"execution": "completed", "finding": "inconclusive", "fix": "not_verified"}
