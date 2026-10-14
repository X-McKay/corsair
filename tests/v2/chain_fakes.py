"""Fake stage callables for the chain, workflow and recorder tests. They log every call and what it received."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from corsair.v2.chain import Stages
from corsair.v2.contracts import (AgentUsage, BuildResult, Case, Citation, Environment, ExitClass, Finding,
                                  FrozenPatch, Label, Outcome, ProbeBrief, ProbeDraft, ProbeFacts, ProbePlan, ProbeRun,
                                  ProbeValidity, Recipe, Revision, Runtime, TerminalReason, Validity, Verdict)

SHA = "0" * 64
AGENT_NAMES = ("grounding", "builder", "investigator", "control_prober", "exploit_prober", "reviewer")


def case(tmp: Path, fixed: bool = False) -> Case:
    revision = Revision(source=str(tmp), tree_sha256=SHA)
    return Case(case_id="case-1", finding=Finding(title="reported issue"), revision=revision,
                fixed_revision=Revision(source=str(tmp), tree_sha256="1" * 64) if fixed else None)


RUNTIME = Runtime(row_id="row", image="image:1", framework="fw", skill="fw", run_template=("run", "{file}"),
                  exit_codes={0: ExitClass.PASS, 1: ExitClass.TEST_FAILED}, evidence="image-only")


def brief(role: str) -> ProbeBrief:
    return ProbeBrief(role=role, test_file=f"tests/test_{role}.x", test_name=f"test_{role}", target="target",
                      seam="direct call", input_description="input", property_to_assert="property",
                      citations=(Citation(path="src/a.x", start_line=1, end_line=2),))


PLAN = ProbePlan(status="planned", target="target", control=brief("control"), exploit=brief("exploit"))
RECIPE = Recipe(baseline_test=("run", "baseline"))
ENVIRONMENT = Environment(image="env:1", runtime_row="row", recipe_sha256=SHA, tree_sha256=SHA)


def draft(role: str, body: str = "") -> ProbeDraft:
    b = brief(role)
    return ProbeDraft(role=role, test_file=b.test_file, test_name=b.test_name,
                      source=f"CORSAIR_START {body} CORSAIR_END")


def usage(agent: str, **values: Any) -> AgentUsage:
    known = dict(model="test", requests=1, input_tokens=10, output_tokens=5, tool_calls=0)
    return AgentUsage(agent=agent, **{**known, **values})


def validity(patch: FrozenPatch, revision: str) -> Validity:
    def one(role):
        return ProbeValidity(role=role, valid=True, calls_real_target=True, exercises_condition=True,
                             assertion_relevant=True, doubles_only_dependencies=True)
    return Validity(patch_sha256=patch.sha256, revision=revision, control=one("control"), exploit=one("exploit"))


def run(patch: FrozenPatch, role: str, revision: str, outcome: Outcome = Outcome.PASSED) -> ProbeRun:
    facts = ProbeFacts(exit_code=0, exit_class=ExitClass.PASS, start_marker=True, end_marker=True,
                       token_in_output=False)
    return ProbeRun(role=role, revision=revision, patch_sha256=patch.sha256, facts=facts, outcome=outcome)


@dataclass
class Fakes:
    """Configurable fake stages. ``calls`` holds (name, args, kwargs) in call order."""

    runtime: Runtime | None = RUNTIME
    plan: ProbePlan | None = PLAN
    recipes: list[Recipe | None] = field(default_factory=lambda: [RECIPE])
    replays: list[bool] = field(default_factory=lambda: [True])
    diagnose_outcomes: dict[str, Outcome] = field(default_factory=dict)
    revised: dict[str, ProbeDraft | None] = field(default_factory=dict)
    raises: dict[str, BaseException] = field(default_factory=dict)
    usages: dict[str, AgentUsage] = field(default_factory=dict)
    grounding: bool = False
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def names(self) -> list[str]:
        return [name for name, _, _ in self.calls]

    def of(self, name: str) -> list[tuple[tuple, dict]]:
        return [(args, kwargs) for n, args, kwargs in self.calls if n == name]

    def _log(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))
        if name in self.raises:
            raise self.raises[name]

    def select(self, case, matrix):
        self._log("select", case, matrix)
        return self.runtime

    async def investigate(self, case, runtime, model, *, source_root):
        self._log("investigate", case, runtime, source_root=source_root)
        await Agent(model).run("plan the probes")  # a native run, so its message history is captured
        return self.plan, self.usages.get("investigator", usage("investigator"))

    async def build(self, case, runtime, plan, model, *, workspace, feedback=None):
        self._log("build", case, runtime, plan, workspace=workspace, feedback=feedback)
        return self.recipes.pop(0), self.usages.get("builder", usage("builder"))

    def replay(self, case, runtime, recipe, *, revision="vulnerable"):
        self._log("replay", case, runtime, recipe, revision=revision)
        ok = self.replays.pop(0) if revision == "vulnerable" else True
        result = BuildResult(recipe=recipe, replayed=ok, baseline_exit_code=0 if ok else 1,
                             reason="" if ok else "baseline test failed: missing module")
        return result, ENVIRONMENT if ok else None

    async def _probe(self, role, brief, runtime, model, *, source_root, diagnostics=None, previous=None):
        self._log(f"probe-{role}", brief, runtime, source_root=source_root, diagnostics=diagnostics,
                  previous=previous)
        out = draft(role) if previous is None else self.revised.get(role, draft(role, "revised"))
        return out, self.usages.get(f"{role}_prober", usage(f"{role}_prober"))

    async def control_probe(self, brief, runtime, model, **kwargs):
        return await self._probe("control", brief, runtime, model, **kwargs)

    async def exploit_probe(self, brief, runtime, model, **kwargs):
        return await self._probe("exploit", brief, runtime, model, **kwargs)

    def diagnose(self, environment, runtime, patch, role):
        self._log("diagnose", environment, runtime, patch, role)
        outcome = self.diagnose_outcomes.get(role, Outcome.PASSED)
        return outcome, f"{role} output: ImportError" if outcome in (Outcome.NOT_RUN, Outcome.ERRORED) else None

    async def review(self, case, plan, patch, model, *, source_root, revision="vulnerable"):
        self._log("review", case, plan, patch, source_root=source_root, revision=revision)
        return validity(patch, revision), self.usages.get("reviewer", usage("reviewer"))

    def execute(self, environment, runtime, patch, role, *, revision="vulnerable"):
        self._log("execute", environment, runtime, patch, role, revision=revision)
        return run(patch, role, revision)

    def decide(self, case, *, runtime, build, plan, validity, runs, stopped=None):
        self._log("decide", case, runtime=runtime, build=build, plan=plan, validity=validity, runs=runs,
                  stopped=stopped)
        if stopped is not None:
            return Verdict(case_id=case.case_id, label=Label.ERROR, rule_id="R1", terminal_reason=stopped,
                           finding="none", fix="not_applicable", runs=runs, validity=validity)
        return Verdict(case_id=case.case_id, label=Label.LIKELY_EXPLOITABLE, rule_id="R4",
                       terminal_reason=TerminalReason.OK, finding="reproduced", fix="not_applicable", runs=runs,
                       validity=validity)

    async def ground(self, finding, context, model):
        self._log("ground", finding, context)
        return {"summary": f"context {context}"}, self.usages.get("grounding", usage("grounding"))

    @asynccontextmanager
    async def workspace(self, case, runtime):
        self._log("workspace-open", case, runtime)
        yield "workspace"
        self._log("workspace-close")

    def stages(self) -> Stages:
        return Stages(select=self.select, investigate=self.investigate, build=self.build, replay=self.replay,
                      control_probe=self.control_probe, exploit_probe=self.exploit_probe, review=self.review,
                      diagnose=self.diagnose, execute=self.execute, decide=self.decide, workspace=self.workspace,
                      ground=self.ground, grounding_context=(lambda case: "ctx") if self.grounding else None)


def models() -> dict[str, TestModel]:
    return {name: TestModel() for name in AGENT_NAMES}
