"""SPEC-0064 guards on the reviewed Maven cache lists; the image build itself compares each list to a clean fetch."""
import re
import xml.etree.ElementTree as ET

import pytest

from tests.qualification.prepare_toolchains import BASES, SOURCE

JAVA = sorted(name for name in BASES if (SOURCE / name / 'pom.xml').exists())
LINE = re.compile(r'([0-9a-f]{64})  \./(\S+)')
POM = '{http://maven.apache.org/POM/4.0.0}'
# Pinned by the Dockerfile's preparation commands rather than by the fixture POM (SPEC-0041 discovery).
PREPARATION = ('org.apache.maven.plugins:maven-dependency-plugin:3.8.1', 'org.junit.platform:junit-platform-console-standalone:1.14.4')


def listed(name):
    rows = [LINE.fullmatch(line) for line in (SOURCE / name / 'm2.sha256').read_text().splitlines()]
    assert all(rows), 'Every line is "<sha256>  ./<repository path>", as sha256sum writes it'
    return {row[2]: row[1] for row in rows}, [row[2] for row in rows]


def jar(coordinate):
    group, artifact, version = coordinate.split(':')
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"


def test_every_java_image_has_a_list():
    assert JAVA == ['java', 'java8'] and all((SOURCE / name / 'm2.sha256').is_file() for name in JAVA)


@pytest.mark.parametrize('name', JAVA)
def test_list_is_sorted_unique_artifacts_only(name):
    hashes, paths = listed(name)
    assert paths == sorted(paths) and len(hashes) == len(paths)
    # Checksum sidecars and resolver bookkeeping are excluded by the build's inventory; an entry for one means drift.
    assert not [p for p in paths if p.startswith('.meta/') or p.endswith(('.sha1', '.md5', '.lastUpdated', '_remote.repositories', 'resolver-status.properties'))]


@pytest.mark.parametrize('name', JAVA)
def test_list_covers_the_fixture_and_discovery_pins(name):
    hashes, _ = listed(name)
    project = ET.parse(SOURCE / name / 'pom.xml').getroot()
    pinned = [':'.join(node.findtext(POM + key) for key in ('groupId', 'artifactId', 'version'))
              for node in project.iter() if node.tag in (POM + 'dependency', POM + 'plugin') and node.findtext(POM + 'version')]
    required = [c for c in pinned if not c.startswith('corsair.qualification:')] + list(PREPARATION)
    assert not [c for c in required if jar(c) not in hashes]
    # Surefire 3.6.0 runs JUnit 4 and 5 alike through its JUnit Platform provider.
    assert 'org/apache/maven/surefire/surefire-junit-platform/3.6.0/surefire-junit-platform-3.6.0.jar' in hashes
    launcher = (SOURCE / name / 'junit-launcher.sha256').read_text().split()[0]
    assert hashes[jar(PREPARATION[1])] == launcher
