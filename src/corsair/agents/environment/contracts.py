"""Environment stage contracts; no model, workflow or execution SDK types.

The model proposes a recipe and cites the manifest lines it follows; trusted
code admits it only against commands actually observed in the current run and
attaches the image, scratch location and command receipts. Dependency closure
digests are never model-authored: the deterministic inventory node records them.
"""

from typing import Annotated, Generic, Literal, Union

from pydantic import Field, field_validator, model_validator

from corsair.core.blockers import Blocker

from corsair.agents.issue_analysis.contracts import (Citation, Contract, Fact, SourceExcerpt, SourceFile,
                                                     SourceReference, confined_path)

Token = Annotated[str, Field(min_length=1, max_length=1024, pattern=r"^[^\x00]+$")]
Command = Annotated[tuple[Token, ...], Field(min_length=1, max_length=64)]
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
Layer = Literal["dependency", "registry", "tls", "toolchain_version", "build", "discovery", "sandbox", "unknown"]


class Toolchain(Contract):
    toolchain_id: Identifier
    image: str = Field(pattern=r"^[^@\s]+@sha256:[0-9a-f]{64}$", max_length=512)
    language: Literal["python", "java", "javascript", "ruby", "perl"]
    runtime: str = Field(min_length=1, max_length=128, description="Native runtime identity, e.g. CPython 3.12 or Temurin 17")
    tools: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...] = Field(max_length=16)


class SmokeTest(Contract):
    """SPEC-0071: an operator test file trusted code wrote into the checkout; never the project's own code."""
    framework: Identifier
    path: str = Field(min_length=1, max_length=256)
    test_id: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=4096)

    _path = field_validator("path")(confined_path)


class EnvironmentInput(Contract):
    """Manifests, CI workflows and setup documentation only; never labels or oracles."""
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_private: bool
    source_files: tuple[SourceFile, ...] = Field(min_length=1, max_length=32)
    toolchains: tuple[Toolchain, ...] = Field(min_length=1, max_length=8)
    policy_profile: Identifier = Field(description="Read-only identity of the operator policy profile")
    smoke_tests: tuple[SmokeTest, ...] = Field(default=(), max_length=4, description=(
        "Operator smoke test files already written into the checkout; a baseline only when no project test runs"))

    @model_validator(mode="after")
    def bounded_unique(self) -> "EnvironmentInput":
        if len({s.path for s in self.source_files}) != len(self.source_files):
            raise ValueError("duplicate source path")
        if sum(len(s.content.encode("utf-8")) for s in self.source_files) > 131072:
            raise ValueError("environment source exceeds 131072 bytes")
        if len({t.toolchain_id for t in self.toolchains}) != len(self.toolchains):
            raise ValueError("duplicate toolchain id")
        if len({t.framework for t in self.smoke_tests}) != len(self.smoke_tests):
            raise ValueError("duplicate smoke test framework")
        if {t.path for t in self.smoke_tests} & {s.path for s in self.source_files}:
            raise ValueError("a smoke test path is a saved source file")
        return self


class RecipeStep(Contract, Generic[Citation]):
    phase: Literal["dependency", "build"] = Field(description="dependency: registry access during setup only; build: no network")
    command: Command
    source: Citation = Field(description="Manifest, CI or documentation lines this step follows")


class CommandRecord(Contract):
    """Trusted observation of one run_setup_command call; output stays in the ledger."""
    run_id: int = Field(ge=1)
    command: Command
    operation: str
    delivery: Literal["not_dispatched", "unknown", "acknowledged"]
    completion: Literal["unknown", "terminal_observed"]
    exit_code: int | None
    failure_layer: str | None
    execution_error: str | None = Field(description="Port-level failure (journal, cleanup or transport); such a run never counts as successful")
    stdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stderr_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    elapsed_seconds: float = Field(ge=0)


class _Ready(Contract, Generic[Citation]):
    status: Literal["ready"]
    toolchain_id: Identifier
    recipe: tuple[RecipeStep[Citation], ...] = Field(max_length=16)
    build_command: Command
    discovery_command: Command
    framework: str = Field(min_length=1, max_length=128, description="Native test framework identity, e.g. pytest or JUnit 5")
    baseline_test_id: str = Field(min_length=1, max_length=512, description="Test id exactly as printed by the discovery command")
    baseline_test_path: str = Field(min_length=1, max_length=256, description="Saved repository path of the baseline test file")
    baseline_test_command: Command = Field(description="Runs exactly the one existing baseline test")
    approved_test_paths: tuple[Annotated[str, Field(min_length=1, max_length=256)], ...] = Field(min_length=1, max_length=8)

    _baseline_path = field_validator("baseline_test_path")(confined_path)

    @field_validator("approved_test_paths")
    @classmethod
    def confined(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(paths)) != len(paths):
            raise ValueError("duplicate approved test path")
        return tuple(confined_path(p) for p in paths)


class _Blocked(Contract, Generic[Citation]):
    status: Literal["blocked"]
    layer: Layer
    evidence: Fact = Field(description="Exact excerpt of a cited run's output or execution error; empty run_ids only after a halt or budget exhaustion")
    run_ids: tuple[int, ...] = Field(max_length=16, description="run_setup_command run_ids showing the failure")
    citations: tuple[Citation, ...] = Field(max_length=8)


class _Unsupported(Contract, Generic[Citation]):
    status: Literal["unsupported"]
    requirement: Fact = Field(description="The requirement the admitted toolchains or policy cannot meet")
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=8)


class ReadyEnvironmentDraft(_Ready[SourceReference]):
    pass


class BlockedEnvironmentDraft(_Blocked[SourceReference]):
    pass


class UnsupportedEnvironmentDraft(_Unsupported[SourceReference]):
    pass


class ReadyEnvironment(_Ready[SourceExcerpt]):
    toolchain_image: str
    language: str
    runtime: str
    baseline_outcome: Literal["passed"]
    baseline_basis: Literal["project_test", "operator_smoke"] = Field(description="Trusted: whether the baseline is a project test or the operator smoke test")
    scratch_location: str
    receipts: tuple[CommandRecord, ...] = Field(min_length=1)


class BlockedEnvironment(_Blocked[SourceExcerpt]):
    diagnostics: tuple[Blocker, ...] = ()
    receipts: tuple[CommandRecord, ...]


class UnsupportedEnvironment(_Unsupported[SourceExcerpt]):
    receipts: tuple[CommandRecord, ...]


EnvironmentDraft = Annotated[Union[ReadyEnvironmentDraft, BlockedEnvironmentDraft, UnsupportedEnvironmentDraft],
                             Field(discriminator="status")]
EnvironmentResult = Annotated[Union[ReadyEnvironment, BlockedEnvironment, UnsupportedEnvironment],
                              Field(discriminator="status")]
