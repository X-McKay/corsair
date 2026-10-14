import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from corsair.v2.contracts import RunResult, RunSpec, SourceRequest, Verdict
from corsair.v2.storage import Store


def spec(request_id: str = "request-1", concern: str = "bounded test concern") -> RunSpec:
    return RunSpec(request_id=request_id, source=SourceRequest(path="/source"), concern=concern)


def result(run_id: str, spec_sha256: str, config_sha256: str, *, summary: str = "saved") -> RunResult:
    return RunResult(run_id=run_id, spec_sha256=spec_sha256, config_sha256=config_sha256,
                     verdict=Verdict(status="inconclusive", reason="test", rule_id="test", summary=summary),
                     qualification="unqualified", cleanup="not_acquired", duration_seconds=0)


def test_artifacts_are_canonical_private_and_detect_tampering(tmp_path):
    with Store(tmp_path / "store") as store:
        assert (tmp_path / "store").stat().st_mode & 0o777 == 0o700
        assert (tmp_path / "store" / "artifacts").stat().st_mode & 0o777 == 0o700
        ref = store.put_json({"b": [2], "a": 1})
        assert store.get(ref) == b'{"a":1,"b":[2]}\n'
        assert store.get_json(ref) == {"a": 1, "b": [2]}
        artifact = store.artifacts_root / ref.sha256
        artifact.chmod(0o600)
        artifact.write_bytes(b"tampered")
        artifact.chmod(0o400)
        with pytest.raises(Exception, match="Artifact"):
            store.get(ref)


def test_store_refuses_a_root_below_an_ancestor_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        Store(link / "store")


def test_register_event_and_result_are_idempotent_across_restart(tmp_path):
    config = "a" * 64
    item = spec()
    with Store(tmp_path / "store") as store:
        run_id, created = store.register_run(item, config)
        assert (run_id, created) == ("request-1", True)
        assert store.register_run(item, config) == (run_id, False)
        first = store.event(run_id, "captured", {"tree": "one"}, "capture-1")
        assert store.event(run_id, "captured", {"tree": "one"}, "capture-1") == first
        with pytest.raises(ValueError, match="different event"):
            store.event(run_id, "captured", {"tree": "two"}, "capture-1")
        second = store.event(run_id, "planned", {"files": 1})
        assert (first["sequence"], second["sequence"]) == (1, 2)
        assert store.events(run_id, after=1) == [second]
        saved = result(run_id, hashlib.sha256(item.model_dump_json().encode()).hexdigest(), config)
        # RunSpec uses canonical bytes, not pydantic's display JSON.
        saved = saved.model_copy(update={"spec_sha256": store.runs()[0]["spec_sha256"]})
        store.save_result(saved)
        store.save_result(saved)
    with Store(tmp_path / "store") as reopened:
        assert reopened.result("request-1") == saved
        assert reopened.runs()[0]["result_sha256"]
        with pytest.raises(ValueError, match="different result"):
            reopened.save_result(saved.model_copy(update={"verdict": saved.verdict.model_copy(update={"summary": "other"})}))


def test_conflicting_ingress_is_rejected_and_event_sequences_are_atomic(tmp_path):
    config = "b" * 64
    with Store(tmp_path / "store") as store:
        run_id, _ = store.register_run(spec(), config)
        with pytest.raises(ValueError, match="already bound"):
            store.register_run(spec(concern="different"), config)
        with pytest.raises(ValueError, match="already bound"):
            store.register_run(spec(), "c" * 64)
        with ThreadPoolExecutor(max_workers=8) as pool:
            events = list(pool.map(lambda n: store.event(run_id, "progress", {"n": n}, f"op-{n}"), range(24)))
        assert sorted(event["sequence"] for event in events) == list(range(1, 25))
        stored = store.events(run_id)
        assert [event["sequence"] for event in stored] == list(range(1, 25))
        assert len({event["sha256"] for event in stored}) == 24


def test_operation_intent_never_means_a_safe_resend_and_receipt_is_immutable(tmp_path):
    digest = "d" * 64
    with Store(tmp_path / "store") as store:
        assert store.claim_operation("dispatch-1", digest) == "new"
        assert store.claim_operation("dispatch-1", digest) == "uncertain"
        assert store.operation("dispatch-1") is None
        with pytest.raises(ValueError, match="different request"):
            store.claim_operation("dispatch-1", "e" * 64)
        store.complete_operation("dispatch-1", {"status": "complete", "value": 1})
        assert store.claim_operation("dispatch-1", digest) == "recorded"
        assert store.operation("dispatch-1") == {"status": "complete", "value": 1}
        store.complete_operation("dispatch-1", {"value": 1, "status": "complete"})
        with pytest.raises(ValueError, match="different operation receipt"):
            store.complete_operation("dispatch-1", {"status": "different"})
        with pytest.raises(ValueError, match="must be claimed"):
            store.complete_operation("never-claimed", {})
