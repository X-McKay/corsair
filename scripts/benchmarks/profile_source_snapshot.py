#!/usr/bin/env python3
"""Profile local source admission and snapshot reads on a tree near the admission limits.

Builds a synthetic Python tree (default 990 files, about 7 MiB) under ``.work/``, then
times, per run and in a fresh artifact store: the first admission, a second admission
of the identical tree, ``prepare_case``, the per-episode ``StoredSourceReader``
construction, ``read_file`` calls (``read_text`` with the default tool budget) and
``list_files`` calls (``iter_files`` names, as the producer tool consumes them). It also
checks that a symbolic link, a FIFO and an oracle file each make admission refuse the
tree. No target code runs and nothing leaves the host.
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import time
from collections.abc import Callable
from pathlib import Path

from corsair.adapters.scm.local import (
    SourceAdmissionError,
    StoredSourceReader,
    prepare_case,
    snapshot_source,
)
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import Case, Finding, PythonRecipe, RunManifest, Source
from corsair.settings import Settings

_TOOL_OUTPUT_BYTES = 32768


def _module_text(index: int, size: int) -> str:
    header = f'"""Synthetic module {index}."""\n\n\ndef read_file(root, path):\n    return path\n\n'
    filler = f"VALUE_{index} = {'x' * 60!r}\n"
    body = filler * max(0, (size - len(header)) // len(filler))
    return header + body


def build_tree(root: Path, files: int, total_bytes: int) -> Path:
    """Write ``files`` modules across nested packages; return the tree path."""
    if root.exists():
        shutil.rmtree(root)
    project = root / "project"
    per_file = total_bytes // files
    for index in range(files):
        package = project / f"pkg{index % 20:02d}" / f"sub{index % 7}"
        package.mkdir(parents=True, exist_ok=True)
        (package / f"module_{index:04d}.py").write_text(
            _module_text(index, per_file), encoding="utf-8"
        )
    (project / "reader.py").write_text(_module_text(-1, 2048), encoding="utf-8")
    return project


def _refusal_variants(root: Path, project: Path) -> dict[str, Path]:
    """Copy the tree three times, each with one entry admission must refuse."""
    variants: dict[str, Path] = {}
    for label in ("symlink", "fifo", "oracle"):
        target = root / f"refuse-{label}"
        shutil.copytree(project, target)
        planted = target / "pkg05" / "sub1"
        if label == "symlink":
            os.symlink("/etc/hostname", planted / "link.py")
        elif label == "fifo":
            os.mkfifo(planted / "pipe.py")
        else:
            (planted / "oracle.json").write_text("{}", encoding="utf-8")
        variants[label] = target
    return variants


def _manifest() -> RunManifest:
    return RunManifest(
        package_version="0.1",
        request_digest="1" * 64,
        config_digest="2" * 64,
        producer_prompt_digest="3" * 64,
        auditor_prompt_digest="4" * 64,
        image_id="sha256:profile",
        models={"producer": "profile", "auditor": "profile"},
    )


def _timed(action: Callable[[], object], repeats: int = 1) -> float:
    started = time.perf_counter()
    for _ in range(repeats):
        action()
    return (time.perf_counter() - started) * 1000


def profile_run(root: Path, project: Path, reads: int, lists: int, run: int) -> dict[str, float]:
    store_root = root / f"store-{run}"
    if store_root.exists():
        shutil.rmtree(store_root)
    settings = Settings(source_root=str(root), artifact_root=str(store_root))
    store = ArtifactStore(store_root)
    source = Source(path=project.name)
    case = Case(
        case_id="profile-case",
        finding=Finding(title="read", description="profile", file="reader.py", line=4),
        source=source,
        recipe=PythonRecipe(
            module_file="reader.py",
            function="read_file",
            payload_parameter="path",
            fixed_kwargs={"root": "/fixtures/allowed"},
        ),
    )
    row: dict[str, float] = {}
    refs: list[object] = []
    row["admit first"] = _timed(lambda: refs.append(snapshot_source(source, settings, store)))
    row["admit identical"] = _timed(lambda: refs.append(snapshot_source(source, settings, store)))
    if refs[0] != refs[1]:
        raise SystemExit("identical tree produced a different snapshot reference")
    prepared = prepare_case(case, settings, store, _manifest())
    row["prepare_case"] = _timed(lambda: prepare_case(case, settings, store, _manifest()))
    row["reader construct"] = _timed(lambda: StoredSourceReader(ArtifactStore(store_root)))
    reader = StoredSourceReader(store)
    names = [name for name, _ in reader.iter_files(prepared.source)]
    picks = [names[(index * 37) % len(names)] for index in range(reads)]

    def read_all() -> None:
        for path in picks:
            reader.read_text(prepared.source, path, max_bytes=_TOOL_OUTPUT_BYTES)

    row[f"read_file x{reads}"] = _timed(read_all)
    row[f"list_files x{lists}"] = _timed(
        lambda: [name for name, _ in reader.iter_files(prepared.source)], lists
    )
    row["snapshot MiB"] = prepared.source.size / 1_048_576
    row["files"] = float(len(names))
    return row


def check_refusals(root: Path, project: Path) -> dict[str, str]:
    settings = Settings(source_root=str(root), artifact_root=str(root / "store-refusal"))
    store = ArtifactStore(root / "store-refusal")
    results: dict[str, str] = {}
    for label, variant in _refusal_variants(root, project).items():
        try:
            snapshot_source(Source(path=variant.name), settings, store)
        except SourceAdmissionError as error:
            results[label] = f"refused: {error}"
        else:
            raise SystemExit(f"admission accepted the {label} variant")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(".work/source-profile"))
    parser.add_argument("--files", type=int, default=990)
    parser.add_argument("--bytes", type=int, default=7 * 1_048_576)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--reads", type=int, default=50)
    parser.add_argument("--lists", type=int, default=20)
    args = parser.parse_args()
    root = args.root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    project = build_tree(root, args.files, args.bytes)
    for label, result in check_refusals(root, project).items():
        print(f"{label:8} {result}")
    rows = [profile_run(root, project, args.reads, args.lists, run) for run in range(args.runs)]
    print(f"\n| measure (ms) | {' | '.join(f'run {i + 1}' for i in range(args.runs))} | median |")
    print(f"|---|{'---|' * args.runs}---|")
    for key in rows[0]:
        values = [row[key] for row in rows]
        cells = " | ".join(f"{value:,.1f}" for value in values)
        print(f"| {key} | {cells} | {statistics.median(values):,.1f} |")


if __name__ == "__main__":
    main()
