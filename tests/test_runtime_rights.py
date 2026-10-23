import io
import json
import tarfile
from pathlib import Path

import pytest

from corsair.runtime_rights import (EvidenceFile, RuntimeEvidence, evidence_files_from_tar,
                                    RUNTIME_SPECS, RuntimeSpec, collect_runtime_evidence,
                                    missing_package_copyrights, render_rights_evidence,
                                    write_rights_evidence)


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_images_pin_install_inputs_and_assert_runtime_versions():
    requirements = (ROOT / "images/python/requirements.lock").read_text().splitlines()
    package_lines = [line for line in requirements if line and not line.startswith("#")]
    assert [line.split("==", 1)[0] for line in package_lines] == [
        "coverage", "iniconfig", "packaging", "pluggy", "Pygments", "pytest",
    ]
    assert all(" --hash=sha256:" in line for line in package_lines)

    python = (ROOT / "images/python/Dockerfile").read_text()
    assert "COPY requirements.lock /opt/corsair/requirements.lock" in python
    assert "--require-hashes --only-binary=:all:" in python
    assert "Python 3.12.15" in python

    javascript = (ROOT / "images/javascript/Dockerfile").read_text()
    assert 'test "$(node --version)" = "v22.23.3"' in javascript

    java = (ROOT / "images/java21/Dockerfile").read_text()
    assert "java.runtime.version = 21.0.12.1+1-LTS" in java
    assert "/opt/corsair/licenses/jacoco-agent/about.html" in java
    assert "/opt/corsair/licenses/jacoco-cli/about.html" in java

    perl = (ROOT / "images/perl/Dockerfile").read_text()
    assert "5.040001" in perl
    assert "snapshot.debian.org/archive/debian/20261023T000000Z" in perl
    assert "snapshot.debian.org/archive/debian-security/20261023T000000Z" in perl
    assert "COPY packages.lock /opt/corsair/packages.lock" in perl
    assert "sed '/^#/d;/^$/d' /opt/corsair/packages.lock" in perl
    assert "--mount=type=secret,id=proxy_ca,mode=0444" in perl
    perl_packages = [line for line in (ROOT / "images/perl/packages.lock").read_text().splitlines()
                     if line and not line.startswith("#")]
    assert len(perl_packages) == 20
    assert "libcpanel-json-xs-perl=4.39-2~deb13u1" in perl_packages
    assert "perl-modules-5.40=5.40.1-6+deb13u1" in perl_packages


def test_runtime_rights_renderer_is_deterministic_and_embeds_exact_license_bytes():
    evidence = RuntimeEvidence(
        runtime_row="row-a", family_id="cf-1", case_ids=("case-b", "case-a"),
        image_reference="runtime:dev", image_id="sha256:" + "a" * 64,
        platform="linux/amd64", image_created="2026-10-23T00:00:00Z",
        parent_reference="registry.example/runtime@sha256:" + "b" * 64,
        parent_image_id="sha256:" + "c" * 64,
        dockerfile="images/runtime/Dockerfile", dockerfile_sha256="d" * 64,
        runtime_versions=("tool 2.0", "runtime 1.0"),
        packages=("zlib\t1.2", "base\t1.0"),
        artifacts=(("tool.jar", "f" * 64), ("runtime.bin", "e" * 64)),
        license_files=(
            EvidenceFile(path="/licenses/z", content=b"last\n"),
            EvidenceFile(path="/licenses/a", content=b"first\nwith-newline\n"),
        ),
    )

    rendered = render_rights_evidence(evidence)
    assert rendered == render_rights_evidence(evidence)
    assert rendered.startswith(b"schema: corsair-runtime-rights-evidence/1\n")
    assert b"review_status: candidate-evidence-unreviewed\n" in rendered
    assert b"clean_rebuild_identity: not-established\n" in rendered
    assert b"no stable clean-rebuild image ID is asserted" in rendered
    assert rendered.index(b"case-a") < rendered.index(b"case-b")
    assert rendered.index(b"base\\t1.0") < rendered.index(b"zlib\\t1.2")
    assert rendered.index(b"/licenses/a") < rendered.index(b"/licenses/z")
    assert b"sha256: b89545c5d2fccb30fc0bf847059b366633baf8e2a14f0a616f5e9741a656408f" in rendered
    assert b"first\nwith-newline\n" in rendered
    assert b"generated_at" not in rendered


def test_runtime_rights_renderer_rejects_ambiguous_evidence_paths():
    common = dict(
        runtime_row="row-a", family_id="cf-1", case_ids=("case-a",),
        image_reference="runtime:dev", image_id="sha256:" + "a" * 64,
        platform="linux/amd64", image_created="2026-10-23T00:00:00Z",
        parent_reference="registry.example/runtime@sha256:" + "b" * 64,
        parent_image_id="sha256:" + "c" * 64,
        dockerfile="images/runtime/Dockerfile", dockerfile_sha256="d" * 64,
        runtime_versions=("runtime 1.0",), packages=(), artifacts=(),
    )
    with pytest.raises(ValueError, match="unique"):
        render_rights_evidence(RuntimeEvidence(
            **common, license_files=(EvidenceFile(path="/LICENSE", content=b"a"),
                                     EvidenceFile(path="/LICENSE", content=b"b"))))
    with pytest.raises(ValueError, match="unsafe"):
        render_rights_evidence(RuntimeEvidence(
            **common, license_files=(EvidenceFile(path="/LICENSE\nspoof", content=b"a"),)))


def _tar(entries: tuple[tuple[str, bytes], ...], *, symlink: str | None = None) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        if symlink is not None:
            info = tarfile.TarInfo(symlink)
            info.type = tarfile.SYMTYPE
            info.linkname = "/outside"
            archive.addfile(info)
    return output.getvalue()


def test_runtime_rights_tar_reader_preserves_exact_regular_file_bytes():
    files = evidence_files_from_tar(_tar((("usr/share/doc/z/copyright", b"z\n"),
                                          ("usr/local/LICENSE", b"license bytes"))))
    assert files == (
        EvidenceFile(path="/usr/local/LICENSE", content=b"license bytes"),
        EvidenceFile(path="/usr/share/doc/z/copyright", content=b"z\n"),
    )


@pytest.mark.parametrize("archive", [
    _tar((("../escape", b"bad"),)),
    _tar((), symlink="usr/share/doc/link"),
])
def test_runtime_rights_tar_reader_rejects_nonregular_or_escaping_entries(archive):
    with pytest.raises(ValueError, match="unsafe"):
        evidence_files_from_tar(archive)


def test_runtime_rights_collector_binds_image_parent_dockerfile_and_inventory(tmp_path):
    dockerfile = tmp_path / "images/runtime/Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text("FROM example\n")
    license_archive = _tar((("usr/share/doc/base/copyright", b"base terms\n"),
                            ("usr/share/doc/zlib/copyright", b"zlib terms\n")))
    calls: list[tuple[str, ...]] = []

    def runner(arguments: tuple[str, ...]) -> bytes:
        calls.append(arguments)
        if arguments[:2] == ("image", "inspect"):
            reference = arguments[2]
            identity = "a" if reference == "runtime:dev" else "b"
            return json.dumps([{
                "Id": "sha256:" + identity * 64,
                "Architecture": "amd64",
                "Os": "linux",
                "Created": "2026-10-23T00:00:00Z",
            }]).encode()
        if arguments[-1] == "versions-command":
            return b"runtime 1.0\ntool 2.0\n"
        if arguments[-1] == "licenses-command":
            return license_archive
        if "dpkg-query" in arguments:
            return b"zlib\t1.2\nbase\t1.0\n"
        if arguments[-1] == "artifacts-command":
            return (b"" + b"c" * 64 + b"  /usr/bin/runtime\n")
        raise AssertionError(arguments)

    spec = RuntimeSpec(
        runtime_row="row-a", family_id="cf-1", case_ids=("case-a",), image="runtime:dev",
        parent="registry.example/runtime@sha256:" + "d" * 64,
        dockerfile="images/runtime/Dockerfile", version_command="versions-command",
        license_command="licenses-command", artifact_command="artifacts-command",
    )
    evidence = collect_runtime_evidence(tmp_path, spec, runner=runner)
    assert evidence.image_id == "sha256:" + "a" * 64
    assert evidence.parent_image_id == "sha256:" + "b" * 64
    assert evidence.platform == "linux/amd64"
    assert evidence.packages == ("base\t1.0", "zlib\t1.2")
    assert evidence.artifacts == (("/usr/bin/runtime", "c" * 64),)
    assert evidence.license_files == (
        EvidenceFile("/usr/share/doc/base/copyright", b"base terms\n"),
        EvidenceFile("/usr/share/doc/zlib/copyright", b"zlib terms\n"),
    )
    assert ("run", "--rm", "--network", "none", "--entrypoint", "dpkg-query", "runtime:dev",
            "-W", "-f=${Package}\\t${Version}\\n") in calls


def test_runtime_rights_specs_cover_every_conformance_runtime_and_required_license_sources():
    assert {spec.runtime_row for spec in RUNTIME_SPECS} == {
        "pytest-cpython312", "node-test-node22", "javac-java21", "perl-tap-540",
    }
    by_row = {spec.runtime_row: spec for spec in RUNTIME_SPECS}
    assert "/usr/local/lib/python3.12/LICENSE.txt" in by_row["pytest-cpython312"].license_command
    assert "/usr/local/LICENSE" in by_row["node-test-node22"].license_command
    assert '"$JAVA_HOME/legal"' in by_row["javac-java21"].license_command
    assert "/opt/corsair/licenses" in by_row["javac-java21"].license_command
    assert all("/usr/share/doc" in spec.license_command for spec in RUNTIME_SPECS)
    assert all("--hard-dereference" in spec.license_command for spec in RUNTIME_SPECS)
    assert "-MDevel::Cover" not in by_row["perl-tap-540"].version_command
    assert "require Devel::Cover" in by_row["perl-tap-540"].version_command
    assert all(spec.parent.startswith("docker.io/library/") and "@sha256:" in spec.parent
               for spec in RUNTIME_SPECS)


def test_runtime_rights_writer_is_atomic_and_check_mode_detects_drift(tmp_path):
    evidence = RuntimeEvidence(
        runtime_row="row-a", family_id="cf-1", case_ids=("case-a",),
        image_reference="runtime:dev", image_id="sha256:" + "a" * 64,
        platform="linux/amd64", image_created="2026-10-23T00:00:00Z",
        parent_reference="registry.example/runtime@sha256:" + "b" * 64,
        parent_image_id="sha256:" + "c" * 64,
        dockerfile="images/runtime/Dockerfile", dockerfile_sha256="d" * 64,
        runtime_versions=("runtime 1.0",), packages=("base\t1.0",), artifacts=(),
        license_files=(EvidenceFile(path="/LICENSE", content=b"terms\n"),),
    )
    destination = write_rights_evidence(tmp_path, evidence)
    assert destination == tmp_path / "benchmarks/dataset/evidence/runtime/row-a/RIGHTS-EVIDENCE.txt"
    assert destination.read_bytes() == render_rights_evidence(evidence)
    assert write_rights_evidence(tmp_path, evidence, check=True) == destination

    destination.write_bytes(b"drift\n")
    with pytest.raises(ValueError, match="differs"):
        write_rights_evidence(tmp_path, evidence, check=True)


def test_runtime_rights_detects_packages_without_extracted_copyright_bytes():
    packages = ("base-files\t1.0", "libc6:amd64\t2.0")
    files = (EvidenceFile("/usr/share/doc/base-files/copyright", b"terms\n"),)
    assert missing_package_copyrights(packages, files) == ("libc6",)
