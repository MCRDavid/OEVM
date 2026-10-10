"""Progress lines for live runs (pipeline/progress.py): pages, percentage and time left.

No test touches the network: the clock is fake and feeds are replayed from tests/fixtures.
"""

import io
import json
import re
from urllib.parse import urlsplit

import httpx
import pytest

from adapters.http import FeedError
from adapters.replay import ReplayTransport
from pipeline import run
from pipeline.progress import OperatorProgress, RunProgress, duration, estimate
from pipeline.registry import load_registry

RELAY = "https://oevm-relay.example.workers.dev"
TOKEN = "test-relay-token-not-real"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Flushes(io.StringIO):
    """Counts flushes, to show each line is sent on at once."""

    def __init__(self) -> None:
        super().__init__()
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1
        super().flush()


@pytest.fixture
def registry():
    return load_registry()


@pytest.fixture
def no_relay(monkeypatch):
    monkeypatch.delenv("OEVM_RELAY_URL", raising=False)
    monkeypatch.delenv("OEVM_RELAY_TOKEN", raising=False)


def progress(**kwargs) -> tuple[RunProgress, io.StringIO, FakeClock]:
    out, clock = io.StringIO(), FakeClock()
    return RunProgress(out=out, clock=clock, **kwargs), out, clock


def lines(out: io.StringIO) -> list[str]:
    return out.getvalue().splitlines()


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0 s"),
        (59.4, "59 s"),
        (60, "1 min"),
        (829, "13 min 49 s"),
        (3600, "1 h"),
        (3900, "1 h 5 min"),
        (-3, "0 s"),
    ],
)
def test_durations_in_words(seconds, text):
    assert duration(seconds) == text


def test_estimates_over_a_minute_are_rounded_to_10_seconds():
    assert estimate(763) == "12 min 40 s"
    assert estimate(45.6) == "46 s"


def test_a_paged_feed_shows_page_of_total_percentage_and_time_left(registry, no_relay):
    """Like char.gy on 8 October 2026: 5,949 locations, 50 a page, about 7 s a page.

    The first request to a host has no gap before it, so page 1 arrives after about 1 s.
    """
    reporter, out, clock = progress()
    op = reporter.operator_started(registry["chargy"], number=1, count=3)
    for page in range(1, 120):
        clock.now += 1 if page == 1 else 7
        op.page("locations", pages=page, records=min(page * 50, 5949), total_records=5949)
    op.module_done("locations", pages=119, records=5949, complete=True)

    shown = lines(out)
    assert shown[0] == "chargy (1 of 3): starting, 6 s between requests"
    # Never faster than the 6 s gap: 118 pages to go at 6 s, not at the first page's 1 s.
    assert shown[1] == (
        "chargy locations: page 1 of 119 (0%), 50 of 5,949 records, "
        "about 11 min 50 s left (estimate)"
    )
    assert shown[2] == (
        "chargy locations: page 10 of 119 (8%), 500 of 5,949 records, "
        "about 12 min 40 s left (estimate)"
    )
    # The first page, then every tenth; the last page is left to the done line.
    assert [line.split(": page ")[1].split(" of")[0] for line in shown[1:-1]] == [
        "1",
        *[str(n) for n in range(10, 120, 10)],
    ]
    assert shown[-1] == "chargy locations: done, 119 pages, 5,949 records in 13 min 47 s"


def test_the_next_module_is_timed_from_the_end_of_the_last(registry, no_relay):
    reporter, out, clock = progress()
    op = reporter.operator_started(registry["chargy"], number=1, count=1)
    clock.now += 100
    op.module_done("locations", pages=2, records=100, complete=True)
    clock.now += 8
    op.page("tariffs", pages=1, records=3, total_records=3)
    op.module_done("tariffs", pages=1, records=3, complete=True)
    assert lines(out)[-1] == "chargy tariffs: done, 1 page, 3 records in 8 s"


def test_a_feed_that_does_not_give_its_total_says_so(registry):
    reporter, out, clock = progress()
    op = reporter.operator_started(registry["jolt"], number=3, count=3)
    clock.now += 2
    op.page("locations", pages=1, records=72)
    assert lines(out)[-1] == (
        "jolt locations: page 1, 72 records (the feed does not say how many there are)"
    )


def test_a_known_number_of_requests_gives_a_percentage_without_a_record_total(registry):
    """Like Jolt's tariffs: one request per tariff id, so the number of pages is known."""
    reporter, out, clock = progress()
    op = reporter.operator_started(registry["jolt"], number=3, count=3)
    op.module_done("locations", pages=1, records=72, complete=True)
    clock.now += 2
    op.page("tariffs", pages=1, records=1, total_pages=5)
    assert lines(out)[-1] == "jolt tariffs: page 1 of 5 (20%), 1 record, about 8 s left (estimate)"


def test_max_pages_caps_the_expected_number_of_pages(registry, no_relay):
    reporter, out, clock = progress(max_pages=3)
    op = reporter.operator_started(registry["chargy"], number=1, count=1)
    clock.now += 7
    op.page("locations", pages=1, records=50, total_records=5949)
    op.module_done("locations", pages=3, records=150, complete=False)
    assert lines(out)[1] == (
        "chargy locations: page 1 of 3 (33%), 50 of 5,949 records, about 14 s left (estimate)"
    )
    assert lines(out)[2] == (
        "chargy locations: incomplete, 3 pages, 150 records in 7 s (see the report)"
    )


def test_a_total_lower_than_the_records_received_does_not_hide_later_pages(registry, no_relay):
    reporter, out, clock = progress()
    op = reporter.operator_started(registry["chargy"], number=1, count=1)
    for page in range(1, 21):
        clock.now += 7
        op.page("locations", pages=page, records=page * 50, total_records=50)
    # Page 1 matches the total, so it looks like the last page and gets no line of its
    # own; once more records arrive than the total, the pages still show.
    assert lines(out)[1:] == [
        "chargy locations: page 10, 500 of 50 records",
        "chargy locations: page 20, 1,000 of 50 records",
    ]


def test_a_total_too_large_to_work_with_never_stops_the_fetch(registry, no_relay):
    """A feed's X-Total-Count is any run of digits; the run must go on whatever it says."""
    huge = "1" + "0" * 309

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status_code": 1000, "data": [{"id": "x"}]},
            headers={"X-Total-Count": huge},
        )

    config = registry["chargy"]
    reporter, out, _ = progress()  # no page cap, so the estimate is worked out
    op = reporter.operator_started(config, number=1, count=1)
    result = run.run_operator(
        config,
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
        max_pages=1,
        progress=op,
    )
    assert result.modules["locations"].total_reported == int(huge)
    assert "chargy locations: page 1, 1 record" in lines(out)


def test_an_empty_first_page_gives_no_estimate(registry, no_relay):
    reporter, out, _ = progress()
    op = reporter.operator_started(registry["chargy"], number=1, count=1)
    op.page("locations", pages=1, records=0, total_records=10)
    assert lines(out)[-1] == "chargy locations: page 1, 0 of 10 records"


def test_relayed_operators_say_so_without_the_relay_address_or_token(registry, monkeypatch):
    monkeypatch.setenv("OEVM_RELAY_URL", RELAY)
    monkeypatch.setenv("OEVM_RELAY_TOKEN", TOKEN)
    reporter, out, _ = progress()
    reporter.operator_started(registry["geniepoint"], number=2, count=3)
    assert lines(out) == ["geniepoint (2 of 3): starting, 2 s between requests, through the relay"]
    assert RELAY not in out.getvalue() and "workers.dev" not in out.getvalue()
    assert TOKEN not in out.getvalue()


def test_direct_operators_do_not_mention_the_relay(registry, no_relay):
    reporter, out, _ = progress()
    reporter.operator_started(registry["geniepoint"], number=2, count=3)
    assert lines(out) == ["geniepoint (2 of 3): starting, 2 s between requests"]


def test_a_half_set_relay_stops_the_operator_before_anything_is_fetched(registry, monkeypatch):
    monkeypatch.setenv("OEVM_RELAY_URL", RELAY)
    monkeypatch.delenv("OEVM_RELAY_TOKEN", raising=False)
    reporter, _, _ = progress()
    with pytest.raises(FeedError, match="needs OEVM_RELAY_TOKEN as well"):
        reporter.operator_started(registry["geniepoint"], number=2, count=3)


def test_operator_and_run_lines(registry, no_relay):
    reporter, out, clock = progress()
    reporter.run_started([["chargy", "geniepoint", "jolt"]])
    reporter.operator_started(registry["chargy"], number=1, count=3)
    clock.now += 829
    reporter.operator_done("chargy", requests=120)
    reporter.operator_started(registry["geniepoint"], number=2, count=3)
    clock.now += 3
    reporter.operator_failed("geniepoint")
    reporter.operator_started(registry["jolt"], number=3, count=3)
    clock.now += 1
    reporter.operator_done("jolt", requests=1)
    reporter.run_done(fetched=2, failed=["geniepoint"])
    assert lines(out) == [
        "Fetching 3 operators, one at a time: chargy, geniepoint, jolt",
        "chargy (1 of 3): starting, 6 s between requests",
        "chargy: finished in 13 min 49 s, 120 requests",
        "geniepoint (2 of 3): starting, 2 s between requests",
        "geniepoint: failed after 3 s (the error follows)",
        "jolt (3 of 3): starting, 2 s between requests",
        "jolt: finished in 1 s, 1 request",
        "Fetching finished in 13 min 53 s: 2 fetched, 1 failed (geniepoint)",
    ]


def test_every_line_is_flushed_at_once(registry, no_relay):
    out = Flushes()
    reporter = RunProgress(out=out, clock=FakeClock())
    reporter.run_started([["chargy"]])
    op = reporter.operator_started(registry["chargy"], number=1, count=1)
    op.page("locations", pages=1, records=50, total_records=100)
    assert out.flushes == len(lines(out)) == 3


# The page lines each recorded feed gives, with a clock that does not move, so each
# estimate is the operator's gap times the pages to come.
PAGE_LINES = {
    "chargy": [
        "chargy locations: page 1 of 2 (50%), 2 of 5,946 records, about 6 s left (estimate)",
        "chargy tariffs: page 1 of 2 (50%), 2 of 3 records, about 6 s left (estimate)",
    ],
    "geniepoint": [],  # each file is one page, so only its done line
    "jolt": [
        "jolt locations: page 1, 4 records (the feed does not say how many there are)",
        "jolt tariffs: page 1 of 5 (20%), 1 record, about 8 s left (estimate)",
    ],
}


@pytest.mark.parametrize("operator", ["chargy", "geniepoint", "jolt"])
def test_the_adapters_report_their_pages(registry, operator):
    """Replays each recorded feed through the real adapter with a progress reporter."""
    manifest = json.loads((run.FIXTURES_DIR / operator / "manifest.json").read_text("utf-8"))
    config = registry[operator].model_copy(update={"relay": None})
    reporter, out, _ = progress(max_pages=manifest["max_pages"])
    op = reporter.operator_started(config, number=1, count=1)
    result = run.run_operator(
        config,
        transport=ReplayTransport(run.FIXTURES_DIR / operator),
        sleep=lambda _seconds: None,
        page_size=manifest["page_size"],
        max_pages=manifest["max_pages"],
        key=run.FIXTURE_KEY,
        progress=op,
    )
    shown = lines(out)
    assert [line for line in shown if ": page " in line] == PAGE_LINES[operator]
    for name, module in result.modules.items():
        ended = [line for line in shown if line.startswith(f"{operator} {name}: ")]
        state = "done" if module.complete else "incomplete"
        pages = f"{len(module.pages)} page" + ("" if len(module.pages) == 1 else "s")
        assert ended[-1].startswith(f"{operator} {name}: {state}, {pages}, ")
    # Numbers and names only: nothing from the feed or its address reaches the log.
    assert all(line.startswith(f"{operator} ") for line in shown)
    assert "http" not in out.getvalue()
    for endpoint in config.endpoints.values():
        assert urlsplit(endpoint.url).netloc not in out.getvalue()
    assert run.FIXTURE_KEY not in out.getvalue()


def test_live_runs_print_progress(monkeypatch, capsys, no_relay):
    replayed = {r.operator_id: r for r in run.run_fixtures(load_registry())}
    capsys.readouterr()

    def fake(config, **kwargs):
        assert isinstance(kwargs["progress"], OperatorProgress)
        if config.id == "jolt":
            raise FeedError("gave up on the Jolt feed: HTTP 503")
        return replayed[config.id]

    monkeypatch.setattr(run, "run_operator", fake)
    assert run.main(["--live", "all"]) == run.EXIT_SOME_FAILED
    shown = capsys.readouterr()
    registry = load_registry()
    enabled = sorted(i for i, c in registry.items() if c.enabled)
    # PoGo Charge, Evolt Network and ChargePlace Scotland share a host, so they are one
    # group; every other enabled operator today is on a host of its own.
    groups = run.host_groups([registry[i] for i in enabled])
    assert ["chargeplace_scotland", "evolt", "pogo_charge"] in [[c.id for c in g] for g in groups]
    listed = "; ".join(", ".join(c.id for c in group) for group in groups)
    assert f"no two groups share a host: {listed}" in shown.out
    assert "jolt: failed after 0 s (the error follows)" in shown.out
    assert "Error: gave up on the Jolt feed: HTTP 503" in shown.err
    assert f"{len(enabled) - 1} fetched, 1 failed (jolt)" in shown.out


def test_a_half_set_relay_fails_that_operator_only(monkeypatch, capsys):
    monkeypatch.setenv("OEVM_RELAY_URL", RELAY)
    monkeypatch.delenv("OEVM_RELAY_TOKEN", raising=False)
    replayed = {r.operator_id: r for r in run.run_fixtures(load_registry())}
    capsys.readouterr()
    fetched = []

    def fake(config, **kwargs):
        fetched.append(config.id)
        return replayed[config.id]

    monkeypatch.setattr(run, "run_operator", fake)
    assert run.main(["--live", "all"]) == run.EXIT_SOME_FAILED
    shown = capsys.readouterr()
    assert "geniepoint" not in fetched and {"chargy", "jolt"} <= set(fetched)
    assert "geniepoint: failed after 0 s (the error follows)" in shown.out
    assert "the relay needs OEVM_RELAY_TOKEN as well" in shown.err


def test_fixture_runs_print_no_progress(capsys):
    assert run.main(["--fixtures"]) == 0
    shown = capsys.readouterr().out
    assert "one at a time" not in shown and "starting," not in shown
    assert "Fetching " not in shown and "finished in" not in shown
    # The report's own module lines are indented; progress lines are not.
    progress_line = r"^(\S+ )?(locations|tariffs): (page \d|done, |incomplete, )"
    assert not re.search(progress_line, shown, re.MULTILINE)
