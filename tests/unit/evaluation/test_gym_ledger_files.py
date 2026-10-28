"""Gym ledger touched files: git resolution, ``constraints`` for a brief and ``backfill``."""

import json
import logging
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from corsair.contracts import LedgerDecision, LedgerRow
from corsair.entrypoints import cli
from corsair.entrypoints.terminal import Terminal
from corsair.evaluation.gym.ledger import (
    append_ledger,
    build_ledger_row,
    changed_files,
    files_cell,
    prior_rejections,
    read_ledger,
    render_constraints,
    render_ledger,
    repository_path,
    rewrite_ledger,
)

ROOT = Path(__file__).resolve().parents[3]
_GIT = ["git", "-c", "user.name=gym", "-c", "user.email=gym@example.invalid"]
_GIT += ["-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [*_GIT, "-C", str(root), *arguments], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def _write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _repository(tmp_path: Path) -> tuple[Path, str]:
    """A repository whose candidate branch ``gym/x`` changed src/a.py, added docs/b.md and
    renamed src/old.py, while main later changed src/c.py."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    for name in ("src/a.py", "src/c.py", "src/old.py", "README.md"):
        _write(root, name, f"{name}\n")
    _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "gym/x")
    _write(root, "src/a.py", "changed\n")
    _write(root, "docs/b.md", "new\n")
    _git(root, "mv", "src/old.py", "src/new.py")
    candidate = _commit(root, "candidate")
    _git(root, "checkout", "-q", "main")
    _write(root, "src/c.py", "integration\n")
    _commit(root, "integration")
    return root, candidate


CANDIDATE_FILES = ["docs/b.md", "src/a.py", "src/new.py", "src/old.py"]


def test_changed_files_diff_the_candidate_from_its_merge_base(tmp_path):
    root, candidate = _repository(tmp_path)
    assert changed_files(root, candidate) == CANDIDATE_FILES
    assert changed_files(root, candidate[:8]) == CANDIDATE_FILES
    assert changed_files(root / "src", candidate) == CANDIDATE_FILES


def test_a_merged_candidate_diffs_from_its_merge_commits_first_parent(tmp_path):
    root, candidate = _repository(tmp_path)
    _git(root, "merge", "-q", "--no-ff", "-m", "merge", "gym/x")
    merge = _git(root, "rev-parse", "HEAD")
    assert changed_files(root, candidate) == []
    assert changed_files(root, candidate, merge) == CANDIDATE_FILES


def test_an_unresolvable_commit_or_a_directory_outside_git_resolves_nothing(tmp_path):
    root, candidate = _repository(tmp_path)
    assert changed_files(root, "d" * 40) is None
    assert changed_files(root, "--output=x") is None
    assert changed_files(root, candidate, "e" * 40) is None
    outside = tmp_path / "plain"
    outside.mkdir()
    assert changed_files(outside, candidate) is None
    assert not (root / "x").exists()


def _row(
    row_id: str,
    files: list[str],
    *,
    decision: LedgerDecision | None = "rejected",
    wave: int = 5,
) -> LedgerRow:
    return build_ledger_row(
        None,
        row_id=row_id,
        recorded_on=date(2026, 10, 28),
        wave=wave,
        entry="experiment",
        branch=f"gym/{row_id}",
        commit="b" * 40,
        track="accuracy",
        idea=f"Idea of {row_id} | piped",
        decision=decision,
        merge_commit="c" * 40 if decision == "merged" else None,
        lesson=f"Lesson of {row_id}.",
        touched_files=files,
    )


def test_a_row_stores_sorted_unique_touched_files_and_old_rows_decode_without_them():
    row = _row("h1", ["src/z.py", "src/a.py", "src/z.py"])
    assert row.touched_files == ["src/a.py", "src/z.py"]
    record = row.model_dump(mode="json")
    record.pop("touched_files")
    assert LedgerRow.model_validate(record).touched_files == []


def test_the_files_cell_shows_the_first_paths_and_counts_the_rest():
    assert files_cell([]) == "—"
    assert files_cell(["a.py"]) == "`a.py`"
    assert files_cell(["a.py", "b.py"]) == "`a.py`, `b.py`"
    assert files_cell(["a.py", "b.py", "c.py", "d.py"]) == "`a.py`, `b.py` +2"


def test_a_wave_shows_a_files_column_only_when_a_row_records_files():
    text = render_ledger([_row("h1", ["src/a.py", "src/b.py", "src/c.py"])], "# Ledger\n")
    assert "| Experiment | Track | Branch@commit | Files | Tier0 gate |" in text
    assert "| h1 | accuracy | `gym/h1@bbbbbbb` | `src/a.py`, `src/b.py` +1 | — |" in text
    mixed = render_ledger([_row("h1", ["src/a.py"]), _row("h2", [])], "# Ledger\n")
    assert "| h2 | accuracy | `gym/h2@bbbbbbb` | — | — |" in mixed
    bare = render_ledger([_row("h1", [])], "# Ledger\n")
    assert "Files" not in bare
    assert "| h1 | accuracy | `gym/h1@bbbbbbb` | — | — | — | — | rejected |" in bare


def test_constraints_match_files_and_directories_newest_first_within_the_limit():
    rows = [
        _row("h1", ["src/corsair/agents/producer/prompt.md"], wave=3),
        _row("h2", ["src/corsair/evaluation/gym/ledger.py"], decision="merged"),
        _row("h3", ["src/corsair/agents/producer/packet.py"], decision="inconclusive"),
        _row("h4", ["docs/x.md"]),
        _row("h5", ["src/corsair/agents/producerx.py"]),
        _row("h6", ["src/corsair/agents/producer/prompt.md"], decision="accepted"),
    ]
    directory = ["src/corsair/agents/producer"]
    assert [row.id for row in prior_rejections(rows, directory, 5)] == ["h3", "h1"]
    assert [row.id for row in prior_rejections(rows, directory, 1)] == ["h3"]
    exact = ["src/corsair/agents/producer/prompt.md", "docs/x.md"]
    assert [row.id for row in prior_rejections(rows, exact, 5)] == ["h4", "h1"]
    assert prior_rejections(rows, ["src/corsair/evaluation"], 5) == []
    assert [row.id for row in prior_rejections(rows, ["."], 9)] == ["h5", "h4", "h3", "h1"]


def test_repository_paths_drop_dot_slash_trailing_slash_and_the_toplevel(tmp_path):
    assert repository_path("./src/corsair/") == "src/corsair"
    assert repository_path(str(tmp_path / "src/a.py"), tmp_path) == "src/a.py"
    assert repository_path("/elsewhere/a.py", tmp_path) == "/elsewhere/a.py"


def test_constraints_render_code_owned_markdown_or_one_line():
    rows = [
        _row("h1", ["src/a.py", "src/b.py", "docs/c.md"], wave=3),
        _row("h2", ["src/a.py"], decision="inconclusive"),
    ]
    matched = prior_rejections(rows, ["src"], 5)
    text = render_constraints(matched, ["src"], unrecorded=0)
    assert text.startswith(
        "## Prior rejected experiments on these files\n\n"
        "These rejected or inconclusive experiments touched `src`. Do not repeat one unless "
        "the brief explains what differs.\n"
    )
    assert (
        "- **h1** (wave 3, rejected): `gym/h1@bbbbbbb`\n"
        "  - Idea: Idea of h1 \\| piped\n"
        "  - Gate: —\n"
        "  - Files: `src/a.py`, `src/b.py` (2 of 3 touched)\n"
        "  - Lesson: Lesson of h1.\n"
    ) in text
    assert text.index("**h2**") < text.index("**h1**")
    assert render_constraints([], ["src"], unrecorded=0) == (
        "No rejected or inconclusive experiment in the ledger touched these files.\n"
    )
    assert render_constraints([], ["src"], unrecorded=3) == (
        "No rejected or inconclusive experiment in the ledger touched these files; "
        "3 rejected or inconclusive experiments record no touched files.\n"
    )
    assert "Not matched: 2 such experiments" in render_constraints(matched, ["src"], unrecorded=2)


def test_constraints_name_the_tier1_or_slice_gate_of_a_recorded_row():
    rows = read_ledger(ROOT / "evals/experiments/ledger.jsonl")
    gated = next(row for row in rows if row.decision == "rejected" and row.tier1 is not None)
    row = gated.model_copy(update={"touched_files": ["src/a.py"]})
    text = render_constraints([row], ["src/a.py"], unrecorded=0)
    assert "  - Gate: REJECTED (" in text or "  - Gate: slice: " in text


def test_rewrite_keeps_unchanged_lines_and_refuses_other_changes(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    shutil.copy(ROOT / "evals/experiments/ledger.jsonl", ledger)
    before = ledger.read_text().splitlines()
    rows = read_ledger(ledger)
    index = next(i for i, row in enumerate(rows) if row.entry == "experiment")
    updated = list(rows)
    updated[index] = rows[index].model_copy(update={"touched_files": ["src/a.py"]})
    rewrite_ledger(ledger, updated)
    after = ledger.read_text().splitlines()
    assert read_ledger(ledger) == updated
    assert [line for i, line in enumerate(after) if i != index] == [
        line for i, line in enumerate(before) if i != index
    ]
    assert [path.name for path in tmp_path.iterdir()] == ["ledger.jsonl"]
    written = ledger.read_bytes()
    wrong = list(updated)
    wrong[index] = updated[index].model_copy(update={"lesson": "rewritten"})
    with pytest.raises(ValueError, match="may change only"):
        rewrite_ledger(ledger, wrong)
    with pytest.raises(ValueError, match="keep every row in its order"):
        rewrite_ledger(ledger, updated[::-1])
    assert ledger.read_bytes() == written


# CLI


def _arguments(*argv: str, format: str = "json") -> cli.CliArguments:
    return cli.parser().parse_args(["--format", format, *argv], namespace=cli.CliArguments())


async def _run(*argv: str, format: str = "json") -> int:
    args = _arguments("gym", "ledger", *argv, format=format)
    return await cli.execute(args, Terminal(args))


def _append_argv(ledger: Path, row_id: str, commit: str, *extra: str) -> list[str]:
    argv = ["append", "--ledger", str(ledger), "--id", row_id, "--entry", "experiment"]
    return [*argv, "--wave", "5", "--branch", "gym/x", "--commit", commit, *extra]


@pytest.mark.asyncio
async def test_append_fills_touched_files_from_git(tmp_path, monkeypatch):
    root, candidate = _repository(tmp_path)
    monkeypatch.chdir(root / "src")
    ledger = tmp_path / "ledger.jsonl"
    assert await _run(*_append_argv(ledger, "h1", candidate, "--decision", "rejected")) == 0
    _git(root, "merge", "-q", "--no-ff", "-m", "merge", "gym/x")
    merge = _git(root, "rev-parse", "HEAD")
    merged = ["--decision", "merged", "--merge-commit", merge]
    assert await _run(*_append_argv(ledger, "h2", candidate, *merged)) == 0
    assert [row.touched_files for row in read_ledger(ledger)] == [CANDIDATE_FILES] * 2


@pytest.mark.asyncio
async def test_an_unresolvable_commit_records_no_files_with_a_notice(tmp_path, monkeypatch, caplog):
    root, _ = _repository(tmp_path)
    monkeypatch.chdir(root)
    ledger = tmp_path / "ledger.jsonl"
    with caplog.at_level(logging.WARNING):
        assert await _run(*_append_argv(ledger, "h1", "d" * 40)) == 0
    (row,) = read_ledger(ledger)
    assert row.touched_files == []
    (notice,) = [record for record in caplog.records if record.msg == "gym.ledger_files_unresolved"]
    assert getattr(notice, "fields", {})["message"] == (
        "commit dddddddddddd is not resolvable in this checkout; the row records no touched files"
    )


@pytest.mark.asyncio
async def test_given_touched_files_win_over_git(tmp_path, monkeypatch, caplog):
    root, candidate = _repository(tmp_path)
    monkeypatch.chdir(root)
    ledger = tmp_path / "ledger.jsonl"
    given = ["--touched-files", "src/z.py", "./docs/", str(root / "src/a.py")]
    with caplog.at_level(logging.WARNING):
        assert await _run(*_append_argv(ledger, "h1", candidate, *given)) == 0
        assert await _run(*_append_argv(ledger, "h2", "d" * 40, *given)) == 0
    assert [row.touched_files for row in read_ledger(ledger)] == [
        ["docs", "src/a.py", "src/z.py"]
    ] * 2
    assert not caplog.records


@pytest.mark.asyncio
async def test_constraints_print_markdown_json_or_the_no_match_line(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    for row in (_row("h1", ["src/a.py"], wave=3), _row("h2", ["src/b/c.py"]), _row("h3", [])):
        append_ledger(ledger, row)
    common = ["--ledger", str(ledger)]
    assert await _run("constraints", "--files", "src/b", "src/a.py", *common, format="human") == 0
    text = capsys.readouterr().out
    assert text.startswith("## Prior rejected experiments on these files\n")
    assert text.index("**h2**") < text.index("**h1**")
    assert "Not matched: 1 such experiments record no touched files." in text
    argv = ["constraints", "--files", "src", "--limit", "1", *common]
    assert await _run(*argv) == 0
    assert [row["id"] for row in json.loads(capsys.readouterr().out)] == ["h2"]
    assert await _run("constraints", "--files", "docs", *common, format="markdown") == 0
    assert capsys.readouterr().out == (
        "No rejected or inconclusive experiment in the ledger touched these files; "
        "1 rejected or inconclusive experiments record no touched files.\n"
    )


@pytest.mark.asyncio
async def test_backfill_shows_without_writing_and_rewrites_with_write(
    tmp_path, monkeypatch, capsys
):
    root, candidate = _repository(tmp_path)
    monkeypatch.chdir(root)
    ledger, markdown = tmp_path / "ledger.jsonl", tmp_path / "LEDGER.md"
    shutil.copy(ROOT / "evals/experiments/LEDGER.md", markdown)
    known = _row("h0", ["kept.py"]).model_copy(update={"commit": candidate})
    resolvable = _row("h1", []).model_copy(update={"commit": candidate})
    reference = {"entry": "baseline", "tier": "tier1", "decision": None, "objective_j": 0.5}
    baseline = LedgerRow.model_validate(
        {**_row("r0", []).model_dump(), **reference, "dataset_digest": "d" * 64}
    )
    for row in (baseline, known, resolvable, _row("h2", [])):
        append_ledger(ledger, row)
    before, rendered = ledger.read_bytes(), markdown.read_bytes()
    common = ["--ledger", str(ledger), "--markdown", str(markdown)]

    assert await _run("backfill", *common, format="human") == 0
    assert capsys.readouterr().out == (
        f"h1 `{candidate[:7]}`: 4 files (docs/b.md, src/a.py, src/new.py +1)\n"
        "h2 `bbbbbbb`: commit not resolvable in this checkout\n"
        "would change 1 of 2 experiment rows without touched files; 1 unresolved; "
        "pass --write to rewrite the ledger and LEDGER.md\n"
    )
    assert (ledger.read_bytes(), markdown.read_bytes()) == (before, rendered)

    assert await _run("backfill", "--write", *common) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["written"] is True
    assert record["rows"] == [
        {"id": "h1", "touched_files": CANDIDATE_FILES},
        {"id": "h2", "touched_files": None},
    ]
    rows = read_ledger(ledger)
    assert rows == [
        baseline,
        known,
        resolvable.model_copy(update={"touched_files": CANDIDATE_FILES}),
        _row("h2", []),
    ]
    lines, stored = ledger.read_text().splitlines(), before.decode().splitlines()
    assert [lines[0], lines[1], lines[3]] == [stored[0], stored[1], stored[3]]
    assert f"| h1 | accuracy | `gym/h1@{candidate[:7]}` | `docs/b.md`, `src/a.py` +2 |" in (
        markdown.read_text()
    )
