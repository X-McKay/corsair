"""Corpus cases as issue requests (kick-off note, 2026-10-13): each variant committed into a local bare repository,
an issue JSON the investigation entry point reads, and an evaluator-only `expected.json` beside it.

The two variants are separate root commits with fixed, neutral metadata, so commit ids are reproducible and neither
history nor ref names say which variant is which. The issue JSON carries only what a reporter would: the finding's
title and neutral text, the repository, the revision and the other revision as `fixed_revision`. Verdicts, oracles,
variant names and the upstream verification tests stay in `expected.json`, which the system never reads.

    python -m evals.corpus.issues --root <operator-allowlisted dir> (--set corpus-python | --case <id> ...)
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from evals.corpus.cases import CORPUS, REPOSITORY, CorpusCase, case_digest, issue_text, load, snapshot

SCHEMA = "corsair-issue-request/v1"
COHORTS = Path(__file__).with_name("cohorts.json")
# Committed issue files for the cohorts (`--root evals/corpus/issues`), so a checkout carries the case data.
ISSUES = Path(__file__).with_name("issues")
_IDENTITY = {"GIT_AUTHOR_NAME": "Corsair corpus", "GIT_AUTHOR_EMAIL": "corpus@corsair.invalid",
             "GIT_COMMITTER_NAME": "Corsair corpus", "GIT_COMMITTER_EMAIL": "corpus@corsair.invalid",
             "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000"}


def _git(repository: Path, *args: str, env: dict | None = None, data: bytes | None = None) -> str:
    environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(repository), "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": os.devnull, **(env or {})}
    return subprocess.run(["git", "--git-dir", str(repository), *args], input=data, env=environment,
                          capture_output=True, check=True).stdout.decode().strip()


def commit(repository: Path, tree: dict[str, bytes]) -> str:
    """One root commit of exactly `tree` (path -> bytes, regular files), with fixed metadata."""
    with tempfile.TemporaryDirectory() as scratch:
        index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        for path, data in sorted(tree.items()):
            blob = _git(repository, "hash-object", "-w", "--stdin", data=data)
            _git(repository, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=index)
        tree_id = _git(repository, "write-tree", env=index)
    sha = _git(repository, "commit-tree", tree_id, "-m", "corpus capture", env=_IDENTITY)
    _git(repository, "update-ref", f"refs/corsair/{sha}", sha)
    return sha


def _location(repository: Path) -> str:
    """Inside this checkout, the repository's checkout-relative path (the same on every clone); elsewhere a file URI."""
    path = repository.absolute()
    return path.relative_to(REPOSITORY).as_posix() if path.is_relative_to(REPOSITORY) else path.as_uri()


def capture(case: CorpusCase, root: Path, corpus: Path = CORPUS, *, materialized_id: str | None = None) -> tuple[dict, dict]:
    """Write `<root>/<case id>/{repository.git, issue.json, expected.json}`; return the issue and expected records."""
    name = materialized_id or case.case_id
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("materialized id must be one directory name")
    directory = root / name
    repository = directory / "repository.git"
    directory.mkdir(parents=True, exist_ok=True)
    if not repository.exists():
        subprocess.run(["git", "init", "--quiet", "--bare", "--template=", str(repository)], check=True)
    revision = commit(repository, snapshot(corpus / str(case.baseline.variant)))
    fixed = commit(repository, snapshot(corpus / str(case.candidate.variant))) if case.candidate else None
    body = issue_text(case.finding).removeprefix(case.finding.title).lstrip("\n")
    issue = {"schema": SCHEMA, "issue": {"provider": "manual", "title": case.finding.title, "body": body, "format": "markdown"},
             "repository": _location(repository), "revision": revision, "scope": "component"}
    if fixed:
        issue["fixed_revision"] = fixed
    expected = {"case": case.case_id, "language": case.language, "split": case.split,
                "oracle": case.oracle.model_dump(mode="json"), "case_sha256": case_digest(case, corpus)}
    (directory / "issue.json").write_text(json.dumps(issue, indent=2) + "\n")
    (directory / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    return issue, expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--set", dest="cohort", choices=sorted(json.loads(COHORTS.read_text())))
    which.add_argument("--case", action="append")
    args = parser.parse_args(argv)
    wanted = json.loads(COHORTS.read_text())[args.cohort] if args.cohort else args.case
    cases = {case.case_id: case for case in load()}
    if unknown := sorted(set(wanted) - set(cases)):
        parser.error(f"unknown case ids: {', '.join(unknown)}")
    for case_id in wanted:
        issue, _ = capture(cases[case_id], args.root)
        print(f"{case_id} {issue['revision']} {issue.get('fixed_revision', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
