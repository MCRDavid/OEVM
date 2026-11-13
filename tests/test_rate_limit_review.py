"""Scratch reproductions for the rate limit review (to be folded into test_rate_limits.py)."""

import threading
import time
from itertools import pairwise

import httpx
import pytest

from adapters import http
from adapters.http import FeedError, PoliteClient
from tests.test_rate_limits import (
    ECO,
    OPERATORS,
    FakeClock,
    KeyServer,
    assert_within_limits,
    keyed_client_for,
)


@pytest.fixture(autouse=True)
def fresh_timers():
    http.reset_host_timers()
    yield
    http.reset_host_timers()


def test_a_burst_still_counts_once_every_key_is_back_to_its_gap():
    """A key that sent most of its hour's allowance close together, then met trouble,
    goes on at its gap: the hour that holds the burst must still hold no more than the
    limit allows."""
    config = OPERATORS["ubitricity"]
    clock = FakeClock()
    ok = httpx.Response(200, json={})
    server = KeyServer(clock, [ok] * 28 + [httpx.Response(503)] + [ok] * 40)
    with keyed_client_for(config, clock, server) as client:
        while server.responses:
            client.get(config.endpoints["locations"].url)
    arrivals = server.arrivals
    assert len(arrivals) == 69
    for documented in config.rate_limit.limits:
        if documented.endpoint != "locations":
            continue
        for start in arrivals:
            window = [t for t in arrivals if start <= t <= start + documented.per_seconds]
            assert len(window) <= documented.requests, (
                f"{len(window)} requests in {documented.per_seconds:g} s, "
                f"limit {documented.requests}"
            )
    # After the trouble every request keeps the gap.
    for earlier, later in pairwise(arrivals[28:]):
        assert later - earlier >= 125 - 1e-9


def test_a_wait_asked_of_one_key_holds_a_request_already_waiting_for_its_turn():
    """Two keys within their allowance. While the second waits the second it leaves
    after the first one's start, the first one's answer asks for a wait: the second must
    not be sent until that wait has passed."""
    first, second = ECO[0], ECO[1]
    clock = FakeClock()
    in_flight, waiting, answered = threading.Event(), threading.Event(), threading.Event()
    arrivals: list[tuple[float, str]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"]
        arrivals.append((clock(), key))
        if key == f"Token made-up-{first.id}":
            in_flight.set()
            assert waiting.wait(5)
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(200, json={})

    def slow_sleep(seconds: float) -> None:
        # The second key's first wait is for its turn to start: let the first key's
        # answer arrive and be dealt with while it waits.
        if not waiting.is_set():
            waiting.set()
            assert answered.wait(5)
        clock.sleep(seconds)

    def ask_first() -> None:
        with PoliteClient(
            first,
            transport=httpx.MockTransport(answer),
            sleep=clock.sleep,
            clock=clock,
            wall_clock=clock.wall,
            key=f"made-up-{first.id}",
            max_retries=0,
        ) as client:
            with pytest.raises(FeedError):
                client.get(first.endpoints["locations"].url)
        answered.set()

    thread = threading.Thread(target=ask_first)
    thread.start()
    assert in_flight.wait(5)
    with PoliteClient(
        second,
        transport=httpx.MockTransport(answer),
        sleep=slow_sleep,
        clock=clock,
        wall_clock=clock.wall,
        key=f"made-up-{second.id}",
    ) as client:
        client.get(second.endpoints["locations"].url)
    thread.join(5)
    assert [key for _, key in arrivals] == [
        f"Token made-up-{first.id}",
        f"Token made-up-{second.id}",
    ]
    asked_at = arrivals[0][0]
    assert arrivals[1][0] >= asked_at + 60


def test_after_trouble_no_request_starts_while_an_earlier_one_is_still_on_its_way(monkeypatch):
    """Real threads. One key's request is slow; another key's fails meanwhile, which puts
    every key back to one request at a time. The retry must wait for the slow request to
    finish, and the host's gap after it."""
    monkeypatch.setattr(http, "SHARED_HOST_SECONDS", 0.02)
    monkeypatch.setattr(http, "MIN_SECONDS_BETWEEN_REQUESTS", 0.005)
    slow, failing = ECO[0], ECO[1]
    lock, seen = threading.Lock(), []
    failed_once = threading.Event()

    def answer(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"]
        start = time.monotonic()
        if key == f"Token made-up-{slow.id}":
            time.sleep(0.4)
            status = 200
        elif not failed_once.is_set():
            failed_once.set()
            status = 503
        else:
            status = 200
        with lock:
            seen.append((start, time.monotonic(), key, status))
        return httpx.Response(status, json={})

    def fetch(config):
        with PoliteClient(
            config,
            transport=httpx.MockTransport(answer),
            key=f"made-up-{config.id}",
            backoff_seconds=0.01,
        ) as client:
            client.min_interval = 0.05
            client.get(config.endpoints["locations"].url)

    threads = [threading.Thread(target=fetch, args=(config,)) for config in (slow, failing)]
    threads[0].start()
    time.sleep(0.05)  # the slow request is on its way
    threads[1].start()
    for thread in threads:
        thread.join(10)
    slow_done = next(finish for _, finish, key, _ in seen if key == f"Token made-up-{slow.id}")
    retry_start = max(start for start, _, key, _ in seen if key == f"Token made-up-{failing.id}")
    assert len(seen) == 3
    assert retry_start >= slow_done + 0.02 - 1e-3
