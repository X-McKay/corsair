"""Ruby coverage layered over the kernel's one Python pytest driver.

The Python probe owns the native subprocess invocation.  Ruby loads the
kernel-owned bootstrap through ``RUBYOPT`` before target code, and SimpleCov
writes an isolated resultset under /tmp/corsair/ruby at process exit.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from corsair.adapters.frameworks.evidence import load_json, work_path
from corsair.adapters.frameworks.pytest_ import Pytest
from corsair.ports.framework import PROBE_DIR, RESULT_DIR, ProbeResult

RUBY_DIR = f"{RESULT_DIR}/ruby"
RUBY_RESULTSET = f"{RUBY_DIR}/.resultset.json"
_BOOTSTRAP = f"{PROBE_DIR}/corsair_simplecov.rb"

SIMPLECOV_BOOTSTRAP = r"""# frozen_string_literal: true
# Loaded through RUBYOPT by the kernel before a target can require application code.
# bundle exec restricts activated gems to the project lockfile. Instrumentation belongs to the trusted image,
# not that lockfile: use the Ruby SDK's normal load path for its pinned image-owned libraries.
$LOAD_PATH.unshift(*Dir["/usr/local/bundle/gems/{simplecov*,docile-*}/lib"])
require "simplecov"

SimpleCov.start do
  root "/work"
  coverage_dir "/tmp/corsair/ruby"
  command_name "corsair-#{ENV.fetch("CORSAIR_ROLE")}" 
  # A fresh probe container gives each payload its own resultset; merging must stay enabled so SimpleCov persists
  # the machine-readable .resultset.json that the adapter, rather than its HTML output, reads.
  use_merging true
  enable_coverage :line
end
# The kernel needs persisted SDK data, not an HTML formatter or extra stdout from the target seam.
SimpleCov.at_exit { SimpleCov.result }
"""


def _nonnegative_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected non-negative integer")
    return value


def read_resultset(data: bytes | None, hypothesis, role: str | None) -> tuple[bool | None, tuple[int, ...]]:
    """Read the one SimpleCov result that belongs to this native payload.

    SimpleCov 0.22 persists ``coverage`` as a mapping from source file to a
    mapping containing ``lines``.  Missing, malformed, duplicate or unexpected
    command-name data remains unknown rather than borrowing Python coverage.
    """
    try:
        report = load_json(data)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None, ()
    if not isinstance(report, dict) or len(report) != 1:
        return None, ()
    command_name, result = next(iter(report.items()))
    if role not in ("control", "exploit") or command_name != f"corsair-{role}":
        return None, ()
    if not isinstance(result, dict) or set(result) != {"coverage", "timestamp"}:
        return None, ()
    timestamp, coverage = result.get("timestamp"), result.get("coverage")
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or not math.isfinite(timestamp)
        or timestamp < 0
    ):
        return None, ()
    if not isinstance(coverage, dict):
        return None, ()

    target = work_path(hypothesis.target_file)
    if target is None:
        return None, ()
    matches: list[object] = []
    for source, values in coverage.items():
        normalized = work_path(source)
        if normalized is None:
            return None, ()
        if normalized == target:
            matches.append(values)
    if len(matches) > 1:
        return None, ()
    if not matches:
        return False, ()

    value = matches[0]
    if not isinstance(value, dict) or set(value) - {"lines", "branches"} or "lines" not in value:
        return None, ()
    if "branches" in value and not isinstance(value["branches"], dict):
        return None, ()
    lines = value["lines"]
    if not isinstance(lines, list):
        return None, ()
    executed: set[int] = set()
    for number, count in enumerate(lines, start=1):
        # nil denotes a non-relevant source line.  Ruby Coverage counts are
        # non-negative integers; booleans are deliberately not accepted.
        if count is None:
            continue
        try:
            count = _nonnegative_integer(count)
        except ValueError:
            return None, ()
        if count > 0:
            executed.add(number)
    wanted = set(hypothesis.target_lines)
    return bool(executed), tuple(sorted(executed & wanted))


class Ruby(Pytest):
    """Python pytest driver plus native SimpleCov coverage for Ruby targets."""

    name = "ruby"
    language = "ruby"

    def driver_files(self) -> dict[str, bytes]:
        files = super().driver_files()
        files["corsair_simplecov.rb"] = SIMPLECOV_BOOTSTRAP.encode()
        return files

    def environment(self, role: str) -> Mapping[str, str]:
        return {**super().environment(role), "RUBYOPT": f"-r{_BOOTSTRAP}"}

    def after_command(self) -> None:
        # SimpleCov persisted the native report at Ruby process exit; Python wrapper coverage is irrelevant.
        return None

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", RUBY_RESULTSET]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        result = super().read(files, hypothesis)
        role = None
        record = files.get(f"{RESULT_DIR}/result.json")
        try:
            parsed = load_json(record)
            role = parsed.get("role") if isinstance(parsed, dict) else None
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            pass
        native = read_resultset(files.get(RUBY_RESULTSET), hypothesis, role)
        return replace(result, covered_target=native[0], covered_lines=native[1])
