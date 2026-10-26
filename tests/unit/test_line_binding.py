"""Line binding: every rule branch of the pure binder, its contract, and its consumers.

The binder chooses, at prepare, the statement line the coverage gate requires in both
runs. Expected lines below are the lines coverage.py 7.13 (the image's pinned version)
reports for these modules; a binding never moves a line to one coverage cannot report.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from temporalio.testing import ActivityEnvironment

from corsair.adapters.scm.local import LocalSourceSnapshots, prepare_case
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Case,
    Finding,
    FixStatus,
    InvestigationRequest,
    LineProvenance,
    PreparedCase,
    PythonRecipe,
    RoleOutcome,
    Source,
    Verdict,
)
from corsair.policies.line_binding import bind_target_line
from corsair.policies.target_binding import TargetBindingBlocked, derive_target_line
from corsair.policies.verdicts import session_verdict
from corsair.settings import Settings
from corsair.steps.activities import Activities
from corsair.steps.verification import EvidenceVerifier
from tests.unit.test_evidence import _audit, _FakeSandbox, _input, _prepared
from tests.unit.test_verdicts import _observation, _role

# Line numbers are part of the expectations: keep this module's layout exact. Every
# binding below was checked against coverage.py's own statement lines for this text.
MODULE = '''\
"""Module docstring
over two lines."""
import functools


@functools.lru_cache(
    maxsize=None
)
@functools.wraps(print)
def target(
    root,
    # interior comment
    path=(
        "x"
    ),
):  # trailing
    """Docstring
    over two lines."""
    # before the first statement

    global STATE
    value = (
        root
        + path
    )
    if (value and
            path):
        return value
    else:
        return None


async def waiting(path):
    """Only one line."""
    return path


def oneliner(path): return path


def docstring_only():
    """Nothing else."""


def annotated(path):
    count: int
    return path


@functools.total_ordering
class Holder(
    object,
):
    """Class docstring
    over two lines."""

    def method(self, path):
        return path


def outer(path):
    @functools.wraps(print)
    def inner(value):
        return value
    try:
        result = inner(path)
    except (ValueError,
            TypeError):
        result = None
    finally:
        pass
    match result:
        case "a":
            return 1
    with open(
        path
    ) as handle:
        return handle
    first = (
        1); second = (
        2)
'''


def _bound(line: int, text: str = MODULE) -> int:
    return bind_target_line(text, line)


# --- the def rule: a function header or docstring binds to the body's first statement --


@pytest.mark.parametrize(
    ("line", "bound"),
    [
        (6, 22),  # first decorator
        (7, 22),  # decorator argument continuation
        (8, 22),  # decorator closing line
        (9, 22),  # second decorator
        (10, 22),  # def line
        (11, 22),  # signature continuation
        (12, 22),  # interior comment of the signature
        (13, 22),  # default value spanning lines
        (16, 22),  # header colon line with a trailing comment
        (17, 22),  # docstring first line
        (18, 22),  # docstring continuation; ``global`` on line 21 is skipped
    ],
)
def test_a_function_header_or_docstring_binds_to_its_first_body_statement(line, bound):
    assert _bound(line) == bound


def test_an_async_function_and_a_method_bind_to_their_body():
    assert _bound(33) == 35  # async def, skipping its one-line docstring
    assert _bound(34) == 35  # that docstring
    assert _bound(57) == 58  # a method in a class body


def test_a_decorated_nested_function_binds_to_its_own_body():
    assert _bound(61) == 63  # outer's def: its first statement is the nested def at 63
    assert _bound(62) == 64  # the nested decorator
    assert _bound(63) == 64  # the nested def line


def test_a_function_whose_body_cannot_be_decided_keeps_its_line():
    assert _bound(38) == 38  # a one-line def: the body statement is on the same line
    assert _bound(41) == 41  # a body that holds only a docstring
    assert _bound(42) == 42  # ... and that docstring
    assert _bound(45) == 45  # a body that begins with an annotation-only declaration


# --- the continuation rule: a statement's other lines bind to its first line ----------


@pytest.mark.parametrize(
    ("line", "bound"),
    [
        (23, 22),  # multi-line assignment
        (24, 22),
        (25, 22),
        (52, 51),  # class bases continuation
        (53, 51),  # class header colon line
        (76, 75),  # with header continuation
        (77, 75),
        (68, 67),  # except clause continuation
        (80, 79),  # two statements joined by ``;`` form one logical line
        (81, 79),
    ],
)
def test_a_continuation_line_binds_to_its_statement_first_line(line, bound):
    assert _bound(line) == bound


# --- everything else stays the declared line ------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        3,  # an executable statement line
        22,  # the first line of a multi-line statement
        1,  # a module docstring
        2,
        50,  # a class decorator
        54,  # a class docstring
        55,
        56,  # a blank line between statements
        19,  # a comment line between the header and the first statement
        20,  # a blank line there
        21,  # a ``global`` declaration
        29,  # an ``else:`` clause line
        67,  # an ``except`` clause line
        70,  # a ``finally:`` clause line
        72,  # a ``match`` header
        73,  # a ``case`` line
        75,  # the first line of a multi-line ``with`` header
        27,  # an ``if`` header continuation that holds the second ``and`` operand
    ],
)
def test_other_lines_are_kept(line):
    assert _bound(line) == line


def test_an_unparseable_module_keeps_the_line():
    assert bind_target_line("def broken(:\n    return 1\n", 1) == 1


def test_a_class_decorator_continuation_binds_to_the_decorator_line():
    text = "@decorate(\n    1\n)\nclass Holder:\n    pass\n"
    assert bind_target_line(text, 2) == 1
    assert bind_target_line(text, 1) == 1


def test_a_module_too_deep_for_the_host_parser_keeps_the_line(monkeypatch):
    import corsair.policies.line_binding as module

    def too_deep(*_args, **_kwargs):
        raise RecursionError

    monkeypatch.setattr(module.ast, "parse", too_deep)
    assert bind_target_line(MODULE, 10) == 10


def test_bom_and_crlf_do_not_shift_the_binding():
    text = "﻿def read(path):\r\n    return path\r\n"
    assert bind_target_line(text, 1) == 2


def test_the_frozen_case01_line_binds_to_itself():
    text = Path("evals/fixtures/case01/source/target.py").read_text(encoding="utf-8")
    request = InvestigationRequest.model_validate_json(
        Path("evals/fixtures/case01/request.json").read_bytes()
    )
    assert request.case.finding.line == 4
    assert bind_target_line(text, 4) == 4


@pytest.mark.parametrize(
    "text",
    [
        "def read(root, path):\n    return path\n",
        (
            'def read(root, path):\n    """Doc."""\n    global STATE\n'
            "    value = (\n        path\n    )\n"
        ),
        (
            "import os\n\n\ndef read(\n    root,\n    path,\n):\n"
            "    # note\n\n    return os.path.join(root, path)\n"
        ),
    ],
)
def test_a_line_derived_for_a_line_less_finding_passes_through_unchanged(text):
    recipe = PythonRecipe(module_file="reader.py", function="read", payload_parameter="path")
    derived = derive_target_line(recipe, text)
    assert derived is not None
    assert bind_target_line(text, derived) == derived


# --- the contract: declared and bound lines are both recorded -------------------------


def test_a_record_without_a_bound_line_binds_to_the_declared_line():
    prepared = _prepared()
    assert prepared.target_line is None
    assert prepared.bound_line == prepared.finding.line == 4
    restored = PreparedCase.model_validate_json(prepared.model_dump_json())
    assert restored.bound_line == 4


def test_a_bound_line_needs_a_declared_line():
    prepared = _prepared()
    payload = prepared.model_dump(mode="json")
    payload["finding"]["line"] = None
    payload["target_line"] = 5
    with pytest.raises(ValidationError, match="needs a declared finding line"):
        PreparedCase.model_validate(payload)


# --- consumers: prepare records the binding, the kernel and verifier use it -----------

READER = (
    "from pathlib import Path\n"
    "\n"
    "def read_file(root, path):\n"
    "    return (Path(root) / path).read_text()\n"
)


class _Sandbox:
    image_id = "sha256:" + "a" * 64

    def image_id_for(self, kind: str) -> str:
        del kind
        return self.image_id


async def test_prepare_records_the_declared_and_the_bound_line(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "reader.py").write_text(READER, encoding="utf-8")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    activities = Activities(
        settings,
        store=store,
        inference=None,  # ty: ignore[invalid-argument-type]
        sources=LocalSourceSnapshots(settings, store),
        sandbox=_Sandbox(),  # ty: ignore[invalid-argument-type]
    )
    recipe = PythonRecipe(
        module_file="reader.py",
        function="read_file",
        payload_parameter="path",
        fixed_kwargs={"root": "/fixtures/allowed"},
    )

    def request(line: int | None) -> InvestigationRequest:
        finding = Finding(title="read", description="test", file="reader.py", line=line)
        return InvestigationRequest(
            case=Case(
                case_id="line-case", finding=finding, source=Source(path="project"), recipe=recipe
            )
        )

    on_def = await ActivityEnvironment().run(activities.prepare, request(3))
    assert (on_def.finding.line, on_def.target_line, on_def.bound_line) == (3, 4, 4)
    on_body = await ActivityEnvironment().run(activities.prepare, request(4))
    assert (on_body.finding.line, on_body.target_line) == (4, 4)
    derived = await ActivityEnvironment().run(activities.prepare, request(None))
    assert derived.line_provenance is LineProvenance.RECIPE_FUNCTION
    assert (derived.finding.line, derived.target_line) == (4, 4)


async def test_the_shared_preparation_binds_exactly_as_the_prepare_activity(tmp_path):
    """verify, replay, preview and the isolated producer call prepare_case directly."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "reader.py").write_text(READER, encoding="utf-8")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    recipe = PythonRecipe(
        module_file="reader.py",
        function="read_file",
        payload_parameter="path",
        fixed_kwargs={"root": "/fixtures/allowed"},
    )
    finding = Finding(title="read", description="test", file="reader.py", line=3)
    case = Case(case_id="line-case", finding=finding, source=Source(path="project"), recipe=recipe)
    activities = Activities(
        settings,
        store=store,
        inference=None,  # ty: ignore[invalid-argument-type]
        sources=LocalSourceSnapshots(settings, store),
        sandbox=_Sandbox(),  # ty: ignore[invalid-argument-type]
    )

    direct = prepare_case(case, settings, store, _prepared().manifest)
    request = InvestigationRequest(case=case)
    via_activity = await ActivityEnvironment().run(activities.prepare, request)

    assert (direct.finding.line, direct.target_line, direct.bound_line) == (3, 4, 4)
    assert (via_activity.target_line, via_activity.bound_line) == (4, 4)

    unbound = case.model_copy(update={"recipe": recipe.model_copy(update={"function": "load"})})
    with pytest.raises(TargetBindingBlocked, match="target_binding function_not_defined"):
        prepare_case(unbound, settings, store, _prepared().manifest)


def _def_line_case() -> PreparedCase:
    """A finding declared on the ``def`` line (3) and bound to its body (4)."""
    prepared = _prepared()
    finding = prepared.finding.model_copy(update={"line": 3})
    return prepared.model_copy(update={"finding": finding, "target_line": 4})


def test_the_kernel_is_decisive_when_both_runs_cover_the_bound_line():
    observation = _observation(
        _role(RoleOutcome.HELD, [1, 3, 4], 0), _role(RoleOutcome.VIOLATION, [1, 3, 4], 1)
    )
    outcome = session_verdict(_def_line_case(), observation, _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_covering_only_the_def_line_is_not_enough_once_bound():
    # The def line runs at import whether or not the function is entered; the bound
    # body line asks that it was. This tightens the gate, never loosens it.
    observation = _observation(
        _role(RoleOutcome.HELD, [1, 3], 0), _role(RoleOutcome.VIOLATION, [1, 3, 4], 1)
    )
    outcome = session_verdict(_def_line_case(), observation, _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.INCONCLUSIVE
    assert outcome.reason == "declared target line not covered in both runs"


def test_a_record_made_before_binding_keeps_the_declared_line_gate():
    unbound = _def_line_case().model_copy(update={"target_line": None})
    observation = _observation(
        _role(RoleOutcome.HELD, [1, 3], 0), _role(RoleOutcome.VIOLATION, [1, 3], 1)
    )
    outcome = session_verdict(unbound, observation, _audit(), FixStatus.NOT_REQUESTED)
    assert outcome.verdict is Verdict.EXPLOIT_DEMONSTRATED


def test_the_verifier_admits_coverage_of_the_bound_line(tmp_path):
    # _FakeSandbox reports covered_lines [4]: the declared def line 3 never appears.
    store = ArtifactStore(tmp_path / "artifacts")
    verifier = EvidenceVerifier(Settings(), store, _FakeSandbox(store))
    request = _input()
    bound = verifier.evaluate(request.model_copy(update={"prepared": _def_line_case()}))
    assert bound.control and bound.control.outcome is RoleOutcome.HELD
    assert bound.adversarial and bound.adversarial.outcome is RoleOutcome.VIOLATION

    unbound_case = _def_line_case().model_copy(update={"target_line": None})
    unbound = verifier.evaluate(_input("unbound").model_copy(update={"prepared": unbound_case}))
    assert unbound.control and unbound.control.outcome is RoleOutcome.INVALID
    assert unbound.control.reason == "relevant source coverage was not observed"


# --- conditional subexpressions: a line that can be skipped is never rebound ----------

# coverage.py reports only line 2 of each multi-line ``return`` below (checked with the
# image's pinned 7.13 under COVERAGE_CORE=sysmon): it reports the statement whether or
# not a short-circuit, conditional or lazy part on a later line ran. Binding such a line
# to line 2 would call it covered when it never executed.
CONDITIONAL = """\
def either(a, b):
    return (a
        or b)


def both(a, b):
    return (a
        and b)


def choose(a, b, c):
    return (a
        if b
        else c)


def kept(xs):
    return [x
        for x in xs
        if x]


def chained(a, b, c):
    return (a <
        b <
        c)


def deferred(a):
    return (lambda: (
        a))


def checked(a):
    assert a, (
        "message")


def called(a, b):
    return max(a,
        b)
"""


@pytest.mark.parametrize(
    "line",
    [
        3,  # ``or`` operand after the first: skipped when ``a`` is truthy
        8,  # ``and`` operand after the first: skipped when ``a`` is falsy
        14,  # ternary ``else`` branch
        19,  # comprehension ``for`` clause: its target is assigned per element only
        20,  # comprehension ``if``: skipped on an empty iterable
        26,  # chained comparison operand after the first comparison
        31,  # lambda body: runs only when the lambda is called
        36,  # assert message: evaluated only when the assertion fails
    ],
)
def test_a_line_inside_a_skippable_subexpression_is_kept(line):
    assert bind_target_line(CONDITIONAL, line) == line


@pytest.mark.parametrize(
    ("line", "bound"),
    [
        (13, 12),  # the ternary test always runs
        (25, 24),  # the first comparison always runs
        (41, 40),  # a plain multi-line call: every argument runs with the statement
    ],
)
def test_a_line_that_always_runs_with_its_statement_still_binds(line, bound):
    assert bind_target_line(CONDITIONAL, line) == bound


def test_a_ternary_body_on_a_continuation_line_is_kept():
    text = "def f(a, b, c):\n    return (\n        a\n        if b\n        else c)\n"
    assert bind_target_line(text, 3) == 3
    assert bind_target_line(text, 4) == 2


def test_a_lazy_lambda_default_in_a_signature_continuation_is_kept():
    text = "def f(a,\n      check=lambda value: (\n          value.run())):\n    return a\n"
    assert bind_target_line(text, 3) == 3  # the lambda body may never run
    assert bind_target_line(text, 2) == 4  # the default itself is part of the header
