"""Keep offline recovery separate from every process using the service journal."""

import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def server_lock(database, *, exclusive=False):
    """Hold a shared API lock, or an exclusive lock for offline operator recovery.

    Several local API processes can share the journal's admission checks. An
    offline recovery command must wait until all of them have stopped. Locks
    release automatically when their process exits, including after a crash.
    """
    path = Path(str(database) + ".server.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        path.chmod(0o600)
        try:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Stop DemoLogic before recovering an unknown attempt") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def activity_lock(database, *, exclusive=False):
    """Keep recovery separate from admission and active inference on this host.

    Each admitted task holds a shared lock until its result is saved, even if
    its caller disconnects. Recovery takes the exclusive lock without waiting.
    A crashed process releases its lock, but its journal marker stays blocked.
    """
    from service.persistence.journal import AdmissionError

    path = Path(str(database) + ".activity.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        path.chmod(0o600)
        try:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AdmissionError("recovery_inflight") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
