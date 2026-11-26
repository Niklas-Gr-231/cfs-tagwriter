# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""One-byte advisory file lock on Windows, flock on POSIX."""
from contextlib import contextmanager
import os


@contextmanager
def locked_file(stream):
    if os.name == 'nt':
        import msvcrt
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write('\0'); stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        try: yield
        finally:
            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
