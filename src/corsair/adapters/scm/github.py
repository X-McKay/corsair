"""Fixed-host, bounded GitHub issue lookup. Never follows issue links or redirects."""

import os
from collections.abc import Callable
from typing import BinaryIO
from urllib.request import HTTPRedirectHandler, Request, build_opener

from corsair.contracts.intake_agent import Issue, IssueReference, parse_issue_json


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def fetch_issue(
    reference: IssueReference, *, opener: Callable[..., BinaryIO] | None = None
) -> Issue:
    request = Request(
        f"https://api.github.com/repos/{reference.owner}/{reference.repository}/issues/{reference.number}",
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    transport = opener if opener is not None else build_opener(_NoRedirect()).open
    with transport(request, timeout=15) as response:
        payload = parse_issue_json(response.read(65537))
    if not isinstance(payload, dict) or "pull_request" in payload:
        raise ValueError("expected one GitHub issue")
    return Issue.model_validate({"title": payload.get("title"), "description": payload.get("body")})
