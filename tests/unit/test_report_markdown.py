"""Golden tests for the Markdown records of saved reports and report comparisons."""

import json

from corsair.entrypoints.cli import execute, parser
from corsair.entrypoints.markdown import comparison_markdown, report_markdown, to_markdown
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.comparison import compare_reports

POLICY = (
    "> Candidate diagnostic, not a promoted baseline: it makes no population accuracy, "
    "false-positive, clearance or production-readiness claim (see the baseline policy, "
    "`evals/baselines/README.md`)."
)
UNRUN = (
    "> Unknown usage is `unknown`, never zero. A gate this record does not show as run "
    "(Docker, Temporal, live model or full chain) is unrun, not passed."
)
# Free text a model may have authored, and payload bytes: a record never carries either.
MODEL_REASON = "auditor prose: the exploit | works\nbecause"
PAYLOAD = "PAYLOAD-1f2e3d"


def row(case_id, status="pass", verdict="EXPLOIT_DEMONSTRATED", gate="demonstrated", **fields):
    return {
        "run_id": f"run-{case_id}",
        "case_id": case_id,
        "status": status,
        "verdict": verdict,
        "disposition": "SUPPORTED",
        "execution_status": "COMPLETED",
        "forbidden_label": False,
        "llm_calls": 4,
        "tool_calls": 2,
        "input_tokens": 100,
        "output_tokens": 20,
        "agent_seconds": 1.23456,
        "config_digest": "config-a",
        "reason": MODEL_REASON,
        "submission": {"exploit": PAYLOAD},
        "gate_ledger": [
            {"session": 0, "round": 0, "stage": "kernel", "gate": gate, "reason": MODEL_REASON}
        ],
        **fields,
    }


def sample_report():
    rows = [
        row("case01"),
        row(
            "case|02\nx",
            status="fail",
            verdict="INCONCLUSIVE",
            gate="producer_invalid:llm_budget",
            execution_status="ERROR",
            llm_calls=None,
            agent_seconds=None,
        ),
        {"run_id": "run-gone", "case_id": "case03", "status": "unavailable", "reason": "vanished"},
    ]
    summary = {
        "attempts": 3,
        "passed": 1,
        "pass_rate": 1 / 3,
        "llm_calls": None,
        "cost_usd": None,
        "gate_ledger": {"demonstrated": 1, "producer_invalid:llm_budget": 1},
        "failure_stops": {"producer_invalid:llm_budget": 1},
    }
    return {"rows": rows, "summary": summary, "dataset_digest": "sha256:frozen"}


REPORT_GOLDEN = f"""## Corsair evaluation report

{POLICY}
>
{UNRUN}

### Identity

| Item | Value |
| --- | --- |
| Dataset digest | `sha256:frozen` |
| Config digests | `config-a` |
| Models | unknown |

### Summary

| Metric | Value |
| --- | ---: |
| attempts | 3 |
| passed | 1 |
| pass rate | 0.3333 |
| llm calls | unknown |
| cost usd | unknown |

### Cases

| Case | # | Run | Status | Label | Stop | LLM calls | Tool calls | Input tokens | Output tokens | Agent s |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `case01` | 0 | `run-case01` | pass | `EXPLOIT_DEMONSTRATED` | `demonstrated` | 4 | 2 | 100 | 20 | 1.2346 |
| `case\\|02 x` | 0 | `run-case\\|02 x` | fail · ERROR | `INCONCLUSIVE` | `producer_invalid:llm_budget` | unknown | 2 | 100 | 20 | unknown |
| `case03` | 0 | `run-gone` | unavailable | unknown | none | unknown | unknown | unknown | unknown | unknown |

### Gate ledger

| Gate | Count |
| --- | ---: |
| `demonstrated` | 1 |
| `producer_invalid:llm_budget` | 1 |

### Failure stops

| Gate | Count |
| --- | ---: |
| `producer_invalid:llm_budget` | 1 |
"""  # noqa: E501


def test_report_markdown_matches_the_golden_record():
    assert report_markdown(sample_report()) == REPORT_GOLDEN


def test_report_markdown_never_carries_reasons_payloads_or_split_cells():
    rendered = report_markdown(sample_report())

    assert "auditor prose" not in rendered and "because" not in rendered
    assert PAYLOAD not in rendered and "vanished" not in rendered
    for line in rendered.splitlines():
        if line.startswith("| `case"):
            # Eleven columns: every literal pipe inside a cell stays escaped.
            assert line.replace("\\|", "").count("|") == 12


def test_report_markdown_escapes_markdown_in_free_text_cells():
    report = {"summary": {"a|b<c>*": "x`y_|z\nw"}, "rows": []}

    rendered = report_markdown(report)

    assert "| a\\|b\\<c\\>\\* | x\\`y\\_\\|z w |" in rendered
    assert "### Cases" not in rendered


def test_isolated_report_records_identity_and_its_scope_caveat():
    rows = [
        {
            "run_id": "isolated-1",
            "case_id": "producer01",
            "repeat": 2,
            "status": "fail",
            "match_kind": "no_valid_output",
            "cohort": "live-model-fixture",
            "agent": "producer",
            "execution_status": "COMPLETED",
            "config_digest": "config-b",
            "agent_resources_digest": "resources-b",
            "model": "model-x",
            "feedback": {"gate": "producer_invalid", "reason": MODEL_REASON},
        }
    ]
    rendered = report_markdown({"rows": rows, "summary": {"attempts": 1}})

    assert "> Isolated agent diagnostic (`live-model-fixture`)" in rendered
    assert "| Dataset digest | unknown |" in rendered
    assert "| Models | `model-x` |" in rendered
    assert "| Agent resources digests | `resources-b` |" in rendered
    assert "| Agents | `producer` |" in rendered
    expected = "| `producer01` | 2 | `isolated-1` | fail | `no_valid_output` | `producer_invalid` |"
    assert expected in rendered
    assert "auditor prose" not in rendered


def test_summary_receipt_renders_without_rows_and_names_the_report():
    rendered = to_markdown({"report": ".runs/evaluations/x.json", "summary": {"attempts": 0}})

    assert "| Report | `.runs/evaluations/x.json` |" in rendered
    assert "| attempts | 0 |" in rendered
    assert "### Cases" not in rendered and "### Gate ledger" not in rendered


def test_an_empty_gate_ledger_is_recorded_as_none():
    rendered = report_markdown({"summary": {"gate_ledger": {}}})

    assert "### Gate ledger\n\nNone recorded." in rendered


def sample_comparison():
    baseline = sample_report()
    baseline["rows"] = [baseline["rows"][0], baseline["rows"][2]]
    candidate = {
        "rows": [
            row(
                "case01",
                status="fail",
                verdict="EXPLOIT_NOT_DEMONSTRATED",
                llm_calls=6,
                agent_seconds=1.0,
                forbidden_label=True,
            ),
            row("case04"),
        ],
        "summary": {},
        "dataset_digest": "sha256:frozen",
    }
    diff = compare_reports(baseline, candidate)
    return {"baseline_report": "before.json", "candidate_report": "after.json", **diff}


COMPARISON_GOLDEN = f"""## Corsair report comparison

Result: **REGRESSION**

{POLICY}
>
> A candidate with no regression on one frozen cohort is not a promoted baseline.
>
{UNRUN}

### Identity

| Item | Baseline | Candidate |
| --- | --- | --- |
| Report | `before.json` | `after.json` |
| Dataset digest | `sha256:frozen` | `sha256:frozen` |
| Config digests | `config-a` | `config-a` |
| Cohorts | unknown | unknown |

### Counts

| Count | Value |
| --- | ---: |
| joined | 1 |
| pass to fail | 1 |
| fail to pass | 0 |
| label changed | 1 |
| new forbidden labels | 1 |
| missing in candidate | 1 |
| new in candidate | 1 |

### Summary deltas

| Metric | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| attempts | 2 | 2 | +0 |
| passed | 1 | 1 | +0 |
| failed | 1 | 1 | +0 |
| pass rate | 0.5 | 0.5 | +0.0 |
| correctly resolved | 0 | 0 | +0 |
| invalid positive evidence | 0 | 0 | +0 |
| forbidden labels | 0 | 1 | +1 |
| inconclusive | 0 | 0 | +0 |
| operational failures | 0 | 0 | +0 |
| unavailable results | 1 | 0 | -1 |
| llm calls | unknown | 10 | unknown |
| tool calls | unknown | 4 | unknown |
| input tokens | unknown | 200 | unknown |
| output tokens | unknown | 40 | unknown |
| agent seconds | unknown | 2.2346 | unknown |

### Regressions

- `case01` #0: `pass_to_fail`
- `case01` #0: `new_forbidden_label`
- `case03` #0: `missing_in_candidate`

### Changed cases

| Case | # | Status | Label | Change | LLM calls Δ | Tool calls Δ | Input tokens Δ | Output tokens Δ | Agent s Δ |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `case01` | 0 | pass → fail | `EXPLOIT_DEMONSTRATED` → `EXPLOIT_NOT_DEMONSTRATED` | pass to fail · new forbidden label | +2 | +0 | +0 | +0 | -0.2346 |
| `case03` | 0 | unavailable → absent | unknown → absent | baseline only | - | - | - | - | - |
| `case04` | 0 | absent → pass | absent → `EXPLOIT_DEMONSTRATED` | candidate only | - | - | - | - | - |
"""  # noqa: E501


def test_comparison_markdown_matches_the_golden_record():
    rendered = comparison_markdown(sample_comparison())

    assert rendered == COMPARISON_GOLDEN
    assert "auditor prose" not in rendered and PAYLOAD not in rendered


def test_comparison_markdown_opens_with_a_dataset_mismatch_and_reports_no_changes():
    report = {"rows": [row("case01")], "summary": {}, "dataset_digest": "sha256:a"}
    other = {**report, "dataset_digest": None}
    diff = compare_reports(report, other, allow_dataset_mismatch=True)

    rendered = comparison_markdown(diff)

    assert rendered.startswith("## Corsair report comparison\n\nResult: **NO REGRESSION**\n\n")
    assert "\n\n> **Dataset mismatch:**" in rendered
    assert "| Dataset digest | `sha256:a` | unknown |" in rendered
    assert "### Regressions\n\nNone." in rendered
    assert "No per-case status or label changes in 1." in rendered
    assert "| Report |" not in rendered


def test_other_receipts_are_kept_whole_inside_a_fence_no_value_can_close():
    receipt = {"checks": [], "note": "``` not a fence end ````"}

    rendered = to_markdown(receipt)

    assert rendered.startswith("`````json\n") and rendered.endswith("\n`````\n")
    assert json.loads(rendered.removeprefix("`````json\n").removesuffix("`````\n")) == receipt


def test_a_result_shaped_receipt_is_never_read_as_a_report():
    rendered = to_markdown({"disposition": "SUPPORTED", "summary": {"attempts": 1}})

    assert rendered.startswith("```json\n")


def test_markdown_format_is_a_presentation_choice_with_no_ansi(capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    terminal = Terminal(parser().parse_args(["report", "x", "--format", "markdown"]))

    terminal.emit(sample_report())

    output = capsys.readouterr().out
    assert output == REPORT_GOLDEN
    assert "\x1b" not in output
    assert not terminal.human and not terminal.animate


async def test_execute_report_and_compare_emit_markdown_with_unchanged_exit_codes(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    worse = tmp_path / "worse.json"
    baseline.write_text(json.dumps(sample_report()))
    worse.write_text(json.dumps({**sample_report(), "rows": sample_report()["rows"][1:]}))

    args = parser().parse_args(["--format", "markdown", "report", str(baseline)])
    assert await execute(args) == 0
    assert capsys.readouterr().out == REPORT_GOLDEN

    args = parser().parse_args(["compare", str(baseline), str(worse), "--format", "markdown"])
    assert await execute(args) == 1
    output = capsys.readouterr().out
    assert output.startswith("## Corsair report comparison\n\nResult: **REGRESSION**\n")
    assert f"| Report | `{baseline}` | `{worse}` |" in output
    assert "- `case01` #0: `missing_in_candidate`" in output
