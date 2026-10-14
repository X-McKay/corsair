"""ADO intake seams: work items to ``FindingInput``, with fixtures in place of Azure DevOps (no HTTP here).

What is real: the WIQL shape check and intake cap, the HTML reduction, the scanner-header parser, the field
mapping with its never-guess rules, and graph location backfill. What is stubbed: fetching (``FixtureWorkItems``)
and write-back (``InMemoryWriteBack``); the production adapters will implement the same Protocols over the ADO
REST API 7.1 (200 ids per GET, ``$top`` = cap + 1 so an overflow is observed).
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .contracts import FindingInput, ScanRef, Skip
from .graph import GraphClient, IssueNotFound, plain_text, source_location

MAX_ITEMS = 500
WIQL_MAX_CHARS = 4_000
DEFAULT_FIELD_MAP: Mapping[str, str] = {
    "title": "System.Title", "description": "System.Description", "repository": "Custom.Repository",
    "revision": "Custom.Revision", "file_path": "Custom.FilePath", "start_line": "Custom.StartLine",
    "cwe": "Custom.CWE", "severity": "Microsoft.VSTS.Common.Severity",
}
"""``source_tool`` is deliberately absent: it is only ever a mapped field, and never a person's name."""


class IntakeTooLarge(ValueError):
    """More work items matched than the intake cap; refused rather than truncated."""


class WorkItemSource(Protocol):
    def fetch_work_items(self, ids: Sequence[int] = (), wiql: str | None = None) -> list[dict[str, Any]]: ...


class CommentSink(Protocol):
    def upsert_comment(self, work_item_id: int, body: str) -> str | None: ...


def check_wiql(wiql: str) -> str:
    """Refuse a WIQL that is not exactly one ``SELECT ... FROM WorkItems`` read (the PAT may hold write scope)."""
    text = wiql.strip()
    if not text or len(text) > WIQL_MAX_CHARS:
        raise ValueError(f"WIQL must be 1 to {WIQL_MAX_CHARS} characters")
    if ";" in text or "--" in text or "/*" in text or "*/" in text:
        raise ValueError("WIQL may not contain a statement separator or comment syntax")
    if len(re.findall(r"\bselect\b", text, re.I)) != 1 or not re.match(r"(?is)^select\b.+\bfrom\s+workitems\b", text):
        raise ValueError("WIQL must be exactly one SELECT ... FROM WorkItems (WorkItemLinks is not accepted)")
    return text


class FixtureWorkItems:
    """Fixture stand-in for the ADO fetch: the same id dedup, WIQL check and cap, over in-memory items."""

    def __init__(self, items: Sequence[dict[str, Any]], *, max_items: int = MAX_ITEMS):
        self.items, self.max_items = {int(item["id"]): item for item in items}, max_items

    def fetch_work_items(self, ids: Sequence[int] = (), wiql: str | None = None) -> list[dict[str, Any]]:
        if wiql is not None:
            check_wiql(wiql)
            ids = list(self.items)  # a fixture cannot evaluate WIQL; it matches every item
        wanted = list(dict.fromkeys(int(i) for i in ids))
        if len(wanted) > self.max_items:
            raise IntakeTooLarge(f"{len(wanted)} work items exceed the intake cap of {self.max_items}")
        return [self.items[i] for i in wanted if i in self.items]


class InMemoryWriteBack:
    """Exactly one comment per work item, edited on re-run; a no-op when write-back is disabled."""

    def __init__(self, *, enabled: bool = False):
        self.enabled, self.comments = enabled, {}

    def upsert_comment(self, work_item_id: int, body: str) -> str | None:
        if not self.enabled:
            return None
        self.comments[work_item_id] = body
        return f"comment-{work_item_id}"


_URLS = (
    re.compile(r"https://dev\.azure\.com/(?P<org>[^/\s]+)/(?P<project>[^/\s]+)/_git/(?P<repo>[^/\s?#]+)"),
    re.compile(r"https://(?P<org>[^./\s]+)\.visualstudio\.com/(?:DefaultCollection/)?(?P<project>[^/\s]+)/_git/"
               r"(?P<repo>[^/\s?#]+)"),
    re.compile(r"git@ssh\.dev\.azure\.com:v3/(?P<org>[^/\s]+)/(?P<project>[^/\s]+)/(?P<repo>[^/\s]+)"),
)
_LABELS = r"(project|repository|branch|commit|run id)"
_FIELD = re.compile(rf"^{_LABELS}\s*:\s*(.+)$", re.I)
_NEXT_FIELD = re.compile(rf"\s{{2,}}(?={_LABELS}\s*:)", re.I)
_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")


def _bounded(value: str) -> str | None:
    value = value.strip().strip("*").strip()
    return value if value and len(value) <= 128 and not any(ord(c) < 32 for c in value) else None


def parse_scan_header(text: str, *, default_organization: str | None = None) -> ScanRef:
    """Read the scanner's header. A URL wins over fields; the last occurrence wins; only ``Commit:`` pins."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip().lstrip("-*•").strip().replace("**", "")
        for segment in _NEXT_FIELD.split(line)[::2]:
            if (match := _FIELD.match(segment.strip())) and (value := _bounded(match.group(2))) is not None:
                fields[match.group(1).lower()] = value
    commit = fields.get("commit")
    org = None
    if (run_id := fields.get("run id", "")).lower().startswith("ado-"):
        org = run_id[4:].split("-", 1)[0] or None
    ref = dict(organization=org or default_organization, project=fields.get("project"),
               repository=fields.get("repository"), branch=fields.get("branch"),
               commit=commit if commit and _COMMIT.match(commit) else None)
    urls = [match for pattern in _URLS for match in pattern.finditer(text)]
    if urls:
        last = max(urls, key=lambda match: match.start())
        ref.update(organization=last["org"], project=last["project"], repository=last["repo"])
    return ScanRef(**ref)


def _cwe(value: Any) -> str | None:
    match = re.fullmatch(r"(?:CWE-)?(\d{1,5})", str(value or "").strip(), re.I)
    return f"CWE-{match.group(1)}" if match else None


def _line(value: Any) -> int | None:
    try:
        line = int(str(value).strip())
    except ValueError:
        return None
    return line if line >= 1 else None


def work_item_to_finding(item: Mapping[str, Any], field_map: Mapping[str, str] = DEFAULT_FIELD_MAP
                         ) -> FindingInput | Skip:
    """Apply the field table, then the scanner header. No repository means Skip, never a guess."""
    item_id, raw = int(item["id"]), dict(item.get("fields") or {})
    def field(name: str) -> Any:
        key = field_map.get(name)
        value = raw.get(key) if key else None
        return value if value not in (None, "") else None
    description = plain_text(str(field("description") or ""))
    header = parse_scan_header(description)
    repo = field("repository") or raw.get("Custom.Repository")
    if not repo and header.organization and header.project and header.repository:
        repo = f"https://dev.azure.com/{header.organization}/{header.project}/_git/{header.repository}"
    if not repo:
        return Skip(external_id=str(item_id), reason="the work item establishes no repository")
    return FindingInput(
        external_id=str(item_id), title=str(field("title") or f"ADO work item {item_id}")[:512],
        description=description[:20_000], repo_url=str(repo),
        revision=str(field("revision") or header.commit or header.branch or "HEAD"),
        file_path=field("file_path"), start_line=_line(field("start_line")), cwe=_cwe(field("cwe")),
        severity=str(field("severity")) if field("severity") else None,
        source_tool=str(field("source_tool")) if field("source_tool") else None,
        source_kind="ado", ado_work_item_id=item_id)


def backfill_location_from_graph(finding: FindingInput, graph: GraphClient) -> tuple[FindingInput, str]:
    """Fill only missing file_path, start_line and cwe from the graph's issue node. Fail-soft: returns a note."""
    if finding.ado_work_item_id is None:
        return finding, "no work item id to look up"
    try:
        node = graph.get_node(str(finding.ado_work_item_id))
    except IssueNotFound:
        return finding, f"graph holds no issue {finding.ado_work_item_id}"
    except Exception as error:  # an unreachable graph weakens the finding but never stops intake
        return finding, f"graph backfill failed: {type(error).__name__}"
    path, line = source_location(str(node.get("source_file") or ""))
    filled = {key: value for key, value in (("file_path", path), ("start_line", line), ("cwe", _cwe(node.get("cwe"))))
              if value is not None and getattr(finding, key) is None}
    return finding.model_copy(update=filled), f"backfilled {', '.join(sorted(filled)) or 'nothing'}"
