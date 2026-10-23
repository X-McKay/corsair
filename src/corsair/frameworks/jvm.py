"""JVM adapter: inherited Python probe driver plus JaCoCo evidence for the real Java target."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import replace

from . import pytest_
from .base import PROBE_DIR, RESULT_DIR, WORKDIR, ProbeResult
from .evidence import MAX_REPORT_BYTES, load_json

JACOCO_AGENT = "/opt/corsair/jacoco/jacocoagent.jar"
JACOCO_CLI = "/opt/corsair/jacoco/jacococli.jar"
JACOCO_XML = f"{RESULT_DIR}/jacoco.xml"
JACOCO_SOURCES = f"{RESULT_DIR}/jacoco-sources.json"
JACOCO_DOCTYPE = re.compile(
    rb'^\s*(?:<\?xml[^>]*\?>\s*)?<!DOCTYPE\s+report\s+PUBLIC\s+"-//JACOCO//DTD Report 1\.1//EN"\s+"report\.dtd"\s*>',
    re.IGNORECASE,
)


# Kept kernel-owned beside the inherited pytest driver: the probe only starts the application's Java process.
JACOCO_COLLECTOR = f'''"""Render one JaCoCo XML report from classes compiled during build replay."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

WORKDIR = Path("{WORKDIR}")
RESULT_DIR = Path("{RESULT_DIR}")
EXEC = RESULT_DIR / "jacoco.exec"
XML = RESULT_DIR / "jacoco.xml"
SOURCES = RESULT_DIR / "jacoco-sources.json"
CLI = "{JACOCO_CLI}"
CLASS_SUFFIXES = (("target", "classes"), ("build", "classes", "java", "main"),
                  ("build", "classes"), ("classes",))
SOURCE_SUFFIXES = (("src", "main", "java"),)


def directories(suffixes):
    found = []
    for directory, _, _ in os.walk(WORKDIR):
        path = Path(directory)
        relative = path.relative_to(WORKDIR).parts
        if any(len(relative) >= len(suffix) and relative[-len(suffix):] == suffix for suffix in suffixes):
            found.append(path)
    return sorted(set(found))


def fail(reason):
    SOURCES.write_text(json.dumps({{"format": "corsair-jacoco/1", "ok": False, "error": reason}}))


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    if not EXEC.is_file():
        fail("JaCoCo execution data is missing")
        return
    class_dirs = [path for path in directories(CLASS_SUFFIXES) if any(path.rglob("*.class"))]
    source_roots = directories(SOURCE_SUFFIXES)
    catalog = {{}}
    for root in source_roots:
        for source in sorted(root.rglob("*.java")):
            if source.is_file() and not source.is_symlink():
                key = source.relative_to(root).as_posix()
                catalog.setdefault(key, []).append(str(source))
    duplicates = sorted(key for key, paths in catalog.items() if len(paths) != 1)
    if duplicates:
        fail("ambiguous Java source paths: " + ", ".join(duplicates[:10]))
        return
    if not class_dirs or not source_roots or not catalog:
        fail("compiled classes or Java source roots are missing")
        return
    SOURCES.write_text(json.dumps({{"format": "corsair-jacoco/1", "ok": True,
                                   "sources": {{key: paths[0] for key, paths in catalog.items()}}}}, sort_keys=True))
    command = ["java", "-jar", CLI, "report", str(EXEC), "--xml", str(XML)]
    for path in class_dirs:
        command.extend(("--classfiles", str(path)))
    for path in source_roots:
        command.extend(("--sourcefiles", str(path)))
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        XML.unlink(missing_ok=True)
        fail("JaCoCo report command could not run")
        return
    if result.returncode != 0 or not XML.is_file() or XML.stat().st_size == 0:
        XML.unlink(missing_ok=True)
        fail("JaCoCo report command failed")


if __name__ == "__main__":
    main()
'''


def _java_source_key(target: str) -> str | None:
    """The path JaCoCo records: relative to one standard Java source root, never a suffix match."""
    parts = target.split("/")
    marker = ("src", "main", "java")
    for index in range(len(parts) - len(marker) + 1):
        if tuple(parts[index:index + len(marker)]) == marker:
            remainder = parts[index + len(marker):]
            if remainder and remainder[-1].endswith(".java") and all(part not in ("", ".", "..") for part in remainder):
                return "/".join(remainder)
    return None


def _source_key(package: str, source: str) -> str | None:
    if not isinstance(package, str) or not isinstance(source, str):
        return None
    if "/" in source or "\\" in source or source in ("", ".", ".."):
        return None
    package_parts = [] if package == "" else package.split("/")
    if any(part in ("", ".", "..") or "\\" in part for part in package_parts):
        return None
    return "/".join((*package_parts, source))


def read_jacoco(xml: bytes | None, source_manifest: bytes | None, hypothesis) -> tuple[bool | None, tuple[int, ...]]:
    """Read a JaCoCo XML report only when its source catalog binds it to the exact target path."""
    try:
        manifest = load_json(source_manifest)
        target = f"{WORKDIR}/{hypothesis.target_file}"
        expected_key = _java_source_key(str(hypothesis.target_file))
        if (not isinstance(manifest, dict) or manifest.get("format") != "corsair-jacoco/1"
                or manifest.get("ok") is not True or expected_key is None):
            return None, ()
        sources = manifest.get("sources")
        if not isinstance(sources, dict) or sources.get(expected_key) != target:
            return None, ()
        if xml is None or len(xml) > MAX_REPORT_BYTES or b"<!entity" in xml.lower():
            return None, ()
        if b"<!doctype" in xml.lower() and JACOCO_DOCTYPE.match(xml) is None:
            return None, ()
        root = ET.fromstring(xml)
    except (ET.ParseError, TypeError, ValueError, json.JSONDecodeError):
        return None, ()
    if root.tag != "report":
        return None, ()

    matches: list[ET.Element] = []
    for package in root.findall("package"):
        package_name = package.get("name")
        if not isinstance(package_name, str):
            return None, ()
        for source in package.findall("sourcefile"):
            key = _source_key(package_name, source.get("name"))
            if key is None:
                return None, ()
            if key == expected_key:
                matches.append(source)
    if len(matches) != 1:
        return (False, ()) if not matches else (None, ())

    covered: set[int] = set()
    seen: set[int] = set()
    try:
        for line in matches[0].findall("line"):
            number, instructions = line.get("nr"), line.get("ci")
            if number is None or instructions is None:
                return None, ()
            line_number, hit_count = int(number), int(instructions)
            if line_number < 1 or hit_count < 0 or line_number in seen:
                return None, ()
            seen.add(line_number)
            if hit_count > 0:
                covered.add(line_number)
    except ValueError:
        return None, ()
    return bool(covered), tuple(sorted(covered & set(hypothesis.target_lines)))


class Java(pytest_.Pytest):
    """The inherited pytest driver executes the Python probe; JaCoCo proves Java target execution."""

    name = "java"
    language = "java"

    def driver_files(self) -> dict[str, bytes]:
        return {**super().driver_files(), "collect_jacoco.py": JACOCO_COLLECTOR.encode()}

    def environment(self, role: str) -> Mapping[str, str]:
        return {**super().environment(role),
                "JAVA_TOOL_OPTIONS": f"-javaagent:{JACOCO_AGENT}=destfile={RESULT_DIR}/jacoco.exec,append=true,output=file"}

    def after_command(self) -> list[str]:
        return ["python", f"{PROBE_DIR}/collect_jacoco.py"]

    def result_paths(self) -> list[str]:
        return [path for path in super().result_paths() if not path.endswith("coverage.json")] + [JACOCO_XML, JACOCO_SOURCES]

    def read(self, files: Mapping[str, bytes | None], hypothesis) -> ProbeResult:
        covered_target, covered_lines = read_jacoco(files.get(JACOCO_XML), files.get(JACOCO_SOURCES), hypothesis)
        return replace(super().read(files, hypothesis), covered_target=covered_target, covered_lines=covered_lines)
