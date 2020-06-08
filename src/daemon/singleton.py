import logging
import os

from pathlib import Path
from typing import Optional, TextIO

try:
    import fcntl

    has_fcntl = True
except ImportError:
    has_fcntl = False

from src.util.path import mkdir

log = logging.getLogger(__name__)


def singleton(path: Path, text="semaphore") -> Optional[TextIO]:
    """
    Open a file with exclusive access at the given path.
    This should work on POSIX (using fcntl) and Windows (which doesn't have fcntl).
    Release the lock by closing the file.
    """

    if not path.parent.exists():
        mkdir(path.parent)

    try:
        if has_fcntl:
            f = open(path, "w")
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            if path.exists():
                path.unlink()
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            f = open(fd, "w")
        f.write(text)
    except IOError:
        return None
    return f
