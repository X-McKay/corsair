"""Run each v2 runtime matrix row's canary pair on its image and record whether the row's D8 table holds.

A row is admitted (``evidence: image-only``) only when its known-passing canary classifies as ``passed`` and its
known-failing canary as ``assertion_failed``, through the row's own run template and exit-code map (redesign
section 13, D8). This tool records that fact; it never edits the matrix, which stays operator-owned.

Each canary runs in a fresh ``docker run --network none`` container labelled ``corsair.v2=1`` and removed after,
with the probe protocol's environment: ``CORSAIR_MARKER_DIR`` (a mounted directory the test writes ``start`` and
``end`` into) and ``CORSAIR_TOKEN`` (a fresh random string per run). The canary tree is the skill's
``canary/project`` (optional) plus ``canary/pass`` or ``canary/fail``, whose one file is the test; the test is
always named ``test_canary``. A row's ``canary_setup`` argv, if any, runs first in its own offline container.

Usage: uv run --locked python tools/v2_canary.py [--row ID ...] [--matrix PATH] [--timeout SECONDS]
Evidence: <repo>/.runs/canary/<row>.json; exit status 1 when any selected row is not admitted.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corsair.v2 import matrix  # noqa: E402
from corsair.v2.contracts import ProbeFacts  # noqa: E402
from corsair.v2.outcome import classify, exit_class  # noqa: E402

SKILLS = ROOT / "src/corsair/v2/skills/frameworks"
EVIDENCE = ROOT / ".runs/canary"
WORKDIR = "/work"
MARKERS = "/corsair/markers"
TEST_NAME = "test_canary"
EXPECTED = {"pass": "passed", "fail": "assertion_failed"}
TAIL = 6_000


def docker_base(name: str) -> list[str]:
    return ["docker", "run", "--name", name, "--label", "corsair.v2=1", "--label", "corsair.v2.tool=canary",
            "--network", "none", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=512",
            "--memory=4g", "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-w", WORKDIR]


def remove(name: str) -> bool:
    """Remove the named container and confirm it is gone."""
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    left = subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{name}$"], capture_output=True, text=True)
    return left.returncode == 0 and not left.stdout.strip()


def run_container(args: list[str], name: str, timeout: int) -> dict:
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout)
        result = {"exit_code": done.returncode, "timed_out": False,
                  "stdout": done.stdout.decode(errors="replace"), "stderr": done.stderr.decode(errors="replace")}
    except subprocess.TimeoutExpired as expired:
        result = {"exit_code": None, "timed_out": True,
                  "stdout": (expired.stdout or b"").decode(errors="replace"),
                  "stderr": (expired.stderr or b"").decode(errors="replace")}
    result["cleanup_confirmed"] = remove(name)
    return result


def test_file(kind_dir: Path) -> str:
    files = [p for p in kind_dir.rglob("*") if p.is_file()]
    if len(files) != 1:
        raise SystemExit(f"{kind_dir} must hold exactly one test file, found {len(files)}")
    return files[0].relative_to(kind_dir).as_posix()


def run_canary(row: matrix.Row, kind: str, scratch: Path, timeout: int) -> dict:
    canary = SKILLS / row.skill / "canary"
    tree, markers = scratch / kind / "tree", scratch / kind / "markers"
    markers.mkdir(parents=True)
    if (canary / "project").is_dir():
        shutil.copytree(canary / "project", tree)
    shutil.copytree(canary / kind, tree, dirs_exist_ok=True)
    file = test_file(canary / kind)
    record: dict = {"test_file": file, "test_name": TEST_NAME, "expected": EXPECTED[kind]}
    mount = ["-v", f"{tree}:{WORKDIR}"]
    if row.canary_setup:
        name = f"corsair-v2-canary-setup-{uuid.uuid4().hex[:12]}"
        setup = run_container(docker_base(name) + mount + [row.image, *row.canary_setup], name, timeout)
        record["setup"] = {"argv": list(row.canary_setup), "exit_code": setup["exit_code"],
                           "timed_out": setup["timed_out"], "cleanup_confirmed": setup["cleanup_confirmed"],
                           "stdout_tail": setup["stdout"][-TAIL:], "stderr_tail": setup["stderr"][-TAIL:]}
        if setup["exit_code"] != 0:
            record["outcome"] = None
            record["detail"] = "canary setup failed; the test did not run"
            return record
    argv = matrix.fill(row.run_template, test_file=file, test_name=TEST_NAME)
    token = secrets.token_hex(16)
    name = f"corsair-v2-canary-{uuid.uuid4().hex[:12]}"
    env = ["-e", f"CORSAIR_MARKER_DIR={MARKERS}", "-e", f"CORSAIR_TOKEN={token}"]
    result = run_container(docker_base(name) + mount + ["-v", f"{markers}:{MARKERS}"] + env + [row.image, *argv],
                           name, timeout)
    output = result["stdout"] + result["stderr"]
    facts = ProbeFacts(exit_code=result["exit_code"], exit_class=exit_class(result["exit_code"], row.exit_codes),
                       timed_out=result["timed_out"], start_marker=(markers / "start").is_file(),
                       end_marker=(markers / "end").is_file(), token_in_output=token in output)
    record.update({"argv": list(argv), "facts": facts.model_dump(mode="json"), "outcome": classify(facts).value,
                   "cleanup_confirmed": result["cleanup_confirmed"],
                   "stdout_tail": result["stdout"][-TAIL:], "stderr_tail": result["stderr"][-TAIL:]})
    return record


def image_id(image: str) -> str | None:
    done = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True)
    return done.stdout.strip() or None if done.returncode == 0 else None


def check_row(row: matrix.Row, timeout: int) -> dict:
    evidence: dict = {"row": row.id, "image": row.image, "image_id": image_id(row.image), "framework": row.framework,
                      "skill": row.skill, "run_template": list(row.run_template),
                      "exit_codes": {str(k): v.value for k, v in row.exit_codes.items()},
                      "matrix_evidence": row.evidence,
                      "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "canaries": {}}
    if evidence["image_id"] is None:
        evidence.update(admitted=False, detail="image not present locally")
        return evidence
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{row.id}-", dir=EVIDENCE) as scratch:
        for kind in ("pass", "fail"):
            evidence["canaries"][kind] = run_canary(row, kind, Path(scratch), timeout)
    evidence["admitted"] = all(evidence["canaries"][kind]["outcome"] == EXPECTED[kind] for kind in EXPECTED)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", type=Path, default=matrix.DEFAULT_MATRIX)
    parser.add_argument("--row", action="append", default=[], help="Row id to check (default: every row)")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per container")
    args = parser.parse_args()
    rows = [row for row in matrix.load(args.matrix) if not args.row or row.id in args.row]
    if args.row and len(rows) != len(set(args.row)):
        parser.error("unknown row id")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    failed = 0
    for row in rows:
        evidence = check_row(row, args.timeout)
        (EVIDENCE / f"{row.id}.json").write_text(json.dumps(evidence, indent=2) + "\n")
        outcomes = {kind: record.get("outcome") for kind, record in evidence["canaries"].items()}
        print(f"{row.id}: {'admitted' if evidence['admitted'] else 'NOT admitted'} {outcomes}"
              f"{'' if evidence['admitted'] else ' ' + evidence.get('detail', '')}")
        failed += not evidence["admitted"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
