"""Shared image-only case harness: a prepared toolchain image under Docker, no OpenShell, any framework's runner.

Each language module supplies its setup script (dependencies with network, no test body), the offline build that
`prepare` runs after copying the checkout, its mounts and environment, and the runner and config; this module owns
the guards (image config id, the commit's own blobs), the capability-dropped offline container standing in for the
workspace and execution ports, evidence and cleanup confirmation. It is image evidence, not sandbox qualification.
"""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.ports.test_runner import ApprovedPatch, PatchFile
from corsair.adapters import docker_image
# The image-only route lives in the adapter; these names stay importable for the language harnesses.
from corsair.adapters.docker_image import (HARDENED, SETUP_RECEIPT, WORK, DockerCase, docker, sha256, user,  # noqa: F401
                                           write_setup)


def commit_tree(checkout, destination, commit='HEAD'):
    try:
        return docker_image.commit_tree(checkout, destination, commit)
    except ValueError as error:
        raise SystemExit(str(error)) from error


def require_setup(directory, expected: dict) -> dict:
    try:
        return docker_image.require_setup(directory, expected)
    except docker_image.SetupMismatch as error:
        raise SystemExit(str(error)) from error

def head(checkout) -> str:
    return subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                          check=True).stdout.strip()


def require_image_id(parser: argparse.ArgumentParser, image: str) -> None:
    # Both phases must name the same content, so a tag that could move between them is refused.
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        parser.error('--image must be an image config id (sha256:<64 hex>), not a tag')


def plain(value):
    if dataclasses.is_dataclass(value):
        return {k: plain(v) for k, v in dataclasses.asdict(value).items()}
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, bytes):
        text = value.decode('utf-8', 'replace')
        return {'sha256': hashlib.sha256(value).hexdigest(), 'size': len(value), 'tail': text[-4000:]}
    return value


def drive(runner, case, config, patch, ids, evidence, summary):
    """One runner run in `case`, with the stored reports under the evidence directory; writes and returns run.json."""
    # LocalArtifacts opens an existing absolute root and never creates it.
    evidence = Path(evidence).resolve()
    (evidence / 'objects').mkdir(mode=0o700)
    with case, LocalArtifacts(evidence / 'objects', max_bytes=8 << 20) as store:
        clock = time.monotonic()
        result = runner(case, case, store, config).run(patch, control_test_id=ids[0], security_test_id=ids[1],
                                                       discovery_command=config.command, operation=uuid4())
        elapsed = round(time.monotonic() - clock, 3)
    summary = {**summary, 'ids': ids, 'patch_sha256': patch.sha256, 'elapsed_seconds': elapsed,
               'container_cleanup': case.cleanup, 'failure_layer': result.failure_layer, 'detail': result.detail,
               'cleanup': result.cleanup,
               'discovery': result.discovery and {'status': result.discovery.status, 'test_ids': result.discovery.test_ids},
               'cases': result.execution and [(c.test_id, c.outcome, c.failure and plain(c.failure))
                                             for c in result.execution.cases],
               'run': plain(result)}
    (evidence / 'run.json').write_text(json.dumps(summary, indent=2, default=str))
    return summary


def print_summary(summary):
    print(json.dumps({k: v for k, v in summary.items() if k != 'run'}, indent=2, default=str))


def tests_patch(path: str, tests_from) -> ApprovedPatch:
    """The unchanged test file at `path` from the tree `tests_from`, as the approved patch."""
    return ApprovedPatch((PatchFile(path, (Path(tests_from) / path).read_bytes()),), (path,))
