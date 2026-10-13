"""SPEC-0042 runtime requirement and selection contracts; no SDK or vendor types.

A requirement is derived only from a project's own build files. Each component says which versions the
project allows (`allowed`, rendered as a version set), which lines declared it, and which declarations
were seen but not understood. Selection against the operator's runtime matrix is a typed union: an
admitted image, an unsupported requirement naming what is missing, or an undetermined requirement.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

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


class Unsupported(_Frozen):
    status: Literal['unsupported']
    needs: tuple[Need, ...] = Field(min_length=1, description='Components no qualified image provides')
    rejected: tuple[Rejection, ...]


class Undetermined(_Frozen):
    status: Literal['undetermined']
    missing: tuple[Text, ...] = Field(min_length=1)


Selection = Annotated[Union[Supported, Unsupported, Undetermined], Field(discriminator='status')]
