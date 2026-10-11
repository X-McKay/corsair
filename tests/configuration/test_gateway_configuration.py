"""Offline guards protect the selected CLI and mandatory local gateway boundaries."""
import re
import yaml

from tests.qualification.support import ROOT, LOCK


def test_gateway_profile_keeps_auth_tls_and_kernel_requirements():
    cli = LOCK['openshell']['cli']
    assert LOCK['openshell']['version'] in cli['url']
    assert all(re.fullmatch('[0-9a-f]{64}', cli[key]) for key in ('sha256', 'binary_sha256'))
    values = yaml.safe_load((ROOT / 'deploy/openshell/values.yaml').read_text())
    assert values['agentSandbox']['preflight']['enabled'] is True
    assert values['server']['disableTls'] is False
    assert values['server']['auth']['allowUnauthenticatedUsers'] is False

    policy = yaml.safe_load((ROOT / 'policies/openshell/identity.yaml').read_text())
    assert policy['landlock']['compatibility'] == 'hard_requirement'
    assert policy['network_policies'] == {}


def test_private_transport_export_withholds_credential_bytes(tmp_path, monkeypatch):
    import base64
    import json
    from types import SimpleNamespace
    from tests.qualification.test_gateway import export_client

    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    private = tmp_path / 'private/mtls'
    secret = b'fixture-private-transport-material'
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=base64.b64encode(secret), stderr=b'private-diagnostic'))
    export_client(SimpleNamespace(argv=['kubectl'], evidence=evidence), private)
    for filename in ('ca.crt', 'tls.crt', 'tls.key'):
        assert (private / filename).read_bytes() == secret
        assert (private / filename).stat().st_mode & 0o777 == 0o600
        receipt = json.loads((evidence / ('private-export-' + filename + '.json')).read_text())
        assert receipt['credential_output_withheld'] is True and receipt['completion'] == 'completed'
        assert 'stdout' not in receipt and 'stderr' not in receipt
    assert not any('fixture-private' in file.read_text() or 'private-diagnostic' in file.read_text() for file in evidence.iterdir())
