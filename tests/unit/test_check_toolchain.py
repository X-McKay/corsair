"""Behavior checks for the stdlib toolchain report run first by `just check`."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_toolchain
from scripts.check_toolchain import PINNED_JUST, Finding, main, satisfies, toolchain_findings

NIX_PYTHON_HOME = "/nix/store/example-python3-3.12.15/bin"


def install_stub_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **versions: str) -> None:
    """Put `--version` stubs on an otherwise empty PATH; real tools never run."""

    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    for tool, output in versions.items():
        stub = bin_path / tool
        stub.write_text(f"#!/bin/sh\necho '{output}'\n")
        stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_path))


def make_project(tmp_path: Path, *, version: str, home: str, providers: bool) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12,<3.14"\n')
    venv = root / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text(f"home = {home}\nversion_info = {version}\n")
    if providers:
        package = venv / f"lib/python{version.rsplit('.', 1)[0]}/site-packages/litellm"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
    return root


def pinned_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, just: str = PINNED_JUST) -> None:
    install_stub_tools(
        tmp_path,
        monkeypatch,
        just=f"just {just}",
        uv="uv 0.13.4 (x86_64-unknown-linux-gnu)",
        docker="Docker version 29.9.1, build v29.9.1",
    )


def by_tool(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.tool: finding for finding in findings}


def test_nix_shell_toolchain_reports_only_ok(tmp_path, monkeypatch):
    pinned_tools(tmp_path, monkeypatch)
    root = make_project(tmp_path, version="3.12.15", home=NIX_PYTHON_HOME, providers=True)

    findings = toolchain_findings(root, f"{NIX_PYTHON_HOME}/python3.12")

    assert [finding.status for finding in findings] == ["ok"] * 5
    assert [finding.tool for finding in findings] == [
        "just",
        "uv",
        "python",
        "providers",
        "docker",
    ]


def test_unpinned_just_fails_with_the_nix_remedy(tmp_path, monkeypatch, capsys):
    pinned_tools(tmp_path, monkeypatch, just="1.47.1")
    root = make_project(tmp_path, version="3.12.15", home=NIX_PYTHON_HOME, providers=True)
    monkeypatch.setenv("UV_PYTHON", f"{NIX_PYTHON_HOME}/python3.12")

    assert main(["--root", str(root)]) == 1

    just_line = capsys.readouterr().out.splitlines()[0]
    assert just_line.startswith("FAIL  just      1.47.1")
    assert "nix develop" in just_line
    assert f"rust-just=={PINNED_JUST}" in just_line


def test_missing_tools_fail_for_just_and_uv_but_only_warn_for_docker(tmp_path, monkeypatch):
    install_stub_tools(tmp_path, monkeypatch)
    root = make_project(tmp_path, version="3.12.15", home=NIX_PYTHON_HOME, providers=True)

    findings = by_tool(toolchain_findings(root, f"{NIX_PYTHON_HOME}/python3.12"))

    assert (findings["just"].status, findings["just"].found) == ("FAIL", "missing")
    assert (findings["uv"].status, findings["uv"].found) == ("FAIL", "missing")
    assert (findings["docker"].status, findings["docker"].found) == ("WARN", "missing")


def test_shell_python_change_warns_that_uv_recreates_venv_without_extras(tmp_path, monkeypatch):
    pinned_tools(tmp_path, monkeypatch)
    root = make_project(
        tmp_path, version="3.13.13", home="/home/dev/uv/cpython-3.13/bin", providers=True
    )

    findings = by_tool(toolchain_findings(root, f"{NIX_PYTHON_HOME}/python3.12"))

    assert findings["python"].status == "WARN"
    assert findings[".venv"].status == "WARN"
    assert "recreates .venv without the providers extra" in findings[".venv"].remedy
    assert "just sync" in findings[".venv"].remedy


def test_nix_venv_outside_the_shell_warns_about_native_libraries(tmp_path, monkeypatch):
    pinned_tools(tmp_path, monkeypatch)
    root = make_project(tmp_path, version="3.12.15", home=NIX_PYTHON_HOME, providers=True)

    findings = by_tool(toolchain_findings(root, None))

    assert findings[".venv"].status == "WARN"
    assert "nix develop" in findings[".venv"].remedy


def test_missing_providers_extra_warns_with_the_sync_remedy(tmp_path, monkeypatch):
    pinned_tools(tmp_path, monkeypatch)
    root = make_project(tmp_path, version="3.12.15", home=NIX_PYTHON_HOME, providers=False)

    findings = by_tool(toolchain_findings(root, f"{NIX_PYTHON_HOME}/python3.12"))

    assert findings["providers"].status == "WARN"
    assert "--all-extras" in findings["providers"].remedy


def test_venv_outside_requires_python_fails(tmp_path, monkeypatch):
    pinned_tools(tmp_path, monkeypatch)
    root = make_project(tmp_path, version="3.11.9", home="/usr/bin", providers=True)

    assert by_tool(toolchain_findings(root, "/usr/bin/python3.11"))["python"].status == "FAIL"


def test_absent_venv_warns_and_skips_venv_dependent_checks(tmp_path, monkeypatch):
    pinned_tools(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12,<3.14"\n')

    findings = by_tool(toolchain_findings(root, None))

    assert (findings["python"].status, findings["python"].found) == ("WARN", "no .venv")
    assert ".venv" not in findings and "providers" not in findings


@pytest.mark.parametrize(
    "version,expected",
    [("3.12.15", True), ("3.13.0", True), ("3.11.9", False), ("3.14.0", False)],
)
def test_requires_python_clauses_compare_by_release_prefix(version, expected):
    assert satisfies(version, ">=3.12,<3.14") is expected


def test_pinned_just_matches_the_justfile_install_comment():
    justfile = (Path(check_toolchain.__file__).parents[1] / "justfile").read_text()

    assert f"rust-just=={PINNED_JUST}" in justfile.splitlines()[0]
