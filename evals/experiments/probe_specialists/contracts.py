"""Independent specialist projections; no sibling draft, identity or execution outcome."""
from hashlib import sha256
from typing import Annotated, Literal
from pydantic import Field, model_validator
from corsair.agents.source.contracts import Contract, Fact, SourceExcerpt, SourceFile, bounded_inventory
from corsair.agents.test_authoring.contracts import AdmissionFinding, PatchedFile
from corsair.agents.test_planning.contracts import EnvironmentEvidence, Scope
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

    @model_validator(mode='after')
    def boundaries(self):
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


def _project(plan, sources, environment, test_id, test_path, cls, plan_cls, own_input, behavior_key, behavior):
    data = plan.model_dump(exclude={'control_input', 'adversarial_input', 'security_property'})
    data[own_input] = getattr(plan, own_input)
    data[behavior_key] = behavior
    env = EnvironmentEvidence.model_validate(environment.model_dump() | {'approved_test_paths': (test_path,)})
    return cls(property_plan=plan_cls.model_validate(data), source_files=sources,
               environment=env, test_id=test_id, test_path=test_path)

def project_control_input(property_plan, source_files, environment, test_id, test_path, *, ordinary_behavior):
    return _project(property_plan, source_files, environment, test_id, test_path,
                    ControlInput, ControlPropertyPlan, 'control_input', 'ordinary_behavior', ordinary_behavior)

def project_exploit_input(property_plan, source_files, environment, test_id, test_path, *, safety_property):
    return _project(property_plan, source_files, environment, test_id, test_path,
                    ExploitInput, ExploitPropertyPlan, 'adversarial_input', 'safety_property', safety_property)

class DraftResult(Contract):
    status: Literal['drafted']
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

class BlockedDraft(Contract):
    status: Literal['blocked']
    layer: Literal['source', 'admission', 'authoring']
    reason: Fact

DraftOutput = Annotated[DraftResult | BlockedDraft, Field(discriminator='status')]

class Drafted(Contract):
    status: Literal['drafted'] = 'drafted'
    role: Literal['control', 'exploit']
    input_digest: str
    files: tuple[PatchedFile, ...] = Field(min_length=1, max_length=1)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

class Blocked(BlockedDraft):
    role: Literal['control', 'exploit']
    input_digest: str
    files: tuple[PatchedFile, ...] = Field(max_length=1)

class RefusedDraftWrite(Contract):
    status: Literal['refused'] = 'refused'
    path: str = Field(max_length=256)
    reason: Fact
    findings: tuple[AdmissionFinding, ...] = Field(min_length=1, max_length=32)
