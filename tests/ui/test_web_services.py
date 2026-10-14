"""Native service boundaries without network calls or workload mutations."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from corsair.web import services


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for name in tuple(services.os.environ):
        if name.startswith('CORSAIR_UI_') or name == 'CORSAIR_OPENSHELL_CONFIG':
            monkeypatch.delenv(name)


def test_unconfigured_performs_no_calls(monkeypatch):
    monkeypatch.setattr(services, '_openshell', lambda *args: pytest.fail('unexpected call'))
    assert [row['status'] for row in services.service_status()] == ['not_configured', 'not_configured']
    assert services.workflow_runs()['status'] == 'not_configured'


def test_status_never_exposes_exception_or_endpoint(monkeypatch):
    monkeypatch.setenv('CORSAIR_UI_TEMPORAL_ADDRESS', 'secret-address')
    monkeypatch.setenv('CORSAIR_UI_OPENSHELL_ENDPOINT', 'secret-address')
    async def fail(*args):
        raise RuntimeError('secret-token')
    monkeypatch.setattr(services, '_temporal', fail)
    monkeypatch.setattr(services, '_openshell', lambda *args: False)
    result = services.service_status()
    assert all(row['status'] == 'unavailable' for row in result)
    assert 'secret' not in str(result)
    assert services.workflow_runs()['status'] == 'unavailable'


def test_native_namespace_probe_no_retry(monkeypatch):
    from temporalio.client import Client
    calls = []
    async def describe(request, **kwargs):
        assert request.namespace == 'operator-space'
        assert kwargs['retry'] is False
        assert kwargs['timeout'].total_seconds() <= 2
    async def connect(address, **kwargs):
        calls.append((address, kwargs))
        return SimpleNamespace(workflow_service=SimpleNamespace(describe_namespace=describe))
    monkeypatch.setattr(Client, 'connect', connect)
    asyncio.run(services._temporal('temporal:7233', {'CORSAIR_UI_TEMPORAL_NAMESPACE': 'operator-space'}))
    assert calls[0][1]['lazy'] is True
    assert calls[0][1]['retry_config'].max_retries == 0


def test_native_deadline(monkeypatch):
    async def hang(*args):
        await asyncio.sleep(60)
    monkeypatch.setattr(services, '_temporal_client', hang)
    monkeypatch.setattr(services, 'PROBE_SECONDS', .01)
    with pytest.raises(TimeoutError):
        asyncio.run(services._temporal('temporal:7233', {}))


def test_tls_requires_absolute_regular_files_and_paired_client_identity(tmp_path):
    with pytest.raises(ValueError):
        services._tls_file('relative.pem')
    with pytest.raises(ValueError):
        services._tls_file(str(tmp_path))
    with pytest.raises(ValueError):
        asyncio.run(services._temporal_client('temporal:7233', {'CORSAIR_UI_TEMPORAL_TLS_CERT': '/missing'}))


def test_native_openshell_health_and_close(monkeypatch, tmp_path):
    import openshell
    from openshell._proto import openshell_pb2
    config = {}
    for name in ('CA', 'CERT', 'KEY'):
        path = tmp_path / name
        path.write_text('fixture')
        config['CORSAIR_UI_OPENSHELL_TLS_' + name] = str(path)
    closed = []
    class Client:
        def __init__(self, endpoint, **kwargs):
            assert endpoint == 'gateway:8080'
            assert kwargs['timeout'] == 2
            assert kwargs['tls'].ca_path == tmp_path / 'CA'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(True)
        def health(self):
            return openshell_pb2.HealthResponse(status=openshell_pb2.SERVICE_STATUS_HEALTHY)
    monkeypatch.setattr(openshell, 'SandboxClient', Client)
    endpoint, paths = services.openshell_connection(config | {'CORSAIR_UI_OPENSHELL_ENDPOINT': 'gateway:8080'})
    assert services._openshell(endpoint, paths)
    assert closed == [True]


def test_openshell_falls_back_to_the_backend_config_endpoint_and_tls_only(tmp_path):
    for name in ('ca', 'cert', 'key'):
        (tmp_path / name).write_text('fixture')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'endpoint': '127.0.0.1:30051', 'ca': str(tmp_path / 'ca'),
                                  'cert': str(tmp_path / 'cert'), 'key': str(tmp_path / 'key'),
                                  'cli_env': {'TOKEN': 'never read'}}))
    endpoint, paths = services.openshell_connection({'CORSAIR_OPENSHELL_CONFIG': str(config)})
    assert endpoint == '127.0.0.1:30051' and paths == [tmp_path / 'ca', tmp_path / 'cert', tmp_path / 'key']
    assert services.openshell_connection({}) is None


def test_workflow_list_native_filter_bound_and_no_payloads(monkeypatch):
    from temporalio.api.workflowservice.v1 import ListWorkflowExecutionsResponse
    from temporalio.api.workflow.v1 import WorkflowExecutionInfo
    from temporalio.api.common.v1 import WorkflowExecution, WorkflowType
    from temporalio.api.enums.v1 import WorkflowExecutionStatus
    entries = [WorkflowExecutionInfo(execution=WorkflowExecution(workflow_id=f'corsair-v2-run-{i}', run_id='native-id'),
                                    type=WorkflowType(name=services.WORKFLOW_TYPES[0]),
                                    status=WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING) for i in range(101)]
    async def listing(request, **kwargs):
        assert request.page_size == 101
        assert request.query == "WorkflowType = 'corsair.v2.Investigation'"
        assert kwargs['retry'] is False
        return ListWorkflowExecutionsResponse(executions=entries)
    async def connect(*args):
        return SimpleNamespace(workflow_service=SimpleNamespace(list_workflow_executions=listing))
    monkeypatch.setattr(services, '_temporal_client', connect)
    result = asyncio.run(services._workflow_runs('temporal', {}))
    assert len(result['runs']) == 100 and result['limited']
    assert result['runs'][0]['status'] == 'RUNNING'
    # the workflow id is corsair-v2-<run id> (corsair.cli), so each execution links to its run record
    assert result['runs'][0]['record'] == 'run-0'
    entries[:] = [WorkflowExecutionInfo(type=WorkflowType(name='other')), WorkflowExecutionInfo(
        type=WorkflowType(name=services.WORKFLOW_TYPES[0]), parent_execution=WorkflowExecution(workflow_id='parent'))]
    result = asyncio.run(services._workflow_runs('temporal', {}))
    assert result['runs'] == []


@pytest.mark.parametrize('address', ['https://gateway:8080', 'gateway', 'user:secret@gateway:8080',
                                     'gateway:8080/path', 'gateway:8080?token=secret', 'gateway:70000'])
def test_native_addresses_reject_http_urls_and_credentials(address):
    with pytest.raises(ValueError):
        services.native_address(address)


def test_native_addresses_accept_service_dns_and_ipv6():
    assert services.native_address('gateway.corsair.svc:8080') == 'gateway.corsair.svc:8080'
    assert services.native_address('[::1]:7233') == '[::1]:7233'


def test_listed_workflow_is_the_one_v2_runs():
    from temporalio.workflow import _Definition
    from corsair.workflow import InvestigationWorkflow
    assert services.WORKFLOW_TYPES == (_Definition.must_from_class(InvestigationWorkflow).name,)
