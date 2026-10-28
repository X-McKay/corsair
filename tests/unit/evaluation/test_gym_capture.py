"""Gym capture: kernel replay cases and agent fixtures that round-trip through the loaders."""

import json
import shutil
from pathlib import Path

import pytest

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    AuditDecision,
    AuditInput,
    Dataset,
    DatasetEntry,
    Disposition,
    ExecutionStatus,
    InvestigationRequest,
    InvestigationResult,
    KernelCase,
    Oracle,
    ProducerDecision,
    ProducerOutput,
    RoundResult,
    Verdict,
    digest,
)
from corsair.evaluation.datasets import (
    auditor_oracle_problems,
    dataset_root,
    load_frozen_fixture,
    producer_oracle_problems,
    validate_dataset,
)
from corsair.evaluation.gym.capture import (
    REDACTED,
    build_kernel_case,
    capture,
    kernel_verdict,
    read_kernel_case,
)
from corsair.evaluation.gym.scoring import REPORT_FILE
from corsair.evaluation.scoring import save_report, score
from corsair.policies.operations import round_operation_id
from corsair.settings import Settings
from corsair.steps.verification import EvidenceVerifier
from tests.unit.test_evidence import _audit, _FakeSandbox, _prepared, _submission
from tests.unit.test_verdicts import _clean_negative

ROOT = Path(__file__).resolve().parents[3]
KERNEL_CASES = ROOT / "tests/replay/kernel"
CASE = "case01"


def _evals_root(tmp_path: Path) -> tuple[Path, Path, Dataset]:
    """A scratch evaluation root holding a byte-identical copy of the frozen case01."""
    root = tmp_path / "evals"
    shutil.copytree(ROOT / "evals/fixtures/case01", root / "fixtures/case01")
    source = json.loads((ROOT / "evals/datasets/dev.json").read_text())
    entry = DatasetEntry.model_validate(source["entries"][0])
    assert entry.case_id == CASE
    dataset = Dataset(entries=[entry])
    path = root / "datasets/gym-capture.json"
    path.parent.mkdir(parents=True)
    path.write_text(dataset.model_dump_json(indent=2))
    return root, path, dataset


def _oracle(root: Path) -> Oracle:
    return Oracle.model_validate_json((root / "fixtures/case01/oracle.json").read_bytes())


def _round(store: ArtifactStore, run_id: str, decision: AuditDecision) -> RoundResult:
    """A genuine receipt for a covered control-vs-exploit differential, then an audit."""
    from corsair.contracts import Budget, EvidenceInput

    prepared = _prepared().model_copy(
        update={"case_id": CASE, "source": store.put(b"admitted source", "application/x-tar")}
    )
    verifier = EvidenceVerifier(Settings(), store, _FakeSandbox(store))
    observation = verifier.evaluate(
        EvidenceInput(
            run_id=run_id,
            operation_id=round_operation_id(run_id, 1, 1),
            prepared=prepared,
            submission=_submission(),
            budget=Budget(probe_timeout_seconds=5),
        )
    )
    return RoundResult(
        index=1,
        producer=ProducerOutput(
            decision=ProducerDecision(kind="proposal", submission=_submission())
        ),
        observation=observation,
        audit=_audit(decision),
    )


def _result(store: ArtifactStore, run_id: str, decision: AuditDecision) -> InvestigationResult:
    accepted = decision is AuditDecision.ACCEPT
    result = InvestigationResult(
        run_id=run_id,
        case_id=CASE,
        disposition=Disposition.SUPPORTED if accepted else Disposition.INCONCLUSIVE,
        verdict=Verdict.EXPLOIT_DEMONSTRATED if accepted else Verdict.INCONCLUSIVE,
        execution_status=ExecutionStatus.COMPLETED,
        reason="reviewed",
        manifest=_prepared().manifest,
        rounds=[_round(store, run_id, decision)],
    )
    store.commit(f"result.{run_id}", store.put_json(result))
    return result


def _gym_run(tmp_path: Path, store: ArtifactStore, root: Path, dataset: Dataset) -> Path:
    oracle = _oracle(root)
    rows = [
        score(_result(store, "gym-rejected", AuditDecision.REJECT), oracle, store),
        score(_result(store, "gym-accepted", AuditDecision.ACCEPT), oracle, store),
    ]
    run_dir = tmp_path / ".runs/gym/run-1"
    save_report(run_dir / REPORT_FILE, rows, dataset_digest=digest(dataset))
    return run_dir


def test_capture_round_trips_through_the_existing_fixture_loader(tmp_path):
    root, dataset_path, dataset = _evals_root(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    run_dir = _gym_run(tmp_path, store, root, dataset)
    kernel_dir = tmp_path / "kernel"

    captured = capture(
        run_dir, CASE, dataset_path=dataset_path, store=store, out_root=root, kernel_dir=kernel_dir
    )

    assert captured["skipped"] == []
    assert len(captured["kernel_cases"]) == 2
    for path in captured["kernel_cases"]:
        case = read_kernel_case(Path(path))
        assert kernel_verdict(case) == case.recorded_verdict
        assert "reviewed" not in Path(path).read_text()
        submission = case.rounds[0].producer.submission_for_verification()
        assert submission is not None and submission.hypothesis == REDACTED

    auditor_path = Path(captured["auditor_dataset"])
    auditor = json.loads(auditor_path.read_text())
    assert len(auditor["entries"]) == 1
    _, content, expected = load_frozen_fixture(dataset_root(auditor_path), auditor["entries"][0])
    packet = AuditInput.model_validate_json(content)
    assert packet.submission.exploit_payload == "../private/secret.txt"
    assert expected == {"decision": "ACCEPT", "rule": "ALL"}
    assert auditor_oracle_problems(expected) == []

    producer_path = Path(captured["producer_dataset"])
    producer = json.loads(producer_path.read_text())
    _, content, expected = load_frozen_fixture(dataset_root(producer_path), producer["entries"][0])
    assert InvestigationRequest.model_validate_json(content).case.case_id == CASE
    assert expected == {
        "control_payload": "hello.txt",
        "candidate_payloads": ["../private/secret.txt"],
    }
    assert producer_oracle_problems(expected) == []
    for path in (auditor_path, producer_path):
        report = validate_dataset(path)
        assert report.valid, report.as_dict()

    outputs = (root / "fixtures" / f"gym-run-1-{CASE}" / "producer-outputs.json").read_text()
    assert "read path traversal" not in outputs

    again = capture(
        run_dir, CASE, dataset_path=dataset_path, store=store, out_root=root, kernel_dir=kernel_dir
    )
    assert again["files"] == captured["files"]


def test_capture_refuses_a_case_without_a_failed_repeat_or_another_dataset(tmp_path):
    root, dataset_path, dataset = _evals_root(tmp_path)
    store = ArtifactStore(tmp_path / "artifacts")
    run_dir = tmp_path / "run-ok"
    save_report(run_dir / REPORT_FILE, [], dataset_digest=digest(dataset))
    with pytest.raises(ValueError, match="no failed repeat"):
        capture(
            run_dir,
            CASE,
            dataset_path=dataset_path,
            store=store,
            out_root=root,
            kernel_dir=tmp_path,
        )
    save_report(run_dir / REPORT_FILE, [], dataset_digest="0" * 64)
    with pytest.raises(ValueError, match="different dataset"):
        capture(
            run_dir,
            CASE,
            dataset_path=dataset_path,
            store=store,
            out_root=root,
            kernel_dir=tmp_path,
        )


def test_two_distinct_clean_negatives_replay_to_a_negative_verdict():
    prepared = _prepared()

    def clean(session: int, exploit: str) -> RoundResult:
        submission = _submission().model_copy(update={"exploit_payload": exploit})
        return RoundResult(
            index=1,
            session=session,
            producer=ProducerOutput(
                decision=ProducerDecision(kind="proposal", submission=submission)
            ),
            observation=_clean_negative(),
            audit=_audit(),
        )

    result = InvestigationResult(
        run_id="neg",
        case_id=prepared.case_id,
        disposition=Disposition.INCONCLUSIVE,
        verdict=Verdict.EXPLOIT_NOT_DEMONSTRATED,
        execution_status=ExecutionStatus.COMPLETED,
        reason="clean",
        manifest=prepared.manifest,
        rounds=[clean(1, "../a"), clean(2, "../b")],
    )
    oracle = Oracle(acceptable=[Disposition.INCONCLUSIVE])
    case = build_kernel_case(result, oracle, prepared.recipe.kind, prepared)
    assert kernel_verdict(case) is Verdict.EXPLOIT_NOT_DEMONSTRATED
    repeated = build_kernel_case(
        result.model_copy(update={"rounds": [clean(1, "../a"), clean(2, "../a")]}),
        oracle,
        prepared.recipe.kind,
        prepared,
    )
    assert kernel_verdict(repeated) is Verdict.INCONCLUSIVE
    errored = build_kernel_case(
        result.model_copy(update={"rounds": [], "execution_status": ExecutionStatus.BLOCKED}),
        oracle,
        prepared.recipe.kind,
        None,
    )
    assert kernel_verdict(errored) is Verdict.UNABLE_TO_RUN


def test_every_committed_kernel_case_replays_to_its_recorded_verdict():
    """Captured kernel cases under tests/replay/kernel are a model-free kernel regression guard."""
    for path in sorted(KERNEL_CASES.glob("*.json")):
        case = KernelCase.model_validate_json(path.read_bytes())
        assert kernel_verdict(case) == case.recorded_verdict, path.name
