"""Behavior checks for the maintained local documentation checker."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_docs.py"
PUBLIC_SKILL_NAMES = ("corsair-development", "corsair-evaluations")


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Execute the independent documentation checker against a temporary repository."""

    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        check=False,
    )


def test_docs_checker_accepts_existing_local_link_and_heading_anchor(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# Project\n\n[Guide](docs/guide.md#use-it)\n")
    (tmp_path / "docs/guide.md").write_text("# Guide\n\n## Use it\n")

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_docs_checker_reports_missing_local_target(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Project\n\n[Missing](docs/missing.md)\n")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "README.md: docs/missing.md: missing target" in result.stderr


def test_docs_checker_reports_missing_heading_anchor(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Project\n\n[Guide](guide.md#not-here)\n")
    (tmp_path / "guide.md").write_text("# Guide\n")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "README.md: guide.md#not-here: missing anchor" in result.stderr


def test_docs_checker_validates_allowlisted_public_skill_markdown(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text("# Guide\n\n## Boundaries\n")
    skill = tmp_path / ".agents/skills/corsair-development/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Skill\n\n[Guide](../../../docs/guide.md#boundaries)\n")

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr


def test_docs_checker_ignores_private_tool_configuration_markdown(tmp_path: Path):
    skill = tmp_path / ".agents/skills/corsair-development/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Public skill\n")
    private_config = skill.parent / "private-tool-config.md"
    private_config.write_text("# Private\n\n[Missing](does-not-exist.md)\n")

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr


def test_docs_checker_skips_imported_package_trees_beside_their_provenance(tmp_path: Path):
    """An imported corpus case (``provenance.json`` beside its ``source``/``fixed`` trees)
    holds upstream package bytes frozen by digest; its Markdown is not maintained docs."""
    case = tmp_path / "evals/datasets/corpus/secbenchjs/sbj-javascript-demo"
    (case / "source").mkdir(parents=True)
    (case / "provenance.json").write_text("{}\n")
    (case / "source/README.md").write_text("[Upstream](../../issues/new)\n")
    (tmp_path / "evals/datasets/corpus/SOURCE.md").write_text("[Missing](absent.md)\n")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "SOURCE.md: absent.md" in result.stderr + result.stdout
    assert "issues/new" not in result.stderr + result.stdout


def test_public_skills_have_unique_matching_frontmatter_and_checked_links():
    names: list[str] = []
    for skill_name in PUBLIC_SKILL_NAMES:
        skill = ROOT / ".agents/skills" / skill_name / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        match = re.match(r"^---\nname: (?P<name>[^\n]+)\n", content)

        assert match is not None
        assert match.group("name") == skill_name
        assert "description: " in content.split("---", maxsplit=2)[1]
        names.append(match.group("name"))

    result = run_checker(ROOT)

    assert len(names) == len(set(names))
    assert result.returncode == 0, result.stderr


def test_coding_agent_workflow_guide_links_the_canonical_skills():
    guide = ROOT / "docs/development/coding-agent-workflows.md"
    content = guide.read_text(encoding="utf-8")

    assert guide.is_file()
    for skill_name in PUBLIC_SKILL_NAMES:
        assert f"../../.agents/skills/{skill_name}/SKILL.md" in content
    for destination in (
        "../../AGENTS.md",
        "conventions.md",
        "testing.md",
        "../guides/extensions.md",
    ):
        assert destination in content


def test_docs_checker_accepts_links_into_the_dataset_review_records(tmp_path: Path):
    records = tmp_path / "evals/datasets/reviews/gym-tier1"
    records.mkdir(parents=True)
    (records / "wave-chain.json").write_text("{}\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text(
        "# Guide\n\n[Records](../evals/datasets/reviews/)\n"
        "[One](../evals/datasets/reviews/gym-tier1/wave-chain.json)\n"
    )

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (ROOT / "evals/datasets/reviews").is_dir()
