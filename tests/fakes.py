"""A deterministic host double for the ``Sandboxes`` port: no containers, scripted probe outcomes.

The kernel is exercised exactly as against Docker: it creates sandboxes, writes files, runs argv lists, copies the
result files out and removes the sandbox. The fake answers the probe argv from a scenario keyed by (revision, role)
and generates the three result files the kernel reads (its own record, the native JUnit report, the coverage report).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from corsair.application.kernel import RESULT_DIR
from corsair.ports.sandbox import Exec, SandboxExists, SandboxSpec

JUNIT_PASS = (
    '<testsuites><testsuite name="pytest" tests="1" failures="0" errors="0">'
    '<testcase classname="test_corsair_probe" name="test_probe[{role}]" time="0.01"/></testsuite></testsuites>'
)
JUNIT_FAIL = (
    '<testsuites><testsuite name="pytest" tests="1" failures="1" errors="0">'
    '<testcase classname="test_corsair_probe" name="test_probe[{role}]" time="0.01">'
    '<failure message="{message}">{message}</failure></testcase></testsuite></testsuites>'
)
JUNIT_ERROR = (
    '<testsuites><testsuite name="pytest" tests="0" failures="0" errors="1">'
    '<testcase classname="test_corsair_probe" name="test_corsair_probe"><error message="collection failed">'
    "ImportError</error></testcase></testsuite></testsuites>"
)


@dataclass(frozen=True)
class Script:
    outcome: str = "holds"  # holds | violated | errored | not_run | timeout
    exception_type: str | None = None
    message: str | None = None
    covered_lines: tuple[int, ...] = (4,)
    covered_target: bool = True
    raised_in_probe: bool = True
    junit_disagrees: bool = False


@dataclass
class FakeSandboxes:
    scenario: dict[tuple[str, str], Script]
    build_exit: dict[str, int] = field(default_factory=dict)  # revision -> exit code (default 0)
    build_stderr: bytes = b"pip: no matching distribution\n"
    creates: list[SandboxSpec] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    execs: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    sealed: dict[str, str] = field(default_factory=dict)  # tag -> key
    held: set[str] = field(default_factory=set)  # names that already exist
    copied_trees: list[tuple[str, Path]] = field(default_factory=list)
    provider = "fake"
    workdir = "/work"
    _files: dict[str, dict[str, bytes]] = field(default_factory=dict)
    _env: dict[str, dict[str, str]] = field(default_factory=dict)
    _labels: dict[str, Mapping[str, str]] = field(default_factory=dict)

    def create(self, spec: SandboxSpec) -> str:
        if spec.name in self.held:
            raise SandboxExists(spec.name)
        self.creates.append(spec)
        self._labels[spec.name] = dict(spec.labels)
        self._files[spec.name] = {}
        return spec.name

    def copy_tree_in(self, name: str, source: Path, destination: str) -> None:
        self.copied_trees.append((name, Path(source)))
        self._files[name].update(
            {
                f"{destination}/{p.relative_to(source).as_posix()}": p.read_bytes()
                for p in source.rglob("*")
                if p.is_file() and not p.is_symlink()
            }
        )

    def write_file(self, name: str, path: str, data: bytes) -> None:
        self._files.setdefault(name, {})[path] = data

    def source_unchanged(self, name: str, source: Path) -> bool:
        return all(
            self._files[name].get(f"/work/{p.relative_to(source).as_posix()}") == p.read_bytes()
            for p in source.rglob("*")
            if p.is_file() and not p.is_symlink()
        )

    def copy_out(self, name: str, paths: Sequence[str]) -> dict[str, bytes | None]:
        return {path: self._files.get(name, {}).get(path) for path in paths}

    def exec_once(
        self,
        name: str,
        argv: Sequence[str],
        *,
        workdir: str,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        trusted: bool = False,
    ) -> Exec:
        argv = tuple(argv)
        self.execs.append((name, argv))
        if env:
            self._env[name] = dict(env)
        if argv[0] == "bash" and argv[-1].endswith("build.sh"):
            revision = self._labels[name].get("corsair.lite.revision", "vulnerable")
            code = self.build_exit.get(revision, 0)
            return Exec(code, b"collecting...\n", self.build_stderr if code else b"")
        if argv[:2] == ("mkdir", "-p"):
            return Exec(0, b"", b"")
        if "coverage" in argv and "json" in argv:
            return Exec(0, b"", b"")
        if "pytest" in argv:
            return self._probe(name)
        return Exec(0, b"", b"")

    def _probe(self, name: str) -> Exec:
        role = self._env[name]["CORSAIR_ROLE"]
        revision = self._labels[name].get("corsair.lite.revision", "vulnerable")
        script = self.scenario[(revision, role)]
        files = self._files.setdefault(name, {})
        if script.outcome == "timeout":
            return Exec(None, b"", b"", timed_out=True)
        if script.outcome == "not_run":
            files[f"{RESULT_DIR}/junit.xml"] = JUNIT_ERROR.encode()
            return Exec(2, b"", b"ImportError while importing test module\n")
        record = {
            "role": role,
            "outcome": script.outcome,
            "exception_type": script.exception_type,
            "message": script.message,
            "raised_in_probe": script.raised_in_probe,
        }
        if script.outcome == "violated" and not script.raised_in_probe:
            record["outcome"] = "errored"
        files[f"{RESULT_DIR}/result.json"] = json.dumps(record).encode()
        failed = record["outcome"] != "holds"
        if script.junit_disagrees:
            failed = not failed
        junit = JUNIT_PASS if not failed else JUNIT_FAIL
        files[f"{RESULT_DIR}/junit.xml"] = junit.format(
            role=role, message=script.message or "failed"
        ).encode()
        coverage = (
            {"files": {"/work/documents.py": {"executed_lines": list(script.covered_lines)}}}
            if script.covered_target
            else {"files": {}}
        )
        files[f"{RESULT_DIR}/coverage.json"] = json.dumps(coverage).encode()
        return Exec(1 if failed else 0, b"1 passed\n" if not failed else b"1 failed\n", b"")

    def drop_network(self, name: str) -> None:
        self.execs.append((name, ("<drop-network>",)))

    def image_id(self, name: str) -> str | None:
        return "sha256:fake"

    def resolve_image(self, reference: str) -> str | None:
        return "sha256:fake"

    def remove(self, name: str) -> bool:
        self.removed.append(name)
        return True

    def labelled(self, run_id: str | None = None) -> list[str]:
        return sorted(set(self._labels) - set(self.removed))

    def workspace_state(self, name: str) -> None:
        return None

    def find_environment(self, tag: str, key: str) -> str | None:
        return "log" if self.sealed.get(tag) == key else None

    def seal_environment(self, name: str, tag: str, key: str, log_sha256: str, writable=()) -> None:
        self.sealed[tag] = key
        self.writable = list(writable)

    def open_environment(self, image: str, workdir: str, sandbox_labels: Mapping[str, str]) -> str:
        from corsair.ports.sandbox import sandbox_name

        name = sandbox_name(sandbox_labels)
        if name in self.held:
            raise SandboxExists(name)
        self.opened.append(name)
        self._labels[name] = dict(sandbox_labels)
        self._files[name] = {}
        return name
