"""Native JavaScript outcomes through the same kernel and Docker boundary as Python."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case
from corsair.frameworks import framework
from corsair.kernel import Fix, Gate, Kernel, Label, RoleResult, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/path-traversal-javascript"
IMAGE = "corsair-lite-javascript:dev"


def test_javascript_adapter_is_explicit_and_shares_the_evidence_contract():
    adapter = framework("node-test")
    assert adapter.language == "javascript"
    assert adapter.probe_file.endswith(".cjs")
    assert adapter.guard("module.exports = {};").passed is False
    reference = Submission.model_validate_json((CASE / "reference-submission.json").read_text())
    assert adapter.guard(reference.probe).passed
    assert matrix.select(load_case(CASE)).framework == "node-test"


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
