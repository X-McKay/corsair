"""Node coverage layered over the kernel's one Python pytest driver.

The submitted Python probe starts the native Node target with ``subprocess``.  Its
child inherits ``NODE_V8_COVERAGE``; c8, installed by the trusted image, converts
that native V8 data to LCOV after pytest exits.  This module deliberately parses
only c8's rendered line report, never V8 byte ranges.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from corsair.adapters.frameworks.evidence import MAX_REPORT_BYTES, work_path
from corsair.adapters.frameworks.pytest_ import Pytest
from corsair.ports.framework import PROBE_DIR, RESULT_DIR, ProbeResult

NODE_DIR = f"{RESULT_DIR}/node"
NODE_V8_DIR = f"{NODE_DIR}/v8"
NODE_LCOV = f"{NODE_DIR}/lcov.info"
_C8_CONFIG = f"{PROBE_DIR}/corsair-c8.json"
_COUNT = r"(?:0|[1-9][0-9]*)"
_LINE = r"(?:[1-9][0-9]*)"
_DA = re.compile(rf"DA:({_LINE}),({_COUNT})(?:,([^,\r\n]+))?$")
_FN = re.compile(rf"FN:({_LINE}),([^,\r\n]+)$")
_FNDA = re.compile(rf"FNDA:({_COUNT}),([^,\r\n]+)$")
_TOTAL = re.compile(rf"(?:FNF|FNH|LF|LH):({_COUNT})$")
_BRDA = re.compile(rf"BRDA:({_LINE}),({_COUNT}),({_COUNT}),(-|{_COUNT})$")
_BRANCH_TOTAL = re.compile(rf"(?:BRF|BRH):({_COUNT})$")


def _parse_lcov_record(record: list[str]) -> tuple[str, set[int]] | None:
    """Validate one c8 LCOV record and return its canonical source and hit lines."""
    source: str | None = None
    executed: set[int] = set()
    seen_da: set[int] = set()
    seen_singletons: set[str] = set()
    for line in record:
        if line.startswith("TN:"):
            if "TN" in seen_singletons or "\x00" in line:
                return None
            seen_singletons.add("TN")
        elif line.startswith("SF:"):
            if source is not None:
                return None
            source = work_path(line[3:])
            if source is None:
                return None
        elif line.startswith("DA:"):
            matched = _DA.fullmatch(line)
            if matched is None:
                return None
            line_number, count = (int(value) for value in matched.groups()[:2])
            if line_number in seen_da:
                return None
            seen_da.add(line_number)
            if count:
                executed.add(line_number)
        elif line.startswith("FN:"):
            if _FN.fullmatch(line) is None:
                return None
        elif line.startswith("FNDA:"):
            if _FNDA.fullmatch(line) is None:
                return None
        elif line.startswith(("FNF:", "FNH:", "LF:", "LH:")):
            key = line[:3]
            if key in seen_singletons or _TOTAL.fullmatch(line) is None:
                return None
            seen_singletons.add(key)
        elif line.startswith("BRDA:"):
            if _BRDA.fullmatch(line) is None:
                return None
        elif line.startswith(("BRF:", "BRH:")):
            key = line[:3]
            if key in seen_singletons or _BRANCH_TOTAL.fullmatch(line) is None:
                return None
            seen_singletons.add(key)
        else:
            return None
    return (source, executed) if source is not None else None


def read_lcov(data: bytes | None, hypothesis) -> tuple[bool | None, tuple[int, ...]]:
    """Read one exact source-file record from c8's LCOV output.

    ``None`` means that c8 did not produce an unambiguous, well-formed native
    report.  It intentionally does not fall back to Python coverage: the
    Python driver only covers the probe, not the foreign target.
    """
    if not data or len(data) > MAX_REPORT_BYTES or b"\x00" in data or b"\r" in data:
        return None, ()
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None, ()
    if not lines:
        return None, ()

    records: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line == "end_of_record":
            if not current:
                return None, ()
            records.append(current)
            current = []
        elif not line:
            return None, ()
        else:
            current.append(line)
    if current or not records:
        return None, ()

    target = work_path(hypothesis.target_file)
    if target is None:
        return None, ()
    seen_target = False
    executed: set[int] = set()
    for record in records:
        parsed = _parse_lcov_record(record)
        if parsed is None:
            return None, ()
        source, hits = parsed
        if source != target:
            continue
        if seen_target:
            return None, ()
        seen_target = True
        executed = hits
    if not seen_target:
        return False, ()
    wanted = set(hypothesis.target_lines)
    return bool(executed), tuple(sorted(executed & wanted))


class Node(Pytest):
    """Python pytest driver plus native Node V8 coverage rendered by c8."""

    name = "node"
    language = "node"

    def driver_files(self) -> dict[str, bytes]:
        files = super().driver_files()
        # Explicitly selecting this empty trusted config prevents c8 from
        # discovering a project-controlled .c8rc or package.json section.
        files["corsair-c8.json"] = b"{}\n"
        return files

    def environment(self, role: str) -> Mapping[str, str]:
        return {**super().environment(role), "NODE_V8_COVERAGE": NODE_V8_DIR}

    def after_command(self) -> list[str]:
        return [
            "c8",
            "report",
            "--config",
            _C8_CONFIG,
            "--temp-directory",
            NODE_V8_DIR,
            "--reports-dir",
            NODE_DIR,
            "--reporter",
            "lcovonly",
            "--exclude-after-remap",
        ]

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", NODE_LCOV]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        native = read_lcov(files.get(NODE_LCOV), hypothesis)
        return replace(super().read(files, hypothesis), covered_target=native[0], covered_lines=native[1])
