"""Private local data must stay out of commits without hiding public project inputs."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SKILL_NAMES = ("corsair-development", "corsair-evaluations")


def _ignored(paths: list[str]) -> set[str]:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    return set(result.stdout.splitlines())


def test_private_generated_paths_are_ignored():
    paths = [
        ".venv/bin/python",
        ".runs/blobs/private-artifact",
        ".state/settings.json",
        ".state/temporal/development.db",
        ".work/investigation/private-trace.jsonl",
        ".cache/uv/private-build",
        ".manus/mcp-results/private-result.json",
        "outputs/package.zip",
        "build/generated.py",
        "dist/corsair.whl",
        "local.env.key",
        "local.pem",
        "local.p12",
        "local.pfx",
        ".env",
        ".env.local",
        "development.db-wal",
        "development.sqlite3-shm",
        "worker.log",
        ".DS_Store",
        ".coverage.local",
    ]
    assert _ignored(paths) == set(paths)


def test_public_project_inputs_are_not_hidden():
    paths = [
        ".env.example",
        "src/corsair/settings.py",
        "deploy/settings.example.json",
        "evals/datasets/dev.json",
        "evals/datasets/reviews/gym-tier1/sib-python-sentinel-expr-chain.json",
        "evals/fixtures/case01/request.json",
        "docs/operations/disaster-recovery.md",
        ".github/workflows/ci.yml",
        "scripts/check_docs.py",
    ]
    assert not _ignored(paths)


def test_canonical_public_skills_and_claude_links_remain_public():
    public_paths: list[str] = []
    for skill_name in PUBLIC_SKILL_NAMES:
        canonical = ROOT / ".agents/skills" / skill_name
        claude_link = ROOT / ".claude/skills" / skill_name

        assert (canonical / "SKILL.md").is_file()
        assert claude_link.is_symlink()
        assert os.readlink(claude_link) == f"../../.agents/skills/{skill_name}"
        assert claude_link.resolve() == canonical.resolve()
        public_paths.append(f".agents/skills/{skill_name}/SKILL.md")

    assert not _ignored(public_paths)


def test_private_skill_tool_configuration_is_ignored():
    private_paths = [
        ".agents/private-tool-config.json",
        ".claude/private-tool-config.json",
        ".codex/private-tool-config.json",
    ]

    assert _ignored(private_paths) == set(private_paths)
