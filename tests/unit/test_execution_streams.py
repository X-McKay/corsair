"""Trusted stream parsing and archive construction have bounded memory and paths."""

import io
import struct
import tarfile
import time

from corsair.adapters.sandboxing.execution import capture_exec, plan_archive
from corsair.contracts.execution import TestFile as PlanFile


class Socket:
    def __init__(self, data):
        self.data = io.BytesIO(data)

    def settimeout(self, value):
        assert value > 0

    def recv(self, count):
        return self.data.read(min(count, 3))


def frame(stream, data):
    return struct.pack(">BxxxI", stream, len(data)) + data


def test_stream_demultiplexes_partial_frames():
    result = capture_exec(Socket(frame(1, b"hello") + frame(2, b"error")), time.monotonic() + 2, 20)
    assert (result.stdout, result.stderr, result.state) == (b"hello", b"error", "completed")


def test_stream_stops_at_combined_output_bound():
    result = capture_exec(Socket(frame(1, b"x" * 100)), time.monotonic() + 2, 12)
    assert result.state == "output_limit"
    assert len(result.stdout) == 12
    assert result.truncated


def test_truncated_frame_is_explicit_error():
    result = capture_exec(Socket(frame(1, b"abc")[:-1]), time.monotonic() + 2, 20)
    assert result.state == "error"


def test_archive_has_only_regular_owned_files_and_directories():
    content = plan_archive([PlanFile(path="nested/test.py", content="print(1)")])
    with tarfile.open(fileobj=io.BytesIO(content)) as archive:
        members = archive.getmembers()
        assert all(item.isfile() or item.isdir() for item in members)
        assert all(item.uid == 1000 and item.gid == 1000 for item in members)
        file = archive.extractfile("nested/test.py")
        assert file is not None and file.read() == b"print(1)"


def test_stream_timeout_is_explicit_and_keeps_partial_output():
    class HangingSocket(Socket):
        def recv(self, count):
            if self.data.tell() < len(self.data.getvalue()):
                return super().recv(count)
            raise TimeoutError

    result = capture_exec(HangingSocket(frame(1, b"partial")), time.monotonic() + 0.01, 100)
    assert result.state == "timeout" and result.stdout == b"partial"
