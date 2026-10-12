"""Two-test authoring contracts; no model, workflow or execution SDK types."""

from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, model_validator

from corsair.ports.test_runner import MAX_PATCH_FILE_BYTES, MAX_PATCH_FILES, MAX_TEST_ID, TEST_ID

from ..source.contracts import Contract, Fact, SourceFile, bounded_inventory, confined_path
from ..test_planning.contracts import EnvironmentEvidence, ReadyTestPlan

TestId = Annotated[str, Field(min_length=1, max_length=MAX_TEST_ID, pattern=TEST_ID.pattern)]
Layer = Literal["compile", "discovery", "dependency", "fixture", "sandbox", "unknown"]
Excerpt = Annotated[str, Field(max_length=4096)]


class TestAuthoringInput(Contract):
    """A ready plan, the saved inventory it was planned over and the same environment evidence."""
    __test__ = False

    plan: ReadyTestPlan
    source_files: tuple[SourceFile, ...] = Field(max_length=16)
    environment: EnvironmentEvidence

    @model_validator(mode="after")
    def admitted_handoff(self) -> "TestAuthoringInput":
        bounded_inventory(self.source_files)
        if self.plan.discovery_command != self.environment.discovery_command:
            raise ValueError("plan discovery command must equal the environment command")
        for spec in (self.plan.control, self.plan.security):
            if spec.test_path not in self.environment.approved_test_paths:
                raise ValueError(f"planned test path {spec.test_path} is not approved")
            if not spec.test_id.startswith(spec.test_path + "::"):
                raise ValueError(f"planned test id {spec.test_id} must be a native node id in {spec.test_path}")
            if len(spec.test_id) > MAX_TEST_ID or not TEST_ID.fullmatch(spec.test_id):
                raise ValueError(f"planned test id {spec.test_id} is not a supported native node id")
        contents = {source.path: source.content.splitlines() for source in self.source_files}
        for excerpt in (*self.plan.citations, *self.plan.control.source_references, *self.plan.security.source_references):
            # The plan must have been made over exactly this inventory, not same-named files of another revision.
            lines = contents.get(excerpt.path)
            if lines is None or excerpt.end_line > len(lines) or \
                    "\n".join(lines[excerpt.start_line - 1:excerpt.end_line]) != excerpt.quote:
                raise ValueError(f"plan excerpt {excerpt.path}:{excerpt.start_line}-{excerpt.end_line} does not match the saved source")
        sources = set(contents)
        if sources & set(self.environment.approved_test_paths):
            # A new test file must not replace saved source; editing existing tests is a separate decision.
            raise ValueError("approved test paths must not overwrite saved source files")
        return self

    @property
    def input_digest(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class WrittenFile(Contract):
    """What write_test_file returns; the content stays in the model's own call arguments."""
    path: str = Field(min_length=1, max_length=256)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0, le=MAX_PATCH_FILE_BYTES)


class DevelopmentOutcome(Contract):
    outcome: Literal["passed", "failed", "error", "skipped"]
    failure_type: str | None = Field(default=None, max_length=256)
    failure_path: str | None = Field(default=None, max_length=256)
    failure_line: int | None = Field(default=None, ge=1)
    message: Excerpt = ""


class DevelopmentRun(Contract):
    """One capped development run as the author sees it; the security outcome is withheld by default."""
    run: int = Field(ge=1)
    operation: str
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["discovered", "collection_error", "workspace_failure", "execution_failure", "report_failure",
                    "not_run"]
    discovered_test_ids: tuple[str, ...] = Field(max_length=64)
    errors: Excerpt
    control: DevelopmentOutcome | None
    security: DevelopmentOutcome | Literal["withheld"] | None
    run_command: tuple[str, ...] = Field(max_length=64)
    cleanup: Literal["not_required", "confirmed", "unconfirmed"]


class PatchedFile(Contract):
    path: str = Field(min_length=1, max_length=256)
    content: str = Field(max_length=MAX_PATCH_FILE_BYTES)


class AuthoredPatchDraft(Contract):
    """Model-facing: trusted code assembles files, ids and runs from this run's tool history."""
    status: Literal["patch"]
    security_assertion_lines: tuple[Annotated[int, Field(ge=1)], ...] = Field(
        min_length=1, max_length=32,
        description="Lines of the assert statements in the security test that check the planned required behavior; not fixture preconditions")
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)


class BlockedAuthoringDraft(Contract):
    status: Literal["blocked"]
    layer: Layer
    reason: Fact


AuthoringDraft = Annotated[AuthoredPatchDraft | BlockedAuthoringDraft, Field(discriminator="status")]


class TestPatch(Contract):
    """Exactly the written test files, confined to approved paths, last run after the last write."""
    __test__ = False

    status: Literal["patch"]
    files: tuple[PatchedFile, ...] = Field(min_length=1, max_length=MAX_PATCH_FILES)
    control_test_id: TestId
    security_test_id: TestId
    discovery_command: tuple[str, ...] = Field(min_length=1, max_length=32)
    run_command: tuple[str, ...] = Field(min_length=1, max_length=64)
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    security_assertion_lines: tuple[Annotated[int, Field(ge=1)], ...] = Field(
        min_length=1, max_length=32, description="Planned security assertion lines in the frozen patch, each verified by trusted code to be an assertion of the security test function")
    dev_runs: tuple[DevelopmentRun, ...] = Field(min_length=1, max_length=8)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def confined_distinct(self) -> "TestPatch":
        paths = [item.path for item in self.files]
        for path in paths:
            confined_path(path)
        if len(set(paths)) != len(paths) or self.control_test_id == self.security_test_id:
            raise ValueError("distinct files and test ids required")
        # Budget-refused calls stay in the audit history; the patch must match the last executed run.
        executed = [run for run in self.dev_runs if run.status != "not_run"]
        if not executed or executed[-1].patch_sha256 != self.patch_sha256:
            raise ValueError("the last executed development run must cover the final patch")
        return self


class BlockedAuthoring(Contract):
    status: Literal["blocked"]
    layer: Layer
    reason: Fact
    files: tuple[PatchedFile, ...] = Field(max_length=MAX_PATCH_FILES, description="Last written files, retained for review")
    dev_runs: tuple[DevelopmentRun, ...] = Field(max_length=8)


AuthoringResult = Annotated[TestPatch | BlockedAuthoring, Field(discriminator="status")]
