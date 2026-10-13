"""SPEC-0035 chain dataset: the scripted E2E-0 composition over every reviewed-pair variant, real host pytest runs."""
import asyncio

import pytest
from pydantic_ai import models

from corsair.composition.direct import run_direct
from evals.fixture_chain.evaluate import dataset, evaluate, passed


@pytest.fixture(autouse=True)
def no_real_requests():
    with models.override_allow_model_requests(False):
        yield


def test_scripted_chain_passes_every_evaluator_with_injected_composition(tmp_path):
    calls = []

    async def composition(case, stage_models, runners, budget):
        calls.append(case.revision_sources)
        return await run_direct(case, stage_models, runners, budget)

    report = asyncio.run(evaluate(tmp_path / "evidence", mode="direct", run=composition))
    assert len(report.cases) == len(dataset().cases) == len(calls) and passed(report)
    runs = list((tmp_path / "evidence").glob("run-*"))
    assert len(runs) == len(calls) and all((run / "result.json").is_file() for run in runs)
