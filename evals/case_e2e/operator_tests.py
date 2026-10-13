"""Operator-written finding tests through the product's own setup, runners, witness and gate, with no model.

Isolates the image-only route below the agent stages for one issue request: `investigation.build` selects the row
and the framework table's entry, `investigation.docker.install` runs the entry's setup on each revision,
`DockerRunners` drives the entry's runner on fresh offline containers, the operator witness probe records the
named target, and `witness_evidence`, `run_evidence` and `assess` decide the gate exactly as the chain does. The
test file, ids, target and expectation are evaluation artifacts supplied here, never agent output, so a result
says whether the route can carry a finding's evidence, not whether an agent finds it. Image evidence, not sandbox
qualification; nothing is retried.

Committed cases (`operator_cases/cases.json`) name a corpus topic, captured as `evals.corpus.issues` does, or two
trees committed with that module's fixed metadata, plus the test file and expectation:

    PYTHONPATH=src:. python -m evals.case_e2e.operator_tests --case <name> --images <json> --evidence <new dir>
"""
import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.composition.evidence import run_evidence
from corsair.core.disposition import AssessmentEvidence, ExpectedFailure, ObservationPlan, assess
from corsair.investigate import images
from corsair.investigation.build import Refused, build
from corsair.investigation.docker import DockerRunners, install
from corsair.investigation.request import IssueRequest
from corsair.nodes.witness import Calibration, witness_evidence
from corsair.ports.test_runner import ApprovedPatch, PatchFile, WitnessRequest
from evals.corpus.cases import load as load_corpus
from evals.corpus.issues import SCHEMA, capture, commit

CASES = Path(__file__).with_name("operator_cases")


def run(request: IssueRequest, evidence: Path, prepared: dict[str, str], roots: tuple[Path, ...], *, path: str,
        content: bytes, ids: tuple[str, str], target: tuple[str, str], effect: str, failure_type: str,
        assertion_lines: tuple[int, ...], safe_behavior: str, timeout: int = 600) -> dict:
    """One request into the new directory `evidence`; returns the record also written as `result.json`."""
    evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
    try:
        investigation = build(request, evidence / "trees", prepared, roots=roots, timeout=timeout)
    except Refused as refused:
        result = {"stopped_at": "admission", "reason": str(refused)}
        (evidence / "result.json").write_text(json.dumps(result, indent=2))
        return result
    revisions = {}
    for revision, commit in investigation.commits.items():
        dependencies = evidence / "dependencies" / revision
        install(investigation.harness, investigation.image, investigation.trees[revision], commit, dependencies,
                evidence / "setup" / revision)
        revisions[revision] = (investigation.trees[revision], dependencies.resolve(), commit)
    patch = ApprovedPatch((PatchFile(path, content),), (path,))
    witness = WitnessRequest(target[0], target[1], effect)
    plan = ObservationPlan(control_test_id=ids[0], security_test_id=ids[1], expected_safe_behavior=safe_behavior,
                           expected_failure=ExpectedFailure(exception_type=failure_type, path=path,
                                                            function=ids[1].replace("#", "::").split("::")[-1],
                                                            assertion_lines=assertion_lines),
                           frozen_patch_sha256=patch.sha256)
    runs, witnesses = {}, {}
    (evidence / "artifacts").mkdir(mode=0o700)
    with ExitStack() as containers, LocalArtifacts(evidence / "artifacts", max_bytes=8 << 20) as store:
        runners = DockerRunners(investigation.harness, investigation.image, revisions, store, timeout,
                                evidence / "runs", containers)
        for revision in ("baseline", "candidate"):
            observed = runners(revision).run(patch, control_test_id=ids[0], security_test_id=ids[1],
                                             discovery_command=investigation.harness.config.command,
                                             operation=uuid4(), witness=witness)
            found = witness_evidence(observed.witness, witness, ids[1], planned_safe_behavior=safe_behavior,
                                     control=Calibration(ids[0], effect))
            runs[revision], witnesses[revision] = observed, found
    gate = assess(AssessmentEvidence(plan=plan, **{
        revision: (run_evidence(runs[revision], environment=investigation.case.environment_identity,
                                witness=witnesses[revision].witness, sandbox_events=witnesses[revision].sandbox_events),)
        for revision in ("baseline", "candidate")}))
    result = {
        "row": investigation.row, "framework": investigation.framework.name, "image": investigation.image,
        "commits": investigation.commits, "patch_sha256": patch.sha256,
        "test_file_sha256": sha256(content).hexdigest(),
        "runs": {revision: {
            "failure_layer": observed.failure_layer, "detail": observed.detail, "cleanup": observed.cleanup,
            "discovery": observed.discovery and observed.discovery.status,
            "outcomes": observed.execution and [(c.test_id, c.outcome, c.failure and (c.failure.type, c.failure.path,
                                                                                       c.failure.line))
                                                for c in observed.execution.cases],
            "witness_capture": observed.witness and observed.witness.status,
            "witness": witnesses[revision].witness and witnesses[revision].witness.model_dump(),
            "witness_reason": witnesses[revision].reason,
            "record": observed.witness and observed.witness.record.decode("utf-8", "replace")}
            for revision, observed in runs.items()},
        "gate": gate.permitted.model_dump(), "limitations": [item.code for item in gate.limitations]}
    (evidence / "result.json").write_text(json.dumps(result, indent=2, default=str))
    return result


def case_request(name: str, root: Path) -> IssueRequest:
    """A committed case as an issue request whose repository is created under `root`."""
    spec = json.loads((CASES / "cases.json").read_text())[name]
    if "corpus" in spec:
        corpus = {case.case_id: case for case in load_corpus()}[spec["corpus"]]
        if corpus.split != "development":
            raise SystemExit(f"{name}: held-out corpus topics are never run here")
        issue, _ = capture(corpus, root)
        return IssueRequest.model_validate(issue)
    repository = root / name / "repository.git"
    repository.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", "--bare", "--template=", str(repository)], check=True)
    revisions = [commit(repository, {p.relative_to(tree).as_posix(): p.read_bytes()
                                     for p in sorted(tree.rglob("*")) if p.is_file()})
                 for tree in (CASES / name / "baseline", CASES / name / "candidate")]
    return IssueRequest.model_validate({
        "schema": SCHEMA, "issue": {"provider": "manual", **spec["issue"], "format": "markdown"},
        "repository": repository.as_uri(), "revision": revisions[0], "fixed_revision": revisions[1]})


def run_case(name: str, evidence: Path, prepared: dict[str, str], timeout: int = 600) -> dict:
    """A committed case into the new directory `evidence`, its expectation joined to the result."""
    spec = json.loads((CASES / "cases.json").read_text())[name]
    evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
    request = case_request(name, evidence / "case")
    path, local = spec["test"]
    result = run(request, evidence / "run", prepared, (evidence / "case",), path=path,
                 content=(CASES / name / local).read_bytes(), ids=(spec["control"], spec["security"]),
                 target=tuple(spec["target"]), effect=spec["effect"], failure_type=spec["failure_type"],
                 assertion_lines=tuple(spec["assertion_lines"]), safe_behavior=spec.get("safe_behavior", "no_file_open"),
                 timeout=timeout)
    joined = {"case": name, "expected": spec["expected"], "gate": result.get("gate"),
              "matches": result.get("gate") == spec["expected"], "limitations": result.get("limitations"),
              "stopped_at": result.get("stopped_at"), "reason": result.get("reason")}
    (evidence / "case.json").write_text(json.dumps(joined, indent=2))
    return joined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--case", action="append", help="a committed case name (repeatable)")
    which.add_argument("--issue-json", type=Path)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--roots", type=Path, action="append", default=[])
    parser.add_argument("--test-file", help="<workspace path>:<local file>")
    parser.add_argument("--control")
    parser.add_argument("--security")
    parser.add_argument("--target", help="<path>:<symbol>")
    parser.add_argument("--effect")
    parser.add_argument("--failure-type")
    parser.add_argument("--assertion-line", type=int, action="append")
    parser.add_argument("--safe-behavior", default="no_file_open")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.case:
        for name in args.case:
            print(json.dumps(run_case(name, args.evidence.resolve() / name, images(args.images), args.timeout)))
        return 0
    path, local = args.test_file.split(":", 1)
    request = IssueRequest.model_validate_json(args.issue_json.read_text())
    result = run(request, args.evidence.resolve(), images(args.images), tuple(r.resolve() for r in args.roots),
                 path=path, content=Path(local).read_bytes(), ids=(args.control, args.security),
                 target=tuple(args.target.split(":", 1)), effect=args.effect, failure_type=args.failure_type,
                 assertion_lines=tuple(args.assertion_line), safe_behavior=args.safe_behavior, timeout=args.timeout)
    print(json.dumps({"gate": result.get("gate"), "limitations": result.get("limitations"),
                      "stopped_at": result.get("stopped_at"), "reason": result.get("reason")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
