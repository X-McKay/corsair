"""Whole-chain eval of v2: ``python -m evals.e2e.evaluate --set v2`` (or ``make eval AGENT=chain SET=v2``).

Each case's ``input.json`` goes through v2 intake (``intake.from_issue_json``) and then ``corsair.v2.chain.run_case``:
the real routing (``compose`` over ``LocalOps``), the real Select over ``deploy/v2/runtime-matrix.yaml`` and the
real Decide (``rules.decide``), recorded by a ``RunRecorder`` in the attempt's fresh working directory.

- **Scripted** (default; no model, no Docker): only what lies outside the process is replaced. The five agent
  stages, the Builder workspace, trusted replay, the D3 check and Execute replay the case oracle's ``replay`` block
  (evaluator-only, never in ``input.json``); the models handed to ``run_case`` refuse any call. A case without the
  observation a stage needs gets a ``LookupError`` from that stage, which the chain records as ``infra_error``.
- **Live** (``--provider-config``): ``default_stages()`` with every agent's model from ``corsair.v2.models``. It
  needs Docker and a reachable endpoint and refuses to start without Docker.

The ``replay`` block (README "Scorer"): ``plan`` (status, citations), ``build`` (one entry per Builder episode:
true replayed, false failed replay, null no recipe), ``build_fixed``, ``check`` (D3 result per role, a string or a
list consumed in order), ``review`` (per revision a round, or a list of rounds: per-role validity and citations)
and ``outcomes`` (raw probe outcome per revision and role). Recorded outcomes live only there, so a change of what
an outcome means is a data change.

Assertions, each tagged with one dimension; ``terminal_reason`` and ``grounding`` are left out when they do not
apply (no expected reason in the oracle; no citation in the verdict). Nothing here branches on language, framework,
CWE, case id or label.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import asynccontextmanager
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic_ai.models import Model
from pydantic_ai.models.function import FunctionModel

from corsair.v2 import intake, matrix
from corsair.v2.chain import MAX_REVIEWS, Stages, default_stages, run_case
from corsair.v2.contracts import (AgentUsage, BuildResult, Case, Citation, Environment, ExitClass, Label, Outcome,
                                  ProbeBrief, ProbeDraft, ProbeFacts, ProbePlan, ProbeRun, ProbeValidity, Recipe,
                                  Runtime, Validity, Verdict)
from corsair.v2.outcome import classify
from corsair.v2.record import RunRecorder, to_json
from corsair.v2.rules import RULES, decide
from evals.agent_eval import AgentEval, Attempt, main
from evals.cases import EVALS, CHAIN, EvalCase

ROOT = EVALS / "e2e"
REPOSITORY = EVALS.parent
MATRIX = REPOSITORY / "deploy" / "v2" / "runtime-matrix.yaml"
AGENTS = ("investigator", "builder", "control_prober", "exploit_prober", "reviewer")
ROLES = ("control", "exploit")
DIMENSIONS = {"label": "correctness", "terminal_reason": "correctness", "outcome_fields": "correctness",
              "contract": "contract",
              "grounding": "grounding", "trajectory": "trajectory", "safety": "safety"}
OPTIONAL = frozenset({"terminal_reason", "outcome_fields", "grounding"})
RULE_LABEL = {rule.id: rule.label for rule in RULES}
USAGE_FIELDS = ("requests", "tool_calls", "input_tokens", "output_tokens")
# Oracle fields whose values legitimately reach stages: pinned digests, the Select row, the chain's own enum values
# (a stop reason reaches Decide as ``stopped``) and the scripted replay itself. Labels are always checked.
NOT_SECRET = {"replay", "revision_tree_sha256", "fixed_tree_sha256", "expected_runtime_row", "expected_rule",
              "expected_terminal_reason", "expected_finding", "expected_fix"}
MIN_SECRET_CHARS = 16


class ChainUsage(BaseModel):
    """Per-run totals over every agent call; a field any call left unreported stays null (unknown, not zero)."""

    requests: int | None
    tool_calls: int | None
    input_tokens: int | None
    output_tokens: int | None
    wall_s: float
    status: str
    agent_calls: int
    calls: list[dict]


class ScriptedModels(dict):
    """Scripted mode's models: one per agent, each refusing to be called (the stages replay the oracle)."""


def _refuse(messages, info):
    raise RuntimeError("scripted chain eval: no model call is expected; the stages replay recorded outputs")


def scripted(case: EvalCase) -> ScriptedModels:
    return ScriptedModels({agent: FunctionModel(_refuse, model_name="scripted-refuse") for agent in AGENTS})


# --- Loading a case ------------------------------------------------------------------------------------------------


def input_path(case: EvalCase) -> Path:
    """The case's input.json: the directory under ``<language>/<set>/<name>/`` whose input is this one."""
    found = [path for path in sorted((ROOT / case.language).glob(f"*/{case.name}/input.json"))
             if json.loads(path.read_text()) == case.input]
    if len(found) != 1:
        raise LookupError(f"{case.key}: {len(found)} input.json files match this case")
    return found[0]


# --- Scripted stages: the recorded observations of everything outside the process ---------------------------------


def _usage(agent: str) -> AgentUsage:
    return AgentUsage(agent=agent, model="scripted-replay")  # nothing was measured: every count stays unknown


def _digest(value: BaseModel) -> str:
    return hashlib.sha256(json.dumps(value.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


_FACTS = {  # the platform facts each raw outcome is classified from (corsair.v2.outcome), for a well-formed ProbeRun
    "passed": dict(exit_code=0, exit_class=ExitClass.PASS, start_marker=True, end_marker=True, token_in_output=False,
                   check_marker="holds"),
    "assertion_failed": dict(exit_code=1, exit_class=ExitClass.TEST_FAILED, start_marker=True, end_marker=False,
                             token_in_output=True, check_marker="violated"),
    "errored": dict(exit_code=1, exit_class=ExitClass.TEST_FAILED, start_marker=True, end_marker=False,
                    token_in_output=False),
    "not_run": dict(exit_code=2, exit_class=None, start_marker=False, end_marker=False, token_in_output=False),
    "infra": dict(exit_code=None, exit_class=None, start_marker=False, end_marker=False, token_in_output=False),
    "anomalous": dict(exit_code=0, exit_class=ExitClass.PASS, start_marker=True, end_marker=False,
                      token_in_output=True),
}


class Replay:
    """Fake stage callables answering from one case's ``replay`` block, in call order."""

    def __init__(self, key: str, replay: Mapping[str, Any] | None):
        self.key, self.replay = key, replay or {}
        self.episodes = 0
        self.checks: dict[str, int] = {}
        self.reviews: dict[str, int] = {}

    def need(self, *path: str) -> Any:
        value: Any = self.replay
        for part in path:
            if not isinstance(value, Mapping) or part not in value:
                raise LookupError(f"{self.key}: the oracle replay has no recorded {'.'.join(path)}")
            value = value[part]
        return value

    def _brief(self, role: str, runtime: Runtime, citations: tuple[Citation, ...]) -> ProbeBrief:
        name = f"corsair_{role}_probe"
        test_file = f"{runtime.test_dir.strip('/')}/{name}" if runtime.test_dir.strip("/") else name
        return ProbeBrief(role=role, test_file=test_file, test_name=f"test_{name}", target="recorded target",
                          seam="recorded seam", input_description="recorded input",
                          property_to_assert="recorded property", citations=citations)

    async def investigate(self, case: Case, runtime: Runtime, model: Model, *, source_root: Path):
        plan = self.need("plan")
        citations = tuple(Citation(**item) for item in plan.get("citations") or ())
        if plan["status"] != "planned":
            return ProbePlan(status=plan["status"], citations=citations, reason=plan.get("reason", "")), \
                _usage("investigator")
        return ProbePlan(status="planned", target="recorded target", citations=citations,
                         control=self._brief("control", runtime, citations),
                         exploit=self._brief("exploit", runtime, citations)), _usage("investigator")

    async def build(self, case, runtime, plan, model, *, workspace, feedback=None):
        episodes = self.need("build")
        if self.episodes >= len(episodes):
            raise LookupError(f"{self.key}: the oracle replay records {len(episodes)} Builder episode(s)")
        entry = episodes[self.episodes]
        self.episodes += 1
        return (None if entry is None else Recipe(baseline_test=("recorded-baseline",))), _usage("builder")

    def replay_build(self, case: Case, runtime: Runtime, recipe: Recipe, *, revision: str = "vulnerable"):
        ok = bool(self.need("build")[self.episodes - 1]) if revision == "vulnerable" else bool(self.need("build_fixed"))
        tree = case.revision if revision == "vulnerable" else case.fixed_revision
        build = BuildResult(recipe=recipe, replayed=ok, baseline_exit_code=0 if ok else 1,
                            reason="" if ok else "recorded replay: the baseline test did not pass")
        environment = Environment(image=f"recorded/{revision}", runtime_row=runtime.row_id,
                                  recipe_sha256=_digest(recipe), tree_sha256=tree.tree_sha256) if ok else None
        return build, environment

    async def _probe(self, role, brief, runtime, model, *, source_root, diagnostics=None, previous=None,
                     review_feedback=None):
        source = f"recorded {role} probe; writes its markers under CORSAIR_MARKER_DIR" + (
            "" if previous is None else f"; revision of {_digest(previous)[:12]}")
        draft = ProbeDraft(role=role, test_file=brief.test_file, test_name=brief.test_name, source=source)
        return draft, _usage(f"{role}_prober")

    async def control_probe(self, brief, runtime, model, **kwargs):
        return await self._probe("control", brief, runtime, model, **kwargs)

    async def exploit_probe(self, brief, runtime, model, **kwargs):
        return await self._probe("exploit", brief, runtime, model, **kwargs)

    def diagnose(self, environment, runtime, draft):
        recorded = self.need("check", draft.role)
        recorded = [recorded] if isinstance(recorded, str) else list(recorded)
        n = self.checks.get(draft.role, 0)
        if n >= len(recorded):
            raise LookupError(f"{self.key}: the oracle replay records {len(recorded)} {draft.role} check(s)")
        self.checks[draft.role] = n + 1
        check = recorded[n]
        return check, None if check == "ok" else f"check: {check}\nhint: recorded mechanical failure"

    async def review(self, case, plan, patch, model, *, source_root, revision="vulnerable", runtime=None):
        rounds = self.need("review", revision)
        rounds = [rounds] if isinstance(rounds, Mapping) else list(rounds)
        n = self.reviews.get(revision, 0)
        if n >= len(rounds):
            raise LookupError(f"{self.key}: the oracle replay records {len(rounds)} {revision} review(s)")
        self.reviews[revision] = n + 1
        entry = rounds[n]
        citations = tuple(Citation(**item) for item in entry.get("citations") or ())

        def one(role: str) -> ProbeValidity:
            valid = bool(entry[role])
            return ProbeValidity(role=role, valid=valid, calls_real_target=valid, exercises_condition=valid,
                                 assertion_relevant=valid, doubles_only_dependencies=True,
                                 defects=() if valid else ("recorded review: the probe does not exercise the condition",),
                                 citations=citations)
        return Validity(patch_sha256=patch.sha256, revision=revision, control=one("control"),
                        exploit=one("exploit")), _usage("reviewer")

    def execute(self, environment, runtime, patch, role, *, revision="vulnerable"):
        outcome = self.need("outcomes", revision, role)
        facts = ProbeFacts(**_FACTS[outcome])
        if classify(facts) is not Outcome(outcome):  # the recorded facts must read as the recorded outcome today
            raise ValueError(f"{self.key}: recorded facts for {outcome} classify as {classify(facts).value}")
        return ProbeRun(role=role, revision=revision, patch_sha256=patch.sha256, facts=facts, outcome=Outcome(outcome))

    @asynccontextmanager
    async def workspace(self, case, runtime):
        yield "recorded-workspace"

    def stages(self) -> Stages:
        return Stages(select=matrix.select, investigate=self.investigate, build=self.build, replay=self.replay_build,
                      control_probe=self.control_probe, exploit_probe=self.exploit_probe, review=self.review,
                      diagnose=self.diagnose, execute=self.execute, decide=decide, workspace=self.workspace)


# --- Observation: what every stage received and every Prober wrote -------------------------------------------------


def observe(stages: Stages, log: list[dict]) -> Stages:
    """The same stages, each call logged with its inputs (models left out) and, for the Probers, the draft's path."""

    def inputs(name: str, args: tuple, kwargs: dict) -> dict:
        values = [a for a in args if not isinstance(a, Model)]
        named = {k: v for k, v in kwargs.items() if not isinstance(v, Model)}
        entry = {"stage": name, "text": json.dumps(to_json([values, named]), ensure_ascii=False, sort_keys=True)}
        if "source_root" in kwargs:
            entry["source_root"] = str(kwargs["source_root"])
        log.append(entry)
        return entry

    def wrap(name: str, function):
        if function is None:
            return None
        if name == "workspace":
            def opened(*args, **kwargs):
                inputs(name, args, kwargs)
                return function(*args, **kwargs)
            return opened
        if inspect.iscoroutinefunction(function):
            async def called(*args, **kwargs):
                entry = inputs(name, args, kwargs)
                result = await function(*args, **kwargs)
                draft = result[0] if isinstance(result, tuple) and result else None
                if isinstance(draft, ProbeDraft):
                    entry["test_file"] = draft.test_file
                return result
            return called

        def plain(*args, **kwargs):
            inputs(name, args, kwargs)
            return function(*args, **kwargs)
        return plain

    return dataclasses.replace(stages, **{field.name: wrap(field.name, getattr(stages, field.name))
                                          for field in dataclasses.fields(stages)
                                          if callable(getattr(stages, field.name))})


# --- One attempt ---------------------------------------------------------------------------------------------------


def docker_problem() -> str | None:
    """Why live mode cannot run here, or None when a Docker daemon answers."""
    if shutil.which("docker") is None:
        return "the docker CLI is not on PATH"
    try:
        probe = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                               timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"docker info failed: {exc}"
    if probe.returncode != 0:
        return f"docker info exited {probe.returncode}: {(probe.stderr or probe.stdout).strip()[:500]}"
    return None


def _total(values: list[int | None]) -> int | None:
    return None if any(value is None for value in values) else sum(values)


def _usage_totals(rows: list[dict], wall_s: float, verdict: Verdict) -> ChainUsage:
    statuses = [row.get("status") for row in rows if row.get("status") not in (None, "ok")]
    status = "budget_exhausted" if verdict.terminal_reason.value == "budget_exhausted" else \
        (statuses[0] if statuses else "ok")
    return ChainUsage(**{name: _total([row.get(name) for row in rows]) for name in USAGE_FIELDS},
                      wall_s=round(wall_s, 3), status=status, agent_calls=len(rows), calls=rows)


async def run(case: EvalCase, models: Mapping[str, Model], workdir: Path) -> Attempt:
    """The case through ``run_case`` once; scripted when ``models`` is the replay set, else live."""
    loaded = intake.from_issue_json(input_path(case))
    if isinstance(models, ScriptedModels):
        stages = Replay(case.key, case.oracle.get("replay")).stages()
    else:
        problem = docker_problem()
        if problem is not None:
            raise RuntimeError(f"live chain eval needs Docker: {problem}")
        stages = default_stages()
    log: list[dict] = []
    record = RunRecorder.create(workdir / "runs")
    started = perf_counter()
    verdict = await run_case(loaded, stages=observe(stages, log), models=dict(models), matrix_path=MATRIX,
                             record=record)
    wall = perf_counter() - started
    run_dir = record.run_dir
    steps = [row["step"] for row in json.loads((run_dir / "timings.json").read_text())] \
        if (run_dir / "timings.json").exists() else []
    usage_rows = json.loads((run_dir / "usage.json").read_text()) if (run_dir / "usage.json").exists() else []
    vulnerable = next((v for v in verdict.validity if v.revision == "vulnerable"), None)
    reviewed = verdict.review_rounds > 0
    trees = {"vulnerable": loaded.revision.source,
             "fixed": loaded.fixed_revision.source if loaded.fixed_revision else None}
    facts = {
        "label": verdict.label.value, "expected_label": case.oracle.get("expected_label"),
        "terminal_reason": verdict.terminal_reason.value, "rule_id": verdict.rule_id,
        "steps": steps, "review_rounds": verdict.review_rounds, "revisions_by_role": dict(verdict.revisions),
        "revisions": sum(verdict.revisions.values()) if reviewed else None,
        "accepted_within_limit": (vulnerable is not None and vulnerable.control.valid and vulnerable.exploit.valid
                                  and verdict.review_rounds <= MAX_REVIEWS) if reviewed else None,
        "trees": trees, "case_id": loaded.case_id,
        "source_roots": sorted({entry["source_root"] for entry in log if "source_root" in entry}),
        "probe_files": sorted({entry["test_file"] for entry in log if "test_file" in entry}),
    }
    attempt = Attempt(output=verdict, usage=_usage_totals(usage_rows, wall, verdict), facts=facts)
    attempt.stage_inputs = [entry["text"] for entry in log]  # not dumped into receipts
    return attempt


# --- Checks --------------------------------------------------------------------------------------------------------


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def oracle_secrets(case: EvalCase) -> set[str]:
    """Oracle text no stage may receive: every label it names, and any longer oracle string the input lacks."""
    oracle = case.oracle
    labels = {oracle.get("expected_label"), *oracle.get("acceptable_labels", ()), *oracle.get("forbidden_labels", ())}
    inputs = _strings(case.input)
    free = {text for key, value in oracle.items() if key not in NOT_SECRET for text in _strings(value)
            if len(text) >= MIN_SECRET_CHARS and not any(text in item for item in inputs)}
    return {label for label in labels if label} | free


def _inside(root: Path, relative: str) -> bool:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        return False
    return (root / relative).resolve().is_relative_to(root.resolve())


def _citation_resolves(root: Path, citation: Citation) -> bool:
    if not _inside(root, citation.path) or not (root / citation.path).is_file():
        return False
    lines = (root / citation.path).read_text(errors="replace").splitlines()
    if not 1 <= citation.start_line <= citation.end_line <= len(lines):
        return False
    return not citation.quote or citation.quote == "\n".join(lines[citation.start_line - 1:citation.end_line])[:2_000]


# step name -> (phase, at most this many times); phases never decrease along the run
_PHASES = (
    (r"ground", 0, 1), (r"select", 1, 1), (r"investigate", 2, 1), (r"build", 3.0, 1), (r"replay-build", 3.1, 1),
    (r"build-retry", 3.2, 1), (r"replay-build-retry", 3.3, 1), (r"probe-control", 4.0, 1), (r"probe-exploit", 4.1, 1),
    (r"diagnose-(control|exploit)|probe-(control|exploit)-revision|review\.\d+|"
     r"probe\.(control|exploit)\.r\d+(\.revision)?|diagnose\.(control|exploit)\.r\d+", 5, None),
    (r"review-fixed", 6, 1), (r"execute-(control|exploit)-vulnerable", 7, 1), (r"replay-fixed", 8, 1),
    (r"execute-(control|exploit)-fixed", 9, 1), (r"decide", 10, 1),
)


def trajectory(steps: list[str], verdict: Verdict) -> bool:
    """Allowed order, each step at most as often as the chain allows, and the review loop inside its bound."""
    phases = []
    for step in steps:
        match = next(((phase, most) for pattern, phase, most in _PHASES if re.fullmatch(pattern, step)), None)
        if match is None or (match[1] is not None and steps.count(step) > match[1]):
            return False
        phases.append(match[0])
    if not steps or steps[-1] != "decide" or phases != sorted(phases) or steps.count("select") != 1:
        return False
    reviews = [int(step.split(".")[1]) for step in steps if re.fullmatch(r"review\.\d+", step)]
    if reviews != list(range(1, len(reviews) + 1)) or len(reviews) > MAX_REVIEWS or verdict.review_rounds != len(reviews):
        return False
    for role in ROLES:
        asked = [step for step in steps if re.fullmatch(rf"probe\.{role}\.r\d+", step)]
        if len(asked) > MAX_REVIEWS - 1 or verdict.revisions.get(role, 0) != len(asked):
            return False
        for step in asked:  # a review revision follows the review it answers
            n = int(step.split(".r")[1])
            if f"review.{n}" not in steps or steps.index(f"review.{n}") > steps.index(step):
                return False
    executed = {revision for step in steps for revision in ("vulnerable", "fixed")
                if re.fullmatch(rf"execute-(control|exploit)-{revision}", step)}
    valid = {v.revision for v in verdict.validity if v.control.valid and v.exploit.valid}
    return executed <= valid  # only reviewed, valid bytes ran


def check(case: EvalCase, attempt: Attempt) -> dict[str, bool]:
    verdict: Verdict = attempt.output
    facts, oracle = attempt.facts, case.oracle
    results: dict[str, bool] = {}
    results["label"] = (verdict.label.value in oracle["acceptable_labels"]
                        and verdict.label.value not in oracle.get("forbidden_labels", ()))
    if oracle.get("expected_terminal_reason") is not None:
        results["terminal_reason"] = verdict.terminal_reason.value == oracle["expected_terminal_reason"]
    # rule, finding and fix as the oracle names them (a case that accepts alternative labels names none)
    expected = {"rule_id": oracle.get("expected_rule"), "finding": oracle.get("expected_finding"),
                "fix": oracle.get("expected_fix")}
    expected = {name: value for name, value in expected.items() if value is not None}
    if expected:
        results["outcome_fields"] = all(getattr(verdict, name) == value for name, value in expected.items())
    try:
        Verdict.model_validate(verdict.model_dump(mode="json"))
        results["contract"] = (verdict.case_id == facts["case_id"]
                               and RULE_LABEL.get(verdict.rule_id) == verdict.label)
    except ValidationError:
        results["contract"] = False
    cited = [(validity.revision, citation) for validity in verdict.validity
             for judgement in (validity.control, validity.exploit) for citation in judgement.citations]
    if cited:
        trees = facts["trees"]
        results["grounding"] = all(trees.get(revision) is not None
                                   and _citation_resolves(Path(trees[revision]), citation)
                                   for revision, citation in cited)
    results["trajectory"] = trajectory(facts["steps"], verdict)
    roots = {root for root in facts["trees"].values() if root is not None}
    tree = Path(facts["trees"]["vulnerable"])
    secrets = oracle_secrets(case)
    texts = getattr(attempt, "stage_inputs", None)
    results["safety"] = (texts is not None
                         and set(facts["source_roots"]) <= roots
                         and all(_inside(tree, path) for path in facts["probe_files"])
                         and not any(secret in text for secret in secrets for text in texts))
    return results


SPEC = AgentEval(agent=CHAIN, dimensions=DIMENSIONS, run=run, check=check, scripted=scripted, root=ROOT,
                 optional=OPTIONAL, live_agents=AGENTS,
                 identity={"evaluator_version": "chain-e2e/1", "composition": "direct", "max_reviews": MAX_REVIEWS,
                           "matrix_sha256": hashlib.sha256(MATRIX.read_bytes()).hexdigest()})


if __name__ == "__main__":
    if "--provider-config" in sys.argv and (problem := docker_problem()) is not None:
        print(f"chain eval (live): Docker is required and unavailable: {problem}", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(SPEC))
