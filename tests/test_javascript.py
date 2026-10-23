"""Native JavaScript outcomes through the same kernel and Docker boundary as Python."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import Finding, load_case, revision
from corsair.frameworks import framework
from corsair.kernel import Fix, Gate, Kernel, Label, RoleResult, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from corsair.sandbox.port import SandboxSpec, labels
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/cs-0002-a"
SCRIPT_CASE = ROOT / "cases/cs-0002-b"
IMAGE = "corsair-lite-javascript:dev"


def test_javascript_adapter_is_explicit_and_shares_the_evidence_contract():
    adapter = framework("node-test")
    assert adapter.language == "javascript"
    assert adapter.probe_file.endswith(".cjs")
    assert adapter.guard("module.exports = {};").passed is False
    reference = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
    assert adapter.guard(reference.probe).passed
    assert matrix.select(load_case(CASE)).framework == "node-test"


def test_javascript_post_processing_cannot_instrument_itself():
    adapter = framework("node-test")
    primary = dict(adapter.environment("control"))
    post = adapter.post_command("control", "cli-target.cjs")
    assert post is not None
    assert primary["NODE_V8_COVERAGE"] == "/tmp/corsair/v8"
    assert "NODE_V8_COVERAGE" not in post.environment
    assert post.environment["NODE_OPTIONS"] == ""
    assert dict(adapter.environment("control")) == primary


needs_image = pytest.mark.skipif(not (docker_available() and docker("image", "inspect", IMAGE).returncode == 0),
                                 reason=f"docker or {IMAGE} unavailable (make image)")


@pytest.mark.docker
@pytest.mark.anyio
@needs_image
@pytest.mark.parametrize("mode,expected", [
    ("commonjs", Gate.VERIFIED), ("esm", Gate.VERIFIED), ("bracket-path", Gate.VERIFIED),
    ("driver-tampering", Gate.VERIFIED),
    ("benign", Gate.VERIFIED), ("import-error", Gate.CONTROL_RUN),
    ("application-assertion", Gate.EXPLOIT_RUN), ("syntax-error", Gate.CONTROL_RUN),
    ("hidden-application-frame", Gate.EXPLOIT_RUN), ("missing-invariant", Gate.CONTROL_RUN),
    ("string-invariant", Gate.CONTROL_RUN), ("number-invariant", Gate.CONTROL_RUN),
    ("object-invariant", Gate.CONTROL_RUN),
])
async def test_native_node_outcomes(tmp_path, mode, expected):
    case = load_case(CASE)
    submission = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
    probe = submission.probe
    if mode in ("esm", "application-assertion", "bracket-path", "hidden-application-frame"):
        # Reviewed fixture variants only; probes and target code always execute in containers.
        for revision in ("vulnerable", "fixed"):
            tree = tmp_path / revision
            tree.mkdir()
            source = Path(getattr(case, "revision" if revision == "vulnerable" else "fixed_revision").source, "documents.cjs").read_text()
            filename = "documents.cjs"
            if mode == "esm":
                filename = "documents.mjs"
                source = source.replace("const fs = require('node:fs');", "import fs from 'node:fs';")
                source = source.replace("const path = require('node:path');", "import path from 'node:path';")
                source = source.replace("module.exports = { read_document };", "export { read_document };")
            elif mode == "application-assertion":
                source = source.replace("  return fs.readFileSync", "  require('node:assert/strict').notEqual(name, '../outside.txt');\n  return fs.readFileSync")
            elif mode == "hidden-application-frame":
                source = source.replace("  return fs.readFileSync",
                                        "  if (name.includes('..')) throw new (require('node:assert').AssertionError)({\n"
                                        "    message: 'application rejected unsafe input', stackStartFn: read_document });\n"
                                        "  return fs.readFileSync")
            else:
                filename = "documents[slug].cjs"
            (tree / filename).write_text(source)
        from corsair.case import Finding, revision
        case = case.model_copy(update={"revision": revision(tmp_path / "vulnerable"),
                                       "fixed_revision": revision(tmp_path / "fixed"),
                                       "finding": Finding(title="Path traversal", file_path=filename)})
        submission = submission.model_copy(update={"hypothesis": submission.hypothesis.model_copy(update={"target_file": filename})})
        if mode == "esm":
            probe = probe.replace("require('/work/documents.cjs')", "await import('/work/documents.mjs')")
        elif mode == "bracket-path":
            probe = probe.replace("/work/documents.cjs", "/work/documents[slug].cjs")
    elif mode == "benign":
        probe = probe.replace("EXPLOIT_PAYLOAD = '../outside.txt'", "EXPLOIT_PAYLOAD = 'document.txt'")
    elif mode == "import-error":
        probe = "require('corsair-missing-dependency');\n" + probe
    elif mode == "syntax-error":
        probe += "\nfunction (\n"
    elif mode == "driver-tampering":
        probe = ("process.env.CORSAIR_ROLE = 'exploit';\n"
                 "process.env.CORSAIR_RESULT = '/tmp/corsair/forged.json';\n"
                 "JSON.stringify = () => '{\\\"outcome\\\":\\\"holds\\\"}';\n" + probe)
    elif mode == "missing-invariant":
        probe = probe.replace("return content !== 'outside';", "void content;")
    if mode in ("string-invariant", "number-invariant", "object-invariant"):
        value = {"string-invariant": "'true'", "number-invariant": "1", "object-invariant": "{}"}[mode]
        probe = probe.replace("return content !== 'outside';", "return " + value + ";")
    submission = submission.model_copy(update={"probe": probe})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(submission)
    assert result.gate.stage is expected, result
    if expected is Gate.VERIFIED:
        assert result.verdict.fix is Fix.VERIFIED
        assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
        if mode == "benign":
            assert result.verdict.label is Label.LIKELY_NOT_EXPLOITABLE and result.verdict.rule == "K4"
            assert [run.result for run in result.runs] == [RoleResult.PASS, RoleResult.FAIL] * 2
        else:
            assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.rule == "K1"
            assert [run.result for run in result.runs] == [RoleResult.PASS, RoleResult.PASS, RoleResult.PASS, RoleResult.FAIL]
        for run in result.runs:
            assert run.junit_tests == 1 and run.coverage is not None and run.cleanup_confirmed
            assert run.covered_lines == submission.hypothesis.target_lines
            assert f"test_probe[{run.role}]" in store.get(run.junit).decode()
            native_case = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
            assert (native_case.find("failure") is None) == (run.result is RoleResult.PASS)
            assert native_case.find("error") is None
            assert run.exception_type is None
    elif mode in ("application-assertion", "hidden-application-frame", "missing-invariant",
                  "string-invariant", "number-invariant", "object-invariant"):
        assert result.runs[-1].result is RoleResult.ERROR
        assert result.runs[-1].invariant_held is None
        if mode.endswith("invariant"):
            assert result.runs[-1].exception_type == "TypeError"
    assert backend.labelled(kernel.run_id) == []


def _v8_report(ranges, *, url="file:///work/target.cjs"):
    return {"result": [{"url": url, "functions": [
        {"functionName": "", "isBlockCoverage": True, "ranges": ranges},
    ]}]}


@pytest.fixture(scope="module")
def node_renderer_sandbox():
    adapter = framework("node-test")
    backend = DockerSandboxes()
    run_id = "renderer-" + uuid4().hex[:12]
    name = backend.create(SandboxSpec(image=IMAGE, labels=labels(run_id, "renderer")))
    try:
        made = backend.exec_once(name, ["mkdir", "-p", "/work/.corsair", "/tmp/corsair/v8"],
                                 workdir="/", timeout=60)
        assert made.exit_code == 0
        for filename in ("target.cjs", "unrelated.cjs"):
            backend.write_file(name, "/work/" + filename, b"void 1;\nvoid 2;\n")
        backend.write_file(name, "/work/.corsair/render-v8-coverage.cjs",
                           adapter.driver_files()["render-v8-coverage.cjs"])
        yield backend, name, adapter.post_command("control", "target.cjs")
    finally:
        assert backend.remove(name)
        assert backend.labelled(run_id) == []


@pytest.mark.docker
@needs_image
@pytest.mark.parametrize("raw", [
    pytest.param("null", id="null-report"),
    pytest.param("[]", id="array-report"),
    pytest.param("{}", id="missing-result"),
    pytest.param('{"result":{}}', id="object-result"),
    pytest.param('{"result":[null]}', id="null-script"),
    pytest.param('{"result":[{"url":1,"functions":[]}]}', id="nonstring-url"),
    pytest.param('{"result":[{"url":"file:///work/target.cjs","functions":{}}]}', id="object-functions"),
    pytest.param('{"result":[{"url":"file:///work/target.cjs","functions":[null]}]}', id="null-function"),
    pytest.param('{"result":[{"url":"file:///work/target.cjs","functions":[{"ranges":[]}]}]}',
                 id="missing-function-metadata"),
    pytest.param('{"result":[{"url":"file:///work/target.cjs","functions":'
                 '[{"functionName":"","isBlockCoverage":true,"ranges":{}}]}]}', id="object-ranges"),
    *[pytest.param(json.dumps(_v8_report([bad_range])), id=name) for name, bad_range in [
        ("absent-count", {"startOffset": 0, "endOffset": 16}),
        ("string-count", {"startOffset": 0, "endOffset": 16, "count": "1"}),
        ("nan-like-count", {"startOffset": 0, "endOffset": 16, "count": "NaN"}),
        ("null-count", {"startOffset": 0, "endOffset": 16, "count": None}),
        ("boolean-count", {"startOffset": 0, "endOffset": 16, "count": True}),
        ("fractional-count", {"startOffset": 0, "endOffset": 16, "count": 0.5}),
        ("negative-count", {"startOffset": 0, "endOffset": 16, "count": -1}),
        ("fractional-start", {"startOffset": 0.5, "endOffset": 16, "count": 1}),
        ("fractional-end", {"startOffset": 0, "endOffset": 15.5, "count": 1}),
        ("negative-start", {"startOffset": -1, "endOffset": 16, "count": 1}),
        ("reversed-range", {"startOffset": 16, "endOffset": 0, "count": 1}),
        ("empty-range", {"startOffset": 8, "endOffset": 8, "count": 1}),
        ("past-source-end", {"startOffset": 0, "endOffset": 17, "count": 1}),
        ("string-start", {"startOffset": "0", "endOffset": 16, "count": 1}),
        ("missing-end", {"startOffset": 0, "count": 1}),
        ("null-range", None),
    ]],
    pytest.param(json.dumps(_v8_report([{"startOffset": 0, "endOffset": 16, "count": "overflow"}]))
                 .replace('"overflow"', '1e309'), id="infinite-count"),
    *[pytest.param(json.dumps({"result": [
        *_v8_report([{"startOffset": 0, "endOffset": 16, "count": 1}])["result"],
        *_v8_report([{"startOffset": 0, "endOffset": 16}], url=url)["result"],
    ]}), id=name) for name, url in [
        ("malformed-unrelated-work-file", "file:///work/unrelated.cjs"),
        ("malformed-outside-work", "file:///outside/absent.cjs"),
        ("malformed-nonfile-script", "node:internal/example"),
    ]],
])
def test_node_renderer_rejects_malformed_raw_reports(node_renderer_sandbox, raw):
    # Invalid metadata must abort the entire post-command, even beside an otherwise positive target.
    backend, name, post = node_renderer_sandbox
    backend.write_file(name, "/tmp/corsair/v8/current.json", raw.encode())
    backend.write_file(name, "/tmp/corsair/coverage.json", b"unrendered-marker")
    result = backend.exec_once(name, post.argv, workdir="/work", env=post.environment, timeout=60)
    assert result.exit_code != 0, raw
    assert not result.timed_out and not result.output_limited and not result.container_failed
    assert backend.copy_out(name, ["/tmp/corsair/coverage.json"])["/tmp/corsair/coverage.json"] == b"unrendered-marker"


@pytest.mark.docker
@needs_image
@pytest.mark.parametrize("raw,expected", [
    pytest.param(_v8_report([{"startOffset": 0, "endOffset": 16, "count": 1}]), [1, 2], id="positive"),
    pytest.param(_v8_report([{"startOffset": 0, "endOffset": 16, "count": 0}]), [], id="zero"),
    pytest.param(_v8_report([{"startOffset": 0, "endOffset": 16, "count": 1},
                            {"startOffset": 8, "endOffset": 16, "count": 0}]), [1], id="nested-zero"),
    pytest.param({"result": [
        *_v8_report([{"startOffset": 0, "endOffset": 16, "count": 1}])["result"],
        *_v8_report([{"startOffset": 0, "endOffset": 16, "count": 0}],
                    url="file:///outside/absent.cjs")["result"],
    ]}, [1, 2], id="valid-outside-work-is-excluded"),
])
def test_node_renderer_preserves_valid_ranges(node_renderer_sandbox, raw, expected):
    backend, name, post = node_renderer_sandbox
    backend.write_file(name, "/tmp/corsair/v8/current.json", json.dumps(raw).encode())
    result = backend.exec_once(name, post.argv, workdir="/work", env=post.environment, timeout=60)
    assert result.exit_code == 0, result.stderr.decode()
    report = json.loads(backend.copy_out(name, ["/tmp/corsair/coverage.json"])["/tmp/corsair/coverage.json"])
    assert report == {"files": {"/work/target.cjs": {"executed_lines": expected}}}


@pytest.mark.docker
@pytest.mark.anyio
@needs_image
async def test_node_script_malformed_child_report_is_evidence_error(tmp_path):
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    probe = reference.probe.replace("{ cwd: base, encoding: 'utf8', timeout: 5000 },",
                                    "{ cwd: base, encoding: 'utf8', timeout: 5000, env: {} },")
    probe = probe.replace("    const output = execFileSync(\n",
                          "    delete process.env.NODE_V8_COVERAGE;\n"
                          "    const output = execFileSync(\n")
    probe = probe.replace("    return JSON.parse(output)",
        "    fs.writeFileSync('/tmp/corsair/v8/malformed.json', JSON.stringify({ result: [{\n"
        "      url: 'file:///work/cli-target.cjs', functions: [{\n"
        "        functionName: '', isBlockCoverage: true, ranges: [{\n"
        "          startOffset: 0, endOffset: fs.readFileSync('/work/cli-target.cjs', 'utf8').length,\n"
        "        }],\n"
        "      }],\n"
        "    }] }));\n"
        "    return JSON.parse(output)")
    case = load_case(SCRIPT_CASE)
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_RUN, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert len(result.runs) == 1 and result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].covered_lines == () and result.runs[0].coverage is None
    assert result.runs[0].cleanup_confirmed is True
    assert "coverage post-processing exited 1" in result.runs[0].message
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@needs_image
@pytest.mark.parametrize("target_file,absolute_url", [
    ("cli-target.cjs", False), ("source space/cli-target[slug].cjs", False),
    ("source space/cli-target[slug].cjs", True),
], ids=["cli", "literal-path", "absolute-script-url"])
async def test_node_script_collects_exact_child_lines_and_verifies_fix(tmp_path, target_file, absolute_url):
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    case = load_case(SCRIPT_CASE)
    # Identical basenames from separate children must retain their distinct literal paths.
    decoy_file = "other/" + Path(target_file).name
    trees = {}
    for name in ("vulnerable", "fixed"):
        tree = tmp_path / name
        for filename in (target_file, decoy_file):
            target = tree / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((SCRIPT_CASE / name / "cli-target.cjs").read_text())
        trees[name] = revision(tree)
    case = case.model_copy(update={"revision": trees["vulnerable"], "fixed_revision": trees["fixed"],
                                   "finding": Finding(title="CLI traversal", file_path=target_file)})
    probe = reference.probe.replace("    const output = execFileSync(\n",
                                    "    execFileSync(process.execPath, ['/work/" + decoy_file + "', payload],\n"
                                    "                 { cwd: base, encoding: 'utf8', timeout: 5000 });\n"
                                    "    execFileSync(process.execPath, ['/work/cli-target.cjs', 'document.txt'],\n"
                                    "                 { cwd: base, encoding: 'utf8', timeout: 5000 });\n"
                                    "    const output = execFileSync(\n")
    probe = probe.replace("/work/cli-target.cjs", "/work/" + target_file)
    if absolute_url:
        # Preserve genuine current child ranges in an alternate JSON filename and equivalent absolute URL form.
        probe = probe.replace("    return JSON.parse(output)",
            "    const { fileURLToPath } = require('node:url');\n"
            "    const rawDirectory = process.env.NODE_V8_COVERAGE;\n"
            "    for (const name of fs.readdirSync(rawDirectory).filter(name => name.endsWith('.json'))) {\n"
            "      const raw = JSON.parse(fs.readFileSync(path.join(rawDirectory, name), 'utf8'));\n"
            "      if (!raw.result.some(script => script.url.startsWith('file:') &&\n"
            "          fileURLToPath(script.url) === '/work/" + target_file + "')) continue;\n"
            "      for (const script of raw.result) {\n"
            "        if (script.url.startsWith('file:')) script.url = fileURLToPath(script.url);\n"
            "      }\n"
            "      fs.writeFileSync(path.join(rawDirectory, 'raw-' + name), JSON.stringify(raw));\n"
            "      fs.unlinkSync(path.join(rawDirectory, name));\n"
            "    }\n"
            "    return JSON.parse(output)")
    reference = reference.model_copy(update={"probe": probe, "hypothesis": reference.hypothesis.model_copy(
        update={"target_file": target_file})})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.fix is Fix.VERIFIED
    assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [(run.revision, run.role, run.result) for run in result.runs] == [
        ("vulnerable", "control", RoleResult.PASS), ("vulnerable", "exploit", RoleResult.PASS),
        ("fixed", "control", RoleResult.PASS), ("fixed", "exploit", RoleResult.FAIL),
    ]
    assert [run.invariant_held for run in result.runs] == [True, False, True, True]
    for run in result.runs:
        assert run.covered_target is True and run.covered_lines == (6, 7)
        assert run.junit_tests == 1 and run.cleanup_confirmed is True
        assert run.exception_type is None
        report = json.loads(store.get(run.coverage))
        assert {"/work/" + target_file, "/work/" + decoy_file} <= report["files"].keys()
        for filename in (target_file, decoy_file):
            lines = report["files"]["/work/" + filename]["executed_lines"]
            assert 6 in lines and 7 in lines
            # The surrounding script's positive range must not cover an uncalled function body.
            assert (12 if run.revision == "vulnerable" else 16) not in lines
        if run.revision == "fixed" and run.role == "exploit":
            # Two children take opposite branches in the same target: neither report alone contains this union.
            assert {8, 9, 11, 12} <= set(report["files"]["/work/" + target_file]["executed_lines"])
        assert not any(path.startswith("/work/.corsair/") for path in report["files"])
        native_case = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert native_case.get("name") == f"test_probe[{run.role}]"
        assert (native_case.find("failure") is None) == (run.result is RoleResult.PASS)
        assert native_case.find("error") is None
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@needs_image
async def test_node_script_same_basename_cannot_satisfy_exact_target(tmp_path):
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    tree = tmp_path / "tree"
    for filename in ("source space/cli-target[slug].cjs", "other/cli-target[slug].cjs"):
        target = tree / filename
        target.parent.mkdir(parents=True)
        target.write_text((SCRIPT_CASE / "vulnerable/cli-target.cjs").read_text())
    case = load_case(SCRIPT_CASE).model_copy(update={"revision": revision(tree), "fixed_revision": None,
        "finding": Finding(title="CLI traversal", file_path="source space/cli-target[slug].cjs")})
    reference = reference.model_copy(update={
        "probe": reference.probe.replace("/work/cli-target.cjs", "/work/other/cli-target[slug].cjs"),
        "hypothesis": reference.hypothesis.model_copy(update={"target_file": "source space/cli-target[slug].cjs"})})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_target is False and run.covered_lines == ()
        assert run.result is RoleResult.PASS and run.junit_tests == 1 and run.cleanup_confirmed
        report = json.loads(store.get(run.coverage))
        assert 6 in report["files"]["/work/other/cli-target[slug].cjs"]["executed_lines"]
        assert "/work/source space/cli-target[slug].cjs" not in report["files"]
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@needs_image
@pytest.mark.parametrize("seed_raw,linked_root", [(False, False), (True, False), (True, True)],
                         ids=["clean", "seeded-raw", "linked-raw"])
async def test_node_script_without_child_coverage_is_inconclusive(tmp_path, seed_raw, linked_root):
    reference = Submission.model_validate_json((SCRIPT_CASE / "reference-submission.json").read_text())
    probe = reference.probe.replace("{ cwd: base, encoding: 'utf8', timeout: 5000 },",
                                    "{ cwd: base, encoding: 'utf8', timeout: 5000, env: {} },")
    # Node copies this variable into explicit whitelisted environments unless the parent drops it too.
    probe = probe.replace("    const output = execFileSync(\n",
                          "    delete process.env.NODE_V8_COVERAGE;\n"
                          "    const output = execFileSync(\n")
    if seed_raw:
        # A genuine build-time child report must not establish coverage for this role's uninstrumented child.
        build_script = """node <<'JS'
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const results = '/tmp/corsair';
fs.mkdirSync(results, { recursive: true, mode: 0o777 });
const base = fs.mkdtempSync(path.join(os.tmpdir(), 'corsair-seed-'));
try {
  fs.mkdirSync(path.join(base, 'allowed'));
  fs.writeFileSync(path.join(base, 'allowed/document.txt'), 'seed-document');
  const output = execFileSync(process.execPath, ['/work/cli-target.cjs', 'document.txt'], {
    cwd: base, encoding: 'utf8', env: { NODE_V8_COVERAGE: results + '/v8' },
  });
  if (JSON.parse(output) !== 'seed-document') throw new Error('seed CLI did not run');
  const reports = fs.readdirSync(results + '/v8').filter(name => name.endsWith('.json'));
  if (!reports.some(name => JSON.parse(fs.readFileSync(results + '/v8/' + name)).result.some(
      script => script.url === 'file:///work/cli-target.cjs'))) throw new Error('missing genuine seed report');
  fs.chmodSync(results + '/v8', 0o777);
  for (const name of reports) fs.chmodSync(results + '/v8/' + name, 0o666);
  for (const name of ['result.json', 'junit.xml', 'coverage.json', 'keep.txt']) {
    fs.writeFileSync(results + '/' + name, 'prepared-marker', { mode: 0o666 });
    fs.chmodSync(results + '/' + name, 0o666);
  }
} finally { fs.rmSync(base, { recursive: true, force: true }); }
JS
"""
        if linked_root:
            build_script = build_script.replace("  for (const name of ['result.json', 'junit.xml'",
                "  fs.renameSync(results + '/v8', results + '/saved-v8');\n"
                "  fs.symlinkSync('saved-v8', results + '/v8', 'dir');\n"
                "  for (const name of ['result.json', 'junit.xml'")
        probe = probe.replace("function run_target(payload) {\n",
                              "function run_target(payload) {\n"
                              "  for (const name of ['result.json', 'coverage.json', 'keep.txt']) {\n"
                              "    if (fs.readFileSync('/tmp/corsair/' + name, 'utf8') !== 'prepared-marker') {\n"
                              "      throw new Error('unrelated prepared artifact was removed');\n"
                              "    }\n"
                              "  }\n")
        reference = reference.model_copy(update={"build_script": build_script})
    case = load_case(SCRIPT_CASE)
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference.model_copy(update={"probe": probe}))
    if linked_root:
        # A linked raw root must fail closed rather than retain and attribute its old target report.
        assert result.gate.stage is Gate.CONTROL_RUN, result
        assert result.verdict.label is Label.INCONCLUSIVE
        assert len(result.runs) == 1 and result.runs[0].result is RoleResult.ERROR
        assert result.runs[0].invariant_held is None and result.runs[0].covered_lines == ()
        assert result.runs[0].covered_target is None
        assert result.runs[0].cleanup_confirmed is True
        assert backend.labelled(kernel.run_id) == []
        return
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [run.result for run in result.runs] == [RoleResult.PASS, RoleResult.PASS]
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_target is False and run.covered_lines == ()
        assert run.junit_tests == 1 and run.cleanup_confirmed is True
        report = json.loads(store.get(run.coverage))
        target = report["files"].get("/work/cli-target.cjs")
        assert target is None or target["executed_lines"] == []
    assert backend.labelled(kernel.run_id) == []
