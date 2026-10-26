"""The pre-model target_binding gate: every branch of the pure check, and its activity."""

from __future__ import annotations

from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from corsair.adapters.scm.local import LocalSourceSnapshots
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Case, Finding, InvestigationRequest, PythonRecipe, Source
from corsair.policies.target_binding import TargetBindingReason, target_binding
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
    assert target_binding(request.case.finding, request.case.recipe, text) is None


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


# --- the prepare activity turns a failure into a non-retryable PREPARE_BLOCKED ----


class _Sandbox:
    image_id = "sha256:" + "a" * 64

    def image_id_for(self, recipe_kind: str) -> str:
        del recipe_kind  # The double runs one trusted image regardless of recipe kind.
        return self.image_id


def _activities(tmp_path: Path, content: str) -> tuple[Activities, InvestigationRequest]:
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
        finding=_finding(),
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
