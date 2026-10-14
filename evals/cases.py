"""Per-case eval directories and frozen set manifests, shared by the agent suites (PLAN-0094).

    evals/<suite>/sets/<set>.json         {"held_out": false, "cases": {"<case id>": "<sha256>", ...}}
    evals/<suite>/cases/<case id>/
      input.json                           exactly what the suite's task receives (the agent's input)
      oracle.json                          evaluator-only expectations and scripted replay; never reaches the agent
      case.json                            language, framework, family, behaviour probed, provenance

A case hash is the SHA-256 of the canonical JSON of the three files together, so a set's identity changes only when
a case it lists changes, not when unrelated cases are added beside it. ``set_digest`` is the dataset identity a suite
reports. ``case.json`` is metadata for people and the inventory; suites never pass it to an agent.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

EVALS = Path(__file__).resolve().parent
CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
LANGUAGES = ("python", "java", "javascript", "ruby", "perl", "none")
CASE_FIELDS = {"language", "framework", "family", "probes", "kind", "provenance"}
PROVENANCE_FIELDS = {"source", "license"}


@dataclass(frozen=True)
class EvalCase:
    name: str
    input: Any
    oracle: Any
    case: dict


def _read(directory: Path) -> EvalCase:
    loaded = {part: json.loads((directory / f"{part}.json").read_text()) for part in ("input", "oracle", "case")}
    return EvalCase(directory.name, loaded["input"], loaded["oracle"], loaded["case"])


def case_hash(case: EvalCase) -> str:
    return sha256(json.dumps({"input": case.input, "oracle": case.oracle, "case": case.case},
                             sort_keys=True).encode()).hexdigest()


def check_case(case: EvalCase) -> None:
    if not CASE_ID.fullmatch(case.name):
        raise ValueError(f"case id {case.name!r} is not lower-case kebab")
    meta = case.case
    missing = CASE_FIELDS - set(meta)
    if missing:
        raise ValueError(f"{case.name}: case.json lacks {sorted(missing)}")
    if meta["language"] not in LANGUAGES:
        raise ValueError(f"{case.name}: unknown language {meta['language']!r}")
    if not PROVENANCE_FIELDS <= set(meta["provenance"]):
        raise ValueError(f"{case.name}: provenance needs {sorted(PROVENANCE_FIELDS)}")


def manifest(suite: str, name: str) -> dict:
    return json.loads((EVALS / suite / "sets" / f"{name}.json").read_text())


def load_set(suite: str, name: str) -> list[EvalCase]:
    """The set's cases in manifest order; refused when a listed case differs from its frozen hash."""
    frozen = manifest(suite, name)
    cases = []
    for case_id, digest in frozen["cases"].items():
        case = _read(EVALS / suite / "cases" / case_id)
        check_case(case)
        if case_hash(case) != digest:
            raise ValueError(f"{suite} case {case_id} differs from the frozen {name} manifest")
        cases.append(case)
    return cases


def set_digest(suite: str, name: str) -> str:
    return sha256(json.dumps(manifest(suite, name), sort_keys=True).encode()).hexdigest()


def freeze(suite: str, name: str, case_ids: list[str] | None = None, *, held_out: bool = False) -> dict:
    """Rewrite a set manifest from the case directories (all of them when no ids are given)."""
    root = EVALS / suite / "cases"
    ids = case_ids if case_ids is not None else sorted(p.name for p in root.iterdir() if p.is_dir())
    cases = {case_id: case_hash(_read(root / case_id)) for case_id in ids}
    for case_id in ids:
        check_case(_read(root / case_id))
    frozen = {"held_out": held_out, "cases": cases}
    path = EVALS / suite / "sets" / f"{name}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(frozen, indent=2) + "\n")
    return frozen


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Freeze a per-case eval set manifest")
    parser.add_argument("suite")
    parser.add_argument("set")
    parser.add_argument("--freeze", action="store_true", help="rewrite the manifest from every case directory")
    args = parser.parse_args()
    if args.freeze:
        frozen = freeze(args.suite, args.set)
        print(f"{args.suite}/{args.set}: {len(frozen['cases'])} cases frozen")
    else:
        print(f"{args.suite}/{args.set}: {len(load_set(args.suite, args.set))} cases match the manifest")


if __name__ == "__main__":
    main()
