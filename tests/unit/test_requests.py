"""Request loading retains lexical source paths for secure SCM admission."""

from pathlib import Path

from corsair.adapters.scm.requests import normalize_request_sources
from corsair.contracts import Case, Finding, InvestigationRequest, PythonRecipe, Source
from corsair.entrypoints.requests import load_investigation_request


def request_with_sources(source: str, fixed_source: str | None = None) -> InvestigationRequest:
    return InvestigationRequest(
        case=Case(
            case_id="case01",
            finding=Finding(title="claim", description="claim", file="target.py"),
            source=Source(path=source),
            fixed_source=None if fixed_source is None else Source(path=fixed_source),
            recipe=PythonRecipe(
                module_file="target.py", function="probe", payload_parameter="value"
            ),
        )
    )


def test_request_source_normalization_is_relative_to_its_request_file(tmp_path: Path, monkeypatch):
    request_dir = tmp_path / "requests"
    request_dir.mkdir()
    source_target = tmp_path / "admitted-source"
    source_target.mkdir()
    source_link = request_dir / "source-link"
    source_link.symlink_to(source_target, target_is_directory=True)
    request_file = request_dir / "request.json"
    request_file.write_text(request_with_sources("source-link", "fixed-source").model_dump_json())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    request = load_investigation_request(request_file)

    assert request.case.source.path == str(source_link.absolute())
    assert request.case.fixed_source is not None
    assert request.case.fixed_source.path == str((request_dir / "fixed-source").absolute())
    assert Path(request.case.source.path).is_symlink()
    assert Path(request.case.source.path).resolve() == source_target


def test_request_source_normalization_preserves_absolute_source_spelling(tmp_path: Path):
    request_file = tmp_path / "request.json"
    absolute_source = str(tmp_path / "source-link")
    request = normalize_request_sources(request_with_sources(absolute_source), request_file)

    assert request.case.source.path == absolute_source
