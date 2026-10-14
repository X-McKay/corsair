"""One command per agent: run its eval suite on the host and file the result for comparison (SPEC-0044).

    make eval AGENT=<agent> [SET=<set>] [PROVIDER_CONFIG=<providers.json>] [REPEAT=3] [NOTE=...]
    make eval-baseline AGENT=<agent> RUN=<run id>
    make baseline-commit AGENT=<agent> RUN=<run id>     v2: also write the committed baseline file

Each suite keeps its own CLI and native report; this wrapper only chooses an evidence directory, runs the
suite in a subprocess with the repository's PYTHONPATH, and writes a summary and a comparison against the
promoted baseline (or else the previous run) with the same set and mode. Nothing here needs a cluster.

    .runs/evals/<agent>/
      index.jsonl                        one line per run
      baseline-<set>-<mode>.json         promoted run id
      <run id>/                          <UTC stamp>-<set>-<mode>
        command.json                     argv, git commit and dirty state, exit code, times
        evidence/                        the suite's configuration.json, report.json and attempt receipts
        summary.json                     versions, model, dataset digest, assertion pass rates, efficiency means
        comparison.md                    differences against the reference run

A v2 baseline is also committed beside the agent's cases, ``<agent evals>/baselines/<set>-<mode>.json``: the run's
summary without per-attempt rows, plus its policy status. A checkout without that run's ``.runs/`` (another host,
CI) compares against the committed file.
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from evals import agent_summary
from evals.cases import AGENTS, AGENTS_PACKAGE, CHAIN, agent_root, set_names

# v2 agents plus the whole chain, which is scored by the same runner over evals/e2e/ (evals/e2e/evaluate.py)
V2_AGENTS = (*AGENTS, CHAIN)
CHAIN_MODULE = "evals.e2e.evaluate"
CHAIN_SETS = ("v2",)  # the e2e sets the chain scorer reads; the older e2e sets keep their own runners

REPOSITORY = Path(__file__).resolve().parents[1]
RESULTS = REPOSITORY / ".runs" / "evals"
# Top-level suite identity; the chain nests per-stage prompt/config/skill under "versions" and names its live stages.
# toolset_sha256 digests the offered tool definitions (SPEC-0052); suites that do not report it leave it absent.
IDENTITY = ("harness_version", "pydantic_ai_version", "factory_source_sha256", "shared_helper_source_sha256", "spec_sha256", "capability_selection_sha256", "budget_policy_sha256", "effective_budget_sha256", "prompt_version", "config_version", "skill_sha256", "toolset_sha256", "versions", "live_stages", "composition", "model",
            "evaluator_version", "dataset", "dataset_sha256", "mode", "runner", "execution", "budget")


@dataclass(frozen=True)
class Suite:
    module: str
    sets: dict[str, tuple[str, ...]]
    repeat: bool = True
    live: tuple[str, ...] = ()
    note: str = ""
    # Sets served by another module than `module`, e.g. the chain's benchmark case cohorts.
    set_modules: dict[str, str] = field(default_factory=dict)


# v2 agents register their suites here as they gain one (src/corsair/README.md); the v1 suites were removed.
SUITES: dict[str, Suite] = {}

# Scorers whose CLI narrows a per-case set to one language (`--language`, evals/cases.py); every other set refuses
# EVAL_LANGUAGE before anything runs. v2 agents add theirs as they register.
LANGUAGE_MODULES: frozenset[str] = frozenset({CHAIN_MODULE})


def narrows_by_language(suite: Suite, set_name: str) -> bool:
    module = suite.set_modules.get(set_name, suite.module)
    return module in LANGUAGE_MODULES or module.startswith(AGENTS_PACKAGE + ".")


def v2_suite(agent: str) -> Suite | None:
    """A v2 agent's suite: its evals/evaluate.py over the sets in its own evals/sets/ (evals/cases.py agent_root)."""
    root = agent_root(agent)
    if not (root / "evaluate.py").exists():
        return None
    if agent == CHAIN:
        return Suite(CHAIN_MODULE, {name: ("--set", name) for name in CHAIN_SETS if name in set_names(root)})
    return Suite(f"{AGENTS_PACKAGE}.{agent}.evals.evaluate", {name: ("--set", name) for name in set_names(root)})


# Agents without an isolated eval set yet, and where the gap is planned.
MISSING = {}


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=REPOSITORY, capture_output=True, text=True, check=False).stdout.strip()


def summarize(evidence: Path) -> dict:
    """Pass rates per assertion and per case, efficiency means and suite identity from the native report."""
    configuration = json.loads((evidence / "configuration.json").read_text()) if (evidence / "configuration.json").exists() else {}
    identity = {key: configuration[key] for key in IDENTITY if key in configuration}
    if not (evidence / "report.json").exists():
        return {"identity": identity, "report": "missing"}
    report = json.loads((evidence / "report.json").read_text())
    assertions: dict[str, list[int]] = {}
    cases: dict[str, dict] = {}
    metrics: dict[str, list[float]] = {}
    for case in report["cases"]:
        name = case.get("source_case_name") or case["name"]
        entry = cases.setdefault(name, {"attempts": 0, "clean": 0, "failed_assertions": {}})
        values = {key: bool(item["value"]) for key, item in case["assertions"].items()}
        entry["attempts"] += 1
        entry["clean"] += int(bool(values) and all(values.values()) and not case["evaluator_failures"])
        for key, value in values.items():
            assertions.setdefault(key, [0, 0])[0] += int(value)
            assertions[key][1] += 1
            if not value:
                entry["failed_assertions"][key] = entry["failed_assertions"].get(key, 0) + 1
        # record_count keeps measured zeros in attributes because native Evals drops
        # zero increments. Use that fallback once per metric, without filling missing data.
        observed = {
            key: value for key, value in case.get("attributes", {}).items()
            if key.startswith("observed_") and isinstance(value, (int, float))
            and not isinstance(value, bool)
        }
        for key, value in (observed | case["metrics"]).items():
            # RunUsage defaults to zero and can contain partial response totals.
            # Neither is a complete token measurement when provider coverage failed.
            if (case.get("attributes", {}).get("provider_usage_present") is False
                    and key in {"observed_input_tokens", "observed_output_tokens",
                                "input_tokens", "output_tokens"}):
                continue
            metrics.setdefault(key, []).append(value)
        for key, item in case["scores"].items():
            metrics.setdefault("score_" + key, []).append(item["value"])
        metrics.setdefault("task_seconds", []).append(case["task_duration"])
    for failure in report["failures"]:
        name = failure.get("source_case_name") or failure["name"]
        entry = cases.setdefault(name, {"attempts": 0, "clean": 0, "failed_assertions": {}})
        entry["attempts"] += 1
        entry.setdefault("task_failures", []).append(failure.get("error_message", "")[:300])
    attempts = sum(entry["attempts"] for entry in cases.values())
    outcomes = json.loads((evidence / "outcomes.json").read_text()) if (evidence / "outcomes.json").exists() else None
    return {"identity": identity,
            **({"semantic_outcomes": outcomes} if outcomes is not None else {}),
            "attempts": attempts, "clean_attempts": sum(entry["clean"] for entry in cases.values()),
            "task_failures": len(report["failures"]),
            "assertions": {key: {"passed": p, "total": t} for key, (p, t) in sorted(assertions.items())},
            "cases": dict(sorted(cases.items())),
            "efficiency_samples": {key: {"observed": len(values), "attempts": attempts} for key, values in sorted(metrics.items())},
            "efficiency_mean": {key: round(sum(v) / len(v), 3) for key, v in sorted(metrics.items())}}


def _rate(item: dict | None) -> str:
    return "-" if item is None else f"{item['passed']}/{item['total']}"


def compare(current: dict, reference: dict | None, reference_id: str | None) -> str:
    """Markdown differences; identity changes are listed first because they decide comparability."""
    summary = current["summary"]
    if summary.get("report") == "missing":
        return f"# {current['agent']} {current['run']}\n\nReport missing: attempt counts, failures and telemetry are unknown.\n"
    lines = [f"# {current['agent']} {current['run']}", "",
             f"Clean attempts: {summary.get('clean_attempts', 0)}/{summary.get('attempts', 0)}"
             f" (task failures {summary.get('task_failures', 0)})", ""]
    if "semantic_outcomes" in summary:
        counts = summary["semantic_outcomes"]["outcomes"]
        lines += ["Review outcomes: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())),
                  "Contract failures are not successful semantic rejections; evaluator defects are separate.", ""]
    if reference is None:
        return "\n".join(lines + ["No earlier run with this set and mode; nothing to compare.", ""])
    before = reference["summary"]
    if before.get("report") == "missing":
        return "\n".join(lines + [f"Reference {reference_id} has a missing report; comparison unavailable.", ""])
    lines += [f"Compared with {reference_id} ({reference['reference_kind']}): clean attempts "
              f"{before.get('clean_attempts', 0)}/{before.get('attempts', 0)}.", ""]
    changed = {key: (before["identity"].get(key), summary["identity"].get(key)) for key in IDENTITY
               if before["identity"].get(key) != summary["identity"].get(key)}
    if changed:
        lines += ["## Changed identity", ""] + [f"- `{key}`: {json.dumps(old)} -> {json.dumps(new)}"
                                                for key, (old, new) in changed.items()]
        if "dataset_sha256" in changed:
            lines.append("- The case set changed: scores are not directly comparable.")
        lines.append("")
    keys = sorted(set(summary.get("assertions", {})) | set(before.get("assertions", {})))
    rows = [(key, _rate(before.get("assertions", {}).get(key)), _rate(summary.get("assertions", {}).get(key)))
            for key in keys]
    lines += ["## Assertions", "", "| Assertion | Before | Now |", "| --- | --- | --- |"]
    lines += [f"| {key} | {old} | {new}{' ←' if old != new else ''} |" for key, old, new in rows]
    names = sorted(set(summary.get("cases", {})) | set(before.get("cases", {})))
    clean = lambda s, name: (lambda c: "-" if c is None else f"{c['clean']}/{c['attempts']}")(s.get("cases", {}).get(name))
    lines += ["", "## Cases (clean attempts)", "", "| Case | Before | Now |", "| --- | --- | --- |"]
    lines += [f"| {name} | {clean(before, name)} | {clean(summary, name)}"
              f"{' ←' if clean(before, name) != clean(summary, name) else ''} |" for name in names]
    metric_keys = sorted(set(summary.get("efficiency_mean", {})) | set(before.get("efficiency_mean", {})))
    lines += ["", "## Efficiency (mean per observed sample)", "", "| Metric | Before | Now |", "| --- | --- | --- |"]
    lines += [f"| {key} | {before.get('efficiency_mean', {}).get(key, '-')} | {summary.get('efficiency_mean', {}).get(key, '-')} |"
              for key in metric_keys]
    lines += ["", "Metric means use only observed samples; absent telemetry is unknown.", ""]
    for key, coverage in summary.get("efficiency_samples", {}).items():
        lines.append(f"- `{key}` coverage: {coverage['observed']}/{coverage['attempts']} attempts")
    return "\n".join(lines + [""])


def _reference(agent_dir: Path, set_name: str, mode: str, run_id: str) -> tuple[str | None, dict | None]:
    pointer = agent_dir / f"baseline-{set_name}-{mode}.json"
    if pointer.exists():
        baseline = json.loads(pointer.read_text())["run"]
        record = json.loads((agent_dir / baseline / "summary.json").read_text())
        return baseline, record | {"reference_kind": "baseline"}
    index = agent_dir / "index.jsonl"
    earlier = [json.loads(line) for line in index.read_text().splitlines()] if index.exists() else []
    earlier = [row for row in earlier if row["set"] == set_name and row["mode"] == mode and row["run"] != run_id
               and (agent_dir / row["run"] / "summary.json").exists()]
    if not earlier:
        return None, None
    previous = earlier[-1]["run"]
    return previous, json.loads((agent_dir / previous / "summary.json").read_text()) | {"reference_kind": "previous run"}


def run(agent: str, set_name: str, provider_config: Path | None, repeat: int | None, note: str,
        results: Path = RESULTS, language: str | None = None) -> int:
    suite = SUITES[agent]
    mode = "live" if provider_config else "scripted"
    agent_dir = results / agent
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    module = suite.set_modules.get(set_name, suite.module)
    argv = [sys.executable, "-m", module, "--evidence", "", *suite.sets[set_name]]
    if language:
        # One language of a set is its own comparison line: baselines and references key on `<set>.<language>`.
        argv += ["--language", language]
        set_name = f"{set_name}.{language}"
    run_id = f"{stamp}-{set_name}-{mode}"
    run_dir = agent_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    argv[4] = str(run_dir / "evidence")
    if provider_config:
        argv += ["--provider-config", str(provider_config.resolve()), *(() if module != suite.module else suite.live)]
    if repeat is not None:
        if not suite.repeat:
            raise SystemExit(f"{agent} has no --repeat option")
        argv += ["--repeat", str(repeat)]
    env = os.environ | {"PYTHONPATH": os.pathsep.join(filter(None, ["src", ".", os.environ.get("PYTHONPATH")]))}
    started = datetime.now(timezone.utc).isoformat()
    command = {"agent": agent, "set": set_name, "mode": mode, "argv": argv[1:], "note": note, "suite_note": suite.note,
               "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
               "started": started}
    (run_dir / "command.json").write_text(json.dumps(command, indent=2))
    exit_code = subprocess.run(argv, cwd=REPOSITORY, env=env, check=False).returncode
    command |= {"ended": datetime.now(timezone.utc).isoformat(), "exit_code": exit_code}
    (run_dir / "command.json").write_text(json.dumps(command, indent=2))
    summary = summarize(run_dir / "evidence")
    record = {"agent": agent, "run": run_id, "set": set_name, "mode": mode, "command": command, "summary": summary}
    (run_dir / "summary.json").write_text(json.dumps(record, indent=2))
    reference_id, reference = _reference(agent_dir, set_name, mode, run_id)
    (run_dir / "comparison.md").write_text(compare(record, reference, reference_id))
    with (agent_dir / "index.jsonl").open("a") as index:
        index.write(json.dumps({"run": run_id, "set": set_name, "mode": mode, "exit_code": exit_code,
                                "git_commit": command["git_commit"], "git_dirty": command["git_dirty"],
                                "prompt_version": summary["identity"].get("prompt_version"),
                                "config_version": summary["identity"].get("config_version"),
                                "clean_attempts": summary.get("clean_attempts"), "attempts": summary.get("attempts"),
                                "note": note}) + "\n")
    print(f"\n{run_dir.relative_to(REPOSITORY) if run_dir.is_relative_to(REPOSITORY) else run_dir}")
    print((run_dir / "comparison.md").read_text())
    return exit_code


def _v2_reference(agent_dir: Path, base_set: str, mode: str, run_id: str) -> tuple[str | None, dict | None]:
    """The promoted baseline for the base set and mode, else the latest earlier run of it; a language-narrowed run
    compares against that reference's language rollup, so no per-language baseline exists."""
    pointer = agent_dir / f"baseline-{base_set}-{mode}.json"
    baseline = json.loads(pointer.read_text())["run"] if pointer.exists() else None
    # the pointer's run may have been pruned from .runs/; the committed baseline still stands
    if baseline and (agent_dir / baseline / "summary.json").exists():
        return baseline, json.loads((agent_dir / baseline / "summary.json").read_text()) | {"reference_kind": "baseline"}
    committed = committed_baseline(agent_dir.name, base_set, mode)
    if committed is not None and committed.exists():
        record = json.loads(committed.read_text())
        return record["run"], record | {"reference_kind": "committed baseline"}
    index = agent_dir / "index.jsonl"
    earlier = [json.loads(line) for line in index.read_text().splitlines()] if index.exists() else []
    # whole-set runs only: a language-narrowed run's overall rollup covers one language, not the set
    earlier = [row for row in earlier if row["set"] == base_set and row["mode"] == mode and row["run"] != run_id
               and not row.get("language") and (agent_dir / row["run"] / "summary.json").exists()]
    if not earlier:
        return None, None
    previous = earlier[-1]["run"]
    return previous, json.loads((agent_dir / previous / "summary.json").read_text()) | {"reference_kind": "previous run"}


def run_v2(agent: str, suite: Suite, set_name: str, provider_config: Path | None, repeat: int | None, note: str,
           results: Path = RESULTS, language: str | None = None) -> int:
    """One v2 agent eval: the runner's attempts become summary.json, comparison.md and policy.json."""
    mode = "live" if provider_config else "scripted"
    agent_dir = results / agent
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = f"{set_name}.{language}" if language else set_name
    run_id = f"{stamp}-{label}-{mode}"
    run_dir = agent_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    argv = [sys.executable, "-m", suite.module, "--evidence", str(run_dir / "evidence"), *suite.sets[set_name]]
    argv += ["--language", language] if language else []
    argv += ["--provider-config", str(provider_config.resolve())] if provider_config else []
    argv += ["--repeat", str(repeat)] if repeat is not None else []
    env = os.environ | {"PYTHONPATH": os.pathsep.join(filter(None, ["src", ".", os.environ.get("PYTHONPATH")]))}
    command = {"agent": agent, "set": set_name, "language": language, "mode": mode, "argv": argv[1:], "note": note,
               "git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
               "started": datetime.now(timezone.utc).isoformat()}
    (run_dir / "command.json").write_text(json.dumps(command, indent=2))
    exit_code = subprocess.run(argv, cwd=REPOSITORY, env=env, check=False).returncode
    command |= {"ended": datetime.now(timezone.utc).isoformat(), "exit_code": exit_code}
    (run_dir / "command.json").write_text(json.dumps(command, indent=2))
    summary = agent_summary.summarize(run_dir / "evidence", agent=agent, set_name=set_name, language=language,
                                      mode=mode, run=run_id, command=command)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    policy = agent_summary.apply_policy(summary, agent_root(agent) / "release-policy.yaml")
    (run_dir / "policy.json").write_text(json.dumps(policy, indent=2))
    reference_id, reference = _v2_reference(agent_dir, set_name, mode, run_id)
    (run_dir / "comparison.md").write_text(agent_summary.compare(summary, reference, reference_id)
                                           + f"\nRelease policy (deferred, does not set the exit code): {policy['status']}\n")
    overall = (summary.get("rollups") or {}).get("all") or {}
    with (agent_dir / "index.jsonl").open("a") as index:
        index.write(json.dumps({"run": run_id, "set": set_name, "language": language, "mode": mode,
                                "exit_code": exit_code, "git_commit": command["git_commit"],
                                "git_dirty": command["git_dirty"],
                                "prompt_version": summary["identity"].get("prompt_version"),
                                "clean_attempts": overall.get("clean_attempts"), "attempts": overall.get("attempts"),
                                "policy": policy["status"], "note": note}) + "\n")
    print(f"\n{run_dir.relative_to(REPOSITORY) if run_dir.is_relative_to(REPOSITORY) else run_dir}")
    print((run_dir / "comparison.md").read_text())
    return exit_code


def promote(agent: str, run_id: str, results: Path = RESULTS) -> None:
    """A baseline is a measurement chosen by a person, never selected automatically."""
    record = json.loads((results / agent / run_id / "summary.json").read_text())
    if record.get("schema") == agent_summary.SCHEMA and record.get("language"):
        raise SystemExit("a language-narrowed run is not a baseline; promote a run of the whole set")
    pointer = results / agent / f"baseline-{record['set']}-{record['mode']}.json"
    pointer.write_text(json.dumps({"run": run_id, "promoted": datetime.now(timezone.utc).isoformat()}, indent=2))
    print(f"{pointer}: {run_id}")


def committed_baseline(agent: str, set_name: str, mode: str) -> Path | None:
    """Where a v2 agent's committed baseline for a set and mode lives (None for a non-v2 suite)."""
    if agent not in V2_AGENTS:
        return None
    return agent_root(agent) / "baselines" / f"{set_name}-{mode}.json"


def commit_baseline(agent: str, run_id: str, results: Path = RESULTS) -> Path:
    """Promote ``run_id`` and write its committed baseline: the summary without per-attempt rows (rollups by
    language and kind, identity, dispositions) and the policy status. Only a whole-set run from a clean checkout
    with a report qualifies; a person chooses the run, nothing selects one automatically."""
    run_dir = results / agent / run_id
    summary = json.loads((run_dir / "summary.json").read_text())
    identity = summary.get("identity") or {}
    if summary.get("language"):
        raise SystemExit("a language-narrowed run is not a baseline; commit a run of the whole set")
    if summary.get("mode") != "live":
        raise SystemExit(f"{run_id}: a {summary.get('mode')} run checks plumbing only; baselines come from live runs")
    if not ((summary.get("rollups") or {}).get("all") or {}).get("attempts"):
        raise SystemExit(f"{run_id}: no attempts were reported; nothing to commit")
    if not identity.get("git_commit") or identity.get("git_dirty") is not False:
        raise SystemExit(f"{run_id}: ran from an unknown or dirty checkout; a baseline needs a clean commit")
    policy = json.loads((run_dir / "policy.json").read_text()) if (run_dir / "policy.json").exists() else {}
    record = {key: value for key, value in summary.items() if key != "attempts"} | {
        "policy_status": policy.get("status"), "committed": datetime.now(timezone.utc).isoformat()}
    target = committed_baseline(agent, summary["set"], summary["mode"])
    if target is None:
        raise SystemExit(f"{agent}: committed baselines are for v2 agents")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n")
    promote(agent, run_id, results)
    print(f"{target.relative_to(REPOSITORY) if target.is_relative_to(REPOSITORY) else target}: commit this file")
    return target


def main(argv: list[str] | None = None) -> int:
    agents = sorted(SUITES) + sorted(V2_AGENTS) + sorted(MISSING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agent", choices=agents)
    parser.add_argument("--set", dest="set_name", help="Case set; defaults to the suite's first set")
    parser.add_argument("--provider-config", type=Path, help="Per-agent provider JSON (or legacy LocalModelConfig); omitted means scripted")
    parser.add_argument("--repeat", type=int)
    parser.add_argument("--language", help="Only this language's cases of the set (python, java, javascript, ruby, perl, common)")
    parser.add_argument("--note", default="", help="Free text recorded with the run, e.g. what changed")
    parser.add_argument("--promote", metavar="RUN", help="Make RUN the baseline for its set and mode instead of running")
    parser.add_argument("--commit-baseline", metavar="RUN",
                        help="v2: promote RUN and write its committed baseline file instead of running")
    parser.add_argument("--results", type=Path, default=RESULTS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.agent in MISSING:
        parser.error(f"{args.agent}: {MISSING[args.agent]}")
    for chosen in filter(None, (args.promote, args.commit_baseline)):
        if not re.fullmatch(r"[0-9TZ]+-[a-z0-9_-]+(\.[a-z]+)?-(scripted|live)", chosen):
            parser.error("RUN must be a run id from index.jsonl")
    if args.commit_baseline:
        if args.agent not in V2_AGENTS:
            parser.error("--commit-baseline is for v2 agents")
        commit_baseline(args.agent, args.commit_baseline, args.results)
        return 0
    if args.promote:
        promote(args.agent, args.promote, args.results)
        return 0
    suite = SUITES.get(args.agent) or v2_suite(args.agent)
    if suite is None:
        parser.error(f"{args.agent} has no evals/evaluate.py yet under {AGENTS_PACKAGE}")
    if not suite.sets:
        parser.error(f"{args.agent} has no frozen set under its evals/sets/")
    set_name = args.set_name or next(iter(suite.sets))
    if set_name not in suite.sets:
        parser.error(f"{args.agent} sets: {', '.join(suite.sets)}")
    if args.language and not narrows_by_language(suite, set_name):
        parser.error(f"{args.agent} set {set_name} is not split by language")
    if args.agent in V2_AGENTS:
        return run_v2(args.agent, suite, set_name, args.provider_config, args.repeat, args.note, args.results,
                      args.language)
    return run(args.agent, set_name, args.provider_config, args.repeat, args.note, args.results, args.language)


if __name__ == "__main__":
    sys.exit(main())
