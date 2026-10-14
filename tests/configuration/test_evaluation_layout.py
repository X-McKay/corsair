"""PLAN-0098 eval layout guards: every set matches its frozen manifest, no case directory is outside a set, and a
held-out set's case ids are never cited in development records (SPEC-0023)."""
from pathlib import Path

import pytest

from evals.cases import AGENTS, LANGUAGES, case_directories, eval_root, load_set, manifest, set_names
from evals.inventory import SUITES

ROOT = Path(__file__).resolve().parents[2]
# v1 suites under evals/ and every v2 agent's own evals/ directory (a Path)
PER_CASE_SUITES = sorted({*SUITES.values(), "e2e"}, key=str)
SETS = [(suite, name) for suite in PER_CASE_SUITES for name in set_names(suite)]


def test_every_agent_suite_has_per_case_sets():
    assert all(set_names(suite) for agent, suite in SUITES.items() if agent not in AGENTS)


@pytest.mark.parametrize("agent", AGENTS)
def test_v2_cases_name_their_dimensions(agent):
    for name in set_names(SUITES[agent]):
        for case in load_set(SUITES[agent], name):
            assert case.case.get("dimensions"), (agent, case.key)


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
            directory = eval_root(suite) / language
            if directory.is_dir():
                assert {path.name for path in directory.iterdir()} <= names, directory


def test_development_records_never_cite_a_held_out_case():
    held_out = [key.split("/", 1)[1] for suite, name in SETS if manifest(suite, name)["held_out"]
                for key in manifest(suite, name)["cases"]]
    assert held_out
    cited = [(str(path), case) for path in (ROOT / "docs/development").rglob("*") if path.is_file()
             for case in held_out if case in path.read_text(errors="replace")]
    assert not cited


def test_eval_language_is_forwarded_only_to_scorers_that_accept_it():
    """`make eval ... EVAL_LANGUAGE=` forwards `--language` only where the set's scorer defines it; others refuse."""
    import importlib.util
    from evals.run import SUITES, narrows_by_language
    for agent, suite in SUITES.items():
        for set_name in suite.sets:
            module = suite.set_modules.get(set_name, suite.module)
            source = Path(importlib.util.find_spec(module).origin).read_text()
            accepts = '"--language"' in source or "'--language'" in source
            assert narrows_by_language(suite, set_name) == accepts, (agent, set_name, module)
