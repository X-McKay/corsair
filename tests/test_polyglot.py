"""Deterministic checks for generated polyglot fixtures; no model and no Docker required."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.polyglot import FAMILIES, LANGUAGES, generate
from corsair.case import load_case, tree_sha256
from corsair.kernel import Submission, ast_guard, target_binding
from tools import benchmark


VARIANTS_PER_FAMILY = 5


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    generate(tmp_path / "polyglot")
    return tmp_path / "polyglot"


def _paths(root: Path) -> list[Path]:
    return sorted(path.parent for path in root.glob("*/*/input.json"))


def test_generation_has_stable_unique_twin_revision_variants(fixture_root: Path):
    paths = _paths(fixture_root)
    assert len(paths) == len(LANGUAGES) * len(FAMILIES) * VARIANTS_PER_FAMILY == 385
    assert len({str(path.relative_to(fixture_root)) for path in paths}) == len(paths)
    assert Counter(path.parent.name for path in paths) == {language: len(FAMILIES) * VARIANTS_PER_FAMILY for language in LANGUAGES}
    catalog = json.loads((fixture_root / "catalog.json").read_text())
    assert all(len(family.exploits) == VARIANTS_PER_FAMILY for family in FAMILIES)
    assert catalog["case_directories"] == 385
    assert catalog["runnable_revision_variants"] == 770
    assert catalog["per_language_runnable_revision_variants"] == 110
    assert "distinct CVEs" in catalog["note"]


def test_each_case_has_provenance_oracle_separation_and_an_independent_raw_string_probe(fixture_root: Path):
    for path in _paths(fixture_root):
        case = load_case(path)
        provenance = json.loads((path / "provenance.json").read_text())
        oracle = json.loads((path / "oracle.json").read_text())
        submission = Submission.model_validate_json((path / "reference-submission.json").read_text())
        raw_input = (path / "input.json").read_text()
        assert case.case_id == provenance["case_id"]
        assert provenance["runnable_revision_variants"] == 2
        assert provenance["target_file"] == case.finding.file_path == submission.hypothesis.target_file
        assert provenance["target_line"] in submission.hypothesis.target_lines
        assert oracle["expected_label"] == "LIKELY_EXPLOITABLE"
        assert "LIKELY_EXPLOITABLE" not in raw_input
        assert "expected_label" not in submission.model_dump_json()
        assert target_binding(case, submission.hypothesis).passed
        assert ast_guard(submission.probe).passed
        assert "class Request" not in submission.probe
        assert "forbidden" not in submission.probe
        assert 'assert decision != "ALLOW" or safe_predicate(payload)' in submission.probe
        assert "def safe_predicate(value: str) -> bool:" in submission.probe
        if provenance["language"] == "python":
            # Importing the actual policy directly lets coverage trace the target source.
            assert "from vulnapp.policy import allowed" in submission.probe
            assert "subprocess.run" not in submission.probe
        else:
            assert "subprocess.run([*COMMAND, payload]" in submission.probe
            assert "if completed.returncode != 0:" in submission.probe
            assert "if decision not in" in submission.probe
        target = Path(case.revision.source) / submission.hypothesis.target_file
        assert f"TARGET: {provenance['family']}" in target.read_text()
        assert tree_sha256(Path(case.revision.source)) == case.revision.tree_sha256
        assert tree_sha256(Path(case.fixed_revision.source)) == case.fixed_revision.tree_sha256


def test_regeneration_is_deterministic_and_preserves_source_provenance(tmp_path: Path):
    root = tmp_path / "regenerated"
    first = generate(root, ["python", "java", "cpp"])
    before = {str(path.relative_to(root)): (tree_sha256(path / "vulnerable"), tree_sha256(path / "fixed"),
                                           (path / "reference-submission.json").read_text()) for path in first}
    second = generate(root, ["python", "java", "cpp"])
    after = {str(path.relative_to(root)): (tree_sha256(path / "vulnerable"), tree_sha256(path / "fixed"),
                                          (path / "reference-submission.json").read_text()) for path in second}
    assert before == after


def test_source_layouts_declare_and_invoke_the_requested_real_build_frameworks(fixture_root: Path):
    examples = {language: next(path for path in _paths(fixture_root) if path.parent.name == language) for language in LANGUAGES}
    assert (examples["python"] / "vulnerable" / "pyproject.toml").is_file()
    python_build = json.loads((examples["python"] / "reference-submission.json").read_text())["build_script"]
    assert "import setuptools" in python_build
    assert "pip install --no-build-isolation --no-deps ." in python_build
    assert (examples["javascript"] / "vulnerable" / "package.json").is_file()
    assert "npm run build" in json.loads((examples["javascript"] / "reference-submission.json").read_text())["build_script"]
    assert (examples["typescript"] / "vulnerable" / "vite.config.ts").is_file()
    typescript_package = json.loads((examples["typescript"] / "vulnerable" / "package.json").read_text())
    assert "npm run build" in json.loads((examples["typescript"] / "reference-submission.json").read_text())["build_script"]
    assert "vite build" in typescript_package["scripts"]["build"]
    assert typescript_package["devDependencies"] == {"@types/node": "22.10.7", "typescript": "5.7.3", "vite": "6.0.11"}
    ts_source = examples["typescript"] / "vulnerable"
    tsconfig = json.loads((ts_source / "tsconfig.json").read_text())["compilerOptions"]
    assert tsconfig["target"] == "ES2022" and tsconfig["sourceMap"] is True and tsconfig["types"] == ["node"]
    assert 'import { allowed } from "./policy.js";' in (ts_source / "src/main.ts").read_text()
    java_builds = {json.loads((path / "provenance.json").read_text())["build_command"] for path in _paths(fixture_root) if path.parent.name == "java"}
    assert any(command.startswith("mvn ") for command in java_builds)
    assert any(command.startswith("gradle ") for command in java_builds)
    gradle_case = next(path for path in _paths(fixture_root) if path.parent.name == "java" and (path / "vulnerable/build.gradle").exists())
    gradle_build = (gradle_case / "vulnerable/build.gradle").read_text()
    assert "sourceCompatibility = JavaVersion.VERSION_17" in gradle_build
    assert "targetCompatibility = JavaVersion.VERSION_17" in gradle_build
    assert "toolchain" not in gradle_build
    assert (examples["ruby"] / "vulnerable" / "Gemfile").is_file() and (examples["ruby"] / "vulnerable" / "Rakefile").is_file()
    assert "bundle exec rake build" in json.loads((examples["ruby"] / "reference-submission.json").read_text())["build_script"]
    assert (examples["perl"] / "vulnerable" / "Makefile.PL").is_file()
    assert "prove -l" in json.loads((examples["perl"] / "reference-submission.json").read_text())["build_script"]
    perl_case = next(path for path in _paths(fixture_root) if path.parent.name == "perl" and "path-sibling-prefix" in path.name)
    assert 'allowed("public/readme.txt")' in (perl_case / "vulnerable/t/policy.t").read_text()
    ruby_case = next(path for path in _paths(fixture_root) if path.parent.name == "ruby" and "header-crlf" in path.name)
    ruby_source = (ruby_case / "vulnerable/lib/vulnapp.rb").read_text()
    assert r'include?("\r")' in ruby_source and r'include?("\n")' in ruby_source
    assert "\r\n" not in ruby_source
    cpp_builds = {json.loads((path / "provenance.json").read_text())["build_command"] for path in _paths(fixture_root) if path.parent.name == "cpp"}
    assert any(command.startswith("cmake ") for command in cpp_builds)
    assert any(command.startswith("make ") for command in cpp_builds)
    cmake_case = next(path for path in _paths(fixture_root) if path.parent.name == "cpp" and (path / "vulnerable/CMakeLists.txt").exists())
    assert "--coverage -O0 -g" in (cmake_case / "vulnerable/CMakeLists.txt").read_text()
    make_case = next(path for path in _paths(fixture_root) if path.parent.name == "cpp" and (path / "vulnerable/Makefile").exists())
    assert "CXXFLAGS = -std=c++17 --coverage -O0 -g" in (make_case / "vulnerable/Makefile").read_text()


def test_generated_python_sources_parse_and_trusted_native_policy_smoke_all_variants(fixture_root: Path):
    """Local subprocesses are trusted-fixture smoke only, never sandbox/isolation evidence."""
    for path in (candidate for candidate in _paths(fixture_root) if candidate.parent.name == "python"):
        provenance = json.loads((path / "provenance.json").read_text())
        for revision, expected in (("vulnerable", ("ALLOW", "ALLOW")), ("fixed", ("ALLOW", "DENY"))):
            source = path / revision
            for module in (source / "vulnapp").glob("*.py"):
                ast.parse(module.read_text(), filename=str(module))
            for payload, want in zip((provenance["control"], provenance["exploit"]), expected, strict=True):
                result = subprocess.run([sys.executable, "-m", "vulnapp", payload], cwd=source, text=True,
                                        capture_output=True, timeout=20, check=False)
                assert result.returncode == 0, result.stderr
                assert result.stdout.strip() == want


def test_cli_generate_only_writes_a_non_passing_json_report(tmp_path: Path):
    root, output = tmp_path / "out", tmp_path / "report.json"
    assert benchmark.main(["--root", str(root), "--language", "python", "--generate-only", "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["generated"] is True
    assert report["execution"] == "not requested"
    assert report["model_accuracy_claim"] == "none"
    assert "results" not in report


def test_cli_native_smoke_is_explicitly_labeled_not_isolation(tmp_path: Path):
    root, output = tmp_path / "native", tmp_path / "native.json"
    status = benchmark.main(["--root", str(root), "--language", "python", "--limit", "1", "--native-smoke", "--output", str(output)])
    report = json.loads(output.read_text())
    assert report["execution"].startswith("native-not-isolated")
    assert report["results"][0]["mode"] == "native-not-isolated"
    assert status == 0 and report["results"][0]["status"] == "passed"
