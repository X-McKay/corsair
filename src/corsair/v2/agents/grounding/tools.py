"""The Grounding agent's read-only tools, over the already retrieved context only (never the graph itself).

Each result is bounded (at most 8 issues, 6 comments per issue and 600 characters per text value, and never more
than ``MAX_GRAPH_BYTES``) and says how much it omitted, so a large neighbourhood cannot flood one request. The
same renderer writes the ``retrieved_context`` block of the prompt.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset

from .contracts import GraphComment, GraphIssue, GroundingContext, RelatedIssue

TOOLSET_ID = "grounding"
MAX_ISSUES, MAX_COMMENTS, TEXT_CAP, MAX_GRAPH_BYTES = 8, 6, 600, 48_000


def _cap(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= TEXT_CAP else f"{text[:TEXT_CAP]} [... {len(text) - TEXT_CAP} characters omitted]"


def render_comments(comments: tuple[GraphComment, ...]) -> list[str]:
    lines = [f"  - {c.author or 'unknown'} ({c.created_at or 'undated'}): {_cap(c.text)}"
             for c in comments[:MAX_COMMENTS]]
    if len(comments) > MAX_COMMENTS:
        lines.append(f"  ({len(comments) - MAX_COMMENTS} more comments omitted)")
    return lines


def render_issue(issue: GraphIssue, *, relation: str = "self", similarity: float | None = None,
                 comments: tuple[GraphComment, ...] = ()) -> str:
    score = "" if similarity is None else f" similarity={similarity}"
    head = f"[{issue.id}] relation={relation}{score} state={issue.state or 'unknown'} cwe={issue.cwe or 'unknown'}"
    lines = [head, f"  title: {_cap(issue.title)}", f"  description: {_cap(issue.description)}"]
    return "\n".join(lines + render_comments(comments))


def _bounded(blocks: list[str], total: int, what: str) -> str:
    shown = blocks[:MAX_ISSUES]
    if total > len(shown):
        shown.append(f"({total - len(shown)} more {what} omitted)")
    text = "\n".join(shown) if shown else f"No {what} in the retrieved context."
    return text.encode()[:MAX_GRAPH_BYTES].decode(errors="ignore")


def render_context(context: GroundingContext) -> str:
    own = (render_issue(context.issue, comments=context.comments) if context.issue
           else "This finding has no issue of its own in the graph.")
    related = _bounded([render_issue(r.issue, relation=r.relation, similarity=r.similarity, comments=r.comments)
                        for r in context.related], len(context.related), "related issues")
    degraded = "\n".join(f"- {note}" for note in context.degraded) or "- none"
    return f"Own issue:\n{own}\n\nRelated decided issues:\n{related}\n\nRetrieval degraded:\n{degraded}"


def _find(context: GroundingContext, issue_id: str) -> tuple[GraphIssue, tuple[GraphComment, ...], RelatedIssue | None]:
    if context.issue is not None and context.issue.id == issue_id:
        return context.issue, context.comments, None
    for related in context.related:
        if related.issue.id == issue_id:
            return related.issue, related.comments, related
    raise KeyError(issue_id)


def read_issue(ctx: RunContext[Any], issue_id: str) -> str:
    """Read one issue listed in retrieved_context: its state, CWE, title and description."""
    try:
        issue, _, related = _find(ctx.deps.context, issue_id)
    except KeyError:
        return f"Issue {issue_id} is not in the retrieved context and cannot be cited."
    return render_issue(issue, relation=related.relation if related else "self",
                        similarity=related.similarity if related else None)


def read_issue_comments(ctx: RunContext[Any], issue_id: str) -> str:
    """Read the review comments retrieved for one listed issue, newest first."""
    try:
        _, comments, _ = _find(ctx.deps.context, issue_id)
    except KeyError:
        return f"Issue {issue_id} is not in the retrieved context and cannot be cited."
    return "\n".join(render_comments(comments)) or f"No comments were retrieved for {issue_id}."


def find_prior_issues(ctx: RunContext[Any]) -> str:
    """List the decided issues retrieval found by similarity to this finding."""
    hits = [r for r in ctx.deps.context.related if r.relation == "similarity"]
    return _bounded([render_issue(r.issue, relation=r.relation, similarity=r.similarity) for r in hits],
                    len(hits), "similar issues")


def read_related_issues(ctx: RunContext[Any], relation: Literal["cwe", "nearby"] = "cwe") -> str:
    """List the decided issues retrieval found by shared CWE or as graph neighbours."""
    hits = [r for r in ctx.deps.context.related if r.relation == relation]
    return _bounded([render_issue(r.issue, relation=r.relation) for r in hits], len(hits), f"{relation} issues")


def grounding_tools() -> FunctionToolset[Any]:
    tools = FunctionToolset[Any](id=TOOLSET_ID)
    for function in (read_issue, read_issue_comments, find_prior_issues, read_related_issues):
        tools.add_function(function, retries=1)
    return tools
