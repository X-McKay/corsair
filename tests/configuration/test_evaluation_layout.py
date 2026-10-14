"""PLAN-0098 eval layout guards: every set matches its frozen manifest, no case directory is outside a set, and a
held-out set's case ids are never cited in development records (SPEC-0023)."""
from pathlib import Path

import pytest

from evals.cases import EVALS, LANGUAGES, case_directories, load_set, manifest, set_names
from evals.inventory import SUITES

ROOT = Path(__file__).resolve().parents[2]
PER_CASE_SUITES = sorted({*SUITES.values(), "e2e"})
SETS = [(suite, name) for suite in PER_CASE_SUITES for name in set_names(suite)]


def test_every_agent_suite_has_per_case_sets():
    assert all(set_names(suite) for suite in SUITES.values())


@pytest.mark.parametrize(("suite", "name"), SETS)
def test_set_matches_its_frozen_manifest(suite, name):
    cases = load_set(suite, name)
    assert cases and len({case.key for case in cases}) == len(cases)


@pytest.mark.parametrize(("suite", "name"), SETS)
def test_every_case_directory_is_listed_in_its_set(suite, name):
    listed = set(manifest(suite, name)["cases"])
    found = {f"{path.parent.parent.name}/{path.name}" for path in case_directories(suite, name)}
    assert found == listed


def test_language_directories_hold_only_sets():
    for suite in PER_CASE_SUITES:
        names = set(set_names(suite))
        for language in LANGUAGES:
            directory = EVALS / suite / language
            if directory.is_dir():
                assert {path.name for path in directory.iterdir()} <= names, directory


def test_development_records_never_cite_a_held_out_case():
    held_out = [key.split("/", 1)[1] for suite, name in SETS if manifest(suite, name)["held_out"]
                for key in manifest(suite, name)["cases"]]
    assert held_out
    cited = [(str(path), case) for path in (ROOT / "docs/development").rglob("*") if path.is_file()
             for case in held_out if case in path.read_text(errors="replace")]
    assert not cited
