import hashlib
import json


def test_native_roundtrip(tmp_path):
    value = {"message": "native Python fixture", "numbers": [1, 2, 3]}
    payload = json.dumps(value, sort_keys=True).encode()
    path = tmp_path / "roundtrip.json"
    path.write_bytes(payload)
    assert json.loads(path.read_bytes()) == value
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(payload).digest()
