"""Single operator-owned local root; standard atomic no-overwrite publication."""
import hashlib
import os
from pathlib import Path
import stat
from uuid import uuid4

from corsair.ports.artifacts import ArtifactRef


class ArtifactStorageError(RuntimeError):
    def __init__(self, detail, *, reference=None, publication='not_published', temporary_cleanup='not_required',
                 temporary_name=None, temporary_identity=None):
        self.reference = reference
        self.publication = publication
        self.temporary_cleanup = temporary_cleanup
        self.temporary_name = temporary_name
        self.temporary_identity = temporary_identity
        super().__init__(detail)


class LocalArtifacts:
    def __init__(self, root: Path, *, max_bytes: int):
        if not root.is_absolute() or type(max_bytes) is not int or not 1 <= max_bytes <= 64*1024*1024:
            raise ValueError('Absolute private root and bounded operator byte limit required')
        self._fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self._fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(self._fd)
            raise ValueError('Artifact root must be user-owned mode0700')
        self._max_bytes = max_bytes

    def __enter__(self): return self
    def __exit__(self, *args): os.close(self._fd)

    def get(self, reference: ArtifactRef) -> bytes:
        if not isinstance(reference, ArtifactRef) or reference.size > self._max_bytes:
            raise ValueError('Bounded artifact reference required')
        try:
            fd = os.open(reference.sha256, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._fd)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o400 or info.st_size != reference.size):
                    raise ValueError('Artifact type/owner/mode/size changed')
                data = stream.read(self._max_bytes+1)
                if len(data) != reference.size or hashlib.sha256(data).hexdigest() != reference.sha256:
                    raise ValueError('Artifact digest/size mismatch')
                return data
        except Exception as error:
            raise ArtifactStorageError(f'{type(error).__name__}: {error}', reference=reference) from error

    def put(self, data: bytes, *, expected_sha256: str | None = None) -> ArtifactRef:
        if type(data) is not bytes or len(data) > self._max_bytes:
            raise ValueError('Bounded exact bytes required')
        reference = ArtifactRef(hashlib.sha256(data).hexdigest(), len(data))
        if expected_sha256 is not None and expected_sha256 != reference.sha256:
            raise ValueError('Expected artifact digest mismatch')
        name = str(uuid4())+'.partial'
        identity = None
        publication = 'not_published'
        cleanup = 'not_required'
        failure = None
        try:
            # Creation failure itself can leave a name; never infer absence.
            cleanup = 'unconfirmed'
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self._fd)
            info = os.fstat(fd)
            identity = (info.st_dev, info.st_ino)
            cleanup = 'unconfirmed'
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
            try:
                # Never replace an existing digest name, including poisoned links.
                publication = 'unknown'
                os.link(name, reference.sha256, src_dir_fd=self._fd, dst_dir_fd=self._fd, follow_symlinks=False)
                publication = 'durability_unknown'
            except FileExistsError:
                self.get(reference)
                publication = 'existing_verified'
            os.fsync(self._fd)
            publication = 'admitted'
        except Exception as error:
            failure = error
        finally:
            if identity is not None:
                try:
                    current = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) != identity:
                        raise ValueError('Temporary identity replaced; cleanup refused')
                    os.unlink(name, dir_fd=self._fd)
                    os.fsync(self._fd)
                    cleanup = 'confirmed'
                except Exception as error:
                    if failure is None: failure = error
        if failure is not None:
            raise ArtifactStorageError(f'{type(failure).__name__}: {failure}', reference=reference,
                                       publication=publication, temporary_cleanup=cleanup,
                                       temporary_name=name, temporary_identity=identity) from failure
        return reference
