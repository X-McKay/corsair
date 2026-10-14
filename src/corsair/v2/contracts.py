"""Corsair v2 stage contracts (redesign doc, sections 5 and 13).

Every stage is a function of (typed input, config digest, input content hashes). These models are the only
types that cross a stage boundary; none of them imports a vendor SDK object. Nothing here names a language,
framework, CWE, corpus case or repository: language knowledge lives in matrix rows and framework skills.

Large content travels as an ``ArtifactRef``; small text (a probe source, a brief) travels inline.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, model_validator, ConfigDict, Field, field_validator

CONTRACT_VERSION = "corsair-v2/1"

def _safe_path(value: str) -> str:
    parts = value.split("/")
    if value.startswith("/") or "\0" in value or ".." in parts or "" in parts:
        raise ValueError("a relative POSIX path inside the tree is required")
    return value


SafePath = Annotated[str, Field(min_length=1, max_length=512), AfterValidator(_safe_path)]
"""A relative POSIX path inside a source tree, never absolute and never climbing with ``..``."""


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactRef(Frozen):
    """Content-addressed bytes in the run's artifact store."""

    uri: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


# --- 1. Intake (code) ---------------------------------------------------------------------------------------------


class Finding(Frozen):
    """What a reporter or scanner claims. Untrusted text: agents read it as data, never as instructions."""

    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    file_path: SafePath | None = None
    start_line: int | None = Field(default=None, ge=1)
    symbol: str | None = Field(default=None, max_length=256)
    cwe: str | None = Field(default=None, pattern=r"^CWE-\d{1,5}$")


class Revision(Frozen):
    """A source tree the chain may investigate: a local directory snapshot or a git commit, plus its digest."""

    source: str = Field(min_length=1, max_length=1024, description="Host path of the tree or git checkout")
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Digest over the tree's paths, modes and bytes")


class Case(Frozen):
    """One reported issue against an exact revision, and optionally its fix revision."""

    contract: Literal["corsair-v2/1"] = CONTRACT_VERSION
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,255}$", description="Opaque to agents")
    finding: Finding
    revision: Revision
    fixed_revision: Revision | None = None


# --- 2. Select (code) -------------------------------------------------------------------------------------------


class ExitClass(StrEnum):
    PASS = "pass"
    TEST_FAILED = "test_failed"
    NO_TESTS = "no_tests"
    HARNESS_ERROR = "harness_error"
    UNKNOWN = "unknown"


class Runtime(Frozen):
    """One matrix row as selected for a case: everything trusted code needs to run one test, as data."""

    row_id: str = Field(min_length=1, max_length=128)
    image: str = Field(min_length=1, max_length=512, description="Image reference, digest-pinned where possible")
    framework: str = Field(min_length=1, max_length=64)
    skill: str = Field(min_length=1, max_length=64, description="Framework guidance skill name")
    run_template: tuple[str, ...] = Field(min_length=1, description="argv with {file} {name} {class} placeholders")
    exit_codes: dict[int, ExitClass] = Field(min_length=1, description="Exit code to class; unlisted is unknown")
    test_dir: str = Field(default="", max_length=256, description="Where probe files go, relative to the root")
    evidence: Literal["image-only", "live", "canary-only"]
    syntax_check: tuple[str, ...] | None = Field(
        default=None, description="argv template (same placeholders) that checks the probe file without running "
                                  "application code; its output may go back to the author (D3). None: no check")


# --- 3. Build (Builder agent, then trusted replay) --------------------------------------------------------------


class RecipeFile(Frozen):
    """A small file the Builder added (a smoke test when the project has none); replay writes it before setup."""

    path: SafePath
    content: str = Field(max_length=16_000)


class Recipe(Frozen):
    """A setup the Builder found, which trusted code replays in a fresh container before anything relies on it."""

    files: tuple[RecipeFile, ...] = Field(default=(), max_length=4, description="New files, written before setup")
    setup: tuple[tuple[str, ...], ...] = Field(default=(), max_length=32, description="argv lists, run in order")
    network_during_setup: bool = False
    baseline_test: tuple[str, ...] = Field(default=(), description="argv of one existing native test, or smoke")
    notes: str = Field(default="", max_length=4_000)
    blocked: str = Field(default="", max_length=2_000,
                         description="Why no recipe is possible (e.g. a dependency the image cannot install); empty "
                                     "for a real recipe")

    @model_validator(mode="after")
    def _baseline_or_reason(self) -> "Recipe":
        if not self.blocked and not self.baseline_test:
            raise ValueError("a recipe needs a baseline_test, or a blocked reason")
        return self


class BuildResult(Frozen):
    recipe: Recipe | None
    replayed: bool
    baseline_exit_code: int | None = None
    log: ArtifactRef | None = None
    reason: str = Field(default="", max_length=2_000)
    cleanup_confirmed: bool | None = Field(default=None, description="False is cleanup_unconfirmed; None unknown")


class Environment(Frozen):
    """A replayed, ready-to-test environment: an image with the revision and its dependencies installed.

    Trusted code builds it from the Recipe in a fresh container (never the one an agent typed into) and keys it by
    (runtime row, recipe, revision tree), which is the exact-environment cache level of amendment A3.
    """

    image: str = Field(min_length=1, max_length=512, description="Local image tag holding the prepared tree")
    workdir: str = Field(default="/work", pattern=r"^/[A-Za-z0-9._/-]*$")
    runtime_row: str
    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


# --- 4. Investigate (Investigator agent) ------------------------------------------------------------------------


class Citation(Frozen):
    path: SafePath
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(default="", max_length=2_000, description="Exact text at those lines, checked by code")


class ProbeBrief(Frozen):
    """Everything one Prober sees. The control and exploit briefs never reference each other."""

    role: Literal["control", "exploit"]
    test_file: SafePath
    test_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    target: str = Field(min_length=1, max_length=512, description="The production callable or entry point")
    seam: str = Field(min_length=1, max_length=1_000, description="How the test reaches the target")
    input_description: str = Field(min_length=1, max_length=2_000)
    property_to_assert: str = Field(min_length=1, max_length=2_000)
    doubles: str = Field(default="", max_length=2_000, description="Dependencies that may be doubled, if any")
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=16)


class ProbePlan(Frozen):
    status: Literal["planned", "unsupported_scope", "target_not_found", "unresolved"]
    """``unresolved``: the Investigator produced no valid plan (output or budget failure), not a refusal."""
    target: str = Field(default="", max_length=512)
    hypothesis: str = Field(default="", max_length=4_000, description="Conditional: if X reaches Y without Z then ...")
    control: ProbeBrief | None = None
    exploit: ProbeBrief | None = None
    citations: tuple[Citation, ...] = ()
    reason: str = Field(default="", max_length=2_000)


# --- 5. Probe (Control Prober and Exploit Prober agents) --------------------------------------------------------


class ProbeDraft(Frozen):
    role: Literal["control", "exploit"]
    test_file: SafePath
    test_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    source: str = Field(min_length=1, max_length=64_000)
    revision_of: str | None = Field(default=None, description="sha256 of the draft this one replaces (a D3 or "
                                                             "a review revision)")

    @field_validator("source")
    @classmethod
    def _markers(cls, value: str) -> str:
        # D8 marker protocol: the test writes the files ``start`` (first statement), ``check`` (``holds`` or
        # ``violated``, immediately before its main assertion) and ``end`` (last, after its assertions) inside the
        # directory named by the CORSAIR_MARKER_DIR environment variable.
        if "CORSAIR_MARKER_DIR" not in value:
            raise ValueError("a probe must write the start, check and end marker files under $CORSAIR_MARKER_DIR")
        return value


class FrozenPatch(Frozen):
    """Both drafts, frozen before review and execution. Execution and review bind to this digest."""

    control: ProbeDraft
    exploit: ProbeDraft
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


# --- 6. Review (Reviewer agent, outcome-blind) ------------------------------------------------------------------


class ProbeValidity(Frozen):
    role: Literal["control", "exploit"]
    valid: bool
    calls_real_target: bool
    exercises_condition: bool
    assertion_relevant: bool
    doubles_only_dependencies: bool
    defects: tuple[str, ...] = Field(default=(), max_length=16)
    citations: tuple[Citation, ...] = Field(default=(), max_length=16)


class Validity(Frozen):
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: Literal["vulnerable", "fixed"]
    control: ProbeValidity
    exploit: ProbeValidity


# --- 7. Execute (code) ------------------------------------------------------------------------------------------


class Outcome(StrEnum):
    PASSED = "passed"
    ASSERTION_FAILED = "assertion_failed"
    ERRORED = "errored"
    NOT_RUN = "not_run"
    INFRA = "infra"
    ANOMALOUS = "anomalous"


CheckResult = Literal["ok", "not_run", "errored"]
"""The D3 mechanical check after freezing: any outcome other than not_run or errored is ``ok`` and discarded."""


class ProbeFacts(Frozen):
    """What trusted code observed for one run of one probe. ``Outcome`` is a pure function of these."""

    exit_code: int | None = Field(description="None when the run timed out or the container failed")
    exit_class: ExitClass | None
    timed_out: bool = False
    start_marker: bool
    end_marker: bool
    token_in_output: bool
    check_marker: Literal["holds", "violated"] | None = Field(
        default=None, description="Content of the check file the test writes before its main assertion; None when "
                                  "absent or not exactly holds/violated after stripping whitespace")


class ProbeRun(Frozen):
    role: Literal["control", "exploit"]
    revision: Literal["vulnerable", "fixed"]
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    facts: ProbeFacts
    outcome: Outcome
    output: ArtifactRef | None = None
    duration_s: float | None = Field(default=None, ge=0)
    cleanup_confirmed: bool | None = Field(default=None, description="False is cleanup_unconfirmed; None unknown")


# --- 8. Decide (code) -------------------------------------------------------------------------------------------


class Label(StrEnum):
    LIKELY_EXPLOITABLE = "LIKELY_EXPLOITABLE"
    LIKELY_NOT_EXPLOITABLE = "LIKELY_NOT_EXPLOITABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNABLE_TO_RUN = "UNABLE_TO_RUN"
    ERROR = "ERROR"


class TerminalReason(StrEnum):
    OK = "ok"
    NO_RUNTIME = "no_runtime"
    BUILD_FAILED = "build_failed"
    PLAN_UNRESOLVED = "plan_unresolved"
    TARGET_NOT_FOUND = "target_not_found"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    PROBE_NOT_RUN = "probe_not_run"
    PROBE_ERRORED = "probe_errored"
    PROBE_ANOMALOUS = "probe_anomalous"
    TEST_INVALID = "test_invalid"
    CONTROL_FAILED = "control_failed"
    NO_VALID_OBSERVATION = "no_valid_observation"
    NOT_DIFFERENTIAL = "not_differential"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_ERROR = "provider_error"
    INFRA_ERROR = "infra_error"
    CLEANUP_UNCONFIRMED = "cleanup_unconfirmed"


class Origin(StrEnum):
    """Where a fact in the report came from (A5)."""

    PLATFORM_OBSERVED = "platform_observed"
    NATIVE_TEST_REPORTED = "native_test_reported"
    MODEL_REVIEWED = "model_reviewed"
    DECLARED = "declared"


class Verdict(Frozen):
    contract: Literal["corsair-v2/1"] = CONTRACT_VERSION
    case_id: str
    label: Label
    rule_id: str = Field(pattern=r"^R\d+$")
    terminal_reason: TerminalReason
    finding: Literal["reproduced", "not_reproduced", "inconclusive", "none"]
    fix: Literal["verified", "not_verified", "not_applicable"]
    fix_reason: TerminalReason | None = Field(
        default=None, description="ok when verified, None when not applicable, else why the fix is not verified")
    runs: tuple[ProbeRun, ...] = ()
    validity: tuple[Validity, ...] = ()
    facts_origin: dict[str, Origin] = Field(default_factory=dict)
    review_rounds: int = Field(default=0, ge=0, description="Reviews of the vulnerable revision, first included")
    revisions: dict[Literal["control", "exploit"], int] = Field(
        default_factory=dict, description="Review revisions each author was asked for (D3 revisions not counted)")
    first_review_valid: dict[Literal["control", "exploit"], bool] = Field(
        default_factory=dict, description="Each probe's validity at the first review; absent when that review did not bind "
                                  "or complete")


# --- Telemetry, recorded per agent call -------------------------------------------------------------------------


class AgentUsage(Frozen):
    """Native usage for one agent run. Missing values stay None: unknown, never zero."""

    agent: Literal["grounding", "builder", "investigator", "control_prober", "exploit_prober", "reviewer"]
    model: str | None = None
    requests: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: int | None = None
    wall_s: float | None = None
    status: Literal["ok", "output_invalid", "budget_exhausted", "provider_error", "infra_error"] = "ok"
    error: str | None = Field(default=None, max_length=2_000, description="Upstream failure detail, if any")

