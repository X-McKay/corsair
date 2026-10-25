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

from corsair.contracts import Budget, PreparedCase, RoleObservation, RoleOutcome, Submission, digest
from corsair.runtime.artifacts import ArtifactStore
from corsair.tools.security.sources import SourceAdmissionError, iter_snapshot_files

Heartbeat = Callable[[], None]


class SandboxUnavailable(RuntimeError):
    """Docker infrastructure could not safely provide the trusted runtime."""


class SandboxExecutionError(RuntimeError):
    """A role container did not leave parseable, cleanup-confirmed evidence."""


class DockerSandbox:
    """Run each role in one fresh, restrictive Docker container.

    The Docker daemon is part of the trust boundary.  This constrains untrusted target
    code but does not claim to defend against a compromised daemon/kernel or arbitrary
    dependency/build systems; initial support imports a pinned source module directly.
    """

    def __init__(self, settings, client: Any | None = None):
        self.settings = settings
        self._client = client
        self._client_error: str | None = None
        self._image_id: str | None = None
        self._image_error: str | None = None
        if client is None:
            try:
                self._client = docker.from_env()
            except DockerException as exc:
                self._client_error = type(exc).__name__

    @property
    def image_id(self) -> str:
        """Return the immutable Docker image ID or raise if it cannot be obtained."""
        return self._ensure_image()

    def _ensure_image(self) -> str:
        if self._image_id is not None:
            return self._image_id
        if self._client is None:
            raise SandboxUnavailable(
                f"Docker client unavailable: {self._client_error or 'unknown error'}"
            )
        try:
            image = self._client.images.get(self.settings.image)
        except ImageNotFound:
            raise SandboxUnavailable(
                "trusted image unavailable; build deploy/python/Dockerfile with make images"
            ) from None
        except (APIError, DockerException) as exc:
            self._image_error = type(exc).__name__
            raise SandboxUnavailable(f"trusted image unavailable: {self._image_error}") from exc
        self._image_id = str(image.id)
        return self._image_id

    def has_unknown_operation(self, operation_id: str) -> bool:
        """An old labeled container means the operation may have run; never rerun it."""
        if self._client is None:
            return False
        try:
            containers = self._client.containers.list(
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
        for relative, content in prepared.recipe.public_files.items():
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

    @staticmethod
    def _provisional(record: dict[str, Any], cleanup_confirmed: bool) -> RoleObservation:
        try:
            outcome = RoleOutcome(record["outcome"])
            covered = record.get("covered_lines", [])
            if not isinstance(covered, list) or any(
                type(line) is not int or line < 1 for line in covered
            ):
                raise ValueError("invalid coverage")
            exit_code = record.get("native_exit_code")
            if type(exit_code) is not int or exit_code < 0:
                raise ValueError("invalid exit code")
            if not cleanup_confirmed:
                raise ValueError("cleanup not confirmed")
            return RoleObservation(
                outcome=outcome,
                target_executed=bool(record.get("target_executed", False)),
                covered_lines=covered,
                reason="trusted driver record",
                native_exit_code=exit_code,
            )
        except (KeyError, TypeError, ValueError):
            return RoleObservation(
                outcome=RoleOutcome.INVALID,
                target_executed=False,
                reason="trusted driver record is invalid",
                native_exit_code=None,
            )

    def _wait_with_heartbeat(
        self, container: Any, timeout_seconds: int, heartbeat: Heartbeat
    ) -> dict:
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
                self._client.api.inspect_container(immutable_id)
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
    ) -> tuple[RoleObservation, Any]:
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
        return (
            RoleObservation(
                outcome=RoleOutcome.ERROR,
                target_executed=False,
                reason=reason,
                native_exit_code=None,
            ),
            ref,
        )

    def run_role(
        self,
        prepared: PreparedCase,
        submission: Submission,
        role: str,
        budget: Budget,
        store: ArtifactStore,
        heartbeat: Heartbeat = lambda: None,
        *,
        operation_id: str | None = None,
    ) -> tuple[RoleObservation, Any]:
        """Run one control/adversarial role and return provisional observation + raw ref.

        ``operation_id`` is keyword-only for backwards compatibility with the public
        role API, but EvidenceVerifier supplies it to bind driver evidence to the
        durable operation identity.
        """
        if role not in {"control", "adversarial"}:
            raise ValueError("role must be control or adversarial")
        image_id = self._ensure_image()
        if operation_id is None:
            operation_id = prepared.manifest.request_digest
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

                container = self._client.containers.create(
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
                    log_config=docker.types.LogConfig(
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
        return self._provisional(record, cleanup_confirmed), raw_ref
