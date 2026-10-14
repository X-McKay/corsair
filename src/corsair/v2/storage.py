"""Private local v2 storage: immutable artifacts plus SQLite receipts.

The artifact directory is deliberately delegated to the already-qualified
``LocalArtifacts`` publisher.  SQLite contains only application records and
never substitutes for immutable evidence bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any, Self

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.artifacts import ArtifactRef as LocalArtifactRef

from .contracts import ArtifactRef, RunResult, RunSpec, canonical_bytes, digest

_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024  # LocalArtifacts' qualified ceiling.
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _private_directory(value: Path) -> Path:
    """Create or validate one operator-owned non-symlink mode-0700 directory."""
    value = value.expanduser().absolute()
    # ``Path.absolute`` is lexical.  Reject a link at any existing component;
    # checking only the final directory would permit ``root/link/child``.
    current = Path(value.anchor)
    for part in value.parts[1:-1]:
        current /= part
        try:
            parent_info = os.lstat(current)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
            raise ValueError("Storage root must not traverse a symbolic link")
    try:
        info = os.lstat(value)
    except FileNotFoundError:
        value.mkdir(mode=0o700, parents=True)
        info = os.lstat(value)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError("Storage directory must be a real directory, not a link")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("Storage directory must be user-owned mode0700")
    return value


def _sha256(value: str, what: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{what} must be a lowercase SHA-256 digest")
    return value


class Store:
    """A small, process-safe local evidence store.

    Connections are short lived rather than shared between threads.  Every
    write takes an SQLite ``BEGIN IMMEDIATE`` transaction, which makes replay
    and idempotency decisions atomic across Store instances and processes.
    """

    def __init__(self, root: Path | str):
        self.root = _private_directory(Path(root))
        self.artifacts_root = _private_directory(self.root / "artifacts")
        self._database = self.root / "records.sqlite3"
        if self._database.exists():
            info = os.lstat(self._database)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise ValueError("Storage database must be an owned regular file")
        self._artifacts: LocalArtifacts | None = LocalArtifacts(self.artifacts_root, max_bytes=_MAX_ARTIFACT_BYTES)
        self._migrate()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._artifacts is not None:
            self._artifacts.__exit__(None, None, None)
            self._artifacts = None

    def _artifact_store(self) -> LocalArtifacts:
        if self._artifacts is None:
            raise RuntimeError("Store is closed")
        return self._artifacts

    def _connect(self) -> sqlite3.Connection:
        if self._artifacts is None:
            raise RuntimeError("Store is closed")
        connection = sqlite3.connect(self._database, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        # The setting persists in the database; issuing it for each new
        # connection also checks that this is a normal SQLite database.
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _migrate(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > 1:
                    raise RuntimeError(f"Unsupported storage schema version {version}")
                if version == 0:
                    schema = """
                        CREATE TABLE runs (
                            run_id TEXT PRIMARY KEY,
                            request_id TEXT NOT NULL UNIQUE,
                            spec_sha256 TEXT NOT NULL,
                            config_sha256 TEXT NOT NULL,
                            spec_json BLOB NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE TABLE run_events (
                            run_id TEXT NOT NULL REFERENCES runs(run_id),
                            sequence INTEGER NOT NULL,
                            kind TEXT NOT NULL,
                            payload_json BLOB NOT NULL,
                            payload_sha256 TEXT NOT NULL,
                            operation_id TEXT,
                            event_sha256 TEXT NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (run_id, sequence)
                        );
                        CREATE UNIQUE INDEX run_events_operation_once
                            ON run_events(run_id, operation_id) WHERE operation_id IS NOT NULL;
                        CREATE TABLE run_results (
                            run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                            result_json BLOB NOT NULL,
                            result_sha256 TEXT NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE TABLE operations (
                            operation_id TEXT PRIMARY KEY,
                            request_sha256 TEXT NOT NULL,
                            result_json BLOB,
                            result_sha256 TEXT,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            completed_at TEXT
                        );
                        """
                    # executescript() implicitly commits an existing transaction.
                    # These fixed DDL statements contain no quoted semicolons.
                    for statement in schema.split(";"):
                        if statement.strip():
                            connection.execute(statement)
                    connection.execute("PRAGMA user_version=1")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        # SQLite creates these according to the process umask.  Keep all store
        # files private even when the caller has a permissive umask.
        for candidate in (self._database, Path(str(self._database) + "-wal"), Path(str(self._database) + "-shm")):
            if candidate.exists() and candidate.is_file():
                os.chmod(candidate, 0o600)

    def put(self, data: bytes, *, expected_sha256: str | None = None) -> ArtifactRef:
        """Publish exact bytes through LocalArtifacts and bridge its reference type."""
        if expected_sha256 is not None:
            _sha256(expected_sha256, "Expected artifact digest")
        local = self._artifact_store().put(data, expected_sha256=expected_sha256)
        return ArtifactRef(sha256=local.sha256, size=local.size)

    def get(self, reference: ArtifactRef) -> bytes:
        if not isinstance(reference, ArtifactRef):
            raise ValueError("A v2 ArtifactRef is required")  # noqa: TRY004 - invalid admission is consistently ValueError
        return self._artifact_store().get(LocalArtifactRef(reference.sha256, reference.size))

    def put_json(self, value: Any) -> ArtifactRef:
        if not isinstance(value, (dict, list)):
            raise ValueError("JSON artifacts must be objects or arrays")  # noqa: TRY004 - invalid admission is consistently ValueError
        return self.put(canonical_bytes(value))

    def get_json(self, reference: ArtifactRef) -> dict[str, Any] | list[Any]:
        try:
            value = json.loads(self.get(reference))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Artifact does not contain valid JSON") from error
        if not isinstance(value, (dict, list)):
            raise ValueError("JSON artifact is not an object or array")  # noqa: TRY004 - invalid admission is consistently ValueError
        # Require canonical bytes too: JSON evidence has exactly one byte form.
        if canonical_bytes(value) != self.get(reference):
            raise ValueError("JSON artifact is not canonical")
        return value

    def register_run(self, spec: RunSpec, config_sha256: str) -> tuple[str, bool]:
        if not isinstance(spec, RunSpec):
            raise ValueError("A v2 RunSpec is required")  # noqa: TRY004 - invalid admission is consistently ValueError
        _sha256(config_sha256, "Configuration digest")
        spec_sha256 = digest(spec)
        # The caller's logical request id deliberately is the durable run id:
        # it is stable across restart and carries no random retry identity.
        run_id = spec.request_id
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT spec_sha256, config_sha256 FROM runs WHERE request_id = ?", (spec.request_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO runs(run_id, request_id, spec_sha256, config_sha256, spec_json) VALUES (?, ?, ?, ?, ?)",
                    (run_id, spec.request_id, spec_sha256, config_sha256, canonical_bytes(spec)),
                )
                return run_id, True
            if row["spec_sha256"] != spec_sha256 or row["config_sha256"] != config_sha256:
                raise ValueError("request_id is already bound to a different spec or configuration")
            return run_id, False

    def event(self, run_id: str, kind: str, payload: dict[str, Any], operation_id: str | None = None) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id is required")
        if not isinstance(kind, str) or not kind or len(kind) > 256:
            raise ValueError("A bounded event kind is required")
        if not isinstance(payload, dict):
            raise ValueError("Event payload must be an object")  # noqa: TRY004 - invalid admission is consistently ValueError
        if operation_id is not None and (not isinstance(operation_id, str) or not operation_id or len(operation_id) > 256):
            raise ValueError("operation_id must be a bounded nonempty string")
        encoded = canonical_bytes(payload)
        payload_sha256 = hashlib.sha256(encoded).hexdigest()
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise ValueError("Unknown run_id")
            if operation_id is not None:
                prior = connection.execute(
                    "SELECT sequence, kind, payload_json, payload_sha256, event_sha256, operation_id "
                    "FROM run_events WHERE run_id = ? AND operation_id = ?", (run_id, operation_id)
                ).fetchone()
                if prior is not None:
                    if prior["kind"] != kind or prior["payload_sha256"] != payload_sha256 or prior["payload_json"] != encoded:
                        raise ValueError("operation_id is already bound to a different event")
                    return self._event_row(run_id, prior)
            previous = connection.execute(
                "SELECT event_sha256 FROM run_events WHERE run_id = ? ORDER BY sequence DESC LIMIT 1", (run_id,)
            ).fetchone()
            sequence = int(connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?", (run_id,)
            ).fetchone()[0])
            event_sha256 = digest({"run_id": run_id, "sequence": sequence, "kind": kind, "payload": payload,
                                   "operation_id": operation_id, "previous": previous[0] if previous else None})
            connection.execute(
                "INSERT INTO run_events(run_id, sequence, kind, payload_json, payload_sha256, operation_id, event_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, sequence, kind, encoded, payload_sha256, operation_id, event_sha256),
            )
            return {"run_id": run_id, "sequence": sequence, "kind": kind, "payload": payload,
                    "operation_id": operation_id, "sha256": event_sha256}

    @staticmethod
    def _event_row(run_id: str, row: sqlite3.Row) -> dict[str, Any]:
        if hashlib.sha256(row["payload_json"]).hexdigest() != row["payload_sha256"]:
            raise ValueError("Stored event payload digest mismatch")
        return {"run_id": run_id, "sequence": row["sequence"], "kind": row["kind"],
                "payload": json.loads(row["payload_json"]), "operation_id": row["operation_id"],
                "sha256": row["event_sha256"]}

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        if not isinstance(after, int) or after < 0:
            raise ValueError("after must be a nonnegative sequence")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT sequence, kind, payload_json, payload_sha256, event_sha256, operation_id "
                "FROM run_events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        result = []
        previous = None
        for expected_sequence, row in enumerate(rows, start=1):
            event = self._event_row(run_id, row)
            expected = digest({"run_id": run_id, "sequence": event["sequence"], "kind": event["kind"],
                               "payload": event["payload"], "operation_id": event["operation_id"], "previous": previous})
            if event["sequence"] != expected_sequence or event["sha256"] != expected:
                raise ValueError("Stored event chain digest or sequence mismatch")
            previous = event["sha256"]
            if event["sequence"] > after:
                result.append(event)
        return result

    def save_result(self, result: RunResult) -> None:
        if not isinstance(result, RunResult):
            raise ValueError("A v2 RunResult is required")  # noqa: TRY004 - invalid admission is consistently ValueError
        encoded = canonical_bytes(result)
        receipt_sha256 = hashlib.sha256(encoded).hexdigest()
        with self._transaction() as connection:
            run = connection.execute("SELECT spec_sha256, config_sha256 FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()
            if run is None:
                raise ValueError("Cannot save a result for an unknown run")
            if run["spec_sha256"] != result.spec_sha256 or run["config_sha256"] != result.config_sha256:
                raise ValueError("Result identities do not bind to the registered run")
            prior = connection.execute("SELECT result_json, result_sha256 FROM run_results WHERE run_id = ?", (result.run_id,)).fetchone()
            if prior is None:
                connection.execute("INSERT INTO run_results(run_id, result_json, result_sha256) VALUES (?, ?, ?)",
                                   (result.run_id, encoded, receipt_sha256))
            elif prior["result_sha256"] != receipt_sha256 or prior["result_json"] != encoded:
                raise ValueError("A different result is already recorded for this run")

    def result(self, run_id: str) -> RunResult | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT result_json, result_sha256 FROM run_results WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row["result_json"]).hexdigest() != row["result_sha256"]:
            raise ValueError("Stored run result digest mismatch")
        return RunResult.model_validate_json(row["result_json"])

    def runs(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT r.run_id, r.request_id, r.spec_sha256, r.config_sha256, r.created_at, "
                "rr.result_sha256 FROM runs r LEFT JOIN run_results rr ON r.run_id = rr.run_id "
                "ORDER BY r.created_at, r.run_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_operation(self, operation_id: str, request_sha256: str) -> str:
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 256:
            raise ValueError("operation_id must be a bounded nonempty string")
        _sha256(request_sha256, "Operation request digest")
        with self._transaction() as connection:
            row = connection.execute("SELECT request_sha256, result_json FROM operations WHERE operation_id = ?",
                                     (operation_id,)).fetchone()
            if row is None:
                connection.execute("INSERT INTO operations(operation_id, request_sha256) VALUES (?, ?)",
                                   (operation_id, request_sha256))
                return "new"
            if row["request_sha256"] != request_sha256:
                raise ValueError("operation_id is already bound to a different request")
            # An intent without a receipt is deliberately uncertain; callers
            # must reconcile rather than dispatch a potentially duplicate side effect.
            return "recorded" if row["result_json"] is not None else "uncertain"

    def operation(self, operation_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT result_json, result_sha256 FROM operations WHERE operation_id = ?", (operation_id,)).fetchone()
        if row is None or row["result_json"] is None:
            return None
        if hashlib.sha256(row["result_json"]).hexdigest() != row["result_sha256"]:
            raise ValueError("Stored operation receipt digest mismatch")
        return json.loads(row["result_json"])

    def complete_operation(self, operation_id: str, result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            raise ValueError("Operation receipt must be an object")  # noqa: TRY004 - invalid admission is consistently ValueError
        encoded = canonical_bytes(result)
        receipt_sha256 = hashlib.sha256(encoded).hexdigest()
        with self._transaction() as connection:
            row = connection.execute("SELECT result_json, result_sha256 FROM operations WHERE operation_id = ?",
                                     (operation_id,)).fetchone()
            if row is None:
                raise ValueError("Operation intent must be claimed before completion")
            if row["result_json"] is None:
                connection.execute("UPDATE operations SET result_json = ?, result_sha256 = ?, completed_at = CURRENT_TIMESTAMP "
                                   "WHERE operation_id = ?", (encoded, receipt_sha256, operation_id))
            elif row["result_sha256"] != receipt_sha256 or row["result_json"] != encoded:
                raise ValueError("A different operation receipt is already recorded")

    from contextlib import contextmanager

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
