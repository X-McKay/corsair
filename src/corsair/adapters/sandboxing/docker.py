"""Hardened Docker execution for trusted Python evidence checks.

There is intentionally no host-process fallback.  If the Docker SDK, daemon, image,
or driver record is unavailable, callers receive non-admissible evidence instead of a
synthetic passing result.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.types import LogConfig

from corsair.adapters.scm.local import SourceAdmissionError, iter_snapshot_files
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    Budget,
    PreparedCase,
    PythonRecipe,
    RubyRecipe,
    Submission,
    digest,
)
from corsair.ports.sandboxing import SandboxRole
from corsair.ports.sandboxing import SandboxUnavailable as SandboxUnavailable
from corsair.settings import Settings

Heartbeat = Callable[[], None]


class SandboxExecutionError(RuntimeError):
    """A role container did not leave parseable, cleanup-confirmed evidence."""


class DockerSandbox:
    """Run each role in one fresh, restrictive Docker container.

    The Docker daemon is part of the trust boundary.  This constrains untrusted target
    code but does not claim to defend against a compromised daemon/kernel or arbitrary
    dependency/build systems; initial support imports a pinned source module directly.
    """

    def __init__(
        self,
        settings: Settings,
        client: docker.DockerClient | None = None,
        *,
        store: ArtifactStore | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self._client: docker.DockerClient | None = client
        self._client_error: str | None = None
        self._image_ids: dict[str, str] = {}
        if client is None:
            try:
                self._client = docker.from_env()
            except DockerException as exc:
                self._client_error = type(exc).__name__

    @property
    def image_id(self) -> str:
        """Return the immutable Docker image ID of the default Python image."""
        return self._ensure_image(self.settings.image)

    def image_id_for(self, kind: str) -> str:
        """Return the immutable Docker image ID for the recipe kind's trusted image."""
        return self._ensure_image(self.settings.image_for(kind))

    def _ensure_image(self, tag: str) -> str:
        cached = self._image_ids.get(tag)
        if cached is not None:
            return cached
        client = self._client
        if client is None:
            raise SandboxUnavailable(
                f"Docker client unavailable: {self._client_error or 'unknown error'}"
            )
        try:
            image = client.images.get(tag)
        except ImageNotFound:
            raise SandboxUnavailable(
                f"trusted image {tag} unavailable; build its deploy/ Dockerfile with just images"
            ) from None
        except (APIError, DockerException) as exc:
            raise SandboxUnavailable(f"trusted image unavailable: {type(exc).__name__}") from exc
        resolved = str(image.id)
        self._image_ids[tag] = resolved
        return resolved

    def has_unknown_operation(self, operation_id: str) -> bool:
        """An old labeled container means the operation may have run; never rerun it."""
        client = self._client
        if client is None:
            return False
        try:
            containers = client.containers.list(
                all=True,
                filters={"label": ["corsair.security=true", f"corsair.operation={operation_id}"]},
            )
        except (APIError, DockerException):
            # We cannot prove absence if Docker cannot enumerate the label.
            return True
        return bool(containers)

    @staticmethod
    def _mkdir(path: Path, mode: int = 0o755) -> None:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, mode)

    @classmethod
    def _materialize_source(cls, root: Path, prepared: PreparedCase, store: ArtifactStore) -> None:
        cls._mkdir(root)
        try:
            files = list(iter_snapshot_files(prepared.source, store))
        except SourceAdmissionError:
            raise
        for relative, content in files:
            destination = root.joinpath(*relative.split("/"))
            cls._mkdir(destination.parent)
            destination.write_bytes(content)
            os.chmod(destination, 0o444)

    @classmethod
    def _materialize_fixtures(cls, root: Path, prepared: PreparedCase) -> None:
        allowed = root / "allowed"
        private = root / "private"
        cls._mkdir(allowed)
        cls._mkdir(private)
        # Only the secret-disclosure recipes (Python, Ruby) use public fixtures and a
        # private secret. Other recipes (e.g. the JavaScript prototype-pollution check)
        # observe a global side effect and read no fixture, so the mount stays empty.
        recipe = prepared.recipe
        if isinstance(recipe, (PythonRecipe, RubyRecipe)):
            for relative, content in recipe.public_files.items():
                destination = allowed.joinpath(*relative.split("/"))
                cls._mkdir(destination.parent)
                destination.write_text(content, encoding="utf-8")
                os.chmod(destination, 0o444)
            # random content never enters PreparedCase, Submission, agent context, logs,
            # evidence reasons, or the driver job JSON.
            secret = secrets.token_urlsafe(32)
            secret_file = private / "secret.txt"
            secret_file.write_text(secret, encoding="utf-8")
            # Bind-mounted files retain host ownership under rootless Docker. The fixture
            # is therefore world-readable within the isolated read-only mount; its random
            # content never reaches a prompt, job JSON, stdout, or Observation reason.
            os.chmod(secret_file, 0o444)
        for directory in (allowed, private, root):
            os.chmod(directory, 0o555)

    @staticmethod
    def _driver_record(stdout: bytes, budget: Budget) -> dict[str, Any]:
        if len(stdout) > budget.tool_output_bytes:
            raise SandboxExecutionError("trusted driver stdout exceeded output limit")
        try:
            lines = [line for line in stdout.decode("utf-8").splitlines() if line.strip()]
        except UnicodeDecodeError as exc:
            raise SandboxExecutionError("trusted driver stdout was not UTF-8") from exc
        if len(lines) != 1:
            raise SandboxExecutionError("trusted driver did not produce exactly one JSON record")
        try:
            record = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            raise SandboxExecutionError("trusted driver record was not JSON") from exc
        if not isinstance(record, dict):
            raise SandboxExecutionError("trusted driver record was not an object")
        return record

    def _wait_with_heartbeat(
        self, container: Any, timeout_seconds: int, heartbeat: Heartbeat
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        failure: list[BaseException] = []

        def waiter() -> None:
            try:
                result.update(container.wait())
            except BaseException as exc:  # re-raised on the supervising thread
                failure.append(exc)

        thread = threading.Thread(target=waiter, name="corsair-docker-wait", daemon=True)
        thread.start()
        deadline = time.monotonic() + timeout_seconds
        while thread.is_alive():
            heartbeat()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                with suppress(APIError, DockerException):
                    container.stop(timeout=1)
                thread.join(timeout=3)
                raise SandboxExecutionError("role execution exceeded its time limit")
            thread.join(timeout=min(0.25, remaining))
        heartbeat()
        if failure:
            raise SandboxExecutionError("Docker wait failed") from failure[0]
        return result

    def _cleanup(self, container: Any, immutable_id: str, labels: dict[str, str]) -> bool:
        """Remove only the created immutable ID and then independently confirm absence."""
        client = self._client
        if client is None:
            return False
        try:
            container.reload()
            actual_id = str(container.attrs.get("Id", ""))
            actual_labels = container.attrs.get("Config", {}).get("Labels", {})
            if actual_id != immutable_id or any(
                actual_labels.get(key) != value for key, value in labels.items()
            ):
                return False
            if container.status not in {"exited", "dead", "removing"}:
                container.stop(timeout=1)
            container.remove(force=True)
            try:
                client.api.inspect_container(immutable_id)
            except NotFound:
                return True
            except (APIError, DockerException):
                return False
            return False
        except (APIError, DockerException, AttributeError):
            return False

    def _raw_error(
        self,
        store: ArtifactStore,
        role: str,
        reason: str,
        operation_id: str,
        *,
        container_id: str = "",
        labels: dict[str, str] | None = None,
        cleanup_confirmed: bool = False,
        image_id: str | None = None,
        docker_exit_code: int | None = None,
    ) -> ArtifactRef:
        ref = store.put_json(
            {
                "schema_version": "corsair.raw-evidence/1",
                "operation_id": operation_id,
                "role": role,
                "container_id": container_id,
                "labels": labels or {},
                "image_id": image_id,
                "docker_exit_code": docker_exit_code,
                "driver": None,
                "cleanup_confirmed": cleanup_confirmed,
                "error": reason,
            }
        )
        return ref

    def execute_role(
        self,
        prepared: PreparedCase,
        submission: Submission,
        role: SandboxRole,
        budget: Budget,
        heartbeat: Heartbeat = lambda: None,
        *,
        operation_id: str,
    ) -> ArtifactRef:
        """Run one role bound to its immutable operation and return the raw receipt."""
        store = self.store
        if store is None:
            raise SandboxUnavailable("execution requires a configured artifact store")

        if role not in {"control", "adversarial"}:
            raise ValueError("role must be control or adversarial")
        image_id = self._ensure_image(self.settings.image_for(prepared.recipe.kind))
        client = self._client
        if client is None:
            raise SandboxUnavailable(
                f"Docker client unavailable: {self._client_error or 'unknown error'}"
            )
        labels = {
            "corsair.security": "true",
            "corsair.operation": operation_id,
            "corsair.role": role,
        }
        payload = submission.control_payload if role == "control" else submission.exploit_payload
        job = {
            "schema_version": "corsair.driver-job/1",
            "operation_id": operation_id,
            "role": role,
            "source_digest": prepared.source.sha256,
            "submission_digest": digest(submission),
            "recipe": prepared.recipe.model_dump(mode="json"),
            "payload": payload,
        }
        container = None
        immutable_id = ""
        cleanup_confirmed = False
        record: dict[str, Any] | None = None
        docker_exit_code: int | None = None
        error_reason: str | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="corsair-security-") as temporary:
                workspace = Path(temporary)
                # Rootless Docker may read only world-readable bind paths on some
                # hosts.  All mounted files remain immutable to uid 1000 in-container.
                os.chmod(workspace, 0o755)
                source_root = workspace / "source"
                fixtures_root = workspace / "fixtures"
                input_root = workspace / "input"
                self._materialize_source(source_root, prepared, store)
                self._materialize_fixtures(fixtures_root, prepared)
                self._mkdir(input_root)
                job_path = input_root / "job.json"
                job_path.write_text(
                    json.dumps(job, sort_keys=True, separators=(",", ":")), encoding="utf-8"
                )
                os.chmod(job_path, 0o444)
                os.chmod(input_root, 0o555)

                container = client.containers.create(
                    image=image_id,
                    labels=labels,
                    network_mode="none",
                    read_only=True,
                    user="1000:1000",
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                    privileged=False,
                    mem_limit=self.settings.memory_limit,
                    nano_cpus=self.settings.nano_cpus,
                    pids_limit=self.settings.pids_limit,
                    runtime=self.settings.runtime,
                    working_dir="/work",
                    environment={
                        "HOME": "/tmp",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONNOUSERSITE": "1",
                    },
                    tmpfs={
                        "/work": "rw,nosuid,nodev,noexec,size=64m,mode=0700,uid=1000,gid=1000",
                        "/tmp": "rw,nosuid,nodev,noexec,size=32m,mode=1777",
                    },
                    log_config=LogConfig(
                        type="json-file",
                        config={"max-size": "128k", "max-file": "1"},
                    ),
                    volumes={
                        str(source_root): {"bind": "/source", "mode": "ro"},
                        str(fixtures_root): {"bind": "/fixtures", "mode": "ro"},
                        str(input_root): {"bind": "/input", "mode": "ro"},
                    },
                )
                immutable_id = str(container.id)
                container.reload()
                if str(container.attrs.get("Id", "")) != immutable_id or any(
                    container.attrs.get("Config", {}).get("Labels", {}).get(key) != value
                    for key, value in labels.items()
                ):
                    raise SandboxExecutionError("created container identity/labels did not match")
                container.start()
                wait_result = self._wait_with_heartbeat(
                    container, budget.probe_timeout_seconds, heartbeat
                )
                docker_exit_code = wait_result.get("StatusCode")
                stdout = container.logs(stdout=True, stderr=False)
                record = self._driver_record(stdout, budget)
                driver_exit = record.get("native_exit_code")
                if (
                    type(driver_exit) is not int
                    or type(docker_exit_code) is not int
                    or driver_exit != docker_exit_code
                ):
                    raise SandboxExecutionError("driver and Docker exit codes disagree")
        except SandboxUnavailable:
            raise
        except (InterruptedError, KeyboardInterrupt):
            # The activity heartbeat is a cancellation boundary. Finally still tears
            # down this immutable container; EvidenceVerifier will not start role two.
            raise
        except (
            APIError,
            DockerException,
            OSError,
            SourceAdmissionError,
            SandboxExecutionError,
        ) as exc:
            # Continue through finally, retaining only a generic non-secret reason.
            record = None
            error_reason = type(exc).__name__
        finally:
            if container is not None:
                cleanup_confirmed = self._cleanup(container, immutable_id, labels)

        if record is None:
            return self._raw_error(
                store,
                role,
                error_reason or "execution failure",
                operation_id,
                container_id=immutable_id,
                labels=labels,
                cleanup_confirmed=cleanup_confirmed,
                image_id=image_id,
                docker_exit_code=docker_exit_code,
            )
        raw = {
            "schema_version": "corsair.raw-evidence/1",
            "operation_id": operation_id,
            "role": role,
            "container_id": immutable_id,
            "labels": labels,
            "cleanup_confirmed": cleanup_confirmed,
            "image_id": image_id,
            "docker_exit_code": docker_exit_code,
            "driver": record,
        }
        raw_ref = store.put_json(raw)
        return raw_ref
