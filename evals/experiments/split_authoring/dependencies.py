"""Immutable read-only seed and source; admitted writes stay in native run history."""

from dataclasses import dataclass

from corsair.agents.source.contracts import SourceFile
from corsair.agents.source.tools import read_saved_source
from .contracts import DraftingInput


@dataclass(frozen=True)
class DraftingDependencies:
    inputs: DraftingInput

    @property
    def source_files(self):
        return self.inputs.source_files + tuple(SourceFile(path=file.path, content=file.content)
                                               for file in self.inputs.frozen_control)

    def read_source(self, path, start_line, end_line):
        return read_saved_source(self.source_files, path, start_line, end_line)
