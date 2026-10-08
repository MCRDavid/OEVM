"""Shared test set-up."""

import pytest

from adapters.http import reset_host_timers


@pytest.fixture(autouse=True)
def fresh_host_timers():
    """Each test has its own fake clock, so start every test with no request history."""
    reset_host_timers()
    yield
    reset_host_timers()
