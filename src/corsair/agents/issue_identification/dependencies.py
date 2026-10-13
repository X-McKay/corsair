"""What each identification mode receives: the authorized input and a confined source reader.

Inline mode reuses the issue-analysis `FixtureDependencies` over saved files; repository mode
reads an immutable `SourceTree` whose identity must match the input commit and tree.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..issue_analysis.tools.source import FixtureDependencies
from ..source.contracts import SourceExcerpt
from ..source.repository import RepositoryLimits, SourceTree
from .contracts import RepositoryIssueInput


class _IdentificationInputs(Protocol):
    @property
    def issue(self) -> str: ...

    @property
    def scope(self) -> Literal["component", "application_path"]: ...


class IdentificationDependencies(Protocol):
    @property
    def inputs(self) -> _IdentificationInputs: ...

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt: ...


@dataclass(frozen=True)
class RepositoryDependencies:
    inputs: RepositoryIssueInput
    source_tree: SourceTree
    source_limits: RepositoryLimits = field(default_factory=RepositoryLimits)

    def __post_init__(self):
        if self.source_tree.identity != (self.inputs.repository.commit, self.inputs.repository.tree):
            raise ValueError("source tree identity does not match the input repository commit and tree")

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        return self.source_tree.excerpt(path, start_line, end_line, self.source_limits)


__all__ = ["FixtureDependencies", "IdentificationDependencies", "RepositoryDependencies"]
