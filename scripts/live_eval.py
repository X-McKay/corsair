#!/usr/bin/env python3
"""Run one live evaluation and keep a comparable, sanitised record under `.runs/live/`.

Developer tooling for the improvement loop's rig step. It refuses before any model call
unless `.state/settings.json` names a model connector and this environment holds the
provider variables that connector needs (it reads variable names, never prints values).
It then runs the existing isolated (`corsair.evaluation.agents`) or composed
(`corsair eval`) evaluator, writes `identity.json` beside the raw report, runs
`corsair compare` against an optional baseline report and renders a README draft for a
human to review before anything is copied under `evals/baselines/candidates/`.

It scores nothing and decides nothing: the report, comparison and gate ledger come from
the evaluator and `corsair compare`; this script only gathers identities and renders text.
`--dry-run` validates the same inputs and prints the plan without calling a model,
Temporal or Docker beyond a read-only image inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SETTINGS = Path(".state/settings.json")
LIVE_ROOT = Path(".runs/live")
CONNECTORS = frozenset({"gemini", "litellm"})
ROLES = ("producer", "auditor")
DATASET_SCHEMAS = {"agent": "corsair.agent-dataset/1", "chain": "corsair.dataset/1"}
# Provider variables, as alternatives: any one group, with every name in it non-empty.
GEMINI_ENV = (
    ("GOOGLE_API_KEY",),
    ("GEMINI_API_KEY",),
    ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT"),
)
# LiteLLM routes by model prefix. `hosted_vllm/` needs `models.api_base` instead of a key.
LITELLM_ROUTE_ENV: dict[str, tuple[tuple[str, ...], ...]] = {
    "hosted_vllm/": (),
    "openai/": (("OPENAI_API_KEY",),),
    "anthropic/": (("ANTHROPIC_API_KEY",),),
    "gemini/": (("GEMINI_API_KEY",), ("GOOGLE_API_KEY",)),
}
# Canonical label values (corsair.contracts.Verdict); a unit test pins them to the enum.
DECISIVE_LABELS = (
    "EXPLOIT_DEMONSTRATED",
    "COMPONENT_EXPLOIT_DEMONSTRATED",
    "EXPLOIT_NOT_DEMONSTRATED",
)
LEDGER_STAGES = ("producer", "evidence", "audit", "kernel")
COMPARED_FIELDS = (
    "attempts",
    "passed",
    "pass_rate",
    "operational_failures",
    "llm_calls",
    "tool_calls",
    "input_tokens",
    "output_tokens",
)


class LiveError(RuntimeError):
    """An operator-facing refusal; printed without a traceback and never with a secret."""


@dataclass(frozen=True)
class Plan:
    """Everything one run needs, validated before any command executes."""

    kind: str
    role: str | None
    root: Path
    dataset: Path
    dataset_digest: str
    baseline: Path | None
    repeats: int
    concurrency: int
    stamp: str
    settings: dict[str, Any]
    provider_env: list[str]
    allow_dataset_mismatch: bool
    run_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        label = f"agent-{self.role}" if self.kind == "agent" else "chain"
        name = f"{self.stamp}-{label}-{self.dataset.stem}"
        object.__setattr__(self, "run_dir", self.root / LIVE_ROOT / name)

    @property
    def run_id(self) -> str:
        """The composed batch identity; a valid Temporal root identity of at most 60 chars."""
        return f"live-{self.stamp.lower()}-{self.dataset.stem}"[:60].rstrip("-_.")

    @property
    def report(self) -> Path:
        return self.run_dir / "report.json"

    def evaluate_command(self) -> list[str]:
        settings = str(self.root / SETTINGS)
        output = ["--repeats", str(self.repeats), "--output", str(self.report)]
        if self.kind == "agent":
            assert self.role is not None
            module = [sys.executable, "-m", "corsair.evaluation.agents", self.role]
            return [*module, str(self.dataset), "--settings", settings, *output]
        cli = [sys.executable, "-m", "corsair.entrypoints.cli", "--format", "json", "eval"]
        batch = ["--concurrency", str(self.concurrency), "--run-id", self.run_id]
        return [*cli, str(self.dataset), "--settings", settings, *batch, *output]

    def doctor_command(self) -> list[str]:
        cli = [sys.executable, "-m", "corsair.entrypoints.cli", "--format", "json", "doctor"]
        return [*cli, "--settings", str(self.root / SETTINGS)]

    def compare_command(self) -> list[str] | None:
        if self.baseline is None:
            return None
        cli = [sys.executable, "-m", "corsair.entrypoints.cli", "--format", "json", "compare"]
        command = [*cli, str(self.baseline), str(self.report)]
        return [*command, "--allow-dataset-mismatch"] if self.allow_dataset_mismatch else command


def canonical_digest(value: object) -> str:
    """The digest corsair.contracts.digest gives a parsed JSON value."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _read_json(path: Path, what: str) -> Any:
    if not path.is_file():
        raise LiveError(f"{what} {path} does not exist")
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise LiveError(f"{what} {path} is not readable JSON ({type(error).__name__})") from None


def read_settings(root: Path) -> dict[str, Any]:
    """The settings file must exist and name a connector explicitly, not by default."""
    path = root / SETTINGS
    if not path.exists():
        raise LiveError(f"{SETTINGS} is missing; run `just settings-init` and configure models")
    settings = _read_json(path, "settings file")
    models = settings.get("models") if isinstance(settings, dict) else None
    if not isinstance(models, dict) or models.get("connector") not in CONNECTORS:
        raise LiveError(
            f"{SETTINGS} must name models.connector as one of {sorted(CONNECTORS)}; "
            "live evaluations never fall back to a default provider"
        )
    return settings


def _present(name: str, environ: Mapping[str, str]) -> bool:
    value = environ.get(name, "")
    if name == "GOOGLE_GENAI_USE_VERTEXAI":
        return value.strip().lower() in {"1", "true"}
    return bool(value.strip())


def provider_environment(
    settings: dict[str, Any],
    roles: Sequence[str],
    environ: Mapping[str, str],
    required: Sequence[str] = (),
) -> list[str]:
    """Return the provider variable names in use, or refuse naming only what is missing."""
    models = settings["models"]
    groups: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    for role in roles:
        model = models.get(role)
        if not isinstance(model, str) or not model:
            raise LiveError(f"{SETTINGS} must name models.{role}")
        if models["connector"] == "gemini":
            groups.append(("gemini", GEMINI_ENV))
            continue
        route = next((prefix for prefix in LITELLM_ROUTE_ENV if model.startswith(prefix)), None)
        if route is None and not required:
            raise LiveError(
                f"models.{role} uses a LiteLLM route this script does not know; "
                "name the provider variables it needs with --require-env NAME"
            )
        if route == "hosted_vllm/" and not models.get("api_base"):
            raise LiveError(f"models.{role} uses hosted_vllm/, which needs models.api_base")
        if route is not None and LITELLM_ROUTE_ENV[route]:
            groups.append((route, LITELLM_ROUTE_ENV[route]))
    groups += [(name, ((name,),)) for name in required]
    used: set[str] = set()
    for provider, alternatives in groups:
        satisfied = next(
            (group for group in alternatives if all(_present(n, environ) for n in group)), None
        )
        if satisfied is None:
            wanted = " or ".join("+".join(group) for group in alternatives)
            raise LiveError(f"provider environment for {provider} is missing: set {wanted}")
        used.update(satisfied)
    return sorted(used)


def read_dataset(path: Path, kind: str) -> str:
    """Check the dataset shape for this kind and return the digest its report will declare."""
    dataset = _read_json(path, "dataset")
    schema = (
        dataset.get("schema_version", DATASET_SCHEMAS["chain"])
        if isinstance(dataset, dict)
        else None
    )
    if schema != DATASET_SCHEMAS[kind]:
        expected = DATASET_SCHEMAS[kind]
        raise LiveError(f"dataset {path} is {schema!r}, not a {kind} dataset ({expected})")
    entries = dataset.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise LiveError(f"dataset {path} needs 1..64 entries")
    if kind == "chain":  # `corsair eval` digests the Dataset model, defaults included.
        dataset.setdefault("schema_version", DATASET_SCHEMAS["chain"])
    return canonical_digest(dataset)


def read_baseline(
    path: Path, kind: str, role: str | None, dataset_digest: str, allow_mismatch: bool
) -> None:
    """Refuse a baseline that `corsair compare` would refuse, before the model is spent."""
    report = _read_json(path, "baseline report")
    if not isinstance(report, dict) or not isinstance(report.get("rows"), list):
        raise LiveError(f"baseline {path} is not an evaluation report with rows")
    agents = {row.get("agent") for row in report["rows"] if isinstance(row, dict)} - {None}
    if kind == "agent" and agents and agents != {role}:
        raise LiveError(f"baseline {path} reports {sorted(agents)}, not the {role}")
    if kind == "chain" and agents:
        raise LiveError(f"baseline {path} is an isolated agent report, not a composed one")
    declared = report.get("dataset_digest")
    if declared != dataset_digest and not allow_mismatch:
        raise LiveError(
            f"baseline {path} covers dataset digest {declared}, this dataset is "
            f"{dataset_digest}; compare would refuse it (pass --allow-dataset-mismatch "
            "to record a mismatched comparison anyway)"
        )


def make_plan(args: argparse.Namespace, root: Path, environ: Mapping[str, str]) -> Plan:
    """Validate settings, provider environment, dataset and baseline; run nothing."""
    settings = read_settings(root)
    roles = [args.role] if args.kind == "agent" else list(ROLES)
    provider_env = provider_environment(settings, roles, environ, args.require_env)
    dataset = Path(args.dataset).resolve()
    dataset_digest = read_dataset(dataset, args.kind)
    baseline = Path(args.baseline).resolve() if args.baseline else None
    if baseline is not None:
        role = args.role if args.kind == "agent" else None
        read_baseline(baseline, args.kind, role, dataset_digest, args.allow_dataset_mismatch)
    plan = Plan(
        kind=args.kind,
        role=args.role if args.kind == "agent" else None,
        root=root,
        dataset=dataset,
        dataset_digest=dataset_digest,
        baseline=baseline,
        repeats=args.repeats,
        concurrency=getattr(args, "concurrency", 1),
        stamp=args.stamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        settings=settings,
        provider_env=provider_env,
        allow_dataset_mismatch=args.allow_dataset_mismatch,
    )
    if plan.run_dir.exists():
        raise LiveError(f"{plan.run_dir} already exists; records are never overwritten")
    return plan


def _display(path: Path | None, root: Path) -> str | None:
    """A repository-relative path, or only the file name for a path outside it."""
    if path is None:
        return None
    return str(path.relative_to(root)) if path.is_relative_to(root) else path.name


def _command_output(command: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def code_identity(root: Path) -> dict[str, Any]:
    """Commit, tree and dirty flag; unknown stays None, never a guess."""
    status = _command_output(["git", "status", "--porcelain"], root)
    return {
        "commit": _command_output(["git", "rev-parse", "HEAD"], root),
        "tree": _command_output(["git", "rev-parse", "HEAD^{tree}"], root),
        "dirty": None if status is None else bool(status),
    }


def image_identity(root: Path, image: str) -> dict[str, Any]:
    inspect = ["docker", "image", "inspect", "--format", "{{.Id}}", image]
    return {"name": image, "id": _command_output(inspect, root)}


def _row_values(rows: list[dict[str, Any]], name: str) -> list[str]:
    return sorted({value for row in rows if isinstance(value := row.get(name), str)})


def build_identity(
    plan: Plan, report: dict[str, Any] | None, code: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The sanitised identity: digests, names and flags, never endpoints or secrets.

    `code` is the tree identity taken before the run; it is read now when not given."""
    rows = [row for row in (report or {}).get("rows", []) if isinstance(row, dict)]
    models = plan.settings["models"]
    resources: dict[str, list[str]] = {}
    for row in rows:
        agent, value = row.get("agent"), row.get("agent_resources_digest")
        if isinstance(agent, str) and isinstance(value, str):
            resources.setdefault(agent, [])
            if value not in resources[agent]:
                resources[agent].append(value)
    settings_bytes = (plan.root / SETTINGS).read_bytes()
    return {
        "schema_version": "corsair.live-identity/1",
        "kind": plan.kind,
        "role": plan.role,
        "stamp": plan.stamp,
        "run_id": plan.run_id if plan.kind == "chain" else None,
        "code": code if code is not None else code_identity(plan.root),
        "settings": {
            "path": str(SETTINGS),
            "sha256": hashlib.sha256(settings_bytes).hexdigest(),
            "config_digests": _row_values(rows, "config_digest"),
        },
        "models": {
            "connector": models["connector"],
            "producer": models.get("producer"),
            "auditor": models.get("auditor"),
            "api_base_configured": bool(models.get("api_base")),
            "request_timeout_seconds": models.get("request_timeout_seconds"),
            "extra_body_keys": sorted(models.get("extra_body") or {}),
        },
        "provider_env_names": plan.provider_env,
        "image": image_identity(plan.root, str(plan.settings.get("image", "corsair-python:0.1"))),
        "runtime": plan.settings.get("runtime", "runc"),
        "dataset": {
            "path": _display(plan.dataset, plan.root),
            "digest": plan.dataset_digest,
            "report_digest": (report or {}).get("dataset_digest"),
        },
        "agent_resources_digests": resources,
        "cohorts": _row_values(rows, "cohort"),
        "repeats": plan.repeats,
        "concurrency": plan.concurrency if plan.kind == "chain" else None,
        "baseline": _display(plan.baseline, plan.root),
    }


def _cell(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value).replace("|", "\\|")


def _label(row: dict[str, Any]) -> str:
    for name in ("verdict", "disposition", "match_kind"):
        if isinstance(row.get(name), str):
            return row[name]
    return str(row.get("status", "unknown"))


def unrun_gates(kind: str, role: str | None, report: dict[str, Any]) -> list[str]:
    """What this record does not exercise, so a reader cannot mistake it for more."""
    rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
    gates: list[str] = []
    if kind == "agent":
        other = "auditor" if role == "producer" else "producer"
        gates += [
            "Docker target execution: an isolated agent evaluation runs no target code.",
            "Temporal durability, the kernel and the verdict labels: not exercised.",
            f"The {other}: not evaluated in this record.",
        ]
    else:
        verdicts = {row.get("verdict") for row in rows}
        gates += [
            f"No row reached `{label}`." for label in DECISIVE_LABELS if label not in verdicts
        ]
        ledgers = [entry for row in rows for entry in row.get("gate_ledger") or []]
        if not ledgers:
            gates.append("The report records no gate ledger; stage reach is unknown.")
        else:
            stages = {entry.get("stage") for entry in ledgers}
            gates += [
                f"No round reached the `{stage}` stage."
                for stage in LEDGER_STAGES
                if stage not in stages
            ]
            if not any((entry.get("session") or 0) >= 2 for entry in ledgers):
                gates.append("No second independent session started.")
    unavailable = report.get("summary", {}).get("unavailable_results")
    if unavailable:
        gates.append(f"{unavailable} rows are unavailable: their results were not scored.")
    gates.append(
        "Not run by this recipe: `just check`, `just -- test -q -W error`, `just test-docker`, "
        "`just test-temporal`. Record each as passed, failed, blocked or unrun."
    )
    return gates


def _case_rows(rows: list[dict[str, Any]]) -> list[str]:
    cases: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        cases.setdefault(str(row.get("case_id", "unidentified")), []).append(row)
    lines = []
    for case_id, attempts in cases.items():
        passed = sum(row.get("status") == "pass" for row in attempts)
        labels = Counter(_label(row) for row in attempts)
        shown = ", ".join(f"`{label}` {count}" for label, count in sorted(labels.items()))
        lines.append(f"| `{case_id}` | {len(attempts)} | {passed} | {shown} |")
    return lines


def _comparison_lines(comparison: dict[str, Any] | None, baseline: str | None) -> list[str]:
    if baseline is None:
        return ["No baseline was given, so no comparison was made."]
    if comparison is None:
        return [f"Comparing against `{baseline}` failed; see the recipe output."]
    lines = [
        f"Baseline `{baseline}`: dataset match `{comparison.get('dataset_match')}`, "
        f"regression `{comparison.get('regression')}`, counts `{comparison.get('counts')}`.",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    delta = comparison.get("summary_delta", {})
    for name in COMPARED_FIELDS:
        item = delta.get(name, {})
        values = (item.get("baseline"), item.get("candidate"), item.get("delta"))
        lines.append(f"| {name} | " + " | ".join(_cell(value) for value in values) + " |")
    for regression in comparison.get("regressions", []):
        lines.append(
            f"- Regression: `{regression.get('case_id')}` attempt {regression.get('repeat')}: "
            f"{regression.get('reason')}"
        )
    return lines


def render_readme(
    identity: dict[str, Any], report: dict[str, Any], comparison: dict[str, Any] | None
) -> str:
    """A candidate README draft; every TODO is for the human reviewer, not this script."""
    rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
    summary = report.get("summary", {})
    code, models, image = identity["code"], identity["models"], identity["image"]
    dirty = {True: "dirty", False: "clean", None: "unknown"}[code["dirty"]]
    title = f"agent {identity['role']}" if identity["kind"] == "agent" else "chain"
    stops = summary.get("failure_stops") or {}
    resources = identity["agent_resources_digests"]
    lines = [
        f"# Live candidate diagnostics: {title}, {identity['stamp']}",
        "",
        "DRAFT generated by `scripts/live_eval.py`. A human reviews every line, resolves each "
        "TODO and removes this paragraph before copying the record under "
        "`evals/baselines/candidates/`.",
        "",
        "AI-run candidate diagnostics, pending human review. These are not promoted baselines "
        "and make no accuracy, false-positive, clearance or production claim (see the "
        "[candidate policy](../README.md)).",
        "",
        "## Identity",
        "",
        "| Item | Value |",
        "| --- | --- |",
        f"| Code | commit `{_cell(code['commit'])}`, tree `{_cell(code['tree'])}`, {dirty} |",
        f"| Settings | file sha256 `{identity['settings']['sha256']}`; config digests "
        + (", ".join(f"`{d}`" for d in identity["settings"]["config_digests"]) or "unknown")
        + " |",
        f"| Model | connector `{models['connector']}`, producer `{_cell(models['producer'])}`, "
        f"auditor `{_cell(models['auditor'])}`, endpoint "
        f"{'configured (not recorded)' if models['api_base_configured'] else 'provider default'}, "
        f"timeout {_cell(models['request_timeout_seconds'])} s |",
        f"| Image | `{image['name']}`, `{_cell(image['id'])}` |",
        f"| Runtime | Docker `{identity['runtime']}`; TODO: rig, Temporal server, workers |",
        f"| Dataset | `{_cell(identity['dataset']['path'])}`, digest "
        f"`{_cell(identity['dataset']['report_digest'])}` |",
        "| Agent resources | "
        + (
            "; ".join(
                f"{agent} " + ", ".join(f"`{d}`" for d in ds) for agent, ds in resources.items()
            )
            or "not recorded by this report"
        )
        + " |",
        f"| Repeats | {identity['repeats']} per case"
        + (f", concurrency {identity['concurrency']}" if identity["concurrency"] else "")
        + " |",
        "| Model sharing | TODO: whether anything else used the model during the run |",
        "",
        "## Results",
        "",
        "| Report | Attempts | Pass | Notes |",
        "| --- | ---: | ---: | --- |",
        f"| `report.json` | {_cell(summary.get('attempts'))} | {_cell(summary.get('passed'))} | "
        f"operational failures {_cell(summary.get('operational_failures'))}, unavailable "
        f"{_cell(summary.get('unavailable_results'))}; TODO: reviewer notes |",
        "",
        "| Case | Attempts | Pass | Labels |",
        "| --- | ---: | ---: | --- |",
        *_case_rows(rows),
        "",
        f"Usage: LLM calls {_cell(summary.get('llm_calls'))}, tool calls "
        f"{_cell(summary.get('tool_calls'))}, input tokens {_cell(summary.get('input_tokens'))}, "
        f"output tokens {_cell(summary.get('output_tokens'))}, cost "
        f"{_cell(summary.get('cost_usd'))}.",
    ]
    if stops:
        shown = ", ".join(f"`{name}` {count}" for name, count in sorted(stops.items()))
        lines += ["", f"Failure stops (final gate-ledger entry of each failed row): {shown}."]
    lines += ["", "## Comparison", "", *_comparison_lines(comparison, identity["baseline"])]
    lines += ["", "## Not exercised", ""]
    lines += [f"- {gate}" for gate in unrun_gates(identity["kind"], identity["role"], report)]
    lines += ["", "## Excluded runs", "", "TODO: list void or excluded runs and why, or say none."]
    return "\n".join(lines) + "\n"


def describe(plan: Plan) -> list[str]:
    """The plan as printable lines: names and paths only, no values from the environment."""
    models = plan.settings["models"]
    lines = [
        f"kind: {plan.kind}" + (f" ({plan.role})" if plan.role else ""),
        f"connector: {models['connector']}; models: producer={models.get('producer')} "
        f"auditor={models.get('auditor')}",
        "provider environment present: " + (", ".join(plan.provider_env) or "none required"),
        f"dataset: {_display(plan.dataset, plan.root)} digest {plan.dataset_digest}",
        f"baseline: {_display(plan.baseline, plan.root) or 'none'}",
        f"record directory: {_display(plan.run_dir, plan.root)}",
    ]
    steps = [plan.doctor_command()] if plan.kind == "chain" else []
    steps.append(plan.evaluate_command())
    if (compare := plan.compare_command()) is not None:
        steps.append(compare)
    lines += [f"run: {shlex.join(step)}" for step in steps]
    records = (
        "identity.json, comparison.json, README.md" if plan.baseline else "identity.json, README.md"
    )
    lines.append(f"write: report.json, {records}")
    return lines


def _run_json(command: list[str], cwd: Path) -> tuple[int, Any]:
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, text=True, check=False)
    try:
        return result.returncode, json.loads(result.stdout)
    except ValueError:
        return result.returncode, None


def execute(plan: Plan) -> int:
    """Run the evaluator, then write identity, comparison and README; 1 means regression."""
    if plan.kind == "chain":
        code, doctor = _run_json(plan.doctor_command(), plan.root)
        if code != 0 or not isinstance(doctor, dict) or not doctor.get("ready"):
            raise LiveError("corsair doctor is not ready; start Temporal and a worker first")
    code_before = code_identity(plan.root)  # the tree the evaluator actually ran
    plan.run_dir.mkdir(parents=True)
    code = subprocess.run(plan.evaluate_command(), cwd=plan.root, check=False).returncode
    if code not in {0, 1} or not plan.report.is_file():
        raise LiveError(f"the evaluator exited {code} without a report in {plan.run_dir}")
    report = json.loads(plan.report.read_bytes())
    identity = build_identity(plan, report, code_before)
    (plan.run_dir / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    comparison, regression = None, False
    if (compare := plan.compare_command()) is not None:
        code, comparison = _run_json(compare, plan.root)
        if code in {0, 1} and isinstance(comparison, dict):
            (plan.run_dir / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
            regression = code == 1
        else:
            comparison = None
            print(f"corsair compare exited {code}; no comparison recorded", file=sys.stderr)
    (plan.run_dir / "README.md").write_text(render_readme(identity, report, comparison))
    print(f"Record: {_display(plan.run_dir, plan.root)} (report.json, identity.json, README.md)")
    print("Review README.md before copying anything under evals/baselines/candidates/.")
    return 1 if regression else 0


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    kinds = parser.add_subparsers(dest="kind", required=True)
    agent = kinds.add_parser("agent", help="isolated producer or auditor evaluation")
    agent.add_argument("role", choices=ROLES)
    chain = kinds.add_parser("chain", help="composed Temporal evaluation; needs a worker")
    chain.add_argument("--concurrency", type=int, choices=range(1, 9), default=1)
    for command in (agent, chain):
        command.add_argument("dataset")
        command.add_argument("baseline", nargs="?", help="saved report to compare against")
        command.add_argument("--repeats", type=int, choices=range(1, 9), default=3)
        command.add_argument("--dry-run", action="store_true", help="validate and print the plan")
        command.add_argument("--allow-dataset-mismatch", action="store_true")
        command.add_argument("--require-env", action="append", default=[], metavar="NAME")
        command.add_argument("--stamp", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = parse_arguments(argv)
    try:
        plan = make_plan(args, args.root.resolve(), os.environ if environ is None else environ)
        print("\n".join(describe(plan)))
        if args.dry_run:
            print("dry run: no model, Temporal or evaluator command was started")
            return 0
        return execute(plan)
    except LiveError as error:
        print(f"live-{args.kind}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
