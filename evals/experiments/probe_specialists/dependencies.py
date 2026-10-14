"""Immutable role input; caller owns budgets and starts a fresh native run."""
from dataclasses import dataclass
from corsair.agents.source.tools import read_saved_source
from .contracts import ControlInput, ExploitInput

@dataclass(frozen=True)
class SpecialistDependencies:
    inputs: ControlInput | ExploitInput

    @property
    def source_files(self):
        return self.inputs.source_files

    def read_source(self, path, start_line, end_line):
        return read_saved_source(self.source_files, path, start_line, end_line)
