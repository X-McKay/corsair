"""Native 1F destructive qualification of fixed synthetic processes only."""
from contextlib import contextmanager, ExitStack
import base64
import hashlib
import json
import subprocess
import sys
import time
import uuid

import pytest
import yaml
from openshell import SandboxClient, TlsConfig, DeletionOutcome
from openshell._proto import openshell_pb2

from tests.qualification.support import ROOT
from tests.qualification.gateway import gateway, inspect_identity, workspace_storage, wait_resource_absent
from tests.qualification.test_lifecycle import SdkReceipts, inert_spec
from tests.qualification.test_policy import require_network, observe_policy, global_policy_observation
from tests.qualification.prepare_toolchains import image_receipt

PYTHON = '/usr/local/bin/python3.12'


@pytest.fixture
def recovery_gateway(kube, request):
    require_network(kube, request.config.getoption('--network-evidence'))
    return request.getfixturevalue('gateway')


def execute(sdk, name, code, timeout=20):
    return sdk.call('exec', name, [PYTHON, '-c', code], workspace='default', workdir='/tmp', no_login_shell=True, timeout_seconds=timeout)


def hold(operation):
    # One exclusive intent file prevents an accidental replay from succeeding.
    return f'''import os,json,subprocess,time
from pathlib import Path
op={operation!r}
def identity(pid):
 s=Path(f'/proc/{{pid}}/stat').read_text().rsplit(')',1)[1].split()
 return {{'pid':pid,'start_ticks':s[19]}}
child=subprocess.Popen([{PYTHON!r},'-c','import time; time.sleep(90)'])
r={{'operation_id':op,'parent':identity(os.getpid()),'child':identity(child.pid)}}
Path('/tmp/'+op+'.json').write_text(json.dumps(r))
with open('/tmp/'+op+'.intent','x') as f:f.write(op+'\\n')
print(json.dumps(r),flush=True)
time.sleep(90)
Path('/tmp/'+op+'.finished').write_text('finished\\n')
child.wait()
'''


def observe_process(sdk, name, operation):
    code = f'''import json
from pathlib import Path
op={operation!r}
r=json.loads(Path('/tmp/'+op+'.json').read_text())
for key in ('parent','child'):
 p=Path('/proc/'+str(r[key]['pid'])+'/stat')
 if p.exists():
  s=p.read_text().rsplit(')',1)[1].split(); r[key]['observed_start_ticks']=s[19]; r[key]['state']=s[0]
 else:r[key]['state']='absent'
r['intent']=Path('/tmp/'+op+'.intent').read_text()
r['finished']=Path('/tmp/'+op+'.finished').exists()
print(json.dumps(r))'''
    result = execute(sdk, name, code)
    assert result.exit_code == 0 and result.stderr == ''
    record = json.loads(result.stdout)
    assert record['operation_id'] == operation and record['intent'] == operation + '\n'
    for key in ('parent', 'child'):
        if record[key]['state'] != 'absent':
            assert record[key]['start_ticks'] == record[key]['observed_start_ticks'], 'PID identity replaced'
    return record


def recovery_spec(image, memory):
    spec = inert_spec()
    spec.template.image = image
    spec.template.resources.Clear()
    spec.template.resources.update({'limits': {'cpu': '1', 'memory': memory}})
    return spec


@contextmanager
def owned(kube, native, sdk, record, memory, *, name=None):
    image = image_receipt('python')
    name = record['name'] = name or ('rec-' + uuid.uuid4().hex[:12])
    record.update(outcome='failed', cleanup_confirmed=False, artifact=image)
    spec = recovery_spec(image['image'], memory)
    sandbox, resources, container_ids = None, [], []
    cluster_id = record['cluster_container_id'] = json.loads((ROOT/'.state/kind/owner.json').read_text())['container_id']
    try:
        sandbox = sdk.call('create', workspace='default', name=name, spec=spec)
        record['sandbox_id'] = sandbox.id
        assert sdk.call('wait_ready', name, workspace='default').id == sandbox.id
        actual = json.loads(native['cli']('sandbox', 'get', name, '-o', 'json').stdout)
        assert actual['id'] == sandbox.id
        pair = inspect_identity(kube, actual, record, expected_image=image['image'])
        cr = kube.get('sandboxes', '-n', 'openshell')['items'][0]
        resources = [('sandbox', cr['metadata']['name'], cr['metadata']['uid'])] + [('pod', p['metadata']['name'], p['metadata']['uid']) for p in pair.values()]
        record['resources'] = resources
        record['workspace_storage'] = workspace_storage(kube, pair, cr['metadata']['uid'])
        container_ids = [c['containerID'].split('://',1)[1] for p in pair.values() for c in p['status']['containerStatuses']]
        record['container_ids'] = container_ids
        agent = next(c for c in pair['workload']['status']['containerStatuses'] if c['name'] == 'agent')
        assert agent['imageID'].endswith(image['manifest_digest'])
        record['image_id'] = agent['imageID']
        limits = next(c['resources'] for c in pair['workload']['spec']['containers'] if c['name'] == 'agent')
        assert limits['limits']['memory'] == limits['requests']['memory'] == memory
        assert limits['limits']['cpu'] == limits['requests']['cpu'] == '1'
        record['resources_profile'] = limits
        record['expected_policy'] = yaml.safe_load((ROOT/'policies/openshell/identity.yaml').read_text())
        observe_policy(native['cli'], name, record['expected_policy'], record)
        control = execute(sdk, name, "print('recovery-native-control')")
        assert (control.exit_code, control.stdout, control.stderr) == (0, 'recovery-native-control\n', '')
        yield name, pair
        record['outcome'] = 'passed'
    finally:
        try:
            if sandbox is not None:
                assert sdk.call('get', name, workspace='default').id == sandbox.id
                if not resources:
                    # Retain original partial-admission identity before any deletion.
                    crs = [c for c in kube.get('sandboxes','-n','openshell')['items'] if c['metadata'].get('annotations',{}).get('openshell.ai/sandbox-id') == sandbox.id]
                    assert len(crs) <= 1
                    if crs:
                        cr = crs[0]
                        assert cr['metadata']['annotations']['openshell.ai/sandbox-name'] == name
                        pods = [p for p in kube.get('pods','-n','openshell')['items'] if p['metadata'].get('labels',{}).get('openshell.ai/boundary-pair') == sandbox.id]
                        assert all(any(o['uid']==cr['metadata']['uid'] for o in p['metadata']['ownerReferences']) for p in pods)
                        resources = [('sandbox',cr['metadata']['name'],cr['metadata']['uid'])] + [('pod',p['metadata']['name'],p['metadata']['uid']) for p in pods]
                        record['resources'] = resources
                        partial = {p['metadata']['labels']['openshell.ai/boundary-role']:p for p in pods}
                        assert len(partial)==len(pods)
                        if 'workload' in partial:
                            record['workspace_storage'] = workspace_storage(kube,partial,cr['metadata']['uid'])
                        container_ids = [c['containerID'].split('://',1)[1] for p in pods for c in p['status'].get('containerStatuses',[]) if c.get('containerID')]
                        record['container_ids'] = container_ids
                        if 'supervisor' in partial:
                            supervisor = partial['supervisor']
                            assert kube.get('pod',supervisor['metadata']['name'],'-n','openshell')['metadata']['uid']==supervisor['metadata']['uid']
                            kube.run('logs','-n','openshell',supervisor['metadata']['name'],'--timestamps=true','--tail=200',check=False)
                deletion = sdk.call('delete', name, workspace='default')
                assert deletion.sandbox_id == sandbox.id and deletion.outcome in (DeletionOutcome.COMPLETED, DeletionOutcome.ACCEPTED)
                sdk.call('wait_deleted', name, workspace='default', expected_sandbox_id=sandbox.id, timeout_seconds=90)
                assert sdk.call('list_all', workspace='default') == []
                for resource, resource_name, uid in resources:
                    wait_resource_absent(kube, resource, resource_name, uid)
                for resource, identity in record.get('workspace_storage', {}).items():
                    wait_resource_absent(kube, resource, identity['name'], identity['uid'], namespace=None if resource == 'pv' else 'openshell')
                tasks = kube.native(['docker','--host=unix:///var/run/docker.sock','exec',cluster_id,'ctr','-n','k8s.io','tasks','list']).stdout
                assert all(cid not in tasks for cid in container_ids), 'Original native container task survived teardown'
                record['container_tasks_absent'] = bool(container_ids)
                record['cleanup_confirmed'] = len(resources) == 3 and bool(record.get('workspace_storage'))
        finally:
            (kube.evidence / (name + '.json')).write_text(json.dumps(record, indent=2))


def client(kube, native, name, sandbox_id, operation, command, budget=8192, timeout=60):
    config = {'operation_id': operation, 'sandbox_id': sandbox_id, 'name': name, 'endpoint': native['endpoint'], 'tls': {k: str(native['mtls'] / filename) for k, filename in [('ca_path','ca.crt'),('cert_path','tls.crt'),('key_path','tls.key')]}, 'command': command, 'budget': budget, 'timeout': timeout, 'receipt': str(kube.evidence / (operation + '.jsonl'))}
    path = kube.evidence / (operation + '-client.json')
    path.write_text(json.dumps(config))
    log = (kube.evidence / (operation + '-client.log')).open('w')
    process = subprocess.Popen([sys.executable,'-m','tests.qualification.recovery_client',str(path)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    return process, log, config


def events(config):
    from pathlib import Path
    path = Path(config['receipt'])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def finish_client(process, log, config, stop=False):
    try:
        if stop and process.poll() is None:
            process.terminate()
        process.wait(timeout=70)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        log.close()
    receipt = {'pid': process.pid, 'exit': process.returncode, 'confirmed_absent': process.poll() is not None, 'events': events(config)}
    return receipt


def started(process, config):
    deadline = time.monotonic() + 20
    while True:
        chunks = [e for e in events(config) if e['type']=='chunk' and e['stream']=='stdout']
        data = b''.join(base64.b64decode(e['base64']) for e in chunks)
        if b'\n' in data:
            value = json.loads(data.splitlines()[0])
            assert value['operation_id']==config['operation_id']
            return value
        assert process.poll() is None, 'Native client exited before actual start proof'
        assert time.monotonic() < deadline, 'Command delivery unknown; do not replay'
        time.sleep(.2)


def restart_gateway(kube, native, record):
    old = kube.get('pod','openshell-0','-n','openshell')
    stateful = kube.get('statefulset','openshell','-n','openshell')
    assert any(o['uid']==stateful['metadata']['uid'] for o in old['metadata']['ownerReferences'])
    record['gateway_restart'] = {'original_uid':old['metadata']['uid'],'statefulset_uid':stateful['metadata']['uid']}
    kube.run('logs','-n','openshell','openshell-0','--timestamps=true')
    assert kube.get('pod','openshell-0','-n','openshell')['metadata']['uid']==old['metadata']['uid']
    kube.run('delete','pod','openshell-0','-n','openshell','--wait=true','--timeout=90s',timeout=100)
    kube.run('rollout','status','statefulset/openshell','-n','openshell','--timeout=120s',timeout=130)
    kube.run('wait','--for=condition=Ready','pod/openshell-0','-n','openshell','--timeout=120s',timeout=130)
    replacement = kube.get('pod','openshell-0','-n','openshell')
    assert replacement['metadata']['uid']!=old['metadata']['uid']
    record['gateway_restart']['replacement_uid'] = replacement['metadata']['uid']
    for original, _ in native['port_forwards']:
        if original.poll() is None:
            original.terminate()
        original.wait(timeout=10)
    log_path = kube.evidence / 'replacement-port-forward.log'
    log = log_path.open('w')
    port = native['endpoint'].rsplit(':',1)[1]
    forward = subprocess.Popen(kube.argv+['port-forward','-n','openshell','svc/openshell','--address=127.0.0.1',f'{port}:8080'],stdout=log,stderr=subprocess.STDOUT)
    native['port_forwards'].append((forward,log))
    deadline = time.monotonic()+15
    while f'Forwarding from 127.0.0.1:{port}' not in log_path.read_text():
        assert forward.poll() is None and time.monotonic()<deadline
        time.sleep(.2)
    record['gateway_restart']['replacement_forward_pid'] = forward.pid


@pytest.mark.recovery
def test_native_interruptions_limits_and_cleanup(kube, recovery_gateway):
    native = recovery_gateway
    paths = ['tests/qualification/test_recovery.py','tests/qualification/recovery_client.py','tests/qualification/gateway.py','tests/qualification/test_lifecycle.py','tests/qualification/test_policy.py','tests/qualification/support.py','deploy/runtime-lock.yaml','policies/openshell/identity.yaml','pyproject.toml','uv.lock']
    (kube.evidence/'recovery-source-hashes.json').write_text(json.dumps({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},indent=2))
    summary = {'outcome':'failed','sandboxes':[],'internal_retries':'unknown'}
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt',cert_path=native['mtls']/'tls.crt',key_path=native['mtls']/'tls.key')
    with ExitStack() as clients:
        connection = clients.enter_context(SandboxClient(native['endpoint'],tls=tls,timeout=60))
        sdk = SdkReceipts(connection,kube.evidence)
        try:
            summary['global_policy'] = global_policy_observation(native['cli']('policy','get','--global','--full','-o','json',check=False))
            for mode in ('timeout-output','client-loss','gateway-restart','oom'):
                record = {'mode':mode};summary['sandboxes'].append(record)
                with owned(kube,native,sdk,record,'128Mi' if mode=='oom' else '512Mi') as (name,pair):
                    operation = 'recovery-'+uuid.uuid4().hex
                    record['operation_id'] = operation
                    if mode=='timeout-output':
                        result = execute(sdk,name,hold(operation),timeout=2)
                        assert result.exit_code==124 and result.stderr==''
                        start = json.loads(result.stdout)
                        assert start['operation_id']==operation
                        observed = observe_process(sdk,name,operation)
                        for key in ('parent','child'):
                            assert all(observed[key][field]==start[key][field] for field in ('pid','start_ticks'))
                        record['timeout'] = {'native_exit':124,'remote_completion':'unknown','start':start,'process_observation':observed}
                        control = execute(sdk,name,"import sys; sys.stdout.write('A'*4096); sys.stderr.write('B'*2048)")
                        assert (control.exit_code,control.stdout,control.stderr)==(0,'A'*4096,'B'*2048)
                        overflow = operation+'-output'
                        process,log,config = client(kube,native,name,record['sandbox_id'],overflow,[PYTHON,'-c',"import sys; sys.stdout.write('C'*131072); sys.stdout.flush()"],budget=4096)
                        record['output'] = finish_client(process,log,config)
                        es = record['output']['events']
                        assert any(e['type']=='budget_exceeded' for e in es) and not any(e['type']=='result' for e in es)
                        assert sum(e['retained_bytes'] for e in es if e['type']=='chunk')==4096
                    elif mode in ('client-loss','gateway-restart'):
                        process,log,config = client(kube,native,name,record['sandbox_id'],operation,[PYTHON,'-c',hold(operation)])
                        try:
                            record['start'] = started(process,config)
                            if mode=='gateway-restart':
                                with open(config['receipt'],'rb') as f:
                                    before_bytes = f.read()
                                before = hashlib.sha256(before_bytes).hexdigest()
                                record['external_receipt_before_restart_sha256'] = before
                                restart_gateway(kube,native,record)
                                with open(config['receipt'],'rb') as f:
                                    assert f.read().startswith(before_bytes), 'External evidence lost across gateway restart'
                                record['external_receipt_prefix_preserved'] = True
                                # A new native client is an explicit reconnect, never a workload replay.
                                sdk.client = clients.enter_context(SandboxClient(native['endpoint'],tls=tls,timeout=60))
                                record['native_client_reopened'] = True
                                assert sdk.call('health').version=='0.1.3'
                                recovered = sdk.call('get',name,workspace='default')
                                assert recovered.id==record['sandbox_id']
                                record['gateway_recovered_phase'] = recovered.status.phase
                                assert sdk.call('wait_ready',name,workspace='default').id==record['sandbox_id']
                                for role,pod in pair.items():
                                    current = kube.get('pod',pod['metadata']['name'],'-n','openshell')
                                    assert current['metadata']['uid']==pod['metadata']['uid']
                                    assert [c['containerID'] for c in current['status']['containerStatuses']]==[c['containerID'] for c in pod['status']['containerStatuses']]
                                record['workspace_storage_after_restart'] = workspace_storage(kube,pair,record['sandbox_uid'])
                                assert record['workspace_storage_after_restart']==record['workspace_storage']
                                observe_policy(native['cli'],name,record['expected_policy'],record)
                            else:
                                assert process.poll() is None, 'Client lost before deliberate interruption'
                                process.terminate()
                        finally:
                            record['client'] = finish_client(process,log,config,stop=True)
                        record['process_observation'] = observe_process(sdk,name,operation)
                        for key in ('parent','child'):
                            assert all(record['process_observation'][key][field]==record['start'][key][field] for field in ('pid','start_ticks'))
                        assert record['client']['events'][0]['sandbox_id']==record['sandbox_id']
                        assert record['client']['confirmed_absent']
                        if mode=='client-loss':
                            assert record['client']['exit']==-15
                        record['remote_completion'] = 'unknown'
                    else:
                        agent = next(c for c in pair['workload']['status']['containerStatuses'] if c['name']=='agent')
                        record['original_agent_container_id'] = agent['containerID']
                        # Touch finite chunks, maximum192Mi against an admitted128Mi cgroup.
                        code = "import os,json,time; from pathlib import Path; chunks=[];\nprint(json.dumps({'operation_id':"+repr(operation)+",'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]}),flush=True);\nfor i in range(96): chunks.append(bytearray(2*1024*1024)); time.sleep(.01)\nprint('unexpected-allocation-success',flush=True)"
                        process,log,config = client(kube,native,name,record['sandbox_id'],operation,[PYTHON,'-c',code],timeout=20)
                        try:
                            record['oom_started'] = started(process,config)
                            deadline = time.monotonic()+30
                            while True:
                                pod = kube.get('pod',pair['workload']['metadata']['name'],'-n','openshell')
                                assert pod['metadata']['uid']==pair['workload']['metadata']['uid']
                                actual = next(c for c in pod['status']['containerStatuses'] if c['name']=='agent')
                                terminated = actual.get('state',{}).get('terminated') or actual.get('lastState',{}).get('terminated')
                                if terminated and terminated.get('reason')=='OOMKilled':
                                    assert terminated['containerID']==record['original_agent_container_id']
                                    record['oom_terminated'] = terminated
                                    break
                                assert time.monotonic()<deadline, 'No original-container native OOMKilled evidence'
                                time.sleep(1)
                        finally:
                            record['oom_client'] = finish_client(process,log,config,stop=True)
            assert all(r['outcome']=='passed' and r['cleanup_confirmed'] and r['container_tasks_absent'] for r in summary['sandboxes'])
            summary['outcome'] = 'passed'
        finally:
            summary['sdk_calls'] = sdk.counter
            (kube.evidence/'recovery.json').write_text(json.dumps(summary,indent=2))
