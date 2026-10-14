"""Environment breadth set: per-language coverage and evaluator sensitivity to plausible wrong outputs."""

from collections import Counter
from types import SimpleNamespace

import pytest

from corsair.agents.environment.contracts import EnvironmentInput
from evals.cases import load_set
from evals.environment.evaluate import EnvironmentChecks, HostInput, load_cases

CASES, DIGEST = load_cases("breadth")
META = {c.name: c.case for c in load_set("environment", "breadth")}


def test_breadth_set_counts_per_language():
    assert [c["name"] for c in CASES] == list(META)
    assert Counter(m["language"] for m in META.values()) == {"python": 4, "java": 12, "javascript": 12, "ruby": 11, "perl": 11}
    assert len(DIGEST) == 64
    statuses = Counter((META[c["name"]]["language"], c["status"]) for c in CASES)
    for language in ("java", "javascript", "ruby", "perl"):
        assert statuses[language, "ready"] >= 4 and statuses[language, "blocked"] >= 5 and statuses[language, "unsupported"] == 1


def output_for(case, **change):
    """The oracle draft as an output; citations and receipts are left empty so only the changed field can fail."""
    draft = case["draft"] | change
    fields = {"recipe": [], "citations": [], "receipts": [], **{k: v for k, v in draft.items() if k not in ("recipe", "citations")}}
    return SimpleNamespace(**fields)


def checks(case, output):
    stop = min(len(case["commands"]), case["max_commands"])
    unknown = next((i for i, o in enumerate(case["observations"]) if o.get("unknown")), None)
    stop = stop if unknown is None else min(stop, unknown + 1)
    ctx = SimpleNamespace(metadata=case, output=output,
                          inputs=HostInput(fixture_id=case["name"], inputs=EnvironmentInput.model_validate(case["inputs"])),
                          attributes={"commands": case["commands"][:stop], "read_paths": case["required_reads"], "records": []})
    return EnvironmentChecks().evaluate(ctx)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_oracle_draft_passes_every_check(case):
    assert all(checks(case, output_for(case)).values())


WRONG_STATUS = {
    # A plausible wrong outcome per expected status: give up on a ready setup, call an observed failure unsupported,
    # or report an unsupported runtime as a generic blocked halt.
    "ready": {"status": "blocked", "layer": "unknown", "evidence": "setup did not complete", "run_ids": []},
    "blocked": {"status": "unsupported", "requirement": "The project requires a runtime the toolchain lacks"},
    "unsupported": {"status": "blocked", "layer": "toolchain_version", "evidence": "wrong runtime", "run_ids": []},
}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_wrong_status_fails(case):
    assert not checks(case, SimpleNamespace(citations=[], receipts=[], **WRONG_STATUS[case["status"]]))["status"]


LAYERED = [c for c in CASES if c["status"] == "blocked" and c["layer"] is not None]


@pytest.mark.parametrize("case", LAYERED, ids=[c["name"] for c in LAYERED])
def test_wrong_failure_layer_fails(case):
    wrong = {"registry": "tls", "tls": "registry", "build": "discovery", "discovery": "build", "sandbox": "unknown",
             "unknown": "sandbox"}[case["layer"]]
    assert not checks(case, output_for(case, layer=wrong))["layer"]


UNSUPPORTED = [c for c in CASES if c["status"] == "unsupported"]


@pytest.mark.parametrize("case", UNSUPPORTED, ids=[c["name"] for c in UNSUPPORTED])
def test_unsupported_requirement_without_versions_fails(case):
    assert case["requirement_patterns"]
    vague = output_for(case, requirement="The project needs a newer runtime than the one prepared")
    assert not checks(case, vague)["unsupported_requirement"]


RECHOSEN = [c for c in CASES if META[c["name"]]["family"] == "baseline-not-passed"]


@pytest.mark.parametrize("case", RECHOSEN, ids=[c["name"] for c in RECHOSEN])
def test_skipped_or_xfailed_first_candidate_as_baseline_fails(case):
    first = case["commands"][-2]  # the earlier candidate run that did not report a pass
    assert first != case["draft"]["baseline_test_command"]
    assert not checks(case, output_for(case, baseline_test_command=first, baseline_test_id=first[-1]))["setup_identity"]
