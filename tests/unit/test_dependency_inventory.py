"""SPEC-0026 realized inventory receipt parser and replay drift; offline only."""
import hashlib

import pytest

from corsair.nodes.dependency_inventory import compare_inventories, parse_inventory

IMAGE = 'sha256:'+'1'*64


def receipt(ecosystem, rows, image=IMAGE, count=None):
    lines = []
    for path, data in rows:
        hexpath = path.encode().hex()
        lines.append((hexpath, f'generated {hexpath}' if data is None else f'file {hashlib.sha256(data).hexdigest()} {len(data)} {hexpath}'))
    body = ''.join(line+'\n' for _, line in sorted(lines))
    return f'corsair-dependency-inventory v1 {ecosystem}\nimage {image}\n{body}end {len(rows) if count is None else count}\n'.encode()


JAVA = [('org/x/x/1/x-1.jar', b'jar'), ('org/x/x/1/x-1.pom', b'<pom/>'), ('org/x/x/1/_remote.repositories', None),
        ('org/x/x/maven-metadata-central.xml', None), ('org/x/x/1/x-1.jar.lastUpdated', None)]
NPM = [('node_modules/a/index.js', b'js'), ('node_modules/.package-lock.json', None)]
PY = [('lib/python3.12/site-packages/a/__init__.py', b''), ('lib/python3.12/site-packages/a-1.dist-info/RECORD', b'r'),
      ('lib/python3.12/site-packages/a-1.dist-info/INSTALLER', b'pip\n')]


@pytest.mark.parametrize('ecosystem,rows', [('java', JAVA), ('javascript', NPM), ('python', PY)])
def test_covered_ecosystems_parse_with_generated_paths_by_presence(ecosystem, rows):
    inventory = parse_inventory(receipt(ecosystem, rows), ecosystem, 16)
    assert inventory.image == IMAGE and len(inventory.files) + len(inventory.generated) == len(rows)
    assert set(inventory.generated) == {p for p, d in rows if d is None}
    assert dict(inventory.files)['node_modules/a/index.js' if ecosystem == 'javascript' else rows[0][0]].size == len(rows[0][1])


@pytest.mark.parametrize('stdout,ecosystem,reason', [
    (receipt('ruby', []), 'ruby', 'not yet covered'), (receipt('perl', []), 'perl', 'not yet covered'),
    (receipt('go', []), 'go', 'not yet covered'), (receipt('java', JAVA), 'python', 'header'),
    (receipt('java', JAVA, image='sha256:abc'), 'java', 'image digest'), (receipt('java', JAVA, image='latest'), 'java', 'image digest'),
    (receipt('java', JAVA).replace(b'file '+hashlib.sha256(b'jar').hexdigest().encode(), b'file -'), 'java', 'missing digest'),
    (receipt('java', JAVA, count=4), 'java', 'count'), (receipt('java', JAVA+JAVA[:1], count=6), 'java', 'duplicated'),
    (receipt('java', JAVA)[:-1], 'java', 'LF'), (receipt('java', JAVA)+b'extra\n', 'java', 'trailer'),
    (receipt('java', [('../escape.jar', b'x')]), 'java', 'Canonical'),
    (receipt('java', [('org/x/x/1/_remote.repositories', b'hashed')]), 'java', 'classification'),
    (receipt('java', [('org/x/x/1/x-1.jar', None)]), 'java', 'classification'),
    (receipt('javascript', [('node_modules/a/node_modules/.package-lock.json', None)]), 'javascript', 'classification'),
    (receipt('python', [('lib/a/__pycache__/m.cpython-312.pyc', b'pyc')]), 'python', 'Prevented'),
    (receipt('python', [('lib/a/m.pyc', None)]), 'python', 'Prevented'),
], ids=['ruby', 'perl', 'unknown', 'wrong-ecosystem', 'short-image', 'tag-image', 'missing-digest', 'count', 'duplicate',
        'unterminated', 'extra', 'path', 'generated-hashed', 'hashed-as-generated', 'nested-npm-lock', 'bytecode', 'bytecode-generated'])
def test_inventory_refusals(stdout, ecosystem, reason):
    with pytest.raises(ValueError, match=reason): parse_inventory(stdout, ecosystem, 8)


def test_oversize_inventory_refused_rather_than_truncated():
    assert len(parse_inventory(receipt('java', JAVA), 'java', 5).files) == 2
    with pytest.raises(ValueError, match='over bound'): parse_inventory(receipt('java', JAVA), 'java', 4)


def parse(rows, image=IMAGE): return parse_inventory(receipt('java', rows, image), 'java', 16)


def test_identical_inventories_have_no_drift_even_with_regenerated_bookkeeping():
    assert compare_inventories(parse(JAVA), parse(JAVA)).empty


def test_drift_reports_added_removed_changed_and_image():
    replay = [r for r in JAVA if r[0] != 'org/x/x/1/x-1.pom'] + [('org/y/y/2/y-2.jar', b'new'), ('org/y/y/maven-metadata-x.xml', None)]
    replay = [(p, b'other jar' if p.endswith('x-1.jar') else d) for p, d in replay]
    drift = compare_inventories(parse(JAVA), parse(replay, 'sha256:'+'2'*64))
    assert drift.image_changed and not drift.empty
    assert drift.added == ('org/y/y/2/y-2.jar', 'org/y/y/maven-metadata-x.xml')
    assert (drift.removed, drift.changed) == (('org/x/x/1/x-1.pom',), ('org/x/x/1/x-1.jar',))
    assert not compare_inventories(parse(JAVA), parse(JAVA, 'sha256:'+'2'*64)).empty
    with pytest.raises(ValueError): compare_inventories(parse(JAVA), parse_inventory(receipt('javascript', NPM), 'javascript', 4))
