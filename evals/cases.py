"""Eval cases as one directory each, grouped by language and set, with frozen set manifests (PLAN-0098).

    evals/<suite>/<language>/<set>/<case id>/
      input.json        exactly what the suite's task receives (the agent's input)
      oracle.json       evaluator-only expectations and scripted replay; never reaches the agent
      case.json         language, framework, family, kind, behaviour probed, provenance
    evals/<suite>/sets/<set>.json
      {"held_out": false, "cases": {"<language>/<case id>": "<sha256>", ...}}

A v2 agent keeps the same layout in its own package, ``src/corsair/agents/<agent>/evals/`` (``agent_root``),
beside its ``release-policy.yaml``; every function here takes either a suite name under evals/ or that root path.
v2 cases also name the eval types they measure in ``case.json`` ``dimensions`` (``DIMENSIONS``).

`<suite>` is the agent's eval package (evals/run.py maps `make eval AGENT=` names onto it); end-to-end cases use
evals/e2e/ the same way. `<language>` is python, java, javascript, ruby, perl, or common for a case with no
language (no source at all, injection only). A case hash is the SHA-256 of the canonical JSON of its three files,
so a set's identity (``set_digest``) changes only when a case it lists changes, not when cases are added beside it.
A held-out set's manifest says so; its case ids must not be named under docs/development
(tests/configuration/test_evaluation_layout.py). ``case.json`` is metadata for people and the inventory; suites
never pass it to an agent.

    PYTHONPATH=src:. .venv/bin/python -m evals.cases <suite> <set>             # check against the manifest
    PYTHONPATH=src:. .venv/bin/python -m evals.cases <suite> <set> --freeze    # rewrite the manifest
"""

from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

EVALS = Path(__file__).resolve().parent
# v2 agents keep their evals in their own package: <agent package>/evals/ (same layout, rooted there). This is the
# one place that names the package; it changes once if the v2 tree moves.
AGENTS_PACKAGE = "corsair.agents"
AGENTS = ("grounding", "builder", "investigator", "control_prober", "exploit_prober", "reviewer")
# The whole chain is scored like an agent (`make eval AGENT=chain`) over the end-to-end cases in evals/e2e/.
CHAIN = "chain"
# A v2 case's case.json `category`: what kind of evidence the case gives (infosec-harness style).
CATEGORIES = ("smoke", "capability", "regression", "adversarial", "failure-mode")
# Eval types a v2 case may name in case.json `dimensions` (efficiency is measured on every attempt, never pass/fail).
DIMENSIONS = ("correctness", "contract", "grounding", "trajectory", "robustness", "safety")
CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
LANGUAGES = ("python", "java", "javascript", "ruby", "perl", "common")
CASE_FIELDS = {"language", "framework", "family", "probes", "kind", "provenance"}
PROVENANCE_FIELDS = {"source", "license"}


@dataclass(frozen=True)
class EvalCase:
    name: str
    language: str
    input: Any
    oracle: Any
    case: dict

    @property
    def key(self) -> str:
        return f"{self.language}/{self.name}"


def agent_root(agent: str) -> Path:
    """A v2 agent's eval root, resolved through its package; an agent without an evals/ directory is refused.
    The chain's root is evals/e2e/."""
    if agent == CHAIN:
        return EVALS / "e2e"
    if agent not in AGENTS:
        raise ValueError(f"unknown v2 agent {agent!r}")
    # Search locations in import order: a namespace package can span several (an editable install plus a
    # checkout on PYTHONPATH), and the first one wins exactly as it does for imports.
    spec = importlib.util.find_spec(f"{AGENTS_PACKAGE}.{agent}")
    for location in (spec.submodule_search_locations or ()) if spec else ():
        root = Path(location) / "evals"
        if root.is_dir():
            return root
    raise ValueError(f"{agent} has no evals/ directory under {AGENTS_PACKAGE}")


def eval_root(suite: str | Path) -> Path:
    """A suite name under evals/, or an eval root path (a v2 agent's evals/ directory)."""
    return suite if isinstance(suite, Path) else EVALS / suite


def _read(directory: Path) -> EvalCase:
    loaded = {part: json.loads((directory / f"{part}.json").read_text()) for part in ("input", "oracle", "case")}
    return EvalCase(directory.name, directory.parent.parent.name, loaded["input"], loaded["oracle"], loaded["case"])


def case_hash(case: EvalCase) -> str:
    return sha256(json.dumps({"input": case.input, "oracle": case.oracle, "case": case.case},
                             sort_keys=True).encode()).hexdigest()


def check_case(case: EvalCase) -> None:
    if not CASE_ID.fullmatch(case.name):
        raise ValueError(f"case id {case.name!r} is not a plain identifier")
    meta = case.case
    missing = CASE_FIELDS - set(meta)
    if missing:
        raise ValueError(f"{case.key}: case.json lacks {sorted(missing)}")
    if meta["language"] not in LANGUAGES or meta["language"] != case.language:
        raise ValueError(f"{case.key}: case.json language {meta['language']!r} does not match its directory")
    if not PROVENANCE_FIELDS <= set(meta["provenance"]):
        raise ValueError(f"{case.key}: provenance needs {sorted(PROVENANCE_FIELDS)}")
    if "category" in meta and meta["category"] not in CATEGORIES:
        raise ValueError(f"{case.key}: category must be one of {CATEGORIES}")
    if "dimensions" in meta and (not meta["dimensions"] or not set(meta["dimensions"]) <= set(DIMENSIONS)):
        raise ValueError(f"{case.key}: dimensions must be a non-empty subset of {DIMENSIONS}")


def manifest(suite: str | Path, name: str) -> dict:
    return json.loads((eval_root(suite) / "sets" / f"{name}.json").read_text())


def set_names(suite: str | Path) -> list[str]:
    directory = eval_root(suite) / "sets"
    return sorted(path.stem for path in directory.glob("*.json")) if directory.is_dir() else []


def load_set(suite: str | Path, name: str, language: str | None = None) -> list[EvalCase]:
    """The set's cases in manifest order, optionally one language; refused when a case differs from its hash."""
    frozen = manifest(suite, name)
    cases = []
    for key, digest in frozen["cases"].items():
        case_language, case_id = key.split("/", 1)
        if language is not None and case_language != language:
            continue
        case = _read(eval_root(suite) / case_language / name / case_id)
        check_case(case)
        if case_hash(case) != digest:
            raise ValueError(f"{suite} case {key} differs from the frozen {name} manifest")
        cases.append(case)
    if language is not None and not cases:
        raise ValueError(f"{suite} set {name} has no {language} case")
    return cases


def set_digest(suite: str | Path, name: str) -> str:
    return sha256(json.dumps(manifest(suite, name), sort_keys=True).encode()).hexdigest()


def case_directories(suite: str | Path, name: str) -> list[Path]:
    return sorted(path for language in LANGUAGES for path in (eval_root(suite) / language / name).glob("*")
                  if path.is_dir())


def freeze(suite: str | Path, name: str, *, held_out: bool | None = None, order: list[str] | None = None) -> dict:
    """Rewrite a set manifest from its case directories; ``order`` (case keys) keeps a curated order."""
    path = eval_root(suite) / "sets" / f"{name}.json"
    if held_out is None:
        held_out = json.loads(path.read_text())["held_out"] if path.exists() else False
    cases = {}
    for directory in case_directories(suite, name):
        case = _read(directory)
        check_case(case)
        cases[case.key] = case_hash(case)
    if order is not None:
        if sorted(order) != sorted(cases):
            raise ValueError(f"{suite}/{name}: the given order does not list exactly the case directories")
        cases = {key: cases[key] for key in order}
    elif path.exists():
        previous = list(json.loads(path.read_text())["cases"])
        cases = {key: cases[key] for key in previous if key in cases} | {
            key: value for key, value in cases.items() if key not in previous}
    frozen = {"held_out": held_out, "cases": cases}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(frozen, indent=2) + "\n")
    return frozen


def write_case(suite: str | Path, name: str, case_id: str, language: str, input: Any, oracle: Any, case: dict,
               root: Path = EVALS) -> Path:
    """Write one case directory: indented JSON, keys in the given order; ``root`` defaults to this evals tree.
    ``suite`` may instead be an eval root path (a v2 agent's evals/ directory), which ``root`` then does not prefix."""
    directory = (suite if isinstance(suite, Path) else root / suite) / language / name / case_id
    directory.mkdir(parents=True, exist_ok=True)
    for part, value in (("input", input), ("oracle", oracle), ("case", case)):
        (directory / f"{part}.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return directory


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Check or freeze an eval set manifest")
    parser.add_argument("suite")
    parser.add_argument("set")
    parser.add_argument("--freeze", action="store_true", help="rewrite the manifest from the set's case directories")
    args = parser.parse_args()
    if args.suite in AGENTS:
        args.suite = agent_root(args.suite)
    if args.freeze:
        frozen = freeze(args.suite, args.set)
        print(f"{args.suite}/{args.set}: {len(frozen['cases'])} cases frozen")
    else:
        print(f"{args.suite}/{args.set}: {len(load_set(args.suite, args.set))} cases match the manifest")


if __name__ == "__main__":
    main()
