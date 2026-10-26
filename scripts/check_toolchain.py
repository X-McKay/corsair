#!/usr/bin/env python3
"""Report developer tool versions against the ones the locked Nix shell provides.

Standard library only, so it runs before `just sync` and under any Just:
`python3 scripts/check_toolchain.py`. A FAIL line exits 1; WARN lines explain a
divergence that makes later commands fail confusingly, and exit 0.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Versions `nix develop` provides from flake.lock. Update with a deliberate flake.lock change.
PINNED_JUST = "1.58.0"
NIX_SHELL_PREFIXES = {"uv": "0.13", "python": "3.12", "docker": "29.9"}
ENTER_NIX = "run `nix develop` first"
JUST_REMEDY = f"{ENTER_NIX} (or `uv tool install rust-just=={PINNED_JUST}`)"
SYNC_REMEDY = "run `just sync` (uv sync --locked --all-extras)"
VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)+")


@dataclass(frozen=True)
class Finding:
    status: str
    tool: str
    found: str
    expected: str
    remedy: str = ""

    def line(self) -> str:
        text = f"{self.status:<5} {self.tool:<9} {self.found:<10} expected {self.expected}"
        return f"{text}; {self.remedy}" if self.remedy else text


def tool_version(tool: str) -> str | None:
    """Return the first dotted version printed by `TOOL --version`, or None if absent."""

    binary = shutil.which(tool)
    if binary is None:
        return None
    process = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    match = VERSION_PATTERN.search(process.stdout + process.stderr)
    return match.group(0) if match else "unknown"


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def satisfies(version: str, requirement: str) -> bool:
    """Evaluate the simple `>=X.Y,<X.Y` form used by pyproject's requires-python."""

    actual = version_tuple(version)
    for clause in (part.strip() for part in requirement.split(",")):
        match = re.fullmatch(r"(>=|<=|==|<|>)\s*([\d.]+)", clause)
        if match is None:
            raise ValueError(f"unsupported requires-python clause {clause!r}")
        operator, bound = match.groups()
        limit = version_tuple(bound)
        width = actual[: len(limit)]
        if not {
            ">=": width >= limit,
            "<=": width <= limit,
            "==": width == limit,
            "<": width < limit,
            ">": width > limit,
        }[operator]:
            return False
    return True


def check_just() -> Finding:
    version = tool_version("just")
    if version == PINNED_JUST:
        return Finding("ok", "just", version, PINNED_JUST)
    return Finding("FAIL", "just", version or "missing", PINNED_JUST, JUST_REMEDY)


def check_prefixed(tool: str, missing_status: str, remedy: str) -> Finding:
    version = tool_version(tool)
    expected = f"{NIX_SHELL_PREFIXES[tool]}.x"
    if version is None:
        return Finding(missing_status, tool, "missing", expected, remedy)
    if version_tuple(version)[:2] == version_tuple(NIX_SHELL_PREFIXES[tool]):
        return Finding("ok", tool, version, expected)
    return Finding("WARN", tool, version, expected, f"differs from the Nix shell; {ENTER_NIX}")


def venv_config(root: Path) -> dict[str, str] | None:
    path = root / ".venv/pyvenv.cfg"
    if not path.is_file():
        return None
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def check_venv_python(root: Path, config: dict[str, str] | None) -> Finding:
    requirement = tomllib.loads((root / "pyproject.toml").read_text())["project"]["requires-python"]
    expected = f"{NIX_SHELL_PREFIXES['python']}.x ({requirement})"
    if config is None:
        return Finding("WARN", "python", "no .venv", expected, SYNC_REMEDY)
    version = config.get("version_info", config.get("version", "unknown"))
    if not VERSION_PATTERN.fullmatch(version) or not satisfies(version, requirement):
        return Finding("FAIL", "python", version, expected, f"recreate it: {SYNC_REMEDY}")
    if version_tuple(version)[:2] != version_tuple(NIX_SHELL_PREFIXES["python"]):
        return Finding("WARN", "python", version, expected, f"differs from CI; {ENTER_NIX}")
    return Finding("ok", "python", version, expected)


def check_venv_owner(config: dict[str, str] | None, uv_python: str | None) -> Finding | None:
    """Explain the .venv swaps that happen when moving in and out of the Nix shell."""

    if config is None:
        return None
    home = config.get("home", "")
    if uv_python is not None and Path(uv_python).parent != Path(home):
        return Finding(
            "WARN",
            ".venv",
            "other python",
            f"{uv_python} (UV_PYTHON)",
            f"the next `uv run` recreates .venv without the providers extra; {SYNC_REMEDY}",
        )
    if uv_python is None and home.startswith("/nix/store/"):
        return Finding(
            "WARN",
            ".venv",
            "Nix python",
            "this shell's python",
            "native wheels (duckdb) need the Nix shell's libraries; "
            f"{ENTER_NIX}, or recreate it here: `uv venv --clear && uv sync --locked --all-extras`",
        )
    return None


def check_providers_extra(root: Path, config: dict[str, str] | None) -> Finding | None:
    if config is None:
        return None
    if any((root / ".venv/lib").glob("python*/site-packages/litellm/__init__.py")):
        return Finding("ok", "providers", "installed", "installed")
    return Finding("WARN", "providers", "missing", "installed", f"LiteLLM is absent; {SYNC_REMEDY}")


def toolchain_findings(root: Path, uv_python: str | None) -> list[Finding]:
    config = venv_config(root)
    findings = [
        check_just(),
        check_prefixed("uv", "FAIL", f"install uv or {ENTER_NIX}"),
        check_venv_python(root, config),
        check_venv_owner(config, uv_python),
        check_providers_extra(root, config),
        check_prefixed("docker", "WARN", f"Docker recipes need a client; {ENTER_NIX}"),
    ]
    return [finding for finding in findings if finding is not None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args(argv)
    findings = toolchain_findings(arguments.root, os.environ.get("UV_PYTHON"))
    for finding in findings:
        print(finding.line())
    return 1 if any(finding.status == "FAIL" for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
