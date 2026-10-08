"""Shared test set-up."""

import socket

import pytest

from adapters.http import reset_host_timers


@pytest.fixture(autouse=True)
def fresh_host_timers():
    """Each test has its own fake clock, so start every test with no request history."""
    reset_host_timers()
    yield
    reset_host_timers()


_CONNECT = socket.socket.connect
_CONNECT_EX = socket.socket.connect_ex


def _refuse(address: object) -> None:
    raise RuntimeError(
        f"tests must never use the network (tried to connect to {address!r}). Replay a "
        "recorded response from tests/fixtures or use httpx.MockTransport instead."
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Enforce the rule that tests never call live feeds: any internet connection fails."""

    def connect(self, address, *args):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse(address)
        return _CONNECT(self, address, *args)

    def connect_ex(self, address, *args):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse(address)
        return _CONNECT_EX(self, address, *args)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
