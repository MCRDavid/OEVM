"""PLUG Charging's keyed OCPI 2.2.1 feed, read by the ocpi_221 adapter (no network)."""

import json
from collections import Counter
from pathlib import Path

import httpx

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "plug_charging"
FAKE = "test-value-plug"  # made-up key; the real one comes from the environment


class HeaderRecorder(ReplayTransport):
    """Replays the fixtures and keeps the Authorization header of each request."""

    def __init__(self, directory: Path):
        super().__init__(directory)
        self.authorization: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.authorization.append(request.headers.get("authorization"))
        return super().handle_request(request)


def replay():
    config = load_registry()["plug_charging"]
    transport = HeaderRecorder(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None, key=FAKE) as client:
        return fetch(config, client), transport


def test_each_module_is_read_in_one_request_with_the_key_as_a_token():
    result, transport = replay()
    assert transport.requested == [
        "https://plugcharging.co.uk/ocpi/2.2.1/locations",
        "https://plugcharging.co.uk/ocpi/2.2.1/tariffs",
    ]
    assert transport.authorization == [f"Token {FAKE}"] * 2
    assert result.complete
    assert result.modules["locations"].total_reported == 8
    assert result.modules["tariffs"].total_reported == 6


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 8
    assert all(location.id.startswith("plug_charging:GB:PLG:") for location in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {
        "available",
        "charging",
        "inoperative",
        "out_of_order",
        "removed",
        "unknown",
    }
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    hours = {loc.opening_hours.twenty_four_seven for loc in result.locations}
    assert hours == {True, False}


def test_single_phase_connectors_with_no_amperage_have_unknown_power():
    result, _ = replay()
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    unknown = [c for c in connectors if c.max_kw is None]
    assert len(unknown) == 2 and {c.power_type for c in unknown} == {"ac_1_phase"}
    assert {c.max_kw for c in connectors if c.power_type == "ac_3_phase"} == {22.0}
    assert result.issues == ["connector power not calculated for power_type 'ac_1_phase' (2 times)"]


def test_prices_show_in_pounds_and_pence_including_vat_and_missing_tariffs_are_unknown():
    result, _ = replay()
    found = {tariff.id for tariff in result.tariffs}
    for tariff in result.tariffs:
        shown = describe_tariff(tariff)
        assert shown.state == "priced" and "per kWh including VAT" in shown.text
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    missing = [c for c in connectors if not set(c.tariff_ids) & found]
    # Tariff 134 is named but not in the tariffs module; one connector names no tariff.
    assert sorted(t for c in missing for t in c.tariff_ids) == ["plug_charging:GB:PLG:134"] * 4
    assert sum(1 for c in missing if not c.tariff_ids) == 1


def test_the_fixtures_hold_no_key_or_credential():
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "Token " not in text and "authorization" not in text.lower(), path.name
        assert "status_code" in json.loads(text).get("response", {"status_code": 0})


def test_plug_charging_records_its_licence_key_and_rate_limit():
    config = load_registry()["plug_charging"]
    assert config.adapter == "ocpi_221" and config.enabled
    assert config.licence.name == "OGL-3.0"
    assert "do not restrict how you use the data" in " ".join(config.licence.basis.split())
    assert config.auth.secret_name == "PLUG_CHARGING_TOKEN" and config.auth.scheme == "Token"
    (limit,) = config.rate_limit.limits
    assert (limit.requests, limit.per_seconds) == (120, 60)
    assert config.rate_limit.min_seconds_between_requests >= limit.min_interval + 1
    assert config.access_granted.isoformat() == "2026-10-23"
