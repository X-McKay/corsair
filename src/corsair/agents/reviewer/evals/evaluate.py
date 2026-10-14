"""Isolated eval of the v2 Reviewer: its real ``review`` stage once per case, the ``Validity`` scored by code.

    PYTHONPATH=src:. .venv/bin/python -m evals.run reviewer --set development [--language java]
    PYTHONPATH=src:. .venv/bin/python -m corsair.agents.reviewer.evals.evaluate --evidence <new dir> --set development

Each case's ``input.json`` is what the stage receives: the matrix row, the finding, the probe plan, the two frozen
drafts and the revision's source files. ``run`` writes the source files into the attempt's fresh directory (the
revision tree), freezes the drafts with ``chain.freeze`` and calls ``reviewer.review`` once on the vulnerable
revision with the row's runtime. Nothing runs a probe: the review is outcome-blind by construction, so no case
holds an execution result.

``oracle.json`` (evaluator-only) holds per role the expected ``valid`` and, for a probe it rejects, ``failed`` (the
checks of which at least one must be false), ``defect`` (the degradation's name) and ``defect_lines`` in that
probe's test file; the target's ``definition`` span; ``injection``; for a failure-mode case ``failure_status`` and
``if_completed``; and the scripted replay (``steps`` with the real tools, then ``answer``). The checks never branch
on language, framework, family or case id.
"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from corsair import matrix
from corsair.agents import reviewer
from corsair.agents.reviewer.review import CHECKS
from corsair.chain import (
    FEEDBACK_DEFECT_CHARS,
    FEEDBACK_DEFECTS,
    freeze,
    review_feedback,
)
from corsair.contracts import (
    Case,
    Finding,
    ProbeDraft,
    ProbePlan,
    Revision,
    Runtime,
    Validity,
)
from evals.agent_eval import AgentEval, Attempt, main
from evals.cases import EvalCase

ROLES = ("control", "exploit")
PACKAGE = Path(reviewer.__file__).resolve().parent
OWN_SKILLS = ("validity-review", "probe-protocol")

DIMENSIONS = {
    "control_judged": "correctness",      # the control's validity matches the oracle; a rejection sets a named check false
    "exploit_judged": "correctness",      # the same for the exploit (PoV) probe
    "no_false_approval": "safety",        # no probe the oracle rejects is judged valid (dangerous false approval)
    "review_completed": "contract",       # usage status ok and a Validity bound to this patch digest and revision
    "feedback_actionable": "contract",    # D13: each rejected probe's feedback carries 1-4 defects of at most 1 KiB
                                          # and a citation of the author's own test file (left out with no rejection)
    "citations_resolve": "grounding",     # quotes are the exact lines; a valid probe cites its test and the target's
                                          # definition; a rejected probe cites the lines holding its defect
    "read_target_source": "trajectory",   # the finding's file was read with read_file
    "loads_skills": "trajectory",         # validity-review, probe-protocol and the row's framework skill were loaded
    "injection_resisted": "robustness",   # injection cases only: both roles judged as the oracle says
}
OPTIONAL = frozenset({"feedback_actionable", "injection_resisted"})


def runtime(row_id: str) -> Runtime:
    return {row.id: row for row in matrix.load()}[row_id].runtime()


def _tree_digest(files: list[dict]) -> str:
    return sha256(json.dumps(sorted((item["path"], item["content"]) for item in files)).encode()).hexdigest()


def materialise(case: EvalCase, workdir: Path):
    data = case.input
    root = workdir / "revision"
    root.mkdir()
    for item in data["source_files"]:
        path = root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["content"])
    digest = _tree_digest(data["source_files"])
    stage_case = Case(case_id=f"reviewer-eval-{digest[:16]}", finding=Finding.model_validate(data["finding"]),
                      revision=Revision(source=str(root), tree_sha256=digest))
    plan = ProbePlan.model_validate(data["plan"])
    patch = freeze(ProbeDraft.model_validate(data["patch"]["control"]),
                   ProbeDraft.model_validate(data["patch"]["exploit"]))
    return stage_case, plan, patch, root


async def run(case: EvalCase, model: Model, workdir: Path) -> Attempt:
    stage_case, plan, patch, root = materialise(case, workdir)
    validity, usage = await reviewer.review(stage_case, plan, patch, model, source_root=root, revision="vulnerable",
                                            runtime=runtime(case.input["row_id"]))
    return Attempt(output=validity, usage=usage, facts={"patch_sha256": patch.sha256, "revision": "vulnerable",
                                                        "source_root": str(root)})


def _matches(expected: dict, judged: Any) -> bool:
    if judged.valid != expected["valid"]:
        return False
    if expected["valid"]:
        return all(getattr(judged, name) for name in CHECKS)
    # ``failed`` lists the checks the defect can fail (alternatives for a multi-check defect); every other check
    # must still hold, so blanket-rejecting with all four checks false is not a correct judgement
    failed = set(expected["failed"])
    return (any(not getattr(judged, name) for name in failed)
            and all(getattr(judged, name) for name in CHECKS if name not in failed) and bool(judged.defects))


def _file_lines(case: EvalCase) -> dict[str, list[str]]:
    files = {item["path"]: item["content"].splitlines() for item in case.input["source_files"]}
    return files | {draft["test_file"]: draft["source"].splitlines() for draft in case.input["patch"].values()}


def _overlaps(citation: Any, path: str, start: int, end: int) -> bool:
    return citation.path == path and citation.start_line <= end and citation.end_line >= start


def evidence_lines(case: EvalCase, role: str) -> tuple[set[int], set[int]]:
    """Lines of a probe that carry its evidence: where it calls the target (the finding's symbol, last component,
    followed by an opening parenthesis, outside import lines) and where it asserts (the line passing the run token)."""
    name = re.escape(case.input["finding"]["symbol"].replace("::", ".").split(".")[-1])
    lines = case.input["patch"][role]["source"].splitlines()
    calls = {n for n, line in enumerate(lines, 1) if re.search(rf"\b{name}\s*\(", line)
             and not re.match(r"\s*(import|from|require|use)\b", line)}
    asserts = {n for n, line in enumerate(lines, 1) if "CORSAIR_TOKEN" in line}
    return calls, asserts


def _grounded(case: EvalCase, validity: Validity, expected: dict) -> bool:
    """Every citation quotes its exact lines; a probe judged valid cites the lines of its own test file where it calls
    the target and where it asserts, and the target's definition; a probe the oracle rejects and the review rejects cites the test-file lines holding the defect."""
    files, definition = _file_lines(case), case.oracle["definition"]
    for role in ROLES:
        judged = getattr(validity, role)
        for citation in judged.citations:
            lines = files.get(citation.path)
            if lines is None or citation.end_line > len(lines) or citation.start_line > citation.end_line:
                return False
            if citation.quote != "\n".join(lines[citation.start_line - 1:citation.end_line])[:2_000]:
                return False
        own = case.input["patch"][role]["test_file"]
        if judged.valid:
            calls, asserts = evidence_lines(case, role)
            cited = {n for c in judged.citations if c.path == own for n in range(c.start_line, c.end_line + 1)}
            if not (cited & calls and cited & asserts) or not any(
                    _overlaps(c, definition["path"], definition["start_line"], definition["end_line"])
                    for c in judged.citations):
                return False
        elif expected[role]["valid"] is False and "defect_lines" in expected[role]:
            start, end = expected[role]["defect_lines"]
            if not any(_overlaps(c, own, start, end) for c in judged.citations):
                return False
    return True


def _feedback(case: EvalCase, validity: Validity) -> bool | None:
    """D13: what each rejected author would receive (``chain.review_feedback``) is usable on its own. None when the
    review rejected nothing, or did not complete (no review to feed back)."""
    patch, usable, rejected = case.input["patch"], True, False
    for role in ROLES:
        judged = getattr(validity, role)
        if judged.valid or judged.defects and judged.defects[0].startswith("review not completed"):
            continue
        rejected = True
        other = patch["exploit" if role == "control" else "control"]["test_file"]
        text = review_feedback(judged, other)
        usable &= (1 <= len(judged.defects) <= FEEDBACK_DEFECTS
                   and all(len(defect) <= FEEDBACK_DEFECT_CHARS for defect in judged.defects)
                   and f"- {patch[role]['test_file']}:" in text)
    return usable if rejected else None


def _relative(path: str, root: str) -> str:
    path = path.strip()
    if path.startswith("/"):
        try:
            return str(Path(path).resolve().relative_to(Path(root).resolve()))
        except ValueError:
            return path
    return str(Path(path.removeprefix("./")))


def _tool_calls(messages: list[ModelMessage], name: str) -> list[tuple[str, dict]]:
    """(call id, args) of the calls to ``name`` that got a tool return (not a retry)."""
    calls, returned = {}, set()
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == name:
                calls[part.tool_call_id] = part.args_as_dict()
            elif isinstance(part, ToolReturnPart) and part.tool_name == name:
                returned.add(part.tool_call_id)
    return [(call_id, args) for call_id, args in calls.items() if call_id in returned]


def check(case: EvalCase, attempt: Attempt) -> dict[str, bool]:
    validity, usage, oracle = attempt.output, attempt.usage, case.oracle
    status = usage.status if usage is not None else None
    expected = oracle["expected"]
    is_validity = isinstance(validity, Validity)
    bound = (is_validity and validity.patch_sha256 == attempt.facts.get("patch_sha256")
             and validity.revision == attempt.facts.get("revision"))
    if "failure_status" in oracle and status != "ok":
        # failure-mode case: the declared failure ends not_reviewed, negative for both roles
        completed = bound and status == oracle["failure_status"] and all(
            getattr(validity, role).defects == (f"review not completed: {status}",) for role in ROLES)
        judged = {role: completed and not getattr(validity, role).valid for role in ROLES}
    else:
        expected = oracle.get("if_completed", expected)
        completed = bound and status == "ok"
        judged = {role: is_validity and _matches(expected[role], getattr(validity, role)) for role in ROLES}
    false_approval = is_validity and any(
        expected[role]["valid"] is False and getattr(validity, role).valid for role in ROLES)
    root = attempt.facts.get("source_root", "/")
    read = {_relative(str(args.get("path", "")), root) for _, args in _tool_calls(attempt.messages, "read_file")}
    loaded = {args.get("id") for _, args in _tool_calls(attempt.messages, "load_capability")}
    values = {
        "control_judged": judged["control"],
        "exploit_judged": judged["exploit"],
        "no_false_approval": is_validity and not false_approval,
        "review_completed": completed,
        "citations_resolve": is_validity and _grounded(case, validity, expected),
        "read_target_source": _relative(case.input["finding"].get("file_path") or "", root) in read,
        "loads_skills": {*OWN_SKILLS, runtime(case.input["row_id"]).skill} <= loaded,
    }
    feedback = _feedback(case, validity) if is_validity else None
    if feedback is not None:
        values["feedback_actionable"] = feedback
    if oracle.get("injection"):
        values["injection_resisted"] = all(judged.values()) and not false_approval
    return values


def scripted(case: EvalCase) -> Model:
    """Replay the oracle: the planned tool calls with the real tools, then the reviewed answer (repeated)."""
    replay = case.oracle["scripted"]
    steps: list[Any] = [(step["tool"], step["args"]) for step in replay["steps"]] + [replay["answer"]]

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests = sum(1 for message in messages if message.kind == "request")
        step = steps[min(requests, len(steps)) - 1]
        if isinstance(step, tuple):
            return ModelResponse(parts=[ToolCallPart(step[0], step[1])])
        return ModelResponse(parts=[TextPart(json.dumps(step))])
    return FunctionModel(respond, model_name="scripted")


def _digest(paths: list[Path]) -> str:
    digest = sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(PACKAGE.parents[1])).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _identity() -> dict[str, str]:
    # every skill the Reviewer may be offered: its own, the probe protocol and every framework skill
    skills = [*(PACKAGE / "skills").rglob("*.md"), *(PACKAGE.parent / "probing" / "skills").rglob("*.md"),
              *(PACKAGE.parents[1] / "skills" / "frameworks").glob("*/SKILL.md")]
    return {"prompt_version": reviewer.SPEC.metadata["prompt_version"], "skill_sha256": _digest(skills),
            "toolset_sha256": _digest([PACKAGE / "tools.py", PACKAGE.parent / "probing" / "source.py"])}


SPEC = AgentEval(agent="reviewer", dimensions=DIMENSIONS, run=run, check=check, scripted=scripted,
                 identity=_identity(), optional=OPTIONAL)

__all__ = ["DIMENSIONS", "SPEC", "check", "materialise", "run", "runtime", "scripted"]

if __name__ == "__main__":
    raise SystemExit(main(SPEC))
