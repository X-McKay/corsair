"""Exact integrity and contract checks for pending real-world Batch C cases."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from corsair import matrix
from corsair.case import load_case, tree_sha256
from corsair.corpus import _patch_sha256, _region_sha256
from corsair.frameworks import framework
from corsair.kernel import Submission

ROOT = Path(__file__).resolve().parents[1]

REQUESTS_CLOSURE = [
    "requests/__init__.py", "requests/__version__.py", "requests/_internal_utils.py",
    "requests/adapters.py", "requests/api.py", "requests/auth.py", "requests/certs.py",
    "requests/compat.py", "requests/cookies.py", "requests/exceptions.py", "requests/hooks.py",
    "requests/models.py", "requests/packages.py", "requests/sessions.py",
    "requests/status_codes.py", "requests/structures.py", "requests/utils.py",
]
REQUESTS_COMMON_HASHES = {
    "requests/__init__.py": "2ef98a863233f261da297b610b632fe72919d5df76be8c9fde826977e56e0228",
    "requests/__version__.py": "22fab4a5a2e89e808a71084c3b2cf7825a83fb836de4b7080bb8def665e4fa5f",
    "requests/_internal_utils.py": "9cc4329abe21b37d93a95a3901b0ab99c24486f3d487bc57965bb2ab0b252e24",
    "requests/adapters.py": "bff1668d4e4a67bea4f98b6d4a1658079469ac8ce184bf18df3816f69e1e050f",
    "requests/api.py": "abad71717ab8b668889abbdc4952d36c5c82883d85f8bffe8562866f3e32f2f8",
    "requests/auth.py": "87e1cb955c7d8fcaca57985f480c9c3f60293928254f3efb474b73eea09b6c41",
    "requests/certs.py": "67d49be35d009efea35054f2b2cd23145854eb1b2df1cb442ea7f2f04bf6de0c",
    "requests/compat.py": "cb19ed54e4841c632b9fb14daffdf61046a6d5934074f45d484d77ff2687cd39",
    "requests/cookies.py": "903de43447028fe9b16ed7f97c9b12693f3a786a046290f75f4092829ce5ec13",
    "requests/exceptions.py": "0e1bde1417255634d1c6145db95a4ef866cc60c203da09a374b7cd12a36923f5",
    "requests/hooks.py": "0a2bb2b221c0dfd57951f702057148c7cdc8ac3a6ec1f37d45c4d482fdbc7ed4",
    "requests/models.py": "f8394a8b4a2bf2014033a573bada1b5efbc15bfdb0ac9b8e17935f9dd4c875d0",
    "requests/packages.py": "0d782ff852487336484e6bf4bc40408568f85bee4218220dfe4b2f811d7b0efb",
    "requests/status_codes.py": "16f1e64f9b87fbfba29ad473e611fd5426eded557e35e8b627dba96de8fa8fc8",
    "requests/structures.py": "f886e6855cf4e92fb968f499b94b6167afba0fd5ce8d1b935c739a6d8d38d573",
    "requests/utils.py": "eacc765f7708540f018163a0f28771172fbf95b5831444d4f072387d4e119aac",
}

CASES = {
    "cs-1009": {
        "runtime": "pytest-cpython312",
        "repository": "https://github.com/psf/requests",
        "commits": ("302225334678490ec66b3614a9dddb8a02c5f4fe", "74ea7cf7a6a27a4eeb2ae24e162bcc942a6706d5"),
        "parents": ("b639e66c816514e40604d46f0088fbceec1a5149", "302225334678490ec66b3614a9dddb8a02c5f4fe"),
        "git_trees": ("e30937c0f917b4fa66d6e4b795505f2a46c89a84", "ab6e18cda9d2c7bb7479e6f17f323aa379821ada"),
        "upstream_trees": ("660206ebd2f449f2d2a74b5a0fa1cd55737e1a2a6549ed4306334d0530417abf", "405167b2ed9dc50ef5c7ac5b25ac78e3506186633a216261cfdbadb9f0ad25b2"),
        "vendored_trees": ("eece4c5e06a0bb677402ec2cc6413934c8b48b6502c70fd2816e682fe1708b70", "57988ee3d481d500abd3a3eb9cac32336bec926e231c0ac61df7a576565a94df"),
        "patches": ("de702eb710109fb7c49d33213f729443f1788af3062aec57a2e6d6b147599786", "146a165b2dd616e653534277247458c492505c9f199ff3e7424db32c185c5be5"),
        "target": ("requests/sessions.py", "SessionRedirectMixin.rebuild_proxies", (327,), (329,)),
        "closure": REQUESTS_CLOSURE,
        "hashes": {
            "vulnerable": {**REQUESTS_COMMON_HASHES, "requests/sessions.py": "294a8971144ba2f35e7d4b3b49c39749454271f49ac93156b5b889ee03929532"},
            "fixed": {**REQUESTS_COMMON_HASHES, "requests/sessions.py": "f8bbd3ceb3ed7ad493ad1ddbbb1bb85e176032b2452c1d6ae43ecffbe2f65e1c"},
        },
        "regions": ("04457d16058589362cd0a38c2191cc31f5667fa291dbb494d1c4810c0e495780", "73befcf13015c2cdea927f00c5a5936dcf9ba29ea184f56d03b6e8bb121be8c7"),
        "evidence": {
            "evidence/source-vulnerable-LICENSE": "09e8a9bcec8067104652c168685ab0931e7868f9c8284b66f5ae6edae5f1130b",
            "evidence/source-fixed-LICENSE": "09e8a9bcec8067104652c168685ab0931e7868f9c8284b66f5ae6edae5f1130b",
            "evidence/source-vulnerable-NOTICE": "f5110972dedad2b4e9d314518daf3b7d72d6e02e499acd802181de6f74571dcc",
            "evidence/source-fixed-NOTICE": "f5110972dedad2b4e9d314518daf3b7d72d6e02e499acd802181de6f74571dcc",
            "evidence/dependency-certifi-LICENSE": "e93716da6b9c0d5a4a1df60fe695b370f0695603d21f6f83f053e42cfc10caf7",
            "evidence/dependency-charset-normalizer-LICENSE": "eb31a0c5a4fb09b8a4e32055d25c1e5f9c358a2752fef3cd720213d1ccfee241",
            "evidence/dependency-idna-LICENSE.md": "a59f0b0ef3635874109a4461ca44ff7a70d50696e814767bfaf721d4c9b0db0f",
            "evidence/dependency-urllib3-LICENSE.txt": "c37bf186e27cf9dbe9619e55edfe3cea7b30091ceb3da63c7dacbe0e6d77907b",
            "evidence/vulnerable-source-manifest.json": "2b0a54f54e71b0c0e5262f884a80ce131f9153103c27be566a8aa44267009db4",
            "evidence/fixed-source-manifest.json": "e58bd6569d83d9a599fac3e1da4014e2817666db690b7062ef828e398c6dc684",
            "evidence/dependency-member-manifest.json": "ec6227468142417f35ab222ab0caaf01d925d151932d33a5cf11d4a83d826508",
        },
        "replay": "python_replay_pending",
    },
    "cs-1010": {
        "runtime": "node-test-node22",
        "repository": "https://github.com/kriszyp/json-schema",
        "commits": ("3b0cec3042a5aac5c967fd43475f5edc4c5b6eff", "f6f6a3b02d667aa4ba2d5d50cc19208c4462abfa"),
        "parents": ("c28470f2d64bace29c73d140f9c6876e3c3a9fef", "ef60987a9a14b9d9c739384460044ba53cd9b9a2"),
        "git_trees": ("46755491ead6b7a9a78166ddc52ee994c63caf66", "39e437a3d8764e11563101165d6b9c64d90fad6c"),
        "upstream_trees": ("f133092168fe6e543f475f65ecac8495d8867cf2adde3bd7ebd51c2fe2f2ca12", "697650b39f1dfaa020e6cb04d9da8f782a5a3f6d1b6bccbdf2c0eb0287bcd109"),
        "vendored_trees": ("e24d55213be65a43368744bc8a875bda50d7a62d4b677b6217fb7eeb0709cd81", "1e7cf193e858f440d786f8019ebf2b2353673feefd8bc82498e5c3906c29e579"),
        "patches": ("a11f35df3c7930f6b9fd1392c90e8c97e5953ccf5abdd4e350db6782440ff019", "ecc934c0bdbbec47f6600c44e653448295356234c27607cdc836a67f6a9b4552"),
        "target": ("lib/validate.js", "checkObj", (211,), (211,)),
        "closure": ["lib/validate.js", "package.json"],
        "hashes": {
            "vulnerable": {"lib/validate.js": "3d2751d8eec3eb9de4630d461906f0851140a89cdcb737a9f78ce95dc6f4e05d", "package.json": "d189a5d099c2aacba3cb41186128870359d11519ac88e421cb31ee50540e8eb5"},
            "fixed": {"lib/validate.js": "b69694434212cdd4ffce4302d4f615da17a87345d6af72482014dcf90298fa26", "package.json": "22004c92d1d7d17e18d287e6b73e9a6b0c3be3259c9984735d68de67f5b37e44"},
        },
        "regions": ("7b31786ae74432d5fb74d5aefcc1031120282572d711f27613870dfa93607a85", "a181ef3ec997a1136adde6c4e33d19a676c21c70e8463697fd49a887dfd9e09d"),
        "evidence": {"evidence/source-vulnerable-LICENSE": "9037c946f70e6397de29745f48caebf80c2b12c1d426d1d23581cb1c8595968e", "evidence/source-fixed-LICENSE": "9037c946f70e6397de29745f48caebf80c2b12c1d426d1d23581cb1c8595968e"},
        "replay": "node22_replay_pending",
    },
    "cs-1011": {
        "runtime": "javac-java21",
        "repository": "https://github.com/jhy/jsoup",
        "commits": ("985f1fe13aa0b1d37c6f6f17a948fc240a03dcef", "4ea768d96b3d232e63edef9594766d44597b3882"),
        "parents": (None, "985f1fe13aa0b1d37c6f6f17a948fc240a03dcef"),
        "git_trees": ("bb355a159c3a671a9123af3849539642053596d8", "c50d82b542527ca5a992ad72f2808263cbe80060"),
        "upstream_trees": ("7ed4f6dd4d68c413d4f4d35c21b0b488ece4227771876b7eddcd2cb16963ab99", "178bbd1580e5e26da6e2cddab17f2383f9294d72dab9497a539132ffcff4a00e"),
        "vendored_trees": ("1692f0ac4f3b3ada0417123339d6dbbf0e75d8f8e90947662e1f0914b48b4420", "37be9f2e4c4d90c3163ae7fa7fd449e26c514e3c3aee6675ecd05ed030e7fd8c"),
        "patches": ("5e8d19c6adb565e0bdde5e6a0c189cb00341438451eaa3d6311f6744b010333f", "64a94d02d5bbbdd1e7b44bdc9a9ac2241a2abeb6c4435ca4fb767ebcaacebf72"),
        "target": ("src/main/java/org/jsoup/internal/StringUtil.java", "StringUtil.resolve", (315,), (318,)),
        "closure": ["src/main/java/org/jsoup/helper/Validate.java", "src/main/java/org/jsoup/helper/ValidationException.java", "src/main/java/org/jsoup/internal/StringUtil.java"],
        "hashes": {
            "vulnerable": {"src/main/java/org/jsoup/helper/Validate.java": "4449c8fa547a70051068046304ad10206324f5ad33e45a010eb753393871075a", "src/main/java/org/jsoup/helper/ValidationException.java": "209e9b62845a9effe55d9e684c8ebe76d6f63be27cd66ee0a2ff24ce3585cfbd", "src/main/java/org/jsoup/internal/StringUtil.java": "070fe7009f43af282f754817e592628f991054a2617f9a1698ce3f0f1af4282f"},
            "fixed": {"src/main/java/org/jsoup/helper/Validate.java": "4449c8fa547a70051068046304ad10206324f5ad33e45a010eb753393871075a", "src/main/java/org/jsoup/helper/ValidationException.java": "209e9b62845a9effe55d9e684c8ebe76d6f63be27cd66ee0a2ff24ce3585cfbd", "src/main/java/org/jsoup/internal/StringUtil.java": "e6aec7293ce97b317cdaadf71c376b7caef3a5285c49666a93ff590612ec8910"},
        },
        "regions": ("7d8dbce4f440a2dc8e02ba8c20dc9e2679432010217b6f98153db5dddf9c6eab", "8a20de39b6a6d0d26f69a695bcfeb53fcfa1df73767d21dde576bcdf20f0cfdc"),
        "evidence": {
            "evidence/source-vulnerable-LICENSE": "2c7530cc19d93dcda58d20c77bd039aab2d2cd8bfe379d240b602c4cc31dd3a2",
            "evidence/source-fixed-LICENSE": "2c7530cc19d93dcda58d20c77bd039aab2d2cd8bfe379d240b602c4cc31dd3a2",
            "evidence/source-vulnerable-pom.xml": "c1e67f71d94afd995420ace624ac0dfff142f48190ffc0fa026316957d18f75e",
            "evidence/source-fixed-pom.xml": "c1e67f71d94afd995420ace624ac0dfff142f48190ffc0fa026316957d18f75e",
            "evidence/jsr305-3.0.2.pom": "19889dbdf1b254b2601a5ee645b8147a974644882297684c798afe5d63d78dfe",
            "evidence/jsr305-Apache-2.0.txt": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
        },
        "replay": "java21_jacoco_replay_pending",
    },
    "cs-1012": {
        "runtime": "perl-tap-540",
        "repository": "https://github.com/rschupp/Module-ScanDeps",
        "commits": ("bb448215c850cc1c009ec8c86196bd865141273d", "30d43e2df13cfca74833b3aa8a641679427c5cd8"),
        "parents": ("e8e57160aa2e3bbf06a6a284bfd9ea85a28021ca", "bb448215c850cc1c009ec8c86196bd865141273d"),
        "git_trees": ("b361173588cccbc39b77e0a9966ebc2ad376ab93", "3f37f6f3c9bb2576a2438f0bd21ae63a5f54d7a1"),
        "upstream_trees": ("dd773a224f8f8b9afaa68fa187d7176c4a27bdedfc91ddd4052a3d34ab33ff02", "20bcaede5f170ae2222a86d5b2d47fbab8426823e82b6d2e7cea321c4e0b1e62"),
        "vendored_trees": ("4be9abd26cacda0b73613ef29a4c21a6d6e5db60fe3603f80c9a575aa607bf79", "c7b78b8b30368f1d0b190f7b30bf41b1d6bc32032047036f341d9a0b8aba52c3"),
        "patches": ("c2d7953cb72bd0f444c9bd586c5eefef3c859367d5fd1d23ff433d98ab9fb6d0", "c2d7953cb72bd0f444c9bd586c5eefef3c859367d5fd1d23ff433d98ab9fb6d0"),
        "target": ("lib/Module/ScanDeps.pm", "scan_file", (871,), (871,)),
        "closure": ["lib/Module/ScanDeps.pm"],
        "hashes": {"vulnerable": {"lib/Module/ScanDeps.pm": "14e4e942bcae5cf36267ec20c332ec90b374247a968969462eec2f911e598646"}, "fixed": {"lib/Module/ScanDeps.pm": "5abc69d32a7338b6751a54b9dd55916403cd9083069bad179b006c1d610534ce"}},
        "regions": ("97b7f858d72878db784a9c2447c2a83f4f7c5df6174eefe9a5974d9a30683f77", "3d1e98784841e26c20ecbe55202f4ce30c38eb171192056d7eedbe805843826e"),
        "evidence": {
            "evidence/source-vulnerable-LICENSE": "1d2d2030e5a5664cc2aebde2bd136b0315b7a3b3b8a26ddc4cf730d073f143a8",
            "evidence/source-fixed-LICENSE": "1d2d2030e5a5664cc2aebde2bd136b0315b7a3b3b8a26ddc4cf730d073f143a8",
            "evidence/source-vulnerable-README": "9679c17475043ba7ab2f91d907a9442e1e71ffbbec70744bbe22394de4f6da59",
            "evidence/source-fixed-README": "9679c17475043ba7ab2f91d907a9442e1e71ffbbec70744bbe22394de4f6da59",
            "evidence/source-vulnerable-Makefile.PL": "3bb507954e14ad0e02cb3ffc1def83ecbf9caffbbebe76e470b575d3362c9a52",
            "evidence/source-fixed-Makefile.PL": "3bb507954e14ad0e02cb3ffc1def83ecbf9caffbbebe76e470b575d3362c9a52",
        },
        "replay": "perl_tap_replay_pending",
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("case_id", CASES)
def test_batch_c_assets_load_with_exact_sources_and_boolean_contract(case_id):
    expected = CASES[case_id]
    case_dir = ROOT / "cases" / case_id
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_bytes())
    assets = json.loads((case_dir / "asset-manifest.json").read_text())

    assert (case.revision.commit, case.fixed_revision.commit) == expected["commits"]
    assert (case.revision.tree_sha256, case.fixed_revision.tree_sha256) == expected["vendored_trees"]
    assert assets["schema"] == "corsair-lite/case-assets/1"
    assert assets["repository"] == expected["repository"]
    assert assets["source_closure"] == expected["closure"]
    assert tuple(assets["upstream_source_pair"][role]["first_parent"] for role in ("vulnerable", "fixed")) == expected["parents"]
    assert tuple(assets["upstream_source_pair"][role]["git_tree"] for role in ("vulnerable", "fixed")) == expected["git_trees"]
    assert tuple(assets["upstream_source_pair"][role]["tree_sha256"] for role in ("vulnerable", "fixed")) == expected["upstream_trees"]
    assert tuple(assets["vendored_source_pair"][role]["tree_sha256"] for role in ("vulnerable", "fixed")) == expected["vendored_trees"]
    assert (assets["upstream_source_pair"]["patch_sha256"], assets["vendored_source_pair"]["patch_sha256"]) == expected["patches"]

    target_file, target_symbol, source_lines, fixed_lines = expected["target"]
    assert (submission.hypothesis.target_file, submission.hypothesis.target_symbol,
            tuple(submission.hypothesis.target_lines)) == (target_file, target_symbol, source_lines)
    assert assets["target"]["lines"] == list(source_lines)
    assert assets["target"].get("fixed_lines", list(source_lines)) == list(fixed_lines)
    assert ("fixed_lines" in assets["target"]) is (source_lines != fixed_lines)
    assert matrix.select(case).id == expected["runtime"]
    assert framework(matrix.select(case).framework).guard(submission.probe).passed

    for role in ("vulnerable", "fixed"):
        root = case_dir / role
        actual = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        assert actual == expected["closure"]
        assert not any(path.is_symlink() for path in root.rglob("*"))
        assert tree_sha256(root) == expected["vendored_trees"][("vulnerable", "fixed").index(role)]
        for relative, sha256 in expected["hashes"][role].items():
            assert digest(root / relative) == sha256
    assert _patch_sha256(case_dir / "vulnerable", case_dir / "fixed") == expected["patches"][1]
    assert _region_sha256(case_dir / "vulnerable" / target_file, source_lines) == expected["regions"][0]
    assert _region_sha256(case_dir / "fixed" / target_file, fixed_lines) == expected["regions"][1]


@pytest.mark.parametrize("case_id", CASES)
def test_batch_c_rights_evidence_and_candidate_boundaries_are_exact(case_id):
    expected = CASES[case_id]
    case_dir = ROOT / "cases" / case_id
    assets = json.loads((case_dir / "asset-manifest.json").read_text())
    oracle = json.loads((case_dir / "oracle.json").read_text())
    case = load_case(case_dir)

    actual_evidence = sorted(path.relative_to(case_dir).as_posix() for path in (case_dir / "evidence").rglob("*") if path.is_file())
    assert actual_evidence == sorted(expected["evidence"])
    manifest_evidence = {entry["path"]: entry for entry in assets["evidence"]}
    assert set(manifest_evidence) == set(expected["evidence"])
    for relative, sha256 in expected["evidence"].items():
        assert digest(case_dir / relative) == sha256 == manifest_evidence[relative]["sha256"]
        assert manifest_evidence[relative]["source_url"]
        assert manifest_evidence[relative]["revision"]

    assert assets["qualification_status"] == oracle["qualification_status"] == "candidate"
    assert set(assets["qualification_blockers"]) == {
        "dataset_manifest_entry_pending", "runtime_rights_pending",
        expected["replay"], "independent_review_pending",
    }
    assert oracle["expected_label"] == "LIKELY_EXPLOITABLE"
    assert oracle["expected_fix"] == "verified"
    assert "expected_label" not in case.model_dump_json()
    assert assets["rights_review"]["reviewer"] == "OpenAI Codex automated factual rights preparation"
    assert assets["rights_review"]["review_kind"] == "automated_factual"
    assert assets["rights_review"]["human_legal_approval"] is False
    covered = {path for component in assets["rights_review"]["components"] for path in component["covered_paths"]}
    assert {f"{role}/{path}" for role in ("vulnerable", "fixed") for path in expected["closure"]} <= covered


def test_batch_c_dependency_locks_are_closed_and_hash_checked():
    requests_dir = ROOT / "cases/cs-1009"
    requests_lock = json.loads((requests_dir / "dependencies.lock").read_text())
    request_hashes = {
        "922820b53db7a7257ffbda3f597266d435245903d80737e34f8a45ff3e3230d8",
        "fe9f97feb71aa9896b81973a7bbada8c49501dc73e58a10fcef6663af95e5079",
        "946d195a0d259cbba61165e88e65941f16e9b36ea6ddb97f00452bae8b1287d3",
        "0ed14ccfbf1c30a9072c7ca157e4319b70d65f623e91e7b32fadb2853431016e",
    }
    assert {item["wheel_sha256"] for item in requests_lock["packages"]} == request_hashes
    requests_submission = json.loads((requests_dir / "reference-submission.json").read_text())
    assert all(digest in requests_submission["build_script"] for digest in request_hashes)

    jsoup_dir = ROOT / "cases/cs-1011"
    jsoup_lock = json.loads((jsoup_dir / "dependencies.lock").read_text())
    assert jsoup_lock["artifacts"] == [{
        "coordinate": "com.google.code.findbugs:jsr305:3.0.2",
        "jar_sha256": "766ad2a0783f2687962c8ad74ceecc38a28b9f72a2d085ee438b7813e928d0c7",
        "pom_sha256": "19889dbdf1b254b2601a5ee645b8147a974644882297684c798afe5d63d78dfe",
    }]
    assert jsoup_lock["compiled_sources"] == CASES["cs-1011"]["closure"]
    jsoup_build = json.loads((jsoup_dir / "reference-submission.json").read_text())["build_script"]
    assert jsoup_lock["artifacts"][0]["jar_sha256"] in jsoup_build
    assert all(f"/work/{path}" in jsoup_build for path in jsoup_lock["compiled_sources"])


def test_requests_build_fetches_verifies_and_installs_only_locked_wheels():
    case_dir = ROOT / "cases/cs-1009"
    packages = json.loads((case_dir / "dependencies.lock").read_text())["packages"]
    build = json.loads((case_dir / "reference-submission.json").read_text())["build_script"]
    install = build.split("python -m pip install", 1)[1]

    assert "--no-index" in install
    assert " -r " not in install
    for package in packages:
        local = f'$wheel_dir/{package["filename"]}'
        assert f'--dest "$wheel_dir" "{package["wheel_url"]}"' in build
        assert f'{package["wheel_sha256"]}  {local}' in build
        assert f'"{local}"' in install


def test_batch_c_probes_preserve_runtime_compatible_owned_state_checks():
    javascript = json.loads((ROOT / "cases/cs-1010/reference-submission.json").read_text())["probe"]
    assert "const ownedPrototype = {};" in javascript
    assert "Object.getOwnPropertyDescriptors(Object.prototype)" in javascript
    assert "Object.create(null)" not in javascript

    perl_dir = ROOT / "cases/cs-1012"
    perl_submission = json.loads((perl_dir / "reference-submission.json").read_text())
    assert perl_submission["hypothesis"]["target_symbol"] == "scan_file"
    assert "our $LAST_SCAN_ERROR;" in perl_submission["probe"]
    assert "$LAST_SCAN_ERROR = $scan_error;" in perl_submission["probe"]


def test_batch_c_json_schema_records_the_non_parent_release_interval():
    assets = json.loads((ROOT / "cases/cs-1010/asset-manifest.json").read_text())
    assert assets["upstream_source_pair"]["relationship"] == "seven-commit-release-interval"
    assert assets["upstream_source_pair"]["ancestry"] == [
        "3b0cec3042a5aac5c967fd43475f5edc4c5b6eff", "b3f42b3331608fe83b6cc267c5fc513ec1b839ed",
        "c52a27c653428149e4f9fb776d5e110d04639a9c", "22f146111f541d9737e832823699ad3528ca7741",
        "fb427cd4d175684786e4b2538718e72453e825e9", "b62f1da1ff5442f23443d6be6a92d00e65cba93a",
        "ef60987a9a14b9d9c739384460044ba53cd9b9a2", "f6f6a3b02d667aa4ba2d5d50cc19208c4462abfa",
    ]
    components = assets["rights_review"]["components"]
    assert len(components) == 1
    assert components[0]["license_expression"] == "AFL-2.1 OR BSD-3-Clause"
    assert components[0]["selected_license"] == "BSD-3-Clause"


def test_batch_c_perl_elects_gpl_v1_without_rewriting_the_offer():
    assets = json.loads((ROOT / "cases/cs-1012/asset-manifest.json").read_text())
    component = assets["rights_review"]["components"][0]
    assert component["license_expression"] == "GPL-1.0-or-later OR LicenseRef-Module-ScanDeps-Artistic-1.0"
    assert component["selected_license"] == "GPL-1.0-only"
    assert set(component["license_evidence_paths"]) == {
        "evidence/source-vulnerable-LICENSE", "evidence/source-fixed-LICENSE",
    }
