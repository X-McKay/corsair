"""Exclusive, fsynced host receipts shared by lifecycle and execution."""
import json
import os
from pathlib import Path
import stat


class ReceiptDirectory:
    def __init__(self, path: Path):
        if not path.is_absolute():
            raise ValueError('Host receipt directory must be absolute')
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            self.close()
            raise ValueError('Host receipt directory must be owned by this user with mode0700')

    def close(self):
        os.close(self.fd)

    def write(self, operation, suffix, value):
        data = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
        fd = os.open(f'{operation}.{suffix}.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self.fd)
