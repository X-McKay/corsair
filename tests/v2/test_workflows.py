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
    assert list(jobs) == ["offline-guards"]
    assert [step["run"] for step in jobs["offline-guards"]["steps"] if "run" in step] == ["make test-v2"]
