"""Private local data must stay out of commits without hiding public project inputs."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
        "evals/fixtures/case01/request.json",
        "docs/operations/disaster-recovery.md",
        ".github/workflows/ci.yml",
        "scripts/check_docs.py",
    ]
    assert not _ignored(paths)
