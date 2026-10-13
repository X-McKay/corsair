"""IDEA-0005 step 1: the 50-row candidate inventory joined with reviewed per-case manifests; offline only.

Every inventory row stays in the denominator. A manifest under ``benchmarks/cases/<dir>/case.yaml`` splits what an
agent may see from evaluator-only labels; the loader refuses manifests that disagree with the inventory or whose
agent text names the case, its advisory or a dataset. Nothing here runs a case or reaches the chain.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml

from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.agents.source.contracts import SourceFile, confined_path
from evals.fixture_chain.evaluate import ChainOracle

REPOSITORY = Path(__file__).resolve().parents[2]
INVENTORY = REPOSITORY / "benchmarks/candidate-cases.json"
CASES = REPOSITORY / "benchmarks/cases"
Gap = Literal["G1", "G2", "G2b", "G2c", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"]
Admission = Literal["not_admitted", "admitted"]
Outcome = Literal["passed", "failed"]
COMMIT = re.compile(r"[0-9a-f]{40}")
ADVISORY = re.compile(r"\bCVE-\d{4}-\d{4,}\b|\bGHSA(?:-[0-9a-z]{4}){3}\b", re.IGNORECASE)

# Operator-owned defaults for rows without a manifest, from the IDEA-0005 "Blocks" column by language. G7 applies
# until a reviewed manifest shows the effect is a file open; G13 applies until a build is measured, so unmeasured
# limits stay visible rather than counting as zero; G9 blocks none; G15 applies until runtime and framework versions
# are resolved from the case's own build files.
_COMMON = ("G2", "G2b", "G2c", "G3", "G4", "G7", "G10", "G11", "G12", "G13", "G15")
DEFAULT_BLOCKING: dict[str, tuple[Gap, ...]] = {
    "Java": (*_COMMON, "G5", "G6", "G8"),
    "Python": (*_COMMON, "G14"),  # Vul4Py tests cannot be copied without a license
    "JavaScript": (*_COMMON, "G5", "G6", "G8", "G14"),  # SecBench.js license
    "Perl": (*_COMMON, "G5", "G6", "G8", "G14"),  # prove emits TAP
    "Ruby": (*_COMMON, "G5", "G6", "G8"),
}


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InventoryCase(_Frozen):
    case_id: str
    language: str
    build_system: str
    project: str
    issue_id: str
    issue_category: str
    cwe: str | None
    source: str
    source_revision: str
    source_record_url: str
    repository_url: str | None
    fixed_reference: str | None
    vulnerable_reference: str | None
    vulnerable_version_claim: str | list[str] | None = None
    # SPEC-0042: the directory (relative to the repository) whose build files define the case's runtime, when the
    # vulnerable component lives inside a larger repository; None means the repository root.
    project_root: str | None = Field(default=None, pattern=r"^[\w.+-]+(/[\w.+-]+)*$")
    fixed_version_claim: str | list[str] | None
    oracle_supplied: bool
    license_status: str
    notes: str
    runtime_qualified: bool
    qualification_status: str
    retrieved_on: str

    @field_validator("project_root")
    @classmethod
    def relative_root(cls, value: str | None) -> str | None:
        if value is not None and any(part in (".", "..") for part in value.split("/")):
            raise ValueError("project_root must stay inside the repository")
        return value

    @property
    def fix_commit(self) -> str | None:
        found = COMMIT.findall(self.fixed_reference or "")
        return found[-1] if found else None


class Inventory(_Frozen):
    schema_version: Literal[1]
    status: str
    retrieved_on: str
    counting_rule: str
    cases: tuple[InventoryCase, ...]


class AgentPart(_Frozen):
    """The only part of a manifest an agent may see."""
    issue: str = Field(min_length=1, max_length=8192)
    scope: Literal["component", "application_path"]
    repository: str = Field(pattern=r"^https://")
    baseline: str = Field(pattern=rf"^{COMMIT.pattern}$")
    candidate: str = Field(pattern=rf"^{COMMIT.pattern}$")
    language: str
    build_system: str

    @field_validator("issue")
    @classmethod
    def no_advisory_id(cls, value: str) -> str:
        if ADVISORY.search(value):
            raise ValueError("agent issue text names an advisory id")
        return value


class ReferenceTest(_Frozen):
    path: str  # relative to the manifest's directory
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    placement: str | None = None  # where identical bytes go in each source variant

    _path = field_validator("path")(confined_path)


class RevisionOutcome(_Frozen):
    control: Outcome
    security: Outcome


class Expected(_Frozen):
    basis: Literal["hypothesis", "observed"]
    revisions: dict[Literal["baseline", "candidate"], RevisionOutcome]
    chain: ChainOracle | None  # None: the gate a whole run should reach is not yet known


class EvaluatorPart(_Frozen):
    """Labels and oracles; never given to an agent."""
    case_id: str
    cwe: str | None
    fix_reference: str | None
    issue_reviewed: bool
    reference_test: ReferenceTest | None
    expected: Expected | None
    split: Literal["development", "held_out"] | None
    admission: Admission
    blocking: tuple[Gap, ...]

    @model_validator(mode="after")
    def admitted_needs_evidence(self):
        if self.admission == "admitted" and not (
                self.issue_reviewed and self.reference_test and self.split and "G10" not in self.blocking
                and self.expected and self.expected.basis == "observed" and self.expected.chain is not None):
            raise ValueError("admitted requires a reviewed issue, reference test, split, observed expectations "
                             "with a chain oracle, and no G10")
        return self


class CaseManifest(_Frozen):
    agent: AgentPart
    evaluator: EvaluatorPart


@dataclass(frozen=True)
class BenchmarkEntry:
    inventory: InventoryCase
    directory: Path | None = None
    manifest: CaseManifest | None = None

    @property
    def admission(self) -> Admission:
        return self.manifest.evaluator.admission if self.manifest else "not_admitted"

    @property
    def blocking(self) -> tuple[Gap, ...]:
        return self.manifest.evaluator.blocking if self.manifest else DEFAULT_BLOCKING[self.inventory.language]


def load_inventory(path: Path = INVENTORY) -> Inventory:
    inventory = Inventory.model_validate_json(path.read_bytes())
    if len({case.case_id for case in inventory.cases}) != len(inventory.cases):
        raise ValueError("duplicate inventory case id")
    return inventory


def _repository(url: str | None) -> str | None:
    return url.rstrip("/").removesuffix(".git") if url else None


def check_manifest(manifest: CaseManifest, row: InventoryCase, datasets: set[str], directory: Path) -> None:
    """Refuse disagreement with the inventory and agent text that names the case, its advisory or a dataset."""
    agent, evaluator = manifest.agent, manifest.evaluator
    issue = agent.issue.casefold()
    for marker in (row.case_id, row.issue_id, *datasets):
        if marker.casefold() in issue:
            raise ValueError(f"{directory.name}: agent issue text names {marker!r}")
    if row.repository_url and _repository(agent.repository) != _repository(row.repository_url):
        raise ValueError(f"{directory.name}: repository differs from the inventory")
    if row.fix_commit and (agent.candidate != row.fix_commit or evaluator.fix_reference != row.fixed_reference):
        raise ValueError(f"{directory.name}: fix commit differs from the inventory")
    if (agent.language, agent.build_system) != (row.language, row.build_system):
        raise ValueError(f"{directory.name}: language or build system differs from the inventory")
    if row.cwe and evaluator.cwe != row.cwe:
        raise ValueError(f"{directory.name}: CWE differs from the inventory")
    test = evaluator.reference_test
    if test and sha256((directory / test.path).read_bytes()).hexdigest() != test.sha256:
        raise ValueError(f"{directory.name}: reference test digest differs from the frozen value")


def load(inventory_path: Path = INVENTORY, cases: Path = CASES) -> tuple[BenchmarkEntry, ...]:
    """All inventory rows in inventory order, each with its manifest if one exists."""
    rows = {row.case_id: row for row in load_inventory(inventory_path).cases}
    datasets = {row.source for row in rows.values()}
    found: dict[str, tuple[Path, CaseManifest]] = {}
    for path in sorted(cases.glob("*/case.yaml")):
        manifest = CaseManifest.model_validate(yaml.safe_load(path.read_text()))
        case_id = manifest.evaluator.case_id
        if case_id not in rows:
            raise ValueError(f"{path.parent.name}: unknown case id {case_id!r}")
        if case_id in found:
            raise ValueError(f"{path.parent.name}: second manifest for {case_id!r}")
        check_manifest(manifest, rows[case_id], datasets, path.parent)
        found[case_id] = (path.parent, manifest)
    return tuple(BenchmarkEntry(row, *found.get(case_id, (None, None))) for case_id, row in rows.items())


def agent_input(entry: BenchmarkEntry, source_files: tuple[SourceFile, ...] = ()) -> IssueAnalysisInput:
    """The issue-analysis input from the agent part alone; the neutral directory name stands in for the case id.

    Repository-scale source is not mapped yet (G2b), so the caller supplies any saved source files.
    """
    if entry.manifest is None or entry.directory is None:
        raise ValueError(f"{entry.inventory.case_id} has no manifest")
    agent = entry.manifest.agent
    return IssueAnalysisInput(fixture_id=entry.directory.name, issue=agent.issue, scope=agent.scope,
                              source_files=source_files)

