"""Agent x language eval case counts over every frozen set (PLAN-0094).

    PYTHONPATH=src:. .venv/bin/python -m evals.inventory            # Markdown table
    PYTHONPATH=src:. .venv/bin/python -m evals.inventory --json

One case is one frozen per-case directory with its own input and oracle that `make eval AGENT=<agent> SET=<set>`
scores; repeats are not cases. The language comes from each case's directory (evals/cases.py). Sets the suites
refuse (retired planning held-out sets) and pending sets (cases that fail today for a recorded production gap) are
listed apart and not counted.
"""

import argparse
from collections import Counter
import json

from evals.cases import LANGUAGES, load_set, set_names

# make eval AGENT= name -> eval package; e2e is the chain's case data (AGENT=chain)
SUITES = {"environment": "environment", "identification": "issue_identification", "planning": "test_planning",
          "authoring": "test_authoring", "assessment": "evidence_assessment", "e2e": "e2e"}
RETIRED = {("planning", "heldout"), ("planning", "heldout2")}
PENDING = {("authoring", "breadth_pending")}
# Issue requests run through `corsair run --issue-json`, not scored by `make eval`.
REQUESTS = {("e2e", "corpus"), ("e2e", "corpus_negative")}


def counts() -> dict[tuple[str, str], Counter]:
    """(agent, set) -> language counter for every set of every agent suite."""
    return {(agent, name): Counter(case.language for case in load_set(suite, name))
            for agent, suite in SUITES.items() for name in set_names(suite)}


def totals(found: dict[tuple[str, str], Counter]) -> dict[str, Counter]:
    result = {agent: Counter() for agent in SUITES}
    for key, counter in found.items():
        if key not in RETIRED | PENDING | REQUESTS:
            result[key[0]].update(counter)
    return result


def markdown(found: dict[tuple[str, str], Counter]) -> str:
    summed = totals(found)
    lines = ["| Agent | " + " | ".join(LANGUAGES) + " |", "|---" * (len(LANGUAGES) + 1) + "|"]
    for agent in SUITES:
        cells = []
        for language in LANGUAGES:
            parts = [f"{name} {counter[language]}" for (a, name), counter in found.items()
                     if a == agent and (a, name) not in RETIRED | PENDING | REQUESTS and counter[language]]
            cells.append(f"**{summed[agent][language]}**" + (f" ({', '.join(parts)})" if parts else ""))
        lines.append(f"| {agent} | " + " | ".join(cells) + " |")
    for title, keys in (("Pending, not counted (fail today for a recorded production gap)", PENDING),
                        ("Retired, not counted (the suite refuses them)", RETIRED),
                        ("Issue requests, not counted (run with corsair run, no make eval scorer)", REQUESTS)):
        rows = [f"{agent} {name}: " + ", ".join(f"{language} {count}" for language, count in sorted(found[(agent, name)].items()))
                for agent, name in sorted(keys) if (agent, name) in found]
        if rows:
            lines += ["", f"{title}: " + "; ".join(rows)]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    found = counts()
    if args.json:
        print(json.dumps({f"{agent}/{name}": dict(counter) for (agent, name), counter in found.items()}, indent=2))
    else:
        print(markdown(found))


if __name__ == "__main__":
    main()
