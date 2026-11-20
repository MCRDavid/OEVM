"""Go Zero's no-key OCPI 2.2.1 feed, read by the ocpi_221 adapter (no network)."""

import json
from collections import Counter
from pathlib import Path

import httpx

from adapters.replay import ReplayTransport
from pipeline import refresh, run
from pipeline.geography import place_in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "go_zero"
LOCATIONS = "https://ocpi.gozerocharge.com/api/v1/ocpi/2.2.1/locations"
TARIFFS = "https://ocpi.gozerocharge.com/api/v1/ocpi/2.2/tariffs"


class HeaderRecorder(ReplayTransport):
    """Replays the fixtures and keeps the authorisation header of each request."""

    def __init__(self, directory: Path):
        super().__init__(directory)
        self.authorization: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.authorization.append(request.headers.get("authorization"))
        return super().handle_request(request)


def replay():
    config = load_registry()["go_zero"]
    transport = HeaderRecorder(FIXTURES)
    result = run.run_operator(config, transport=transport, sleep=lambda _s: None)
    return result, transport


def location(result, ocpi_id: str):
    (found,) = [loc for loc in result.locations if loc.id == f"go_zero:GB:GOZ:{ocpi_id}"]
    return found


def connectors(result):
    return [c for loc in result.locations for e in loc.evses for c in e.connectors]


def test_each_module_is_read_in_one_request_with_no_key():
    result, transport = replay()
    assert transport.requested == [LOCATIONS, TARIFFS]
    assert transport.authorization == [None, None]
    assert result.complete and result.issues == []
    assert result.modules["locations"].total_reported == 11
    assert result.modules["tariffs"].total_reported == 11


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 11
    assert all(loc.id.startswith("go_zero:GB:GOZ:") for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {"available", "charging", "out_of_order", "inoperative"}
    power = {(c.power_type, c.max_kw, c.standard) for c in connectors(result)}
    assert power == {
        ("ac_1_phase", 7.4, "IEC_62196_T2"),
        ("ac_3_phase", 22.0, "IEC_62196_T2"),
        ("dc", 30.0, "IEC_62196_T2_COMBO"),
        ("dc", 40.0, "IEC_62196_T2_COMBO"),
        ("dc", 50.0, "IEC_62196_T2_COMBO"),
    }
    steamship = location(result, "141076")
    assert len(steamship.evses) == 4
    assert all(loc.opening_hours.twenty_four_seven for loc in result.locations)
    assert all(e.evse_id.startswith("GB*GOZ*E") for loc in result.locations for e in loc.evses)


def test_every_location_is_genuinely_in_the_uk_including_the_outer_hebrides():
    result, _ = replay()
    for loc in result.locations:
        point = loc.coordinates
        assert place_in_uk(point.latitude, point.longitude, loc.address.postal_code), loc.id
    assert location(result, "154126").address.postal_code == "HS6 5EJ"


def test_prices_add_the_stated_vat_to_whole_pence_and_are_never_free():
    result, _ = replay()
    assert len(result.tariffs) == 11
    shown = {t.id.removeprefix("go_zero:GB:GOZ:"): describe_tariff(t) for t in result.tariffs}
    assert all(t.currency == "GBP" for t in result.tariffs)
    assert all(d.state == "priced" for d in shown.values())
    # 0.55 with VAT 20 is 66p; 0.4666... is 56p; 0.65 is 78p; 0.18333... is 22p.
    expected = {"TARIFF-141076": 66, "TARIFF-141052": 56, "TARIFF-153874": 78}
    expected |= {"TARIFF-220384": 22, "TARIFF-238647": 40}
    for tariff_id, pence in expected.items():
        text = shown[tariff_id].text
        assert text.count(f"{pence}p per kWh") == 2 and text.endswith("including VAT"), text
    assert not any("Free" in d.text for d in shown.values())
    assert all(len(c.tariff_ids) == 1 for c in connectors(result))


def test_the_ocpi_2_1_1_type_field_is_not_read_as_a_parking_type():
    """Finding of 2026-11-20: "type": "PARKING_LOT" instead of parking_type."""
    raw = json.loads((FIXTURES / "locations_page1.json").read_text(encoding="utf-8"))
    records = raw["response"]["body"]["data"]
    assert {r["type"] for r in records} == {"PARKING_LOT"}
    assert not any("parking_type" in r for r in records)
    result, _ = replay()
    assert all(loc.parking_type is None for loc in result.locations)


def test_the_address_quirks_are_shown_as_published():
    """Finding of 2026-11-20: mistyped postcodes, a city with its postcode, a leading space."""
    result, _ = replay()
    assert location(result, "153874").address.postal_code == "S021 2EE"
    assert location(result, "191698").address.postal_code == "G639PT"
    assert location(result, "215443").address.city == "Kinross KY13 9LY"
    assert location(result, "141066").name == " EdenMill Farm Ltd"


def test_the_hourly_refresh_reads_only_the_locations_module():
    config = load_registry()["go_zero"]
    assert refresh.refreshable(config)
    transport = HeaderRecorder(FIXTURES)
    result = refresh.refresh_operator(config, transport=transport, sleep=lambda _s: None)
    assert transport.requested == [LOCATIONS]
    assert result.complete and result.requests == 1
    evses = [e for found in result.statuses.values() for e in found]
    assert len(result.statuses) == 11 and len(evses) == 24
    assert {e.status for e in evses} == {"available", "charging", "out_of_order", "inoperative"}


def test_the_fixtures_hold_no_key_or_credential():
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "authorization" not in text.lower() and "token" not in text.lower(), path.name


def test_go_zero_records_its_open_feed_and_the_projects_own_gap():
    config = load_registry()["go_zero"]
    assert config.enabled and config.adapter == "ocpi_221"
    assert config.engagement.status == "open_anonymous"
    assert config.auth.method == "none" and config.auth.secret_name is None
    assert config.rate_limit.limits == []  # Go Zero publishes no limit
    assert config.rate_limit.min_seconds_between_requests == 2
    assert config.endpoints["locations"].url == LOCATIONS
    assert config.endpoints["locations"].status == "documented"
    # The tariffs address is the earlier page's path on today's host, so it needs testing.
    assert config.endpoints["tariffs"].url == TARIFFS
    assert config.endpoints["tariffs"].status == "needs_testing"
    assert (config.ocpi_country_code, config.ocpi_party_id) == ("GB", "GOZ")
    assert config.licence.name == "OGL-3.0" and str(config.licence.checked) == "2026-11-20"
    assert "2026-10-10" in " ".join(config.licence.basis.split())
