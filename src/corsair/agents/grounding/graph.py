"""Security graph seams: the client Protocol, an in-memory fixture graph, the retrieval operations and ``gather``.

The production client will make three HTTP calls (``GET /graph/node/{id}``, ``POST /graph/search``,
``POST /graph/query``); none is written here. Everything above the client is real and runs against the fixture:
parameterised queries only (the one formatted value, the hop count, is range-checked), the terminal-state filter,
the similarity floor, the top-k caps, and ``gather``, which never raises and names every failure in ``degraded``.
"""
from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .contracts import TERMINAL_STATES, GraphComment, GraphIssue, GraphRepoRef, GroundingContext, RelatedIssue

MIN_SIMILARITY = 0.5
"""Below this a match is a coincidence of vocabulary, not precedent. A missing score is kept."""


class IssueNotFound(LookupError):
    """The graph answered and holds no such issue."""


class GraphClient(Protocol):
    def get_node(self, node_id: str) -> dict[str, Any]: ...
    def search(self, query: str, label: str = "Issues", top_k: int = 20) -> list[tuple[str, float | None]]: ...
    def query(self, cypher: str, params: Mapping[str, Any]) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class GraphSettings:
    top_k: int = 20
    max_comments_per_issue: int = 10
    row_limit: int = 500
    max_hops: int = 2
    terminal_states: frozenset[str] = TERMINAL_STATES

    def __post_init__(self) -> None:
        if not (1 <= self.top_k <= 100 and 1 <= self.max_comments_per_issue <= 50 and 1 <= self.row_limit <= 5000):
            raise ValueError("graph settings out of range")
        hops_in_range(self.max_hops)


def hops_in_range(hops: Any) -> int:
    """The one value formatted into a query; openCypher cannot parameterise a path length."""
    if isinstance(hops, bool) or not isinstance(hops, int) or not 1 <= hops <= 4:
        raise ValueError("hop count must be an int from 1 to 4")
    return hops


COMMENTS = ("MATCH (peer:Issues)<-[:COMMENT_ON]-(c:Comments) WHERE peer.id IN $ids AND toLower(peer.state) IN "
            "$states WITH peer, c ORDER BY c.created_at DESC "
            "RETURN peer.id AS issue_id, collect(c)[..$max_per_issue] AS comments LIMIT $row_limit")
CWE_PEERS = ("MATCH (:Issues {id: $id})-[:HAS_CWE]->(:CWEs)<-[:HAS_CWE]-(peer:Issues) "
             "WHERE toLower(peer.state) IN $states RETURN DISTINCT peer LIMIT $top_k")
NEARBY = ("MATCH (:Issues {{id: $id}})-[:HAS_CWE|AFFECTS_REPO|IN_CLUSTER*1..{hops}]-(peer:Issues) "
          "WHERE peer.id <> $id AND toLower(peer.state) IN $states RETURN DISTINCT peer LIMIT $top_k")
_WRITE = re.compile(r"(?i)\b(create|merge|delete|detach|set|remove|drop|load|call)\b")


# --- text helpers shared with intake ------------------------------------------------------------------------------

_BLOCK_END = re.compile(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])\s*>")
_TAG = re.compile(r"<[^>]*>")


def plain_text(markup: str) -> str:
    """Reduce tracker HTML to text: block ends become newlines, other tags drop, entities decode once.

    Normalisation, not sanitisation: the result is still untrusted.
    """
    text = html.unescape(_TAG.sub("", _BLOCK_END.sub("\n", markup))).replace("\xa0", " ")
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def source_location(text: str) -> tuple[str | None, int | None]:
    """Split ``path:line``; a leading / is stripped and any ``..`` segment yields (None, None)."""
    path, _, line = text.strip().lstrip("/").rpartition(":")
    if not path or not re.fullmatch(r"\d{1,7}", line):
        path, line = text.strip().lstrip("/"), ""
    if not path or ".." in path.split("/"):
        return None, None
    return path, int(line) if line and int(line) >= 1 else None


def _text(value: Any, cap: int) -> str:
    return "" if value is None else str(value)[:cap]


def _props(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    for key in ("properties", "node", "issue", "data"):
        if isinstance(body.get(key), dict):
            return body[key]
    return body


def issue_from(body: Any) -> GraphIssue | None:
    """Tolerant unwrap of an issue node; a record without an id is discarded."""
    props = _props(body)
    node_id = props and (props.get("id") or props.get("issue_id") or props.get("_id"))
    if not node_id:
        return None
    optional = {key: _text(props[key], 2048) for key in ("cwe", "severity", "repo_url", "web_url", "source_file")
                if props.get(key)}
    return GraphIssue(id=_text(node_id, 256), title=_text(props.get("title"), 500), state=_text(props.get("state"), 100),
                      description=_text(props.get("description") or props.get("body"), 20_000), **optional)


def comment_from(body: Any) -> GraphComment:
    props = _props(body) or {}
    return GraphComment(author=_text(props.get("author"), 200), created_at=_text(props.get("created_at"), 64),
                        text=plain_text(_text(props.get("text"), 8_000))[:4_000])


# --- the fixture graph ------------------------------------------------------------------------------------------


@dataclass
class InMemoryGraph:
    """A fixture graph answering exactly the retrieval queries above. Edges are implied by shared properties:
    HAS_CWE by ``cwe``, AFFECTS_REPO by ``repo_url``, IN_CLUSTER by ``cluster``."""

    issues: list[dict[str, Any]]
    comments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def _issue(self, node_id: str) -> dict[str, Any] | None:
        return next((issue for issue in self.issues if issue.get("id") == node_id), None)

    def get_node(self, node_id: str) -> dict[str, Any]:
        if (issue := self._issue(node_id)) is None:
            raise IssueNotFound(node_id)
        return dict(issue)

    def search(self, query: str, label: str = "Issues", top_k: int = 20) -> list[tuple[str, float | None]]:
        words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for issue in self.issues:
            other = set(re.findall(r"\w+", f"{issue.get('title', '')} {issue.get('description', '')}".lower()))
            scored.append((issue["id"], round(len(words & other) / len(words | other), 3) if words | other else 0.0))
        return sorted(scored, key=lambda pair: -(pair[1] or 0))[:top_k]

    def query(self, cypher: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        if _WRITE.search(cypher):
            raise ValueError("only parameterised reads are accepted")
        states = set(params.get("states", ()))
        def decided(issue: dict[str, Any]) -> bool:
            return str(issue.get("state", "")).lower() in states
        if cypher == COMMENTS:
            rows = [{"issue_id": i["id"], "comments": sorted(self.comments.get(i["id"], []), reverse=True,
                                                             key=lambda c: c.get("created_at", ""))
                     [:params["max_per_issue"]]}
                    for i in self.issues if i["id"] in params["ids"] and decided(i)]
            return rows[:params["row_limit"]]
        own = self._issue(params["id"]) or {}
        if cypher == CWE_PEERS:
            peers = [i for i in self.issues if own.get("cwe") and i.get("cwe") == own.get("cwe")
                     and i["id"] != own.get("id") and decided(i)]
        elif any(cypher == NEARBY.format(hops=hops) for hops in range(1, 5)):
            keys = ("cwe", "repo_url", "cluster")
            peers = [i for i in self.issues if i["id"] != own.get("id") and decided(i)
                     and any(own.get(key) and i.get(key) == own.get(key) for key in keys)]
        else:
            raise ValueError("the fixture graph answers only the retrieval queries")
        return [{"peer": peer} for peer in peers[:params["top_k"]]]


# --- retrieval operations ---------------------------------------------------------------------------------------


def get_issue(client: GraphClient, issue_id: str) -> GraphIssue:
    issue = issue_from(client.get_node(issue_id))
    if issue is None:
        raise IssueNotFound(issue_id)
    return issue


def issue_comments(client: GraphClient, ids: Sequence[str], settings: GraphSettings
                   ) -> dict[str, tuple[GraphComment, ...]]:
    """Comments of terminal-state issues only, newest first: a conclusion, not an argument in progress."""
    if not ids:
        return {}
    rows = client.query(COMMENTS, {"ids": list(ids), "states": sorted(settings.terminal_states),
                                   "max_per_issue": settings.max_comments_per_issue, "row_limit": settings.row_limit})
    return {str(row["issue_id"]): tuple(comment_from(c) for c in row.get("comments", [])) for row in rows}


def _with_comments(client: GraphClient, found: list[tuple[GraphIssue, str, float | None]],
                   settings: GraphSettings) -> list[RelatedIssue]:
    comments = issue_comments(client, [issue.id for issue, _, _ in found], settings)
    return [RelatedIssue(issue=issue, relation=relation, similarity=score, comments=comments.get(issue.id, ()))
            for issue, relation, score in found]


def find_prior_issues(client: GraphClient, query_text: str, settings: GraphSettings) -> list[RelatedIssue]:
    """Over-fetch top_k x 3, drop scores under MIN_SIMILARITY (keep missing ones), keep the first top_k decided."""
    found = []
    for issue_id, score in client.search(query_text, "Issues", settings.top_k * 3):
        if score is not None and score < MIN_SIMILARITY:
            continue
        try:
            issue = get_issue(client, issue_id)
        except IssueNotFound:
            continue
        if issue.state.lower() in settings.terminal_states:
            found.append((issue, "similarity", score))
        if len(found) == settings.top_k:
            break
    return _with_comments(client, found, settings)


def related_issues(client: GraphClient, issue_id: str, relation: str, settings: GraphSettings) -> list[RelatedIssue]:
    """Decided neighbours by shared CWE, or "nearby" over the allowlisted edges; a cap, not a ranking."""
    if relation == "cwe":
        cypher = CWE_PEERS
    elif relation == "nearby":
        cypher = NEARBY.format(hops=hops_in_range(settings.max_hops))
    else:
        raise ValueError("relation must be cwe or nearby")
    rows = client.query(cypher, {"id": issue_id, "states": sorted(settings.terminal_states), "top_k": settings.top_k})
    peers = [issue for row in rows if (issue := issue_from(row.get("peer"))) is not None]
    return _with_comments(client, [(issue, relation, None) for issue in peers[:settings.top_k]], settings)


def issue_repo_ref(client: GraphClient, issue_id: str) -> GraphRepoRef | None:
    """Stub: the repository from the issue node's own ``repo_url``. Callers fail closed on None.

    TODO(grounding): compose the clone URL from the Repositories node coordinates as the spec describes.
    """
    try:
        issue = get_issue(client, issue_id)
    except IssueNotFound:
        return None
    return GraphRepoRef(clone_url=issue.repo_url, source="coordinates") if issue.repo_url else None


def query_text_for(title: str, cwe: str | None, description: str, vulnerability_class: str | None = None) -> str:
    """What the finding is, not where: title, CWE, class and the first 600 characters of the description."""
    body = " ".join(description.split())[:600]
    return " ".join(part for part in (title, cwe or "", vulnerability_class or "", body) if part)


def gather(client: GraphClient | None, issue_id: str | None, query_text: str,
           settings: GraphSettings = GraphSettings()) -> GroundingContext:
    """Assemble the context. Never raises: each step is wrapped and its failure named in ``degraded``."""
    if client is None:
        reason = "security graph not configured (empty base URL); no retrieval was attempted"
        return GroundingContext(degraded=(reason,))
    degraded: list[str] = []
    issue, comments, related = None, (), []
    def step(name: str, call):
        try:
            return call()
        except Exception as error:  # every failure is recorded by name; silence would read as "no precedent"
            degraded.append(f"{name} failed: {type(error).__name__}: {str(error)[:200]}")
            return None
    if issue_id:
        issue = step("issue lookup", lambda: get_issue(client, issue_id))
        if issue is not None:
            comments = (step("issue comments", lambda: issue_comments(client, [issue.id], settings)) or {}
                        ).get(issue.id, ())
            related += step("same-CWE neighbours", lambda: related_issues(client, issue.id, "cwe", settings)) or []
    seen = {r.issue.id for r in related} | ({issue.id} if issue else set())
    for hit in step("similarity search", lambda: find_prior_issues(client, query_text, settings)) or []:
        if hit.issue.id not in seen:
            related.append(hit)
            seen.add(hit.issue.id)
    return GroundingContext(issue=issue, comments=comments, related=tuple(related), degraded=tuple(degraded))
