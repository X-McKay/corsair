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
