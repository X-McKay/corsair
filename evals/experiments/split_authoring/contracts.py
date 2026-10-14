"""Eval-only draft roles and immutable operator inputs; no execution claims."""

from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, model_validator

from corsair.agents.source.contracts import Contract, Fact, SourceExcerpt, SourceFile, bounded_inventory
from corsair.agents.test_authoring.contracts import AdmissionFinding, PatchedFile
from corsair.agents.test_planning.contracts import EnvironmentEvidence
from corsair.ports.test_runner import MAX_TEST_ID, names_test_in
from evals.test_planning.property_plan import ReadyPropertyPlan

Role = Literal["control", "exploit", "pair"]


class DraftingInput(Contract):
    role: Role
    property_plan: ReadyPropertyPlan[SourceExcerpt]
    source_files: tuple[SourceFile, ...] = Field(max_length=16)
    environment: EnvironmentEvidence
    control_test_id: str = Field(min_length=1, max_length=MAX_TEST_ID)
    control_test_path: str
    exploit_test_id: str = Field(min_length=1, max_length=MAX_TEST_ID)
    exploit_test_path: str
    frozen_control: tuple[PatchedFile, ...] = Field(default=(), max_length=1)

    @model_validator(mode="after")
    def boundaries(self):
        bounded_inventory(self.source_files)
        sources = {source.path: source.content for source in self.source_files}
        for path, identity in ((self.control_test_path, self.control_test_id),
                               (self.exploit_test_path, self.exploit_test_id)):
            if path not in self.environment.approved_test_paths or path in sources:
                raise ValueError("role test paths must be approved new files outside production source")
            if not names_test_in(identity, path):
                raise ValueError("operator-resolved native identity must name its role file")
        if self.control_test_id == self.exploit_test_id:
            raise ValueError("control and exploit native identities must differ")
        if self.role != "exploit" and self.frozen_control:
            raise ValueError("only the exploit role receives a frozen control seed")
        if self.role == "exploit" and (len(self.frozen_control) != 1 or
                                       self.frozen_control[0].path != self.control_test_path):
            raise ValueError("exploit role requires exactly its frozen control artifact")
        bounded_inventory(self.source_files + tuple(SourceFile(path=file.path, content=file.content)
                                                    for file in self.frozen_control))
        for citation in self.property_plan.citations:
            content = sources.get(citation.path)
            if content is None or "\n".join(content.splitlines()[citation.start_line - 1:citation.end_line]) != citation.quote:
                raise ValueError("property-plan citation does not match immutable source")
        return self

    @property
    def owned_paths(self) -> tuple[str, ...]:
        return ((self.control_test_path, self.exploit_test_path) if self.role == "pair" else
                (self.control_test_path,) if self.role == "control" else (self.exploit_test_path,))

    @property
    def layout_supported(self) -> bool:
        return self.control_test_path != self.exploit_test_path

    @property
    def input_digest(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()


class Drafted(Contract):
    status: Literal["drafted"] = "drafted"
    role: Role
    files: tuple[PatchedFile, ...] = Field(min_length=1, max_length=2)
    frozen_control_sha256: str | None = None
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)


class DraftResult(Contract):
    """Model cannot attest files, role, execution or pair admission."""
    status: Literal["drafted"]
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)


class BlockedDraft(Contract):
    status: Literal["blocked"]
    layer: Literal["layout", "source", "admission", "authoring"]
    reason: Fact


class Blocked(BlockedDraft):
    role: Role
    files: tuple[PatchedFile, ...] = ()


DraftOutput = Annotated[DraftResult | BlockedDraft, Field(discriminator="status")]


class RefusedDraftWrite(Contract):
    """Refusal leaves current files unchanged; total native tool budget is operator-owned."""
    status: Literal["refused"] = "refused"
    path: str = Field(max_length=256)
    reason: Fact
    findings: tuple[AdmissionFinding, ...] = Field(min_length=1, max_length=32)
