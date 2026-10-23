"""C++ adapter: inherited Python probe driver plus gcov evidence for the real native target."""

from __future__ import annotations

import json
import posixpath
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from corsair.adapters.frameworks import pytest_
from corsair.adapters.frameworks.evidence import load_json
from corsair.ports.framework import PROBE_DIR, RESULT_DIR, WORKDIR, ProbeResult

GCOV_ROOT = f"{RESULT_DIR}/gcov"
GCOV_JSON = f"{RESULT_DIR}/gcov.json"


# gcov requires each redirected .gcda to sit beside its matching .gcno.  Stage only those pairs under /tmp, then
# retain the machine-readable output; the probe never writes coverage next to immutable build artifacts.
GCOV_COLLECTOR = f'''"""Collect every GCOV_PREFIX data file through gcov's JSON output."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

WORKDIR = Path("{WORKDIR}")
RESULT_DIR = Path("{RESULT_DIR}")
PREFIX = RESULT_DIR / "gcov"
REPORT = RESULT_DIR / "gcov.json"


def write(payload):
    REPORT.write_text(json.dumps(payload, sort_keys=True))


def fail(reason):
    write({{"format": "corsair-gcov/1", "ok": False, "error": reason}})


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    if not PREFIX.is_dir():
        fail("GCOV_PREFIX data directory is missing")
        return
    data_files = sorted(path for path in PREFIX.rglob("*.gcda") if path.is_file() and not path.is_symlink())
    if not data_files:
        fail("no gcov data files were written")
        return
    reports = []
    with tempfile.TemporaryDirectory(dir=RESULT_DIR, prefix="gcov-stage-") as temporary:
        stage = Path(temporary)
        for data in data_files:
            relative = data.relative_to(PREFIX)
            if any(part in ("", ".", "..") for part in relative.parts):
                fail("unsafe redirected gcov data path")
                return
            notes = WORKDIR / relative.with_suffix(".gcno")
            if not notes.is_file() or notes.is_symlink():
                fail("matching gcov notes are missing for " + relative.as_posix())
                return
            staged_data = stage / relative
            staged_data.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data, staged_data)
            shutil.copy2(notes, staged_data.with_suffix(".gcno"))
            try:
                result = subprocess.run(["gcov", "--json-format", "--stdout", str(staged_data)], check=False,
                                        capture_output=True, text=True, timeout=90)
                report = json.loads(result.stdout)
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                fail("gcov JSON command failed for " + relative.as_posix())
                return
            if result.returncode != 0 or report.get("format_version") != "1" or not isinstance(report.get("files"), list):
                fail("invalid gcov JSON for " + relative.as_posix())
                return
            reports.append(report)
    write({{"format": "corsair-gcov/1", "ok": True, "reports": reports}})


if __name__ == "__main__":
    main()
'''


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected integer")
    return value


def read_gcov(data: bytes | None, hypothesis) -> tuple[bool | None, tuple[int, ...]]:
    """Accept only one exact `/work/<target_file>` source entry from a complete gcov JSON aggregate."""
    try:
        aggregate = load_json(data)
        if (
            not isinstance(aggregate, dict)
            or aggregate.get("format") != "corsair-gcov/1"
            or aggregate.get("ok") is not True
            or not isinstance(aggregate.get("reports"), list)
            or not aggregate["reports"]
        ):
            return None, ()
        target = f"{WORKDIR}/{hypothesis.target_file}"
        matches: list[dict[str, Any]] = []
        for report in aggregate["reports"]:
            if (
                not isinstance(report, dict)
                or report.get("format_version") != "1"
                or not isinstance(report.get("files"), list)
            ):
                return None, ()
            for source in report["files"]:
                if (
                    not isinstance(source, dict)
                    or not isinstance(source.get("file"), str)
                    or not isinstance(source.get("lines"), list)
                ):
                    return None, ()
                path = source["file"]
                if ".." in path.split("/"):
                    return None, ()
                if not path.startswith("/"):
                    directory = report.get("current_working_directory")
                    if (
                        not isinstance(directory, str)
                        or not directory.startswith("/work")
                        or ".." in directory.split("/")
                    ):
                        return None, ()
                    path = posixpath.join(directory, path)
                if posixpath.normpath(path) == target:
                    matches.append(source)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, ()
    if len(matches) != 1:
        return (False, ()) if not matches else (None, ())

    covered: set[int] = set()
    seen: set[int] = set()
    try:
        for line in matches[0]["lines"]:
            if not isinstance(line, dict):
                return None, ()
            number, count = _integer(line.get("line_number")), _integer(line.get("count"))
            if number < 1 or count < 0 or number in seen:
                return None, ()
            seen.add(number)
            if count > 0:
                covered.add(number)
    except ValueError:
        return None, ()
    return bool(covered), tuple(sorted(covered & set(hypothesis.target_lines)))


class Cpp(pytest_.Pytest):
    """The inherited pytest driver executes the Python probe; gcov proves C++ target execution."""

    name = "cpp"
    language = "cpp"

    def driver_files(self) -> dict[str, bytes]:
        return {**super().driver_files(), "collect_gcov.py": GCOV_COLLECTOR.encode()}

    def environment(self, role: str) -> Mapping[str, str]:
        return {**super().environment(role), "GCOV_PREFIX": GCOV_ROOT, "GCOV_PREFIX_STRIP": "1"}

    def after_command(self) -> list[str]:
        return ["python", f"{PROBE_DIR}/collect_gcov.py"]

    def result_paths(self) -> list[str]:
        return [path for path in super().result_paths() if not path.endswith("coverage.json")] + [GCOV_JSON]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        covered_target, covered_lines = read_gcov(files.get(GCOV_JSON), hypothesis)
        return replace(
            super().read(files, hypothesis), covered_target=covered_target, covered_lines=covered_lines
        )
