"""Cheap structural guards; these do not certify Claude/Codex behavior."""
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ("corsair-development", "corsair-review", "corsair-handoff", "corsair-base-image", "corsair-agent-scaffold")


@pytest.mark.parametrize("name", SKILLS)
def test_clients_discover_one_current_skill_source(name):
    canonical = ROOT / ".claude" / "skills" / name
    codex = ROOT / ".agents" / "skills" / name
    assert codex.is_symlink() and codex.resolve() == canonical.resolve()
    text = (canonical / "SKILL.md").read_text()
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    assert metadata["name"] == name and metadata["description"]
    assert "SPEC-0082" in body and len(body.split()) < 800
    if name == "corsair-handoff":
        assert "`docs/development/CURRENT.md`" in body and "`CURRENT.md`" not in body
    if name == "corsair-agent-scaffold":
        assert "`v2_suite()`" in body and "register the scorer in" not in body
    for retired in ("SPEC-0080", "SPEC-0081", "PLAN-0095", "PLAN-0096", "corsair.agents.spec",
                    "environment, identification, planning", "tests/qualification/prepare_toolchains.py"):
        assert retired not in body


def test_config_golden_path_runs_only_configuration_suite():
    result = subprocess.run(["make", "-n", "test-config"], cwd=ROOT, text=True, capture_output=True, check=True)
    assert "uv run --locked python -m pytest" in result.stdout
    assert "tests/configuration" in result.stdout and "-n auto" not in result.stdout


def test_base_image_skill_preserves_pins_layout_and_progressive_evidence():
    text = (ROOT / ".claude/skills/corsair-base-image/SKILL.md").read_text()
    for rule in ("one image per exact runtime version", "same digest string", "Dockerfile and its matrix row",
                 "hash-pinned", "available offline", "USER 10001", "HOME=/tmp", "/opt/corsair-fixture",
                 "Never add a package to an image for one case", "plain-Docker image build", "the gate body",
                 "one real case at both commits", "evidence: image-only", "evidence: live", "milestone gate"):
        assert rule in text
    runbook = "docs/runbooks/openshell-v2.md"
    assert runbook in text and (ROOT / runbook).is_file()
