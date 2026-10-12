"""Issue-analysis dependencies over the shared confined saved-source reader."""

from dataclasses import dataclass

from ...source.tools import READ_SOURCE_TOOL, TOOL_RETRIES, ranged_source_tools, read_saved_source
from ..contracts import IssueAnalysisInput, SourceExcerpt, SourceFile


@dataclass(frozen=True)
class FixtureDependencies:
    inputs: IssueAnalysisInput

    @property
    def source_files(self) -> tuple[SourceFile, ...]:
        return self.inputs.source_files

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        return read_saved_source(self.inputs.source_files, path, start_line, end_line)


def source_tools():
    # Toolset id is the durable fixture histories' tool identity; it must not change.
    return ranged_source_tools("issue_analysis_source")


__all__ = ["READ_SOURCE_TOOL", "TOOL_RETRIES", "FixtureDependencies", "source_tools"]
