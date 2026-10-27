"""Reviewed case intake: ``dataset draft`` proposes, a human reviews, ``dataset freeze`` writes.

Synthetic chain directories live in tmp_path under their own ``evals/datasets`` tree, so no
checked-in file is edited; one test drafts the real python ``xxe`` pair into tmp_path. No
model, Docker or Temporal: drafting admits sources and runs the offline dataset checks only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from corsair.contracts import (
    Dataset,
    FixStatus,
    Oracle,
    PythonCommandSentinel,
    PythonRecipe,
    ScannerFinding,
    Scope,
    Source,
    Verdict,
    digest,
)
from corsair.contracts.recipes import CLEAN_NEGATIVE_QUALIFIED_KINDS
from corsair.entrypoints import cli
from corsair.entrypoints.requests import load_recipe_template, request_from_scanner
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation import datasets, families
from corsair.evaluation.intake import (
    DRAFT_SCHEMA,
    REVIEW_COLUMNS,
    DraftRefused,
    draft_dataset,
    freeze_dataset,
    propose_oracle,
)

ROOT = Path(__file__).resolve().parents[2]
CHAIN_PYTHON = ROOT / "evals/datasets/chain/python"
LEGACY = "../../../../../benchmarks/corpus/infosec-harness"
NARRATIVE = "NARRATIVE-MARKER"
TEMPLATE = {
    "kind": "python.secret_disclosure/1",
    "payload_parameter": "name",
    "public_files": {"hello.txt": "hello"},
    "expected_control": "hello",
    "allowed_exceptions": ["builtins.ValueError"],
}
MODULE = (
    "def lookup(name: str) -> str:\n"
    '    """Return the name."""\n'
    "    value = name.strip()\n"
    "    return value\n"
)


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def _chain_pair(evals: Path, stem: str, *, label: str = "EXPLOIT_DEMONSTRATED") -> list[Path]:
    """A synthetic ``<stem>-a``/``<stem>-b`` pair over an in-place corpus tree."""
    for variant in ("a", "b"):
        tree = evals / f"datasets/corpus/infosec-harness/python/{stem}/{variant}"
        tree.mkdir(parents=True)
        (tree / "app.py").write_text(MODULE + ("" if variant == "b" else "# fixed\n"))
    directories = []
    for variant in ("a", "b"):
        chain = evals / f"datasets/chain/python/{stem}-{variant}"
        _write_json(
            chain / "case.json",
            {
                "language": "python",
                "family": stem,
                "kind": "positive" if variant == "b" else "negative",
                "probes": NARRATIVE,
                "expected": NARRATIVE,
                "provenance": {
                    "path": f"benchmarks/corpus/infosec-harness/python/{stem}/{variant}"
                },
            },
        )
        finding = {
            "title": f"Lookup issue in {stem}",
            "description": NARRATIVE,
            "file_path": "app.py",
            "start_line": 3,
            "symbol": "lookup",
            "cwe": "CWE-20",
        }
        record: dict[str, Any] = {
            "case_id": f"corpus:{stem}{variant}",
            "finding": finding,
            "source": f"{LEGACY}/python/{stem}/{variant}",
        }
        if variant == "b":
            record["fixed_source"] = f"{LEGACY}/python/{stem}/a"
        _write_json(chain / "input.json", record)
        _write_json(
            chain / "oracle.json",
            {
                "expected_label": label if variant == "b" else "EXPLOIT_NOT_DEMONSTRATED",
                "expected_rule": "R4" if variant == "b" else "R5",
                "why": NARRATIVE,
                "replay": {"plan": NARRATIVE},
            },
        )
        (chain / "README.md").write_text(NARRATIVE)
        _write_json(chain / "submission.json", {"note": NARRATIVE})
        _write_json(chain / "manifest.json", {"note": NARRATIVE})
        _write_json(chain / "verification/result.json", {"note": NARRATIVE})
        directories.append(chain)
    return directories


@pytest.fixture
def evals(tmp_path: Path) -> Path:
    root = tmp_path / "evals"
    _chain_pair(root, "demo")
    return root


def _template(tmp_path: Path, **overrides: object) -> Path:
    return _write_json(tmp_path / "recipe-template.json", {**TEMPLATE, **overrides})


def _draft(tmp_path: Path, evals: Path, *, stem="demo", split="held_out", out="draft") -> Path:
    directories = [evals / f"datasets/chain/python/{stem}-{variant}" for variant in ("a", "b")]
    destination = tmp_path / out
    draft_dataset(directories, recipe_template=_template(tmp_path), split=split, out=destination)
    return destination


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip()[1:-1].split("|")]


def _rows(sheet: str) -> dict[str, list[str]]:
    lines = [line for line in sheet.splitlines() if line.startswith("| ")]
    return {_cells(line)[0]: _cells(line) for line in lines[1:] if not line.startswith("| ---")}


def _reviewed(draft: Path, decisions: dict[str, tuple[str, str, str]], name="reviewed.md") -> Path:
    """A reviewer's copy of review.md with the three reviewer columns filled."""
    lines = []
    for line in (draft / "review.md").read_text().splitlines():
        cells = _cells(line) if line.startswith("| ") else []
        if cells and cells[0] in decisions:
            cells[-3:] = decisions[cells[0]]
            line = "| " + " | ".join(cells) + " |"
        lines.append(line)
    path = draft.parent / name
    path.write_text("\n".join(lines) + "\n")
    return path


def _accept_all(draft: Path, *cases: str) -> Path:
    return _reviewed(draft, dict.fromkeys(cases, ("accept", "reviewer", "")))


def _rules(result: dict[str, Any]) -> set[str]:
    return {item["rule"] for item in result["refusals"]}


# Recipe templates bind to every Recipe union member (adapters/scm/requests.py)


def test_a_command_sentinel_template_binds_through_the_recipe_union(tmp_path):
    template = _write_json(
        tmp_path / "t.json",
        {"kind": "python.command_sentinel/1", "function": "lookup", "payload_parameter": "name"},
    )
    finding = ScannerFinding.model_validate(
        {
            "title": "t",
            "description": "d",
            "file": "app.py",
            "scope": {
                "application": "[Library] app",
                "repositories": [{"name": "app", "url": "https://example.invalid/app"}],
            },
        }
    )
    request = request_from_scanner(
        finding,
        case_id="c-000",
        source=Source(path="/src"),
        recipe_template=load_recipe_template(template),
    )
    assert isinstance(request.case.recipe, PythonCommandSentinel)
    assert request.case.recipe.module_file == "app.py"


def test_a_template_for_another_runtime_validates_without_its_module_file(tmp_path):
    template = _write_json(tmp_path / "t.json", {"kind": "perl.html_injection/1", "package": "R"})
    loaded = load_recipe_template(template, bound=("module_file", "function", "method"))
    assert loaded["kind"] == "perl.html_injection/1"


def test_an_unknown_recipe_kind_is_refused_not_invented(tmp_path):
    template = _write_json(tmp_path / "t.json", {**TEMPLATE, "kind": "python.xxe/1"})
    with pytest.raises(ValueError, match="not an admitted Recipe kind"):
        load_recipe_template(template, bound=("module_file", "function", "method"))


def test_a_drafting_template_may_not_set_the_callable(tmp_path):
    template = _write_json(tmp_path / "t.json", {**TEMPLATE, "function": "lookup"})
    with pytest.raises(ValueError, match="may not set function"):
        load_recipe_template(template, bound=("module_file", "function", "method"))


def test_an_invalid_template_field_still_fails_up_front(tmp_path):
    template = _write_json(tmp_path / "t.json", {**TEMPLATE, "payload_parameter": "_private"})
    with pytest.raises(ValueError, match="payload_parameter"):
        load_recipe_template(template, bound=("module_file", "function", "method"))


# The proposed oracle is mechanical (evaluation/intake.py)


@pytest.mark.parametrize("kind", sorted(CLEAN_NEGATIVE_QUALIFIED_KINDS))
def test_a_qualified_kind_proposes_both_decisive_verdicts_and_no_label(kind):
    oracle = propose_oracle(kind, fixed_source=False)
    assert oracle.acceptable_verdicts == [
        Verdict.EXPLOIT_DEMONSTRATED,
        Verdict.EXPLOIT_NOT_DEMONSTRATED,
    ]
    assert oracle.expected_verdict is None
    assert oracle.expected_fix is FixStatus.NOT_REQUESTED
    assert not datasets.case_oracle_problems(oracle)
    assert not datasets.claim_scope_problems(Scope.COMPONENT, oracle)


def test_a_kind_without_a_qualified_rubric_never_proposes_a_clean_negative():
    oracle = propose_oracle("perl.html_injection/1", fixed_source=True)
    assert Verdict.EXPLOIT_NOT_DEMONSTRATED not in (oracle.acceptable_verdicts or [])
    assert oracle.expected_verdict is None
    assert oracle.expected_fix is None  # a fixed source exists: the reviewer sets it
    assert not datasets.negative_label_problems("perl.html_injection/1", oracle)


# dataset draft


def test_draft_assembles_requests_proposals_and_a_review_sheet(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    document = json.loads((draft / "draft.json").read_text())
    assert document["schema_version"] == DRAFT_SCHEMA
    assert [entry["case_id"] for entry in document["entries"]] == [
        "ih-python-demo-a",
        "ih-python-demo-b",
    ]
    assert {entry["family"] for entry in document["entries"]} == {"ih-python-demo"}
    assert {entry["split"] for entry in document["entries"]} == {"held_out"}

    request = json.loads((draft / "ih-python-demo-b/request.json").read_text())
    case = request["case"]
    corpus = evals / "datasets/corpus/infosec-harness/python/demo"
    assert case["source"]["path"] == str((corpus / "b").absolute())
    assert case["fixed_source"]["path"] == str((corpus / "a").absolute())
    assert len(case["source"]["expected_digest"]) == 64
    assert case["finding"]["claim_scope"] == "component"
    assert case["finding"]["file"] == case["recipe"]["module_file"] == "app.py"
    assert case["finding"]["line"] == 3
    assert case["recipe"]["function"] == "lookup"
    assert case["recipe"]["payload_parameter"] == "name"
    a_request = json.loads((draft / "ih-python-demo-a/request.json").read_text())
    assert "fixed_source" not in a_request["case"]

    a_oracle = Oracle.model_validate_json(
        (draft / "ih-python-demo-a/oracle.proposed.json").read_bytes()
    )
    b_oracle = Oracle.model_validate_json(
        (draft / "ih-python-demo-b/oracle.proposed.json").read_bytes()
    )
    assert a_oracle.expected_fix is FixStatus.NOT_REQUESTED and b_oracle.expected_fix is None
    # The legacy label is data: both rows propose the same verdicts whatever it says.
    assert a_oracle.acceptable_verdicts == b_oracle.acceptable_verdicts
    provenance = {entry["case_id"]: entry["provenance"] for entry in document["entries"]}
    assert provenance["ih-python-demo-b"] == {
        "legacy_expected_label": "EXPLOIT_DEMONSTRATED",
        "legacy_expected_rule": "R4",
        "truth_type": "positive",
    }

    sheet = (draft / "review.md").read_text()
    header = next(line for line in sheet.splitlines() if line.startswith("| "))
    assert _cells(header) == list(REVIEW_COLUMNS)
    row = _rows(sheet)["ih-python-demo-b"]
    assert row[1:4] == ["python.secret_disclosure/1", "ih-python-demo", "held_out"]
    assert row[4] == case["source"]["expected_digest"]
    assert "legacy label EXPLOIT_DEMONSTRATED" in row[7]
    assert row[8] == "none"
    assert row[-3:] == ["", "", ""]


def test_draft_reads_no_narrative_and_writes_none(tmp_path, evals, monkeypatch):
    read: list[str] = []
    original_bytes, original_text = Path.read_bytes, Path.read_text

    def spy_bytes(self: Path) -> bytes:
        read.append(str(self))
        return original_bytes(self)

    def spy_text(self: Path, *args: Any, **kwargs: Any) -> str:
        read.append(str(self))
        return original_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", spy_bytes)
    monkeypatch.setattr(Path, "read_text", spy_text)
    draft = _draft(tmp_path, evals)
    monkeypatch.undo()

    names = {Path(path).name for path in read}
    assert not names & {"README.md", "submission.json", "manifest.json"}
    assert not any("verification" in Path(path).parts for path in read)
    for path in draft.rglob("*"):
        if path.is_file():
            assert NARRATIVE not in path.read_text(), path


def test_a_draft_is_accepted_by_no_dataset_loader(tmp_path, evals):
    path = _draft(tmp_path, evals) / "draft.json"
    report = datasets.validate_dataset(path)
    assert not report.valid and "not an evaluation dataset manifest" in report.problems[0]
    with pytest.raises(ValidationError):
        datasets.load_dataset(path)
    with pytest.raises(ValueError, match="unsupported dataset manifest"):
        families.dataset_members(path)


def test_draft_never_writes_under_the_evals_tree_or_over_an_earlier_draft(tmp_path, evals):
    chain = [evals / "datasets/chain/python/demo-a"]
    template = _template(tmp_path)
    with pytest.raises(DraftRefused, match="outside the evals tree"):
        draft_dataset(chain, recipe_template=template, split="held_out", out=evals / "x")
    _draft(tmp_path, evals)
    with pytest.raises(DraftRefused, match="not empty"):
        draft_dataset(chain, recipe_template=template, split="held_out", out=tmp_path / "draft")


def test_draft_reports_validator_blockers_on_the_row(tmp_path, evals):
    finding = evals / "datasets/chain/python/demo-a/input.json"
    record = json.loads(finding.read_text())
    record["finding"]["start_line"] = 40
    finding.write_text(json.dumps(record))
    draft = _draft(tmp_path, evals)
    row = _rows((draft / "review.md").read_text())["ih-python-demo-a"]
    assert "target_binding" in row[8]
    assert _rows((draft / "review.md").read_text())["ih-python-demo-b"][8] == "none"


def test_provenance_is_unknown_without_a_recognised_corpus(tmp_path):
    root = tmp_path / "evals"
    chain = root / "datasets/chain/python/local-b"
    (chain / "tree").mkdir(parents=True)
    (chain / "tree/app.py").write_text(MODULE)
    _write_json(chain / "case.json", {"language": "python", "family": "local", "kind": "positive"})
    _write_json(
        chain / "input.json",
        {
            "finding": {"title": "t", "file_path": "app.py", "start_line": 3, "symbol": "lookup"},
            "source": "tree",
        },
    )
    out = tmp_path / "draft"
    draft_dataset([chain], recipe_template=_template(tmp_path), split="held_out", out=out)
    [entry] = json.loads((out / "draft.json").read_text())["entries"]
    assert (entry["case_id"], entry["family"]) == ("syn-python-local-b", "syn-python-local")
    assert entry["provenance"] == {"truth_type": "positive"}


# dataset freeze


def test_freeze_refuses_a_row_without_a_decision_and_writes_nothing(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _reviewed(draft, {"ih-python-demo-a": ("accept", "al", "")})
    into = evals / "datasets/gym-tier2.json"
    result = freeze_dataset(draft, review=review, into=into, against=[])
    assert not result["written"] and "decision_missing" in _rules(result)
    assert not into.exists()
    assert not list((evals / "datasets/corpus").glob("*.json"))


def test_freeze_writes_accepted_rows_with_frozen_digests_and_both_identities(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _reviewed(
        draft, {"ih-python-demo-a": ("accept", "al", ""), "ih-python-demo-b": ("reject", "al", "")}
    )
    into = evals / "datasets/gym-tier2.json"
    result = freeze_dataset(draft, review=review, into=into, against=[])
    assert result["written"] and not result["refusals"]
    manifest = Dataset.model_validate_json(into.read_bytes())
    [entry] = manifest.entries
    assert (entry.case_id, entry.family, entry.split) == (
        "ih-python-demo-a",
        "ih-python-demo",
        "held_out",
    )
    # In place beside the corpus, as the existing Perl row: admission refuses ".." sources.
    assert entry.request == "datasets/corpus/ih-python-demo-a.request.json"
    assert entry.oracle == "datasets/corpus/ih-python-demo-a.oracle.json"
    assert result["identity"] == {"old": None, "new": digest(manifest)}
    frozen = json.loads((evals / entry.request).read_text())
    assert frozen["case"]["source"]["path"] == "infosec-harness/python/demo/a"
    assert result["absolute_sources"] is False
    assert datasets.validate_dataset(into).valid
    assert result["validation"]["valid"] is True


def test_freeze_takes_an_amended_oracle_and_checks_its_reviewed_digest(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    amended = Oracle(
        acceptable=["REFUTED", "INCONCLUSIVE"],
        forbidden=["SUPPORTED"],
        expected_fix=FixStatus.NOT_REQUESTED,
        acceptable_verdicts=[Verdict.EXPLOIT_NOT_DEMONSTRATED],
        forbidden_verdicts=[Verdict.EXPLOIT_DEMONSTRATED],
    )
    oracle = draft / "ih-python-demo-a/oracle.json"
    oracle.write_text(amended.model_dump_json(indent=2, exclude_none=True) + "\n")
    into = evals / "datasets/gym-tier2.json"

    stale = _reviewed(draft, {"ih-python-demo-a": ("amend", "al", "0" * 64)}, "stale.md")
    stale_result = freeze_dataset(draft, review=stale, into=into, against=[])
    assert "reviewed_digest_mismatch" in _rules(stale_result) and not into.exists()

    review = _reviewed(
        draft,
        {
            "ih-python-demo-a": ("amend", "al", digest(oracle.read_bytes())),
            "ih-python-demo-b": ("reject", "al", ""),
        },
    )
    result = freeze_dataset(draft, review=review, into=into, against=[])
    assert result["written"]
    [entry] = Dataset.model_validate_json(into.read_bytes()).entries
    assert (evals / entry.oracle).read_bytes() == oracle.read_bytes()


def test_freeze_refuses_an_accepted_oracle_that_fails_validation(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    contradictory = {
        "acceptable": ["SUPPORTED"],
        "acceptable_verdicts": ["EXPLOIT_DEMONSTRATED"],
        "forbidden_verdicts": ["EXPLOIT_DEMONSTRATED"],
    }
    _write_json(draft / "ih-python-demo-a/oracle.json", contradictory)
    review = _reviewed(
        draft, {"ih-python-demo-a": ("amend", "al", ""), "ih-python-demo-b": ("accept", "al", "")}
    )
    into = evals / "datasets/gym-tier2.json"
    result = freeze_dataset(draft, review=review, into=into, against=[])
    assert _rules(result) == {"row_invalid"} and not into.exists()
    assert "ih-python-demo-a" in result["refusals"][0]["detail"]


def test_freeze_refuses_an_edited_code_owned_cell(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _accept_all(draft, "ih-python-demo-a", "ih-python-demo-b")
    review.write_text(review.read_text().replace("| held_out |", "| dev |", 1))
    result = freeze_dataset(draft, review=review, into=evals / "datasets/t2.json", against=[])
    assert "sheet_mismatch" in _rules(result)


def test_freeze_refuses_a_family_or_source_tree_in_another_split(tmp_path, evals):
    dev = _draft(tmp_path, evals, split="dev", out="dev-draft")
    tier1 = evals / "datasets/tier1.json"
    freeze_dataset(
        dev,
        review=_accept_all(dev, "ih-python-demo-a", "ih-python-demo-b"),
        into=tier1,
        against=[],
    )
    holdout = _draft(tmp_path, evals)
    review = _accept_all(holdout, "ih-python-demo-a", "ih-python-demo-b")
    into = evals / "datasets/gym-tier2.json"

    result = freeze_dataset(holdout, review=review, into=into, against=[tier1])
    assert {"family_crosses_splits", "source_tree_crosses_splits"} <= _rules(result)
    assert not into.exists()

    # A renamed family in the other manifest still shares the source tree.
    document = json.loads(tier1.read_text())
    for entry in document["entries"]:
        entry["family"] = "legacy-demo"
    tier1.write_text(json.dumps(document))
    result = freeze_dataset(holdout, review=review, into=into, against=[tier1])
    assert "source_tree_crosses_splits" in _rules(result)
    assert "family_crosses_splits" not in _rules(result)


def test_freeze_refuses_more_than_sixty_four_entries_and_a_case_frozen_twice(tmp_path, evals):
    draft = _draft(tmp_path, evals)
    review = _accept_all(draft, "ih-python-demo-a", "ih-python-demo-b")
    into = evals / "datasets/gym-tier2.json"
    filler = {
        "family": "filler",
        "split": "held_out",
        "request": "datasets/none/request.json",
        "oracle": "datasets/none/oracle.json",
        "request_digest": "0" * 64,
        "oracle_digest": "0" * 64,
    }
    entries = [{"case_id": f"filler-{index}", **filler} for index in range(63)]
    _write_json(into, {"schema_version": "corsair.dataset/1", "entries": entries})
    result = freeze_dataset(draft, review=review, into=into, against=[])
    assert "too_many_entries" in _rules(result)

    into.unlink()
    assert freeze_dataset(draft, review=review, into=into, against=[])["written"]
    again = freeze_dataset(draft, review=review, into=into, against=[])
    assert "case_already_frozen" in _rules(again)


# The CLI


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())


def test_draft_and_freeze_parse_their_arguments():
    draft = cli.parser().parse_args(
        ["dataset", "draft", "a", "b", "--recipe-template", "t.json", "--split", "held_out"]
        + ["--out", "o", "--budget", "budget.json"]
    )
    assert draft.dataset_command == "draft" and draft.chain_dirs == ["a", "b"]
    assert (draft.recipe_template, draft.split, draft.out, draft.budget) == (
        "t.json",
        "held_out",
        "o",
        "budget.json",
    )
    freeze = cli.parser().parse_args(
        ["dataset", "freeze", "d", "--review", "r.md", "--into", "x.json", "--against", "a", "b"]
    )
    assert (freeze.draft_dir, freeze.review, freeze.into, freeze.against) == (
        "d",
        "r.md",
        "x.json",
        ["a", "b"],
    )


async def test_cli_draft_then_freeze_exits_zero_two_and_one(tmp_path, evals, capsys):
    out = tmp_path / "draft"
    chain = [str(evals / f"datasets/chain/python/demo-{variant}") for variant in "ab"]
    template = str(_template(tmp_path))
    args = _arguments(
        "dataset", "draft", *chain, "--recipe-template", template, "--split", "held_out",
        "--out", str(out),
    )  # fmt: skip
    assert await cli.execute(args, Terminal(args)) == 0
    drafted = json.loads(capsys.readouterr().out)
    assert drafted["review"] == str(out / "review.md")

    into = evals / "datasets/gym-tier2.json"
    tier1 = _write_json(
        evals / "datasets/empty.json",
        {"schema_version": "corsair.agent-dataset/1", "entries": []},
    )
    unreviewed = _arguments(
        "dataset", "freeze", str(out), "--review", str(out / "review.md"), "--into", str(into),
        "--against", str(tier1),
    )  # fmt: skip
    assert await cli.execute(unreviewed, Terminal(unreviewed)) == 2
    assert "decision_missing" in {
        item["rule"] for item in json.loads(capsys.readouterr().out)["refusals"]
    }

    review = _accept_all(out, "ih-python-demo-a", "ih-python-demo-b")
    freeze = _arguments(
        "dataset", "freeze", str(out), "--review", str(review), "--into", str(into),
        "--against", str(tier1),
    )  # fmt: skip
    assert await cli.execute(freeze, Terminal(freeze)) == 1
    frozen = json.loads(capsys.readouterr().out)
    assert frozen["written"] is True and frozen["identity"]["old"] is None


async def test_cli_draft_refusal_exits_two(tmp_path, evals):
    args = _arguments(
        "dataset", "draft", str(evals / "datasets/chain/python/demo-a"), "--recipe-template",
        str(_template(tmp_path, kind="python.xxe/1")), "--split", "held_out", "--out",
        str(tmp_path / "out"),
    )  # fmt: skip
    assert await cli.execute(args, Terminal(args)) == 2
    assert not (tmp_path / "out").exists()


# The real holdout-eligible python pair, drafted into tmp_path only


def test_the_python_xxe_pair_drafts_without_blockers(tmp_path):
    out = tmp_path / "xxe"
    template = _write_json(tmp_path / "t.json", {**TEMPLATE, "payload_parameter": "document"})
    result = draft_dataset(
        [CHAIN_PYTHON / "xxe-a", CHAIN_PYTHON / "xxe-b"],
        recipe_template=template,
        split="held_out",
        out=out,
    )
    assert [entry["case_id"] for entry in result["entries"]] == [
        "ih-python-xxe-a",
        "ih-python-xxe-b",
    ]
    assert all(not entry["blockers"] for entry in result["entries"])
    request = json.loads((out / "ih-python-xxe-b/request.json").read_text())
    assert request["case"]["recipe"]["function"] == "parse_note"
    assert PythonRecipe.model_validate(request["case"]["recipe"]).payload_parameter == "document"
