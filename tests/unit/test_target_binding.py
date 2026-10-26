"""The pre-model target_binding gate: every branch of the pure check, and its activity."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    Case,
    Finding,
    InvestigationRequest,
    LineProvenance,
    PythonRecipe,
    Source,
)
from corsair.policies import line_binding
from corsair.policies.target_binding import (
    TargetBindingReason,
    bind_target_line,
    derive_target_line,
    target_binding,
)
from corsair.settings import Settings
from corsair.steps.activities import Activities

READER = (
    "from pathlib import Path\n\n"
    "def read_file(root, path):\n"
    "    return (Path(root) / path).read_text()\n"
)


def _finding(line: int | None = 4) -> Finding:
    return Finding(title="read", description="test", file="reader.py", line=line)


def _recipe(**update: object) -> PythonRecipe:
    fields: dict[str, object] = {
        "module_file": "reader.py",
        "function": "read_file",
        "payload_parameter": "path",
        "fixed_kwargs": {"root": "/fixtures/allowed"},
    }
    fields.update(update)
    return PythonRecipe.model_validate(fields)


def _reason(text: str | None, *, line: int | None = 4, **recipe: object):
    failure = target_binding(_finding(line), _recipe(**recipe), text)
    return None if failure is None else failure.reason


def test_a_bound_target_passes():
    assert target_binding(_finding(), _recipe(), READER) is None


def test_the_frozen_case_fixtures_bind():
    request = InvestigationRequest.model_validate_json(
        Path("evals/fixtures/case01/request.json").read_bytes()
    )
    text = Path("evals/fixtures/case01/source/target.py").read_text(encoding="utf-8")
    recipe = request.case.recipe
    assert isinstance(recipe, PythonRecipe)
    assert target_binding(request.case.finding, recipe, text) is None


def test_an_absent_module_is_file_absent():
    assert _reason(None) is TargetBindingReason.FILE_ABSENT


def test_a_finding_without_a_line_cannot_bind():
    assert _reason(READER, line=None) is TargetBindingReason.LINE_MISSING


@pytest.mark.parametrize(
    ("text", "line", "expected"),
    [
        (READER, 5, TargetBindingReason.LINE_OUT_OF_RANGE),
        (READER.rstrip("\n"), 4, None),  # no trailing newline still has four lines
        ("x = 1\r\ny = 2\r\n", 3, TargetBindingReason.LINE_OUT_OF_RANGE),
        # A form feed is not a source line break, unlike in str.splitlines().
        ("x = 1\x0cy = 2\n", 2, TargetBindingReason.LINE_OUT_OF_RANGE),
    ],
)
def test_a_line_beyond_the_module_is_out_of_range(text, line, expected):
    failure = target_binding(_finding(line), _recipe(function="x"), text)
    if expected is None:
        assert failure is None or failure.reason is not TargetBindingReason.LINE_OUT_OF_RANGE
    else:
        assert failure is not None and failure.reason is expected
        assert str(line) in failure.detail


@pytest.mark.parametrize("text", ["def read_file(root, path:\n    pass\n\n\n", "x = 1\x00\n\n\n\n"])
def test_an_unparseable_module_is_reported(text):
    assert _reason(text) is TargetBindingReason.MODULE_UNPARSEABLE


def test_a_utf8_bom_does_not_make_the_module_unparseable():
    assert _reason("﻿" + READER) is None


def test_a_module_too_deep_for_the_host_parser_is_left_to_the_kernel(monkeypatch):
    import corsair.policies.target_binding as module

    def deep(*_args, **_kwargs):
        raise RecursionError

    monkeypatch.setattr(module.ast, "parse", deep)
    assert _reason(READER) is None


def test_a_missing_function_is_not_defined():
    failure = target_binding(_finding(), _recipe(function="write_file"), READER)
    assert failure is not None
    assert failure.reason is TargetBindingReason.FUNCTION_NOT_DEFINED
    assert str(failure).startswith("target_binding function_not_defined: write_file")


@pytest.mark.parametrize(
    "text",
    [
        "from helpers import *\n\n\n\n",
        "def __getattr__(name):\n    return print\n\n\n",
        "from helpers import read_file\n\n\n\n",
        "import read_file\n\n\n\n",
        "read_file = print\n\n\n\n",
        "class read_file:\n    pass\n\n\n",
        "if True:\n    def read_file(root, path):\n        pass\n\n",
        READER + "\ndef read_file(root, path, extra):\n    pass\n",
        "import functools\n\n@functools.cache\ndef read_file():\n    pass\n",
    ],
)
def test_a_binding_static_analysis_cannot_decide_passes(text):
    """Only a certain violation blocks; the run-time gates stay the authority."""
    assert _reason(text) is None


def test_an_async_function_cannot_be_called_synchronously():
    text = READER.replace("def read_file", "async def read_file")
    assert _reason(text) is TargetBindingReason.FUNCTION_ASYNC


def test_an_unknown_payload_parameter_is_reported():
    assert _reason(READER, payload_parameter="filename") is (
        TargetBindingReason.PAYLOAD_PARAMETER_UNKNOWN
    )


def test_a_positional_only_payload_parameter_is_not_a_keyword():
    text = "def read_file(path, /, root):\n    pass\n\n\n"
    assert _reason(text) is TargetBindingReason.PAYLOAD_PARAMETER_UNKNOWN


def test_an_unknown_fixed_kwarg_is_reported():
    failure = target_binding(_finding(), _recipe(fixed_kwargs={"root": "/r", "mode": "r"}), READER)
    assert failure is not None
    assert failure.reason is TargetBindingReason.FIXED_KWARG_UNKNOWN
    assert "'mode'" in failure.detail


def test_var_keyword_accepts_any_payload_and_fixed_names():
    text = "def read_file(**options):\n    pass\n\n\n"
    assert _reason(text, payload_parameter="anything", fixed_kwargs={"other": 1}) is None


@pytest.mark.parametrize(
    "text",
    [
        "def read_file(root, path, encoding):\n    pass\n\n\n",
        "def read_file(root, path, *, encoding):\n    pass\n\n\n",
        "def read_file(handle, /, root, path, **rest):\n    pass\n\n\n",
    ],
)
def test_a_required_parameter_the_recipe_never_supplies_is_unbound(text):
    assert _reason(text) is TargetBindingReason.REQUIRED_PARAMETER_UNBOUND


@pytest.mark.parametrize(
    "text",
    [
        "def read_file(root, path, encoding='utf-8'):\n    pass\n\n\n",
        "def read_file(root, path, *args, encoding='utf-8', **rest):\n    pass\n\n\n",
        "def read_file(handle=None, /, root='', path=''):\n    pass\n\n\n",
    ],
)
def test_defaulted_parameters_need_not_be_supplied(text):
    assert _reason(text) is None


# --- a line-less finding binds to the recipe function's first body statement ----


def _executed_lines(text: str, function: str) -> tuple[set[int], set[int]]:
    """Line events of ``text`` at import, and then during one call of ``function``."""
    code = compile(text, "derived_target.py", "exec")
    phase: set[int] = set()

    def tracer(frame, event, _arg):
        if frame.f_code.co_filename == "derived_target.py" and event == "line":
            phase.add(frame.f_lineno)
        return tracer

    namespace: dict[str, object] = {}
    sys.settrace(tracer)
    try:
        exec(code, namespace)
        imported, phase = set(phase), set()
        callable_ = namespace[function]
        assert callable(callable_)
        callable_(root="/fixtures/allowed", path="hello.txt")
    finally:
        sys.settrace(None)
    return imported, phase


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (READER, 4),
        ('def read_file(root, path):\n    """Read one file."""\n    return path\n', 3),
        (
            'def read_file(root, path):\n    """Read\n    one file."""\n\n    return path\n',
            5,
        ),
        ("def read_file(\n    root,\n    path,\n):\n    return path\n", 5),
        ("COUNT = 0\n\ndef read_file(root, path):\n    global COUNT\n    COUNT += 1\n", 5),
        ("def read_file(root, path):\n    size: int\n    return path\n", 3),
        ("def read_file(root, path):\n    pass\n", 2),
        ("\ufeffdef read_file(root, path):\n    return path\n", 2),
        ("def read_file(root, path):\r\n    return path\r\n", 2),
    ],
)
def test_a_line_is_derived_from_a_plain_top_level_def(text, expected):
    assert derive_target_line(_recipe(), text) == expected
    # The derived line passes the pre-model gate and is in range.
    assert target_binding(_finding(expected), _recipe(), text) is None


@pytest.mark.parametrize(
    "text",
    [
        "from pathlib import Path\n\ndef read_file(root, path):\n    return Path(root) / path\n",
        'def read_file(root, path):\n    """Read one file."""\n    return path\n',
        "COUNT = 0\n\ndef read_file(root, path):\n    global COUNT\n    COUNT += 1\n",
        "def read_file(root, path):\n    size: int\n    return path\n",
        "def read_file(root, path):\n    pass\n",
    ],
)
def test_the_derived_line_runs_on_the_call_and_not_at_import(text):
    """Why the def line is never chosen: importing the module already executes it,
    so its coverage would not show that the recipe call reached the function."""
    line = derive_target_line(_recipe(), text)
    assert line is not None
    imported, called = _executed_lines(text, "read_file")
    assert line not in imported
    assert line in called
    def_line = next(n for n, row in enumerate(text.splitlines(), 1) if "def read_file" in row)
    assert def_line in imported


@pytest.mark.parametrize(
    "text",
    [
        "def read_file(root, path): return path\n",  # the body shares the def line
        "def read_file(\n    root, path): return path\n",  # ...or the signature's last
        'def read_file(root, path):\n    """Only a docstring."""\n',
        "def read_file(root, path):\n    global COUNT\n",
        "import functools\n\n@functools.cache\ndef read_file(root, path):\n    return path\n",
        "async def read_file(root, path):\n    return path\n",
        "if True:\n    def read_file(root, path):\n        return path\n",
        "class Reader:\n    def read_file(self, root, path):\n        return path\n",
        "def read_file(root, path):\n    return 1\n\ndef read_file(root, path):\n    return 2\n",
        "def read_file(root, path):\n    return path\n\nread_file = print\n",
        "from os import *\n\ndef read_file(root, path):\n    return path\n",
        "def read_file(root, path):\n    return path\n\ndef __getattr__(name):\n    return 1\n",
        "def load_file(root, path):\n    return path\n",
        "def read_file(root, path)\n    return path\n",
    ],
)
def test_a_line_is_not_derived_unless_it_is_certain(text):
    assert derive_target_line(_recipe(), text) is None


def test_a_module_too_deep_to_parse_derives_no_line(monkeypatch):
    def too_deep(*_args, **_kwargs):
        raise RecursionError

    monkeypatch.setattr("corsair.policies.target_binding.ast.parse", too_deep)
    assert derive_target_line(_recipe(), READER) is None


def test_an_underivable_line_missing_reason_names_the_recipe_function():
    failure = target_binding(_finding(None), _recipe(), "def read_file(root, path): pass\n")
    assert failure is not None and failure.reason is TargetBindingReason.LINE_MISSING
    assert "could be derived from recipe function read_file" in str(failure)


# --- a line the module import executes cannot show the recipe call ran ----------

SCOPES = (
    "import os\n"  # 1  module
    "TABLE = {'a': os.environ.get('X')}\n"  # 2  module
    "\n"
    "class Config:\n"  # 4  module
    "    LIMIT = 3\n"  # 5  class body
    "\n"
    "    def method(self):\n"  # 7  header, binds to 8
    "        return self.LIMIT\n"  # 8  method body
    "\n"
    "def traced(function):\n"  # 10 header, binds to 11
    "    return function\n"  # 11
    "\n"
    "@traced\n"  # 13 decorator, binds to 15
    "def helper(path):\n"  # 14 header, binds to 15
    "    return TABLE.get(path)\n"  # 15 a helper the entry calls
    "\n"
    "def read_file(root, path):\n"  # 17 header, binds to 18
    "    def nested(value):\n"  # 18 runs on the call
    "        return helper(value)\n"  # 19 nested function body
    "    class Local:\n"  # 20 a class statement inside the entry
    "        SIZE = 1\n"  # 21 its body runs on the call, not at import
    "    return nested(path)\n"  # 22
    "\n"
    "def one_line(x): return x\n"  # 24 module: the body shares the def line
    "if TABLE:\n"  # 25 module
    "    FLAG = True\n"  # 26 module, inside a compound statement
)


@pytest.mark.parametrize(
    ("line", "scope"),
    [(1, "module"), (2, "module"), (4, "module"), (5, "class body"), (24, "module")]
    + [(25, "module"), (26, "module")],
)
def test_a_line_that_runs_at_import_is_blocked(line: int, scope: str):
    failure = target_binding(_finding(line), _recipe(), SCOPES)
    assert failure is not None, scope
    assert failure.reason is TargetBindingReason.LINE_RUNS_AT_IMPORT
    assert f"line {line}" in failure.detail


@pytest.mark.parametrize(
    "line",
    [
        7,  # a method header binds to the method body
        8,  # a method body
        13,  # a decorator binds to the decorated function's body
        14,
        15,  # a helper the entry calls: lexical containment in the entry is not required
        17,
        18,
        19,  # a nested function body
        20,
        21,  # a class body inside a function runs on the call
        22,
        3,  # a blank line is never reported: the run-time gates keep it INCONCLUSIVE
    ],
)
def test_a_line_inside_any_function_is_allowed(line: int):
    assert target_binding(_finding(line), _recipe(), SCOPES) is None


def test_the_import_time_gate_agrees_with_the_interpreter_line_events():
    """Every blocked line is a line event of the import itself, and the only import-time
    line events allowed are function bodies the import calls (here ``traced``, applied
    as a decorator): the gate decides by static scope and never follows calls."""
    imported, _called = _executed_lines(SCOPES, "read_file")
    allowed_at_import: set[int] = set()
    for line in range(1, SCOPES.count("\n") + 1):
        bound = line_binding.bind_target_line(SCOPES, line)
        failure = target_binding(_finding(line), _recipe(), SCOPES)
        blocked = failure is not None and failure.reason is TargetBindingReason.LINE_RUNS_AT_IMPORT
        if blocked:
            assert bound in imported, line
        elif bound in imported:
            allowed_at_import.add(bound)
    assert allowed_at_import == {11}


def test_the_verifier_review_case_line_is_blocked():
    """The external review's reproduction: a module-level table the entry reads."""
    text = (
        "import os\nTABLE = {'a': os.environ.get('X')}\n\ndef unrelated():\n    return 2\n\n"
        "def entry(payload):\n    return TABLE.get(payload)\n"
    )
    recipe = PythonRecipe(module_file="reader.py", function="entry", payload_parameter="payload")
    failures = {line: target_binding(_finding(line), recipe, text) for line in (2, 5, 7, 8)}
    reasons = {line: failure and failure.reason for line, failure in failures.items()}
    assert reasons == {
        2: TargetBindingReason.LINE_RUNS_AT_IMPORT,
        5: None,
        7: None,
        8: None,
    }


# --- the prepare activity turns a failure into a non-retryable PREPARE_BLOCKED ----


class _Sandbox:
    image_id = "sha256:" + "a" * 64

    def image_id_for(self, kind: str) -> str:
        del kind
        return self.image_id


def _activities(
    tmp_path: Path, content: str, *, line: int | None = 4
) -> tuple[Activities, InvestigationRequest]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "reader.py").write_text(content, encoding="utf-8")
    settings = Settings(source_root=str(tmp_path), artifact_root=str(tmp_path / "artifacts"))
    store = ArtifactStore(settings.artifact_root)
    activities = Activities(
        settings,
        store=store,
        inference=None,  # ty: ignore[invalid-argument-type]
        sources=LocalSourceSnapshots(settings, store),
        sandbox=_Sandbox(),  # ty: ignore[invalid-argument-type]
    )
    case = Case(
        case_id="binding-case",
        finding=_finding(line),
        source=Source(path="project"),
        recipe=_recipe(),
    )
    return activities, InvestigationRequest(case=case)


async def test_prepare_admits_a_bound_target(tmp_path):
    activities, request = _activities(tmp_path, READER)
    prepared = await ActivityEnvironment().run(activities.prepare, request)
    assert prepared.case_id == "binding-case"


async def test_prepare_blocks_an_unbound_target_before_any_model_call(tmp_path):
    activities, request = _activities(tmp_path, READER.replace("read_file", "load_file"))
    with pytest.raises(ApplicationError) as rejected:
        await ActivityEnvironment().run(activities.prepare, request)
    assert rejected.value.type == "PREPARE_BLOCKED"
    assert rejected.value.non_retryable
    assert "target_binding function_not_defined" in str(rejected.value)


async def test_prepare_blocks_an_import_time_line_before_any_model_call(tmp_path):
    activities, request = _activities(tmp_path, "ROOT = '/srv'\n" + READER, line=1)
    with pytest.raises(ApplicationError) as rejected:
        await ActivityEnvironment().run(activities.prepare, request)
    assert rejected.value.type == "PREPARE_BLOCKED"
    assert rejected.value.non_retryable
    assert "target_binding line_runs_at_import" in str(rejected.value)


async def test_prepare_binds_a_line_less_finding_to_the_recipe_function(tmp_path):
    activities, request = _activities(tmp_path, READER, line=None)
    prepared = await ActivityEnvironment().run(activities.prepare, request)
    assert prepared.finding.line == 4
    assert prepared.line_provenance is LineProvenance.RECIPE_FUNCTION
    # The excerpt centres on the derived line, exactly as for a declared one.
    assert "4:     return (Path(root) / path).read_text()" in prepared.source_excerpt
    # Everything else about the request finding is carried unchanged.
    assert prepared.finding.model_copy(update={"line": None}) == request.case.finding


async def test_prepare_keeps_a_declared_line_and_records_it_as_declared(tmp_path):
    activities, request = _activities(tmp_path, READER)
    prepared = await ActivityEnvironment().run(activities.prepare, request)
    assert prepared.finding == request.case.finding
    assert prepared.line_provenance is LineProvenance.DECLARED


async def test_prepare_never_derives_a_line_from_the_finding_description(tmp_path):
    """The description is untrusted narrative: naming another function or a line
    in it never moves the derived line off the recipe function."""
    content = READER + "\n\ndef load_file(root, path):\n    return path\n"
    activities, request = _activities(tmp_path, content, line=None)
    finding = request.case.finding.model_copy(
        update={"description": "The bug is in load_file() at line 9 of reader.py."}
    )
    request = request.model_copy(
        update={"case": request.case.model_copy(update={"finding": finding})}
    )
    prepared = await ActivityEnvironment().run(activities.prepare, request)
    assert prepared.finding.line == 4


async def test_prepare_still_blocks_a_line_less_finding_it_cannot_bind(tmp_path):
    activities, request = _activities(
        tmp_path, "def read_file(root, path): return path\n", line=None
    )
    with pytest.raises(ApplicationError) as rejected:
        await ActivityEnvironment().run(activities.prepare, request)
    assert rejected.value.type == "PREPARE_BLOCKED"
    assert "target_binding line_missing" in str(rejected.value)


def test_bind_target_line_keeps_a_declared_line_and_derives_only_a_missing_one():
    """The one binding prepare and the intake dry run share."""
    declared = _finding(3)
    assert bind_target_line(declared, _recipe(), READER) == (declared, LineProvenance.DECLARED)
    derived, provenance = bind_target_line(_finding(None), _recipe(), READER)
    assert (derived.line, provenance) == (4, LineProvenance.RECIPE_FUNCTION)
    one_line = "def read_file(root, path): pass\n"
    unbound, provenance = bind_target_line(_finding(None), _recipe(), one_line)
    assert (unbound.line, provenance) == (None, LineProvenance.DECLARED)
