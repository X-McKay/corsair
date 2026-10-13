"""Read-only two-test planning contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from pathlib import PurePosixPath
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
# Same identifier shape the deterministic disposition gates (SPEC-0027) compare against.
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
CommandTokens = Annotated[tuple[Token, ...], Field(min_length=1, max_length=32)]


# SPEC-0040: effect kinds an operator facility can record; added only with a recorder for them.
WitnessEffect = Literal["file_open", "process_start", "socket_connect"]
Subject = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_.:/-]+$")]


class WitnessFacility(Contract):
    """An operator-owned recorder of one effect kind during a test's call."""
    id: Identifier
    kind: WitnessEffect
    description: Fact


class PlannedWitness(Contract):
    """What a listed facility must record (occurs) or must not record (absent) for one subject during the call."""
    facility: Identifier = Field(description="id of one listed witness facility")
    effect: WitnessEffect = Field(description="The listed facility's kind")
    subject: Subject = Field(description="For file_open, a path relative to the scratch location (the sentinel file); for process_start or socket_connect, a token that appears in the recorded arguments or address")
    expectation: Literal["occurs", "absent"] = Field(description="occurs for the control, absent for the security test")


def scratch_relative(subject: str) -> str:
    path = PurePosixPath(subject)
    if path.is_absolute() or ".." in path.parts or subject.startswith("~") or path == PurePosixPath("."):
        raise ValueError(f"file_open subject {subject!r} must be a path inside the scratch location, relative to it")
    # One spelling per file, so distinct subjects are distinct files ("./a", "a//b", "a/./b" and "a/" are refused).
    if str(path) != subject:
        raise ValueError(f"file_open subject {subject!r} must be written canonically as {str(path)!r}")
    return subject


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
    witness_facilities: tuple[WitnessFacility, ...] = Field(default=(), max_length=8, description="Operator recorders a planned witness must name")

    @field_validator("witness_facilities")
    @classmethod
    def unique_facility_ids(cls, value: tuple[WitnessFacility, ...]) -> tuple[WitnessFacility, ...]:
        if len({facility.id for facility in value}) != len(value):
            raise ValueError("duplicate witness facility id")
        return value

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
        # A planned test file must never replace saved source (application or existing test).
        overlap = set(self.environment.approved_test_paths) & {source.path for source in self.source_files}
        if overlap:
            raise ValueError(f"approved test paths overlap saved source: {sorted(overlap)}")
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
    observable_witness: Fact = Field(description="Explanation of the witness, separating the application observation from any sandbox observation; never read by a gate")
    witness: PlannedWitness
    source_references: tuple[Citation, ...] = Field(min_length=1, max_length=8)

    _path = field_validator("test_path")(confined_path)


class SecurityExpectation(Contract):
    """Typed expectations for the security test, so later gates never parse model prose."""
    failure_type: Identifier = Field(description="Native exception type reported when the security assertion fails, for example AssertionError")
    safe_behavior: Identifier = Field(description="Identity of the specific required safe behavior, for example the rejection exception type ValueError")


def _environment(info: ValidationInfo) -> EnvironmentEvidence | None:
    context: Any = info.context
    return context.environment if isinstance(context, TestPlanningInput) else None


class _ReadyPlan(Contract, Generic[Citation]):
    status: Literal["ready"]
    scope: Scope
    control: TestSpecification[Citation] = Field(description="Benign control through the real implementation path")
    security: TestSpecification[Citation] = Field(description="Security regression for the reported concern")
    security_expectation: SecurityExpectation
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
            # SPEC-0022 precondition, admitted in code: without an executed baseline no native test is known to run.
            if environment.baseline_test is None:
                raise ValueError("environment.baseline_test is null, so no native test is known to run: return unsupported")
            for spec in (self.control, self.security):
                if spec.test_path not in environment.approved_test_paths:
                    raise ValueError(f"test path {spec.test_path} is not an approved test path")
            if self.discovery_command != environment.discovery_command:
                raise ValueError("discovery command tokens must equal the supplied environment command")
            planned_witnesses(self, environment)
        return self


def planned_witnesses(plan: "_ReadyPlan", environment: EnvironmentEvidence) -> None:
    """SPEC-0040 admission: typed witnesses against the operator's facilities, checked without reading prose."""
    facilities = {facility.id: facility for facility in environment.witness_facilities}
    for name, spec, expected in (("control", plan.control, "occurs"), ("security", plan.security, "absent")):
        witness = spec.witness
        facility = facilities.get(witness.facility)
        if facility is None:
            listed = ", ".join(facilities) or "none"
            raise ValueError(f"{name} witness facility {witness.facility!r} is not listed (listed: {listed}); "
                             "if no listed facility records the sensitive operation, return an unsupported plan")
        if witness.effect != facility.kind:
            raise ValueError(f"{name} witness effect {witness.effect} differs from facility {facility.id} kind {facility.kind}")
        if witness.expectation != expected:
            raise ValueError(f"the {name} witness expectation must be {expected}")
        if witness.effect == "file_open":
            scratch_relative(witness.subject)
    control, security = plan.control.witness, plan.security.witness
    if (control.effect, control.subject) == (security.effect, security.subject):
        raise ValueError("control and security witnesses must name different subjects")
    token = PurePosixPath(security.subject).name if security.effect == "file_open" else security.subject
    if not any(token in text for text in (plan.security.input, *plan.security.fixture_setup)):
        raise ValueError(f"the security input or fixture setup must name the witness subject {token!r} the adversarial input aims at")
    safe = plan.security_expectation.safe_behavior
    if safe != f"no_{security.effect}" and safe not in plan.security.required_behavior:
        raise ValueError(f"safe_behavior must be no_{security.effect} or an exception type named in the security required_behavior")


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
