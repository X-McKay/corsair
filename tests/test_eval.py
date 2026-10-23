"""The eval command is a release gate for both the finding and its fix."""
import argparse
import hashlib
import json
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from corsair import benchmark as benchmark_module, cli
from corsair.benchmark import verify_references
from corsair.kernel import RESULT_DIR
from tests.fakes import FakeSandboxes
from tests.test_kernel import CASE


@pytest.mark.anyio
@pytest.mark.parametrize("label,fix,exit_code", [
    ("LIKELY_EXPLOITABLE", "verified", 0),
    ("INCONCLUSIVE", "verified", 1),
    ("LIKELY_EXPLOITABLE", "not_verified", 1),
])
async def test_eval_fails_on_label_or_fix_regressions(tmp_path, monkeypatch, label, fix, exit_code):
    @asynccontextmanager
    async def models(config):
        yield {}

    async def investigate(case, args, models):
        return {"verdict": {"label": label, "fix": fix}, "submissions": [], "run_id": "scripted"}

    monkeypatch.setattr(cli, "load_provider_config", lambda path: None)
    monkeypatch.setattr(cli, "agent_models", models)
    monkeypatch.setattr(cli, "_investigate_one", investigate)
    args = argparse.Namespace(provider="unused", cases=[str(CASE)], runs=str(tmp_path), max_submissions=4)
    assert await cli._eval(args) == exit_code
    report = json.loads(next(tmp_path.glob("eval-*.json")).read_text())
    assert report["cases"][0]["correct"] is (exit_code == 0)


@pytest.mark.anyio
@pytest.mark.parametrize("outcome,label,exit_code", [
    ("violated", "LIKELY_EXPLOITABLE", 0),
    ("holds", "LIKELY_NOT_EXPLOITABLE", 0),
    ("errored", "INCONCLUSIVE", 1),
])
async def test_verify_exit_status_requires_a_decisive_label(tmp_path, monkeypatch, outcome, label, exit_code):
    from functools import partial
    from corsair.kernel import Kernel
    from tests.fakes import FakeSandboxes, Script
    from tests.test_kernel import HAPPY, accept

    fake = FakeSandboxes({**HAPPY, ("vulnerable", "exploit"): Script(
        outcome, "AssertionError" if outcome == "violated" else "ValueError" if outcome == "errored" else None)})
    monkeypatch.setattr(cli, "sandboxes", lambda: fake)
    monkeypatch.setattr(cli, "Kernel", partial(Kernel, auditor=accept))
    args = argparse.Namespace(case=str(CASE), submission=str(CASE / "reference-submission.json"),
                              runs=str(tmp_path), run_id="verify-exit", provider=None)
    actual = await cli._verify(args)
    record = json.loads((tmp_path / "verify-exit/run.json").read_text())
    assert record["verdict"]["label"] == label
    assert actual == exit_code


@pytest.mark.anyio
@pytest.mark.parametrize("version", [None, "corsair-lite/differential-probe/1"])
async def test_verify_rejects_stale_submission_before_constructing_a_sandbox(tmp_path, monkeypatch, capsys, version):
    data = json.loads((CASE / "reference-submission.json").read_text())
    if version is None:
        data.pop("contract_version", None)
    else:
        data["contract_version"] = version
    path = tmp_path / "stale-submission.json"
    path.write_text(json.dumps(data))

    def forbidden_backend():
        pytest.fail("stale submissions must be rejected before sandbox construction")

    monkeypatch.setattr(cli, "sandboxes", forbidden_backend)
    args = argparse.Namespace(case=str(CASE), submission=str(path), runs=str(tmp_path / "runs"),
                              run_id="stale", provider=None)

    assert await cli._verify(args) == 2
    error = capsys.readouterr().err
    assert "contract_version" in error and "corsair-lite/differential-probe/2" in error
    assert "Boolean" in error
    assert not (tmp_path / "runs").exists()


@pytest.mark.anyio
@pytest.mark.parametrize("label,exit_code", [
    ("LIKELY_EXPLOITABLE", 0),
    ("LIKELY_NOT_EXPLOITABLE", 0),
    ("INCONCLUSIVE", 1),
    ("ERROR", 1),
    ("UNABLE_TO_RUN", 1),
])
async def test_investigate_exit_status_requires_a_decisive_label(tmp_path, monkeypatch, label, exit_code):
    from corsair.case import load_case
    from corsair.kernel import Fix, Verdict

    @asynccontextmanager
    async def models(config):
        yield {}

    async def investigate(case, args, models):
        rule = {"LIKELY_EXPLOITABLE": "K1", "LIKELY_NOT_EXPLOITABLE": "K4",
                "INCONCLUSIVE": "K3", "UNABLE_TO_RUN": "K2", "ERROR": "K0"}[label]
        verdict = Verdict(label=label, rule=rule, reason="scripted kernel disposition", fix=Fix.NOT_APPLICABLE)
        return cli._record(tmp_path / "investigate-exit", load_case(CASE), None, verdict, (),
                           mode="investigate", extra={})

    monkeypatch.setattr(cli, "load_provider_config", lambda path: None)
    monkeypatch.setattr(cli, "agent_models", models)
    monkeypatch.setattr(cli, "_investigate_one", investigate)
    args = argparse.Namespace(case=str(CASE), provider="unused")
    assert await cli._investigate(args) == exit_code


def qualification_fixture(tmp_path: Path) -> Path:
    from tests.test_corpus import VALID_CORPUS, corpus_fixture, read_manifest, write_manifest

    root = corpus_fixture(tmp_path)
    data = read_manifest(root)
    case = data["cases"][0]
    case["status"] = "candidate"
    case["runtime"] = "pytest-cpython312"
    case["runtime_image_id"] = "sha256:" + "9" * 64
    case["expected"]["vulnerable"]["reason_code"] = "EXPLOIT_EXPECTATION_MET"
    case["expected"]["fixed"]["reason_code"] = "INVARIANT_PRESERVED"
    write_manifest(root, data)
    (root / "benchmarks/dataset/receipts").mkdir()
    return root


class QualificationFake(FakeSandboxes):
    """One fresh full-image-id fake per qualification attempt."""

    def __init__(self, scenario):
        super().__init__(scenario)

    def resolve_image(self, reference):
        return "sha256:" + "9" * 64

    def _probe(self, name):
        result = super()._probe(name)
        path = f"{RESULT_DIR}/coverage.json"
        if path in self._files[name]:
            coverage = json.loads(self._files[name][path])
            if "/work/documents.py" in coverage["files"]:
                coverage["files"]["/work/target.py"] = coverage["files"].pop("/work/documents.py")
                self._files[name][path] = json.dumps(coverage).encode()
        return result


@pytest.mark.anyio
async def test_three_fresh_reference_replays_publish_immutable_receipts_without_manifest_mutation(tmp_path):
    from tests.test_kernel import HAPPY
    from tests.test_corpus import checked

    root = qualification_fixture(tmp_path)
    manifest_path = root / "benchmarks/dataset/manifest.json"
    before = manifest_path.read_bytes()
    backends = []

    def backend_factory():
        backend = QualificationFake(dict(HAPPY))
        backends.append(backend)
        return backend

    instants = iter(datetime(2026, 10, 23, 10, 0, second, tzinfo=timezone.utc) for second in range(6))
    report = await verify_references(
        root=root,
        manifest_path=manifest_path,
        eval_set="development",
        attempts=3,
        runs_root=root / ".runs/lite",
        receipts_root=root / "benchmarks/dataset/receipts",
        backend_factory=backend_factory,
        now=lambda: next(instants),
        id_factory=lambda: "qualification-fixed-id",
        corpus_validator=checked,
    )

    assert report.ok
    assert len(report.cases) == 1
    assert [attempt.attempt for attempt in report.cases[0].attempts] == [1, 2, 3]
    assert [attempt.outcome for attempt in report.cases[0].attempts] == ["complete"] * 3
    assert report.cases[0].admission_ready is False  # independent review is deliberately never manufactured
    assert manifest_path.read_bytes() == before
    assert len(backends) == 3
    assert all(backend.labelled() == [] for backend in backends)
    records = [json.loads((root / attempt.path).read_text()) for attempt in report.cases[0].attempts]
    assert [record["attempt"] for record in records] == [1, 2, 3]
    assert len({record["qualification_run_id"] for record in records}) == 1
    assert all(len(record["roles"]) == 4 and record["audit_mode"] == "trusted_reference"
               for record in records)
    serialized = json.dumps(records)
    assert "oracle.json" not in serialized and str(root) not in serialized


@pytest.mark.anyio
async def test_reference_replay_uses_manifest_fixed_revision_target_lines(tmp_path):
    from corsair.corpus import _region_sha256
    from tests.fakes import Script
    from tests.test_corpus import checked, read_manifest, write_manifest
    from tests.test_kernel import HAPPY

    root = qualification_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["target"]["fixed_lines"] = [5]
    data["cases"][0]["source_pair"]["fixed"]["affected_region_sha256"] = _region_sha256(
        root / "cases/cs-1001/fixed/target.py", (5,))
    write_manifest(root, data)
    scenario = {
        **HAPPY,
        ("fixed", "control"): Script("holds", covered_lines=(5,)),
        ("fixed", "exploit"): Script("holds", covered_lines=(5,)),
    }

    report = await verify_references(
        root=root, manifest_path=root / "benchmarks/dataset/manifest.json",
        eval_set="development", attempts=1, runs_root=root / ".runs/lite",
        receipts_root=root / "benchmarks/dataset/receipts",
        backend_factory=lambda: QualificationFake(scenario), corpus_validator=checked)

    assert report.ok
    receipt = json.loads((root / report.cases[0].attempts[0].path).read_text())
    assert [(role["revision"], role["covered_lines"]) for role in receipt["roles"]] == [
        ("vulnerable", [4]), ("vulnerable", [4]), ("fixed", [5]), ("fixed", [5])]


@pytest.mark.anyio
async def test_infrastructure_failure_blocks_admission_and_keeps_sanitized_evidence(tmp_path):
    from tests.fakes import Script
    from tests.test_kernel import HAPPY
    from tests.test_corpus import checked

    root = qualification_fixture(tmp_path)
    scenario = {**HAPPY, ("vulnerable", "exploit"): Script("timeout")}
    report = await verify_references(
        root=root,
        manifest_path=root / "benchmarks/dataset/manifest.json",
        eval_set="development",
        attempts=3,
        runs_root=root / ".runs/lite",
        receipts_root=root / "benchmarks/dataset/receipts",
        backend_factory=lambda: QualificationFake(scenario),
        now=lambda: datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc),
        id_factory=lambda: "qualification-infra",
        corpus_validator=checked,
    )

    assert not report.ok and not report.cases[0].admission_ready
    first = report.cases[0].attempts[0]
    assert first.outcome == "infrastructure"
    record = json.loads((root / first.path).read_text())
    assert record["failure_code"] == "KERNEL_INFRASTRUCTURE"
    assert record["roles"] and record["cleanup_confirmed"] is True
    serialized = json.dumps(record)
    assert "timed out" not in serialized and str(root) not in serialized and "oracle.json" not in serialized


def test_benchmark_verify_cli_uses_manifest_set_and_attempt_count(tmp_path, monkeypatch, capsys):
    from corsair.benchmark import QualificationAttempt, QualificationCaseReport, QualificationReport

    captured = {}

    async def verify(**kwargs):
        captured.update(kwargs)
        attempt = QualificationAttempt(attempt=1, outcome="complete", path="benchmarks/dataset/receipts/x.json",
                                       sha256="a" * 64)
        case = QualificationCaseReport(case_id="cs-1001", family_id="cf-1001",
                                       case_revision_sha256="b" * 64, attempts=(attempt,),
                                       admission_ready=False, admission_code="REPLAY_TRIO_REQUIRED")
        return QualificationReport(dataset_version="fixture-1", eval_set=kwargs["eval_set"],
                                   qualification_run_id="run-1", cases=(case,))

    monkeypatch.setattr(cli, "verify_references", verify)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["benchmark-verify", "--manifest", "selected.json", "--eval-set", "conformance",
                     "--attempts", "1", "--runs", "artifacts", "--receipts", "receipts"]) == 0
    assert captured["manifest_path"] == Path("selected.json")
    assert captured["eval_set"] == "conformance" and captured["attempts"] == 1
    assert captured["runs_root"] == Path("artifacts") and captured["receipts_root"] == Path("receipts")
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True and output["admission_ready"] == 0


@pytest.mark.anyio
@pytest.mark.parametrize("artifact", ["oracle.json", "reference-submission.json", "vulnerable/target.py"])
async def test_reference_replay_hash_drift_fails_before_sandbox_construction(tmp_path, artifact):
    from tests.test_corpus import checked

    root = qualification_fixture(tmp_path)
    path = root / "cases/cs-1001" / artifact
    path.write_bytes(path.read_bytes() + b"\n# drift\n")
    constructed = False

    def backend_factory():
        nonlocal constructed
        constructed = True
        pytest.fail("artifact drift must fail before sandbox construction")

    with pytest.raises(ValueError):
        await verify_references(
            root=root, manifest_path=root / "benchmarks/dataset/manifest.json",
            eval_set="development", attempts=1, runs_root=root / ".runs/lite",
            receipts_root=root / "benchmarks/dataset/receipts", backend_factory=backend_factory,
            corpus_validator=checked)
    assert not constructed


@pytest.mark.anyio
async def test_reference_kernel_boundary_receives_only_case_and_submission(tmp_path, monkeypatch):
    from corsair.corpus import _region_sha256
    from corsair.case import Case
    from corsair.kernel import Submission
    from tests.fakes import Script
    from tests.test_corpus import checked, read_manifest, write_manifest
    from tests.test_kernel import HAPPY

    root = qualification_fixture(tmp_path)
    data = read_manifest(root)
    data["cases"][0]["target"]["fixed_lines"] = [5]
    data["cases"][0]["source_pair"]["fixed"]["affected_region_sha256"] = _region_sha256(
        root / "cases/cs-1001/fixed/target.py", (5,))
    write_manifest(root, data)
    real_kernel = benchmark_module.Kernel
    seen = []

    class BoundaryKernel:
        def __init__(self, backend, row, case, **kwargs):
            assert isinstance(case, Case)
            serialized = json.dumps(case.model_dump(mode="json"))
            assert all(word not in serialized for word in
                       ("expected_label", "oracle", "rights", "family_id", "review_receipt", "fixed_lines"))
            assert kwargs["fixed_target_lines"] == (5,)
            self.inner = real_kernel(backend, row, case, **kwargs)
            self.runtime_image_id = self.inner.runtime_image_id

        async def evaluate(self, submission):
            assert isinstance(submission, Submission)
            serialized = submission.model_dump_json()
            assert all(word not in serialized for word in
                       ("expected_label", "oracle", "rights", "family_id", "fixed_lines"))
            seen.append((self.inner.case, submission))
            return await self.inner.evaluate(submission)

    monkeypatch.setattr(benchmark_module, "Kernel", BoundaryKernel)
    report = await verify_references(
        root=root, manifest_path=root / "benchmarks/dataset/manifest.json",
        eval_set="development", attempts=1, runs_root=root / ".runs/lite",
        receipts_root=root / "benchmarks/dataset/receipts",
        backend_factory=lambda: QualificationFake({
            **HAPPY,
            ("fixed", "control"): Script("holds", covered_lines=(5,)),
            ("fixed", "exploit"): Script("holds", covered_lines=(5,)),
        }), corpus_validator=checked)
    assert report.ok and len(seen) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(("resolved_image", "failure_code"), [
    (None, "RUNTIME_IMAGE_UNRESOLVED"),
    ("sha256:" + "d" * 64, "RUNTIME_IMAGE_MISMATCH"),
])
async def test_reference_replay_fails_closed_when_the_current_image_cannot_match_the_manifest_pin(
        tmp_path, resolved_image, failure_code):
    from tests.test_corpus import checked
    from tests.test_kernel import HAPPY

    root = qualification_fixture(tmp_path)

    class CurrentImageFake(QualificationFake):
        def resolve_image(self, reference):
            return resolved_image

        def _probe(self, name):
            pytest.fail("a missing or mismatched runtime image must fail before role execution")

    report = await verify_references(
        root=root, manifest_path=root / "benchmarks/dataset/manifest.json",
        eval_set="development", attempts=3, runs_root=root / ".runs/lite",
        receipts_root=root / "benchmarks/dataset/receipts",
        backend_factory=lambda: CurrentImageFake(dict(HAPPY)), corpus_validator=checked)

    assert not report.ok
    assert len(report.cases[0].attempts) == 1
    attempt = report.cases[0].attempts[0]
    assert attempt.outcome == "infrastructure" and attempt.failure_code == failure_code
    record = json.loads((root / attempt.path).read_text())
    assert record["runtime_image_id"] == resolved_image


@pytest.mark.anyio
async def test_reference_replay_requires_the_exact_dataset_receipts_root_before_sandbox_construction(tmp_path):
    from tests.test_corpus import checked

    root = qualification_fixture(tmp_path)
    alternate = root / "benchmarks/dataset/alternate-receipts"
    alternate.mkdir()
    constructed = False

    def backend_factory():
        nonlocal constructed
        constructed = True
        pytest.fail("an alternate receipts root must fail before sandbox construction")

    with pytest.raises(ValueError, match="benchmarks/dataset/receipts"):
        await verify_references(
            root=root, manifest_path=root / "benchmarks/dataset/manifest.json",
            eval_set="development", attempts=1, runs_root=root / ".runs/lite",
            receipts_root=alternate, backend_factory=backend_factory, corpus_validator=checked)
    assert not constructed


@pytest.mark.anyio
@pytest.mark.parametrize("alias_kind", ["hardlink", "intermediate-symlink"])
async def test_reference_replay_applies_strict_declared_path_rules_to_the_review_receipt(tmp_path, alias_kind):
    from corsair.benchmark import receipt_bytes
    from corsair.corpus import load_manifest
    from tests.test_corpus import checked, family_review, read_manifest, write_manifest
    from tests.test_kernel import HAPPY

    root = qualification_fixture(tmp_path)
    dataset = root / "benchmarks/dataset"
    receipts = dataset / "receipts"
    case = load_manifest(dataset / "manifest.json").cases[0]
    review_raw = receipt_bytes(family_review(case))
    if alias_kind == "hardlink":
        review_path = receipts / "review.json"
        review_path.write_bytes(review_raw)
        (root / "review-hardlink.json").hardlink_to(review_path)
        pointer_path = "receipts/review.json"
    else:
        actual = receipts / "actual"
        actual.mkdir()
        review_path = actual / "review.json"
        review_path.write_bytes(review_raw)
        (receipts / "review-link").symlink_to(actual, target_is_directory=True)
        pointer_path = "receipts/review-link/review.json"
    data = read_manifest(root)
    data["cases"][0]["review_receipt"] = {
        "path": pointer_path,
        "sha256": hashlib.sha256(review_raw).hexdigest(),
        "reviewer": "independent-reviewer",
        "reviewed_at": "2026-10-23",
    }
    write_manifest(root, data)

    with pytest.raises(ValueError, match="regular file below the receipts root"):
        await verify_references(
            root=root, manifest_path=dataset / "manifest.json", eval_set="development", attempts=3,
            runs_root=root / ".runs/lite", receipts_root=receipts,
            backend_factory=lambda: QualificationFake(dict(HAPPY)), corpus_validator=checked,
            now=lambda: datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc),
            id_factory=lambda: f"strict-review-{alias_kind}")


@pytest.mark.anyio
@pytest.mark.parametrize("alias_kind", ["manifest", "root"])
async def test_reference_replay_rejects_lexical_symlink_aliases_before_sandbox_construction(
        tmp_path, alias_kind):
    from tests.test_corpus import checked

    root = qualification_fixture(tmp_path)
    if alias_kind == "manifest":
        selected_root = root
        selected_manifest = root / "benchmarks/dataset/manifest-alias.json"
        selected_manifest.symlink_to("manifest.json")
    else:
        selected_root = tmp_path / "repository-alias"
        selected_root.symlink_to(root, target_is_directory=True)
        selected_manifest = selected_root / "benchmarks/dataset/manifest.json"
    constructed = False

    def backend_factory():
        nonlocal constructed
        constructed = True
        pytest.fail("lexical symlink aliases must fail before sandbox construction")

    with pytest.raises(ValueError, match="manifest|symlink"):
        await verify_references(
            root=selected_root, manifest_path=selected_manifest, eval_set="development", attempts=1,
            runs_root=root / ".runs/lite", receipts_root=root / "benchmarks/dataset/receipts",
            backend_factory=backend_factory, corpus_validator=checked)
    assert not constructed
