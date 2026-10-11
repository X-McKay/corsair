"""Fixed qualification client: native streaming, bounded retained output, no retries."""
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import sys

import grpc
from openshell import SandboxClient, TlsConfig, ExecChunk, ExecResult


def bounded_chunk(data, remaining):
    assert remaining >= 0
    kept = data[:remaining]
    return {'observed_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'retained_bytes': len(kept), 'base64': base64.b64encode(kept).decode()}, len(data) > remaining


def terminal_receipt(item):
    # Native exits include synthetic timeout/I/O statuses. Keep remote outcome
    # separate from this acknowledged terminal; each case has native probes.
    return {'type': 'result', 'delivery': 'acknowledged', 'exit_code': item.exit_code, 'stdout_bytes': len(item.stdout.encode()), 'stderr_bytes': len(item.stderr.encode()), 'stdout_sha256': hashlib.sha256(item.stdout.encode()).hexdigest(), 'stderr_sha256': hashlib.sha256(item.stderr.encode()).hexdigest(), 'remote_completion': 'unknown'}


def native_tls(paths):
    return TlsConfig(**{key: Path(value) for key, value in paths.items()})


def main(path):
    config = json.loads(Path(path).read_text())
    evidence = Path(config['receipt'])
    assert not evidence.exists()
    remaining = config['budget']
    assert 0 < remaining <= 131072
    def emit(record):
        record['at'] = datetime.now(timezone.utc).isoformat()
        with evidence.open('a') as f:
            f.write(json.dumps(record) + '\n')
    emit({'type': 'intent', 'operation_id': config['operation_id'], 'sandbox_id': config['sandbox_id'], 'command': config['command'], 'delivery': 'unknown', 'budget': remaining})
    try:
        with SandboxClient(config['endpoint'], tls=native_tls(config['tls']), timeout=60) as client:
            for item in client.exec_stream(config['name'], config['command'], workspace='default', no_login_shell=True, timeout_seconds=config['timeout']):
                if isinstance(item, ExecChunk):
                    record, overflow = bounded_chunk(item.data, remaining)
                    remaining -= record['retained_bytes']
                    emit(dict(record, type='chunk', stream=item.stream))
                    if overflow:
                        emit({'type': 'budget_exceeded', 'delivery': 'unknown', 'remote_completion': 'unknown'})
                        client.close()
                        return
                else:
                    assert isinstance(item, ExecResult)
                    emit(terminal_receipt(item))
    except Exception as error:
        record = {'type': 'error', 'delivery': 'unknown', 'error_type': type(error).__name__, 'detail': str(error)}
        if isinstance(error, grpc.RpcError):
            record.update(grpc_code=error.code().name, grpc_details=error.details())
        emit(record)
        raise


if __name__ == '__main__':
    main(sys.argv[1])
