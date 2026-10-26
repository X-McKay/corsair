"""Unit tests for CLI argument admission before runtime handlers execute."""

import pytest

from corsair.entrypoints.cli import parser


@pytest.mark.parametrize("option", ["repeats", "concurrency"])
@pytest.mark.parametrize("value", [1, 8])
def test_eval_parser_accepts_bounded_endpoints(option, value):
    args = parser().parse_args(["eval", "unread-dataset.json", f"--{option}", str(value)])

    assert getattr(args, option) == value


@pytest.mark.parametrize(
    ("option", "value"),
    [("repeats", 0), ("repeats", 9), ("concurrency", 0), ("concurrency", 9)],
)
def test_eval_parser_rejects_out_of_bounds_values(option, value):
    with pytest.raises(SystemExit) as error:
        parser().parse_args(["eval", "unread-dataset.json", f"--{option}", str(value)])

    assert error.value.code == 2


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ([], "the following arguments are required: command"),
        (["publish"], "invalid choice: 'publish'"),
        (["inspect"], "the following arguments are required: run_id"),
        (["verify", "request.json"], "the following arguments are required: submission"),
        (["rescore", "dataset.json"], "the following arguments are required: run_ids"),
        (["report", "x", "--format", "yaml"], "argument --format: invalid choice: 'yaml'"),
        (["report", "x", "--log-level", "TRACE"], "argument --log-level: invalid choice"),
        (["cancel", "run1", "--wait"], "unrecognized arguments: --wait"),
    ],
)
def test_parser_rejects_malformed_commands_with_usage_exit(capsys, arguments, message):
    with pytest.raises(SystemExit) as error:
        parser().parse_args(arguments)

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_compare_parser_requires_two_reports_and_defaults_to_refusing_mismatches():
    args = parser().parse_args(["compare", "baseline.json", "candidate.json"])

    assert (args.command, args.baseline, args.candidate) == (
        "compare",
        "baseline.json",
        "candidate.json",
    )
    assert args.allow_dataset_mismatch is False
    allowed = parser().parse_args(
        ["compare", "baseline.json", "candidate.json", "--allow-dataset-mismatch"]
    )
    assert allowed.allow_dataset_mismatch is True
    with pytest.raises(SystemExit) as error:
        parser().parse_args(["compare", "baseline.json"])
    assert error.value.code == 2
