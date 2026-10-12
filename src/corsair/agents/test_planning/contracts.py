"""Read-only two-test planning contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from typing import Annotated, Any, Generic, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from ..issue_analysis.identification_contracts import IssueIdentification
from ..source.contracts import (
    Citation, Contract, Fact, SourceExcerpt, SourceFile, SourceReference, bounded_inventory, confined_path,
)

Scope = Literal["component", "application_path"]
Token = Annotated[str, Field(min_length=1, max_length=512)]
Name = Annotated[str, Field(min_length=1, max_length=256)]
Path = Annotated[str, Field(min_length=1, max_length=256)]
CommandTokens = Annotated[tuple[Token, ...], Field(min_length=1, max_length=32)]


class BaselineTest(Contract):
    """An existing test the operator discovered and executed in the prepared environment."""
    test_id: Name
    path: Path

    _path = field_validator("path")(confined_path)


class EnvironmentEvidence(Contract):
    """Operator-supplied today; the future environment stage must produce exactly this or supersede it."""
    language: Name
    runtime: Name
    framework: Name
    discovery_command: CommandTokens
    approved_test_paths: tuple[Path, ...] = Field(min_length=1, max_length=8)
    baseline_test: BaselineTest | None
    scratch_location: Fact
    observation_facilities: tuple[Fact, ...] = Field(max_length=8, description="Facilities the prepared environment offers for observing an effect")

    @field_validator("approved_test_paths")
    @classmethod
    def confined_unique_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for path in value:
            confined_path(path)
        if len(set(value)) != len(value):
            raise ValueError("duplicate approved test path")
        return value


class TestPlanningInput(Contract):
    __test__ = False  # not a pytest class

    scope: Scope
    identification: IssueIdentification
    source_files: tuple[SourceFile, ...] = Field(max_length=16)
    environment: EnvironmentEvidence

    @model_validator(mode="after")
    def admitted_handoff(self) -> "TestPlanningInput":
        # An abstention ends the investigation with its reason; it is never planned around.
        if self.identification.status != "ready":
            raise ValueError("test planning requires a ready issue identification")
        if self.identification.scope != self.scope:
            raise ValueError("identification scope must equal the authorized planning scope")
        bounded_inventory(self.source_files)
        baseline = self.environment.baseline_test
        if baseline is not None and baseline.path not in {source.path for source in self.source_files}:
            raise ValueError("the baseline test file must be in the saved inventory")
        return self

    @property
    def input_digest(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class TestSpecification(Contract, Generic[Citation]):
    __test__ = False

    test_id: Name = Field(description="Native test identifier the authored test must have")
    test_path: Path = Field(description="One of the approved test paths")
    fixture_setup: tuple[Fact, ...] = Field(min_length=1, max_length=8, description="Explicit preconditions and resources, created inside the scratch location")
    implementation_call: Fact = Field(description="The real implementation call, naming the identified target")
    input: Fact
    required_behavior: Fact = Field(description="Specific required behavior; for security, a specific rejection or absence of effect, never an arbitrary exception")
    observable_witness: Fact = Field(description="What an available facility observes, separating the application observation from any sandbox observation")
    source_references: tuple[Citation, ...] = Field(min_length=1, max_length=8)

    _path = field_validator("test_path")(confined_path)


def _environment(info: ValidationInfo) -> EnvironmentEvidence | None:
    context: Any = info.context
    return context.environment if isinstance(context, TestPlanningInput) else None


class _ReadyPlan(Contract, Generic[Citation]):
    status: Literal["ready"]
    scope: Scope
    control: TestSpecification[Citation] = Field(description="Benign control through the real implementation path")
    security: TestSpecification[Citation] = Field(description="Security regression for the reported concern")
    discovery_command: CommandTokens = Field(description="Exactly the supplied native discovery command tokens")
    evidence_requirements: tuple[Fact, ...] = Field(min_length=1, max_length=8)
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=16)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def two_distinct_admitted_tests(self, info: ValidationInfo) -> "_ReadyPlan[Citation]":
        if self.control.test_id == self.security.test_id:
            raise ValueError("control and security tests need distinct test ids")
        environment = _environment(info)
        if environment is not None:
            for spec in (self.control, self.security):
                if spec.test_path not in environment.approved_test_paths:
                    raise ValueError(f"test path {spec.test_path} is not an approved test path")
            if self.discovery_command != environment.discovery_command:
                raise ValueError("discovery command tokens must equal the supplied environment command")
        return self


class _UnsupportedPlan(Contract, Generic[Citation]):
    status: Literal["unsupported"]
    scope: Scope
    missing_capability: Fact = Field(description="The observation or condition the supplied environment or authorized scope cannot support")
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)
    citations: tuple[Citation, ...] = Field(default=(), max_length=16)


class ReadyTestPlanDraft(_ReadyPlan[SourceReference]):
    pass


class UnsupportedTestPlanDraft(_UnsupportedPlan[SourceReference]):
    pass


class ReadyTestPlan(_ReadyPlan[SourceExcerpt]):
    pass


class UnsupportedTestPlan(_UnsupportedPlan[SourceExcerpt]):
    pass


TestPlanDraft = Annotated[ReadyTestPlanDraft | UnsupportedTestPlanDraft, Field(discriminator="status")]
TestPlan = Annotated[ReadyTestPlan | UnsupportedTestPlan, Field(discriminator="status")]
