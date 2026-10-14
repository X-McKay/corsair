"""The shared v2 agent eval runner and its summary/policy reports, over a throwaway eval root and a tiny agent."""
import asyncio
import json

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from corsair.v2.agents.common.usage import to_agent_usage
from evals import agent_summary
from evals.agent_eval import AgentEval, Attempt, evaluate
from evals.cases import freeze, write_case


def _root(tmp_path):
    root = tmp_path / "evals"
    for language, name, answer in (("python", "upper", "ABC"), ("java", "lower", "abc")):
        write_case(root, "dev", name, language, {"text": "abc"}, {"answer": answer},
                   {"language": language, "framework": "none", "family": name, "kind": "positive",
                    "probes": "echo", "dimensions": ["correctness"],
                    "provenance": {"source": "synthetic", "license": "n/a (synthetic)"}})
    freeze(root, "dev")
    (root / "release-policy.yaml").write_text(
        "schema_version: 1\napplies_to: {sets: [], mode: scripted}\n"
        "hard_gates: {contract_rate: 1.0, safety_failures: 0, budget_exhausted_count: 0}\n"
        "thresholds:\n  accuracy:\n    correctness: {min: 0.5, by_language: {java: 0.9}}\n"
        "  clean_attempt_rate: {min: null}\n  latency_s: {p90_max: null}\n  input_tokens: {mean_max: 1}\n"
        "required_provenance: [git_commit, dataset_sha256]\n")
    return root


def _spec(root):
    async def run(case, model, workdir):
        usage = RunUsage()
        result = await Agent(model).run(case.input["text"], usage=usage)
        return Attempt(output=result.output, usage=to_agent_usage("builder", usage, model=model, wall_s=0.5),
                       facts={"workdir_empty": not any(workdir.iterdir())})

    def scripted(case):
        return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("ABC")]), model_name="scripted")

    return AgentEval(agent="builder", root=root, dimensions={"answer": "correctness", "fresh_workdir": "contract"},
                     run=run, scripted=scripted,
                     check=lambda case, attempt: {"answer": attempt.output == case.oracle["answer"],
                                                  "fresh_workdir": attempt.facts["workdir_empty"]})


def test_runner_rows_summary_and_policy(tmp_path):
    root = _root(tmp_path)
    passed = asyncio.run(evaluate(_spec(root), tmp_path / "evidence", "dev", repeat=2))
    assert passed is False  # the java case expects lower case
    lines = (tmp_path / "evidence" / "attempts.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines[1:]]
    assert len(rows) == 4 and {row["language"] for row in rows} == {"python", "java"}
    assert all(row["requests"] == 1 and row["latency_s"] == 0.5 for row in rows)
    assert len(list((tmp_path / "evidence" / "receipts").iterdir())) == 4
    summary = agent_summary.summarize(tmp_path / "evidence", agent="builder", set_name="dev", language=None,
                                      mode="scripted", run="r1", command={"git_commit": "abc", "git_dirty": False})
    overall = summary["rollups"]["all"]
    assert overall["dimensions"] == {"contract": {"passed": 4, "total": 4}, "correctness": {"passed": 2, "total": 4}}
    assert summary["rollups"]["by_language"]["java"]["dimensions"]["correctness"] == {"passed": 0, "total": 2}
    assert overall["latency_s"]["observed"] == 4 and overall["clean_attempts"] == 2
    policy = agent_summary.apply_policy(summary, root / "release-policy.yaml")
    entries = policy["entries"]
    assert entries["hard_gates.contract_rate"]["status"] == "pass"
    assert entries["hard_gates.safety_failures"]["status"] == "unknown"  # no safety assertion was measured
    assert entries["accuracy.correctness"]["status"] == "pass" and entries["accuracy.correctness.java"]["status"] == "fail"
    assert entries["clean_attempt_rate"]["status"] == "not_set"
    assert policy["status"] == "fail" and policy["deferred"] is True


def test_unreported_usage_is_unknown_not_zero(tmp_path):
    rows = [{"case": "python/a", "language": "python", "kind": "positive", "dimensions": {"correctness": True},
             "passed": True, "assertions": {"x": True}, "failure": None, "latency_s": None, "requests": None,
             "tool_calls": None, "input_tokens": None, "output_tokens": None}]
    rolled = agent_summary.rollup(rows)
    assert rolled["input_tokens"] == {"observed": 0, "mean": None, "p50": None, "p90": None, "total": None}


def test_chain_dispositions_keep_abstention_out_of_accuracy(tmp_path):
    def row(language, label, expected, reason):
        return {"case": f"{language}/{label}-{expected}", "language": language, "kind": "positive",
                "dimensions": {"correctness": label == expected}, "passed": label == expected, "assertions": {},
                "failure": None, "label": label, "expected_label": expected, "terminal_reason": reason,
                **{metric: None for metric in agent_summary.METRICS}}
    rows = [row("python", "LIKELY_EXPLOITABLE", "LIKELY_EXPLOITABLE", "completed"),
            row("python", "INCONCLUSIVE", "LIKELY_NOT_EXPLOITABLE", "probe_not_run"),
            row("java", "UNABLE_TO_RUN", "LIKELY_EXPLOITABLE", "no_runtime"),
            row("java", "LIKELY_NOT_EXPLOITABLE", "LIKELY_EXPLOITABLE", "completed")]
    found = agent_summary.rollup(rows)["dispositions"]
    assert found["decisive_rate"] == 0.5 and found["decisive_correct"] == 1
    assert found["accuracy_by_expected_label"]["LIKELY_EXPLOITABLE"] == {"passed": 1, "total": 3}
    assert found["abstentions"]["INCONCLUSIVE"] == {"count": 1, "rate": 0.25, "by_terminal_reason": {"probe_not_run": 1}}
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("schema_version: 1\nthresholds:\n  decisive_rate: {min: 0.6, by_language: {python: null}}\n"
                           "  inconclusive_rate: {max: null}\n  accuracy_by_label: {LIKELY_EXPLOITABLE: {min: null}}\n")
    summary = {"set": "v2", "mode": "live", "identity": {},
               "attempts": rows, "rollups": {"all": agent_summary.rollup(rows),
                                             "by_language": {"python": agent_summary.rollup(rows[:2])}}}
    entries = agent_summary.apply_policy(summary, policy_path)["entries"]
    assert entries["decisive_rate"]["status"] == "fail" and entries["decisive_rate.python"]["status"] == "not_set"
    assert entries["inconclusive_rate"]["status"] == "not_set"
