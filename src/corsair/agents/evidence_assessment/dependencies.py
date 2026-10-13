"""Injected frozen evidence for one assessment; bounded reads over its admitted items only."""

from dataclasses import dataclass

from .contracts import WINDOW_LINES, AssessmentInput, ValidityInput, EvidenceExcerpt


@dataclass(frozen=True)
class AssessmentDependencies:
    inputs: AssessmentInput | ValidityInput

    def read_evidence(self, item_id: str, start_line: int, end_line: int) -> EvidenceExcerpt:
        item = next((item for item in self.inputs.items if item.item_id == item_id), None)
        if item is None:
            raise ValueError("evidence item is absent from this assessment")
        lines = item.content.splitlines()
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            raise ValueError("evidence line range is absent from the item")
        if end_line - start_line + 1 > WINDOW_LINES:
            raise ValueError(f"evidence read exceeds {WINDOW_LINES} lines")
        return EvidenceExcerpt(item_id=item_id, start_line=start_line, end_line=end_line,
                               quote="\n".join(lines[start_line - 1:end_line]))
