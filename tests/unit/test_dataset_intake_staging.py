"""Reviewed intake from a staging root: ``dataset draft --source-root`` and
``dataset freeze --import-into``.

Staged material (fetched datasets, agent-built chain inputs) lives under a private tree that
is never source of a frozen dataset. Drafting reads it in place below an explicit staging
root; only freeze, after the owner's decisions, copies the reviewed trees with their licence
files into the corpus. Every staging root here is synthetic under tmp_path. No model, Docker
or Temporal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair.contracts import Dataset, digest
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation import datasets, intake
from corsair.evaluation.intake import (
    REVIEW_COLUMNS,
    STAGED_REVIEW_COLUMNS,
    DraftRefused,
    draft_dataset,
    freeze_dataset,
)
from tests.unit.test_dataset_intake_draft import (
    MODULE,
    _accept_all,
    _cells,
    _reviewed,
    _rows,
    _rules,
    _template,
    _write_json,
)

LICENCE = b"Permission is hereby granted, free of charge.\n"
NOTICE = b"Copyright the authors.\n"


def _staged_case(
    stage: Path, name: str, *, licence: bool = True, fixed_licence: bool = True
) -> Path:
    """A chain directory under ``stage/chain`` over a vulnerable and a fixed tree under
    ``stage/trees``; the trees carry a LICENSE and a nested NOTICE unless told not to."""
    trees = stage / "trees" / name
    for variant, has_licence in (("vulnerable", licence), ("fixed", fixed_licence)):
        tree = trees / variant
        (tree / "lib").mkdir(parents=True)
        (tree / "app.py").write_text(MODULE + ("# fixed\n" if variant == "fixed" else ""))
        (tree / "lib/helper.py").write_bytes(b"VALUE = 1\n")
        if has_licence:
            (tree / "LICENSE").write_bytes(LICENCE)
            (tree / "lib/NOTICE.md").write_bytes(NOTICE)
    chain = stage / "chain" / name
    _write_json(chain / "case.json", {"family": name.removesuffix("-b"), "kind": "positive"})
    _write_json(
        chain / "input.json",
        {
            "finding": {"title": "t", "file_path": "app.py", "start_line": 3, "symbol": "lookup"},
            "source": f"../../trees/{name}/vulnerable",
            "fixed_source": f"../../trees/{name}/fixed",
        },
    )
    return chain


@pytest.fixture
def stage(tmp_path: Path) -> Path:
    root = tmp_path / "work/intake"
    _staged_case(root, "demo-b")
    return root


@pytest.fixture
def evals(tmp_path: Path) -> Path:
    root = tmp_path / "evals"
    (root / "datasets/corpus").mkdir(parents=True)
    return root


def _staged_draft(tmp_path: Path, stage: Path, *names: str, out: str = "draft") -> Path:
    destination = tmp_path / out
    draft_dataset(
        [stage / "chain" / name for name in names or ("demo-b",)],
        recipe_template=_template(tmp_path),
        split="held_out",
        out=destination,
        source_root=stage,
    )
    return destination


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_licence_files_are_named_licence_copying_or_notice_files_at_any_depth():
    names = [
        "LICENSE", "licence.txt", "LICENSE-MIT", "COPYING.LESSER", "UNLICENSE", "pkg/NOTICE.md",
        "notice.py", "licenses.json", "LICENSES/x", "src/license_check.js", "README.md",
    ]  # fmt: skip
    assert intake.licence_files(dict.fromkeys(names, b"")) == [
        "COPYING.LESSER",
        "LICENSE",
        "LICENSE-MIT",
        "UNLICENSE",
        "licence.txt",
        "pkg/NOTICE.md",
    ]


# dataset draft --source-root


def test_draft_reads_chain_directories_and_trees_in_place_below_a_staging_root(tmp_path, stage):
    draft = _staged_draft(tmp_path, stage)
    document = json.loads((draft / "draft.json").read_text())
    assert document["staged"] is True
    assert document["source_root"] == str(stage)
    [entry] = document["entries"]
    assert entry["case_id"] == "unk-python-demo-b"
    assert entry["origin"] == "chain/demo-b"
    assert entry["blockers"] == []
    assert entry["staged_source"] == {
        "path": "trees/demo-b/vulnerable",
        "licence_files": ["LICENSE", "lib/NOTICE.md"],
    }
    assert entry["staged_fixed_source"]["path"] == "trees/demo-b/fixed"
    request = json.loads((draft / "unk-python-demo-b/request.json").read_text())
    assert request["case"]["source"]["path"] == str(stage / "trees/demo-b/vulnerable")

    sheet = (draft / "review.md").read_text()
    header = next(line for line in sheet.splitlines() if line.startswith("| "))
    assert _cells(header) == list(STAGED_REVIEW_COLUMNS)
    assert {"staged tree", "licence file"} <= set(STAGED_REVIEW_COLUMNS)
    assert STAGED_REVIEW_COLUMNS[-3:] == REVIEW_COLUMNS[-3:]
    row = dict(zip(STAGED_REVIEW_COLUMNS, _rows(sheet)["unk-python-demo-b"], strict=True))
    assert row["staged tree"] == "trees/demo-b/vulnerable; fixed trees/demo-b/fixed"
    assert row["licence file"] == "LICENSE, lib/NOTICE.md; fixed LICENSE, lib/NOTICE.md"
    assert row["validator blockers"] == "none"


def test_a_licence_less_staged_tree_shows_none_on_the_sheet(tmp_path, stage):
    _staged_case(stage, "bare-b", licence=False)
    draft = _staged_draft(tmp_path, stage, "bare-b")
    row = dict(
        zip(
            STAGED_REVIEW_COLUMNS,
            _rows((draft / "review.md").read_text())["unk-python-bare-b"],
            strict=True,
        )
    )
    assert row["licence file"] == "none; fixed LICENSE, lib/NOTICE.md"


def test_a_staged_row_declaring_secbenchjs_material_has_provenance_sbj(tmp_path, stage):
    """SecBench.js pointer rows are staged with npm trees under ``external/secbenchjs/``;
    their case.json provenance path names that corpus, so ids read ``sbj-``, not ``unk-``."""
    chain = _staged_case(stage, "deep-b")
    case = json.loads((chain / "case.json").read_text())
    case["provenance"] = {"path": "external/secbenchjs/pkgs/deep/1.0.0", "license": "MIT"}
    _write_json(chain / "case.json", case)
    draft = _staged_draft(tmp_path, stage, "deep-b")
    [entry] = json.loads((draft / "draft.json").read_text())["entries"]
    assert (entry["case_id"], entry["family"]) == ("sbj-python-deep-b", "sbj-python-deep")


def test_an_unstaged_draft_keeps_its_schema_and_sheet(tmp_path):
    from tests.unit.test_dataset_intake_draft import _chain_pair, _draft

    evals = tmp_path / "evals"
    _chain_pair(evals, "demo")
    draft = _draft(tmp_path, evals)
    document = json.loads((draft / "draft.json").read_text())
    assert "staged" not in document
    assert not any("staged_source" in entry for entry in document["entries"])
    header = next(line for line in (draft / "review.md").read_text().splitlines() if "|" in line)
    assert _cells(header) == list(REVIEW_COLUMNS)


def test_draft_refuses_a_chain_directory_outside_the_staging_root(tmp_path, stage):
    outside = _staged_case(tmp_path / "elsewhere", "demo-b")
    out = tmp_path / "draft"
    with pytest.raises(DraftRefused, match="staging root"):
        draft_dataset(
            [outside],
            recipe_template=_template(tmp_path),
            split="held_out",
            out=out,
            source_root=stage,
        )
    assert not out.exists()


def test_draft_refuses_a_source_tree_outside_the_staging_root(tmp_path, stage):
    _staged_case(tmp_path / "work", "far-b")  # trees under work/trees, beside the root
    chain = stage / "chain/far-b"
    _write_json(chain / "case.json", {"family": "far", "kind": "positive"})
    _write_json(
        chain / "input.json",
        {
            "finding": {"title": "t", "file_path": "app.py", "start_line": 3, "symbol": "lookup"},
            "source": "../../../trees/far-b/vulnerable",
        },
    )
    out = tmp_path / "draft"
    with pytest.raises(DraftRefused, match="not admissible"):
        draft_dataset(
            [chain],
            recipe_template=_template(tmp_path),
            split="held_out",
            out=out,
            source_root=stage,
        )
    assert not out.exists()


@pytest.mark.parametrize("where", ["tree", "file", "chain"])
def test_draft_refuses_symlinks_below_the_staging_root(tmp_path, stage, where):
    tree = stage / "trees/demo-b/vulnerable"
    chain = stage / "chain/demo-b"
    if where == "tree":
        moved = stage / "trees/real"
        tree.rename(moved)
        tree.symlink_to(moved)
    elif where == "file":
        (tree / "lib/helper.py").unlink()
        (tree / "lib/helper.py").symlink_to(tree / "app.py")
    else:
        moved = stage / "chain/real-b"
        chain.rename(moved)
        chain.symlink_to(moved)
    out = tmp_path / "draft"
    with pytest.raises(DraftRefused, match="symbolic link"):
        draft_dataset(
            [chain],
            recipe_template=_template(tmp_path),
            split="held_out",
            out=out,
            source_root=stage,
        )
    assert not out.exists()


def test_a_staged_draft_never_writes_under_an_evals_tree(tmp_path, stage, evals):
    with pytest.raises(DraftRefused, match="evals tree"):
        _staged_draft(tmp_path, stage, out="evals/datasets/draft")
    assert not (evals / "datasets/draft").exists()


# dataset freeze --import-into


def test_freeze_refuses_a_staged_draft_without_import_and_writes_nothing(tmp_path, stage, evals):
    draft = _staged_draft(tmp_path, stage)
    into = evals / "datasets/gym-tier2.json"
    before = _files(evals)
    result = freeze_dataset(
        draft, review=_accept_all(draft, "unk-python-demo-b"), into=into, against=[]
    )
    assert _rules(result) == {"import_required"} and not result["written"]
    assert _files(evals) == before


def test_freeze_refuses_an_import_for_an_unstaged_draft(tmp_path, evals):
    from tests.unit.test_dataset_intake_draft import _chain_pair, _draft

    _chain_pair(evals, "demo")
    draft = _draft(tmp_path, evals)
    review = _accept_all(draft, "ih-python-demo-a", "ih-python-demo-b")
    into = evals / "datasets/gym-tier2.json"
    result = freeze_dataset(
        draft, review=review, into=into, against=[], import_into=evals / "datasets/corpus/x"
    )
    assert _rules(result) == {"import_not_staged"} and not into.exists()


@pytest.mark.parametrize("target", ["datasets/corpus", "datasets/elsewhere", "../outside"])
def test_freeze_imports_only_below_the_corpus_of_the_manifest(tmp_path, stage, evals, target):
    draft = _staged_draft(tmp_path, stage)
    into = evals / "datasets/gym-tier2.json"
    before = _files(evals)
    result = freeze_dataset(
        draft,
        review=_accept_all(draft, "unk-python-demo-b"),
        into=into,
        against=[],
        import_into=evals / target,
    )
    assert _rules(result) == {"import_outside_corpus"}
    assert _files(evals) == before and not into.exists()


def test_freeze_refuses_a_licence_less_tree_unless_noassertion_is_allowed(tmp_path, stage, evals):
    _staged_case(stage, "bare-b", licence=False)
    draft = _staged_draft(tmp_path, stage, "bare-b")
    review = _accept_all(draft, "unk-python-bare-b")
    into = evals / "datasets/gym-tier2.json"
    target = evals / "datasets/corpus/staged"
    before = _files(evals)

    refused = freeze_dataset(draft, review=review, into=into, against=[], import_into=target)
    assert _rules(refused) == {"licence_missing"} and not refused["written"]
    [refusal] = refused["refusals"]
    assert (
        "unk-python-bare-b" in refusal["detail"] and "trees/bare-b/vulnerable" in refusal["detail"]
    )
    assert _files(evals) == before and not target.exists()

    allowed = freeze_dataset(
        draft, review=review, into=into, against=[], import_into=target, allow_noassertion=True
    )
    assert allowed["written"] and not allowed["refusals"]
    provenance = json.loads((target / "unk-python-bare-b/provenance.json").read_text())
    assert provenance["licence"] == "NOASSERTION"
    assert provenance["trees"]["source"]["licence_files"] == []
    assert provenance["trees"]["fixed"]["licence_files"] == ["LICENSE", "lib/NOTICE.md"]
    assert [item["licence"] for item in allowed["imported"]] == ["NOASSERTION"]


def test_freeze_imports_reviewed_trees_byte_for_byte_with_their_licence_files(
    tmp_path, stage, evals
):
    _staged_case(stage, "other-b")
    draft = _staged_draft(tmp_path, stage, "demo-b", "other-b")
    review = _reviewed(
        draft,
        {
            "unk-python-demo-b": ("accept", "owner", ""),
            "unk-python-other-b": ("reject", "owner", ""),
        },
    )
    into = evals / "datasets/gym-tier2.json"
    target = evals / "datasets/corpus/staged"
    result = freeze_dataset(draft, review=review, into=into, against=[], import_into=target)

    assert result["written"] and not result["refusals"]
    assert result["frozen"] == ["unk-python-demo-b"] and result["rejected"] == [
        "unk-python-other-b"
    ]
    # Only the accepted row is imported, each tree byte for byte with its licence files.
    assert sorted(path.name for path in target.iterdir()) == ["unk-python-demo-b"]
    case = target / "unk-python-demo-b"
    assert _files(case / "source") == _files(stage / "trees/demo-b/vulnerable")
    assert _files(case / "fixed") == _files(stage / "trees/demo-b/fixed")
    assert (case / "source/LICENSE").read_bytes() == LICENCE
    assert (case / "fixed/lib/NOTICE.md").read_bytes() == NOTICE

    # The frozen request points at the imported trees, with the drafted snapshot digests.
    [entry] = Dataset.model_validate_json(into.read_bytes()).entries
    assert entry.request == "datasets/corpus/unk-python-demo-b.request.json"
    frozen = json.loads((evals / entry.request).read_text())["case"]
    drafted = json.loads((draft / "unk-python-demo-b/request.json").read_text())["case"]
    assert frozen["source"] == {
        "path": "staged/unk-python-demo-b/source",
        "expected_digest": drafted["source"]["expected_digest"],
    }
    assert frozen["fixed_source"] == {
        "path": "staged/unk-python-demo-b/fixed",
        "expected_digest": drafted["fixed_source"]["expected_digest"],
    }
    assert result["absolute_sources"] is False
    assert result["validation"]["valid"] is True
    assert datasets.validate_dataset(into).valid
    provenance = json.loads((case / "provenance.json").read_text())
    assert provenance == {
        "case_id": "unk-python-demo-b",
        "licence": "retained",
        "trees": {
            "source": {
                "staged_tree": "trees/demo-b/vulnerable",
                "snapshot_digest": drafted["source"]["expected_digest"],
                "licence_files": ["LICENSE", "lib/NOTICE.md"],
            },
            "fixed": {
                "staged_tree": "trees/demo-b/fixed",
                "snapshot_digest": drafted["fixed_source"]["expected_digest"],
                "licence_files": ["LICENSE", "lib/NOTICE.md"],
            },
        },
    }
    assert result["identity"] == {
        "old": None,
        "new": digest(Dataset.model_validate_json(into.read_bytes())),
    }


def test_freeze_refuses_an_existing_import_target_and_writes_nothing(tmp_path, stage, evals):
    draft = _staged_draft(tmp_path, stage)
    target = evals / "datasets/corpus/staged"
    (target / "unk-python-demo-b").mkdir(parents=True)
    into = evals / "datasets/gym-tier2.json"
    before = _files(evals)
    result = freeze_dataset(
        draft,
        review=_accept_all(draft, "unk-python-demo-b"),
        into=into,
        against=[],
        import_into=target,
    )
    assert _rules(result) == {"import_target_exists"}
    assert _files(evals) == before and not into.exists()


def test_freeze_refuses_a_staged_tree_changed_since_the_draft(tmp_path, stage, evals):
    draft = _staged_draft(tmp_path, stage)
    (stage / "trees/demo-b/fixed/lib/helper.py").write_bytes(b"VALUE = 2\n")
    into = evals / "datasets/gym-tier2.json"
    before = _files(evals)
    result = freeze_dataset(
        draft,
        review=_accept_all(draft, "unk-python-demo-b"),
        into=into,
        against=[],
        import_into=evals / "datasets/corpus/staged",
    )
    assert "import_source_changed" in _rules(result)
    assert _files(evals) == before and not into.exists()


def test_a_copy_whose_digest_does_not_match_is_removed_and_refused(
    tmp_path, stage, evals, monkeypatch
):
    draft = _staged_draft(tmp_path, stage)
    original = intake._write_tree

    def corrupting(target: Path, files: dict[str, bytes]) -> None:
        original(target, {**files, "app.py": files["app.py"] + b"# drift\n"})

    monkeypatch.setattr(intake, "_write_tree", corrupting)
    into = evals / "datasets/gym-tier2.json"
    before = _files(evals)
    result = freeze_dataset(
        draft,
        review=_accept_all(draft, "unk-python-demo-b"),
        into=into,
        against=[],
        import_into=evals / "datasets/corpus/new/staged",
    )
    assert _rules(result) == {"import_digest_mismatch"} and not result["written"]
    assert _files(evals) == before and not into.exists()
    assert not (evals / "datasets/corpus/new").exists()


# The CLI


def _arguments(*argv: str) -> cli.CliArguments:
    return cli.parser().parse_args(["--format", "json", *argv], namespace=cli.CliArguments())


def test_draft_and_freeze_parse_the_staging_arguments():
    draft = cli.parser().parse_args(
        ["dataset", "draft", "a", "--recipe-template", "t.json", "--split", "held_out"]
        + ["--out", "o", "--source-root", ".work/intake"]
    )
    assert draft.staging_root == ".work/intake"
    unstaged = cli.parser().parse_args(
        ["dataset", "draft", "a", "--recipe-template", "t.json", "--split", "s", "--out", "o"]
    )
    assert unstaged.staging_root is None
    freeze = cli.parser().parse_args(
        ["dataset", "freeze", "d", "--review", "r.md", "--into", "x.json", "--against", "a"]
        + ["--import-into", "evals/datasets/corpus/x", "--allow-noassertion"]
    )
    assert (freeze.import_into, freeze.allow_noassertion) == ("evals/datasets/corpus/x", True)
    plain = cli.parser().parse_args(
        ["dataset", "freeze", "d", "--review", "r.md", "--into", "x.json", "--against", "a"]
    )
    assert (plain.import_into, plain.allow_noassertion) == (None, False)


async def test_cli_staged_draft_then_freeze_exits_zero_two_and_one(tmp_path, stage, evals, capsys):
    out = tmp_path / "draft"
    args = _arguments(
        "dataset", "draft", str(stage / "chain/demo-b"), "--recipe-template",
        str(_template(tmp_path)), "--split", "held_out", "--out", str(out),
        "--source-root", str(stage),
    )  # fmt: skip
    assert await cli.execute(args, Terminal(args)) == 0
    drafted = json.loads(capsys.readouterr().out)
    assert drafted["staged"] is True and drafted["source_root"] == str(stage)

    review = _accept_all(out, "unk-python-demo-b")
    into = evals / "datasets/gym-tier2.json"
    against = _write_json(
        evals / "datasets/empty.json", {"schema_version": "corsair.agent-dataset/1", "entries": []}
    )
    common = ("dataset", "freeze", str(out), "--review", str(review), "--into", str(into))
    refused = _arguments(*common, "--against", str(against))
    assert await cli.execute(refused, Terminal(refused)) == 2
    assert {item["rule"] for item in json.loads(capsys.readouterr().out)["refusals"]} == {
        "import_required"
    }
    target = evals / "datasets/corpus/staged"
    freeze = _arguments(*common, "--import-into", str(target), "--against", str(against))
    assert await cli.execute(freeze, Terminal(freeze)) == 1
    frozen = json.loads(capsys.readouterr().out)
    assert frozen["written"] is True
    assert [item["case_id"] for item in frozen["imported"]] == ["unk-python-demo-b"]
    assert (target / "unk-python-demo-b/source/LICENSE").is_file()
