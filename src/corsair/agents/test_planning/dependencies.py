"""The planner's only dependency: its typed input, with a confined reader over the saved source it carries."""

from dataclasses import dataclass

from ..source.contracts import SourceExcerpt, SourceFile
from ..source.tools import read_saved_source
from .contracts import TestPlanningInput


@dataclass(frozen=True)
class PlanningDependencies:
    inputs: TestPlanningInput

    @property
    def source_files(self) -> tuple[SourceFile, ...]:
        return self.inputs.source_files

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        return read_saved_source(self.inputs.source_files, path, start_line, end_line)
