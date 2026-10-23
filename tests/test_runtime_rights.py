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
    assert "rm -rf /usr/local/lib/node_modules/npm" in javascript
    assert "/usr/local/lib/node_modules/corepack" in javascript
    assert "/opt/yarn-v1.22.22" in javascript
    assert "! command -v npm" in javascript
    assert "! command -v corepack" in javascript
    assert "! command -v yarn" in javascript

    java = (ROOT / "images/java21/Dockerfile").read_text()
    assert "java.runtime.version = 21.0.12.1+1-LTS" in java
    assert "/opt/corsair/licenses/jacoco-agent/about.html" in java
    assert "/opt/corsair/licenses/jacoco-cli/about.html" in java
    assert "/opt/corsair/licenses/jacoco/EPL-2.0.txt" in java
    assert "61616a4066701bc7888ad910de1633dbc55eb4d4d30d930feef55afb9492e33c" in java

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
        runtime_row="row-a",
        image_reference="runtime:dev", image_id="sha256:" + "a" * 64,
        platform="linux/amd64", image_created="2026-10-23T00:00:00Z",
        parent_reference="registry.example/runtime@sha256:" + "b" * 64,
        parent_image_id="sha256:" + "c" * 64,
        dockerfile="images/runtime/Dockerfile", dockerfile_sha256="d" * 64,
        runtime_versions=("tool 2.0", "runtime 1.0"),
        packages=("zlib\t1.2", "base\t1.0"),
        artifacts=(("/tool.jar", "f" * 64), ("/runtime.bin", "e" * 64)),
        license_files=(
            EvidenceFile(path="/licenses/z", content=b"last\n"),
            EvidenceFile(path="/licenses/a", content=b"first\nwith-newline\n"),
        ),
    )

    rendered = render_rights_evidence(evidence)
    assert rendered == render_rights_evidence(evidence)
    assert rendered.startswith(b"schema: corsair-runtime-rights-evidence/2\n")
    assert b"review_status: candidate-evidence-unreviewed\n" in rendered
    assert b"clean_rebuild_identity: not-established\n" in rendered
    assert b"no stable clean-rebuild image ID is asserted" in rendered
    assert b"family_id:" not in rendered
    assert b"case_ids:" not in rendered
    assert (b"case_binding: \"Cases cite this evidence by runtime row, exact image ID, "
            b"and receipt; the bundle is case-agnostic.\"\n") in rendered
    assert rendered.index(b"base\\t1.0") < rendered.index(b"zlib\\t1.2")
    assert rendered.index(b"/licenses/a") < rendered.index(b"/licenses/z")
    assert b"sha256: b89545c5d2fccb30fc0bf847059b366633baf8e2a14f0a616f5e9741a656408f" in rendered
    assert b"first\nwith-newline\n" in rendered
    assert b"generated_at" not in rendered


def test_runtime_rights_renderer_rejects_ambiguous_evidence_paths():
    common = dict(
        runtime_row="row-a",
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


@pytest.mark.parametrize("name", [
    "../escape",
    "/absolute",
    "//server/share",
    "a/../b",
    "a//b",
    "a/./b",
])
def test_runtime_rights_tar_reader_rejects_absolute_or_noncanonical_paths(name):
    with pytest.raises(ValueError, match="unsafe"):
        evidence_files_from_tar(_tar(((name, b"bad"),)))


def test_runtime_rights_tar_reader_rejects_nonregular_entries():
    with pytest.raises(ValueError, match="unsafe"):
        evidence_files_from_tar(_tar((), symlink="usr/share/doc/link"))


@pytest.mark.parametrize("path", [
    "/../escape",
    "/a/../b",
    "//server/share",
    "/a//b",
    "/a/./b",
    "relative/path",
])
def test_runtime_rights_renderer_rejects_noncanonical_artifact_paths(path):
    evidence = RuntimeEvidence(
        runtime_row="row-a",
        image_reference="runtime:dev", image_id="sha256:" + "a" * 64,
        platform="linux/amd64", image_created="2026-10-23T00:00:00Z",
        parent_reference="registry.example/runtime@sha256:" + "b" * 64,
        parent_image_id="sha256:" + "c" * 64,
        dockerfile="images/runtime/Dockerfile", dockerfile_sha256="d" * 64,
        runtime_versions=("runtime 1.0",), packages=(),
        artifacts=((path, "e" * 64),),
        license_files=(EvidenceFile(path="/LICENSE", content=b"terms\n"),),
    )
    with pytest.raises(ValueError, match="canonical absolute"):
        render_rights_evidence(evidence)


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
                "RootFS": {"Type": "layers", "Layers": []},
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
        runtime_row="row-a", image="runtime:dev",
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
    assert ("run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--entrypoint", "dpkg-query", "sha256:" + "a" * 64,
            "-W", "-f=${Package}\\t${Version}\\n") in calls


def test_runtime_rights_specs_cover_every_conformance_runtime_and_required_license_sources():
    assert {spec.runtime_row for spec in RUNTIME_SPECS} == {
        "pytest-cpython312", "node-test-node22", "javac-java21", "perl-tap-540",
    }
    by_row = {spec.runtime_row: spec for spec in RUNTIME_SPECS}
    assert "/usr/local/lib/python3.12/LICENSE.txt" in by_row["pytest-cpython312"].license_command
    assert "*.dist-info/licenses/*" in by_row["pytest-cpython312"].license_command
    assert "*.dist-info/METADATA" in by_row["pytest-cpython312"].license_command
    assert "*/.dist-info/" not in by_row["pytest-cpython312"].license_command
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
        runtime_row="row-a",
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

# Phase A behavioral fixtures: freeze identities, retain byte spans, and reject
# evidence edges that cannot be verified from the bundle alone.
import hashlib
import os
from dataclasses import replace
import corsair.runtime_rights as rights

FIXED_IDS = dict(zip((spec.runtime_row for spec in RUNTIME_SPECS), (
    'sha256:43b0c43a93350375aa45a6ac664489826fce01599daae81dbc10127e4854110a',
    'sha256:0c057726aa5f32ca5e8b6793c2f0d40dfe1f9492dded237d7c1e14bc0a5401e1',
    'sha256:e09616f1ef5468b518d42719c99561f6944b4d8e8dfd7d56345c9272afe5532d',
    'sha256:90a29df261025b1c1e0d001373e10393ccc9c14f00b7baa14dc19a88c1c6b37f',
)))


def _fixture(tmp_path, row='row-a', extra=(), inputs=(), candidates=None):
    spec = RuntimeSpec(row, 'runtime:dev', 'parent@sha256:' + 'b'*64,
                       'images/runtime/Dockerfile', 'versions', 'licenses', 'artifacts')
    dockerfile = tmp_path / spec.dockerfile
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.write_bytes(b'FROM example\n')
    calls = []
    files = (('usr/share/doc/base/copyright', b'base terms\n'), *extra)
    candidates = candidates or {}
    def runner(args):
        calls.append(args)
        if args[:2] == ('image', 'inspect'):
            return json.dumps([dict(Id='sha256:' + ('b' if args[2] == spec.parent else 'a')*64,
                Architecture='amd64', Os='linux', Created='2026-10-23T00:00:00Z',
                RootFS=dict(Type='layers', Layers=['sha256:'+'f'*64, 'sha256:'+'e'*64, 'sha256:'+'f'*64]))]).encode()
        assert 'runtime:dev' not in args  # the tag could now identify another image
        assert '--read-only' in args and '--cap-drop' in args and 'ALL' in args
        assert '--security-opt' in args and 'no-new-privileges' in args
        if args[-1] == 'versions': return b'runtime 1\n'
        if 'dpkg-query' in args: return b'base\t1\n'
        if args[-1] == 'licenses': return _tar(files)
        if args[-1] == 'artifacts': return b'c'*64 + b'  /bin/runtime\n'
        if rights._FACT_COMMAND in args:
            result = []
            for path in args[args.index('--')+1:]:
                content = candidates.get(path, dict(('/'+p, c) for p,c in files).get(path))
                if content is None: result.append(dict(path=path, exists=False))
                else: result.append(dict(path=path, exists=True, resolved_path=path,
                    kind='regular', link_target=None, sha256=hashlib.sha256(content).hexdigest()))
            return b''.join(('\0'.join((r['path'], 'present' if r['exists'] else 'absent',
                    r.get('resolved_path',''),r.get('kind',''),r.get('link_target') or '',r.get('sha256','')))+'\0').encode() for r in result)
        if rights._PATH_ARCHIVE_COMMAND in args:
            requested = args[args.index('--')+1:]
            lookup = {**dict(('/'+p,c) for p,c in files), **dict(inputs), **candidates}
            return _tar(tuple((p[1:],lookup[p]) for p in requested))
        raise AssertionError(args)
    return spec, runner, calls


def test_phase_a_freezes_selected_identity_and_ordered_layers(tmp_path):
    spec, runner, calls = _fixture(tmp_path)
    evidence = collect_runtime_evidence(tmp_path, spec, runner=runner, image_id='sha256:'+'a'*64)
    assert evidence.image_reference == evidence.image_id == 'sha256:'+'a'*64
    assert evidence.configured_image_reference == 'runtime:dev'
    assert evidence.rootfs_diff_ids == ('sha256:'+'f'*64, 'sha256:'+'e'*64, 'sha256:'+'f'*64)
    assert evidence.parent_rootfs_diff_ids == evidence.rootfs_diff_ids
    assert all('sha256:'+'a'*64 in c for c in calls if c[0] == 'run')
    rendered = render_rights_evidence(evidence)
    assert rendered.startswith(b'schema: corsair-runtime-rights-evidence/2\n')
    assert b'layer_coverage: "not-collected"' in rendered
    header, _ = _parse_bundle(rendered)
    assert header['rootfs_diff_ids'] == ['sha256:'+'f'*64, 'sha256:'+'e'*64, 'sha256:'+'f'*64]
    assert header['parent_rootfs_diff_ids'] == header['rootfs_diff_ids']


@pytest.mark.parametrize('override', ['sha256:'+'b'*64, 'bad'])
def test_phase_a_rejects_bad_or_mismatching_identity(tmp_path, override):
    spec, runner, calls = _fixture(tmp_path)
    with pytest.raises(ValueError):
        collect_runtime_evidence(tmp_path, spec, runner=runner, image_id=override)
    assert not any(c[0] == 'run' for c in calls)


@pytest.mark.parametrize('overrides', [
    ['unknown=sha256:'+'a'*64], ['pytest-cpython312=bad'], ['=sha256:'+'a'*64],
    ['pytest-cpython312='], ['pytest-cpython312=sha256:'+'a'*64]*2,
    ['node-test-node22=sha256:'+'a'*64],
])
def test_phase_a_cli_validates_all_overrides_before_docker_or_writes(tmp_path, monkeypatch, overrides):
    def forbidden(*args, **kwargs): pytest.fail('invalid override reached Docker/write')
    monkeypatch.setattr(rights, 'docker_runner', forbidden)
    monkeypatch.setattr(rights, 'write_rights_evidence', forbidden)
    with pytest.raises(SystemExit):
        rights.main(['--root', str(tmp_path), '--write', '--row', 'pytest-cpython312',
                     *[arg for value in overrides for arg in ('--image-id',value)]])


@pytest.mark.parametrize('rootfs', [None, {}, {'Type':'other','Layers':[]},
    {'Type':'layers','Layers':['bad']}, {'Type':'layers','Layers':'not-a-list'}])
def test_phase_a_requires_rootfs_metadata(rootfs):
    raw=json.dumps([dict(Id='sha256:'+'a'*64,Architecture='amd64',Os='linux',Created='now',RootFS=rootfs)]).encode()
    with pytest.raises(ValueError): rights._image_metadata(raw, 'image')


@pytest.mark.parametrize('name', ['a\nspoof','a\x7f','a\udcff'])
def test_phase_a_tar_rejects_controls_and_non_utf8_names(name):
    with pytest.raises(ValueError, match='unsafe'): evidence_files_from_tar(_tar(((name,b'x'),)))


def test_phase_a_metadata_repeated_folded_headers_and_pep639(tmp_path):
    base='/usr/local/lib/python3.12/site-packages/demo.dist-info'
    metadata=b'Metadata-Version: 2.4\nLicense-File: LICENSE\nLicense-File:\n AUTHORS.txt\nLicense-File: MISSING\n\nbody\n'
    candidates={base+'/LICENSE':b'terms', base+'/licenses/AUTHORS.txt':b'authors'}
    vendor='/usr/local/lib/python3.12/site-packages/pip/_vendor/vendor.txt'
    spec, runner, calls=_fixture(tmp_path,'pytest-cpython312',((base[1:]+'/METADATA',metadata),),
        inputs=((vendor,b'packaging==1\n    nested==2\n'),),candidates=candidates)
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    refs=[r for r in evidence.references if r.reference_kind=='metadata-license-file']
    assert [r.status for r in refs]==['embedded','embedded','unresolved-missing']
    assert refs[1].raw_reference=='\n AUTHORS.txt'
    assert metadata[refs[1].byte_start:refs[1].byte_end]==b'\n AUTHORS.txt'
    assert refs[1].target_path==base+'/licenses/AUTHORS.txt'
    assert dict((f.path,f.content) for f in evidence.input_files)[vendor]==b'packaging==1\n    nested==2\n'
    assert len(evidence.file_facts)==2
    _parse_bundle(render_rights_evidence(evidence))


@pytest.mark.parametrize('declaration',['../escape','/absolute','a//b','a/./b','a/*','a\x7f'])
def test_phase_a_unsafe_declaration_fails_before_candidate_probe(tmp_path,declaration):
    path='usr/local/lib/python3.12/site-packages/demo.dist-info/METADATA'
    spec,runner,calls=_fixture(tmp_path,'pytest-cpython312',((path,('License-File: '+declaration+'\n').encode()),))
    with pytest.raises(ValueError): collect_runtime_evidence(tmp_path,spec,runner=runner)
    assert not any(getattr(rights,'_FACT_COMMAND','unimplemented') in c for c in calls)


def test_phase_a_two_declared_candidates_are_embedded_but_not_selected(tmp_path):
    base='/usr/local/lib/python3.12/site-packages/demo.dist-info'
    vendor='/usr/local/lib/python3.12/site-packages/pip/_vendor/vendor.txt'
    spec,runner,_=_fixture(tmp_path,'pytest-cpython312',((base[1:]+'/METADATA',b'License-File: LICENSE\n'),),
        inputs=((vendor,b'list'),),candidates={base+'/LICENSE':b'same',base+'/licenses/LICENSE':b'same'})
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    ref=next(r for r in evidence.references if r.reference_kind=='metadata-license-file')
    assert ref.status=='unresolved-ambiguous' and ref.target_path is None
    assert {f.path for f in evidence.license_files} >= {base+'/LICENSE',base+'/licenses/LICENSE'}


def test_phase_a_reference_spans_punctuation_ambiguity_and_non_utf8():
    source=EvidenceFile('/doc/LICENSE',b'\xc3\xa9 See /usr/share/common-licenses/GPL. /usr/share/common-licenses/GFDL-3;\n'
        b'/uncollected/x https://example.test/LICENSE AUTHORS NOTICE /literal/name.\n')
    files=(source,EvidenceFile('/usr/share/common-licenses/GPL',b'GPL'),
        EvidenceFile('/doc/AUTHORS',b'author'),EvidenceFile('/other/NOTICE',b'notice'),
        EvidenceFile('/literal/name',b'a'),EvidenceFile('/literal/name.',b'b'),EvidenceFile('/bad/LICENSE',b'\xff'))
    refs=rights._scan_references(files,absent={'/usr/share/common-licenses/GFDL-3'})
    by_raw={r.raw_reference:r for r in refs if r.reference_kind!='unparsed-source'}
    assert by_raw['/usr/share/common-licenses/GPL.'].target_path=='/usr/share/common-licenses/GPL'
    assert by_raw['/usr/share/common-licenses/GFDL-3;'].status=='unresolved-missing'
    assert by_raw['/uncollected/x'].status=='unresolved-unsupported'
    assert by_raw['https://example.test/LICENSE'].status=='unresolved-external'
    assert by_raw['AUTHORS'].target_path=='/doc/AUTHORS'
    assert by_raw['NOTICE'].status=='unresolved-unsupported'
    assert by_raw['/literal/name.'].status=='unresolved-ambiguous'
    assert any(r.status=='unresolved-non-utf8' for r in refs)
    for r in refs:
        if r.reference_kind!='unparsed-source':
            assert source.content[r.byte_start:r.byte_end].decode()==r.raw_reference


@pytest.mark.parametrize('same',[True,False])
def test_phase_a_installed_perl_lock_is_compared_not_substituted(tmp_path,same):
    repo=tmp_path/'images/perl/packages.lock'; repo.parent.mkdir(parents=True)
    repo.write_bytes(b'image lock' if same else b'repository lock')
    spec,runner,_=_fixture(tmp_path,'perl-tap-540',inputs=(('/opt/corsair/packages.lock',b'image lock'),))
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    assert evidence.input_files==(EvidenceFile('/opt/corsair/packages.lock',b'image lock'),)
    assert evidence.input_comparisons[0].byte_identical is same
    assert evidence.input_comparisons[0].repository_sha256==hashlib.sha256(repo.read_bytes()).hexdigest()
    assert ('/opt/corsair/packages.lock',hashlib.sha256(b'image lock').hexdigest()) in evidence.artifacts
    assert same or any('mismatch' in b for b in evidence.remaining_blockers)


def test_phase_a_repository_component_symlinks_rejected(tmp_path):
    inside=tmp_path/'real'; inside.mkdir(); (inside/'Dockerfile').write_bytes(b'x')
    (tmp_path/'images').symlink_to(inside,target_is_directory=True)
    with pytest.raises(ValueError): rights._repository_bytes(tmp_path,'images/Dockerfile')


def _parse_bundle(raw):
    """Independent length framing parser: content may contain every marker."""
    stream=io.BytesIO(raw); header={}; files={}; kinds={}
    while True:
        line=stream.readline()
        if line==b'\n': break
        assert line
        if line.startswith(b'  - '):
            header[key].append(json.loads(line[4:]))
        elif line.startswith(b'    sha256: '):
            continue  # legacy artifact pair layout
        else:
            key,_,value=line.decode().rstrip('\n').partition(':')
            if key=='artifacts':
                # Artifacts retain their legacy two-line objects.
                while True:
                    position=stream.tell(); candidate=stream.readline()
                    if not candidate.startswith(b'  - name: '): stream.seek(position); break
                    json.loads(candidate[len(b'  - name: '):]); assert stream.readline().startswith(b'    sha256: ')
                continue
            value=value.strip()
            header[key]=json.loads(value) if value.startswith('"') else value if value else []
    while stream.tell()<len(raw):
        marker=stream.readline(); assert marker in (b'--- BEGIN LICENSE FILE ---\n',b'--- BEGIN INPUT FILE ---\n')
        kind='INPUT' if b'INPUT' in marker else 'LICENSE'
        assert stream.readline()==b'origin: image\n'
        path=json.loads(stream.readline()[6:]); digest=stream.readline()[8:].strip().decode()
        size=int(stream.readline()[6:]); assert stream.readline()==b'content:\n'
        content=stream.read(size); assert len(content)==size
        if not content.endswith(b'\n'): assert stream.read(1)==b'\n'
        assert stream.readline()==f'--- END {kind} FILE ---\n'.encode()
        assert stream.readline()==b'\n'
        assert path not in files; assert hashlib.sha256(content).hexdigest()==digest
        files[path]=(content,digest); kinds[path]=kind
    for ref in header['references']:
        content,digest=files[ref['source_path']]; assert digest==ref['source_sha256']
        if ref['reference_kind']!='unparsed-source':
            assert content[ref['byte_start']:ref['byte_end']].decode()==ref['raw_reference']
        if ref['status']=='embedded': assert files[ref['target_path']][1]==ref['target_sha256']
        else: assert ref['target_path'] is None and ref['target_sha256'] is None
    for fact in header['file_facts']:
        assert files[fact['path']][1]==fact['sha256']
        if fact['resolved_path'] in files: assert files[fact['resolved_path']][1]==fact['sha256']
    for comparison in header['input_comparisons']:
        assert kinds[comparison['image_path']]=='INPUT'
        assert files[comparison['image_path']][1]==comparison['image_sha256']
        assert comparison['byte_identical']==(comparison['image_sha256']==comparison['repository_sha256'])
    return header,files


def test_phase_a_length_framing_and_invalid_edges(tmp_path):
    spec,runner,_=_fixture(tmp_path)
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    content=b'--- END INPUT FILE ---\n\xff\x00no newline'
    evidence=replace(evidence,input_files=(EvidenceFile('/input',content),))
    assert _parse_bundle(render_rights_evidence(evidence))[1]['/input'][0]==content
    with pytest.raises(ValueError):
        render_rights_evidence(replace(evidence,input_files=evidence.license_files))
    fact=rights.ImageFileFact('/missing','/missing','regular',None,'a'*64)
    with pytest.raises(ValueError): render_rights_evidence(replace(evidence,file_facts=(fact,)))
    file=evidence.license_files[0]
    ref=rights.EvidenceReference(file.path,hashlib.sha256(file.content).hexdigest(),0,4,'WRONG',
        'ancillary-name',None,(),'unresolved-unsupported',None,None,'outside-phase-a-collection')
    with pytest.raises(ValueError): render_rights_evidence(replace(evidence,references=(ref,)))


def test_phase_a_combined_limits_and_duplicate_records(tmp_path,monkeypatch):
    spec,runner,_=_fixture(tmp_path); evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    monkeypatch.setattr(rights,'_MAX_EVIDENCE_TOTAL',20)
    with pytest.raises(ValueError): render_rights_evidence(replace(evidence,input_files=(EvidenceFile('/input',b'x'*19),)))


def test_phase_a_checked_in_bundles_parse_offline():
    for spec in RUNTIME_SPECS:
        header,files=_parse_bundle((ROOT/'benchmarks/dataset/evidence/runtime'/spec.runtime_row/'RIGHTS-EVIDENCE.txt').read_bytes())
        assert header['schema']=='corsair-runtime-rights-evidence/2'
        assert header['review_status']=='candidate-evidence-unreviewed'
        assert header['image_id']==FIXED_IDS[spec.runtime_row]
        assert header['remaining_blockers']
        assert '/usr/share/common-licenses/Artistic' in files


@pytest.mark.docker
@pytest.mark.parametrize('spec',RUNTIME_SPECS,ids=lambda spec:spec.runtime_row)
def test_phase_a_current_images(spec):
    if os.environ.get('CORSAIR_RUNTIME_EVIDENCE_INTEGRATION')!='1': pytest.skip('opt in to fixed current-image acquisition')
    evidence=collect_runtime_evidence(ROOT,spec,runner=rights.docker_runner,image_id=FIXED_IDS[spec.runtime_row])
    header,files=_parse_bundle(render_rights_evidence(evidence))
    assert all('/usr/share/common-licenses/'+name in files
               for name in ('GPL-1','GFDL-1.2','LGPL-2','Artistic'))
    for alias,target in [('GPL','GPL-3'),('LGPL','LGPL-3'),('GFDL','GFDL-1.3')]:
        fact=next(f for f in evidence.file_facts if f.path=='/usr/share/common-licenses/'+alias)
        assert fact.kind=='symlink' and fact.link_target==target
        assert fact.resolved_path=='/usr/share/common-licenses/'+target
    if spec.runtime_row=='pytest-cpython312':
        assert any(r.reference_kind=='metadata-license-file' and r.target_path and r.target_path.endswith('/AUTHORS.txt') for r in evidence.references)
        assert any(f.path.endswith('/pip/_vendor/vendor.txt') for f in evidence.input_files)
    if spec.runtime_row=='perl-tap-540':
        assert evidence.input_comparisons[0].image_sha256=='a53f3bf76cce884fd7088c133b0c438d04940e4c6317d4b693f314f5d3be1cc3'
        assert evidence.input_comparisons[0].byte_identical
    if spec.runtime_row=='node-test-node22':
        assert any(o.startswith('sqlite_version=') for o in evidence.observations)
        assert any('inherited' in b for b in evidence.remaining_blockers)
    assert render_rights_evidence(evidence)==(ROOT/'benchmarks/dataset/evidence/runtime'/spec.runtime_row/'RIGHTS-EVIDENCE.txt').read_bytes()


def test_phase_a_cli_accepts_valid_override_and_passes_it_to_collection(tmp_path,monkeypatch):
    spec,runner,_=_fixture(tmp_path)
    specimen=collect_runtime_evidence(tmp_path,spec,runner=runner)
    seen=[]
    def collect(root,spec,*,runner,image_id=None):
        seen.append((spec.runtime_row,image_id))
        return replace(specimen,runtime_row=spec.runtime_row)
    monkeypatch.setattr(rights,'collect_runtime_evidence',collect)
    assert rights.main(['--root',str(tmp_path),'--write','--row','pytest-cpython312',
        '--image-id','pytest-cpython312=sha256:'+'a'*64])==0
    assert seen==[('pytest-cpython312','sha256:'+'a'*64)]


def test_phase_a_node_dangling_launcher_and_sqlite_are_facts(tmp_path):
    spec,base,calls=_fixture(tmp_path,'node-test-node22')
    def runner(args):
        if getattr(rights,'_NODE_SQLITE_COMMAND','unimplemented') in args:
            return b'{"sqlite_version":"3.50.4","sqlite_source_id":"2025-07-30 abc"}'
        if getattr(rights,'_NODE_PATH_COMMAND','unimplemented') in args:
            return b'path:/usr/local/bin/npm=present\nlauncher:npm=absent\n'
        return base(args)
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    assert 'sqlite_version=3.50.4' in evidence.observations
    assert 'sqlite_source_id=2025-07-30 abc' in evidence.observations
    assert 'path:/usr/local/bin/npm=present' in evidence.observations
    assert any('present' in b and '/usr/local/bin/npm' in b for b in evidence.remaining_blockers)
    assert any('inherited' in b for b in evidence.remaining_blockers)


def test_phase_a_folded_value_preserves_unfolded_whitespace():
    source=EvidenceFile('/demo.dist-info/METADATA',b'License-File: legal/\n COPYING\n')
    declarations=rights._metadata_declarations((source,))
    assert declarations[0][3]=='legal/\n COPYING'
    assert declarations[0][4]==('/demo.dist-info/legal/ COPYING','/demo.dist-info/licenses/legal/ COPYING')


def test_phase_a_non_utf8_record_has_verifiable_empty_reference_span():
    source=EvidenceFile('/LICENSE',b'\xff')
    ref=rights._scan_references((source,))[0]
    assert ref.status=='unresolved-non-utf8'
    assert source.content[ref.byte_start:ref.byte_end]==ref.raw_reference.encode()==b''


def test_phase_a_renderer_sorts_records_and_rejects_duplicate_keys(tmp_path):
    spec,runner,_=_fixture(tmp_path)
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    a=EvidenceFile('/a/LICENSE',b'/b/LICENSE'); b=EvidenceFile('/b/LICENSE',b'terms')
    fact=rights.ImageFileFact(a.path,a.path,'regular',None,hashlib.sha256(a.content).hexdigest())
    refs=rights._scan_references((a,b))
    evidence=replace(evidence,license_files=(a,b),file_facts=(fact,),references=refs,
        input_files=(EvidenceFile('/z/input',b'z'),EvidenceFile('/a/input',b'a')),
        observations=('z','a','z'),remaining_blockers=('z','a','z'))
    shuffled=replace(evidence,license_files=tuple(reversed(evidence.license_files)),
        input_files=tuple(reversed(evidence.input_files)),references=tuple(reversed(evidence.references)),
        observations=('a','z'),remaining_blockers=('a','z'))
    assert render_rights_evidence(evidence)==render_rights_evidence(shuffled)
    for kwargs in (dict(file_facts=(fact,fact)),dict(references=refs+refs)):
        with pytest.raises(ValueError,match='duplicate'): render_rights_evidence(replace(evidence,**kwargs))
    with pytest.raises(ValueError): render_rights_evidence(replace(evidence,references=(replace(refs[0],target_sha256='f'*64),)))


def test_phase_a_late_acquisition_failure_leaves_bundle_untouched(tmp_path,monkeypatch):
    spec,runner,_=_fixture(tmp_path)
    evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    destination=write_rights_evidence(tmp_path,evidence); before=destination.read_bytes()
    def fail(args):
        if args[-1]=='artifacts': raise RuntimeError('late probe failure')
        return runner(args)
    monkeypatch.setattr(rights,'RUNTIME_SPECS',(spec,)); monkeypatch.setattr(rights,'docker_runner',fail)
    with pytest.raises(SystemExit): rights.main(['--root',str(tmp_path),'--write'])
    assert destination.read_bytes()==before


def test_phase_a_tar_rejects_duplicate_hardlink_and_aggregate_overflow(monkeypatch):
    with pytest.raises(ValueError): evidence_files_from_tar(_tar((('a',b'1'),('a',b'2'))))
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as archive:
        member=tarfile.TarInfo('a'); member.type=tarfile.LNKTYPE; member.linkname='b'; archive.addfile(member)
    with pytest.raises(ValueError): evidence_files_from_tar(output.getvalue())
    monkeypatch.setattr(rights,'_MAX_EVIDENCE_TOTAL',5)
    with pytest.raises(ValueError): evidence_files_from_tar(_tar((('a',b'123'),('b',b'456'))))


def test_phase_a_file_probe_keeps_raw_links_and_rejects_invalid_facts():
    digest=hashlib.sha256(b'bytes').hexdigest()
    raw=('\0'.join(('/alias','present','/real','symlink','../real\nopaque',digest))+'\0').encode()
    facts,absent=rights._file_facts(raw,('/alias',))
    assert facts[0].link_target=='../real\nopaque' and not absent
    for invalid in (raw+raw, raw.replace(b'/real\0symlink',b'/../escape\0symlink'),
                    raw.replace(digest.encode(),b'not-a-digest'), b'/alias\0absent\0x\0\0\0\0'):
        with pytest.raises(ValueError): rights._file_facts(invalid,('/alias',))


def test_phase_a_docker_runner_bounds_stdout_and_stderr(monkeypatch):
    import subprocess
    import sys
    real_popen=subprocess.Popen
    monkeypatch.setattr(rights,'_MAX_EVIDENCE_TOTAL',1024)
    def producing(*args,**kwargs):
        return real_popen([sys.executable,'-c','import sys; sys.stderr.write("x"*2048); sys.stdout.write("ok")'],**kwargs)
    monkeypatch.setattr(rights.subprocess,'Popen',producing)
    with pytest.raises(ValueError,match='oversized'): rights.docker_runner(('image','inspect','ignored'))


def test_phase_a_external_reference_count_cannot_bypass_budget(monkeypatch):
    monkeypatch.setattr(rights,'_MAX_EVIDENCE_TOTAL',256)
    source=EvidenceFile('/LICENSE',b'https://a.test https://b.test https://c.test')
    with pytest.raises(ValueError,match='oversized'): rights._scan_references((source,))


def test_phase_a_fixed_file_probe_dereferences_links_and_rejects_loops(tmp_path):
    import subprocess
    target=tmp_path/'real'; target.write_bytes(b'bytes')
    link=tmp_path/'alias'; link.symlink_to('real')
    args=('sh','-c',rights._FACT_COMMAND,'--',str(link),str(target),str(tmp_path/'absent'))
    completed=subprocess.run(args,check=True,capture_output=True)
    facts,absent=rights._file_facts(completed.stdout,args[4:])
    assert facts[0].kind=='symlink' and facts[0].link_target=='real'
    assert facts[0].resolved_path==str(target) and facts[0].sha256==facts[1].sha256
    assert absent=={str(tmp_path/'absent')}
    link.unlink(); link.symlink_to('alias')
    assert subprocess.run(('sh','-c',rights._FACT_COMMAND,'--',str(link)),capture_output=True).returncode!=0
    link.unlink(); link.symlink_to('.')
    assert subprocess.run(('sh','-c',rights._FACT_COMMAND,'--',str(link)),capture_output=True).returncode!=0


def test_phase_a_matching_curly_quotes_and_backticks_preserve_raw_span():
    source=EvidenceFile('/LICENSE','See ‘/usr/share/common-licenses/GPL-2’. and `/usr/share/common-licenses/GPL-2`.'.encode())
    target=EvidenceFile('/usr/share/common-licenses/GPL-2',b'terms')
    refs=rights._scan_references((source,target))
    assert [r.raw_reference for r in refs]==['/usr/share/common-licenses/GPL-2’.','/usr/share/common-licenses/GPL-2`.']
    assert all(r.target_path==target.path and r.status=='embedded' for r in refs)


def test_phase_a_bare_ancillary_absence_is_unsupported_not_a_declaration():
    source=EvidenceFile('/doc/LICENSE',b'NOTICE')
    ref=rights._scan_references((source,),absent={'/doc/NOTICE'})[0]
    assert ref.status=='unresolved-unsupported'


def test_phase_a_same_source_span_cannot_assert_conflicting_candidate_records(tmp_path):
    spec,runner,_=_fixture(tmp_path); evidence=collect_runtime_evidence(tmp_path,spec,runner=runner)
    source=EvidenceFile('/LICENSE',b'/target'); target=EvidenceFile('/target',b'terms')
    ref=rights._scan_references((source,target))[0]
    other=replace(ref,candidate_paths=('/other','/target'))
    with pytest.raises(ValueError,match='duplicate'):
        render_rights_evidence(replace(evidence,license_files=(source,target),references=(ref,other)))


def test_phase_a_node_path_program_counts_a_dangling_link_as_present(tmp_path):
    import subprocess
    directory=tmp_path/'usr/local/bin'; directory.mkdir(parents=True)
    (directory/'npm').symlink_to('removed-npm')
    # Relocate only the fixed path prefix so the actual probe program can run
    # against a disposable filesystem fixture without touching host launchers.
    command=rights._NODE_PATH_COMMAND.replace('/usr/local/',str(tmp_path)+'/usr/local/')
    result=subprocess.run(('/bin/sh','-c',command),env={'PATH':str(directory)},check=True,capture_output=True)
    assert f'path:{directory}/npm=present\n'.encode() in result.stdout
    assert b'launcher:npm=absent\n' in result.stdout
