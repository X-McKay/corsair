"""Denominator report over all inventory rows (IDEA-0005 step 1); counts metadata only, runs nothing.

A row counts once per value of each dimension; a row blocked by several gaps counts once under each gap.
"""
import argparse
from collections import Counter
import json
from typing import get_args

from evals.benchmark.cases import BenchmarkEntry, Gap, load

DIMENSIONS = ("language", "build_system", "cwe", "manifest", "admission", "blocking")


def counts(entries: tuple[BenchmarkEntry, ...]) -> dict:
    by = {name: Counter() for name in DIMENSIONS}
    for entry in entries:
        row = entry.inventory
        by["language"][row.language] += 1
        by["build_system"][row.build_system] += 1
        by["cwe"][row.cwe or "unrecorded"] += 1
        by["manifest"]["present" if entry.manifest else "absent"] += 1
        by["admission"][entry.admission] += 1
        by["blocking"].update(set(entry.blocking))
    ordered = {name: dict(sorted(counter.items())) for name, counter in by.items()}
    ordered["blocking"] = {gap: by["blocking"][gap] for gap in get_args(Gap) if gap in by["blocking"]}
    return {"total": len(entries), "by": ordered}


def markdown(report: dict) -> str:
    lines = [f"Cases: {report['total']}", "", "| Dimension | Value | Cases |", "| --- | --- | --- |"]
    lines += [f"| {name} | {value} | {count} |" for name, values in report["by"].items()
              for value, count in values.items()]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    report = counts(load())
    print(json.dumps(report, indent=2) if args.format == "json" else markdown(report))


if __name__ == "__main__":
    main()
