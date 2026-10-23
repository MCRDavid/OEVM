"""Tests for the Monta adapter (adapters/monta.py) and the token request it uses.

No test touches the network. tests/fixtures/monta/ holds made-up responses in the real
feed's shape (no real record is kept: Monta's records name site owners). Made-up
responses (httpx.MockTransport) cover the token request, HTTP 500 answers and paging.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from adapters import monta
from adapters.http import FeedError, PoliteClient
from adapters.replay import ReplayTransport
from pipeline import run
from pipeline.registry import load_registry
from schema.operator import OperatorConfig

FIXTURES = Path(__file__).parent / "fixtures" / "monta"
NOW = datetime(2026, 10, 23, 0, 0, tzinfo=UTC)
API = "https://public-api.monta.com/api/v1"
FAKE = "test-value-monta"  # made-up client id and secret; real ones come from the environment
TOKEN = "made-up-access-token"


class Recorder:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def config(**update) -> OperatorConfig:
    return load_registry()["monta"].model_copy(update=update)


def site(cursor: int, status: str = "AVAILABLE", **extra) -> dict:
    """A made-up site whose lowest charge point id is cursor."""
    return {
        "country_code": "DK",
        "party_id": "MON",
        "id": f"s{cursor}",
        "publish": True,
        "name": f"Example Site {cursor}",
        "address": "1 Example Road",
        "city": "Manchester",
        "postal_code": "M1 1AE",
        "country": "GBR",
        "coordinates": {"latitude": "53.47740", "longitude": "-2.23090"},
        "owner": {"name": "A Private Person", "website": None, "logo": None},
        "operator": {"name": "Monta ApS", "website": "https://monta.com", "logo": None},
        "evses": [
            {
                "uid": str(cursor),
                "status": status,
                "connectors": [
                    {
                        "id": "1",
                        "standard": "IEC_62196_T2",
                        "format": "SOCKET",
                        "power_type": "AC_3_PHASE",
                        "max_electric_power": 22000,
                        "tariff_ids": ["1"],
                        "last_updated": "2026-10-21T08:30:00Z",
                    }
                ],
                "tariffs": [],
                "last_updated": "2026-10-21T08:30:00Z",
            }
        ],
        "last_updated": "2026-10-21T08:30:00Z",
        **extra,
    }


class Server:
    """Serves made-up sites by cursor, as Monta does, answering HTTP 500 for any page that
    holds a site in `broken`."""

    def __init__(self, cursors: list[int], broken: frozenset[int] = frozenset(), **kwargs):
        self.sites = {c: site(c) for c in cursors}
        self.broken = broken
        self.token_status = kwargs.get("token_status", 200)
        self.token_body = kwargs.get("token_body", {"accessToken": TOKEN})
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/auth/token"):
            return httpx.Response(self.token_status, json=self.token_body)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.url.params["group_by_location"] == "true"
        after = int(request.url.params.get("after", 0))
        size = int(request.url.params["per_page"])
        rows = [c for c in sorted(self.sites) if c > after][:size]
        if any(c in self.broken for c in rows):
            return httpx.Response(
                500, json={"message": "An unexpected error occurred", "errorCode": "UNKNOWN"}
            )
        more = bool(rows) and any(c > rows[-1] for c in self.sites)
        pagination = {"after": rows[-1] if rows else None, "has_more": more}
        body = {"data": [self.sites[c] for c in rows], "meta": {"pagination": pagination}}
        return httpx.Response(200, json=body)

    def gets(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "GET"]


def run_with(handler, cfg: OperatorConfig | None = None, sleep=None, **kwargs):
    cfg = cfg or config()
    transport = httpx.MockTransport(handler)
    with PoliteClient(
        cfg, transport=transport, sleep=sleep or Recorder(), clock=lambda: 0, key=FAKE
    ) as client:
        return monta.fetch(cfg, client, now=NOW, **kwargs)


# The registry file


def test_operator_file_uses_a_token_request_and_both_secrets():
    cfg = config()
    assert cfg.adapter == "custom"
    assert cfg.auth.method == "client_credentials"
    assert cfg.auth.token_url == f"{API}/auth/token"
    assert cfg.auth.secret_names == ("MONTA_CLIENT_ID", "MONTA_CLIENT_SECRET")
    # 10 requests a minute across a user's applications, plus the project's 1 second.
    assert cfg.rate_limit.min_seconds_between_requests >= 7
    assert run.CUSTOM_ADAPTERS["monta"] is monta.fetch


# The token request


def test_the_token_request_posts_the_client_id_and_secret_then_sends_the_token():
    server = Server([1, 2])
    result = run_with(server)
    token_request = server.requests[0]
    assert token_request.method == "POST"
    assert str(token_request.url) == f"{API}/auth/token"
    assert json.loads(token_request.content) == {"clientId": FAKE, "clientSecret": FAKE}
    assert "Authorization" not in token_request.headers
    assert len(result.locations) == 2  # every later request checked the Bearer token


@pytest.mark.parametrize(
    ("status", "body"),
    [(401, {"message": "Unauthorized"}), (200, {"refreshToken": "x"}), (200, ["not", "a", "map"])],
    ids=["refused", "no-access-token", "not-an-object"],
)
def test_no_token_stops_the_fetch(status, body):
    server = Server([1], token_status=status, token_body=body)
    with pytest.raises(FeedError, match="token request"):
        run_with(server)
    assert server.gets() == []


def test_the_token_is_never_shown():
    server = Server([1, 2, 3], broken=frozenset({2}))
    result = run_with(server)
    shown = json.dumps([p.body for p in result.modules["locations"].pages]) + str(result.issues)
    assert TOKEN not in shown
    assert FAKE not in shown


def test_requests_are_at_least_seven_seconds_apart():
    sleep = Recorder()
    server = Server(list(range(1, 251)))
    run_with(server, sleep=sleep)
    # The clock never moves, so the client waits the whole gap before every request after
    # the first, the token request included.
    assert len(server.requests) == 4
    assert sleep.sleeps == [config().rate_limit.min_seconds_between_requests] * 3


def test_a_missing_secret_stops_before_any_request(monkeypatch):
    monkeypatch.delenv("MONTA_CLIENT_ID", raising=False)
    monkeypatch.setenv("MONTA_CLIENT_SECRET", "not-used")
    with pytest.raises(FeedError, match="MONTA_CLIENT_ID is not set"):
        PoliteClient(config(), transport=httpx.MockTransport(Server([1])))


# Reading the list


def test_reads_every_page_and_removes_owner_names():
    server = Server(list(range(1, 251)))
    result = run_with(server)
    locations = result.modules["locations"]
    assert locations.complete and result.complete
    assert len(locations.records) == 250 and len(result.locations) == 250
    assert [r.url.params.get("after") for r in server.gets()] == [None, "100", "200"]
    assert all("owner" not in record for record in locations.records)
    assert "A Private Person" not in json.dumps([p.body for p in locations.pages])
    assert result.locations[0].id == "monta:DK:MON:s1"
    assert result.locations[0].operator.name == "Monta ApS"


def test_sites_with_every_charger_removed_are_not_kept():
    server = Server([1, 2, 3])
    server.sites[2] = site(2, status="REMOVED")
    server.sites[3] = site(3, evses=[])
    result = run_with(server)
    assert [loc.id for loc in result.locations] == ["monta:DK:MON:s1"]
    assert result.dropped_location_ids == ["monta:DK:MON:s2", "monta:DK:MON:s3"]
    assert any(
        "no EVSE that is not REMOVED" in issue and "2 times" in issue for issue in result.issues
    )


def test_a_failing_page_is_asked_for_in_smaller_pages_then_bigger_again():
    server = Server(list(range(1, 81)))
    failed = []

    def once(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and not failed:
            failed.append(request)
            return httpx.Response(500, json={"message": "An unexpected error occurred"})
        return server(request)

    result = run_with(once)
    assert failed[0].url.params["per_page"] == "100"
    # Five good pages of 10, then pages of 100 again.
    assert [r.url.params["per_page"] for r in server.gets()] == ["10"] * 5 + ["100"]
    assert len(result.locations) == 80
    assert result.complete


def test_a_site_the_server_cannot_send_is_skipped_and_the_fetch_marked_incomplete():
    cursors = [5, 9, 20, 400, 401, 9000, 9100, 12000]
    server = Server(cursors, broken=frozenset({400, 9100}))
    result = run_with(server)
    kept = sorted(int(loc.id.rsplit(":s", 1)[1]) for loc in result.locations)
    assert kept == [5, 9, 20, 401, 9000, 12000]
    assert not result.modules["locations"].complete
    assert "skipped 2 time(s) past sites the server answered HTTP 500 for" in " ".join(
        result.issues
    )


def test_failing_sites_next_to_each_other_are_passed_in_one_skip():
    server = Server([1, 2, 3, 4], broken=frozenset({2, 3}))
    result = run_with(server)
    assert [loc.id for loc in result.locations] == ["monta:DK:MON:s1", "monta:DK:MON:s4"]
    assert "skipped 1 time(s)" in " ".join(result.issues)


def test_skipping_stops_after_the_most_sites_allowed(monkeypatch):
    monkeypatch.setattr(monta, "MAX_SKIPS", 1)
    server = Server([1, 2, 3, 4, 5], broken=frozenset({2, 4}))
    result = run_with(server)
    assert [loc.id for loc in result.locations] == ["monta:DK:MON:s1", "monta:DK:MON:s3"]
    assert any("stopped after skipping 1 times" in issue for issue in result.issues)
    assert not result.complete


def test_the_run_stops_at_the_request_limit(monkeypatch):
    monkeypatch.setattr(monta, "MAX_REQUESTS", 3)
    result = run_with(Server(list(range(1, 501))))
    assert len(result.locations) == 200
    assert any("stopped after 3 requests" in issue for issue in result.issues)
    assert not result.complete


def test_max_pages_limits_the_pages_read():
    result = run_with(Server(list(range(1, 501))), max_pages=2)
    assert len(result.modules["locations"].pages) == 2
    assert not result.complete


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(403, json={"message": "Forbidden"}),
        httpx.Response(200, json={"items": []}),
        httpx.Response(200, json={"data": [site(5)], "meta": {"pagination": {"has_more": True}}}),
    ],
    ids=["refused", "no-data-list", "no-cursor"],
)
def test_unexpected_answers_stop_the_fetch(answer):
    server = Server([1])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return answer
        return server(request)

    with pytest.raises(FeedError):
        run_with(handler)


def test_a_cursor_that_does_not_move_forward_stops_the_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"accessToken": TOKEN})
        body = {"data": [site(5)], "meta": {"pagination": {"after": 5, "has_more": True}}}
        return httpx.Response(200, json=body)

    with pytest.raises(FeedError, match="does not move forward"):
        run_with(handler)


def test_rejects_options_the_feed_does_not_have():
    with pytest.raises(FeedError):
        run_with(Server([1]), page_size=10)


# The made-up fixtures, as the offline pipeline replays them


def test_fixture_replay_keeps_published_current_sites_only():
    cfg = config()
    with PoliteClient(
        cfg, transport=ReplayTransport(FIXTURES), sleep=Recorder(), clock=lambda: 0, key=FAKE
    ) as client:
        result = monta.fetch(cfg, client, now=NOW)
    ids = [loc.id for loc in result.locations]
    assert ids == ["monta:DK:MON:s1001", "monta:GB:EXN:s1012", "monta:DK:MON:s1020"]
    assert result.complete and result.tariffs == []
    assert result.locations[1].operator.name == "Example Network"
    issues = " ".join(result.issues)
    assert "publish is false" in issues and "no EVSE that is not REMOVED" in issues
    raw = json.dumps([p.body for p in result.modules["locations"].pages])
    assert "Example Owner Ltd" not in raw and "owner" not in raw
