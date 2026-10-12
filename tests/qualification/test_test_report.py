"""Native inert report producer -> existing execution/artifacts -> claim consumer.

Not an application test run or semantic security disposition qualification.
"""
from dataclasses import asdict
import hashlib
import json
from uuid import uuid4

from openshell import SandboxClient, TlsConfig

from corsair.adapters.local_artifacts import LocalArtifacts
from corsair.adapters.openshell import OpenShellLifecycle
from corsair.adapters.openshell_execution import OpenShellConnection, OpenShellExecution, serialized
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionLimits
from corsair.reports.test_observations import consume_test_report
from tests.qualification.test_adapter_lifecycle import ObservedClient, AdapterHarness, adapter_gateway
from tests.qualification.gateway import gateway
from tests.qualification.test_lifecycle import SdkReceipts
from tests.qualification.test_recovery import owned, recovery_spec, PYTHON
from tests.qualification.prepare_toolchains import image_receipt
from tests.qualification.support import ROOT


def test_native_fixed_report_claims(kube, adapter_gateway):
    native = adapter_gateway
    summary = dict(outcome='failed', scope='fixed report claims only; no actual application tests',
                   cases=[], sandbox={}, application_retries=0)
    receipts, objects = kube.evidence/'report-receipts', kube.evidence/'report-objects'
    receipts.mkdir(mode=0o700); objects.mkdir(mode=0o700)
    owner = uuid4()
    tls = TlsConfig(ca_path=native['mtls']/'ca.crt', cert_path=native['mtls']/'tls.crt', key_path=native['mtls']/'tls.key')
    connection = OpenShellConnection(native['endpoint'], native['mtls']/'ca.crt', native['mtls']/'tls.crt', native['mtls']/'tls.key')
    limits = ExecutionLimits(4096, 2, 20, 512*1024*1024)
    summary['consumer_hashes'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
        'src/corsair/reports/test_observations.py', 'tests/qualification/test_test_report.py', 'pyproject.toml', 'uv.lock')}
    try:
        with SandboxClient(native['endpoint'], tls=tls, timeout=60) as client, LocalArtifacts(objects, max_bytes=4096) as store:
            source, tests = store.put(b'inert source identity fixture'), store.put(b'inert two-test identity fixture')
            observed = ObservedClient(SdkReceipts(client, kube.evidence))
            with OpenShellLifecycle(observed, spec=recovery_spec(image_receipt('python')['image'], '512Mi'), workspace='default', owner=owner, receipts=receipts) as lifecycle, OpenShellExecution(connection, workspace='default', owner=owner, workdir='/tmp', limits=limits, receipts=receipts) as execution:
                driver = AdapterHarness(lifecycle, observed); driver.creation = uuid4()
                with owned(kube, native, driver, summary['sandbox'], '512Mi', name='cs-'+driver.creation.hex[:16]):
                    for exit_code, security in ((0, 'passed'), (1, 'failed')):
                        operation = uuid4()
                        payload = dict(schema_version='test-observations-v1', operation=str(operation),
                                       source_sha256=source.sha256, tests_sha256=tests.sha256,
                                       control=dict(test_id='fixture_control', outcome='passed'),
                                       security=dict(test_id='fixture_security', outcome=security))
                        data = json.dumps(payload, separators=(',', ':')).encode()
                        record = dict(operation=str(operation), expected_exit=exit_code, expected_security_claim=security)
                        summary['cases'].append(record)
                        # Inert literal bytes, no eval of report content or repository code.
                        command = (PYTHON, '-I', '-S', '-B', '-c', f'import os;os.write(1,{data!r});raise SystemExit({exit_code})')
                        result = execution.execute(driver.handle, command, operation)
                        record['execution'] = serialized(result)
                        assert result.stdout == data and result.stderr == b''
                        reference = store.put(result.stdout)
                        admitted = consume_test_report(store, reference, receipt=result, operation=operation,
                                                       handle=driver.handle, source=source, tests=tests)
                        assert admitted.claims.security.outcome == security and admitted.native_exit == exit_code
                        record.update(report=asdict(reference), claims=admitted.claims.model_dump(), outcome='passed')
                assert summary['sandbox']['cleanup_confirmed'] and summary['sandbox']['container_tasks_absent']
                # Actual immutable reread after original sandbox deletion.
                for record in summary['cases']:
                    assert hashlib.sha256(store.get(ArtifactRef(**record['report']))).hexdigest() == record['report']['sha256']
            summary.update(outcome='passed', source=asdict(source), tests=asdict(tests),
                           native_sdk_method_calls=observed.sdk.counter, native_internal_attempts='unknown')
    finally:
        (kube.evidence/'test-report-consumption.json').write_text(json.dumps(summary, indent=2))
