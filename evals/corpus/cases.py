"""SPEC-0067: the infosec-harness paired corpus as Corsair cases; offline and evaluator-owned.

`benchmarks/corpus/infosec-harness/` is a verbatim copy of that repository's `eval-corpus/` (`SOURCE.md` names the
commit). Each topic directory becomes one case: the variant whose truth is `potentially_exploitable` is the baseline
revision and the other variant the candidate, so a full run should reach completed / reproduced / verified. The two
unpaired topics have only a baseline and should reach completed / not_reproduced / not_applicable. Both expectations
are hypotheses until a chain run observes them.

Agents see only the shared finding text (`issue_text()`) and the variant trees themselves. Variant names, verdicts, the manifest, the corpus README (it holds the answer key) and the
verification tests never enter an agent input. The loader refuses verdict words in anything an agent can read, as
the upstream corpus hygiene test does, so a copy that drifts is caught here too.
"""
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REPOSITORY = Path(__file__).resolve().parents[2]
CORPUS = REPOSITORY / "benchmarks/corpus/infosec-harness"
HELD_OUT = Path(__file__).with_name("held_out.json")
Language = Literal["python", "java", "javascript", "perl", "c"]
Verdict = Literal["potentially_exploitable", "likely_not_exploitable"]
SPLIT_SALT = "corsair-corpus-split-v1"
# Maintainer-only entries at the corpus root; none of them is a fixture.
NOT_FIXTURES = frozenset({"README.md", "SOURCE.md", "manifest.json", "external", "verification"})

# Ported from infosec-harness tests/evals/test_corpus_hygiene.py: label stems at a word start or a camelCase hump.
_STEMS = ("vuln", "fixed", "insecure", "secure", "unsafe", "safe", "exploit", "patch", "mitigat", "sanitiz", "unsanitiz")
LABEL = re.compile(r"(?<![A-Za-z])(?i:" + "|".join(_STEMS) + r")[A-Za-z]*"
                   r"|(?<=[a-z])(?:" + "|".join(stem.capitalize() for stem in _STEMS) + r")[A-Za-z]*")
ALLOWED_WORDS = ("AddressSanitizer",)  # a tool name, identical in both C variants


def label_words(text: str) -> list[str]:
    for word in ALLOWED_WORDS:
        text = re.sub(rf"(?<![A-Za-z]){word}(?![A-Za-z])", " ", text)
    return [match.group(0) for match in LABEL.finditer(text)]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Finding(_Frozen):
    title: str = Field(min_length=1)
    repo_url: str
    revision: Literal["HEAD"]
    file_path: str
    start_line: int = Field(ge=1)
    symbol: str
    cwe: str = Field(pattern=r"^CWE-\d+$")
    severity: str
    source_tool: str
    description: str = Field(min_length=1)


class Truth(_Frozen):
    expected_verdict: Verdict
    reachability: Literal["reachable", "neutralized", "unreachable", "unknown"]
    sink_file: str
    sink_line: int = Field(ge=1)
    source: str
    target_callable: str
    early_exit: str | None = None


class Entry(_Frozen):
    name: str
    language: Language
    finding: Finding
    truth: Truth

    @property
    def variant(self) -> PurePosixPath:
        """The variant directory relative to the corpus root, such as `python/cmdi/a`."""
        return PurePosixPath(self.finding.repo_url.removeprefix("eval-corpus/"))


class Manifest(_Frozen):
    version: Literal["1"]
    cases: tuple[Entry, ...]
    note: str


@dataclass(frozen=True)
class CorpusCase:
    """One Corsair case per topic. `baseline`/`candidate` are evaluator-only variant directories."""
    case_id: str
    language: Language
    topic: PurePosixPath
    finding: Finding  # the baseline variant's finding; a pair shares everything but location
    baseline: Entry
    candidate: Entry | None
    split: Literal["development", "held_out"]

    @property
    def oracle(self) -> dict:
        """The evaluator-only chain oracle, in the JSON shape the committed oracle.json files and held_out.json
        digests were frozen with (v1's ChainOracle with a completed gate)."""
        fix = "verified" if self.candidate else "not_applicable"
        finding = "reproduced" if self.baseline.truth.expected_verdict == "potentially_exploitable" else "not_reproduced"
        return {"stopped_at": None, "gate": {"execution": "completed", "finding": finding, "fix": fix},
                "assessment_admitted": True}

    def verification(self, role: Literal["baseline", "candidate"]) -> Path | None:
        """The upstream verification tests for a revision's variant (evaluator-only oracle), if the corpus has any."""
        entry = self.baseline if role == "baseline" else self.candidate
        directory = CORPUS / "verification" / str(entry.variant) if entry else None
        return directory if directory and directory.is_dir() else None


def load_manifest(corpus: Path = CORPUS) -> Manifest:
    return Manifest.model_validate_json((corpus / "manifest.json").read_bytes())


def snapshot(variant: Path) -> dict[str, bytes]:
    """The variant tree an agent and a sandbox may see: regular files, relative paths, nothing else."""
    files = {}
    for path in sorted(variant.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"{path}: symlink in a corpus variant")
        if path.is_file():
            files[path.relative_to(variant).as_posix()] = path.read_bytes()
    return files


def _check_visible(case_id: str, finding: Finding, tree: dict[str, bytes]) -> None:
    for field in ("title", "description", "file_path", "symbol"):
        if words := label_words(getattr(finding, field)):
            raise ValueError(f"{case_id}: finding {field} carries label words {words}")
    for path, data in tree.items():
        if words := label_words(path) + label_words(data.decode("utf-8", errors="replace")):
            raise ValueError(f"{case_id}: {path} carries label words {sorted(set(words))}")
    if finding.file_path not in tree:
        raise ValueError(f"{case_id}: finding file {finding.file_path} is not in the variant")


def _split(case_ids: list[str]) -> set[str]:
    """Held-out: per language, the quarter (rounded down) of cases with the lowest salted digest."""
    ranked = sorted(case_ids, key=lambda case_id: sha256(f"{SPLIT_SALT}:{case_id}".encode()).hexdigest())
    return set(ranked[:len(ranked) // 4])


def load(corpus: Path = CORPUS) -> tuple[CorpusCase, ...]:
    """Every topic as one case, in manifest order; refuses a pair that differs in more than location."""
    manifest = load_manifest(corpus)
    if len({entry.name for entry in manifest.cases}) != len(manifest.cases):
        raise ValueError("duplicate corpus case name")
    topics: dict[PurePosixPath, list[Entry]] = defaultdict(list)
    for entry in manifest.cases:
        if entry.variant.name not in {"a", "b"} or entry.variant.parts[0] != entry.language:
            raise ValueError(f"{entry.name}: variant directory {entry.variant} is not <language>/<topic>/<a|b>")
        topics[entry.variant.parent].append(entry)
    drafts = []
    for topic, entries in topics.items():
        case_id = f"ih-{topic.parts[0]}-{topic.name}"
        verdicts = sorted(entry.truth.expected_verdict for entry in entries)
        if len(entries) == 2:
            if verdicts != ["likely_not_exploitable", "potentially_exploitable"]:
                raise ValueError(f"{case_id}: a pair needs one verdict of each kind")
            first, second = (entry.finding.model_dump(exclude={"repo_url", "start_line"}) for entry in entries)
            if first != second:
                raise ValueError(f"{case_id}: paired findings differ beyond location")
            baseline, candidate = sorted(entries, key=lambda e: e.truth.expected_verdict != "potentially_exploitable")
        elif len(entries) == 1:
            baseline, candidate = entries[0], None
        else:
            raise ValueError(f"{case_id}: {len(entries)} variants")
        for entry in filter(None, (baseline, candidate)):
            _check_visible(case_id, entry.finding, snapshot(corpus / str(entry.variant)))
        drafts.append((case_id, topic, baseline, candidate))
    held_out = set()
    for language in {topic.parts[0] for _, topic, _, _ in drafts}:
        held_out |= _split([case_id for case_id, topic, _, _ in drafts if topic.parts[0] == language])
    return tuple(CorpusCase(case_id, baseline.language, topic, baseline.finding, baseline, candidate,
                            "held_out" if case_id in held_out else "development")
                 for case_id, topic, baseline, candidate in drafts)


def case_digest(case: CorpusCase, corpus: Path = CORPUS) -> str:
    """SHA-256 over a case's finding, oracle and both variant trees, so a changed held-out case is caught."""
    digest = sha256(json.dumps(dict(finding=case.finding.model_dump(mode="json"),
                                    oracle=case.oracle), sort_keys=True).encode())
    for role, entry in (("baseline", case.baseline), ("candidate", case.candidate)):
        for path, data in snapshot(corpus / str(entry.variant)).items() if entry else ():
            digest.update(f"\0{role}\0{path}\0".encode() + sha256(data).digest())
    return digest.hexdigest()


def tree_digest(corpus: Path = CORPUS) -> str:
    """SHA-256 over every copied file's path and bytes (SOURCE.md excluded), recorded in SOURCE.md at import."""
    digest = sha256()
    for path in sorted(p for p in corpus.rglob("*") if p.is_file() and p.relative_to(corpus).as_posix() != "SOURCE.md"):
        digest.update(path.relative_to(corpus).as_posix().encode() + b"\0" + sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def issue_text(finding: Finding) -> str:
    """Neutral issue text from the finding fields upstream submits to its investigator."""
    return (f"{finding.title}\n\nReported location: {finding.file_path} line {finding.start_line}, in {finding.symbol}. "
            f"Weakness class: {finding.cwe}.\n\n{finding.description}\n\nAnalyze this component only.")


def freeze_held_out(path: Path = HELD_OUT) -> None:
    path.write_text(json.dumps({case.case_id: case_digest(case) for case in load() if case.split == "held_out"},
                               indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Corpus case loader (SPEC-0067)")
    parser.add_argument("--freeze-held-out", action="store_true", help="rewrite held_out.json; the only way to change it")
    parser.add_argument("--tree-digest", action="store_true", help="print the copied corpus digest for SOURCE.md")
    parser.add_argument("--compare", type=Path, metavar="EVAL_CORPUS",
                        help="an upstream checkout's eval-corpus/ at the SOURCE.md commit; exit 1 unless it digests the same")
    args = parser.parse_args()
    if args.freeze_held_out: freeze_held_out()
    if args.tree_digest: print(tree_digest())
    if args.compare:
        upstream, copy = tree_digest(args.compare), tree_digest()
        print(f"upstream {upstream}\ncopy     {copy}")
        raise SystemExit(0 if upstream == copy else 1)
