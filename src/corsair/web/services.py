"""Read-only native service probes. Availability is not workload qualification."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit

PROBE_SECONDS = 2.0


def _result(service: str, status: str, detail: str) -> dict[str, str]:
    return {'id': service, 'status': status, 'detail': detail}


def _tls_file(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('TLS paths must be absolute')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
        raise ValueError('TLS material must be a bounded regular file')
    return path


def native_address(value: str) -> str:
    """The pinned gRPC clients require host:port, not an HTTP URL."""
    parsed = urlsplit('//' + value)
    if (not parsed.hostname or parsed.port is None or not 1 <= parsed.port <= 65535
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or any(char.isspace() for char in value)):
        raise ValueError('Native service address must be host:port without a URL scheme')
    return value


async def _temporal_client(address: str, config: dict[str, str]):
    from temporalio.client import Client
    from temporalio.service import TLSConfig, RetryConfig

    ca, cert, key = (config.get('CORSAIR_UI_TEMPORAL_TLS_' + name, '') for name in ('CA', 'CERT', 'KEY'))
    if bool(cert) != bool(key):
        raise ValueError('Both client certificate and key are required')
    tls = TLSConfig(server_root_ca_cert=_tls_file(ca).read_bytes() if ca else None,
                    client_cert=_tls_file(cert).read_bytes() if cert else None,
                    client_private_key=_tls_file(key).read_bytes() if key else None) if any((ca, cert, key)) else False
    namespace = config.get('CORSAIR_UI_TEMPORAL_NAMESPACE', 'default')
    return await Client.connect(native_address(address), namespace=namespace, tls=tls, lazy=True,
                                retry_config=RetryConfig(max_retries=0))


async def _temporal(address: str, config: dict[str, str]) -> None:
    from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
    async with asyncio.timeout(PROBE_SECONDS):
        client = await _temporal_client(address, config)
        await client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=config.get('CORSAIR_UI_TEMPORAL_NAMESPACE', 'default')),
            retry=False, timeout=timedelta(seconds=PROBE_SECONDS))


def _openshell(endpoint: str, config: dict[str, str]) -> bool:
    from openshell import SandboxClient, TlsConfig
    from openshell._proto import openshell_pb2
    from corsair.adapters.openshell_execution import OpenShellConnection

    paths = [_tls_file(config['CORSAIR_UI_OPENSHELL_TLS_' + name]) for name in ('CA', 'CERT', 'KEY')]
    connection = OpenShellConnection(native_address(endpoint), *paths)
    with SandboxClient(connection.endpoint, tls=TlsConfig(ca_path=connection.ca, cert_path=connection.cert,
                                                        key_path=connection.key), timeout=PROBE_SECONDS) as client:
        return client.health().status == openshell_pb2.SERVICE_STATUS_HEALTHY


def service_status() -> list[dict[str, str]]:
    """Two sequential native probes, each limited to two seconds; no workload mutations.

    Configuration comes only from the operator environment, never request parameters.
    Raw SDK exceptions, endpoint addresses and TLS material are never returned.
    """
    config = dict(os.environ)
    results = []
    for service, setting in (('temporal', 'CORSAIR_UI_TEMPORAL_ADDRESS'),
                             ('openshell', 'CORSAIR_UI_OPENSHELL_ENDPOINT')):
        endpoint = config.get(setting, '')
        if not endpoint:
            results.append(_result(service, 'not_configured', f'Set {setting} to enable the native read-only check.'))
            continue
        try:
            if service == 'temporal':
                asyncio.run(_temporal(endpoint, config))
                detail = 'Configured namespace is accessible. Worker availability and workload execution are not checked.'
            elif _openshell(endpoint, config):
                detail = 'Gateway reports healthy. Sandbox admission and workload execution are not checked.'
            else:
                results.append(_result(service, 'unavailable', 'Gateway reports degraded or unhealthy; inspect OpenShell gateway health.'))
                continue
            results.append(_result(service, 'available', detail))
        except ImportError:
            results.append(_result(service, 'unavailable', 'Install the pinned UI service dependencies and restart the UI.'))
        except (ValueError, KeyError, OSError):
            results.append(_result(service, 'unavailable', 'Check the configured service address and readable TLS CA/certificate/key files; client certificate and key must be paired.'))
        except Exception:
            detail = ('Check Temporal connectivity, TLS, namespace existence and access permissions.' if service == 'temporal'
                      else 'Check OpenShell gateway connectivity, TLS identity and gateway logs.')
            results.append(_result(service, 'unavailable', detail))
    return results


WORKFLOW_TYPES = ('corsair.chain.Investigation', 'corsair.fixture.Investigation')


async def _workflow_runs(address: str, config: dict[str, str]) -> dict:
    from temporalio.api.workflowservice.v1 import ListWorkflowExecutionsRequest
    from temporalio.api.enums.v1 import WorkflowExecutionStatus
    query = "WorkflowType IN ('corsair.chain.Investigation', 'corsair.fixture.Investigation')"
    async with asyncio.timeout(PROBE_SECONDS):
        client = await _temporal_client(address, config)
        response = await client.workflow_service.list_workflow_executions(
            ListWorkflowExecutionsRequest(namespace=config.get('CORSAIR_UI_TEMPORAL_NAMESPACE', 'default'),
                                          page_size=101, query=query),
            retry=False, timeout=timedelta(seconds=PROBE_SECONDS))
    runs = []
    for info in response.executions[:101]:
        if info.type.name not in WORKFLOW_TYPES or info.HasField('parent_execution'):
            continue
        row = {'id': info.execution.workflow_id, 'run_id': info.execution.run_id,
               'workflow_type': info.type.name,
               'status': WorkflowExecutionStatus.Name(info.status).removeprefix('WORKFLOW_EXECUTION_STATUS_'),
               'started': info.start_time.ToJsonString() if info.HasField('start_time') else None}
        if info.HasField('close_time'):
            row['ended'] = info.close_time.ToJsonString()
        runs.append(row)
    return {'status': 'available', 'detail': 'Native Temporal executions; fixture investigations are scripted fixtures, not live qualification.',
            'runs': runs[:100], 'limited': len(runs) > 100 or bool(response.next_page_token)}


def workflow_runs() -> dict:
    """One bounded native visibility page, never workflow inputs, results or history."""
    config = dict(os.environ)
    address = config.get('CORSAIR_UI_TEMPORAL_ADDRESS', '')
    if not address:
        return {'status': 'not_configured', 'detail': 'Set CORSAIR_UI_TEMPORAL_ADDRESS to list durable investigations.',
                'runs': [], 'limited': False}
    try:
        return asyncio.run(_workflow_runs(address, config))
    except Exception:
        return {'status': 'unavailable', 'detail': 'Check Temporal connectivity, TLS, namespace and visibility permissions; workflow listing could not be read.',
                'runs': [], 'limited': False}
