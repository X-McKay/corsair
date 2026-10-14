"""Agent x language eval case counts across every runnable host eval set (PLAN-0094).

    PYTHONPATH=src:. .venv/bin/python -m evals.inventory            # Markdown table
    PYTHONPATH=src:. .venv/bin/python -m evals.inventory --json

One case is one frozen dataset entry with its own input and oracle that `make eval AGENT=<agent> SET=<set>` scores;
repeats are not cases. Per-case sets (evals/cases.py) carry their language in case.json. The older single-file sets
record no language: their cases are Python apart from the few listed in LEGACY_LANGUAGE. Corpus pairs under
benchmarks/corpus count nowhere here, since no agent eval reads them. Sets the suites refuse (retired held-out
planning sets) are not counted. Pending sets hold cases that fail today for a recorded production gap.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

import yaml

from evals.cases import EVALS, LANGUAGES, load_set, manifest

LANGUAGE_ORDER = ("python", "java", "javascript", "ruby", "perl")
# Older single-file sets: (agent, set) -> (path, loader key). Their cases are Python unless listed below.
LEGACY = {
    ("environment", "development"): "environment/cases.json",
    ("identification", "development"): "issue_identification/cases.yaml",
    ("planning", "development"): "test_planning/cases.yaml",
    ("planning", "heldout3"): "test_planning/cases-heldout-3.yaml",
    ("planning", "unit"): "test_planning/cases-unit.yaml",
    ("authoring", "development"): "test_authoring/cases.yaml",
    ("authoring", "unit"): "test_authoring/cases-unit.yaml",
    ("assessment", "development+held_out"): "evidence_assessment/cases.yaml",
    ("assessment", "unit"): "evidence_assessment/unit_test_cases.json",
}
LEGACY_LANGUAGE = {("environment", "java-ready"): "java", ("identification", "command_target"): "ruby",
                   ("identification", "missing_source"): "none"}
# Per-case sets: (agent, set) -> suite directory.
PER_CASE = {
    ("environment", "breadth"): "environment",
    ("identification", "breadth"): "issue_identification",
    ("planning", "breadth"): "test_planning",
    ("authoring", "breadth"): "test_authoring",
    ("assessment", "breadth"): "evidence_assessment",
}
PENDING = {("authoring", "breadth_pending"): "test_authoring"}
AGENTS = ("environment", "identification", "planning", "authoring", "assessment")


def _legacy_names(path: Path) -> list[str]:
    data = json.loads(path.read_text()) if path.suffix == ".json" else yaml.safe_load(path.read_text())
    cases = data["cases"] if isinstance(data, dict) else data
    return [case["name"] for case in cases]


def counts(include_pending: bool = False) -> dict[tuple[str, str], Counter]:
    """(agent, set) -> language counter, for every set present in this checkout."""
    found: dict[tuple[str, str], Counter] = {}
    for key, relative in LEGACY.items():
        names = _legacy_names(EVALS / relative)
        found[key] = Counter(LEGACY_LANGUAGE.get((key[0], name), "python") for name in names)
    for key, suite in (PER_CASE | (PENDING if include_pending else {})).items():
        if (EVALS / suite / "sets" / f"{key[1]}.json").exists():
            found[key] = Counter(case.case["language"] for case in load_set(suite, key[1]))
    return found


def table(found: dict[tuple[str, str], Counter]) -> dict[str, dict[str, int]]:
    totals = {agent: {language: 0 for language in LANGUAGES} for agent in AGENTS}
    for (agent, name), counter in found.items():
        if (agent, name) in PENDING:
            continue
        for language, count in counter.items():
            totals[agent][language] += count
    return totals


def markdown(found: dict[tuple[str, str], Counter]) -> str:
    totals = table(found)
    lines = ["| Agent | " + " | ".join(LANGUAGE_ORDER) + " | no language |", "|---" * (len(LANGUAGE_ORDER) + 2) + "|"]
    for agent in AGENTS:
        cells = []
        for language in (*LANGUAGE_ORDER, "none"):
            parts = [f"{name} {found[(a, name)][language]}" for (a, name) in found
                     if a == agent and (a, name) not in PENDING and found[(a, name)][language]]
            cells.append(f"**{totals[agent][language]}**" + (f" ({', '.join(parts)})" if parts else ""))
        lines.append(f"| {agent} | " + " | ".join(cells) + " |")
    pending = [f"{agent} {name}: " + ", ".join(f"{language} {count}" for language, count in sorted(counter.items()))
               for (agent, name), counter in found.items() if (agent, name) in PENDING]
    if pending:
        lines += ["", "Pending (fail today for a recorded production gap, not counted): " + "; ".join(pending)]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    found = counts(include_pending=True)
    if args.json:
        print(json.dumps({f"{agent}/{name}": dict(counter) for (agent, name), counter in found.items()}, indent=2))
    else:
        print(markdown(found))


if __name__ == "__main__":
    main()
