"""Build replay may install and compile; it may not substitute the reported source."""

import pytest

from corsair.adapters.artifacts.filesystem import ArtifactStore
from corsair.adapters.frameworks import framework
from corsair.application.cases import load_case
from corsair.application.kernel import Kernel, environment_key
from corsair.domain.verification import Gate
from tests.fakes import FakeSandboxes
from tests.test_kernel import CASE, HAPPY, REFERENCE, ROW

pytestmark = pytest.mark.anyio


class RewritingBuild(FakeSandboxes):
    def exec_once(self, name, argv, **kwargs):
        result = super().exec_once(name, argv, **kwargs)
        if argv[0] == "bash":
            self._files[name]["/work/documents.py"] = b'def get_document(): return "fabricated"\n'
        return result


async def test_replayed_build_cannot_fabricate_a_target_bug(tmp_path):
    backend = RewritingBuild(dict(HAPPY))
    kernel = Kernel(
        backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path), framework=framework(ROW.framework)
    )
    evaluation = await kernel.evaluate(REFERENCE.model_copy(update={"build_script": "rewrite-target"}))
    assert evaluation.gate.stage is Gate.BUILD_REPLAY and "changed" in evaluation.gate.reason
    assert not evaluation.runs and not backend.sealed and not backend.labelled()


def test_cache_binds_the_resolved_image_and_runtime_policy():
    digest = load_case(CASE).revision.tree_sha256
    assert environment_key(ROW, digest, "", "sha256:old") != environment_key(ROW, digest, "", "sha256:new")
    other = ROW.model_copy(update={"framework": "node"})
    assert environment_key(ROW, digest, "") != environment_key(other, digest, "")
    assert environment_key(ROW, digest, "", protected_target="a.py") != environment_key(
        ROW, digest, "", protected_target="b.py"
    )


async def test_unresolved_image_cannot_reuse_an_unidentified_cache(tmp_path):
    backend = FakeSandboxes(dict(HAPPY))
    backend.resolve_image = lambda name: None
    kernel = Kernel(
        backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path), framework=framework(ROW.framework)
    )
    result = await kernel.evaluate(REFERENCE)
    assert result.gate.stage is Gate.INFRA and "unavailable" in result.gate.reason
    assert not backend.creates


async def test_every_native_report_is_preserved_as_content_addressed_evidence(tmp_path):
    backend = FakeSandboxes(dict(HAPPY))
    store = ArtifactStore(tmp_path)
    kernel = Kernel(backend, ROW, load_case(CASE), artifacts=store, framework=framework(ROW.framework))
    result = await kernel.evaluate(REFERENCE)
    assert result.gate.passed
    for run in result.runs:
        assert set(run.reports) == {
            "/tmp/corsair/result.json",
            "/tmp/corsair/junit.xml",
            "/tmp/corsair/coverage.json",
        }
        assert all(store.get(reference) for reference in run.reports.values())


async def test_auditor_failure_is_recorded_and_cannot_authorize_a_verdict(tmp_path):
    async def unavailable(submission):
        raise TimeoutError("endpoint unavailable")

    backend = FakeSandboxes(dict(HAPPY))
    kernel = Kernel(
        backend,
        ROW,
        load_case(CASE),
        artifacts=ArtifactStore(tmp_path),
        auditor=unavailable,
        framework=framework(ROW.framework),
    )
    result = await kernel.evaluate(REFERENCE)
    assert result.gate.stage is Gate.BLIND_AUDIT and not result.verdict
    assert "audit unavailable" in result.gate.reason and len(result.runs) == 2


@pytest.mark.parametrize("symlink", [False, True])
async def test_revision_cannot_occupy_the_reserved_kernel_path(tmp_path, symlink):
    import shutil

    from corsair.domain.case import revision

    case = load_case(CASE)
    source = tmp_path / "source"
    shutil.copytree(case.revision.source, source)
    if symlink:
        (source / ".corsair").symlink_to("/work", target_is_directory=True)
    else:
        (source / ".corsair").mkdir()
    backend = FakeSandboxes(dict(HAPPY))
    kernel = Kernel(
        backend,
        ROW,
        case.model_copy(update={"revision": revision(source)}),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        framework=framework(ROW.framework),
    )
    result = await kernel.evaluate(REFERENCE)
    assert result.gate.stage is Gate.BUILD_REPLAY and "reserved" in result.gate.reason
    assert not backend.creates


@pytest.mark.parametrize("policy", ["", None, 7])
async def test_cache_policy_must_be_explicit_before_any_execution(tmp_path, policy):
    backend = FakeSandboxes(dict(HAPPY))
    backend.cache_identity = policy
    kernel = Kernel(
        backend, ROW, load_case(CASE), artifacts=ArtifactStore(tmp_path), framework=framework(ROW.framework)
    )
    result = await kernel.evaluate(REFERENCE)
    assert result.gate.stage is Gate.INFRA and "cache policy" in result.gate.reason
    assert not backend.creates and not backend.sealed


def test_cache_is_bound_to_provider_and_reviewed_policy():
    digest = load_case(CASE).revision.tree_sha256
    base = environment_key(ROW, digest, "", sandbox_policy="docker:policy-a")
    assert base != environment_key(ROW, digest, "", sandbox_policy="openshell:policy-a")
    assert base != environment_key(ROW, digest, "", sandbox_policy="docker:policy-b")
