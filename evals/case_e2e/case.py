"""A benchmark case as an issue request plus its expected outcome: the eval wrapper's way to call the issue entry.

The manifest's agent part becomes a `corsair-issue-request/v1` with a `manual` issue, the clone under the operator's
case-source root as a `file://` repository, and the two commits; the evaluator part stays here as the expected
outcome, which the investigation never reads. The case id never reaches the request.
"""
from pathlib import Path

from corsair.investigation.request import IssueRequest
from evals.benchmark.cases import BenchmarkEntry
from evals.benchmark.cases import load as load_cases
from evals.benchmark.sources import case_dir


class CaseRefused(ValueError):
    """No manifest names the case."""


def entry(case: str) -> BenchmarkEntry:
    """The manifest by its directory name or its case id."""
    found = [e for e in load_cases() if e.manifest and (e.inventory.case_id == case or e.directory.name == case)]
    if len(found) != 1:
        raise CaseRefused(f"{case!r} names {len(found)} benchmark manifests")
    return found[0]


def case_request(found: BenchmarkEntry, sources: Path) -> IssueRequest:
    agent = found.manifest.agent
    title, _, body = agent.issue.strip().partition("\n")
    return IssueRequest.model_validate({
        "schema": "corsair-issue-request/v1",
        "issue": {"provider": "manual", "title": title, "body": body.strip()},
        "repository": f"file://{(case_dir(sources.resolve(), found.inventory.case_id) / 'repo').as_posix()}",
        "revision": agent.baseline, "fixed_revision": agent.candidate, "scope": agent.scope})


def expected(found: BenchmarkEntry):
    """The evaluator's chain oracle, or None when unknown; written beside the request, never read by it."""
    known = found.manifest.evaluator.expected
    return known.chain if known else None
