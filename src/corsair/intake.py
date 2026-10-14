"""The Intake stage: turn a request into a ``Case`` (redesign section 5, stage 1).

Two sources today. ``load_corpus_case`` reads one case of the seeded corpus manifest
(``benchmarks/corpus/infosec-harness/manifest.json``); ``from_issue_json`` reads a generic request file. Neither
ever puts scoring truth into the Case: ``load_oracle`` returns it separately, for evaluators only.

A revision is a local directory, identified by ``tree_sha256``: a digest over the sorted (relative path, mode,
content sha256) of every file in the tree, so two runs agree on what they investigated. Modes are normalised as
git does (755 executable, 644 otherwise, 120000 for a symlink, whose content is its target), so the digest does
not depend on a checkout's umask. ``.git`` directories are left out.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .contracts import Case, Finding, Label, Revision

CORPUS_PREFIX = "eval-corpus/"
EXPECTED_LABELS = {
    "potentially_exploitable": Label.LIKELY_EXPLOITABLE,
    "likely_not_exploitable": Label.LIKELY_NOT_EXPLOITABLE,
}
FINDING_FIELDS = ("title", "description", "file_path", "start_line", "symbol", "cwe")


def tree_sha256(root: Path) -> str:
    """Digest over the sorted (relative POSIX path, normalised mode, content sha256) of every file under ``root``."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"revision source is not a directory: {root}")
    entries: list[tuple[str, str, str]] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        here = Path(directory)
        # os.walk lists a symlinked directory without descending into it; record it as a link.
        for name in [d for d in dirnames if (here / d).is_symlink()] + filenames:
            path = here / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                mode, content = "120000", os.readlink(path).encode()
            elif stat.S_ISREG(info.st_mode):
                mode = "100755" if info.st_mode & 0o111 else "100644"
                content = path.read_bytes()
            else:
                continue
            entries.append((path.relative_to(root).as_posix(), mode, hashlib.sha256(content).hexdigest()))
    digest = hashlib.sha256()
    for relative, mode, content in sorted(entries):
        digest.update(f"{relative}\0{mode}\0{content}\n".encode())
    return digest.hexdigest()


def revision(source: Path, commit: str | None = None) -> Revision:
    source = Path(source).resolve()
    return Revision(source=str(source), commit=commit, tree_sha256=tree_sha256(source))


def _manifest_case(manifest: Path, name: str) -> dict:
    cases = json.loads(Path(manifest).read_text())["cases"]
    matches = [case for case in cases if case.get("name") == name]
    if len(matches) != 1:
        raise KeyError(f"{name!r} names {len(matches)} cases in {manifest}")
    return matches[0]


def corpus_case_id(name: str) -> str:
    """Opaque, stable id for a corpus case: the manifest name never appears in a run's inputs."""
    return f"corpus:{hashlib.sha256(name.encode()).hexdigest()[:16]}"


def load_corpus_case(manifest: Path, name: str) -> Case:
    """One corpus case as a Case: the finding and the variant's tree, never its ``truth``.

    ``repo_url`` looks like ``eval-corpus/<lang>/<topic>/<a|b>``; the ``eval-corpus/`` prefix is the manifest's
    own directory. Manifest names carry the answer (``sqli-vulnerable``), so ``case_id`` is an opaque digest of the
    name (``corpus_case_id``); evaluators map it back through ``load_oracle``.
    """
    manifest = Path(manifest).resolve()
    entry = _manifest_case(manifest, name)
    finding = entry["finding"]
    repo_url = finding["repo_url"]
    if not repo_url.startswith(CORPUS_PREFIX):
        raise ValueError(f"{name}: repo_url {repo_url!r} is not under {CORPUS_PREFIX}")
    source = (manifest.parent / repo_url[len(CORPUS_PREFIX):]).resolve()
    if not source.is_relative_to(manifest.parent):
        raise ValueError(f"{name}: repo_url {repo_url!r} leaves the corpus directory")
    return Case(case_id=corpus_case_id(name), finding=Finding(**{key: finding.get(key) for key in FINDING_FIELDS
                                                 if finding.get(key) is not None}),
                revision=revision(source))


def load_oracle(manifest: Path, name: str) -> dict:
    """The case's scoring truth, for evaluators only; ``expected_label`` maps the manifest verdict to a v2 label."""
    entry = _manifest_case(Path(manifest), name)
    truth = dict(entry["truth"])
    verdict = truth["expected_verdict"]
    if verdict not in EXPECTED_LABELS:
        raise ValueError(f"{name}: unmapped expected_verdict {verdict!r}")
    return {"case_id": corpus_case_id(name), "name": name, "language": entry.get("language"), "expected_label": EXPECTED_LABELS[verdict].value,
            **truth}


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    finding: Finding
    source: str = Field(min_length=1)
    commit: str | None = None
    fixed_source: str | None = None
    fixed_commit: str | None = None


def from_issue_json(path: Path) -> Case:
    """A Case from a generic request file. The file is JSON with exactly these keys::

        {
          "case_id": "optional, opaque id; default issue:<first 16 hex of the file's sha256>",
          "finding": {"title": "...", "description": "...", "file_path": "src/app.py", "start_line": 12,
                      "symbol": "get_user", "cwe": "CWE-89"},
          "source": "path to the vulnerable revision's tree, relative to this file or absolute",
          "commit": "optional 40-hex commit the tree was checked out at",
          "fixed_source": "optional path to the fix revision's tree",
          "fixed_commit": "optional 40-hex commit of the fix revision"
        }

    Only ``finding.title`` and ``source`` are required. Any other key (a label, an oracle) is refused, so scoring
    truth cannot travel into a Case through this door.
    """
    path = Path(path).resolve()
    raw = path.read_bytes()
    request = _Request.model_validate_json(raw)
    base = path.parent
    fixed = revision(base / request.fixed_source, request.fixed_commit) if request.fixed_source else None
    return Case(case_id=request.case_id or f"issue:{hashlib.sha256(raw).hexdigest()[:16]}", finding=request.finding,
                revision=revision(base / request.source, request.commit), fixed_revision=fixed)
