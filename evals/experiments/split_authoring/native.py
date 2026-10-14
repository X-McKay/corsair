"""Pilot fixture execution via existing Docker workspace and native runner ports.

This is explicit post-draft execution, never part of the isolated host agent eval.
The independent source-only review must already be frozen. No generated code runs
on the host, and native outcomes are never fed back into the drafting experiment.
"""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from corsair.adapters.docker_image import DockerCase, WORK, docker
from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.pytest_runner import PytestRunner, PytestRunnerConfig
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun
from .cases import load_cases

FIXTURE = Path(__file__).resolve().parents[3] / 'benchmarks/fixtures/sql-query-construction'
IMAGE = 'sha256:68f08d0e933760a96e97ccafb3604a11ebddd0779e04c355f3a552dcf332832b'
IDS = ('test_control.py::test_benign_control',
       'test_exploit.py::test_security_preserves_query_structure')
COMMAND = ('python', '-m', 'pytest', '-c', '/dev/null', '--noconftest',
           '--rootdir=.', '--import-mode=importlib', '-p', 'no:cacheprovider')


def sources():
    return {name: (FIXTURE / name / 'queries.py').read_bytes() for name in ('unsafe', 'safe')}


def source_inventories():
    """Complete captured input trees, cross-checked against the fixture source."""
    inventories = {}
    for case, name in zip(load_cases(2), ("unsafe", "safe"), strict=True):
        files = {file["path"]: file["content"].encode() for file in case["inputs"]["source_files"]}
        if files["queries.py"] != sources()[name]:
            raise ValueError("captured source differs from fixture")
        inventories[name] = files
    return inventories


def inventory_hashes():
    return {name: {path: sha256(content).hexdigest() for path, content in files.items()}
            for name, files in source_inventories().items()}


def limited_docker(*args, **kwargs):
    if args[0] == 'run':
        args = (args[0], '--read-only', '--pids-limit=64', '--memory=256m', '--cpus=1',
                '--tmpfs', '/tmp:rw,nosuid,size=64m', *args[1:])
    return docker(*args, **kwargs)


def execute_pair(patch: ApprovedPatch, review: dict, destination: Path):
    """Execute both probes unchanged on both reviewed fixtures, after bound review.

    `review` is operator-retained independent review, not a field accepted from an
    author. Native reports establish execution/sensitivity, not semantic validity.
    """
    source_bytes = sources()
    inventories = source_inventories()
    all_hashes = inventory_hashes()
    hashes = {name: sha256(content).hexdigest() for name, content in source_bytes.items()}
    paths = {test_id.split('::')[0] for test_id in IDS}
    if set(item.path for item in patch.files) != paths:
        raise ValueError('pilot requires the two operator-owned probe files')
    if review.get('status') != 'supported' or review.get('patch_sha256') != patch.sha256 or review.get('sources') != hashes or review.get('source_inventory') != all_hashes:
        raise ValueError('independent supported review must bind this patch and both captured sources')
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'pre-execution-review.json').write_text(json.dumps(review, indent=2))
    store_root = destination / 'objects'
    store_root.mkdir(mode=0o700)
    report = {'image': IMAGE, 'patch_sha256': patch.sha256, 'source_sha256': hashes, 'source_inventory': all_hashes,
              'scope': 'isolated fixture query construction; no database-engine or OpenShell qualification',
              'runs': {}}
    with LocalArtifacts(store_root, max_bytes=1024 * 1024) as store:
        for name, content in source_bytes.items():
            work = destination / name
            tree = work / 'source'
            tree.mkdir(parents=True)
            for path, captured in inventories[name].items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(captured)
            with DockerCase(IMAGE, tree, hashes[name], 60, kind='split-authoring-pilot',
                    docker=limited_docker, env=('PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', 'PYTHONPATH=.'),
                    evidence=work) as sandbox:
                runner = PytestRunner(sandbox, sandbox, store,
                    PytestRunnerConfig(COMMAND, '.corsair-junit.xml', WORK))
                outcome = runner.run(patch, control_test_id=IDS[0], security_test_id=IDS[1],
                    discovery_command=COMMAND + ('--collect-only', '-q'), operation=uuid4())
            report['runs'][name] = {
                'native': TypeAdapter(NativeTestRun).dump_python(outcome, mode='json'),
                'container_cleanup': sandbox.cleanup,
            }
            (destination / 'report.json').write_text(json.dumps(report, indent=2))
    return report
