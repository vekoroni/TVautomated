"""Offline release tests: fail on any attempted provider/network connection."""
import socket

def _blocked(*args,**kwargs):
    raise AssertionError('Offline Phantom release tests prohibit network/provider calls')

def pytest_sessionstart(session):
    socket.socket.connect=_blocked
    socket.socket.connect_ex=_blocked
    socket.create_connection=_blocked
    socket.getaddrinfo=_blocked
