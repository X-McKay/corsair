"""Meaningful guards for the new native-stream evidence budget translation."""
import base64
import hashlib
import pytest
from tests.qualification.recovery_client import bounded_chunk


@pytest.mark.parametrize('data,budget',[(b'abc',5),(bytes(range(256))*32,4096),(b'',0),(b'x',0)])
def test_retained_output_respects_budget_and_keeps_observed_identity(data,budget):
    record,overflow=bounded_chunk(data,budget)
    assert base64.b64decode(record['base64'])==data[:budget]
    assert record['retained_bytes']==min(len(data),budget)
    assert record['observed_bytes']==len(data)
    assert record['sha256']==hashlib.sha256(data).hexdigest()
    assert overflow==(len(data)>budget)


def test_invalid_budget_cannot_admit_output():
    with pytest.raises(AssertionError):bounded_chunk(b'x',-1)


@pytest.mark.parametrize('memory',['512Mi','128Mi'])
def test_native_resource_request_roundtrip_uses_supported_limits_shape(memory):
    from google.protobuf.json_format import MessageToDict
    from openshell._proto import openshell_pb2
    from tests.qualification.test_recovery import recovery_spec
    spec = recovery_spec('example.invalid/fixed@sha256:'+'a'*64,memory)
    restored = openshell_pb2.SandboxSpec.FromString(spec.SerializeToString())
    actual = MessageToDict(restored,preserving_proto_field_name=True)
    assert actual['template']['resources']=={'limits':{'cpu':'1','memory':memory}}
    assert actual['policy']['landlock']['compatibility']=='hard_requirement'
    assert actual['command']==['/bin/sleep','600']
    assert actual['restart_policy']=='SANDBOX_RESTART_POLICY_NEVER'


def test_json_transport_paths_support_native_sdk_file_reads(tmp_path):
    import json
    from tests.qualification.recovery_client import native_tls
    paths={}
    for key in ('ca_path','cert_path','key_path'):
        path=tmp_path/key
        path.write_bytes(b'public-synthetic-transport-fixture')
        paths[key]=str(path)
    tls=native_tls(json.loads(json.dumps(paths)))
    assert all(getattr(tls,key).read_bytes()==b'public-synthetic-transport-fixture' for key in paths)


@pytest.mark.parametrize('native_exit',[74,124])
def test_synthetic_native_terminal_cannot_establish_remote_completion(native_exit):
    from openshell import ExecResult
    from tests.qualification.recovery_client import terminal_receipt
    result=terminal_receipt(ExecResult(exit_code=native_exit,stdout='é',stderr=''))
    assert result['delivery']=='acknowledged' and result['exit_code']==native_exit
    assert result['remote_completion']=='unknown'
    assert result['stdout_bytes']==2 and result['stdout_sha256']==hashlib.sha256('é'.encode()).hexdigest()
