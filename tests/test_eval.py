"""The eval command is a release gate for both the finding and its fix."""
import argparse
import json
from contextlib import asynccontextmanager

import pytest

from corsair import cli
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
