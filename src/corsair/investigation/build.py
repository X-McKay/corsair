"""From an issue request to chain input, deterministically and before any model request.

The repository is acquired at the request's exact commits, runtime selection reads the vulnerable revision's own
build files and fixes the image row and its one framework row, and the framework table supplies the runner and the
facilities declared to the planner. Setup source is the revision's build and CI files; issue source is the files
the issue names. Nothing here branches on a language. Every refusal is an `Refused` with a reason, recorded as the
run's admission stop.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from uuid import uuid4

from corsair.adapters.docker_image import commit_tree
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput, SourceFile
from corsair.agents.test_planning.contracts import EnvironmentEvidence
from corsair.composition.direct import CapturedReviewSource, FixtureCase, SetupSource
from corsair.core.disposition import EnvironmentIdentity
from corsair.nodes.runtime.detect import is_build_file
from corsair.nodes.runtime.environment import RuntimeCatalog, framework_row, runtime_inputs, select_runtime
from corsair.nodes.runtime.matrix import FrameworkRow, Matrix, load as load_matrix
from corsair.ports.tickets import TicketSnapshot

from .frameworks import Harness, NoHarness, harness as harness_for
from .request import IssueRequest

# The checkout a relative repository path is resolved against (committed corpus repositories).
CHECKOUT = Path(__file__).resolve().parents[3]
# A local image's config id in reference form: image-only evidence names the image Docker ran, not a registry manifest.
LOCAL = "local/corsair-{row}@{config}"
SETUP_POLICY = "setup-public"
TEST_POLICY = "docker-offline-cap-drop-all"
# Setup source: the agent's contract bounds (EnvironmentInput, SourceFile).
SETUP_FILES, SETUP_BYTES, FILE_CHARS = 32, 131072, 16384
# Issue source (IssueAnalysisInput).
SOURCE_FILES, SOURCE_BYTES = 16, 65536
CI = re.compile(r"(?:\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.yml|\.travis\.yml|appveyor\.yml|\.circleci/config\.yml"
                r"|azure-pipelines\.yml|Jenkinsfile|tox\.ini|Makefile)")
NAMED_PATH = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]+)(?![\w/-])")


class Refused(ValueError):
    """The request cannot become chain input; nothing ran and no model was asked."""


@dataclass(frozen=True)
class Investigation:
    request: IssueRequest
    case: FixtureCase
    catalog: RuntimeCatalog
    framework: FrameworkRow
    harness: Harness
    row: str  # The selected matrix image row
    image: str  # Its local image config id
    commits: dict[str, str]
    trees: dict[str, Path]
    repository: str
    bases: dict[str, str]  # How each field the request left out was filled: repository, scope


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def repository_of(request: IssueRequest) -> tuple[str, str]:
    """The repository and its basis: the request's, else a GitHub issue's own repository."""
    if request.repository:
        return request.repository, "request"
    issue = request.issue
    if isinstance(issue, TicketSnapshot) and issue.provider == "github":
        parts = urlsplit(issue.url)
        owner_repo = "/".join(parts.path.strip("/").split("/")[:2])
        return f"https://{parts.netloc}/{owner_repo}", "ticket"
    raise Refused("the request names no repository and the issue is not a GitHub issue")


def local_repository(url: str, roots: tuple[Path, ...]) -> Path:
    path = Path(url.removeprefix("file://")).resolve()
    if not any(path.is_relative_to(root.resolve()) for root in roots):
        raise Refused(f"{url} is not under an operator-allowed local repository root")
    return path


def _readable(tree: Path, paths) -> list[SourceFile]:
    files = []
    for path in paths:
        target = tree / path
        if target.is_symlink() or not target.is_file():
            continue
        try:
            content = target.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if len(content) <= FILE_CHARS:
            files.append(SourceFile(path=path, content=content))
    return files


def _bounded(files: list[SourceFile], count: int, total: int) -> tuple[SourceFile, ...]:
    """Smallest first while both bounds hold, then in path order; deterministic."""
    kept, used = [], 0
    for item in sorted(files, key=lambda f: (len(f.content.encode()), f.path)):
        size = len(item.content.encode())
        if len(kept) < count and used + size <= total:
            kept.append(item)
            used += size
    return tuple(sorted(kept, key=lambda f: f.path))


def setup_files(tree: Path, paths: list[str]) -> tuple[SourceFile, ...]:
    """The environment stage's setup source: the revision's build and CI files within the agent's bounds."""
    return _bounded(_readable(tree, [p for p in paths if is_build_file(p) or CI.fullmatch(p)]), SETUP_FILES, SETUP_BYTES)


def named_files(text: str, tree: Path, paths: list[str]) -> tuple[SourceFile, ...]:
    """The revision's files the issue names by repository path, within the identification input's bounds.

    Repository-scale identification (SPEC-0038) is not in the chain yet, so an issue that names no file has no
    source to identify against."""
    present = set(paths)
    named = [p.lstrip("./") for p in NAMED_PATH.findall(text)]
    return _bounded(_readable(tree, sorted({p for p in named if p in present})), SOURCE_FILES, SOURCE_BYTES)


def _acquire(repository: str, commits: dict[str, str], work: Path, roots: tuple[Path, ...], acquisition,
             checkout: Path = CHECKOUT) -> dict[str, Path]:
    """Each revision's tree as its commit records it."""
    if not repository.startswith(("file://", "https://")):
        source = (checkout / repository).resolve()
        if not source.is_relative_to(checkout.resolve()):
            raise Refused(f"{repository} escapes the checkout")
        clones = dict.fromkeys(commits, source)
    elif repository.startswith("file://"):
        source = local_repository(repository, roots)
        clones = dict.fromkeys(commits, source)
    else:
        if acquisition is None:
            raise Refused("no repository acquisition is configured for https repositories")
        from corsair.adapters.git_acquire import AcquisitionError
        from corsair.nodes.source_fetch import FetchTarget
        clones = {}
        for revision, commit in commits.items():
            try:
                acquired = acquisition.acquire(FetchTarget(repository, commit), (work / f"repo-{revision}").resolve(), uuid4())
            except (AcquisitionError, ValueError) as error:
                raise Refused(f"repository acquisition refused for {revision} {commit}: {error}"[:2048]) from error
            clones[revision] = Path(acquired.repository)
    trees = {}
    for revision, commit in commits.items():
        present = subprocess.run(["git", "-C", str(clones[revision]), "cat-file", "-e", f"{commit}^{{commit}}"],
                                 capture_output=True, check=False)
        if present.returncode != 0:
            detail = present.stderr.decode(errors="replace").strip()
            # Anything but git's missing-object message (ownership, corruption) is not "missing".
            raise Refused(f"{repository} does not hold the {revision} commit {commit}" if "Not a valid object" in detail else
                          f"{repository}: git could not read the {revision} commit {commit}: {detail}"[:2048])
        try:
            trees[revision] = commit_tree(clones[revision], work / revision, commit)
        except ValueError as error:
            raise Refused(str(error)) from error
    return trees


def build(request: IssueRequest, work: Path, images: dict[str, str], *, roots: tuple[Path, ...] = (),
          acquisition=None, matrix: Matrix | None = None, timeout: int = 600,
          default_scope: str = "component", checkout: Path = CHECKOUT) -> Investigation:
    """Chain input for one request; `images` maps matrix row ids to the operator's local image config ids, `roots`
    are the allowed local repository roots and `acquisition` a `GitAcquisition` for https repositories."""
    try:
        issue_text = request.issue_text()
    except ValueError as error:
        raise Refused(f"the issue text does not fit the identification input: {error}"[:2048]) from error
    repository, repository_basis = repository_of(request)
    if request.revision is None:
        raise Refused("the request names no revision (resolving a branch to a commit is not built yet)")
    if request.fixed_revision is None:
        raise Refused("the request names no fixed revision (a vulnerable-only run is not built yet)")
    commits = {"baseline": request.revision, "candidate": request.fixed_revision}
    trees = _acquire(repository, commits, work, roots, acquisition, checkout)
    baseline = trees["baseline"]
    paths = sorted(p.relative_to(baseline).as_posix() for p in baseline.rglob("*") if p.is_file() and not p.is_symlink())
    runtime = runtime_inputs({p: (baseline / p).read_bytes() for p in paths if is_build_file(p)})
    catalog = RuntimeCatalog(matrix or load_matrix(),
                             {row: LOCAL.format(row=row, config=config) for row, config in images.items()})
    outcome = select_runtime(runtime, catalog)
    if outcome.status != "supported":
        raise Refused(outcome.reason[:2048])
    framework = framework_row(outcome.selection, catalog.matrix)
    try:
        harness = harness_for(framework.name, route=True)
    except NoHarness as error:
        raise Refused(str(error)) from error
    setup = setup_files(baseline, paths)
    if not setup:
        raise Refused("no build or CI file of the revision fits the environment stage's setup source")
    sources = named_files(issue_text, baseline, paths)
    if not sources:
        raise Refused("the issue names no file of the revision; repository-scale identification (SPEC-0038) is not "
                      "in the chain yet")
    image = images[outcome.selection.image_id]
    # Declared only so the contracts hold before the environment stage replaces them (ready_evidence).
    environment = EnvironmentEvidence(
        language=outcome.toolchain.language, runtime=outcome.toolchain.runtime, framework=framework.name,
        discovery_command=harness.config.command, approved_test_paths=("declared-before-environment-stage",),
        baseline_test=None, scratch_location=harness.scratch_location,
        observation_facilities=harness.observation_facilities, witness_facilities=harness.witness_facilities)
    installed = {revision: [commit, image, *(sha256((trees[revision] / f).read_bytes()).hexdigest()
                                            if (trees[revision] / f).is_file() else None for f in harness.lockfiles)]
                 for revision, commit in commits.items()}
    identity = EnvironmentIdentity(
        image_digest=outcome.image.rsplit("@sha256:", 1)[1], recipe_sha256=_digest("declared before the environment stage"),
        dependency_inventory_sha256=_digest(json.dumps(installed, sort_keys=True)), policy_revision=TEST_POLICY,
        limits_sha256=_digest(json.dumps({"network": "none", "timeout_seconds": timeout}, sort_keys=True)))
    scope = request.scope or default_scope
    issue = IssueAnalysisInput(fixture_id=request.label[:128], issue=issue_text, scope=scope,
                               source_files=sources)
    case = FixtureCase(
        issue=issue, environment=environment, environment_identity=identity,
        # The Docker workspace digests the commit it copied (DockerCase.prepare).
        revision_sources={revision: _digest(commit) for revision, commit in commits.items()},
        # A real issue has no per-case envelope; the framework table's recorders bind the request (SPEC-0073).
        witness_from_recorders=True,
        review_sources={revision: CapturedReviewSource(
                            source_sha256=_digest(commits[revision]),
                            files=_bounded(_readable(tree, (source.path for source in sources)),
                                           SOURCE_FILES, SOURCE_BYTES))
                        for revision, tree in trees.items()},
        runtime=runtime,
        setup=SetupSource(commit=request.revision, source_private=False, policy_profile=SETUP_POLICY, source_files=setup))
    return Investigation(request, case, catalog, framework, harness, outcome.selection.image_id, image, commits, trees,
                         repository, {"repository": repository_basis, "scope": "request" if request.scope else "default"})
