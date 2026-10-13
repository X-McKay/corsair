"""SPEC-0042 runtime requirement and selection contracts; no SDK or vendor types.

A requirement is derived only from a project's own build files. Each component says which versions the
project allows (`allowed`, rendered as a version set), which lines declared it, and which declarations
were seen but not understood. Selection against the operator's runtime matrix is a typed union: an
admitted image, an unsupported requirement naming what is missing, or an undetermined requirement.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from corsair.agents.environment.contracts import SmokeTest, Toolchain
from corsair.core.blockers import Blocker

Language = Literal['python', 'java', 'javascript', 'ruby', 'perl']
Kind = Literal['runtime', 'build_tool', 'test_framework']
Strength = Literal['constraint', 'tested', 'pinned']
# `image`: the sandbox image must provide this component (runtime, Maven, npm, Bundler, make).
# `registry`: resolved from the project's own dependencies during setup (SPEC-0026). Only test frameworks among
# these are matched, against the runner support table; other registry components are recorded for setup.
Provider = Literal['image', 'registry']
Text = Annotated[str, Field(max_length=240)]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Evidence(_Frozen):
    path: str = Field(max_length=512)
    line: int = Field(ge=1)
    text: Text
    strength: Strength
    source: str = Field(max_length=32, description='Declaration kind, e.g. requires-python, ci, tox, classifier, compiler-target')
    declares: str = Field(max_length=240, description='The version set this line declares')


class Unparsed(_Frozen):
    path: str = Field(max_length=512)
    line: int = Field(ge=1)
    text: Text
    strength: Strength = Field(description="What the line would have declared; a 'tested' alternative (a CI PyPy or dev entry) "
                                           "can be ignored, a constraint or pin cannot")
    reason: Text


class Component(_Frozen):
    kind: Kind
    name: str = Field(max_length=64)
    provider: Provider
    allowed: str = Field(max_length=512, description="Combined version set; '*' when nothing was declared")
    preferred: str | None = Field(max_length=64, description='Version to provision when no image matches')
    declared: bool
    conflict: bool = Field(description='Declarations admit no common version')
    evidence: tuple[Evidence, ...] = Field(max_length=64)
    unparsed: tuple[Unparsed, ...] = Field(max_length=64)


class RuntimeRequirement(_Frozen):
    language: Language
    root: str = Field(max_length=512, description="Project directory within the tree; '.' is the repository root")
    components: tuple[Component, ...] = Field(max_length=32)
    files: tuple[str, ...] = Field(max_length=4096, description='Build files read')
    unresolved: tuple[Text, ...] = Field(max_length=64, description='Inputs the detector needed but did not have')

    def component(self, kind: Kind, name: str | None = None) -> tuple[Component, ...]:
        return tuple(c for c in self.components if c.kind == kind and (name is None or c.name == name))


class AxisCheck(_Frozen):
    kind: Kind
    name: str
    allowed: str
    provided: str | None
    satisfied: bool


class Rejection(_Frozen):
    image_id: str
    unmet: tuple[AxisCheck, ...]


class Need(_Frozen):
    kind: Kind
    name: str
    allowed: str
    preferred: str | None


class Supported(_Frozen):
    status: Literal['supported']
    image_id: str
    image: str = Field(description='Base image reference with digest')
    checks: tuple[AxisCheck, ...]
    evidence: Literal['live', 'image-only'] = Field(description='Weakest evidence of the selected image row and the '
                                                                 'framework rows that satisfied it; only live is qualified')
    runtime_basis: Literal['declared', 'inferred'] = Field(
        default='declared', description="'inferred': the build files declare no runtime version, so the runtime range came "
                                        "from operator inference rows for the declared test framework (SPEC-0069)")
    inferred_from: tuple[Text, ...] = Field(default=(), max_length=16,
                                            description='Each inference row used: framework versions, runtime range, source')


class Unsupported(_Frozen):
    status: Literal['unsupported']
    needs: tuple[Need, ...] = Field(min_length=1, description='Components no qualified image provides')
    rejected: tuple[Rejection, ...]


class Undetermined(_Frozen):
    status: Literal['undetermined']
    missing: tuple[Text, ...] = Field(min_length=1)


Selection = Annotated[Union[Supported, Unsupported, Undetermined], Field(discriminator='status')]


# Bound on the encoded JSON of `RuntimeInputs` (paths, keys and base64 bytes included), not on raw content: the
# whole chain request must stay under Temporal's default 2 MB payload limit.
MAX_INPUT_BYTES = 1 << 20


class RuntimeInputs(_Frozen):
    """SPEC-0060 operator input: the baseline revision's build files, never shown to an agent. Bytes cross a
    Temporal payload as base64 so non-UTF-8 content survives; `omitted` names build files left out to keep the encoded
    inputs within `MAX_INPUT_BYTES`, which selection reports as unresolved (so undetermined) in every mode."""
    model_config = ConfigDict(extra='forbid', frozen=True, ser_json_bytes='base64', val_json_bytes='base64')
    files: dict[str, bytes] = Field(description='Project-relative path to bytes from the captured snapshot')
    language: Language | None = None
    parents: dict[str, bytes] = Field(default_factory=dict, description='Operator-supplied Maven parent POMs')
    root: str = Field(default='.', max_length=512)
    omitted: tuple[str, ...] = Field(default=(), max_length=64, description='Build files left out for size')

    @model_validator(mode='after')
    def bounded(self) -> 'RuntimeInputs':
        if len(self.__pydantic_serializer__.to_json(self)) > MAX_INPUT_BYTES:
            raise ValueError(f'runtime inputs encode to over {MAX_INPUT_BYTES} bytes; omit the largest build files by name')
        return self


class RuntimeOutcome(_Frozen):
    """SPEC-0060: the chain's runtime stage. Only `supported` continues; every other status ends the run."""
    status: Literal['supported', 'unsupported', 'undetermined', 'not_prepared']
    requirement: RuntimeRequirement | None
    detection: Text | None = Field(description='Why no requirement was derived, when none was')
    selection: Selection | None
    image: str | None = Field(pattern=r'^[^@\s]+@sha256:[0-9a-f]{64}$', max_length=512,
                              description="The selected row's prepared image on this node")
    reason: str = Field(max_length=2048)
    diagnostic: Blocker | None = Field(default=None, description='Operator or developer guidance; absent only when supported')
    toolchain: Toolchain | None = Field(default=None, description="The selected row as the environment agent's only toolchain (SPEC-0068)")
    smoke_tests: tuple[SmokeTest, ...] = Field(default=(), max_length=4, description="SPEC-0071: the admitted framework rows' smoke templates")

    @model_validator(mode='after')
    def consistent(self) -> 'RuntimeOutcome':
        supported = isinstance(self.selection, Supported)
        if (self.status == 'supported') != (self.image is not None) or (self.status == 'supported') != (self.diagnostic is None) or \
                (self.toolchain is not None and (self.status != 'supported' or self.toolchain.image != self.image)) or \
                (self.smoke_tests and self.status != 'supported') or \
                (self.status in ('supported', 'not_prepared')) != supported or (self.requirement is None) == (self.detection is None):
            raise ValueError('runtime outcome fields disagree with its status')
        return self
