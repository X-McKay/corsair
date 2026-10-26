"""The live-eval recipe script: refusals, sanitised identity and README rendering.

No model, Temporal or Docker runs here. The evaluator is a stand-in that writes a synthetic
report; `corsair compare` runs for real because it is an offline reader.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from corsair.contracts import Verdict, digest
from scripts import live_eval

ROOT = Path(__file__).resolve().parents[2]
SECRET = "sk-test-never-printed-0042"
SETTINGS = {
    "image": "corsair-python:0.1",
    "runtime": "runc",
    "models": {
        "connector": "gemini",
        "producer": "gemini-2.5-flash",
        "auditor": "gemini-2.5-flash",
        "api_base": None,
        "request_timeout_seconds": 120,
        "extra_body": {},
    },
}
AGENT_DATASET = {
    "schema_version": "corsair.agent-dataset/1",
    "entries": [{"case_id": "audit01", "input": "a.json", "oracle": "o.json"}],
}
CHAIN_DATASET = {
    "schema_version": "corsair.dataset/1",
    "entries": [{"case_id": "case01", "request": "r.json", "oracle": "o.json"}],
}


def _agent_row(case_id: str, repeat: int, status: str, match_kind: str) -> dict:
    return {
        "run_id": f"isolated-{case_id}-{repeat}",
        "case_id": case_id,
        "repeat": repeat,
        "status": status,
        "match_kind": match_kind,
        "cohort": "live-model-fixture",
        "execution_status": "ERROR" if match_kind == "operational_failure" else "COMPLETED",
        "agent": "auditor",
        "config_digest": "c" * 64,
        "agent_resources_digest": "r" * 64,
        "llm_calls": 1,
        "tool_calls": 0,
        "input_tokens": None,
        "output_tokens": 40,
        "agent_seconds": 2.5,
    }


def _report(rows: list[dict], dataset_digest: str) -> dict:
    passed = sum(row["status"] == "pass" for row in rows)
    return {
        "dataset_digest": dataset_digest,
        "rows": rows,
        "summary": {
            "attempts": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "operational_failures": 1,
            "unavailable_results": 0,
            "llm_calls": len(rows),
            "tool_calls": 0,
            "input_tokens": None,
            "output_tokens": 40 * len(rows),
            "cost_usd": None,
        },
    }


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".state").mkdir()
    (tmp_path / ".state/settings.json").write_text(json.dumps(SETTINGS))
    (tmp_path / "agent.json").write_text(json.dumps(AGENT_DATASET))
    (tmp_path / "chain.json").write_text(json.dumps(CHAIN_DATASET))
    return tmp_path


def run(root: Path, *arguments: str, env: dict[str, str] | None = None):
    """Run the script as the recipe does, with an explicit environment."""
    environment = {"PATH": "/usr/bin:/bin", **(env or {})}
    command = [sys.executable, str(ROOT / "scripts/live_eval.py"), "--root", str(root)]
    return subprocess.run(
        [*command, *arguments], cwd=root, env=environment, capture_output=True, text=True
    )


def plan_for(root: Path, *arguments: str, environ: dict[str, str] | None = None):
    """Plan in-process; `.json` arguments name files under the test root, as cwd would."""
    paths = [str(root / item) if item.endswith(".json") else item for item in arguments]
    args = live_eval.parse_arguments(["--root", str(root), *paths, "--stamp", "20261026T0000Z"])
    return live_eval.make_plan(args, root, environ or {"GOOGLE_API_KEY": SECRET})


def test_script_vocabulary_matches_canonical_contracts(tmp_path):
    assert set(live_eval.DECISIVE_LABELS) <= {verdict.value for verdict in Verdict}
    assert live_eval.canonical_digest(AGENT_DATASET) == digest(AGENT_DATASET)
    dataset = json.loads((ROOT / "evals/datasets/auditor-dev.json").read_bytes())
    assert live_eval.canonical_digest(dataset) == digest(dataset)
    from corsair.evaluation.scoring import Dataset

    chain = {"entries": [json.loads((ROOT / "evals/datasets/dev.json").read_bytes())["entries"][0]]}
    path = tmp_path / "chain.json"
    path.write_text(json.dumps(chain))
    assert live_eval.read_dataset(path, "chain") == digest(Dataset.model_validate(chain))


def test_dry_run_prints_plan_without_secret_or_records(root):
    result = run(
        root, "agent", "auditor", "agent.json", "--dry-run", env={"GEMINI_API_KEY": SECRET}
    )
    assert result.returncode == 0, result.stderr
    assert "provider environment present: GEMINI_API_KEY" in result.stdout
    assert "corsair.evaluation.agents auditor" in result.stdout
    assert "dry run: no model" in result.stdout
    assert SECRET not in result.stdout + result.stderr
    assert not (root / ".runs").exists()


@pytest.mark.parametrize(
    "settings,message",
    [
        (None, "is missing; run `just settings-init`"),
        ({"image": "corsair-python:0.1"}, "must name models.connector"),
        ({"models": {"connector": "other"}}, "must name models.connector"),
        ({"models": {"connector": "gemini"}}, "must name models.auditor"),
    ],
)
def test_refuses_without_a_named_connector(root, settings, message):
    path = root / ".state/settings.json"
    if settings is None:
        path.unlink()
    else:
        path.write_text(json.dumps(settings))
    result = run(root, "agent", "auditor", "agent.json", "--dry-run", env={"GOOGLE_API_KEY": "x"})
    assert result.returncode == 2
    assert message in result.stderr


def test_refuses_missing_provider_environment_naming_only_variables(root):
    result = run(root, "chain", "chain.json", "--dry-run", env={"GOOGLE_GENAI_USE_VERTEXAI": "1"})
    assert result.returncode == 2
    assert "set GOOGLE_API_KEY or GEMINI_API_KEY or GOOGLE_GENAI_USE_VERTEXAI+" in result.stderr


@pytest.mark.parametrize(
    "models,environ,outcome",
    [
        ({"producer": "hosted_vllm/m", "api_base": "http://h:8000/v1"}, {}, []),
        ({"producer": "hosted_vllm/m"}, {}, "needs models.api_base"),
        ({"producer": "anthropic/claude"}, {}, "set ANTHROPIC_API_KEY"),
        ({"producer": "anthropic/claude"}, {"ANTHROPIC_API_KEY": SECRET}, ["ANTHROPIC_API_KEY"]),
        ({"producer": "bedrock/x"}, {}, "--require-env NAME"),
    ],
)
def test_litellm_routes_need_their_provider_environment(models, environ, outcome):
    settings = {"models": {"connector": "litellm", **models}}
    if isinstance(outcome, list):
        assert live_eval.provider_environment(settings, ["producer"], environ) == outcome
        return
    with pytest.raises(live_eval.LiveError, match=outcome) as error:
        live_eval.provider_environment(settings, ["producer"], environ)
    assert SECRET not in str(error.value)


def test_required_environment_names_are_added_and_checked():
    settings = {"models": {"connector": "litellm", "producer": "bedrock/x"}}
    environ = {"AWS_PROFILE": "operator"}
    assert live_eval.provider_environment(settings, ["producer"], environ, ["AWS_PROFILE"]) == [
        "AWS_PROFILE"
    ]
    with pytest.raises(live_eval.LiveError, match="set AWS_REGION"):
        live_eval.provider_environment(settings, ["producer"], environ, ["AWS_REGION"])


def test_refuses_dataset_of_the_other_kind(root):
    with pytest.raises(live_eval.LiveError, match="not a chain dataset"):
        plan_for(root, "chain", "agent.json")
    with pytest.raises(live_eval.LiveError, match="not a agent dataset"):
        plan_for(root, "agent", "producer", "chain.json")


def test_refuses_baseline_that_compare_would_refuse(root):
    (root / "other.json").write_text(json.dumps(_report([], "0" * 64)))
    with pytest.raises(live_eval.LiveError, match="--allow-dataset-mismatch"):
        plan_for(root, "agent", "auditor", "agent.json", "other.json")
    plan = plan_for(
        root, "agent", "auditor", "agent.json", "other.json", "--allow-dataset-mismatch"
    )
    assert plan.compare_command()[-1] == "--allow-dataset-mismatch"
    producer = _agent_row("audit01", 0, "pass", "exact_match") | {"agent": "producer"}
    (root / "producer.json").write_text(json.dumps(_report([producer], digest(AGENT_DATASET))))
    with pytest.raises(live_eval.LiveError, match="not the auditor"):
        plan_for(root, "agent", "auditor", "agent.json", "producer.json")
    with pytest.raises(live_eval.LiveError, match="not a composed one"):
        plan_for(root, "chain", "chain.json", "producer.json")


def test_refuses_to_overwrite_an_existing_record(root):
    plan = plan_for(root, "agent", "auditor", "agent.json")
    plan.run_dir.mkdir(parents=True)
    with pytest.raises(live_eval.LiveError, match="never overwritten"):
        plan_for(root, "agent", "auditor", "agent.json")


def test_chain_run_id_is_a_bounded_root_identity(root):
    from corsair.contracts import validate_root_identity

    (root / ("x" * 80 + ".json")).write_text(json.dumps(CHAIN_DATASET))
    plan = plan_for(root, "chain", "x" * 80 + ".json")
    assert validate_root_identity(plan.run_id) == plan.run_id
    assert plan.run_dir.parent == root / ".runs/live"


def test_identity_is_sanitised_and_read_from_report_rows(root):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "agent.json"], cwd=root, check=True)
    commit = [
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "commit",
        "-qm",
        "x",
    ]
    subprocess.run(commit, cwd=root, check=True)
    settings = json.loads((root / ".state/settings.json").read_text())
    settings["models"] |= {"api_base": "http://private-host:8000/v1", "extra_body": {"thinking": 1}}
    (root / ".state/settings.json").write_text(json.dumps(settings))
    plan = plan_for(root, "agent", "auditor", "agent.json")
    rows = [_agent_row("audit01", 0, "pass", "exact_match"), _agent_row("audit01", 1, "fail", "x")]
    identity = live_eval.build_identity(plan, _report(rows, plan.dataset_digest))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    assert identity["code"] == {
        "commit": head.stdout.strip(),
        "tree": identity["code"]["tree"],
        "dirty": True,  # chain.json and .state are untracked in this repository
    }
    assert len(identity["code"]["tree"]) == 40
    assert identity["settings"]["config_digests"] == ["c" * 64]
    assert identity["agent_resources_digests"] == {"auditor": ["r" * 64]}
    assert identity["dataset"] == {
        "path": "agent.json",
        "digest": digest(AGENT_DATASET),
        "report_digest": digest(AGENT_DATASET),
    }
    assert identity["models"]["api_base_configured"] is True
    assert identity["models"]["extra_body_keys"] == ["thinking"]
    assert identity["provider_env_names"] == ["GOOGLE_API_KEY"]
    text = json.dumps(identity)
    assert "private-host" not in text and SECRET not in text and str(root) not in text


def test_readme_renders_tables_identity_and_unrun_gates_from_a_saved_report(root):
    plan = plan_for(root, "chain", "chain.json")
    ledger = [{"session": 1, "round": 1, "stage": "producer", "gate": "producer_invalid:llm"}]
    rows = [
        {"case_id": "case01", "status": "fail", "verdict": "INCONCLUSIVE", "gate_ledger": ledger},
        {"case_id": "case01", "status": "pass", "verdict": "EXPLOIT_DEMONSTRATED"},
        {"case_id": "case02", "status": "unavailable", "reason": "lost"},
    ]
    report = _report(rows, plan.dataset_digest)
    report["summary"] |= {"unavailable_results": 1, "failure_stops": {"producer_invalid:llm": 1}}
    readme = live_eval.render_readme(live_eval.build_identity(plan, report), report, None)
    assert "| `report.json` | 3 | 1 |" in readme
    assert "| `case01` | 2 | 1 | `EXPLOIT_DEMONSTRATED` 1, `INCONCLUSIVE` 1 |" in readme
    assert "| `case02` | 1 | 0 | `unavailable` 1 |" in readme
    assert f"`{plan.dataset_digest}`" in readme
    assert "input tokens unknown" in readme and "cost unknown" in readme
    assert "`producer_invalid:llm` 1" in readme
    assert "No row reached `EXPLOIT_NOT_DEMONSTRATED`." in readme
    assert "No row reached `EXPLOIT_DEMONSTRATED`." not in readme
    assert "No round reached the `kernel` stage." in readme
    assert "No second independent session started." in readme
    assert "1 rows are unavailable" in readme
    assert "No baseline was given" in readme
    assert "pending human review" in readme and "DRAFT" in readme
    agent = plan_for(root, "agent", "auditor", "agent.json")
    agent_report = _report([_agent_row("audit01", 0, "pass", "exact_match")], digest(AGENT_DATASET))
    text = live_eval.render_readme(
        live_eval.build_identity(agent, agent_report), agent_report, None
    )
    assert "Docker target execution" in text and "The producer: not evaluated" in text
    assert "auditor `" + "r" * 64 + "`" in text


def test_execute_writes_record_and_comparison_from_a_stand_in_evaluator(root, monkeypatch):
    baseline_rows = [_agent_row("audit01", 0, "pass", "exact_match")]
    (root / "baseline.json").write_text(json.dumps(_report(baseline_rows, digest(AGENT_DATASET))))
    plan = plan_for(root, "agent", "auditor", "agent.json", "baseline.json", "--repeats", "1")
    real_run = subprocess.run

    def stand_in(command, **kwargs):
        if "corsair.evaluation.agents" in command:
            output = Path(command[command.index("--output") + 1])
            rows = [_agent_row("audit01", 0, "fail", "candidate_exact_mismatch")]
            output.write_text(json.dumps(_report(rows, digest(AGENT_DATASET))))
            return subprocess.CompletedProcess(command, 1)
        if command[0] == "docker":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return real_run(command, **kwargs)

    monkeypatch.setattr(live_eval.subprocess, "run", stand_in)
    assert live_eval.execute(plan) == 1  # the real corsair compare found a regression
    comparison = json.loads((plan.run_dir / "comparison.json").read_text())
    assert comparison["regression"] is True
    assert comparison["counts"]["pass_to_fail"] == 1
    identity = json.loads((plan.run_dir / "identity.json").read_text())
    assert identity["image"] == {"name": "corsair-python:0.1", "id": None}
    readme = (plan.run_dir / "README.md").read_text()
    assert "Regression: `audit01` attempt 0: pass_to_fail" in readme
    assert "| passed | 1 | 0 | -1 |" in readme


def test_execute_stops_when_the_evaluator_leaves_no_report(root, monkeypatch):
    plan = plan_for(root, "agent", "auditor", "agent.json")
    monkeypatch.setattr(
        live_eval.subprocess, "run", lambda command, **_: subprocess.CompletedProcess(command, 2)
    )
    with pytest.raises(live_eval.LiveError, match="exited 2 without a report"):
        live_eval.execute(plan)


def test_chain_execution_refuses_when_doctor_is_not_ready(root, monkeypatch):
    plan = plan_for(root, "chain", "chain.json")
    not_ready = json.dumps({"ready": False, "checks": []})
    monkeypatch.setattr(
        live_eval.subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 1, stdout=not_ready),
    )
    with pytest.raises(live_eval.LiveError, match="doctor is not ready"):
        live_eval.execute(plan)
    assert not plan.run_dir.exists()
