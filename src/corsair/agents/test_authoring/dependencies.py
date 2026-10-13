"""Injected runner, operator-owned budget and saved source for the authoring agent.

The patch is not held in mutable dependencies: it is rebuilt from this run's successful
write_test_file calls, so the same tools work when native durability serializes deps.
"""

from dataclasses import dataclass

from corsair.ports.test_runner import TestRunner

from ..source.contracts import SourceExcerpt, SourceFile
from ..source.tools import read_saved_source
from .contracts import TestAuthoringInput


@dataclass(frozen=True)
class AuthoringBudget:
    """Operator-owned; nothing in the prompt, plan or source can change it."""
    dev_runs: int = 3
    reveal_security_outcome: bool = False
    # Refused writes the author may act on; the next refusal ends the stage blocked at admission.
    admission_refusals: int = 1

    def __post_init__(self):
        if type(self.dev_runs) is not int or not 1 <= self.dev_runs <= 5:
            raise ValueError("development run budget outside the admitted range 1..5")
        if type(self.admission_refusals) is not int or not 0 <= self.admission_refusals <= 2:
            raise ValueError("admission refusal budget outside the admitted range 0..2")


@dataclass(frozen=True)
class AuthoringDependencies:
    inputs: TestAuthoringInput
    runner: TestRunner
    budget: AuthoringBudget = AuthoringBudget()

    @property
    def source_files(self) -> tuple[SourceFile, ...]:
        return self.inputs.source_files

    def read_source(self, path: str, start_line: int, end_line: int) -> SourceExcerpt:
        return read_saved_source(self.inputs.source_files, path, start_line, end_line)
