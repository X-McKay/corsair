"""Focused integrity and contract checks for the pending real-world Batch B cases."""
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

JINJA_CLOSURE = [
    "jinja2/__init__.py", "jinja2/_identifier.py", "jinja2/async_utils.py", "jinja2/bccache.py",
    "jinja2/compiler.py", "jinja2/constants.py", "jinja2/debug.py", "jinja2/defaults.py",
    "jinja2/environment.py", "jinja2/exceptions.py", "jinja2/ext.py", "jinja2/filters.py",
    "jinja2/idtracking.py", "jinja2/lexer.py", "jinja2/loaders.py", "jinja2/meta.py",
    "jinja2/nativetypes.py", "jinja2/nodes.py", "jinja2/optimizer.py", "jinja2/parser.py",
    "jinja2/py.typed", "jinja2/runtime.py", "jinja2/sandbox.py", "jinja2/tests.py",
    "jinja2/utils.py", "jinja2/visitor.py",
]

BC_CLOSURE = [
    "crypto/DataLengthException.java", "crypto/RuntimeCryptoException.java",
    "crypto/generators/BCrypt.java", "crypto/generators/OpenBSDBCrypt.java", "util/Arrays.java",
    "util/Objects.java", "util/Pack.java", "util/StringList.java", "util/Strings.java",
    "util/encoders/UTF8.java",
]

CASES = {
    "cs-1005": {
        "runtime": "pytest-cpython312",
        "repository": "https://github.com/pallets/jinja",
        "vulnerable_commit": "033c20015c7ca899ab52eb921bb0f08e6d3dd145",
        "fixed_commit": "90457bbf33b8662926ae65cdde4c4c32e756e403",
        "upstream_trees": [
            "a397e3d5a7bafbd038763213e47f2f042fd3226c8dc495736a182696e0d1568e",
            "c36a98956a752fe404e934455510244fa759b2d09a05165bcd4a5442e16e4630",
        ],
        "vendored_trees": [
            "ec56261e9388b9844260ddcfd4130685f18ead7eafaaed6678d2d4e4266a9ab7",
            "74d1c0effb83fbc86e6cc11e2f8f385ea5f4589f12de43f92d9fa50e104c10f5",
        ],
        "target_file": "jinja2/filters.py",
        "target_symbol": "do_attr",
        "target_lines": [1433],
        "source_closure": JINJA_CLOSURE,
        "evidence_hashes": {
            "evidence/source-vulnerable-LICENSE.txt": "3b49dcee4105eb37bac10faf1be260408fe85d252b8e9df2e0979fc1e094437b",
            "evidence/source-fixed-LICENSE.txt": "3b49dcee4105eb37bac10faf1be260408fe85d252b8e9df2e0979fc1e094437b",
            "evidence/dependency-markupsafe-LICENSE.txt": "489a8e1108509ed98a37bb983e11e0f7e1d31f0bd8f99a79c8448e7ff37d07ea",
            "evidence/GHSA-cpwx-vrp4-4pq7.json": "dd20a2e4e7fbc8812f5b4216fdc9f9d192003e5ef0ee9148f9a5d525084b6438",
            "evidence/advisory-LICENSE.md": "9e5f1b3c610b9c2da5c313bf81d577a7d1acec686bdb0384edefa6df0f90cd94",
        },
    },
    "cs-1006": {
        "runtime": "node-test-node22",
        "repository": "https://github.com/ljharb/shell-quote",
        "vulnerable_commit": "c7de931fa4ed0975ea9756983c88334fe4b8cde5",
        "fixed_commit": "6a8a899c62a58a30fb128a7079f02826ed4faee0",
        "upstream_trees": [
            "06a5f67ca77853509c7f992c522a654f08c04fdc40c90e2de22f7c02ac0add8b",
            "1c54de15ee45ad42727b491be8af6ba8718a1ef5b2bf0e5ed567c0accb8f5b1d",
        ],
        "vendored_trees": [
            "86f80d065eb0ec5121b7e43316e8ab8dab3cfcc8c2d09c098fc12cf7529c764c",
            "5bc13333abcbd77fa0eb6bffa22cec656cbe92d861a4bf83433ade7af852a1d1",
        ],
        "target_file": "index.js",
        "target_symbol": "exports.quote",
        "target_lines": [13],
        "source_closure": ["index.js"],
        "evidence_hashes": {
            "evidence/source-vulnerable-LICENSE": "8bb16db1b047019e4395965f2cf3611b06c34bf86dc2d0210b3c3f91b53c21fe",
            "evidence/source-fixed-LICENSE": "8bb16db1b047019e4395965f2cf3611b06c34bf86dc2d0210b3c3f91b53c21fe",
            "evidence/GHSA-g4rg-993r-mgx7.json": "3e751a17ce5b9dcab128226a200fdbe37f4db3169b5675c47ae8ebf83a2dc505",
            "evidence/advisory-LICENSE.md": "9e5f1b3c610b9c2da5c313bf81d577a7d1acec686bdb0384edefa6df0f90cd94",
        },
    },
    "cs-1007": {
        "runtime": "javac-java21",
        "repository": "https://github.com/bcgit/bc-java",
        "vulnerable_commit": "df521933f6e615306d552ed72f2d568f9728fc23",
        "fixed_commit": "97578f9b7ed277e6ecb58834e85e3d18385a4219",
        "upstream_trees": [
            "82c46eceab429d4a529293a434d690ac1d0d2ac79d1ce97fe039bce6d936cc7a",
            "7b36ad62d1c0fb11dba1cec85a8b39c04fc0062c5534c40002940c80996bc677",
        ],
        "vendored_trees": [
            "9ae711cc48cb0aee1c8ab712ff915a9c9a5f43b14ad5b53fa24a892097c4bad9",
            "4aeb161ea81295f8fa917964f2842089721d6a8399404c8a8f32e7f6c2a6d15b",
        ],
        "target_file": "crypto/generators/OpenBSDBCrypt.java",
        "target_symbol": "OpenBSDBCrypt.doCheckPassword",
        "target_lines": [312],
        "source_closure": BC_CLOSURE,
        "evidence_hashes": {
            "evidence/source-vulnerable-LICENSE.html": "07feba85e9808094dbe52877f28e399c08f7991ec2ce662d20fef666aabb6e66",
            "evidence/source-fixed-LICENSE.html": "07feba85e9808094dbe52877f28e399c08f7991ec2ce662d20fef666aabb6e66",
            "evidence/GHSA-73xv-w5gp-frxh.json": "0f69f64740ba84fea9c0ec62e19525877821bf5d9c77d4bb8992ed5a7790fa26",
            "evidence/advisory-LICENSE.md": "9e5f1b3c610b9c2da5c313bf81d577a7d1acec686bdb0384edefa6df0f90cd94",
        },
    },
    "cs-1008": {
        "runtime": "perl-tap-540",
        "repository": "https://github.com/richardc/perl-file-find-rule",
        "vulnerable_commit": "835cb561643e1eed51aa27a4dce9e17937325273",
        "fixed_commit": "df58128bcee4c1da78c34d7f3fe1357e575ad56f",
        "upstream_trees": [
            "88a88a08b9e97124344f0c958d2f5c91b0a75ae6db4278f0fb7c4a1f4352b854",
            "c3abb9692e7a7157b649f044fd6ca57e456f636eff145066bc9c8200ecce1302",
        ],
        "vendored_trees": [
            "4fcf71d5c7bb5d7d27575a6b0d3ae28b71bb91fb050335388489193a068aa81b",
            "9ecbc8d5692966eaf4e66d76afca3210f4ba75ea64b6906101084cf4b72569e6",
        ],
        "target_file": "File/Find/Rule.pm",
        "target_symbol": "File::Find::Rule::grep",
        "target_lines": [423],
        "source_closure": ["File/Find/Rule.pm", "Number/Compare.pm", "Text/Glob.pm"],
        "evidence_hashes": {
            "evidence/source-vulnerable-Rule.pm": "2e0abbacc15c6f15199477caf48afaee0a243af164b26ff9d07598859e4b9f5c",
            "evidence/source-fixed-Rule.pm": "d47958ec4174c1c2245085816c201a4ac1a2515a4f5cb70d61f057c74bae8014",
            "evidence/dependency-Number-Compare.pm": "624e30890c19bd56089bd8318235ca995bfab7d31bcf2a371e4ae3e6bd79c008",
            "evidence/dependency-Text-Glob.pm": "39edabab69b3a5438b39682149581dbc36c98932821eb160e9dc13760aed4c12",
            "evidence/CPANSA-File-Find-Rule.yml": "99710b425d40c2f62d78a545374a01cb5eb92b229122e373c4dae72363ecad31",
            "evidence/advisory-LICENSE": "4cabb00406b10ab960d3ebb5c14e5042cf54d2b970cc4047588aa28c703525fe",
        },
    },
}


@pytest.mark.parametrize("case_id", CASES)
def test_batch_b_assets_load_with_exact_closures_and_boolean_contract(case_id):
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
    assert [case.revision.tree_sha256, case.fixed_revision.tree_sha256] == expected["vendored_trees"]
    assert submission.hypothesis.target_file == expected["target_file"]
    assert submission.hypothesis.target_symbol == expected["target_symbol"]
    assert list(submission.hypothesis.target_lines) == expected["target_lines"]
    assert provenance["repository"] == expected["repository"]
    assert "fixed_lines" not in provenance["target"]
    assert provenance["source_closure"] == expected["source_closure"]
    assert [provenance["upstream_source_pair"][name]["tree_sha256"]
            for name in ("vulnerable", "fixed")] == expected["upstream_trees"]
    assert [provenance["vendored_source_pair"][name]["tree_sha256"]
            for name in ("vulnerable", "fixed")] == expected["vendored_trees"]
    for revision in ("vulnerable", "fixed"):
        actual_closure = sorted(
            path.relative_to(case_dir / revision).as_posix()
            for path in (case_dir / revision).rglob("*") if path.is_file()
        )
        assert actual_closure == expected["source_closure"]
    assert selected is not None and selected.id == expected["runtime"]
    assert framework(selected.framework).guard(submission.probe).passed

    for relative, digest in expected["evidence_hashes"].items():
        assert hashlib.sha256((case_dir / relative).read_bytes()).hexdigest() == digest
    for evidence in provenance["evidence"]:
        assert evidence["revision"] in evidence["source_url"]
        assert hashlib.sha256((case_dir / evidence["path"]).read_bytes()).hexdigest() == evidence["sha256"]

    dependency_lock = provenance["dependency_lock"]
    if lock_path := dependency_lock.get("path"):
        lock = (case_dir / lock_path).read_text()
        assert lock.strip()
        for package in dependency_lock["packages"]:
            digest = package.get("wheel_sha256") or package["archive_sha256"]
            assert digest in lock
    if case_id == "cs-1005":
        assert dependency_lock["packages"][0]["wheel_sha256"] in submission.build_script
    elif case_id == "cs-1007":
        assert dependency_lock["compiled_sources"] == expected["source_closure"]
        assert all(f"/work/{path}" in submission.build_script for path in expected["source_closure"])
    elif case_id == "cs-1008":
        for package in dependency_lock["packages"]:
            relative = package["name"].replace("::", "/") + ".pm"
            assert hashlib.sha256((case_dir / "vulnerable" / relative).read_bytes()).hexdigest() == \
                package["module_sha256"]


@pytest.mark.parametrize("case_id", CASES)
def test_batch_b_truth_stays_evaluator_only_and_qualification_stays_pending(case_id):
    case_dir = ROOT / "cases" / case_id
    case = load_case(case_dir)
    oracle = json.loads((case_dir / "oracle.json").read_text())
    provenance = json.loads((case_dir / "asset-manifest.json").read_text())

    assert oracle["expected_label"] == "LIKELY_EXPLOITABLE"
    assert oracle["expected_fix"] == "verified"
    assert oracle["qualification_status"] == "candidate"
    assert provenance["qualification_status"] == "candidate"
    assert provenance["qualification_blockers"]
    assert "expected_label" not in case.model_dump_json()
