"""Java and Perl use the same kernel gates and boolean-invariant contract as JavaScript."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import pytest

from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import Case, Finding, load_case, revision
from corsair.frameworks import framework
from corsair.frameworks.javac_java import _jacoco_coverage
from corsair.kernel import Fix, Gate, Hypothesis, Kernel, Label, RoleResult, Submission
from corsair.sandbox import DockerSandboxes
from corsair.sandbox.docker import docker, docker_available
from corsair.sandbox.port import SandboxSpec, labels
from tests.test_kernel import accept

ROOT = Path(__file__).resolve().parents[1]
PERL_SCRIPT = ROOT / "cases/cs-0004-b"
PERL_IMAGE = "corsair-lite-perl:dev"


def perl_script_reference():
    return Submission.model_validate_json((PERL_SCRIPT / "reference-submission.json").read_text())


def require_perl_image():
    if not (docker_available() and docker("image", "inspect", PERL_IMAGE).returncode == 0):
        pytest.skip(f"docker or {PERL_IMAGE} unavailable (make image)")


class ObservedPerlDocker(DockerSandboxes):
    """Record actual native role containers without replacing any sandbox operation."""

    def __init__(self):
        super().__init__()
        self.probe_containers = []

    def open_environment(self, image, workdir, sandbox_labels):
        name = super().open_environment(image, workdir, sandbox_labels)
        self.probe_containers.append((name, sandbox_labels["corsair.lite.revision"],
                                      sandbox_labels["corsair.lite.role"]))
        return name


def test_perl_script_post_environment_is_independent():
    adapter = framework("perl-tap")
    primary = dict(adapter.environment("control"))
    post = adapter.post_command("control", "bin/script-target.pl")
    assert primary["PERL5OPT"] and primary["DEVEL_COVER_OPTIONS"]
    assert "PERL5OPT" not in post.environment and "DEVEL_COVER_OPTIONS" not in post.environment
    assert post.environment["PERL5LIB"] == "/work"
    assert dict(adapter.environment("control")) == primary


def test_perl_script_reader_rejects_identical_content_source_ambiguity(tmp_path):
    target = tmp_path / "bin/script-target.pl"
    duplicate = tmp_path / "different-name.pm"
    target.parent.mkdir()
    target.write_text("sub main { return 1; }\nmain();\n")
    duplicate.write_bytes(target.read_bytes())
    hypothesis = perl_script_reference().hypothesis
    record = dict(role="control", result="PASS", invariant_held=True, exception_type=None, message=None)
    files = {"/tmp/corsair/result.json": json.dumps(record).encode(),
        "/tmp/corsair/junit.xml": b'<testsuite><testcase name="test_probe[control]"/></testsuite>',
        "/tmp/corsair/coverage.json": b'{"files":{"/work/bin/script-target.pl":{"executed_lines":[5,6]}}}'}
    read = framework("perl-tap").read(files, hypothesis, "control", tmp_path)
    assert read.result is RoleResult.PASS and read.invariant_held is True
    assert read.junit_tests == 1 and read.covered_target is None and read.covered_lines == ()


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("target_file,union", [
    ("bin/script-target.pl", False), ("bin/script-target.pl", True),
    ("source space/script-target[slug].pl", True),
], ids=["reference", "complementary-children", "literal-path"])
async def test_perl_script_collects_exact_child_statements_and_union(tmp_path, target_file, union):
    require_perl_image()
    reference = perl_script_reference()
    case = load_case(PERL_SCRIPT)
    decoy_file = "other/" + Path(target_file).name
    trees = {}
    for name in ("vulnerable", "fixed"):
        tree = tmp_path / name
        for filename in (target_file, decoy_file):
            target = tree / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = (PERL_SCRIPT / name / "bin/script-target.pl").read_text()
            target.write_text(contents + ("# Distinct same-basename decoy.\n" if filename == decoy_file else ""))
        trees[name] = revision(tree)
    case = case.model_copy(update={"revision": trees["vulnerable"], "fixed_revision": trees["fixed"],
        "finding": Finding(title="Perl child traversal", file_path=target_file)})
    probe = reference.probe
    if union:
        probe = probe.replace("    my $content = _launch(",
            "    _launch('/work/" + decoy_file + "', \"$base/allowed\", $payload, 'second');\n"
            "    _launch('/work/bin/script-target.pl', \"$base/allowed\", 'document', 'first');\n"
            "    my $content = _launch(")
    probe = probe.replace("/work/bin/script-target.pl", "/work/" + target_file)
    reference = reference.model_copy(update={"probe": probe, "hypothesis": reference.hypothesis.model_copy(
        update={"target_file": target_file})})
    backend = ObservedPerlDocker()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.fix is Fix.VERIFIED
    assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [run.invariant_held for run in result.runs] == [True, False, True, True]
    assert [run.result for run in result.runs] == [RoleResult.PASS, RoleResult.PASS, RoleResult.PASS, RoleResult.FAIL]
    assert len({name for name, _, _ in backend.probe_containers}) == 4
    assert [(rev, role) for _, rev, role in backend.probe_containers] == [
        ("vulnerable", "control"), ("vulnerable", "exploit"), ("fixed", "control"), ("fixed", "exploit")]
    for run in result.runs:
        assert run.covered_lines == (5, 6) and run.covered_target is True
        assert run.junit_tests == 1 and run.cleanup_confirmed
        files = json.loads(store.get(run.coverage))["files"]
        assert {5, 6, 10} <= set(files["/work/" + target_file]["executed_lines"])
        if union:
            assert 8 in files["/work/" + target_file]["executed_lines"]
            assert {5, 6, 10} <= set(files["/work/" + decoy_file]["executed_lines"])
        else:
            assert 8 not in files["/work/" + target_file]["executed_lines"]
            assert "/work/" + decoy_file not in files
        assert (19 if run.revision == "vulnerable" else 23) not in files["/work/" + target_file]["executed_lines"]
        native = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert native.get("name") == f"test_probe[{run.role}]"
        assert (native.find("failure") is None) == (run.result is RoleResult.PASS)
        assert native.find("error") is None
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
async def test_perl_script_same_basename_does_not_cover_target(tmp_path):
    require_perl_image()
    reference = perl_script_reference()
    tree = tmp_path / "tree"
    for filename in ("source space/script-target[slug].pl", "other/script-target[slug].pl"):
        target = tree / filename
        target.parent.mkdir(parents=True)
        contents = (PERL_SCRIPT / "vulnerable/bin/script-target.pl").read_text()
        target.write_text(contents + ("# Distinct same-basename decoy.\n" if filename.startswith("other/") else ""))
    case = load_case(PERL_SCRIPT).model_copy(update={"revision": revision(tree), "fixed_revision": None,
        "finding": Finding(title="Exact script identity", file_path="source space/script-target[slug].pl")})
    reference = reference.model_copy(update={
        "probe": reference.probe.replace("/work/bin/script-target.pl", "/work/other/script-target[slug].pl"),
        "hypothesis": reference.hypothesis.model_copy(update={"target_file": "source space/script-target[slug].pl"})})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_lines == () and run.covered_target is False
        assert run.result is RoleResult.PASS and run.junit_tests == 1 and run.cleanup_confirmed
        files = json.loads(store.get(run.coverage))["files"]
        assert 6 in files["/work/other/script-target[slug].pl"]["executed_lines"]
        assert "/work/source space/script-target[slug].pl" not in files
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
async def test_perl_script_identical_decoy_cannot_supply_target_branch(tmp_path):
    require_perl_image()
    tree = tmp_path / "tree"
    for filename in ("bin/script-target.pl", "other/script-target.pl"):
        target = tree / filename
        target.parent.mkdir(parents=True)
        target.write_text((PERL_SCRIPT / "vulnerable/bin/script-target.pl").read_text())
    reference = perl_script_reference()
    # The target only reaches line 8. A byte-identical decoy reaches line 10 afterwards.
    probe = reference.probe.replace("$payload, 'second');", "$payload, 'first');")
    probe = probe.replace("    return $content ne 'outside';",
        "    _launch('/work/other/script-target.pl', \"$base/allowed\", 'document', 'second');\n"
        "    return $content ne 'outside';")
    reference = reference.model_copy(update={"probe": probe, "hypothesis": reference.hypothesis.model_copy(
        update={"target_lines": (10,)})})
    case = load_case(PERL_SCRIPT).model_copy(update={"revision": revision(tree), "fixed_revision": None})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_target is None and run.covered_lines == () and run.cleanup_confirmed
        assert run.result is RoleResult.PASS and run.junit_tests == 1
    assert backend.labelled(kernel.run_id) == []


def perl_seed_database():
    # Generate genuine target statement data with the installed collector during build replay.
    return """mkdir -p /tmp/corsair /tmp/perl-seed/allowed
printf inside > /tmp/perl-seed/allowed/document
PERL5OPT=-MDevel::Cover DEVEL_COVER_OPTIONS='-db,/tmp/corsair/cover_db,-merge,1,-silent,1,-coverage,statement' perl /work/bin/script-target.pl /tmp/perl-seed/allowed document first
test -n "$(find /tmp/corsair/cover_db/runs -name 'cover.*' -type f -print -quit)"
for name in result.json junit.xml coverage.json keep.txt; do
    printf prepared-marker > /tmp/corsair/$name
done
chmod -R a+rwX /tmp/corsair
"""


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("seed", [False, True], ids=["clean", "genuine-stale-db"])
async def test_perl_script_cleared_child_startup_is_inconclusive(tmp_path, seed):
    require_perl_image()
    reference = perl_script_reference()
    probe = reference.probe.replace("    open my $child, '-|'",
        "    local $ENV{PERL5OPT};\n    delete $ENV{PERL5OPT};\n    open my $child, '-|'")
    if seed:
        probe = probe.replace("    my ($payload) = @_;", """    my ($payload) = @_;
    for my $name ('result.json', 'junit.xml', 'coverage.json', 'keep.txt') {
        open my $marker, '<', "/tmp/corsair/$name" or die 'missing prepared sibling';
        local $/;
        die 'prepared sibling changed' unless <$marker> eq 'prepared-marker';
        close $marker;
    }""")
    reference = reference.model_copy(update={"probe": probe, "build_script": perl_seed_database() if seed else ""})
    case = load_case(PERL_SCRIPT)
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_lines == () and run.covered_target is False
        assert run.result is RoleResult.PASS and run.junit_tests == 1 and run.cleanup_confirmed
        assert "/work/bin/script-target.pl" not in json.loads(store.get(run.coverage))["files"]
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("invalid", ["root-link", "interior-link", "root-file", "interior-fifo", "unwritable"])
async def test_perl_script_rejects_invalid_prepared_database(tmp_path, invalid):
    require_perl_image()
    alterations = {
        "root-link": "mv /tmp/corsair/cover_db /tmp/corsair/saved-db\nln -s saved-db /tmp/corsair/cover_db",
        "interior-link": "mv /tmp/corsair/cover_db/runs /tmp/corsair/saved-runs\nln -s ../saved-runs /tmp/corsair/cover_db/runs",
        "root-file": "rm -rf /tmp/corsair/cover_db\nprintf invalid > /tmp/corsair/cover_db",
        "interior-fifo": "mkfifo /tmp/corsair/cover_db/invalid-fifo",
        "unwritable": "chmod a-w /tmp/corsair/cover_db",
    }
    reference = perl_script_reference().model_copy(update={"build_script": perl_seed_database() + alterations[invalid]})
    case = load_case(PERL_SCRIPT)
    backend = DockerSandboxes()
    kernel = Kernel(backend, matrix.select(case), case, artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.CONTROL_RUN, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert len(result.runs) == 1 and result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].invariant_held is None and result.runs[0].covered_lines == ()
    assert result.runs[0].cleanup_confirmed
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
async def test_perl_script_repository_core_module_and_trusted_renderer(tmp_path):
    require_perl_image()
    # Text::ParseWords is core but absent from Devel::Cover 1.44's observed early %INC.
    # File::Spec is early-loaded, so it would not honestly qualify repository shadowing here.
    tree = tmp_path / "tree"
    (tree / "Text").mkdir(parents=True)
    (tree / "Devel/Cover").mkdir(parents=True)
    (tree / "Text/ParseWords.pm").write_text("# SPDX-License-Identifier: Apache-2.0\n"
        "package Text::ParseWords;\nsub fixture_value {\n    return 'repository-core-shadow';\n}\n1;\n")
    (tree / "Devel/Cover/DB.pm").write_text("die 'repository DB dependency must not load';\n")
    (tree / "JSON").mkdir()
    (tree / "JSON/PP.pm").write_text("die 'repository JSON dependency must not load';\n")
    (tree / "launch.pl").write_text("# SPDX-License-Identifier: Apache-2.0\nuse Text::ParseWords ();\n"
        "die 'wrong core identity' unless $INC{'Text/ParseWords.pm'} eq '/work/Text/ParseWords.pm';\n"
        "print Text::ParseWords::fixture_value();\n")
    case = load_case(PERL_SCRIPT).model_copy(update={"revision": revision(tree), "fixed_revision": None,
        "finding": Finding(title="Repository core shadow", file_path="Text/ParseWords.pm")})
    probe = """package CorsairProbe;
our $CONTROL_PAYLOAD = 'same';
our $EXPLOIT_PAYLOAD = 'same';
sub run_target {
    chdir '/tmp' or die 'cannot enter child working directory';
    open my $child, '-|', $^X, '/work/launch.pl' or die 'launch failed';
    local $/;
    my $value = <$child>;
    close $child or die 'child failed';
    die 'wrong distinctive behavior' unless $value eq 'repository-core-shadow';
    return 1;
}
1;
"""
    reference = perl_script_reference().model_copy(update={"probe": probe, "hypothesis": Hypothesis(
        target_file="Text/ParseWords.pm", target_symbol="fixture_value", target_lines=(4,),
        root_cause="Synthetic module identity qualification.", expected_violation="No violation is expected.")})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict.label is Label.LIKELY_NOT_EXPLOITABLE
    for run in result.runs:
        assert run.invariant_held is True and run.covered_lines == (4,) and run.cleanup_confirmed
        files = json.loads(store.get(run.coverage))["files"]
        assert 4 in files["/work/Text/ParseWords.pm"]["executed_lines"]
        assert not any("render_coverage.pl" in path or "Devel/Cover/DB.pm" in path for path in files)
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.parametrize("invalid", [None, "root-link", "interior-link"])
def test_perl_script_renderer_unsets_image_defaults_and_does_not_collect(invalid):
    require_perl_image()
    adapter = framework("perl-tap")
    backend = DockerSandboxes()
    run_id = "perl-render-" + uuid4().hex[:12]
    seed_name = backend.create(SandboxSpec(image=PERL_IMAGE, labels=labels(run_id, "seed")))
    image = "corsair-perl-render-test:" + uuid4().hex
    name = None
    try:
        # Missing -M module makes retaining an image-level PERL5OPT fail before the renderer can run.
        committed = docker("commit", "--change", "ENV PERL5OPT=-MNoSuchCorsairCollector",
                           "--change", "ENV DEVEL_COVER_OPTIONS=image-default", seed_name, image)
        assert committed.returncode == 0, committed.stderr
        name = backend.create(SandboxSpec(image=image, labels=labels(run_id, "render")))
        assert backend.exec_once(name, ["mkdir", "-p", "/work/.corsair", "/tmp/corsair"],
                                 workdir="/", timeout=60).exit_code == 0
        for filename, data in adapter.driver_files().items():
            backend.write_file(name, "/work/.corsair/" + filename, data)
        backend.write_file(name, "/work/target.pl", b"my $value = 42;\nprint $value;\n")
        env = dict(adapter.environment("control"))
        # Renderer qualification seeds native data independently of primary startup configuration.
        env.update(PERL5OPT="-MDevel::Cover", DEVEL_COVER_OPTIONS="-db,/tmp/corsair/cover_db,-silent,1,-coverage,statement")
        seeded = backend.exec_once(name, ["perl", "/work/target.pl"], workdir="/work", env=env, timeout=60)
        assert seeded.exit_code == 0, seeded.stderr
        listing = ["sh", "-c", "find /tmp/corsair/cover_db/runs -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' | sort"]
        before = backend.exec_once(name, listing, workdir="/", timeout=60).stdout.splitlines()
        assert len(before) == 1
        if invalid:
            command = {
                "root-link": "mv /tmp/corsair/cover_db /tmp/corsair/saved-db; ln -s saved-db /tmp/corsair/cover_db",
                "interior-link": "mv /tmp/corsair/cover_db/runs /tmp/corsair/saved-runs; ln -s ../saved-runs /tmp/corsair/cover_db/runs",
            }[invalid]
            assert backend.exec_once(name, ["sh", "-c", command], workdir="/", timeout=60).exit_code == 0
            backend.write_file(name, "/tmp/corsair/coverage.json", b"unrendered-marker")
        renderer = adapter.driver_files()["render_coverage.pl"]
        precondition = b"BEGIN { die 'startup variable present' if exists $ENV{PERL5OPT} || exists $ENV{DEVEL_COVER_OPTIONS}; die 'PERL5LIB lost' unless $ENV{PERL5LIB} eq '/work'; }\n"
        backend.write_file(name, "/work/.corsair/render_coverage.pl", precondition + renderer)
        post = adapter.post_command("control", "target.pl")
        rendered = backend.exec_once(name, post.argv, workdir="/work", env=post.environment, timeout=60)
        if invalid:
            assert rendered.exit_code != 0
            assert backend.copy_out(name, ["/tmp/corsair/coverage.json"])["/tmp/corsair/coverage.json"] == b"unrendered-marker"
            return
        assert rendered.exit_code == 0, rendered.stderr
        files = backend.copy_out(name, ["/tmp/corsair/coverage.json"])
        assert json.loads(files["/tmp/corsair/coverage.json"])["files"]["target.pl"]["executed_lines"] == [1, 2]
        after = backend.exec_once(name, listing, workdir="/", timeout=60).stdout.splitlines()
        # merge_runs consumes native shards; a renderer collector would append a new one on exit.
        assert after == []
    finally:
        if name is not None:
            assert backend.remove(name)
        assert backend.remove(seed_name)
        docker("image", "rm", image)
    assert backend.labelled(run_id) == []


def test_java_coverage_rejects_duplicate_package_and_source_identity(tmp_path):
    target = tmp_path / "safe/src/main/java/Documents.java"
    duplicate = tmp_path / "other/src/main/java/Documents.java"
    target.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    target.write_text("final class Documents {}\n")
    duplicate.write_text('final class Helper {\n  private static final String TEXT = """\n'
                         + r'    \"""' + '\n    package fake;\n'
                         + r'    \"""' + '\n    """;\n}\n')
    jacoco = (b'<report name="ambiguous"><package name=""><sourcefile name="Documents.java">'
              b'<line nr="1" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>')

    assert _jacoco_coverage(jacoco, "safe/src/main/java/Documents.java", tmp_path) is None


def test_java_coverage_uses_unique_declared_package_identity(tmp_path):
    target = tmp_path / "app/src/main/java/org/example/Documents.java"
    target.parent.mkdir(parents=True)
    target.write_text("package org.example; final class Documents {}\n")
    jacoco = (b'<report name="unique"><package name="org/example"><sourcefile name="Documents.java">'
              b'<line nr="1" mi="0" ci="1" mb="0" cb="0"/></sourcefile></package></report>')

    normalized = _jacoco_coverage(jacoco, "app/src/main/java/org/example/Documents.java", tmp_path)
    assert json.loads(normalized)["files"]["app/src/main/java/org/example/Documents.java"]["executed_lines"] == [1]


@pytest.mark.docker
@pytest.mark.anyio
async def test_java_kernel_rejects_coverage_merged_across_module_source_roots(tmp_path):
    image = "corsair-lite-java:dev"
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    source = tmp_path / "source"
    target = source / "safe/src/main/java/Documents.java"
    duplicate = source / "other/src/main/java/Documents.java"
    target.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    target.write_text("final class Documents {\n  static boolean reviewed(String value) { return true; }\n}\n")
    duplicate.write_text('final class Helper {\n  private static final String TEXT = """\n'
                         + r'    \"""' + '\n    package fake;\n'
                         + r'    \"""' + '\n    """;\n'
                         '  static boolean check(String value) { return !value.equals("bad"); }\n}\n')
    case = Case(case_id="fixture:ambiguous-java-source", revision=revision(source), finding=Finding(
        title="reviewed Java target", file_path="safe/src/main/java/Documents.java", symbol="Documents.reviewed"))
    submission = Submission(contract_version="corsair-lite/differential-probe/2", hypothesis=Hypothesis(
        target_file="safe/src/main/java/Documents.java", target_symbol="Documents.reviewed", target_lines=(2,),
        root_cause="A helper accepts a bad value.", expected_violation="The helper returns false."),
        build_script=("mkdir -p /work/.corsair-java/classes\n"
                      "javac -d /work/.corsair-java/classes "
                      "/work/safe/src/main/java/Documents.java /work/other/src/main/java/Documents.java"),
        probe=('public final class CorsairProbe {\n'
               '  public static final String CONTROL_PAYLOAD = "ok";\n'
               '  public static final String EXPLOIT_PAYLOAD = "bad";\n'
               '  public static boolean runTarget(String payload) { return Helper.check(payload); }\n'
               '}\n'))
    backend = DockerSandboxes()

    result = await Kernel(backend, matrix.select(case), case,
                          artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept).evaluate(submission)

    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.runs[0].covered_target is None
    assert result.verdict.label is Label.INCONCLUSIVE and result.verdict.rule == "K3"
    assert result.verdict.revisions[0].reason_code == "CONTROL_COVERAGE"
    assert result.verdict.reason == "control did not execute safe/src/main/java/Documents.java lines [2]"
    assert backend.labelled() == []


@pytest.mark.parametrize("adapter_name,language,probe_fragment", [
    ("javac-java", "java", "public static boolean runTarget"),
    ("perl-tap", "perl", "sub run_target"),
])
def test_adapter_registry_has_explicit_java_and_perl_contracts(adapter_name, language, probe_fragment):
    adapter = framework(adapter_name)
    case_dir = ROOT / f"cases/path-traversal-{language}"
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    assert adapter.language == language and adapter.guard(submission.probe).passed
    assert probe_fragment in submission.probe
    assert matrix.select(load_case(case_dir)).framework == adapter_name


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("language,image", [
    ("java", "corsair-lite-java:dev"),
    ("perl", "corsair-lite-perl:dev"),
])
async def test_reference_submission_is_verified_in_native_runtime(tmp_path, language, image):
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    case_dir = ROOT / f"cases/path-traversal-{language}"
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    result = await Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept).evaluate(submission)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict is not None
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.fix is Fix.VERIFIED
    assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [run.invariant_held for run in result.runs] == [True, False, True, True]
    assert [run.result for run in result.runs] == [
        RoleResult.PASS, RoleResult.PASS, RoleResult.PASS, RoleResult.FAIL,
    ]
    for run in result.runs:
        assert run.junit_tests == 1 and run.coverage is not None and run.cleanup_confirmed
        assert run.covered_lines == submission.hypothesis.target_lines
        assert f"test_probe[{run.role}]" in store.get(run.junit).decode()
        native_case = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert (native_case.find("failure") is None) == (run.result is RoleResult.PASS)
        assert native_case.find("error") is None
        assert run.exception_type is None
        if language == "perl":
            status = "ok" if run.result is RoleResult.PASS else "not ok"
            assert f"{status} 1 - test_probe[{run.role}]" in store.get(run.output).decode().splitlines()
    assert backend.labelled() == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("language,image", [
    ("java", "corsair-lite-java:dev"),
    ("perl", "corsair-lite-perl:dev"),
])
async def test_probe_or_application_assertions_are_errors_in_boolean_runtimes(tmp_path, language, image):
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    case_dir = ROOT / f"cases/path-traversal-{language}"
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    if language == "java":
        probe = submission.probe.replace(
            'return !"outside".equals(content);',
            'if ("outside".equals(content)) throw new AssertionError("application assertion");\n'
            '            return true;')
    else:
        probe = submission.probe.replace(
            "return $content ne 'outside';",
            "die \"application assertion\\n\" if $content eq 'outside';\n    return 1;")
    backend = DockerSandboxes()
    result = await Kernel(backend, matrix.select(case), case, artifacts=ArtifactStore(tmp_path / "artifacts"), auditor=accept).evaluate(
        submission.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.EXPLOIT_RUN, result
    assert result.runs[-1].result is RoleResult.ERROR
    assert backend.labelled() == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("language,image", [("java", "corsair-lite-java:dev"), ("perl", "corsair-lite-perl:dev")])
@pytest.mark.parametrize("value", ["string", "number", "object", "missing"])
async def test_native_drivers_require_boolean(tmp_path, language, image, value):
    if not (docker_available() and docker("image", "inspect", image).returncode == 0):
        pytest.skip(f"docker or {image} unavailable (make image)")
    case_dir = ROOT / f"cases/path-traversal-{language}"
    case = load_case(case_dir)
    submission = Submission.model_validate_json((case_dir / "reference-submission.json").read_text())
    if language == "java":
        returned = {"string": '\"true\"', "number": "1", "object": "new Object()", "missing": "null"}[value]
        probe = submission.probe.replace("static boolean runTarget", "static Object runTarget")
        probe = probe.replace('return !"outside".equals(content);', "return " + returned + ";")
    else:
        returned = {"string": "'true'", "number": "2", "object": "{}", "missing": "undef"}[value]
        probe = submission.probe.replace("return $content ne 'outside';", "return " + returned + ";")
    backend = DockerSandboxes()
    result = await Kernel(backend, matrix.select(case), case, artifacts=ArtifactStore(tmp_path / "artifacts"),
                          auditor=accept).evaluate(submission.model_copy(update={"probe": probe}))
    assert result.gate.stage is Gate.CONTROL_RUN
    assert result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].exception_type == "TypeError" and result.runs[0].invariant_held is None
    assert backend.labelled() == []


JAVA_SCRIPT_CASE = ROOT / "cases/cs-0003-b"


class JavaEvidenceSandboxes(DockerSandboxes):
    """Inspect real role evidence around rendering without replacing execution."""

    def __init__(self, *, inspect_prepared=False, replace_raw=None, inspect_xml=False):
        super().__init__()
        self.primary_names = []
        self.raw_snapshots = []
        self.prepared = []
        self.prepared_after = []
        self.inspect_prepared = inspect_prepared
        self.replace_raw = replace_raw
        self.inspect_xml = inspect_xml
        self.xml_siblings = []

    def exec_once(self, name, argv, **kwargs):
        primary = tuple(argv) == ("sh", "/work/.corsair/run-java.sh")
        if primary:
            self.primary_names.append(name)
            if self.inspect_prepared:
                paths = [f"/tmp/corsair/{p}" for p in ("result.json", "junit.xml", "jacoco.xml", "keep.txt")]
                self.prepared.append(self.copy_out(name, paths))
        rendering = not primary and self.primary_names and name == self.primary_names[-1] and kwargs.get("env") is not None
        if rendering:
            # A fixed argv unset must defeat inherited/image-level startup options as well as the snapshot.
            kwargs["env"] = dict(kwargs["env"], JAVA_TOOL_OPTIONS="-javaagent:/absent-renderer-agent.jar")
        result = super().exec_once(name, argv, **kwargs)
        if primary and self.inspect_prepared:
            self.prepared_after.append(self.copy_out(name, paths))
        if primary and self.replace_raw:
            changed = super().exec_once(name, ["sh", "-c", self.replace_raw], workdir="/work", timeout=30)
            assert changed.exit_code == 0, changed
        if primary:
            self.raw_snapshots.append([self.copy_out(name, ["/tmp/corsair/jacoco.exec"])["/tmp/corsair/jacoco.exec"]])
        elif rendering:
            self.raw_snapshots[-1].append(self.copy_out(name, ["/tmp/corsair/jacoco.exec"])["/tmp/corsair/jacoco.exec"])
            if self.inspect_xml:
                self.xml_siblings.append(self.copy_out(name, ["/tmp/corsair/keep.txt", "/tmp/corsair/missing.xml"]))
        return result


def _java_script_reference():
    return Submission.model_validate_json((JAVA_SCRIPT_CASE / "reference-submission.json").read_text())


def _require_java_image():
    if not (docker_available() and docker("image", "inspect", "corsair-lite-java:dev").returncode == 0):
        pytest.skip("docker or corsair-lite-java:dev unavailable (make image)")


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("target_file", ["src/ScriptTarget.java", "source space/[main]/ScriptTarget.java"])
async def test_java_script_collects_exact_child_lines_and_verifies_fix(tmp_path, target_file):
    _require_java_image()
    reference = _java_script_reference()
    case = load_case(JAVA_SCRIPT_CASE)
    trees = {}
    for name in ("vulnerable", "fixed"):
        tree = tmp_path / name
        target = tree / target_file
        target.parent.mkdir(parents=True)
        target.write_text((JAVA_SCRIPT_CASE / name / "src/ScriptTarget.java").read_text())
        decoy = tree / "other/ScriptTarget.java"
        decoy.parent.mkdir()
        decoy.write_text(target.read_text().replace("package fixture;", "package other;"))
        trees[name] = revision(tree)
    case = case.model_copy(update={"revision": trees["vulnerable"], "fixed_revision": trees["fixed"],
                                   "finding": Finding(title="Java main traversal", file_path=target_file)})
    reference = reference.model_copy(update={"build_script": reference.build_script.replace(
        "/work/src/ScriptTarget.java", "'/work/" + target_file + "' /work/other/ScriptTarget.java"),
        "hypothesis": reference.hypothesis.model_copy(update={"target_file": target_file})})
    backend = JavaEvidenceSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.VERIFIED, result
    assert result.verdict.label is Label.LIKELY_EXPLOITABLE and result.verdict.fix is Fix.VERIFIED
    assert result.verdict.revisions[1].label is Label.LIKELY_NOT_EXPLOITABLE
    assert [(run.revision, run.role, run.result) for run in result.runs] == [
        ("vulnerable", "control", RoleResult.PASS), ("vulnerable", "exploit", RoleResult.PASS),
        ("fixed", "control", RoleResult.PASS), ("fixed", "exploit", RoleResult.FAIL),
    ]
    assert [run.invariant_held for run in result.runs] == [True, False, True, True]
    assert len(backend.primary_names) == len(set(backend.primary_names)) == 4
    for run, snapshots in zip(result.runs, backend.raw_snapshots, strict=True):
        assert run.covered_target is True and run.covered_lines == (8, 9)
        assert run.junit_tests == 1 and run.cleanup_confirmed and run.exception_type is None
        native_case = next(ET.fromstring(store.get(run.junit)).iter("testcase"))
        assert native_case.get("name") == f"test_probe[{run.role}]"
        assert native_case.find("error") is None
        assert (native_case.find("failure") is None) == (run.result is RoleResult.PASS)
        normalized = json.loads(_jacoco_coverage(store.get(run.coverage), target_file,
                                               Path(getattr(case, "revision" if run.revision == "vulnerable"
                                                            else "fixed_revision").source)))
        assert {8, 9} <= set(normalized["files"][target_file]["executed_lines"])
        assert len(snapshots) == 2 and snapshots[0] and snapshots[0] == snapshots[1]
        report = ET.fromstring(store.get(run.coverage))
        decoy = report.find("./package[@name='other']/sourcefile[@name='ScriptTarget.java']")
        assert decoy is not None and all(int(line.get("ci")) == 0 for line in decoy.findall("line"))
    assert backend.labelled(kernel.run_id) == []


_JAVA_SEED = '''
mkdir -p /tmp/corsair
chmod 777 /tmp/corsair
seed=$(mktemp -d)
mkdir "$seed/allowed"
printf seed-document > "$seed/allowed/document.txt"
(cd "$seed" && java -javaagent:/opt/corsair/jacoco-agent.jar=destfile=/tmp/corsair/jacoco.exec -cp /work/.corsair-java/classes fixture.ScriptTarget document.txt)
java -jar /opt/corsair/jacoco-cli.jar report /tmp/corsair/jacoco.exec --classfiles /work/.corsair-java/classes --xml /tmp/corsair/seed.xml
grep -Eq '<line nr="8" mi="0" ci="[1-9]' /tmp/corsair/seed.xml
chmod 666 /tmp/corsair/jacoco.exec
for file in result.json junit.xml jacoco.xml keep.txt; do
  printf prepared-marker > "/tmp/corsair/$file"
  chmod 666 "/tmp/corsair/$file"
done
rm -rf "$seed"
'''


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("prepared", ["clean", "stale", "symlink", "dangling", "directory", "unwritable", "locked-parent"])
async def test_java_script_without_child_agent_cannot_reuse_prepared_evidence(tmp_path, prepared):
    _require_java_image()
    reference = _java_script_reference()
    probe = reference.probe.replace("            Process process = child.start();",
                                    '            child.environment().remove("JAVA_TOOL_OPTIONS");\n'
                                    "            Process process = child.start();")
    build = reference.build_script
    if prepared != "clean":
        build += "\n" + _JAVA_SEED
        if prepared == "symlink":
            build += "mv /tmp/corsair/jacoco.exec /tmp/corsair/saved.exec\nln -s saved.exec /tmp/corsair/jacoco.exec\n"
        elif prepared == "dangling":
            build += "rm /tmp/corsair/jacoco.exec\nln -s missing.exec /tmp/corsair/jacoco.exec\n"
        elif prepared == "directory":
            build += "rm /tmp/corsair/jacoco.exec\nmkdir /tmp/corsair/jacoco.exec\nchmod 777 /tmp/corsair/jacoco.exec\n"
        elif prepared == "unwritable":
            build += "chmod 444 /tmp/corsair/jacoco.exec\n"
        elif prepared == "locked-parent":
            build += "chmod 555 /tmp/corsair\n"
        probe = probe.replace('        Path base = Files.createTempDirectory("corsair-java-main-");',
            '        for (String name : new String[]{"result.json", "junit.xml", "jacoco.xml", "keep.txt"}) {\n'
            '            if (!Files.readString(Path.of("/tmp/corsair", name)).equals("prepared-marker"))\n'
            '                throw new IllegalStateException("unrelated prepared artifact changed");\n'
            '        }\n'
            '        Path base = Files.createTempDirectory("corsair-java-main-");')
    backend = JavaEvidenceSandboxes(inspect_prepared=prepared != "clean")
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(load_case(JAVA_SCRIPT_CASE)), load_case(JAVA_SCRIPT_CASE),
                    artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference.model_copy(update={"probe": probe, "build_script": build}))
    assert result.verdict.label is Label.INCONCLUSIVE, result
    if prepared == "locked-parent":
        # Publishing a fresh report inode requires a writable parent; failure must remain nondecisive.
        assert result.gate.stage is Gate.CONTROL_RUN, result
        assert len(result.runs) == 1 and result.runs[0].result is RoleResult.ERROR
        assert result.runs[0].coverage is None and result.runs[0].invariant_held is None
        assert "coverage post-processing exited" in result.runs[0].message
    elif prepared in ("symlink", "dangling", "directory", "unwritable"):
        assert result.gate.stage is Gate.CONTROL_RUN, result
        assert len(result.runs) == 1 and result.runs[0].result in (RoleResult.ERROR, RoleResult.NOT_RUN)
        assert result.runs[0].invariant_held is None and result.runs[0].covered_lines == ()
        assert "Picked up JAVA_TOOL_OPTIONS" not in store.get(result.runs[0].output).decode().split("$ env")[0]
        assert all(set(snapshot.values()) == {b"prepared-marker"} for snapshot in backend.prepared_after)
    else:
        assert result.gate.stage is Gate.CONTROL_COVERAGE, result
        assert [run.result for run in result.runs] == [RoleResult.PASS, RoleResult.PASS]
        assert [run.invariant_held for run in result.runs] == [True, False]
        for run in result.runs:
            assert run.covered_target is False and run.covered_lines == () and run.junit_tests == 1
            normalized = json.loads(_jacoco_coverage(store.get(run.coverage), "src/ScriptTarget.java",
                                                   JAVA_SCRIPT_CASE / "vulnerable"))
            assert normalized["files"]["src/ScriptTarget.java"]["executed_lines"] == []
    for snapshot in backend.prepared:
        assert set(snapshot.values()) == {b"prepared-marker"}
    for snapshot in backend.prepared_after:
        assert snapshot["/tmp/corsair/jacoco.xml"] == snapshot["/tmp/corsair/keep.txt"] == b"prepared-marker"
    assert all(run.cleanup_confirmed for run in result.runs)
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("same_package", [False, True], ids=["different-package", "ambiguous-package"])
async def test_java_script_duplicate_basename_cannot_satisfy_target(tmp_path, same_package):
    _require_java_image()
    reference = _java_script_reference()
    tree = tmp_path / "source"
    for name in ("source space/[main]/ScriptTarget.java", "other/ScriptTarget.java"):
        target = tree / name
        target.parent.mkdir(parents=True)
        content = (JAVA_SCRIPT_CASE / "vulnerable/src/ScriptTarget.java").read_text()
        if name.startswith("other/") and not same_package:
            content = content.replace("package fixture;", "package other;")
        target.write_text(content)
    case = load_case(JAVA_SCRIPT_CASE).model_copy(update={"revision": revision(tree), "fixed_revision": None,
        "finding": Finding(title="Java main traversal", file_path="source space/[main]/ScriptTarget.java")})
    reference = reference.model_copy(update={
        "build_script": reference.build_script.replace("/work/src/ScriptTarget.java", "/work/other/ScriptTarget.java"),
        "probe": reference.probe if same_package else reference.probe.replace('"fixture.ScriptTarget"', '"other.ScriptTarget"'),
        "hypothesis": reference.hypothesis.model_copy(update={"target_file": "source space/[main]/ScriptTarget.java"})})
    backend = DockerSandboxes()
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference)
    assert result.gate.stage is Gate.CONTROL_COVERAGE, result
    assert result.verdict.label is Label.INCONCLUSIVE
    assert [run.invariant_held for run in result.runs] == [True, False]
    for run in result.runs:
        assert run.covered_lines == () and run.covered_target is (None if same_package else False)
        assert run.result is RoleResult.PASS and run.junit_tests == 1 and run.cleanup_confirmed
        report = ET.fromstring(store.get(run.coverage))
        package = "fixture" if same_package else "other"
        lines = report.findall(f"./package[@name='{package}']/sourcefile[@name='ScriptTarget.java']/line")
        assert {8, 9} <= {int(line.get("nr")) for line in lines if int(line.get("ci")) > 0}
    assert backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("raw_path", ["missing", "symlink", "directory"])
async def test_java_script_renderer_rejects_nonregular_current_raw(tmp_path, raw_path):
    _require_java_image()
    mutation = "mv /tmp/corsair/jacoco.exec /tmp/corsair/saved.exec\n"
    if raw_path == "symlink":
        mutation += "ln -s saved.exec /tmp/corsair/jacoco.exec\n"
    elif raw_path == "directory":
        mutation += "mkdir /tmp/corsair/jacoco.exec\n"
    backend = JavaEvidenceSandboxes(replace_raw=mutation)
    store = ArtifactStore(tmp_path / "artifacts")
    case = load_case(JAVA_SCRIPT_CASE)
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(_java_script_reference())
    assert result.gate.stage is Gate.CONTROL_RUN and result.verdict.label is Label.INCONCLUSIVE, result
    assert len(result.runs) == 1 and result.runs[0].result is RoleResult.ERROR
    assert result.runs[0].coverage is None and result.runs[0].invariant_held is None
    assert "coverage post-processing exited" in result.runs[0].message
    assert result.runs[0].cleanup_confirmed and backend.labelled(kernel.run_id) == []


@pytest.mark.docker
@pytest.mark.anyio
@pytest.mark.parametrize("output_path", [
    "symlink-raw", "hardlink-raw", "dangling", "directory", "symlink-sibling", "hardlink-sibling", "regular",
])
async def test_java_script_renderer_preserves_raw_and_siblings_for_prepared_xml(tmp_path, output_path):
    _require_java_image()
    reference = _java_script_reference()
    # Raw starts empty at build time and receives only genuine current compiler/driver/child evidence.
    build = reference.build_script + "\n" + """
mkdir -p /tmp/corsair
chmod 777 /tmp/corsair
: > /tmp/corsair/jacoco.exec
chmod 666 /tmp/corsair/jacoco.exec
printf sibling-marker > /tmp/corsair/keep.txt
chmod 666 /tmp/corsair/keep.txt
"""
    build += {
        "symlink-raw": "ln -s jacoco.exec /tmp/corsair/jacoco.xml\n",
        "hardlink-raw": "ln /tmp/corsair/jacoco.exec /tmp/corsair/jacoco.xml\n",
        "dangling": "ln -s missing.xml /tmp/corsair/jacoco.xml\n",
        "directory": "mkdir /tmp/corsair/jacoco.xml\nchmod 777 /tmp/corsair/jacoco.xml\n",
        "symlink-sibling": "ln -s keep.txt /tmp/corsair/jacoco.xml\n",
        "hardlink-sibling": "ln /tmp/corsair/keep.txt /tmp/corsair/jacoco.xml\n",
        "regular": "printf old-xml > /tmp/corsair/jacoco.xml\nchmod 666 /tmp/corsair/jacoco.xml\n",
    }[output_path]
    case = load_case(JAVA_SCRIPT_CASE)
    backend = JavaEvidenceSandboxes(inspect_xml=True)
    store = ArtifactStore(tmp_path / "artifacts")
    kernel = Kernel(backend, matrix.select(case), case, artifacts=store, auditor=accept)
    result = await kernel.evaluate(reference.model_copy(update={"build_script": build}))
    assert backend.raw_snapshots, result
    for before, after in backend.raw_snapshots:
        assert before and before[:5] == bytes.fromhex("01c0c01007")
        before_hash, after_hash = hashlib.sha256(before).hexdigest(), hashlib.sha256(after).hexdigest()
        assert before_hash == after_hash, {"before": before_hash, "after": after_hash, "raw_after": after[:20]}
    for siblings in backend.xml_siblings:
        assert siblings == {"/tmp/corsair/keep.txt": b"sibling-marker", "/tmp/corsair/missing.xml": None}
    if output_path in ("regular", "hardlink-sibling"):
        assert result.gate.stage is Gate.VERIFIED and result.verdict.fix is Fix.VERIFIED, result
        assert len(result.runs) == 4 and all(run.covered_lines == (8, 9) for run in result.runs)
    else:
        assert result.gate.stage is Gate.CONTROL_RUN and result.verdict.label is Label.INCONCLUSIVE, result
        assert len(result.runs) == 1 and result.runs[0].result is RoleResult.ERROR
        assert result.runs[0].coverage is None and result.runs[0].invariant_held is None
        assert "coverage post-processing exited" in result.runs[0].message
    assert all(run.cleanup_confirmed for run in result.runs)
    assert backend.labelled(kernel.run_id) == []
