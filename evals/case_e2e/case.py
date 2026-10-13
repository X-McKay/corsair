"""A benchmark case as chain input: the manifest's agent part over the baseline and candidate commits of a local
clone, the runtime selected from the baseline's build files and the harness of the selected framework row.

Only the manifest's agent part, the baseline's listed source and setup files and its build files reach an agent;
the evaluator part, the candidate commit's bytes and the case id stay here. The environment stage (SPEC-0068)
replaces the declared environment below with what it observes; only the scratch location and the observation and
witness facilities stay as declared. No witness facility is declared yet for languages other than Python.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from corsair.agents.issue_analysis.contracts import SourceFile
from corsair.agents.test_planning.contracts import EnvironmentEvidence
from corsair.composition.direct import FixtureCase, SetupSource
from corsair.core.disposition import EnvironmentIdentity
from corsair.nodes.runtime.detect import is_build_file
from corsair.nodes.runtime.environment import RuntimeCatalog, framework_row, runtime_inputs, select_runtime
from corsair.nodes.runtime.matrix import FrameworkRow, load as load_matrix
from evals.benchmark.cases import BenchmarkEntry, agent_input
from evals.benchmark.cases import load as load_cases
from tests.qualification.image_case import commit_tree

from .frameworks import Harness, harness as harness_for

REPOSITORY = Path(__file__).resolve().parents[2]
REVISIONS = ("baseline", "candidate")
# A local image's config id in reference form: image-only evidence names the image Docker ran, not a registry manifest.
LOCAL = "local/corsair-{row}@{config}"
SETUP_POLICY = "setup-public"
TEST_POLICY = "docker-offline-cap-drop-all"


class CaseRefused(ValueError):
    """The case cannot become chain input; nothing ran and no model was asked."""


@dataclass(frozen=True)
class CaseRun:
    case: FixtureCase
    catalog: RuntimeCatalog
    framework: FrameworkRow
    harness: Harness
    row: str  # The selected matrix image row
    image: str  # Its local image config id
    commits: dict[str, str]
    trees: dict[str, Path]


def entry(case: str) -> BenchmarkEntry:
    """The manifest by its directory name or its case id."""
    found = [e for e in load_cases() if e.manifest and (e.inventory.case_id == case or e.directory.name == case)]
    if len(found) != 1:
        raise CaseRefused(f"{case!r} names {len(found)} benchmark manifests")
    return found[0]


def _files(tree: Path, paths, what: str) -> tuple[SourceFile, ...]:
    files = []
    for path in paths:
        target = tree / path
        if target.is_symlink() or not target.is_file():
            raise CaseRefused(f"{what} {path} is not a regular file at the baseline commit")
        try:
            files.append(SourceFile(path=path, content=target.read_text()))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CaseRefused(f"{what} {path}: {exc}"[:512]) from exc
    return tuple(files)


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def build_case(found: BenchmarkEntry, repository: Path, work: Path, images: dict[str, str], timeout: int) -> CaseRun:
    """Chain input for one case; `images` maps matrix row ids to the operator's local image config ids. Raises
    CaseRefused, before any model request, when the baseline's build files select no row with a case harness."""
    agent = found.manifest.agent
    if not agent.source_paths or not agent.setup_paths:
        raise CaseRefused(f"{found.directory.name}: the manifest lists no source_paths or setup_paths")
    commits = {"baseline": agent.baseline, "candidate": agent.candidate}
    trees = {}
    for revision, commit in commits.items():
        present = subprocess.run(["git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
                                 capture_output=True, check=False)
        if present.returncode != 0:
            raise CaseRefused(f"{repository} does not hold the {revision} commit {commit}")
        trees[revision] = commit_tree(repository, work / revision, commit)
    baseline = trees["baseline"]
    language = agent.language.casefold()
    build = {p.relative_to(baseline).as_posix(): p.read_bytes() for p in sorted(baseline.rglob("*"))
             if p.is_file() and not p.is_symlink() and is_build_file(p.relative_to(baseline).as_posix())}
    runtime = runtime_inputs(build, language)
    catalog = RuntimeCatalog(load_matrix(), {row: LOCAL.format(row=row, config=config) for row, config in images.items()})
    outcome = select_runtime(runtime, catalog)
    if outcome.status != "supported":
        raise CaseRefused(outcome.reason[:2048])
    framework = framework_row(outcome.selection, catalog.matrix)
    try:
        harness = harness_for(framework)
    except ValueError as exc:
        raise CaseRefused(str(exc)) from exc
    image = images[outcome.selection.image_id]
    toolchain = outcome.toolchain
    # Declared only so the contracts hold before the environment stage replaces them (ready_evidence).
    environment = EnvironmentEvidence(
        language=agent.language, runtime=toolchain.runtime, framework=framework.name,
        discovery_command=harness.config.command, approved_test_paths=("declared-before-environment-stage",),
        baseline_test=None,
        scratch_location=harness.scratch_location, observation_facilities=harness.observation_facilities,
        witness_facilities=harness.witness_facilities)
    installed = {revision: harness.setup_identity(image, trees[revision], commit) for revision, commit in commits.items()}
    identity = EnvironmentIdentity(
        image_digest=outcome.image.rsplit("@sha256:", 1)[1], recipe_sha256=_digest("declared before the environment stage"),
        dependency_inventory_sha256=_digest(json.dumps(installed, sort_keys=True)), policy_revision=TEST_POLICY,
        limits_sha256=_digest(json.dumps({"network": "none", "timeout_seconds": timeout}, sort_keys=True)))
    case = FixtureCase(
        issue=agent_input(found, _files(baseline, agent.source_paths, "source")), environment=environment,
        environment_identity=identity,
        # The Docker workspace digests the commit it copied (tests/qualification/image_case.py DockerCase.prepare).
        revision_sources={revision: _digest(commit) for revision, commit in commits.items()},
        runtime=runtime,
        setup=SetupSource(commit=agent.baseline, source_private=False, policy_profile=SETUP_POLICY,
                          source_files=_files(baseline, agent.setup_paths, "setup file")))
    return CaseRun(case, catalog, framework, harness, outcome.selection.image_id, image, commits, trees)
