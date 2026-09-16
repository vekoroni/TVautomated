"""Isolated test root for the ``avshunter`` rebuild package.

Run from the repository root:
    venv\\Scripts\\python.exe -m pytest tests_rebuild -q -p no:cacheprovider --basetemp=%TEMP%\\avs_rb

Tests here never read live ``data/`` stores and never call the network.
"""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*_args, **_kwargs):
        raise RuntimeError("network access is blocked in tests_rebuild")

    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
