#!/usr/bin/env python3
"""Check local Markdown destinations and anchors in maintained repository files."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".runs",
        ".state",
        ".venv",
        ".work",
        "__pycache__",
        "build",
        "dist",
        "outputs",
    }
)
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\((?P<destination>[^\n)]+)\)")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(?P<heading>.*?)(?:\s+#+)?\s*$")
SETEXT_PATTERN = re.compile(r"^\s{0,3}(?:=+|-+)\s*$")
HTML_ANCHOR_PATTERN = re.compile(
    r"<a\b[^>]*\b(?:id|name)\s*=\s*['\"](?P<anchor>[^'\"]+)['\"][^>]*>",
    re.IGNORECASE,
)
HEADING_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]*\)")


@dataclass(frozen=True, order=True)
class Issue:
    """One local-reference problem reported by the checker."""

    source: str
    destination: str
    message: str

    def format(self) -> str:
        return f"{self.source}: {self.destination}: {self.message}"


def markdown_files(root: Path) -> list[Path]:
    """Return repository Markdown files without private or generated directories."""

    files: list[Path] = []
    for directory, child_directories, names in root.walk():
        child_directories[:] = [
            name
            for name in child_directories
            if name not in EXCLUDED_DIRECTORIES and not name.startswith(".")
        ]
        files.extend(directory / name for name in names if name.endswith(".md"))
    return sorted(files)


def prose_lines(markdown: str) -> list[str]:
    """Exclude fenced code blocks, whose examples are not repository references."""

    lines: list[str] = []
    marker: tuple[str, int] | None = None
    for line in markdown.splitlines():
        fence = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker is None:
            if fence is not None:
                marker = (fence.group(1)[0], len(fence.group(1)))
            else:
                lines.append(line)
            continue
        if (
            fence is not None
            and fence.group(1)[0] == marker[0]
            and len(fence.group(1)) >= marker[1]
        ):
            marker = None
    return lines


def heading_slug(heading: str) -> str:
    """Produce the GitHub-compatible slug used by this repository's Markdown links."""

    text = HEADING_LINK_PATTERN.sub(r"\1", heading).replace("`", "")
    return "".join(
        character for character in text.lower() if character.isalnum() or character in " -_"
    ).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    """Collect implicit heading and explicit HTML anchor identifiers from one page."""

    lines = prose_lines(path.read_text(encoding="utf-8"))
    identifiers: set[str] = set()
    occurrences: dict[str, int] = {}

    def add_heading(heading: str) -> None:
        slug = heading_slug(heading)
        if not slug:
            return
        occurrence = occurrences.get(slug, 0)
        occurrences[slug] = occurrence + 1
        identifiers.add(slug if occurrence == 0 else f"{slug}-{occurrence}")

    for index, line in enumerate(lines):
        heading = HEADING_PATTERN.match(line)
        if heading is not None:
            add_heading(heading.group("heading"))
        elif index + 1 < len(lines) and line.strip() and SETEXT_PATTERN.match(lines[index + 1]):
            add_heading(line.strip())
    identifiers.update(
        match.group("anchor") for match in HTML_ANCHOR_PATTERN.finditer("\n".join(lines))
    )
    return identifiers


def destination_url(raw_destination: str) -> str:
    """Extract the URL portion of an inline Markdown destination with an optional title."""

    destination = raw_destination.strip()
    if destination.startswith("<"):
        closing = destination.find(">")
        return destination[1:closing] if closing != -1 else destination
    return destination.split(maxsplit=1)[0] if destination else ""


def local_reference(destination: str) -> tuple[str, str] | None:
    """Return decoded local path and fragment, ignoring external URLs without fetching them."""

    parsed = urllib.parse.urlsplit(destination)
    if parsed.scheme or parsed.netloc or destination.startswith("//"):
        return None
    return urllib.parse.unquote(parsed.path), urllib.parse.unquote(parsed.fragment)


def resolve_target(root: Path, source: Path, target: str) -> Path:
    """Resolve a repository-local target without allowing an external filesystem escape."""

    if target.startswith("/"):
        return (root / target.removeprefix("/")).resolve()
    return (source.parent / target).resolve()


def check(root: Path) -> list[Issue]:
    """Return sorted local-link and anchor errors below the supplied repository root."""

    root = root.resolve()
    anchor_cache: dict[Path, set[str]] = {}
    issues: list[Issue] = []
    for source in markdown_files(root):
        relative_source = source.relative_to(root).as_posix()
        for match in LINK_PATTERN.finditer(
            "\n".join(prose_lines(source.read_text(encoding="utf-8")))
        ):
            destination = destination_url(match.group("destination"))
            reference = local_reference(destination)
            if reference is None:
                continue
            target, fragment = reference
            resolved = resolve_target(root, source, target)
            try:
                resolved.relative_to(root)
            except ValueError:
                issues.append(Issue(relative_source, destination, "target escapes repository root"))
                continue
            if not resolved.exists():
                issues.append(Issue(relative_source, destination, "missing target"))
                continue
            if fragment and resolved.suffix.lower() == ".md":
                if resolved not in anchor_cache:
                    anchor_cache[resolved] = anchors(resolved)
                if fragment not in anchor_cache[resolved]:
                    issues.append(Issue(relative_source, destination, "missing anchor"))
    return sorted(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root to check")
    arguments = parser.parse_args()
    if not arguments.root.is_dir():
        parser.error(f"not a directory: {arguments.root}")
    issues = check(arguments.root)
    for issue in issues:
        print(issue.format(), file=sys.stderr)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
