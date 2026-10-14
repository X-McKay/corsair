"""Independent specialist projections; no sibling draft, identity or execution outcome."""
from hashlib import sha256
from typing import Annotated, Literal
from pydantic import Field, model_validator
from corsair.agents.source.contracts import Contract, Fact, SourceExcerpt, SourceFile, bounded_inventory, confined_path
from corsair.agents.test_authoring.contracts import AdmissionFinding, PatchedFile
from corsair.agents.test_planning.contracts import EnvironmentEvidence, Scope, PlannedObservation, PlannedWitness
from corsair.ports.test_runner import MAX_TEST_ID, names_test_in

class PropertyBoundary(Contract):
    status: Literal['ready']
    scope: Scope
    condition: Fact
    dependency_limits: Fact
    citations: tuple[SourceExcerpt, ...] = Field(min_length=1, max_length=8)

class ControlPropertyPlan(PropertyBoundary):
    control_input: Fact
    ordinary_behavior: Fact

class ExploitPropertyPlan(PropertyBoundary):
    adversarial_input: Fact
    safety_property: Fact

class SpecialistInput(Contract):
    source_files: tuple[SourceFile, ...] = Field(max_length=16)
    environment: EnvironmentEvidence
    test_id: str = Field(min_length=1, max_length=MAX_TEST_ID)
    test_path: str
    fixture_setup: tuple[Fact, ...] = Field(default=(), max_length=8)
    implementation_call: Fact | None = None
    observation: PlannedObservation | None = None
    witness: PlannedWitness | None = None
    observable_witness: Fact | None = None

    @model_validator(mode='after')
    def boundaries(self):
        confined_path(self.test_path)
        bounded_inventory(self.source_files)
        sources = {source.path: source.content for source in self.source_files}
        if self.environment.approved_test_paths != (self.test_path,) or self.test_path in sources:
            raise ValueError('exactly the own new test path must be approved')
        if not names_test_in(self.test_id, self.test_path):
            raise ValueError('native identity must name the own test file')
        for citation in self.property_plan.citations:
            content = sources.get(citation.path)
            if content is None or '\n'.join(content.splitlines()[citation.start_line-1:citation.end_line]) != citation.quote:
                raise ValueError('property citation does not match immutable source')
        return self

    @property
    def input_digest(self):
        return sha256(self.model_dump_json().encode()).hexdigest()

class ControlInput(SpecialistInput):
    property_plan: ControlPropertyPlan

class ExploitInput(SpecialistInput):
    property_plan: ExploitPropertyPlan


def project_control_input(plan, source_files, environment):
    """Project the own ordinary behavior, identity, file and source anchors from a ready plan."""
    return _project_ready(plan, source_files, environment, 'control')


def project_exploit_input(plan, source_files, environment):
    """Project the own adversarial input and safety property from a ready plan."""
    return _project_ready(plan, source_files, environment, 'exploit')

AssertionLine = Annotated[int, Field(ge=1)]

class DraftResult(Contract):
    assertion_lines: tuple[AssertionLine, ...] = Field(min_length=1, max_length=32)
    status: Literal['drafted']
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

class BlockedDraft(Contract):
    status: Literal['blocked']
    layer: Literal['source', 'admission', 'authoring']
    reason: Fact

DraftOutput = Annotated[DraftResult | BlockedDraft, Field(discriminator='status')]

class Drafted(Contract):
    assertion_lines: tuple[AssertionLine, ...] = Field(min_length=1, max_length=32)
    assertion_anchors: tuple[SourceExcerpt, ...] = Field(min_length=1, max_length=32)
    status: Literal['drafted'] = 'drafted'
    role: Literal['control', 'exploit']
    input_digest: str
    files: tuple[PatchedFile, ...] = Field(min_length=1, max_length=1)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)
    read_anchors: tuple[SourceExcerpt, ...] = Field(min_length=1, max_length=8)

class Blocked(BlockedDraft):
    read_anchors: tuple[SourceExcerpt, ...] = Field(default=(), max_length=8)
    role: Literal['control', 'exploit']
    input_digest: str
    files: tuple[PatchedFile, ...] = Field(max_length=1)

class RefusedDraftWrite(Contract):
    status: Literal['refused'] = 'refused'
    path: str = Field(max_length=256)
    reason: Fact
    findings: tuple[AdmissionFinding, ...] = Field(min_length=1, max_length=32)


def _project_ready(plan, sources, environment, role):
    """Project exactly one production ReadyTestPlan specification and its cited source."""
    from corsair.agents.test_planning.contracts import ReadyTestPlan
    if not isinstance(plan, ReadyTestPlan):
        raise TypeError('production projection requires ReadyTestPlan')
    if plan.control.test_path == plan.security.test_path:
        raise ValueError('independent authors require distinct own test paths')
    if plan.discovery_command != environment.discovery_command:
        raise ValueError('plan discovery command differs from operator environment')
    spec = plan.control if role == 'control' else plan.security
    if spec.test_path not in environment.approved_test_paths:
        raise ValueError('own planned path is not operator approved')
    cls = ControlInput if role == 'control' else ExploitInput
    boundary = dict(status='ready', scope=plan.scope, condition=spec.implementation_call,
        dependency_limits=(spec.observation.controlled_dependency or 'No substituted dependency') if spec.observation else 'Only the admitted witness facility',
        citations=spec.source_references)
    if role == 'control':
        boundary.update(control_input=spec.input, ordinary_behavior=spec.required_behavior)
        property_plan = ControlPropertyPlan(**boundary)
    else:
        boundary.update(adversarial_input=spec.input, safety_property=spec.required_behavior)
        property_plan = ExploitPropertyPlan(**boundary)
    env = EnvironmentEvidence.model_validate(environment.model_dump() | {'approved_test_paths': (spec.test_path,)})
    return cls(property_plan=property_plan, source_files=sources, environment=env,
        test_id=spec.test_id, test_path=spec.test_path, fixture_setup=spec.fixture_setup,
        implementation_call=spec.implementation_call, observation=spec.observation, witness=spec.witness,
        observable_witness=spec.observable_witness)
