"""Focused integrity and contract checks for the pending real-world Batch A cases."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from corsair import matrix
from corsair.case import load_case
from corsair.frameworks import framework
from corsair.kernel import Submission

ROOT = Path(__file__).resolve().parents[1]

CASES = {
    "cs-1001": {
        "runtime": "pytest-cpython312",
        "repository": "https://github.com/encode/starlette",
        "vulnerable_commit": "24c1fac62a80bb153c6548145334fc643991e35a",
        "fixed_commit": "1797de464124b090f10cf570441e8292936d63e3",
        "vulnerable_tree": "1dfea6699ac78d3d94129ad7095d3b58570e2d12ba68504d50d42417074d1e93",
        "fixed_tree": "2e7c23669bdef77ff5c5e082aae2cf183f358e31e5c14551dafe0c16f2808458",
        "target_file": "starlette/staticfiles.py",
        "target_symbol": "StaticFiles.lookup_path",
        "target_lines": [172],
        "fixed_lines": [172],
        "source_closure": [
            "starlette/__init__.py", "starlette/_compat.py", "starlette/_utils.py",
            "starlette/background.py", "starlette/concurrency.py", "starlette/datastructures.py",
            "starlette/exceptions.py", "starlette/responses.py", "starlette/staticfiles.py", "starlette/types.py",
        ],
        "license_hashes": {
            "evidence/source-vulnerable-LICENSE.md": "dcb95677a02240243187e964f941847d19b17821cf99e5afae684fab328c19bf",
            "evidence/source-fixed-LICENSE.md": "dcb95677a02240243187e964f941847d19b17821cf99e5afae684fab328c19bf",
            "evidence/dependency-anyio-LICENSE": "5361ac9dc58f2ef5fd2e9b09c68297c17f04950909bbc8023bdb82eacf22c2b0",
            "evidence/dependency-idna-LICENSE.md": "a59f0b0ef3635874109a4461ca44ff7a70d50696e814767bfaf721d4c9b0db0f",
            "evidence/dependency-sniffio-LICENSE": "652c878488d1456361e08c3f8607fd7ba59892a14103d15cce4ff93c85b5cc8b",
            "evidence/dependency-sniffio-LICENSE.MIT": "3e6dae555eb92787fc82d1d48355677f454c7f65aeb38d3f9e72bf9a3daf034b",
            "evidence/dependency-sniffio-LICENSE.APACHE2": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
        },
    },
    "cs-1002": {
        "runtime": "node-test-node22",
        "repository": "https://github.com/jshttp/cookie",
        "vulnerable_commit": "26031e362d8473112b24a76c7c03b45ef7576d61",
        "fixed_commit": "e10042845354fea83bd8f34af72475eed1dadf5c",
        "vulnerable_tree": "792d611ffe5f410666060902fb72177a459b26635a5db7137bc3bc3a938ccf6a",
        "fixed_tree": "04b040d94abd2f215cfd711940d24a8ca01fc2acce5236ee2633b91483a85a7f",
        "target_file": "index.js",
        "target_symbol": "serialize",
        "target_lines": [119],
        "fixed_lines": [165],
        "source_closure": ["index.js"],
        "license_hashes": {
            "evidence/source-vulnerable-LICENSE": "c02110eedc16c7114f1a9bdc026c65626ce1d9c7e27fd51a8e0feee8a48a6858",
            "evidence/source-fixed-LICENSE": "c02110eedc16c7114f1a9bdc026c65626ce1d9c7e27fd51a8e0feee8a48a6858",
        },
    },
    "cs-1003": {
        "runtime": "javac-java21",
        "repository": "https://github.com/apache/commons-io",
        "vulnerable_commit": "7791a851c4a303f47743b156007fb19c6ed8ed81",
        "fixed_commit": "2736b6fe0b3fa22ec8e2b4184897ecadb021fc78",
        "vulnerable_tree": "4ddfa795d23c802316ad509f476ee3e21879736154fca806ea9ced7ee3ffe414",
        "fixed_tree": "68968c19c8fc9f88e73962068caf0398d46cf6b7f8dce9bb0052b2c1aabe0496",
        "target_file": "src/main/java/org/apache/commons/io/FilenameUtils.java",
        "target_symbol": "FilenameUtils.getPrefixLength",
        "target_lines": [679],
        "fixed_lines": [685],
        "source_closure": [
            "src/main/java/org/apache/commons/io/FilenameUtils.java",
            "src/main/java/org/apache/commons/io/IOCase.java",
        ],
        "license_hashes": {
            "evidence/source-vulnerable-LICENSE.txt": "8c6db340475136df3c1201d458fa5755698eace76e510471ecc9d857d6083dac",
            "evidence/source-fixed-LICENSE.txt": "8c6db340475136df3c1201d458fa5755698eace76e510471ecc9d857d6083dac",
            "evidence/source-vulnerable-NOTICE.txt": "f738390135295a249c4fb7118469ff881ae0bd11401b410f7564a52b7e54c4d2",
            "evidence/source-fixed-NOTICE.txt": "f738390135295a249c4fb7118469ff881ae0bd11401b410f7564a52b7e54c4d2",
        },
    },
    "cs-1004": {
        "runtime": "perl-tap-540",
        "repository": "https://github.com/jmaslak/Net-Netmask",
        "vulnerable_commit": "d98776e4badf6a92f281600756b962e696b906f0",
        "fixed_commit": "9023b403682f1eaadadf6cb71ba0117a1fa4f163",
        "vulnerable_tree": "1d17a8f435d8721e749f1314a6da91369daa214c0df8b2ae56be9f1a29be4a85",
        "fixed_tree": "a3825fa3b85150a70e2b617807afcd20bc7aa9ec2db3626b4535e93a1f4ce2e7",
        "target_file": "lib/Net/Netmask.pm",
        "target_symbol": "quad2int",
        "target_lines": [392],
        "fixed_lines": [398],
        "source_closure": ["lib/Net/Netmask.pm"],
        "license_hashes": {
            "evidence/source-vulnerable-dist.ini": "8f2e592cae4612026e37eaa98500ee3f8991fa82ff34d7cd58d5e90b505e3937",
            "evidence/source-fixed-dist.ini": "195c7b3e4b52f32b1aadcfc46645d7330ed02b63ea09e83b4451924148356ed6",
            "evidence/source-vulnerable-Netmask.pod": "524dc16e913a8a9005eb65f2af461fd4359f3651b2db67c618ce8f06755f18ae",
            "evidence/source-fixed-Netmask.pod": "40362c41b136b4cbcec9ccd8228f9de1799836e49604b1550b38741aa2f7f399",
        },
    },
}


@pytest.mark.parametrize("case_id", CASES)
def test_batch_a_assets_load_with_their_exact_source_and_probe_contract(case_id):
    expected = CASES[case_id]
    case_dir = ROOT / "cases" / case_id

    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_bytes())
    provenance = json.loads((case_dir / "asset-manifest.json").read_text())
    selected = matrix.select(case)

    assert case.case_id == case_id
    assert case.revision.commit == expected["vulnerable_commit"]
    assert case.fixed_revision is not None
    assert case.fixed_revision.commit == expected["fixed_commit"]
    assert case.revision.tree_sha256 == expected["vulnerable_tree"]
    assert case.fixed_revision.tree_sha256 == expected["fixed_tree"]
    assert submission.hypothesis.target_file == expected["target_file"]
    assert submission.hypothesis.target_symbol == expected["target_symbol"]
    assert list(submission.hypothesis.target_lines) == expected["target_lines"]
    assert provenance["repository"] == expected["repository"]
    assert provenance["target"]["fixed_lines"] == expected["fixed_lines"]
    assert provenance["source_closure"] == expected["source_closure"]
    for revision in ("vulnerable", "fixed"):
        actual_closure = sorted(
            path.relative_to(case_dir / revision).as_posix()
            for path in (case_dir / revision).rglob("*") if path.is_file()
        )
        assert actual_closure == expected["source_closure"]
    assert provenance["vendored_source_pair"]["vulnerable"]["tree_sha256"] == expected["vulnerable_tree"]
    assert provenance["vendored_source_pair"]["fixed"]["tree_sha256"] == expected["fixed_tree"]
    assert selected is not None and selected.id == expected["runtime"]
    assert framework(selected.framework).guard(submission.probe).passed

    for relative, digest in expected["license_hashes"].items():
        assert hashlib.sha256((case_dir / relative).read_bytes()).hexdigest() == digest
    for evidence in provenance["evidence"]:
        assert evidence["revision"] in evidence["source_url"]
        assert hashlib.sha256((case_dir / evidence["path"]).read_bytes()).hexdigest() == evidence["sha256"]


@pytest.mark.parametrize("case_id", CASES)
def test_batch_a_oracles_are_evaluator_only_and_keep_qualification_pending(case_id):
    case_dir = ROOT / "cases" / case_id
    case = load_case(case_dir)
    oracle = json.loads((case_dir / "oracle.json").read_text())

    assert oracle["expected_label"] == "LIKELY_EXPLOITABLE"
    assert oracle["expected_fix"] == "verified"
    assert oracle["qualification_status"] == "candidate"
    assert "expected_label" not in case.model_dump_json()
