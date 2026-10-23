"""Node and Ruby adapters: native coverage parsers and real pinned-toolchain smoke coverage."""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from corsair.frameworks import pytest_
from corsair.frameworks.node import NODE_LCOV, NODE_V8_DIR, Node, read_lcov
from corsair.frameworks.ruby import RUBY_RESULTSET, SIMPLECOV_BOOTSTRAP, Ruby, read_resultset
from corsair.kernel import Outcome
from corsair.sandbox.docker import docker, docker_available

NODE_TARGET = SimpleNamespace(target_file="src/target.ts", target_lines=(2, 3))
NODE_JS_TARGET = SimpleNamespace(target_file="src/target.js", target_lines=(2,))
RUBY_TARGET = SimpleNamespace(target_file="lib/target.rb", target_lines=(2, 3))
NODE_IMAGE = "corsair-lite-node:dev"
RUBY_IMAGE = "corsair-lite-ruby:dev"


def lcov(*records: str) -> bytes:
    return ("\n".join(records) + "\n").encode()


def lcov_record(source: str, lines: str = "DA:2,1\nDA:3,0") -> str:
    return "\n".join(("TN:", f"SF:{source}", "FNF:0", "FNH:0", lines, "LF:2", "LH:1", "end_of_record"))


def resultset(*, source: str = "lib/target.rb", lines: object = None, role: str = "control",
              timestamp: object = 1.0, value: object = None) -> bytes:
    if lines is None:
        lines = [None, 1, 1]
    if value is None:
        value = {"lines": lines}
    return json.dumps({f"corsair-{role}": {"coverage": {source: value}, "timestamp": timestamp}}).encode()


def driver_files() -> dict[str, bytes]:
    junit = b'<testsuites><testsuite><testcase name="test_probe[control]"/></testsuite></testsuites>'
    record = json.dumps({"role": "control", "outcome": "holds", "exception_type": None, "message": None}).encode()
    return {"/tmp/corsair/result.json": record, "/tmp/corsair/junit.xml": junit,
            # This intentionally contradictory Python evidence must never become Node/Ruby target evidence.
            "/tmp/corsair/coverage.json": b'{"files":{"/work/not-the-native-target.py":{"executed_lines":[999]}}}'}


def test_lcov_binds_the_exact_canonical_work_target_and_reports_only_positive_line_hits():
    report = lcov(lcov_record("/work/src/target.ts", "DA:2,2\nDA:3,0"))
    assert read_lcov(report, NODE_TARGET) == (True, (2,))
    assert read_lcov(lcov(lcov_record("src/other.ts")), NODE_TARGET) == (False, ())


@pytest.mark.parametrize("report", [
    lcov(lcov_record("src/target.ts", "DA:2,1\nDA:2,2")),
    lcov(lcov_record("src/target.ts", "DA:0,1")),
    lcov(lcov_record("src/target.ts", "DA:2,-1")),
    lcov(lcov_record("src/target.ts", "FNF:wat\nDA:2,1")),
    lcov(lcov_record("src/target.ts", "FN:0,name\nDA:2,1")),
    lcov(lcov_record("src/target.ts", "BRDA:2,0,0,wat\nDA:2,1")),
    lcov("SF:src/target.ts\nDA:2,1\nend_of_record\ntrailing"),
])
def test_lcov_parser_fails_closed_for_malformed_native_reports(report):
    assert read_lcov(report, NODE_TARGET) == (None, ())


def test_lcov_rejects_duplicate_canonical_targets_and_path_traversal():
    duplicate = lcov(lcov_record("src/target.ts"), lcov_record("/work/src/target.ts"))
    assert read_lcov(duplicate, NODE_TARGET) == (None, ())
    assert read_lcov(lcov(lcov_record("../src/target.ts")), NODE_TARGET) == (None, ())
    assert read_lcov(lcov(lcov_record("/work/src/../src/target.ts")), NODE_TARGET) == (None, ())
    assert read_lcov(lcov(lcov_record("/etc/target.ts")), NODE_TARGET) == (None, ())
    assert read_lcov(lcov(lcov_record("src\\target.ts")), NODE_TARGET) == (None, ())


def test_simplecov_binds_the_exact_role_and_canonical_work_target():
    assert read_resultset(resultset(lines=[None, 1, 0]), RUBY_TARGET, "control") == (True, (2,))
    assert read_resultset(resultset(source="lib/other.rb"), RUBY_TARGET, "control") == (False, ())
    assert read_resultset(resultset(), RUBY_TARGET, "exploit") == (None, ())


@pytest.mark.parametrize("report", [
    b'{"corsair-control":{"coverage":{},"timestamp":1},"corsair-control":{"coverage":{},"timestamp":1}}',
    b'{"corsair-control":{"coverage":{"lib/target.rb":{"lines":[null,1],"lines":[null,1]}},"timestamp":1}}',
    resultset(lines=[None, True]),
    resultset(lines=[None, -1]),
    resultset(lines=[None, "1"]),
    resultset(timestamp=float("nan")),
    resultset(value={"lines": [None, 1], "branches": []}),
    resultset(value={"lines": [None, 1], "unexpected": 1}),
])
def test_simplecov_parser_fails_closed_for_malformed_or_duplicate_json(report):
    assert read_resultset(report, RUBY_TARGET, "control") == (None, ())


def test_simplecov_rejects_duplicate_canonical_targets_and_path_traversal():
    duplicate = json.dumps({"corsair-control": {"timestamp": 1, "coverage": {
        "lib/target.rb": {"lines": [None, 1]}, "/work/lib/target.rb": {"lines": [None, 1]},
    }}}).encode()
    assert read_resultset(duplicate, RUBY_TARGET, "control") == (None, ())
    assert read_resultset(resultset(source="../lib/target.rb"), RUBY_TARGET, "control") == (None, ())
    assert read_resultset(resultset(source="/work/lib/../lib/target.rb"), RUBY_TARGET, "control") == (None, ())


def test_adapters_preserve_the_python_driver_but_replace_coverage_with_only_native_evidence():
    node_files = driver_files() | {NODE_LCOV: lcov(lcov_record("src/target.ts", "DA:2,1\nDA:3,1"))}
    ruby_files = driver_files() | {RUBY_RESULTSET: resultset(lines=[None, 1, 1])}
    node, ruby = Node(), Ruby()
    assert node.command("control", "anything") == pytest_.Pytest().command("control", "anything")
    assert ruby.command("control", "anything") == pytest_.Pytest().command("control", "anything")
    assert node.environment("control")["NODE_V8_COVERAGE"] == NODE_V8_DIR
    assert ruby.environment("control")["RUBYOPT"] == "-r/work/.corsair/corsair_simplecov.rb"
    assert "/tmp/corsair/coverage.json" not in node.result_paths()
    assert "/tmp/corsair/coverage.json" not in ruby.result_paths()
    node_result, ruby_result = node.read(node_files, NODE_TARGET), ruby.read(ruby_files, RUBY_TARGET)
    assert node_result.outcome is Outcome.HOLDS and node_result.covered_lines == (2, 3)
    assert ruby_result.outcome is Outcome.HOLDS and ruby_result.covered_lines == (2, 3)


@pytest.mark.docker
@pytest.mark.skipif(not (docker_available() and docker("image", "inspect", NODE_IMAGE).returncode == 0),
                    reason=f"Docker or {NODE_IMAGE} unavailable (build images/node first)")
def test_node_image_runs_js_and_remapped_typescript_coverage_as_uid_1000_with_readonly_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "src" / "target.js").write_text(
        'export function jsTarget(value) {\n  return value === "control" ? "safe" : "observed";\n}\n')
    (tmp_path / "src" / "target.ts").write_text(
        'export function tsTarget(value: string): string {\n  return value === "control" ? "safe" : "observed";\n}\n')
    (tmp_path / "runner.mjs").write_text(
        'import { jsTarget } from "./src/target.js";\nimport { tsTarget } from "./src/target.ts";\n'
        'if (jsTarget("control") !== "safe" || tsTarget("control") !== "safe") process.exit(2);\n')
    command = '''set -eu
        test "$(id -u)" = 1000
        test ! -w /work/src/target.ts
        mkdir -p /tmp/corsair/node/v8
        NODE_V8_COVERAGE=/tmp/corsair/node/v8 tsx runner.mjs
        c8 report --temp-directory /tmp/corsair/node/v8 --reports-dir /tmp/corsair/node --reporter lcovonly --exclude-after-remap
        cat /tmp/corsair/node/lcov.info
    '''
    result = subprocess.run([
        "docker", "run", "--rm", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--user", "1000:1000", "--mount", f"type=bind,src={tmp_path},dst=/work,readonly", NODE_IMAGE,
        "sh", "-ceu", command,
    ], check=True, text=True, capture_output=True)
    assert read_lcov(result.stdout.encode(), NODE_TARGET) == (True, (2, 3))
    assert read_lcov(result.stdout.encode(), NODE_JS_TARGET) == (True, (2,))


@pytest.mark.docker
@pytest.mark.skipif(not (docker_available() and docker("image", "inspect", RUBY_IMAGE).returncode == 0),
                    reason=f"Docker or {RUBY_IMAGE} unavailable (build images/ruby first)")
def test_ruby_image_runs_simplecov_under_kernel_rubyopt_as_uid_1000_with_readonly_source(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / ".corsair").mkdir()
    (tmp_path / "lib" / "target.rb").write_text(
        'module Target\n  def self.native_target(value)\n    value == "control" ? "safe" : "observed"\n  end\nend\n')
    (tmp_path / "runner.rb").write_text(
        'require_relative "lib/target"\nabort "unexpected target result" unless Target.native_target("control") == "safe"\n')
    (tmp_path / ".corsair" / "corsair_simplecov.rb").write_text(SIMPLECOV_BOOTSTRAP)
    command = '''set -eu
        test "$(id -u)" = 1000
        test ! -w /work/lib/target.rb
        ruby runner.rb
        cat /tmp/corsair/ruby/.resultset.json
    '''
    result = subprocess.run([
        "docker", "run", "--rm", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--user", "1000:1000", "-e", "CORSAIR_ROLE=control",
        "-e", "RUBYOPT=-r/work/.corsair/corsair_simplecov.rb",
        "--mount", f"type=bind,src={tmp_path},dst=/work,readonly", RUBY_IMAGE, "sh", "-ceu", command,
    ], check=True, text=True, capture_output=True)
    report = result.stdout[result.stdout.index("{"):].encode()
    assert read_resultset(report, RUBY_TARGET, "control") == (True, (2, 3))


@pytest.mark.docker
@pytest.mark.parametrize("image, tools", [
    (NODE_IMAGE, ("node --version", "python --version", "python -m pytest --version", "python -m coverage --version", "c8 --version", "tsx --version", "tsc --version", "vite --version")),
    (RUBY_IMAGE, ("ruby --version", "bundle --version", "rake --version", "gem list -i simplecov -v 0.22.0", "python --version", "python -m pytest --version", "python -m coverage --version")),
])
def test_images_are_root_owned_build_runtimes_with_an_existing_uid_1000_probe_identity(image, tools):
    if not docker_available() or docker("image", "inspect", image).returncode != 0:
        pytest.skip(f"Docker or {image} unavailable")
    command = "set -eu; test \"$(id -u)\" = 0; getent passwd 1000; " + "; ".join(tools)
    subprocess.run(["docker", "run", "--rm", "--network=none", image, "sh", "-ceu", command], check=True)


def test_lcov_never_borrows_hits_from_a_later_unrelated_record():
    missed = lcov(lcov_record('src/target.ts', 'DA:2,0\nDA:3,0'),
                  lcov_record('src/other.ts', 'DA:2,10\nDA:3,10'))
    reached = lcov(lcov_record('src/target.ts', 'DA:2,1\nDA:3,0'),
                   lcov_record('src/other.ts', 'DA:2,0\nDA:3,1'))
    assert read_lcov(missed, NODE_TARGET) == (False, ())
    assert read_lcov(reached, NODE_TARGET) == (True, (2,))
