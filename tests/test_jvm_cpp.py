"""Native-coverage adapter tests; the subprocess fixture is a host harness, not container isolation evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from corsair.adapters.frameworks import pytest_
from corsair.adapters.frameworks.jvm import JACOCO_COLLECTOR, JACOCO_SOURCES, JACOCO_XML, Java, read_jacoco
from corsair.adapters.frameworks.native_cpp import GCOV_COLLECTOR, GCOV_JSON, Cpp, read_gcov
from corsair.domain.verification import Outcome

JAVA_TARGET = SimpleNamespace(target_file="module/src/main/java/com/acme/Target.java", target_lines=(7, 9))
CPP_TARGET = SimpleNamespace(target_file="src/target.cpp", target_lines=(4, 7))


def jacoco_manifest(target=JAVA_TARGET, *, path: str | None = None) -> bytes:
    return json.dumps(
        {
            "format": "corsair-jacoco/1",
            "ok": True,
            "sources": {"com/acme/Target.java": path or f"/work/{target.target_file}"},
        }
    ).encode()


def jacoco_xml(*, package="com/acme", source="Target.java", lines='<line nr="7" ci="2"/>') -> bytes:
    return f'<report><package name="{package}"><sourcefile name="{source}">{lines}</sourcefile></package></report>'.encode()


def gcov_report(*files: object) -> bytes:
    return json.dumps(
        {"format": "corsair-gcov/1", "ok": True, "reports": [{"format_version": "1", "files": list(files)}]}
    ).encode()


def test_jacoco_binds_the_full_standard_source_path_and_only_positive_instruction_hits():
    covered = read_jacoco(
        jacoco_xml(lines='<line nr="7" ci="1"/><line nr="9" ci="0"/>'), jacoco_manifest(), JAVA_TARGET
    )
    assert covered == (True, (7,))
    # Same basename but another package is not coverage for the reported target.
    assert read_jacoco(jacoco_xml(package="com/other"), jacoco_manifest(), JAVA_TARGET) == (False, ())
    # A source catalog entry from another module cannot claim this target.
    assert read_jacoco(
        jacoco_xml(), jacoco_manifest(path="/work/other/src/main/java/com/acme/Target.java"), JAVA_TARGET
    ) == (None, ())


@pytest.mark.parametrize(
    "xml, manifest",
    [
        (b'<!DOCTYPE report [<!ENTITY x "x">]><report/>', jacoco_manifest()),
        (jacoco_xml(lines='<line nr="7" ci="1"/><line nr="7" ci="1"/>'), jacoco_manifest()),
        (
            jacoco_xml(),
            b'{"format":"corsair-jacoco/1","ok":true,"sources":{"com/acme/Target.java":"/work/a","com/acme/Target.java":"/work/b"}}',
        ),
    ],
)
def test_jacoco_parser_fails_closed_for_untrusted_or_ambiguous_native_evidence(xml, manifest):
    assert read_jacoco(xml, manifest, JAVA_TARGET) == (None, ())


def test_gcov_binds_only_the_exact_absolute_target_and_rejects_ambiguous_reports():
    source = {
        "file": "/work/src/target.cpp",
        "lines": [{"line_number": 4, "count": 3}, {"line_number": 7, "count": 0}],
    }
    assert read_gcov(gcov_report(source), CPP_TARGET) == (True, (4,))
    assert read_gcov(gcov_report({**source, "file": "/work/elsewhere/target.cpp"}), CPP_TARGET) == (False, ())
    assert read_gcov(gcov_report(source, source), CPP_TARGET) == (None, ())


@pytest.mark.parametrize(
    "report",
    [
        gcov_report({"file": "/work/src/target.cpp", "lines": [{"line_number": 4, "count": True}]}),
        gcov_report(
            {
                "file": "/work/src/target.cpp",
                "lines": [{"line_number": 4, "count": 1}, {"line_number": 4, "count": 2}],
            }
        ),
        b'{"format":"corsair-gcov/1","ok":true,"reports":[],"reports":[]}',
    ],
)
def test_gcov_parser_fails_closed_for_invalid_or_duplicate_json(report):
    assert read_gcov(report, CPP_TARGET) == (None, ())


def test_native_adapters_keep_the_shared_python_driver_but_replace_its_coverage_evidence():
    junit = b'<testsuites><testsuite><testcase name="test_probe[control]"/></testsuite></testsuites>'
    record = json.dumps(
        {"role": "control", "outcome": "holds", "exception_type": None, "message": None}
    ).encode()
    files = {
        "/tmp/corsair/result.json": record,
        "/tmp/corsair/junit.xml": junit,
        "/tmp/corsair/coverage.json": b'{"files":{"/work/src/target.cpp":{"executed_lines":[4,7]}}}',
        JACOCO_XML: jacoco_xml(),
        JACOCO_SOURCES: jacoco_manifest(),
        GCOV_JSON: gcov_report({"file": "/work/src/target.cpp", "lines": [{"line_number": 4, "count": 1}]}),
    }
    java, cpp = Java(), Cpp()
    assert java.command("control", "anything") == pytest_.Pytest().command("control", "anything")
    assert cpp.command("control", "anything") == pytest_.Pytest().command("control", "anything")
    assert java.after_command() == ["python", "/work/.corsair/collect_jacoco.py"]
    assert cpp.after_command() == ["python", "/work/.corsair/collect_gcov.py"]
    assert "/tmp/corsair/coverage.json" not in java.result_paths()
    assert "/tmp/corsair/coverage.json" not in cpp.result_paths()
    assert (
        "-javaagent:/opt/corsair/jacoco/jacocoagent.jar=" in java.environment("control")["JAVA_TOOL_OPTIONS"]
    )
    assert cpp.environment("control")["GCOV_PREFIX"] == "/tmp/corsair/gcov"
    java_result, cpp_result = java.read(files, JAVA_TARGET), cpp.read(files, CPP_TARGET)
    assert java_result.outcome is Outcome.HOLDS and java_result.covered_lines == (7,)
    # The inherited Python coverage says line 7 ran; gcov, the only admissible C++ evidence, says it did not.
    assert cpp_result.outcome is Outcome.HOLDS and cpp_result.covered_lines == (4,)


def _jacoco_tools() -> tuple[Path, Path] | None:
    directory = Path(os.environ.get("CORSAIR_JACOCO_DIR", "/opt/corsair/jacoco"))
    agent, cli = directory / "jacocoagent.jar", directory / "jacococli.jar"
    if all(shutil.which(command) for command in ("java", "javac")) and agent.is_file() and cli.is_file():
        return agent, cli
    return None


@pytest.mark.skipif(_jacoco_tools() is None, reason="JDK and pinned JaCoCo CLI/agent are required")
def test_jacoco_collector_runs_against_a_real_local_compiled_target(tmp_path):
    agent, cli = _jacoco_tools()  # type: ignore[misc]
    work, result = tmp_path / "work", tmp_path / "result"
    source_dir, classes = (
        work / "module" / "src" / "main" / "java" / "com" / "acme",
        work / "module" / "target" / "classes",
    )
    source_dir.mkdir(parents=True)
    classes.mkdir(parents=True)
    source = source_dir / "Target.java"
    source.write_text(
        "package com.acme;\npublic class Target {\n  static int guarded(int value) {\n    if (value > 0) return value;\n    return 0;\n  }\n  public static void main(String[] ignored) { guarded(1); }\n}\n"
    )
    subprocess.run(["javac", "-g", "-d", str(classes), str(source)], check=True)
    subprocess.run(
        ["java", "-cp", str(classes), "com.acme.Target"],
        check=True,
        env={
            **os.environ,
            "JAVA_TOOL_OPTIONS": f"-javaagent:{agent}=destfile={result / 'jacoco.exec'},append=true,output=file",
        },
    )
    collector = (
        JACOCO_COLLECTOR.replace('WORKDIR = Path("/work")', f"WORKDIR = Path({str(work)!r})")
        .replace('RESULT_DIR = Path("/tmp/corsair")', f"RESULT_DIR = Path({str(result)!r})")
        .replace('CLI = "/opt/corsair/jacoco/jacococli.jar"', f"CLI = {str(cli)!r}")
    )
    script = tmp_path / "collect_jacoco.py"
    script.write_text(collector)
    subprocess.run([sys.executable, str(script)], check=True)
    manifest = json.loads((result / "jacoco-sources.json").read_text())
    assert manifest["ok"] is True
    xml = (result / "jacoco.xml").read_bytes()
    # The collector catalog records the temporary root; normalize only for the adapter parser's fixed /work contract.
    manifest["sources"]["com/acme/Target.java"] = "/work/module/src/main/java/com/acme/Target.java"
    target = SimpleNamespace(target_file="module/src/main/java/com/acme/Target.java", target_lines=(4, 5))
    assert read_jacoco(xml, json.dumps(manifest).encode(), target) == (True, (4,))


@pytest.mark.skipif(
    not all(shutil.which(command) for command in ("g++", "gcov")), reason="g++ and gcov are required"
)
def test_gcov_collector_runs_against_a_real_local_compiled_target(tmp_path):
    work, result = tmp_path / "work", tmp_path / "result"
    build, source_dir = work / "build", work / "src"
    build.mkdir(parents=True)
    source_dir.mkdir()
    source = source_dir / "target.cpp"
    source.write_text(
        "int guarded(int value) {\n  if (value > 0) return value;\n  return 0;\n}\nint main() { guarded(1); return 0; }\n"
    )
    executable = build / "target"
    subprocess.run(["g++", "--coverage", "-O0", "-g", str(source), "-o", str(executable)], check=True)
    prefix = result / "gcov"
    # The committed adapter uses /work (one leading component); this local harness has a deeper temp path.
    strip = len(work.resolve().parts) - 1
    subprocess.run(
        [str(executable)],
        check=True,
        env={**os.environ, "GCOV_PREFIX": str(prefix), "GCOV_PREFIX_STRIP": str(strip)},
    )
    collector = GCOV_COLLECTOR.replace('WORKDIR = Path("/work")', f"WORKDIR = Path({str(work)!r})").replace(
        'RESULT_DIR = Path("/tmp/corsair")', f"RESULT_DIR = Path({str(result)!r})"
    )
    script = tmp_path / "collect_gcov.py"
    script.write_text(collector)
    subprocess.run([sys.executable, str(script)], check=True)
    aggregate = json.loads((result / "gcov.json").read_text())
    assert aggregate["ok"] is True and len(aggregate["reports"]) == 1
    files = aggregate["reports"][0]["files"]
    target = next(entry for entry in files if entry["file"] == str(source))
    assert any(line["line_number"] == 2 and line["count"] > 0 for line in target["lines"])
