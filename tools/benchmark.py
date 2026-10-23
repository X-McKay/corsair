#!/usr/bin/env python3
"""Generate and optionally exercise the deterministic polyglot benchmark fixtures.

Generation is the default and makes no pass or model-accuracy claim.  ``--run-kernel``
replays the checked-in trusted reference submission in the selected sandbox without an
LLM or blind auditor.  ``--native-smoke`` is explicitly local trusted-fixture
execution, *not* isolation and never evidence for a Corsair verdict.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

# ``python tools/benchmark.py`` gives sys.path only the tools directory.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.polyglot import LANGUAGES, generate
from corsair.adapters.artifacts.filesystem import ArtifactStore, write_json
from corsair.adapters.frameworks import framework
from corsair.adapters.sandbox import sandboxes
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel
from corsair.domain.policy import terminal_verdict
from corsair.domain.verification import Fix, Label, Submission
from corsair.runtime import matrix


def _report_path(value: str) -> Path | None:
    return None if value == "-" else Path(value).resolve()


def _write_report(report: dict[str, Any], output: str) -> None:
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    target = _report_path(output)
    if target is None:
        print(text, end="")
    else:
        write_json(target, report)
        print(f"wrote JSON report to {target}", file=sys.stderr)


def _provenance(path: Path) -> dict[str, Any]:
    return json.loads((path / "provenance.json").read_text(encoding="utf-8"))


def _required_tools(provenance: dict[str, Any]) -> tuple[str, ...]:
    language = provenance["language"]
    command = tuple(provenance["command"])
    table = {
        "python": ("python",),
        "javascript": ("node", "npm"),
        "typescript": ("node", "npm"),
        "ruby": ("bundle", "ruby", "rake"),
        "perl": ("perl", "make", "prove"),
        "cpp": ("g++", "make"),
    }
    if language == "java":
        return ("java", "mvn") if provenance["build_command"].startswith("mvn ") else ("java", "gradle")
    if language == "cpp" and provenance["build_command"].startswith("cmake "):
        return ("g++", "cmake")
    return tuple(dict.fromkeys((*table[language], command[0])))


def _invoke(command: list[str], payload: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*command, payload], cwd=cwd, text=True, capture_output=True, timeout=30, check=False
    )


def _native_one(path: Path) -> dict[str, Any]:
    """Run a trusted fixture locally.  This is intentionally not a sandbox verdict."""
    provenance = _provenance(path)
    missing = [tool for tool in _required_tools(provenance) if shutil.which(tool) is None]
    row: dict[str, Any] = {
        "case": str(path),
        "mode": "native-not-isolated",
        "language": provenance["language"],
    }
    if missing:
        return {
            **row,
            "status": "blocked",
            "reason": f"required local tool(s) unavailable: {', '.join(missing)}",
        }
    command = list(provenance["command"])
    expected = {"vulnerable": ("ALLOW", "ALLOW"), "fixed": ("ALLOW", "DENY")}
    evidence: list[dict[str, str]] = []
    try:
        for revision, outcomes in expected.items():
            source = path / revision
            build = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + provenance["build_command"]],
                cwd=source,
                text=True,
                capture_output=True,
                timeout=300,
                check=False,
            )
            if build.returncode != 0:
                return {
                    **row,
                    "status": "error",
                    "reason": f"{revision} build exited {build.returncode}",
                    "stderr_tail": build.stderr[-1000:],
                }
            for role, payload, want in (
                ("control", provenance["control"], outcomes[0]),
                ("exploit", provenance["exploit"], outcomes[1]),
            ):
                result = _invoke(command, payload, source)
                got = result.stdout.strip()
                evidence.append({"revision": revision, "role": role, "decision": got})
                if result.returncode != 0 or got != want:
                    return {
                        **row,
                        "status": "error",
                        "reason": f"{revision} {role}: expected {want}, got {got!r}",
                        "stderr_tail": result.stderr[-1000:],
                        "evidence": evidence,
                    }
    except subprocess.TimeoutExpired as error:
        return {
            **row,
            "status": "error",
            "reason": f"local trusted fixture timed out: {error}",
            "evidence": evidence,
        }
    return {
        **row,
        "status": "passed",
        "evidence": evidence,
        "note": "trusted fixture smoke passed locally; this is native execution, not container isolation",
    }


def _docker_ready() -> str | None:
    if shutil.which("docker") is None:
        return "docker CLI unavailable"
    try:
        checked = subprocess.run(["docker", "info"], text=True, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"docker availability check failed: {error}"
    return None if checked.returncode == 0 else f"docker daemon unavailable: {checked.stderr[-500:].strip()}"


async def _kernel_one(path: Path, root: Path, index: int, docker_problem: str | None) -> dict[str, Any]:
    started = time.monotonic()
    provenance = _provenance(path)
    row: dict[str, Any] = {
        "case": str(path),
        "language": provenance["language"],
        "auditor": "not configured (no model call)",
    }
    if docker_problem:
        return {**row, "status": "blocked", "reason": docker_problem}
    case = load_case(path)
    selected = matrix.select(case)
    if selected is None:
        return {**row, "status": "blocked", "reason": "no runtime matrix row matches this source tree"}
    try:
        submission = Submission.model_validate_json(
            (path / "reference-submission.json").read_text(encoding="utf-8")
        )
        backend = sandboxes()
        row["mode"] = f"{backend.provider}-kernel-trusted-reference"
        kernel = Kernel(
            backend,
            selected,
            case,
            artifacts=ArtifactStore(root / "kernel-artifacts" / f"{index:04d}"),
            run_id=f"poly-{uuid.uuid4().hex[:8]}",
            framework=framework(selected.framework),
        )
        evaluation = await kernel.evaluate(submission)
    except Exception as error:  # e.g. image / framework adapter not yet available
        return {
            **row,
            "status": "blocked",
            "reason": f"kernel setup/execution unavailable: {type(error).__name__}: {error}",
        }
    verdict = evaluation.verdict or terminal_verdict(evaluation.gate, 1)
    passed = (
        verdict.label is Label.LIKELY_EXPLOITABLE
        and verdict.fix is Fix.VERIFIED
        and all(run.cleanup_confirmed is True for run in evaluation.runs)
    )
    return {
        **row,
        "status": "passed" if passed else "error",
        "verdict": verdict.label,
        "fix": verdict.fix,
        "gate": evaluation.gate.stage,
        "reason": evaluation.gate.reason,
        "runtime_row": selected.id,
        "image": selected.image,
        "run_id": kernel.run_id,
        "tree_sha256": case.revision.tree_sha256,
        "submission_sha256": submission.sha256,
        "duration_s": time.monotonic() - started,
        "evaluation": evaluation.model_dump(mode="json"),
        "note": "trusted reference only; this measures fixture/runtime mechanics, not model accuracy",
    }


async def _kernel_runs(paths: list[Path], root: Path, workers: int) -> list[dict[str, Any]]:
    docker_problem = _docker_ready()
    semaphore = asyncio.Semaphore(workers)
    completed = 0

    async def one(index: int, path: Path) -> dict[str, Any]:
        nonlocal completed
        async with semaphore:
            row = await asyncio.to_thread(lambda: asyncio.run(_kernel_one(path, root, index, docker_problem)))
            write_json(root / "results" / f"{index:04d}.json", row)
            completed += 1
            print(
                f"[{completed}/{len(paths)}] {path.parent.name}/{path.name}: {row['status']} "
                f"{row.get('gate', '')}",
                file=sys.stderr,
                flush=True,
            )
            return row

    return await asyncio.gather(*(one(index, path) for index, path in enumerate(paths, 1)))


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    requested = tuple(dict.fromkeys(args.language or LANGUAGES))
    paths = generate(root, requested)
    selected = paths[: args.limit] if args.limit is not None else paths
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "schema": "corsair-polyglot/report/1",
        "root": str(root),
        "generated": True,
        "generation": catalog,
        "selected_case_directories": len(selected),
        "selected_runnable_revision_variants": len(selected) * 2,
        "workers": args.workers,
        "execution": "not requested",
        "model_accuracy_claim": "none",
        "notes": [
            "A case directory has vulnerable and fixed revisions.",
            "Counts are revision-variants, not a count of unique CVEs.",
            "oracle.json is evaluator-only and is not supplied to corsair.application.cases.load_case.",
        ],
        "generator_sha256": hashlib.sha256(Path(generate.__code__.co_filename).read_bytes()).hexdigest(),
    }
    if args.generate_only and (args.run_kernel or args.native_smoke):
        raise SystemExit("--generate-only cannot be combined with execution flags")
    rows: list[dict[str, Any]] = []
    if args.native_smoke:
        report["execution"] = "native-not-isolated trusted fixture smoke"
        rows = [_native_one(path) for path in selected]
    elif args.run_kernel:
        report["execution"] = f"{sandboxes().provider} trusted reference replay without auditor/model"
        rows = asyncio.run(_kernel_runs(selected, root, args.workers))
    if rows:
        report["results"] = rows
        report["result_counts"] = dict(sorted(Counter(row["status"] for row in rows).items()))
        report["per_language"] = {
            language: dict(Counter(row["status"] for row in rows if row["language"] == language))
            for language in requested
        }
    _write_report(report, args.output)
    # Generation alone is not a passed execution.  Once execution is requested, blocked and unexpected outcomes fail.
    if not rows:
        return 0
    return 0 if all(row["status"] == "passed" for row in rows) else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", required=True, help="user-selected temporary output directory for generated fixtures"
    )
    parser.add_argument(
        "--language",
        action="append",
        choices=LANGUAGES,
        help="language to generate; repeatable; defaults to every supported language",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="maximum generated case directories to execute"
    )
    parser.add_argument("--output", default="-", help="JSON report path, or - for stdout")
    parser.add_argument(
        "--generate-only", action="store_true", help="only generate; make no execution/pass claim"
    )
    parser.add_argument(
        "--run-kernel",
        action="store_true",
        help="replay trusted references through the CORSAIR_SANDBOX provider (default docker)",
    )
    parser.add_argument(
        "--native-smoke", action="store_true", help="run trusted local fixtures; explicitly not isolation"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        choices=range(1, 17),
        metavar="1..16",
        help="maximum concurrent sandbox evaluations; results retain stable input order",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
