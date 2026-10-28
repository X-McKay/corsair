"""One immutable-ID, read-only Docker inspection session per intake episode."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from docker.errors import NotFound

from corsair.adapters.scm.local import iter_snapshot_files
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts.intake import PreparedIntake
from corsair.settings import Settings


class DockerInspection:
    def __init__(
        self, settings: Settings, store: ArtifactStore, prepared: PreparedIntake, client: Any
    ):
        self.settings = settings
        self.store = store
        self.prepared = prepared
        self.client = client
        self.container: Any = None
        self.container_id: str | None = None
        self.staging: TemporaryDirectory[str] | None = None
        self.image_id: str | None = None

    def __enter__(self) -> DockerInspection:
        labels = {"corsair.intake": self.prepared.run_id}
        if self.client.containers.list(
            all=True, filters={"label": [f"corsair.intake={self.prepared.run_id}"]}
        ):
            raise RuntimeError("unreconciled inspection container; refusing retry")
        image = self.client.images.get(self.settings.intake_image)
        self.image_id = str(image.id)
        staging_root = Path(self.settings.artifact_root) / ".inspection"
        staging_root.mkdir(parents=True, exist_ok=True)
        self.staging = TemporaryDirectory(prefix="intake-", dir=staging_root)
        root = Path(self.staging.name).absolute()
        os.chmod(root, 0o755)
        try:
            for relative, content in iter_snapshot_files(self.prepared.source, self.store):
                path = root.joinpath(*relative.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(0o444)
            self.container = self.client.containers.create(
                self.image_id,
                command=["python", "-I", "-c", "import time; time.sleep(3600)"],
                entrypoint=[],
                network_mode="none",
                read_only=True,
                user="1000:1000",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit=self.settings.memory_limit,
                nano_cpus=self.settings.nano_cpus,
                pids_limit=self.settings.pids_limit,
                runtime=self.settings.runtime,
                volumes={str(root): {"bind": "/source", "mode": "ro"}},
                labels=labels,
                working_dir="/",
                environment={"PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.container_id = str(self.container.id)
            self.container.start()
            return self
        except BaseException:
            self.close()
            raise

    def read(self, operation: str, relative: str = "") -> dict:
        if self.container is None:
            raise RuntimeError("inspection session is not open")
        result = self.container.exec_run(
            [
                "python",
                "-I",
                "/opt/corsair/inspection_reader.py",
                operation,
                relative,
                str(self.prepared.request.budget.tool_output_bytes),
            ],
            user="1000:1000",
            workdir="/",
        )
        if (
            result.exit_code != 0
            or len(result.output) > self.prepared.request.budget.tool_output_bytes * 6 + 1024
        ):
            raise RuntimeError("inspection reader failed or exceeded its output bound")
        payload = json.loads(result.output)
        if not isinstance(payload, dict):
            raise ValueError("invalid inspection response")
        return payload

    def close(self) -> None:
        if self.container_id is not None:
            try:
                container = self.client.containers.get(self.container_id)
                container.remove(force=True)
            except NotFound:
                pass
            try:
                self.client.containers.get(self.container_id)
            except NotFound:
                self.container_id = None
            else:
                raise RuntimeError("inspection cleanup is uncertain")
        if self.staging is not None:
            self.staging.cleanup()
            self.staging = None

    def __exit__(self, *_exc: object) -> None:
        self.close()


@asynccontextmanager
async def inspection_session(session: Any) -> AsyncGenerator[DockerInspection]:
    """Let heartbeats progress and reconcile setup before cancellation cleanup."""
    setup = asyncio.create_task(asyncio.to_thread(session.__enter__))
    try:
        await asyncio.shield(setup)
    except BaseException:
        await asyncio.gather(setup, return_exceptions=True)
        await asyncio.to_thread(session.close)
        raise
    try:
        yield session
    finally:
        cleanup = asyncio.create_task(asyncio.to_thread(session.close))
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise
