"""Host execution confined to the reviewed, repository-owned SPEC-0018 bytes.

Model-authored test code is untrusted workload code and never runs on the host. This workspace
refuses every patch except the reviewed ``test_documents.py`` bytes before anything executes, so a
live author's tests reach no interpreter here; they need the OpenShell test workspace instead.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import PreparedWorkspace

FIXTURE = Path(__file__).resolve().parents[2] / 'benchmarks/fixtures/path-traversal'
REVIEWED_TEST = 'test_documents.py'
# Operator-owned pytest argv: no plugins, config or conftest from the workspace; scratch stays inside it.
PREFIX = ('env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', 'PYTHONDONTWRITEBYTECODE=1', 'PYTHONPATH=.', 'python3.12', '-m',
          'pytest', '-c', '/dev/null', '--rootdir', '.', '--noconftest', '--import-mode=importlib',
          '-p', 'no:cacheprovider', '--basetemp', 'scratch')
DISCOVER = PREFIX + ('--collect-only', '-q')


class ReviewedWorkspace:
    """Delivers only the reviewed SPEC-0018 test and one source variant into a private scratch directory."""
    def __init__(self, store, root, variant):
        self.store, self.root, self.variant = store, root, variant

    def prepare(self, patch, operation):
        reviewed = (FIXTURE / REVIEWED_TEST).read_bytes()
        if [(f.path, f.content) for f in patch.files] != [(REVIEWED_TEST, reviewed)]:
            raise PermissionError('host execution admits only the reviewed SPEC-0018 test bytes; '
                                  'other test code needs the sandbox test workspace')
        source = (FIXTURE / self.variant / 'documents.py').read_bytes()
        self.root.mkdir(mode=0o700)
        (self.root / 'documents.py').write_bytes(source)
        (self.root / REVIEWED_TEST).write_bytes(reviewed)
        handle = SandboxHandle(str(uuid4()), 'reviewed', 'local', 'tests', str(operation))
        return PreparedWorkspace(handle, self.store.put(source), self.store.put(reviewed), patch.sha256)

    def release(self, workspace, operation):
        shutil.rmtree(self.root)
        return 'unconfirmed' if self.root.exists() else 'confirmed'


class ReviewedLocalExecution:
    """Host execution, allowed solely because ReviewedWorkspace admits nothing but the reviewed fixture bytes."""
    def __init__(self, root):
        self.root = root

    def execute(self, handle, command, operation):
        argv = [sys.executable if token == 'python3.12' else token for token in command]
        started = time.monotonic()
        done = subprocess.run(argv, cwd=self.root, env={'PATH': os.environ['PATH']}, capture_output=True, timeout=60)
        return ExecutionReceipt(str(operation), handle, 'local', time.monotonic()-started, 'acknowledged',
                                'terminal_observed', 'terminal', stdout=done.stdout, stderr=done.stderr,
                                native_exit=done.returncode, worker_cleanup='confirmed')
