"""Actual Docker process evidence, limits and immutable replay behavior."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from corsair.adapters.sandboxing.execution import DockerExecutor
from corsair.adapters.sandboxing.images import discover_images
from corsair.adapters.scm.local import snapshot_source
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Source, digest
from corsair.contracts.execution import ExecutionRequest, PreparedExecution
from corsair.contracts.execution import TestPlan as Plan
from corsair.contracts.intake import Issue
from corsair.settings import Settings

pytestmark = pytest.mark.docker


def test_actual_execution_is_bounded_and_cleanup_is_recorded():
    root = Path(__file__).resolve().parents[2]
    scratch = root / ".work"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="execution-native-", dir=scratch) as directory:
        workspace = Path(directory)
        repository = workspace / "repository"
        repository.mkdir()
        (repository / "reader.py").write_text("def answer():\n    return 42\n")
        settings = Settings(source_root=str(workspace), artifact_root=str(workspace / "artifacts"))
        store = ArtifactStore(settings.artifact_root)
        image = next(i for i in discover_images(settings).images if i.language == "python")
        request = ExecutionRequest(
            case_id="native",
            issue=Issue(title="Inspect answer"),
            source=Source(path=str(repository)),
            image=image,
        )
        source = snapshot_source(request.source, settings, store)
        prepared = PreparedExecution(
            run_id="native",
            request=request,
            source=source,
            config_digest=settings.identity,
            request_digest=digest(request),
            resources_digest="0" * 64,
        )
        executor = DockerExecutor(settings, store)
        for code, expected, error in [
            (
                (
                    "import sys; sys.path.insert(0, '/source'); from reader import answer; "
                    "print(answer()); print('err', file=sys.stderr)"
                ),
                "SUCCEEDED",
                None,
            ),
            ("open('/source/reader.py','w').write('changed')", "FAILED", None),
            ("import time; time.sleep(30)", "ERROR", "TIMEOUT"),
            ("while True: print('x'*10000)", "ERROR", "OUTPUT_LIMIT"),
        ]:
            plan = Plan(
                hypothesis="Native process check",
                revision=1,
                locations=[{"path": "reader.py"}],
                files=[{"path": "test.py", "content": code}],
                commands=[{"argv": ["python", "/work/test.py"], "timeout_seconds": 2}],
            )
            identity = f"exec-{uuid4().hex}"
            result = executor.execute(prepared, plan, identity, timeout_seconds=15)
            assert result.outcome == expected, result
            assert result.error == error
            assert result.cleanup_confirmed
            assert result.container_id
            assert executor.execute(prepared, plan, identity) == result
            if expected == "SUCCEEDED":
                assert store.get(result.receipts[0].stdout) == b"42\n"
                assert store.get(result.receipts[0].stderr) == b"err\n"
        assert (repository / "reader.py").read_text() == "def answer():\n    return 42\n"


@pytest.mark.parametrize("language", ["javascript", "java"])
def test_generic_language_tools_use_unchanged_source(language):
    scratch = Path(__file__).resolve().parents[2] / ".work"
    with TemporaryDirectory(prefix="execution-language-", dir=scratch) as directory:
        root = Path(directory)
        repository = root / "repository"
        repository.mkdir()
        if language == "javascript":
            name = "reader.mjs"
            source = "export function answer() { return 42; }\n"
            files = [
                {
                    "path": "check.mjs",
                    "content": "import {answer} from '/source/reader.mjs'; console.log(answer());",
                }
            ]
            commands = [{"argv": ["node", "/work/check.mjs"], "timeout_seconds": 10}]
        else:
            name = "Gate.java"
            source = "public class Gate { public static int answer() { return 42; } }\n"
            files = [
                {
                    "path": "Check.java",
                    "content": (
                        "public class Check { public static void main(String[] args) { "
                        "System.out.println(Gate.answer()); } }"
                    ),
                }
            ]
            commands = [
                {"argv": ["cp", "/source/Gate.java", "/work/Gate.java"], "timeout_seconds": 10},
                {
                    "argv": ["javac", "-proc:none", "/work/Gate.java", "/work/Check.java"],
                    "timeout_seconds": 10,
                },
                {"argv": ["java", "-cp", "/work", "Check"], "timeout_seconds": 10},
            ]
        (repository / name).write_text(source)
        settings = Settings(
            source_root=str(root),
            artifact_root=str(root / "artifacts"),
            node_image=os.environ.get("CORSAIR_TEST_NODE_IMAGE", "corsair-node:0.1"),
            java_image=os.environ.get("CORSAIR_TEST_JAVA_IMAGE", "corsair-java:0.1"),
        )
        store = ArtifactStore(settings.artifact_root)
        image = next(
            (item for item in discover_images(settings).images if item.language == language), None
        )
        if image is None:
            pytest.skip(f"configured local {language} execution image unavailable")
        request = ExecutionRequest(
            case_id="language",
            issue=Issue(title="Inspect answer"),
            source=Source(path=str(repository)),
            image=image,
        )
        snapshot = snapshot_source(request.source, settings, store)
        prepared = PreparedExecution(
            run_id="language",
            request=request,
            source=snapshot,
            config_digest=settings.identity,
            request_digest=digest(request),
            resources_digest="0" * 64,
        )
        proposal = Plan(
            hypothesis="Exercise unchanged source with installed tools",
            revision=1,
            files=files,
            commands=commands,
            locations=[{"path": name}],
        )
        observed = DockerExecutor(settings, store).execute(
            prepared, proposal, f"lang-{uuid4().hex}", timeout_seconds=30
        )
        assert observed.outcome == "SUCCEEDED", observed
        assert observed.cleanup_confirmed
        assert store.get(observed.receipts[-1].stdout) == b"42\n"
        assert (repository / name).read_text() == source
