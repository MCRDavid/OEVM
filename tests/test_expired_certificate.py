"""Reading a feed past one expired certificate, only by the owner's decision (ADR 0021).

No network: the TLS connection is stood in for by an object that answers the same questions
httpx's network stream does.
"""

import ssl
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from adapters.http import (
    NO_CHECK_TIME,
    FeedError,
    PoliteClient,
    certificate_fingerprint,
    certificate_problem,
    expired_certificate_context,
)
from schema.operator import OperatorConfig

HOST = "data.example.com"
FEED = f"https://{HOST}/locations"
OTHER = "https://other.example.com/locations"
# Names the variable a key would be in; holds no key.
KEYED = {
    "method": "header",
    "name": "Authorization",
    "secret_name": "EXAMPLE_KEY",  # pragma: allowlist secret
}
PINNED = b"the expired certificate the owner accepted"
NOW = datetime(2026, 10, 11, 18, 0, tzinfo=UTC)
EXPIRED = {"notBefore": "Mar 23 07:59:07 2026 GMT", "notAfter": "Oct  7 07:59:07 2026 GMT"}
IN_DATE = {"notBefore": "Oct  9 00:00:00 2026 GMT", "notAfter": "Oct  9 00:00:00 2027 GMT"}


def decision(**overrides) -> dict:
    data = {
        "decided": "2026-10-11",
        "basis": "The certificate expired; the owner decided to read past it.",
        "evidence_url": "https://example.com/open-data",
        "host": HOST,
        "sha256": certificate_fingerprint(PINNED),
        "expired": "2026-10-07",
    }
    data.update(overrides)
    return data


def make_config(**overrides) -> OperatorConfig:
    data = {
        "id": "example_operator",
        "display_name": "Example Operator",
        "ocpi_country_code": "GB",
        "ocpi_party_id": "EXA",
        "adapter": "ocpi_221",
        "base_url": "unknown",
        "endpoints": {"locations": {"url": FEED, "status": "documented"}},
        "auth": {"method": "none"},
        "supports_single_location": "unknown",
        "cors": "unknown",
        "engagement": {"status": "unknown"},
        "expired_certificate": decision(),
        "enabled": False,
    }
    data.update(overrides)
    return OperatorConfig.model_validate(data)


class FakeTls:
    """Answers getpeercert as ssl.SSLSocket's own object does, positionally."""

    def __init__(self, der: bytes, details: dict):
        self.der, self.details = der, details

    def getpeercert(self, binary: bool = False):
        return self.der if binary else self.details


class FakeStream:
    def __init__(self, tls: FakeTls | None):
        self.tls = tls

    def get_extra_info(self, name: str):
        return self.tls if name == "ssl_object" else None


def client_for(der: bytes, details: dict, calls: list[str] | None = None) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        stream = FakeStream(FakeTls(der, details))
        return httpx.Response(200, json={"ok": True}, extensions={"network_stream": stream})

    return PoliteClient(
        make_config(),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
        wall_clock=lambda: NOW,
    )


def test_the_context_checks_chain_and_host_name_and_skips_only_dates():
    context = expired_certificate_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.verify_flags & NO_CHECK_TIME
    assert not ssl.create_default_context().verify_flags & NO_CHECK_TIME


def test_fingerprints_are_written_like_openssl():
    assert certificate_fingerprint(b"").startswith("E3:B0:C4:42:98:FC:1C:14:")
    assert len(certificate_fingerprint(b"x")) == 95


def test_only_the_accepted_certificate_or_one_in_date_passes():
    accepted = OperatorConfig.model_validate(
        make_config().model_dump(mode="json")
    ).expired_certificate
    assert certificate_problem(PINNED, EXPIRED, accepted, NOW) == (None, False)
    assert certificate_problem(b"renewed", IN_DATE, accepted, NOW) == (None, True)
    problem, renewed = certificate_problem(b"another expired one", EXPIRED, accepted, NOW)
    assert "is not in date and is not the one the operator file accepts" in problem
    assert not renewed
    assert certificate_problem(b"no dates", {}, accepted, NOW)[0].endswith("no readable dates")
    assert certificate_problem(None, {}, accepted, NOW)[0] == "the server presented no certificate"


def test_the_accepted_certificate_is_read_without_a_note():
    with client_for(PINNED, EXPIRED) as client:
        assert client.get(FEED).json() == {"ok": True}
        assert client.events == []


def test_another_expired_certificate_stops_the_fetch_without_retrying():
    calls: list[str] = []
    with (
        client_for(b"a different certificate", EXPIRED, calls) as client,
        pytest.raises(FeedError, match="not using the response"),
    ):
        client.get(FEED)
    assert calls == [FEED]


def test_a_renewed_certificate_is_used_and_says_the_decision_can_go():
    with client_for(b"renewed", IN_DATE) as client:
        client.get(FEED)
        client.get(FEED)
    assert client.events == [
        f"{HOST} now presents a certificate that is in date; the expired_certificate "
        "decision in the operator file can be removed"
    ]


def test_a_real_connection_without_a_readable_certificate_stops_the_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, extensions={"network_stream": FakeStream(None)})

    transport = httpx.MockTransport(handler)
    with (
        PoliteClient(make_config(), transport=transport, sleep=lambda _s: None) as client,
        pytest.raises(FeedError, match="could not read the TLS certificate"),
    ):
        client.get(FEED)


def test_recorded_responses_have_no_connection_to_check():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    with PoliteClient(
        make_config(), transport=httpx.MockTransport(handler), sleep=lambda _s: None
    ) as client:
        assert client.get(FEED).json() == {"ok": True}


def test_operators_without_the_decision_never_relax_dates():
    config = make_config(expired_certificate=None)
    with PoliteClient(config, transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        assert c._expired_certificate is None


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        (
            {"auth": KEYED},
            "only a feed that needs no key may be read past a certificate",
        ),
        (
            {"endpoints": {"locations": {"url": OTHER, "status": "documented"}}},
            "must be an https URL on data.example.com",
        ),
        (
            {"endpoints": {"locations": {"url": f"http://{HOST}/l", "status": "documented"}}},
            "must be an https URL on data.example.com",
        ),
        ({"expired_certificate": decision(sha256="49:82")}, "sha256"),
        ({"expired_certificate": decision(host="Data.Example.com")}, "host"),
    ],
)
def test_the_decision_is_refused_where_it_could_reach_further(overrides, problem):
    with pytest.raises(ValidationError, match=problem):
        make_config(**overrides)
