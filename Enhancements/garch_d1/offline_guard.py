"""Pytest plugin: reject network connections during saved-data regression tests."""
import socket


def _blocked(*args, **kwargs):
    raise AssertionError("Offline GARCH validation: network access forbidden")


def pytest_sessionstart(session):
    socket.socket.connect = _blocked
    socket.create_connection = _blocked
