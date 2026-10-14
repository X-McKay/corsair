"""CI guards: every workflow pins actions by full commit SHA, reads the repository only, and keeps checkout
credentials out of the workspace; the PR check `offline-guards` (branch protection waits on that name) runs the v2
suite."""
from pathlib import Path
import re

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda path: path.name)
def test_ci_has_only_read_permissions_and_pinned_actions(path):
    config = yaml.safe_load(path.read_text())
    assert config["permissions"] == {"contents": "read"}
    for job in config["jobs"].values():
        assert "permissions" not in job
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False


def test_pr_check_runs_the_v2_suite():
    jobs = yaml.safe_load((WORKFLOWS / "development.yml").read_text())["jobs"]
    assert [step["run"] for step in jobs["offline-guards"]["steps"] if "run" in step] == ["make test-v2"]
    assert "if" not in jobs["offline-guards"]


def test_scripted_evals_cover_every_agent_with_a_suite_and_the_chain():
    from tests.v2.test_release_check import release_check
    jobs = yaml.safe_load((WORKFLOWS / "development.yml").read_text())["jobs"]
    assert sorted(jobs["scripted-evals"]["strategy"]["matrix"]["agent"]) == sorted(release_check.evaluated())


def test_release_check_runs_only_toward_main():
    jobs = yaml.safe_load((WORKFLOWS / "development.yml").read_text())["jobs"]
    assert jobs["release-check"]["if"] == "github.base_ref == 'main' || github.ref == 'refs/heads/main'"
    assert [step["run"] for step in jobs["release-check"]["steps"] if "run" in step] == ["make release-check"]


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda path: path.name)
def test_ci_never_reaches_a_model(path):
    """No provider configuration, endpoint or credential reaches a workflow: evals run scripted only."""
    text = path.read_text().lower()
    assert not [word for word in ("provider-config", "provider_config", "llm.", "secrets.", "api_key") if word in text]


def test_every_runtime_row_gets_a_job_from_its_toolchain_source():
    from tools.ci_rows import rows
    from corsair.v2 import matrix
    assert [row["id"] for row in rows()] == [row.id for row in matrix.load()]
