"""Release-test plugin: no network or operational data/code mutations."""
import os
from pathlib import Path
import socket
import sys

PROTECTED = (
    Path("C:/Users/ACKVerissimo/AVSHUNTER-Intelligence"),
    Path("C:/Users/ACKVerissimo/vanguard"),
    Path("C:/Users/ACKVerissimo/vanguard_backup"),
)


def _network_forbidden(*args, **kwargs):
    raise AssertionError("Retention release tests must not use providers/network")


def _check_path(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return
    path = Path(os.fsdecode(value)).absolute()
    if any(path == root or path.is_relative_to(root) for root in PROTECTED):
        raise AssertionError("Release test attempted operational mutation: " + str(path))


def _audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if write:
            _check_path(args[0])
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.truncate", "os.chmod", "os.utime"}:
        _check_path(args[0])
    elif event in {"os.rename", "os.link", "os.symlink"}:
        _check_path(args[0])
        _check_path(args[1])
    elif event == "sqlite3.connect":
        _check_path(args[0])


def pytest_sessionstart(session):
    socket.socket.connect = _network_forbidden
    socket.create_connection = _network_forbidden
    sys.addaudithook(_audit)
