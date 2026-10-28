"""Public intake entrypoints and operator bindings preserve admission boundaries."""

from corsair.contracts.intake import IntakeRequest
from corsair.entrypoints.cli import parser


def test_cli_admits_exactly_one_input_and_explicit_source():
    args = parser().parse_args(["intake", "--issue", "org/repo#7", "--source", "./repo"])
    assert args.issue == "org/repo#7" and args.source == "./repo"


def test_numeric_issue_uses_the_single_configured_repository():
    from corsair.entrypoints.requests import parse_issue_reference

    assert parse_issue_reference("7", ["org/repo"]).model_dump() == {
        "kind": "issue_reference",
        "owner": "org",
        "repository": "repo",
        "number": 7,
    }


def test_intake_input_has_no_recipe_or_investigation_binding_contract():
    assert set(IntakeRequest.model_fields) == {"schema_version", "input", "source", "budget"}
