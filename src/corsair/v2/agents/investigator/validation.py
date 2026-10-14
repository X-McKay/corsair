"""Output checks for a ProbePlan, run in code before the plan leaves the Investigator.

A failure raises ``ModelRetry`` naming every problem, so the one output correction tells the model exactly what
to fix. The checks are mechanical and language-neutral: citations resolve in the tree, the two briefs are
complete, separate and placed under the test directory, and neither repeats the other's input.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic_ai import ModelRetry

from corsair.v2.contracts import Citation, ProbeBrief, ProbePlan

_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def citation_problem(root: Path, citation: Citation) -> str | None:
    """Why ``citation`` does not resolve under ``root``, or None when it does."""
    where = f"{citation.path}:{citation.start_line}-{citation.end_line}"
    root = root.resolve()
    path = (root / citation.path).resolve()
    if not path.is_relative_to(root):
        return f"{where}: path leaves the source tree"
    if not path.is_file():
        return f"{where}: no such file in the source tree"
    if citation.end_line < citation.start_line:
        return f"{where}: end_line is before start_line"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if citation.end_line > len(lines):
        return f"{where}: the file has only {len(lines)} lines"
    quote = normalise(citation.quote)
    if not quote:
        return f"{where}: quote is empty; copy the cited text"
    if quote not in normalise("\n".join(lines[citation.start_line - 1:citation.end_line])):
        return f"{where}: quote does not match the text at those lines"
    return None


def _brief_text(brief: ProbeBrief) -> str:
    return normalise(" ".join((brief.target, brief.seam, brief.input_description, brief.property_to_assert,
                               brief.doubles))).lower()


def plan_problems(plan: ProbePlan, root: Path, test_dir: str) -> list[str]:
    problems: list[str] = []
    briefs = [brief for brief in (plan.control, plan.exploit) if brief is not None]
    citations = [*plan.citations, *(citation for brief in briefs for citation in brief.citations)]
    problems += [problem for citation in citations if (problem := citation_problem(root, citation))]
    if plan.status != "planned":
        if not plan.reason.strip():
            problems.append(f"status {plan.status} needs a reason")
        return problems
    if not plan.target.strip() or not plan.hypothesis.strip():
        problems.append("a planned investigation needs a target and a conditional hypothesis")
    if plan.control is None or plan.exploit is None:
        return problems + ["a planned investigation needs both a control and an exploit brief"]
    for field, brief, role in (("control", plan.control, "control"), ("exploit", plan.exploit, "exploit")):
        if brief.role != role:
            problems.append(f"the {field} brief has role {brief.role!r}; it must be {role!r}")
        prefix = test_dir.strip("/")
        if prefix and not brief.test_file.startswith(prefix + "/"):
            problems.append(f"the {field} test_file {brief.test_file!r} must be under {prefix}/")
    if plan.control.test_file == plan.exploit.test_file:
        problems.append("the control and exploit briefs need separate test files")
    for this, other, name in ((plan.control, plan.exploit, "control"), (plan.exploit, plan.control, "exploit")):
        other_input = normalise(other.input_description).lower()
        if other_input and other_input in _brief_text(this):
            problems.append(f"the {name} brief repeats the other brief's input; each brief must stand alone")
    return problems


def check_plan(plan: ProbePlan, root: Path, test_dir: str) -> ProbePlan:
    problems = plan_problems(plan, root, test_dir)
    if problems:
        raise ModelRetry("The plan was refused:\n- " + "\n- ".join(problems))
    return plan
