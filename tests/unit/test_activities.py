"""Activity heartbeats keep flowing while a blocking port call runs in a worker thread."""

from __future__ import annotations

import time
from pathlib import Path

from temporalio.testing import ActivityEnvironment

from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Case,
    Finding,
    InvestigationRequest,
    PreparedCase,
    PythonRecipe,
    RunManifest,
    Source,
)
from corsair.settings import Settings
from corsair.steps import activities as activities_module
from corsair.steps.activities import Activities

READER = (
    "from pathlib import Path\n\n"
    "def read_file(root, path):\n"
    "    return (Path(root) / path).read_text()\n"
)
BLOCKED_SECONDS = 0.3
INTERVAL_SECONDS = 0.02


class _SlowSandbox:
    """Resolves the image only after blocking, as a slow Docker daemon would."""

    def __init__(self, beats: list[tuple]):
        self.beats = beats
        self.during: list[tuple] = []

    def image_id_for(self, kind: str) -> str:
        del kind
        start = len(self.beats)
        time.sleep(BLOCKED_SECONDS)
        self.during = self.beats[start:]
        return "sha256:" + "a" * 64


class _SlowSources(LocalSourceSnapshots):
    """Admits the source only after blocking, as a large snapshot would."""

    def __init__(self, settings: Settings, store: ArtifactStore, beats: list[tuple]):
        super().__init__(settings, store)
        self.beats = beats
        self.during: list[tuple] = []

    def prepare(self, case: Case, manifest: RunManifest) -> PreparedCase:
        start = len(self.beats)
        time.sleep(BLOCKED_SECONDS)
        self.during = self.beats[start:]
        return super().prepare(case, manifest)


async def test_prepare_heartbeats_while_its_blocking_calls_run(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        activities_module, "HEARTBEAT_INTERVAL_SECONDS", INTERVAL_SECONDS, raising=False
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / "reader.py").write_text(READER, encoding="utf-8")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    beats: list[tuple] = []
    sandbox = _SlowSandbox(beats)
    sources = _SlowSources(settings, store, beats)
    activities = Activities(
        settings,
        store=store,
        inference=None,  # ty: ignore[invalid-argument-type]
        sources=sources,
        sandbox=sandbox,  # ty: ignore[invalid-argument-type]
    )
    request = InvestigationRequest(
        case=Case(
            case_id="slow-prepare",
            finding=Finding(title="read", description="test", file="reader.py", line=4),
            source=Source(path="project"),
            recipe=PythonRecipe(
                module_file="reader.py",
                function="read_file",
                payload_parameter="path",
                fixed_kwargs={"root": "/fixtures/allowed"},
            ),
        )
    )
    environment = ActivityEnvironment()
    environment.on_heartbeat = lambda *details: beats.append(details)

    prepared = await environment.run(activities.prepare, request)

    assert prepared.case_id == "slow-prepare"
    # Each blocked call spans many intervals; a single heartbeat before it would leave
    # the activity silent past its heartbeat timeout.
    assert len(sandbox.during) >= 3
    assert len(sources.during) >= 3
