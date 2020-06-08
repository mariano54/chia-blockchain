import logging
import os

try:
    import fcntl

    has_fcntl = True
except ImportError:
    has_fcntl = False

from src.util.path import mkdir

log = logging.getLogger(__name__)


def singleton(lockfile, text="semaphore"):
    """
    Open a lockfile exclusively.
    """

    if not lockfile.parent.exists():
        mkdir(lockfile.parent)

    try:
        if has_fcntl:
            f = open(lockfile, "w")
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            if lockfile.exists():
                lockfile.unlink()
            fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            f = open(fd, "w")
        f.write(text)
    except IOError:
        return None
    return f
