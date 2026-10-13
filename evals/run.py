"""One command per agent: run its eval suite on the host and file the result for comparison (SPEC-0044).

    make eval AGENT=planning [SET=heldout3] [PROVIDER_CONFIG=<LocalModelConfig.json>] [REPEAT=3] [NOTE=...]
    make eval-baseline AGENT=planning RUN=<run id>

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

REPOSITORY = Path(__file__).resolve().parents[1]
RESULTS = REPOSITORY / ".runs" / "evals"
# Top-level suite identity; the chain nests per-stage prompt/config/skill under "versions" and names its live stages.
IDENTITY = ("prompt_version", "config_version", "skill_sha256", "versions", "live_stages", "composition", "model",
            "dataset", "dataset_sha256", "mode", "runner", "execution", "budget")


@dataclass(frozen=True)
class Suite:
    module: str
    sets: dict[str, tuple[str, ...]]
    repeat: bool = True
    live: tuple[str, ...] = ()
    note: str = ""


SUITES: dict[str, Suite] = {
    "environment": Suite("evals.environment.evaluate", {"development": ()}, note="synthetic observations; setup commands never execute on the host"),
    "identification": Suite("evals.issue_identification.evaluate", {"development": ()}, repeat=False),
    "planning": Suite("evals.test_planning.evaluate", {
        "development": ("--cases", "development"), "heldout": ("--cases", "heldout"),
        "heldout2": ("--cases", "heldout2"), "heldout3": ("--cases", "heldout3")}),
    "authoring": Suite("evals.test_authoring.evaluate", {"development": ()},
                       note="runs answered by injected observations or the static host runner; tests are not executed"),
    "assessment": Suite("evals.evidence_assessment.evaluate", {
        "development": ("--split", "development"), "held_out": ("--split", "held_out")}),
    "chain": Suite("evals.fixture_chain.evaluate", {"fixture": ()},
                   live=("--live", "identification,planning,assessment"),
                   note="live authoring needs the sandbox; authoring stays scripted on the host"),
}
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
    return {"identity": identity,
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
        results: Path = RESULTS) -> int:
    suite = SUITES[agent]
    mode = "live" if provider_config else "scripted"
    agent_dir = results / agent
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{set_name}-{mode}"
    run_dir = agent_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    argv = [sys.executable, "-m", suite.module, "--evidence", str(run_dir / "evidence"), *suite.sets[set_name]]
    if provider_config:
        argv += ["--provider-config", str(provider_config.resolve()), *suite.live]
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


def promote(agent: str, run_id: str, results: Path = RESULTS) -> None:
    """A baseline is a measurement chosen by a person, never selected automatically."""
    record = json.loads((results / agent / run_id / "summary.json").read_text())
    pointer = results / agent / f"baseline-{record['set']}-{record['mode']}.json"
    pointer.write_text(json.dumps({"run": run_id, "promoted": datetime.now(timezone.utc).isoformat()}, indent=2))
    print(f"{pointer}: {run_id}")


def main(argv: list[str] | None = None) -> int:
    agents = sorted(SUITES) + sorted(MISSING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agent", choices=agents)
    parser.add_argument("--set", dest="set_name", help="Case set; defaults to the suite's first set")
    parser.add_argument("--provider-config", type=Path, help="Explicit LocalModelConfig JSON; omitted means scripted")
    parser.add_argument("--repeat", type=int)
    parser.add_argument("--note", default="", help="Free text recorded with the run, e.g. what changed")
    parser.add_argument("--promote", metavar="RUN", help="Make RUN the baseline for its set and mode instead of running")
    parser.add_argument("--results", type=Path, default=RESULTS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.agent in MISSING:
        parser.error(f"{args.agent}: {MISSING[args.agent]}")
    if args.promote:
        if not re.fullmatch(r"[0-9TZ]+-[a-z0-9_]+-(scripted|live)", args.promote):
            parser.error("RUN must be a run id from index.jsonl")
        promote(args.agent, args.promote, args.results)
        return 0
    suite = SUITES[args.agent]
    set_name = args.set_name or next(iter(suite.sets))
    if set_name not in suite.sets:
        parser.error(f"{args.agent} sets: {', '.join(suite.sets)}")
    return run(args.agent, set_name, args.provider_config, args.repeat, args.note, args.results)


if __name__ == "__main__":
    sys.exit(main())
