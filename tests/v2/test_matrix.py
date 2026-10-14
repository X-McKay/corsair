"""The v2 runtime matrix: the file loads, every row has its skill and canaries, and selection is a manifest lookup."""
import importlib.util
import shutil
import string
import subprocess
from pathlib import Path

import pytest
import yaml

from corsair.v2 import matrix
from corsair.v2.contracts import Case, Finding, Revision

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "src/corsair/v2/skills/frameworks"
PLACEHOLDERS = {"file", "name", "class", "module"}


def case_for(tree: Path) -> Case:
    return Case(case_id="c", finding=Finding(title="t"), revision=Revision(source=str(tree), tree_sha256="0" * 64))


def test_matrix_loads_with_unique_rows_and_known_placeholders():
    rows = matrix.load()
    assert len({row.id for row in rows}) == len(rows) >= 6
    for row in rows:
        for template in (row.run_template, row.syntax_check or ()):
            fields = {f for part in template for _, f, _, _ in string.Formatter().parse(part) if f is not None}
            assert fields <= PLACEHOLDERS, row.id
        assert row.runtime().syntax_check == row.syntax_check, row.id
        assert row.exit_codes.get(0) is not None, row.id
        canary = SKILLS / row.skill / "canary"
        assert (SKILLS / row.skill / "SKILL.md").is_file(), row.id
        assert len([p for p in (canary / "pass").rglob("*") if p.is_file()]) == 1, row.id
        assert len([p for p in (canary / "fail").rglob("*") if p.is_file()]) == 1, row.id


def test_duplicate_ids_and_unknown_keys_are_refused(tmp_path):
    data = yaml.safe_load(matrix.DEFAULT_MATRIX.read_text())
    data["rows"].append(data["rows"][0])
    (tmp_path / "dup.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        matrix.load(tmp_path / "dup.yaml")
    data = yaml.safe_load(matrix.DEFAULT_MATRIX.read_text())
    data["rows"][0]["selector"] = "python"
    (tmp_path / "extra.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        matrix.load(tmp_path / "extra.yaml")


@pytest.mark.parametrize(("files", "row_id"), [
    ({"requirements.txt": "flask\n"}, "pytest-cpython312"),
    ({"pyproject.toml": "[project]\n"}, "pytest-cpython312"),
    ({"pom.xml": "<artifactId>junit-jupiter</artifactId>"}, "junit5-maven-temurin17"),
    ({"pom.xml": "<artifactId>junit</artifactId>"}, "junit4-maven-temurin8"),
    # First matching row wins: a pom naming both selects the earlier JUnit 5 row.
    ({"pom.xml": "<artifactId>junit</artifactId><artifactId>junit-jupiter</artifactId>"}, "junit5-maven-temurin17"),
    ({"pom.xml": "<project/>"}, None),
    ({"package.json": '{"devDependencies": {"jest": "^29.7.0"}}'}, "jest29-node22"),
    ({"package.json": '{"scripts": {"test": "node --test"}}'}, None),
    ({"cpanfile": "requires 'DBI';"}, "prove-perl526"),
    ({"t/basic.t": "use Test::More;"}, "prove-perl526"),
    ({"Gemfile": "source 'https://rubygems.org'"}, "minitest-ruby31"),
    ({"Makefile": "all:"}, None),
    ({}, None),
])
def test_select_by_manifest(tmp_path, files, row_id):
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    runtime = matrix.select(case_for(tmp_path), include_unchecked=True)
    assert (runtime.row_id if runtime else None) == row_id


def test_unchecked_rows_are_skipped_by_default(tmp_path):
    data = yaml.safe_load(matrix.DEFAULT_MATRIX.read_text())
    for row in data["rows"]:
        row["evidence"] = "canary-only"
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data))
    (tmp_path / "tree").mkdir()
    (tmp_path / "tree/requirements.txt").write_text("")
    assert matrix.select(case_for(tmp_path / "tree"), path) is None
    assert matrix.select(case_for(tmp_path / "tree"), path, include_unchecked=True).row_id == "pytest-cpython312"


def test_missing_tree_selects_nothing(tmp_path):
    assert matrix.select(case_for(tmp_path / "absent")) is None


def test_fill_placeholders():
    template = ("run", "{file}::{name}", "-Dtest={class}#{name}", "{module}")
    assert matrix.fill(template, test_file="src/test/java/com/x/FooTest.java", test_name="probe") == (
        "run", "src/test/java/com/x/FooTest.java::probe", "-Dtest=FooTest#probe", "src.test.java.com.x.FooTest")
    with pytest.raises(KeyError):
        matrix.fill(("{other}",), test_file="a.py", test_name="t")


def _docker_image(image: str) -> bool:
    if shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        return False
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def test_pytest_canary_pair_on_its_image():
    """The cheapest row's canary pair end to end; the full set runs with tools/v2_canary.py."""
    row = next(row for row in matrix.load() if row.id == "pytest-cpython312")
    if not _docker_image(row.image):
        pytest.skip("Docker or the row's image is not available")
    spec = importlib.util.spec_from_file_location("v2_canary", ROOT / "tools/v2_canary.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    evidence = tool.check_row(row, timeout=300)
    assert {kind: c["outcome"] for kind, c in evidence["canaries"].items()} == {"pass": "passed",
                                                                                 "fail": "assertion_failed"}
    assert evidence["admitted"] and all(c["cleanup_confirmed"] for c in evidence["canaries"].values())
    assert all(c["facts"]["check_marker"] == {"pass": "holds", "fail": "violated"}[kind]
               for kind, c in evidence["canaries"].items())
    assert all(c["syntax_check"]["holds"] for c in evidence["canaries"].values())
