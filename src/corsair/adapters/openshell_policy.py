"""Pinned native `openshell policy set --wait` on the original sandbox, observed loaded (SPEC-0070).

The curated SDK has no policy methods, so this runs the pinned CLI as the SPEC-0006 qualification does. No
retries: anything but an observed loaded revision of the same document on the same sandbox id is a failure.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import UUID

import yaml

from corsair.adapters.receipts import ReceiptDirectory
from corsair.ports.sandbox import PolicyError, PolicyReceipt, SandboxHandle


def policy_sha256(policy: dict) -> str:
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


# The fields of an OpenShell policy document, as the SPEC-0006 policy gate compares them.
POLICY_FIELDS = frozenset({'version', 'landlock', 'filesystem_policy', 'process', 'network_policies'})


def loads_requested(native: dict, requested: dict) -> bool:
    """Whether the gateway's effective policy is the requested document: every field the document sets is equal,
    an absent `network_policies` is empty, and the gateway adds nothing but its own `process` defaults."""
    if not set(native) <= POLICY_FIELDS or not set(requested) <= POLICY_FIELDS:
        return False
    expected = {'network_policies': {}} | requested
    return all(native.get(key, {} if key == 'network_policies' else None) == value for key, value in expected.items())


class CliPolicy:
    def __init__(self, binary: Path, binary_sha256: str, *, gateway: str, env: dict[str, str],
                 timeout_seconds: int, receipts: Path):
        if not binary.is_absolute() or not gateway or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
            raise ValueError('Absolute pinned binary, gateway name and bounded timeout required')
        if any(type(k) is not str or type(v) is not str for k, v in env.items()):
            raise ValueError('Explicit string environment required')
        self._binary, self._sha256, self._gateway = binary, binary_sha256, gateway
        self._env, self._timeout = dict(env), timeout_seconds
        self._journal = ReceiptDirectory(receipts)

    def __enter__(self): return self
    def __exit__(self, *args): self._journal.close()

    def _cli(self, handle: SandboxHandle, *args: str) -> subprocess.CompletedProcess:
        argv = [str(self._binary), '--gateway', self._gateway, '--workspace', handle.workspace, *args]
        done = subprocess.run(argv, capture_output=True, timeout=self._timeout, env=self._env)
        if done.returncode != 0:
            raise RuntimeError(f'{" ".join(args[:2])} exit {done.returncode}: '
                               + done.stderr[-1024:].decode('utf-8', 'replace'))
        return done

    def _observe(self, handle: SandboxHandle, policy: dict) -> tuple[int, str]:
        actual = json.loads(self._cli(handle, 'sandbox', 'get', handle.name, '-o', 'json').stdout)
        full = json.loads(self._cli(handle, 'policy', 'get', handle.name, '--full', '-o', 'json').stdout)
        revision = json.loads(self._cli(handle, 'policy', 'get', handle.name, '--rev', str(full['version']),
                                        '--full', '-o', 'json').stdout)
        admission = actual['configuration_admission']
        if (actual['id'] != handle.id or actual['policy_source'] != 'sandbox' or admission['state'] != 'accepted'
                or full['hash'] != admission['policy_hash'] or revision['status'] != 'loaded'
                or revision['hash'] != full['hash']):
            raise ValueError('policy revision not observed loaded on the original sandbox')
        if not (loads_requested(actual['policy'], policy) and loads_requested(full['policy'], policy)):
            raise ValueError('loaded policy differs from the requested document')
        return int(full['version']), str(full['hash'])

    def apply(self, handle: SandboxHandle, policy: dict, phase: str, operation: UUID) -> PolicyReceipt:
        if not isinstance(operation, UUID):
            raise ValueError('Operation must be a UUID')
        receipt = PolicyReceipt(str(operation), handle, phase, policy_sha256(policy), 'not_dispatched', False, 0.0)
        try:
            self._journal.write(operation, 'intent', dict(asdict(receipt), policy=policy,
                                started_at=datetime.now(timezone.utc).isoformat()))
        except Exception as error:
            raise PolicyError(replace(receipt, storage_error=f'{type(error).__name__}: {error}')) from error
        started, failure = time.monotonic(), None
        try:
            if hashlib.sha256(self._binary.read_bytes()).hexdigest() != self._sha256:
                raise ValueError('native CLI binary differs from its pin')
            with tempfile.TemporaryDirectory() as scratch:
                path = Path(scratch) / 'policy.yaml'
                path.write_text(yaml.safe_dump(policy))
                receipt = replace(receipt, delivery='unknown')
                self._cli(handle, 'policy', 'set', handle.name, '--policy', str(path), '--wait',
                          '--timeout', str(self._timeout))
            receipt = replace(receipt, delivery='acknowledged')
            version, native_hash = self._observe(handle, policy)
            receipt = replace(receipt, loaded=True, native_version=version, native_hash=native_hash)
        except Exception as error:
            failure = error
            receipt = replace(receipt, error_detail=f'{type(error).__name__}: {error}'[:2048])
        receipt = replace(receipt, elapsed_seconds=time.monotonic() - started)
        try:
            self._journal.write(operation, 'result', asdict(receipt))
        except Exception as error:
            receipt = replace(receipt, loaded=False, storage_error=f'{type(error).__name__}: {error}')
            failure = failure or error
        if failure is not None:
            raise PolicyError(receipt) from failure
        return receipt
