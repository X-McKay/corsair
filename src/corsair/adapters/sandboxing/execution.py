"""Generic test execution inside a configured container; host code records process facts."""

from __future__ import annotations

import io
import socket
import struct
import tarfile
import time
from contextlib import closing, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any, Literal

import docker
from docker.errors import NotFound

from corsair.adapters.sandboxing.images import recheck_image
from corsair.adapters.scm.local import iter_snapshot_files
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import digest
from corsair.contracts.execution import (
    CommandReceipt,
    PreparedExecution,
    ProcessObservation,
    TestFile,
    TestPlan,
)
from corsair.settings import Settings


@dataclass(frozen=True)
class StreamCapture:
    stdout: bytes
    stderr: bytes
    state: Literal["completed", "timeout", "output_limit", "error"]
    truncated: bool = False


def capture_exec(sock: Any, deadline: float, limit: int) -> StreamCapture:
    """Parse Docker's non-TTY frames incrementally, bounding bytes before allocation."""
    output = [bytearray(), bytearray()]

    def read(count: int, *, eof: bool = False) -> bytes:
        data = bytearray()
        while len(data) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            sock.settimeout(min(remaining, 1.0))
            try:
                chunk = sock.recv(min(count - len(data), 65536))
            except TimeoutError:
                continue
            if not chunk:
                if eof and not data:
                    return b""
                raise ValueError("truncated Docker stream")
            data.extend(chunk)
        return bytes(data)

    state: Literal["completed", "timeout", "output_limit", "error"] = "completed"
    try:
        while header := read(8, eof=True):
            stream, size = struct.unpack(">BxxxI", header)
            if stream not in (1, 2):
                raise ValueError("unexpected Docker stream")
            while size:
                left = limit - len(output[0]) - len(output[1])
                if left <= 0:
                    return StreamCapture(bytes(output[0]), bytes(output[1]), "output_limit", True)
                chunk = read(min(size, left, 65536))
                output[stream - 1].extend(chunk)
                size -= len(chunk)
    except TimeoutError:
        state = "timeout"
    except (OSError, ValueError):
        state = "error"
    return StreamCapture(bytes(output[0]), bytes(output[1]), state)


def plan_archive(files: list[TestFile]) -> bytes:
    """Construct regular files and owned directories; never archive host paths."""
    buffer = io.BytesIO()
    directories: set[str] = set()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for file in files:
            for parent in reversed(PurePosixPath(file.path).parents):
                name = str(parent)
                if name == "." or name in directories:
                    continue
                item = tarfile.TarInfo(name)
                item.type = tarfile.DIRTYPE
                item.mode = 0o700
                item.uid = item.gid = 1000
                archive.addfile(item)
                directories.add(name)
            item = tarfile.TarInfo(file.path)
            item.mode = 0o600
            item.uid = item.gid = 1000
            content = file.content.encode()
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    return buffer.getvalue()


def close_exec_socket(raw: Any) -> None:
    sock = getattr(raw, "_sock", raw)
    response = getattr(raw, "_response", None)
    with suppress(OSError, ValueError):
        sock.shutdown(socket.SHUT_RDWR)
    for resource in (raw, sock if sock is not raw else None, response):
        if resource is not None:
            with suppress(OSError, ValueError):
                resource.close()


def materialize_tests(client: Any, container_id: str, archive: bytes, deadline: float) -> None:
    """Feed a safe archive to fixed tar inside tmpfs; Docker archive API rejects read-only roots."""
    execution = client.api.exec_create(
        container_id,
        ["tar", "-x", "-f", "-", "-C", "/work"],
        stdin=True,
        stdout=True,
        stderr=True,
        tty=False,
        user="1000:1000",
        workdir="/work",
    )
    raw = client.api.exec_start(execution["Id"], socket=True, tty=False)
    try:
        sock = getattr(raw, "_sock", raw)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        sock.settimeout(min(remaining, 15))
        sock.sendall(archive)
        sock.shutdown(socket.SHUT_WR)
        captured = capture_exec(sock, deadline, 4096)
    finally:
        close_exec_socket(raw)
    status = client.api.exec_inspect(execution["Id"])
    if captured.state != "completed" or status.get("Running") or status.get("ExitCode") != 0:
        raise RuntimeError("sandbox test materialization failed")


class DockerExecutor:
    def __init__(self, settings: Settings, store: ArtifactStore):
        self.settings = settings
        self.store = store

    def execute(
        self,
        prepared: PreparedExecution,
        plan: TestPlan,
        operation_id: str,
        *,
        fixed: bool = False,
        timeout_seconds: int | None = None,
    ) -> ProcessObservation:
        # Revalidate even typed calls; model_copy can bypass Pydantic validation.
        plan = TestPlan.model_validate(plan.model_dump())
        prepared = PreparedExecution.model_validate(prepared.model_dump())
        source = prepared.fixed_source if fixed else prepared.source
        if source is None:
            raise ValueError("fixed source was not admitted")
        intent = self.store.put_json(
            {
                "prepared": digest(prepared),
                "plan": digest(plan),
                "fixed": fixed,
                "operation_id": operation_id,
            }
        )
        committed = self.store.reconcile(f"execution.{operation_id}")
        if committed is not None:
            observation = ProcessObservation.model_validate(self.store.get_json(committed))
            if (observation.source_digest, observation.plan_digest, observation.image_id) != (
                source.sha256,
                digest(plan),
                prepared.request.image.image_id,
            ):
                raise ValueError("operation identity conflict")
            return observation.model_copy(update={"artifact": committed})
        observation = ProcessObservation(
            operation_id=operation_id,
            source_digest=source.sha256,
            image_id=prepared.request.image.image_id,
            plan_digest=digest(plan),
        )
        if not self.store.claim(f"execution-intent.{operation_id}", intent):
            return self.record_observation(
                observation.model_copy(update={"error": "OPERATION_UNCERTAIN"})
            )
        deadline = time.monotonic() + min(
            timeout_seconds or prepared.request.budget.max_elapsed_seconds,
            prepared.request.budget.max_elapsed_seconds,
        )
        staging_root = Path(self.settings.artifact_root) / ".execution"
        staging_root.mkdir(parents=True, exist_ok=True)
        container_id: str | None = None
        creation_attempted = False
        ownership_unknown = False
        error: ProcessObservation | None = None
        try:
            with (
                closing(docker.from_env(timeout=15)) as client,
                TemporaryDirectory(prefix="source-", dir=staging_root) as directory,
            ):
                root = Path(directory).absolute()
                root.chmod(0o755)
                for relative, content in iter_snapshot_files(source, self.store):
                    path = root.joinpath(*relative.split("/"))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                    path.chmod(0o444)
                try:
                    if prepared.config_digest != self.settings.identity:
                        raise ValueError("configuration changed")
                    if not recheck_image(client, prepared.request.image):
                        error = observation.model_copy(
                            update={"outcome": "ERROR", "error": "IMAGE_CHANGED"}
                        )
                    elif client.containers.list(
                        all=True, filters={"label": [f"corsair.execution={operation_id}"]}
                    ):
                        ownership_unknown = True
                        error = observation.model_copy(update={"error": "OPERATION_UNCERTAIN"})
                    else:
                        creation_attempted = True
                        container = client.containers.create(
                            prepared.request.image.image_id,
                            command=["/bin/sh", "-c", "exec sleep 3600"],
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
                            tmpfs={
                                "/work": "rw,nosuid,nodev,size=256m,uid=1000,gid=1000,mode=0700",
                                "/tmp": "rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=0700",
                            },
                            labels={"corsair.execution": operation_id},
                            working_dir="/work",
                            environment={"PYTHONDONTWRITEBYTECODE": "1", "HOME": "/work"},
                        )
                        container_id = str(container.id)
                        observation = observation.model_copy(update={"container_id": container_id})
                        container.start()
                        if plan.files:
                            materialize_tests(
                                client, container_id, plan_archive(plan.files), deadline
                            )
                        receipts = []
                        for command in plan.commands:
                            if time.monotonic() >= deadline:
                                error = observation.model_copy(
                                    update={"outcome": "INCOMPLETE", "error": "TIMEOUT"}
                                )
                                break
                            execution = client.api.exec_create(
                                container_id,
                                command.argv,
                                user="1000:1000",
                                workdir="/work" if command.cwd == "." else f"/work/{command.cwd}",
                                stdout=True,
                                stderr=True,
                                stdin=False,
                                tty=False,
                            )
                            exec_id = str(execution["Id"])
                            raw = client.api.exec_start(exec_id, socket=True, tty=False)
                            try:
                                sock = getattr(raw, "_sock", raw)
                                captured = capture_exec(
                                    sock,
                                    min(
                                        deadline,
                                        time.monotonic() + command.timeout_seconds,
                                        time.monotonic()
                                        + prepared.request.budget.probe_timeout_seconds,
                                    ),
                                    prepared.request.budget.tool_output_bytes,
                                )
                            finally:
                                close_exec_socket(raw)
                            status = client.api.exec_inspect(exec_id)
                            state = captured.state
                            exit_code = status.get("ExitCode")
                            if state == "completed" and (
                                status.get("Running") or not isinstance(exit_code, int)
                            ):
                                state = "error"
                            receipts.append(
                                CommandReceipt(
                                    command_digest=digest(command),
                                    exec_id=exec_id,
                                    state=state,
                                    exit_code=exit_code if state == "completed" else None,
                                    stdout=self.store.put(
                                        captured.stdout, "application/octet-stream"
                                    ),
                                    stderr=self.store.put(
                                        captured.stderr, "application/octet-stream"
                                    ),
                                    truncated=captured.truncated,
                                )
                            )
                            observation = observation.model_copy(
                                update={"receipts": list(receipts)}
                            )
                            if state != "completed":
                                codes = {
                                    "timeout": "TIMEOUT",
                                    "output_limit": "OUTPUT_LIMIT",
                                    "error": "EXECUTION_FAILED",
                                }
                                error = observation.model_copy(
                                    update={"outcome": "ERROR", "error": codes[state]}
                                )
                                break
                        if error is None:
                            success = len(receipts) == len(plan.commands) and all(
                                (receipt.exit_code == 0) == (cmd.expected == "zero")
                                for receipt, cmd in zip(receipts, plan.commands, strict=True)
                            )
                            observation = observation.model_copy(
                                update={"outcome": "SUCCEEDED" if success else "FAILED"}
                            )
                except Exception:
                    error = observation.model_copy(
                        update={
                            "outcome": "ERROR",
                            "error": "EXECUTION_FAILED" if container_id else "SETUP_FAILED",
                        }
                    )
                finally:
                    observation = error or observation
                    try:
                        if container_id is not None:
                            with suppress(NotFound):
                                client.containers.get(container_id).remove(force=True)
                            try:
                                client.containers.get(container_id)
                            except NotFound:
                                pass
                            else:
                                raise RuntimeError("cleanup uncertain")
                        confirmed = container_id is not None or not (
                            creation_attempted or ownership_unknown
                        )
                        observation = observation.model_copy(
                            update={"cleanup_confirmed": confirmed}
                        )
                    except Exception:
                        observation = observation.model_copy(
                            update={"outcome": "ERROR", "error": "CLEANUP_UNCERTAIN"}
                        )
        except Exception:
            observation = observation.model_copy(
                update={"outcome": "ERROR", "error": "SETUP_FAILED"}
            )
        return self.record_observation(observation)

    def record_observation(self, observation: ProcessObservation) -> ProcessObservation:
        observation = ProcessObservation.model_validate(observation.model_dump())
        artifact = self.store.put_json(observation)
        kind = "execution-refusal" if observation.error == "OPERATION_UNCERTAIN" else "execution"
        self.store.commit(f"{kind}.{observation.operation_id}", artifact)
        return observation.model_copy(update={"artifact": artifact})
