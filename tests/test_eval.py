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
