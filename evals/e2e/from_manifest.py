"""Write the v2 whole-chain cases for one imported corpus family (evals/e2e/<language>/v2/<family>-<letter>/).

    PYTHONPATH=src:. .venv/bin/python -m evals.e2e.from_manifest benchmarks/corpus/<dataset>/manifest.json <family>
    PYTHONPATH=src:. .venv/bin/python -m evals.cases e2e v2 --freeze

A family is one exploitable and one fixed variant of the manifest (``repo_url`` ``eval-corpus/<lang>/<family>/<a|b>``).
The exploitable variant's case carries the fixed tree as ``fixed_source`` (expected R4, fix verified); the fixed
variant's case stands alone (expected R5). Inputs reuse the manifest finding and the opaque ``corpus:<digest>`` id,
so they build the same Case as ``corsair-v2 run --case``; the manifest truth goes only into ``oracle.json``. The
``replay`` block is the reference trajectory for that expected path (see README "Scorer"), citing the finding's
own line. Provenance comes from the family's ``provenance.json``. Held-out families are refused.
"""
import argparse
import json
from pathlib import Path

from corsair import intake, matrix

ROOT = Path(__file__).resolve().parents[2]
E2E = ROOT / "evals/e2e"
DIMENSIONS = ["correctness", "contract", "grounding", "trajectory", "safety"]


def _tree(manifest: Path, entry: dict) -> Path:
    return manifest.parent / entry["finding"]["repo_url"].removeprefix(intake.CORPUS_PREFIX)


def _citation(tree: Path, finding: dict) -> dict:
    line = finding["start_line"]
    return {"path": finding["file_path"], "start_line": line, "end_line": line,
            "quote": (tree / finding["file_path"]).read_text().splitlines()[line - 1]}


def _relative(path: Path, start: Path) -> str:
    return str(Path(*[".."] * len(start.relative_to(ROOT).parts)) / path.relative_to(ROOT))


def write_family(manifest: Path, family: str) -> list[Path]:
    manifest = manifest.resolve()
    held = set(json.loads((ROOT / "evals/corpus/held_out.json").read_text()))
    if family in held:
        raise SystemExit(f"{family} is held out")
    entries = [entry for entry in json.loads(manifest.read_text())["cases"]
               if Path(_tree(manifest, entry)).parent.name == family]
    verdicts = sorted(entry["truth"]["expected_verdict"] for entry in entries)
    if verdicts != ["likely_not_exploitable", "potentially_exploitable"]:
        raise SystemExit(f"{family}: expected one exploitable and one fixed variant, found {verdicts}")
    exploitable = next(e for e in entries if e["truth"]["expected_verdict"] == "potentially_exploitable")
    fixed = next(e for e in entries if e is not exploitable)
    provenance = json.loads((_tree(manifest, exploitable).parent / "provenance.json").read_text())
    written = []
    for entry in (exploitable, fixed):
        tree, finding, positive = _tree(manifest, entry), entry["finding"], entry is exploitable
        language, letter = entry["language"], tree.name
        directory = E2E / language / "v2" / f"{family}-{letter}"
        directory.mkdir(parents=True, exist_ok=True)
        case = intake.Case(case_id=intake.corpus_case_id(entry["name"]),
                           finding=intake.Finding(**{key: finding[key] for key in intake.FINDING_FIELDS if key in finding}),
                           revision=intake.revision(tree))
        row = matrix.select(case)
        if row is None:
            raise SystemExit(f"{entry['name']}: no runtime matrix row selects this tree")
        request = {"case_id": case.case_id, "finding": case.finding.model_dump(exclude_none=True),
                   "source": _relative(tree, directory)}
        cited = [_citation(tree, finding)]
        review = {"control": True, "exploit": True, "citations": cited}
        replay = {"plan": {"status": "planned", "citations": cited}, "build": [True],
                  "check": {"control": "ok", "exploit": "ok"}, "review": {"vulnerable": review},
                  "outcomes": {"vulnerable": {"control": "passed",
                                              "exploit": "passed" if positive else "assertion_failed"}}}
        if positive:
            other = _tree(manifest, fixed)
            request["fixed_source"] = _relative(other, directory)
            replay["review"]["fixed"] = review | {"citations": [_citation(other, fixed["finding"])]}
            replay["outcomes"]["fixed"] = {"control": "passed", "exploit": "assertion_failed"}
            replay["build_fixed"] = True
        label = "LIKELY_EXPLOITABLE" if positive else "LIKELY_NOT_EXPLOITABLE"
        other_label = "LIKELY_NOT_EXPLOITABLE" if positive else "LIKELY_EXPLOITABLE"
        truth = entry["truth"]
        oracle = {
            "expected_label": label, "acceptable_labels": [label], "forbidden_labels": [other_label],
            "expected_rule": "R4" if positive else "R5", "expected_terminal_reason": "ok",
            "expected_finding": "reproduced" if positive else "not_reproduced",
            "expected_fix": "verified" if positive else "not_applicable",
            "expected_runtime_row": row.row_id,
            "truth": {"source": "manifest", "manifest": str(manifest.relative_to(ROOT)), "manifest_case": entry["name"],
                      "manifest_truth": truth},
            "why": f"Manifest truth {truth['expected_verdict']} (reachability {truth.get('reachability')}).",
            "revision_tree_sha256": case.revision.tree_sha256,
            "fixed_tree_sha256": intake.revision(_tree(manifest, fixed)).tree_sha256 if positive else None,
            "replay": replay,
        }
        title = f"{finding['title']} ({finding.get('cwe')})"
        meta = {
            "language": language, "framework": row.framework, "family": family,
            "kind": "positive" if positive else "negative", "category": "capability",
            "probes": (f"{title} on the variant where untrusted input reaches the sink: the whole chain must reproduce "
                       f"it through {finding['symbol']}.") if positive else
                      (f"{title} reported against the variant where the upstream fix stops the input: the chain must "
                       "not reproduce it."),
            "expected": ("The control and the proof-of-vulnerability (exploit) probe pass on this tree, so the label "
                         "is LIKELY_EXPLOITABLE by R4; on the paired fixed tree the control passes and the PoV's "
                         "assertion fails, so the fix is verified.") if positive else
                        ("The control passes and the proof-of-vulnerability (exploit) probe's assertion fails on this "
                         "tree (the condition is not shown), so the label is LIKELY_NOT_EXPLOITABLE by R5."),
            "dimensions": DIMENSIONS,
            "provenance": {"source": provenance["upstream_repo"], "license": provenance["upstream_spdx"],
                           "record": provenance.get("record"), "fix_commit": provenance.get("fix_commit"),
                           "verbatim": provenance.get("verbatim"),
                           "path": str(tree.relative_to(ROOT))},
        }
        for name, content in (("input", request), ("oracle", oracle), ("case", meta)):
            (directory / f"{name}.json").write_text(json.dumps(content, indent=2) + "\n")
        written.append(directory)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("family", nargs="+")
    args = parser.parse_args(argv)
    for family in args.family:
        for directory in write_family(args.manifest, family):
            print(directory.relative_to(ROOT))


if __name__ == "__main__":
    main()
