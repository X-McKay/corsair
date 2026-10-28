"""Trusted intake adapters never fetch arbitrary URLs or invent available images."""

import io
import json

import pytest
from docker.errors import ImageNotFound

from corsair.adapters.sandboxing.images import available_images
from corsair.adapters.scm.github import fetch_issue
from corsair.contracts.intake_agent import IssueReference, JsonIssueInput, parse_issue_json
from corsair.settings import Settings


def test_issue_json_rejects_duplicate_keys_and_non_json_numbers():
    for raw in [b'{"title":"a","title":"b"}', b'{"value":NaN}']:
        with pytest.raises(ValueError):
            parse_issue_json(raw)


def test_issue_json_cannot_override_request_source():
    assert parse_issue_json(b'{"source":"/etc","title":"test"}') == {
        "source": "/etc",
        "title": "test",
    }


@pytest.mark.parametrize("value", [None, True, 91, 1.5, "report 🧭", [], {}, [{"a": None}]])
def test_all_json_root_types_preserve_values(value):
    raw = json.dumps(value, ensure_ascii=False).encode()
    assert parse_issue_json(raw) == value
    assert JsonIssueInput(payload=parse_issue_json(raw)).payload == value


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_json_encoding_and_whitespace_do_not_change_scanner_data(encoding):
    value = {"results": [{"message": "Private disclosure – 🧭", "path": "resolver.py"}]}
    raw = json.dumps(value, indent=2, ensure_ascii=False).replace("\n", "\r\n").encode(encoding)
    assert parse_issue_json(raw) == value


@pytest.mark.parametrize(
    "raw",
    [
        b'{"nested":{"name":1,"name":2}}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{"title":',
        b'{"title":"\xff"}',
        b'{"a":1} {"b":2}',
    ],
)
def test_invalid_json_fails_admission(raw):
    with pytest.raises(ValueError):
        parse_issue_json(raw)


def test_json_size_limit_counts_utf8_bytes():
    accepted = json.dumps("a" * 65534).encode()
    assert len(accepted) == 65536
    assert parse_issue_json(accepted) == "a" * 65534
    for value in ["a" * 65535, "🧭" * 16384]:
        with pytest.raises(ValueError, match="64 KiB"):
            parse_issue_json(json.dumps(value, ensure_ascii=False).encode())


@pytest.mark.parametrize("container", [list, dict])
def test_json_container_entry_limit(container):
    def value(count):
        return list(range(count)) if container is list else {str(n): n for n in range(count)}

    assert parse_issue_json(json.dumps(value(256)).encode()) == value(256)
    with pytest.raises(ValueError, match="entry limit"):
        parse_issue_json(json.dumps(value(257)).encode())


def test_json_nesting_limit():
    value = None
    for _ in range(16):
        value = [value]
    assert parse_issue_json(json.dumps(value).encode()) == value
    with pytest.raises(ValueError, match="nesting limit"):
        parse_issue_json(json.dumps([value]).encode())


def test_github_fetch_uses_fixed_api_and_discards_extra_fields():
    seen = []

    def transport(request, timeout):
        seen.append((request.full_url, timeout))
        return io.BytesIO(
            json.dumps({"title": "Traversal", "body": "Report", "secret": "not forwarded"}).encode()
        )

    issue = fetch_issue(IssueReference(owner="org", repository="repo", number=7), opener=transport)
    assert issue.model_dump() == {"title": "Traversal", "description": "Report", "locations": []}
    assert seen == [("https://api.github.com/repos/org/repo/issues/7", 15)]


def test_inventory_only_includes_present_configured_candidates():
    class Image:
        id = "sha256:" + "1" * 64
        attrs = {"Os": "linux", "Architecture": "arm64"}

    class Images:
        def get(self, reference):
            if reference != "corsair-python:0.1":
                raise ImageNotFound("missing")
            return Image()

    class API:
        images = Images()

        def info(self):
            return {"Architecture": "aarch64", "OSType": "linux"}

    inventory = available_images(Settings(), API())
    assert [image.reference for image in inventory.images] == ["corsair-python:0.1"]
    assert inventory.images[0].image_id == "sha256:" + "1" * 64
