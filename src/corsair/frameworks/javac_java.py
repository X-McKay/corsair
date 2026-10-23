"""Java 21 adapter using javac/java for execution and JaCoCo for line evidence."""
from __future__ import annotations

import json
import posixpath
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

from .base import PROBE_DIR, RESULT_DIR, PostCommand, ProbeResult
from .reports import read_probe

DRIVER = r'''import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CorsairDriver {
    private static final String ROLE = System.getenv("CORSAIR_ROLE");
    private static final Path RESULT = Path.of(System.getenv("CORSAIR_RESULT"));
    private static final Path JUNIT = Path.of(System.getenv("CORSAIR_JUNIT"));

    private static String escaped(String value, boolean xml) {
        if (value == null) return "";
        StringBuilder out = new StringBuilder();
        int limit = Math.min(value.length(), 2000);
        for (int index = 0; index < limit; index++) {
            char c = value.charAt(index);
            if (xml) {
                if (c == '&') out.append("&amp;");
                else if (c == '<') out.append("&lt;");
                else if (c == '>') out.append("&gt;");
                else if (c == '\"') out.append("&quot;");
                else if (c == '\'') out.append("&apos;");
                else if (c >= 0x20) out.append(c);
            } else {
                if (c == '\\' || c == '\"') out.append('\\').append(c);
                else if (c == '\n') out.append("\\n");
                else if (c == '\r') out.append("\\r");
                else if (c == '\t') out.append("\\t");
                else if (c >= 0x20) out.append(c);
            }
        }
        return out.toString();
    }

    private static void record(String result, Boolean invariantHeld, Throwable error) throws Exception {
        String type = error == null ? null : error.getClass().getSimpleName();
        String message = error == null ? null : error.getMessage();
        String json = "{\"role\":\"" + escaped(ROLE, false) + "\",\"result\":\"" + result
            + "\",\"exception_type\":" + (type == null ? "null" : "\"" + escaped(type, false) + "\"")
            + ",\"message\":" + (message == null ? "null" : "\"" + escaped(message, false) + "\"")
            + ",\"invariant_held\":" + invariantHeld + "}";
        Files.writeString(RESULT, json, StandardCharsets.UTF_8);
        String problem = "";
        if (!"PASS".equals(result)) {
            String tag = "ERROR".equals(result) ? "error" : "failure";
            String detail = error == null ? "security invariant did not match the role expectation" : message;
            problem = "<" + tag + " type=\"" + escaped(type, true) + "\" message=\""
                + escaped(detail, true) + "\"/>";
        }
        String junit = "<testsuites><testsuite tests=\"1\"><testcase name=\"test_probe[" + escaped(ROLE, true)
            + "]\">" + problem + "</testcase></testsuite></testsuites>";
        Files.writeString(JUNIT, junit, StandardCharsets.UTF_8);
    }

    private static final class TypeError extends Exception {
        TypeError(String message) { super(message); }
    }

    public static void main(String[] args) throws Exception {
        final boolean expected = "control".equals(ROLE);
        final Boolean invariant;
        try {
            String payload = expected ? CorsairProbe.CONTROL_PAYLOAD : CorsairProbe.EXPLOIT_PAYLOAD;
            Object observed = CorsairProbe.runTarget(payload);
            if (!(observed instanceof Boolean)) {
                throw new TypeError("runTarget(payload) must return a boolean security invariant");
            }
            invariant = (Boolean) observed;
        } catch (Throwable error) {
            record("ERROR", null, error);
            error.printStackTrace();
            System.exit(1);
            return;
        }
        String result = invariant.booleanValue() == expected ? "PASS" : "FAIL";
        record(result, invariant, null);
        if ("FAIL".equals(result)) System.exit(1);
    }
}
'''

RUNNER = r'''#!/bin/sh
set -eu
classes=/work/.corsair-java/classes
classpath="/work/.corsair:${classes}:/work/.corsair-java/lib/*"
if [ ! -d "$classes" ]; then
  echo "build_script must compile target classes into $classes" >&2
  exit 2
fi
raw=/tmp/corsair/jacoco.exec
if [ -L /tmp/corsair ] || [ -L "$raw" ] || { [ -e "$raw" ] && { [ ! -f "$raw" ] || [ ! -w "$raw" ]; }; }; then
  echo "unsafe or unwritable JaCoCo raw destination" >&2
  exit 2
fi
# A sealed build can contain genuine old data. Reset before javac's JVM starts, without unlinking siblings.
if ! : > "$raw"; then
  echo "cannot reset JaCoCo raw destination" >&2
  exit 2
fi
javac -cp "$classpath" -d /work/.corsair /work/.corsair/CorsairProbe.java /work/.corsair/CorsairDriver.java || exit $?
exec java -cp "$classpath" CorsairDriver
'''

RENDERER = r'''#!/bin/sh
set -eu
raw=/tmp/corsair/jacoco.exec
if [ -L /tmp/corsair ] || [ -L "$raw" ] || [ ! -f "$raw" ] || [ ! -r "$raw" ] || [ ! -w "$raw" ]; then
  echo "missing or unsafe JaCoCo raw input" >&2
  exit 2
fi
exec java -jar /opt/corsair/jacoco-cli.jar report "$raw" \
  --classfiles /work/.corsair-java/classes --sourcefiles /work --xml /tmp/corsair/jacoco.xml
'''


_JAVA_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_PACKAGE = re.compile(rf"\bpackage\s+({_JAVA_IDENTIFIER}(?:\s*\.\s*{_JAVA_IDENTIFIER})*)\s*;")


def _source_package(path: Path) -> str | None:
    """Return a Java source's declared package, or ``""`` for the default package.

    JaCoCo identifies source as package plus basename and drops Maven/module roots. This small lexer masks comments
    and literals before reading the package declaration. Unicode escapes are rejected because Java expands them
    before tokenization and a partial lexer could otherwise assign the wrong identity.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if "\\u" in text or "\\U" in text:
        return None
    masked = list(text)
    index = 0
    state = "code"
    while index < len(text):
        pair = text[index:index + 2]
        triple = text[index:index + 3]
        if state == "code":
            if pair == "//":
                masked[index:index + 2] = "  "
                state, index = "line", index + 2
                continue
            if pair == "/*":
                masked[index:index + 2] = "  "
                state, index = "block", index + 2
                continue
            if triple == '\"\"\"':
                masked[index:index + 3] = "   "
                state, index = "text", index + 3
                continue
            if text[index] in ('\"', "'"):
                state = "string" if text[index] == '\"' else "char"
                masked[index] = " "
                index += 1
                continue
        elif state == "line":
            if text[index] == "\n":
                state = "code"
            else:
                masked[index] = " "
            index += 1
            continue
        elif state == "block":
            if pair == "*/":
                masked[index:index + 2] = "  "
                state, index = "code", index + 2
            else:
                if text[index] != "\n":
                    masked[index] = " "
                index += 1
            continue
        elif state == "text":
            if text[index] == "\\" and index + 1 < len(text):
                masked[index:index + 2] = "  "
                index += 2
            elif triple == '\"\"\"':
                masked[index:index + 3] = "   "
                state, index = "code", index + 3
            else:
                if text[index] != "\n":
                    masked[index] = " "
                index += 1
            continue
        else:
            quote = '\"' if state == "string" else "'"
            if text[index] == "\\" and index + 1 < len(text):
                masked[index:index + 2] = "  "
                index += 2
            else:
                if text[index] == quote:
                    state = "code"
                if text[index] != "\n":
                    masked[index] = " "
                index += 1
            continue
        index += 1
    if state not in ("code", "line"):
        return None
    matches = _PACKAGE.findall("".join(masked))
    if len(matches) > 1:
        return None
    return re.sub(r"\s+", "", matches[0]) if matches else ""


def _unique_source_key(source: Path, target: str) -> str | None:
    """Prove that JaCoCo's package/basename key names exactly the target source file."""
    root = source.resolve()
    target_path = root / target
    try:
        if not target_path.resolve().is_relative_to(root) or not target_path.is_file():
            return None
    except (OSError, RuntimeError):
        return None
    package = _source_package(target_path)
    if package is None:
        return None
    key = posixpath.join(package.replace(".", "/"), target_path.name) if package else target_path.name
    matches: list[str] = []
    for candidate in root.rglob(target_path.name):
        try:
            relative = candidate.relative_to(root)
            if ".git" in relative.parts:
                continue
            if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        candidate_package = _source_package(candidate)
        if candidate_package is None:
            return None
        candidate_key = (posixpath.join(candidate_package.replace(".", "/"), candidate.name)
                         if candidate_package else candidate.name)
        if candidate_key == key:
            matches.append(relative.as_posix())
    return key if matches == [posixpath.normpath(target)] else None


def _jacoco_coverage(data: bytes | None, target: str, source: Path) -> bytes | None:
    if not data:
        return None
    try:
        root = ET.fromstring(data)
        if root.tag != "report":
            return None
        key = _unique_source_key(source, target)
        if key is None:
            return None
        lines: set[int] = set()
        matched = False
        for package in root.findall("package"):
            prefix = package.get("name", "").strip("/")
            for source in package.findall("sourcefile"):
                name = source.get("name")
                reported = posixpath.join(prefix, name) if prefix and name else name
                if reported != key:
                    continue
                matched = True
                lines.update(int(line.get("nr", "0")) for line in source.findall("line")
                             if int(line.get("ci", "0")) > 0)
        report = {"files": {target: {"executed_lines": sorted(lines)}} if matched else {}}
        return json.dumps(report).encode()
    except (ET.ParseError, TypeError, ValueError):
        return None


class JavacJava:
    name = "javac-java"
    language = "java"
    target_suffixes = (".java",)
    guidance = "java-javac"
    probe_file = "CorsairProbe.java"

    def guard(self, probe: str):
        from ..kernel import Gate, GateVerdict

        required = ("class CorsairProbe", "CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "runTarget")
        missing = [symbol for symbol in required if symbol not in probe]
        banned = re.search(r"\b(?:Mockito|PowerMock|EasyMock)\b", probe)
        reason = (f"probe must define {', '.join(missing)}" if missing else
                  "mocking frameworks cannot own the observed property" if banned else
                  "symbol preflight passed; javac validates types and signatures in the container")
        return GateVerdict(passed=not missing and banned is None, stage=Gate.AST_GUARD, reason=reason)

    def driver_files(self) -> dict[str, bytes]:
        return {"CorsairDriver.java": DRIVER.encode(), "run-java.sh": RUNNER.encode(),
                "render-java.sh": RENDERER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        return ["sh", f"{PROBE_DIR}/run-java.sh"]

    def post_command(self, role: str, target_file: str) -> PostCommand:
        environment = dict(self.environment(role))
        environment.pop("JAVA_TOOL_OPTIONS")
        # Omission from docker exec's environment does not clear an image-level setting.
        return PostCommand(("env", "-u", "JAVA_TOOL_OPTIONS", "sh", f"{PROBE_DIR}/render-java.sh"), environment)

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json",
                "CORSAIR_JUNIT": f"{RESULT_DIR}/junit.xml", "HOME": "/tmp",
                "JAVA_TOOL_OPTIONS": "-javaagent:/opt/corsair/jacoco-agent.jar="
                                     f"destfile={RESULT_DIR}/jacoco.exec,append=true,dumponexit=true"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/jacoco.xml"]

    def read(self, files: Mapping[str, bytes | None], hypothesis, role: str, source: Path) -> ProbeResult:
        normalized = dict(files)
        normalized[f"{RESULT_DIR}/coverage.json"] = _jacoco_coverage(
            files.get(f"{RESULT_DIR}/jacoco.xml"), hypothesis.target_file, source)
        return read_probe(normalized, hypothesis, role, native_error_kind="error")
