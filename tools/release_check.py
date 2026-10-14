"""Release check: decide from committed live baselines, with no model call, whether the v2 agents and chain may ship.

Prepared while gates are deferred (docs/design/gates-and-release.md); nothing runs it on the PR path until Al turns
the gates on. Three subcommands, all offline and deterministic:

``check``   For each agent and the chain: the committed live baseline for each set its release policy names (the
            suite's first set when the policy names none) must exist, must have been measured on the current agent
            (every identity key the eval spec records, plus the set's dataset digest, equals the baseline's), and must
            pass its release policy with every threshold set. Exit 1 when anything is missing, stale or failing.
``gate``    The enabling gate (SPEC-0082 "Acceptance and validation"): every agent has a committed live baseline, and
            the chain's live baseline gets both directions right (a correct LIKELY_EXPLOITABLE with its fix result
            and a correct LIKELY_NOT_EXPLOITABLE) in at least three languages. Exit 1 until it holds.
``propose`` Print suggested thresholds for one agent from its committed baseline. It never edits a policy, which is
            operator-owned; a person copies what they accept.

Baselines live beside the cases: ``<eval root>/baselines/<set>-live.json`` is the promoted run's summary without
per-attempt rows, written by ``make baseline-commit AGENT= RUN=`` (``evals/run.py --commit-baseline``). An unobserved metric or missing provenance is unknown, which
never passes.

Usage: uv run --locked python tools/release_check.py {check,gate,propose AGENT} [--agent NAME ...]
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from evals import agent_summary  # noqa: E402
from evals.cases import AGENTS, CHAIN, agent_root, set_digest, set_names  # noqa: E402

DECISIVE = ("LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE")
GATE_LANGUAGES = 3
# Suggested margins for `propose`; the accepted values are Al's call (docs/design/gates-and-release.md).
ACCURACY_MARGIN = 0.05
EFFICIENCY_MARGIN = 0.25


def evaluated() -> list[str]:
    """Agents (and the chain) that have an eval suite; an agent without one has nothing to baseline yet."""
    return [name for name in (*AGENTS, CHAIN) if (agent_root(name) / "evaluate.py").exists()]


def spec_identity(agent: str) -> dict:
    module = "evals.e2e.evaluate" if agent == CHAIN else f"corsair.agents.{agent}.evals.evaluate"
    return dict(importlib.import_module(module).SPEC.identity)


def policy_path(agent: str) -> Path:
    return agent_root(agent) / "release-policy.yaml"


def policy_sets(agent: str) -> list[str]:
    policy = yaml.safe_load(policy_path(agent).read_text()) or {}
    named = (policy.get("applies_to") or {}).get("sets") or []
    available = set_names(agent_root(agent))
    if agent == CHAIN:  # the chain scorer reads only its own sets; older e2e sets keep their runners
        from evals.run import CHAIN_SETS
        available = [name for name in CHAIN_SETS if name in available]
    return list(named) or available[:1]


def baseline_path(agent: str, set_name: str) -> Path:
    return agent_root(agent) / "baselines" / f"{set_name}-live.json"


def load_baseline(agent: str, set_name: str) -> dict | None:
    path = baseline_path(agent, set_name)
    return json.loads(path.read_text()) if path.exists() else None


def stale_keys(agent: str, set_name: str, baseline: dict) -> list[str]:
    """Identity keys on which the committed baseline differs from the agent as it stands."""
    identity = baseline.get("identity") or {}
    current = spec_identity(agent) | {"dataset_sha256": set_digest(agent_root(agent), set_name)}
    return sorted(key for key, value in current.items() if identity.get(key) != value)


def check_one(agent: str, set_name: str) -> tuple[str, list[str]]:
    """``pass`` or ``fail`` with reasons for one agent and set."""
    baseline = load_baseline(agent, set_name)
    if baseline is None:
        path = baseline_path(agent, set_name)
        return "fail", [f"no committed live baseline at {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"]
    reasons = []
    if baseline.get("mode") != "live":
        reasons.append(f"baseline mode is {baseline.get('mode')!r}, not live")
    if baseline.get("language"):
        reasons.append("baseline is a language-narrowed run")
    if stale := stale_keys(agent, set_name, baseline):
        reasons.append("baseline measured a different agent: " + ", ".join(stale))
    verdict = agent_summary.apply_policy(baseline, policy_path(agent))
    if verdict["status"] == "missing":
        reasons.append("no release-policy.yaml")
    else:
        if verdict["deferred"]:
            reasons.append("release policy is not enforced (enforced: false)")
        if not verdict["in_scope"]:
            reasons.append("release policy does not apply to this set and mode")
        for name, entry in verdict["entries"].items():
            if entry["status"] != "pass":
                reasons.append(f"{name}: {entry['status']} (value {entry['value']}, limit {entry['limit']})")
        if verdict["missing_provenance"]:
            reasons.append("missing provenance: " + ", ".join(verdict["missing_provenance"]))
    return ("fail" if reasons else "pass"), reasons


def check(agents: list[str]) -> int:
    failed = False
    for agent in agents:
        for set_name in policy_sets(agent):
            status, reasons = check_one(agent, set_name)
            failed |= status != "pass"
            print(f"{status.upper():4}  {agent} {set_name}")
            for reason in reasons:
                print(f"      {reason}")
    return 1 if failed else 0


def decisive_languages(summary: dict) -> list[str]:
    """Languages where the live chain got both directions right: at least one case expected LIKELY_EXPLOITABLE
    labelled so and at least one expected LIKELY_NOT_EXPLOITABLE labelled so. A committed baseline carries the
    per-language dispositions, not per-attempt rows; a LIKELY_EXPLOITABLE label already requires the differential
    result on the fixed revision (D12/R4). Language-free (``common``) cases do not count."""
    languages = []
    for language, group in sorted(((summary.get("rollups") or {}).get("by_language") or {}).items()):
        per_label = (group.get("dispositions") or {}).get("accuracy_by_expected_label") or {}
        if language != "common" and all((per_label.get(label) or {}).get("passed", 0) >= 1 for label in DECISIVE):
            languages.append(language)
    return languages


def gate() -> int:
    held = True
    for agent in evaluated():
        sets = policy_sets(agent)
        present = [s for s in sets if (b := load_baseline(agent, s)) is not None and b.get("mode") == "live"]
        ok = bool(sets) and present == sets
        held &= ok
        print(f"{'ok' if ok else 'MISSING':7}  live baseline: {agent} ({', '.join(sets) or 'no set'})")
    missing = [agent for agent in AGENTS if agent not in evaluated()]
    for agent in missing:
        held = False
        print(f"MISSING  eval suite: {agent}")
    languages = []
    for set_name in policy_sets(CHAIN):
        baseline = load_baseline(CHAIN, set_name)
        if baseline is not None and baseline.get("mode") == "live":
            languages = sorted(set(languages) | set(decisive_languages(baseline)))
    ok = len(languages) >= GATE_LANGUAGES
    held &= ok
    print(f"{'ok' if ok else 'MISSING':7}  end to end, both directions correct: "
          f"{len(languages)}/{GATE_LANGUAGES} languages ({', '.join(languages) or 'none'})")
    print("gate holds" if held else "gate does not hold")
    return 0 if held else 1


def propose(agent: str) -> int:
    """Thresholds a person may adopt: accuracy a margin below the baseline, efficiency a margin above it."""
    for set_name in policy_sets(agent):
        baseline = load_baseline(agent, set_name)
        if baseline is None or not baseline.get("rollups"):
            print(f"# {agent} {set_name}: no committed live baseline")
            continue
        rollups = baseline["rollups"]
        overall = rollups["all"]

        def floor(stat):
            return None if stat is None or not stat.get("total") else round(
                max(0.0, stat["passed"] / stat["total"] - ACCURACY_MARGIN), 3)
        accuracy = {}
        for dimension, stat in (overall.get("dimensions") or {}).items():
            if dimension in ("contract", "safety"):
                continue  # hard gates, never relaxed from a measurement
            by_language = {language: value for language, group in sorted((rollups.get("by_language") or {}).items())
                           if (value := floor((group.get("dimensions") or {}).get(dimension))) is not None}
            accuracy[dimension] = {"min": floor(stat), "by_language": by_language}
        thresholds = {"accuracy": accuracy}
        attempts = overall.get("attempts")
        if attempts:
            thresholds["clean_attempt_rate"] = {"min": round(max(0.0, overall["clean_attempts"] / attempts
                                                                 - ACCURACY_MARGIN), 3)}
        for metric, statistic in (("latency_s", "p90"), ("input_tokens", "mean"), ("output_tokens", "mean"),
                                  ("requests", "p90"), ("tool_calls", "p90")):
            value = (overall.get(metric) or {}).get(statistic)
            if value is not None:
                thresholds[metric] = {f"{statistic}_max": round(value * (1 + EFFICIENCY_MARGIN), 3)}
        print(f"# {agent} {set_name}: proposed from {baseline.get('run')} "
              f"(accuracy -{ACCURACY_MARGIN}, efficiency +{EFFICIENCY_MARGIN:.0%})")
        print(yaml.safe_dump({"applies_to": {"sets": [set_name], "mode": "live"}, "thresholds": thresholds},
                             sort_keys=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("check")
    one.add_argument("--agent", action="append", choices=(*AGENTS, CHAIN))
    commands.add_parser("gate")
    proposal = commands.add_parser("propose")
    proposal.add_argument("agent", choices=(*AGENTS, CHAIN))
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.agent or evaluated())
    if args.command == "gate":
        return gate()
    return propose(args.agent)


if __name__ == "__main__":
    sys.exit(main())
