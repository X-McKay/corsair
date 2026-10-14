"""Stage signatures shared by the chain, the workflow and the evals.

Each module implements its function with exactly this shape, so ``chain.py`` composes them and each agent's eval
calls its stage alone. Agent stages return their native usage beside the result; a missing value is None.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic_ai.models import Model

from .contracts import (AgentUsage, Attempt, BuildResult, Case, CheckResult, Environment, FrozenPatch, ProbeBrief,
                        ProbeDraft, ProbePlan, ProbeRun, Recipe, Runtime, Validity, Verdict)


class Select(Protocol):
    def __call__(self, case: Case, matrix: Path) -> Runtime | None: ...


class Investigate(Protocol):
    """Read-only source under ``source_root``; never executes anything."""

    async def __call__(self, case: Case, runtime: Runtime, model: Model, *, source_root: Path
                       ) -> tuple[ProbePlan, AgentUsage]: ...


class BuildAgent(Protocol):
    """Explores a disposable workspace container and proposes a Recipe; trusted replay decides if it holds."""

    async def __call__(self, case: Case, runtime: Runtime, plan: ProbePlan, model: Model, *, workspace: object,
                       feedback: str | None = None) -> tuple[Recipe | None, AgentUsage]: ...
    # ``feedback`` is set only for the single extra episode after a failed replay (A2): the replay log's tail.


class Replay(Protocol):
    """Trusted: replays the recipe in a fresh container and requires the baseline test to pass."""

    def __call__(self, case: Case, runtime: Runtime, recipe: Recipe, *, revision: str = "vulnerable"
                 ) -> tuple[BuildResult, Environment | None]: ...


class Probe(Protocol):
    """One Prober. ``diagnostics`` is set only for a D3 correction after a not_run or errored check run;
    ``review_feedback`` only for a review revision, and holds the Reviewer's judgement of this author's own draft
    (failed checks, defects, cited lines), never a run result or the other probe. Either comes with ``previous``."""

    async def __call__(self, brief: ProbeBrief, runtime: Runtime, model: Model, *, source_root: Path,
                       diagnostics: str | None = None, previous: ProbeDraft | None = None,
                       review_feedback: str | None = None) -> tuple[ProbeDraft | None, AgentUsage]: ...


class Review(Protocol):
    """Outcome-blind: sees the plan, the frozen patch and source, never a ProbeRun.

    ``runtime`` names the run's framework skill, which the Reviewer reads the way the Probers do, so it judges
    marker placement by that framework's sanctioned pattern. It is optional so a Review written before it composes.
    """

    async def __call__(self, case: Case, plan: ProbePlan, patch: FrozenPatch, model: Model, *, source_root: Path,
                       revision: str = "vulnerable", runtime: Runtime | None = None
                       ) -> tuple[Validity, AgentUsage]: ...


class Execute(Protocol):
    """Trusted: runs one probe alone, exactly once, with a fresh token, and classifies it."""

    def __call__(self, environment: Environment, runtime: Runtime, patch: FrozenPatch, role: str, *,
                 revision: str = "vulnerable") -> ProbeRun: ...


class Diagnose(Protocol):
    """Trusted D3 mechanical check: runs one frozen probe once on the vulnerable revision, before review.

    Returns ``ok`` (any outcome other than not_run or errored; the outcome itself is discarded) with no feedback, or
    ``not_run`` / ``errored`` with a fixed hint and the row's optional syntax-check output, never the run's own
    output. Nothing from this run counts as evidence; only reviewed bytes are executed later.
    """

    def __call__(self, environment: Environment, runtime: Runtime, draft: ProbeDraft
                 ) -> tuple[CheckResult, str | None]: ...


class Decide(Protocol):
    """``stopped`` is why the chain stopped (it concerns the vulnerable revision); ``fix_stopped`` is why the
    fixed-revision steps stopped, which only makes the fix ``not_verified``. ``attempts`` names each exploit
    attempt's pair (D18); the table decides on the last one."""

    def __call__(self, case: Case, *, runtime: Runtime | None, build: BuildResult | None, plan: ProbePlan | None,
                 validity: tuple[Validity, ...], runs: tuple[ProbeRun, ...], stopped: str | None = None,
                 fix_stopped: str | None = None, attempts: tuple[Attempt, ...] = ()) -> Verdict: ...
