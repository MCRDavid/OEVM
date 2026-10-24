"""Fastned's keyed UK Open Data API, OCPI 2.2.1, read by the ocpi_221 adapter (no network)."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from adapters.replay import ReplayTransport
from pipeline import publish, run
from pipeline.geography import place_in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "fastned"
FAKE = "test-value-fastned"  # made-up key; the real one comes from the environment
WHEN = datetime(2026, 10, 24, 23, 0, tzinfo=UTC)


class HeaderRecorder(ReplayTransport):
    """Replays the fixtures and keeps the key headers of each request."""

    def __init__(self, directory: Path):
        super().__init__(directory)
        self.api_key: list[str | None] = []
        self.authorization: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.api_key.append(request.headers.get("x-api-key"))
        self.authorization.append(request.headers.get("authorization"))
        return super().handle_request(request)


def replay():
    config = load_registry()["fastned"]
    transport = HeaderRecorder(FIXTURES)
    result = run.run_operator(config, transport=transport, sleep=lambda _s: None, key=FAKE)
    return result, transport


def connectors(result):
    return [c for loc in result.locations for e in loc.evses for c in e.connectors]


def test_each_module_is_read_in_one_request_with_the_key_in_its_own_header():
    result, transport = replay()
    assert transport.requested == [
        "https://uk-public.api.fastned.nl/uk-public/ocpi/cpo/2.2.1/locations",
        "https://uk-public.api.fastned.nl/uk-public/ocpi/cpo/2.2.1/tariffs",
    ]
    assert transport.api_key == [FAKE] * 2  # the key alone, with no scheme before it
    assert transport.authorization == [None] * 2
    assert result.complete and result.issues == []
    assert result.modules["locations"].total_reported == 7
    assert result.modules["tariffs"].total_reported == 1


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 7
    assert all(location.id.startswith("fastned:GB:FAS:") for location in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {
        "available",
        "blocked",
        "charging",
        "out_of_order",
        "removed",
        "unknown",
    }
    power = Counter((c.power_type, c.max_kw) for c in connectors(result))
    assert {kind for kind, _kw in power} == {"ac_3_phase", "dc"}
    assert {kw for kind, kw in power if kind == "dc"} == {50.0, 100.0, 150.0, 175.0, 300.0, 400.0}
    assert {kw for kind, kw in power if kind == "ac_3_phase"} == {22.0, 38.0, 43.0}
    assert all(loc.opening_hours.twenty_four_seven for loc in result.locations)


def test_every_location_is_genuinely_in_the_uk_including_northern_ireland():
    result, _ = replay()
    for location in result.locations:
        point = location.coordinates
        assert place_in_uk(point.latitude, point.longitude, location.address.postal_code)
    (antrim,) = [loc for loc in result.locations if loc.id == "fastned:GB:FAS:51031"]
    assert antrim.address.postal_code.startswith("BT")


def test_prices_show_in_pounds_and_pence_including_vat_and_never_as_free():
    result, _ = replay()
    (tariff,) = result.tariffs
    assert tariff.currency == "GBP"
    shown = describe_tariff(tariff)
    assert shown.state == "priced" and shown.text == "79p per kWh including VAT"
    assert all(c.tariff_ids == [tariff.id] for c in connectors(result))


def test_the_postcode_finding_is_shown_as_published():
    """Finding of 2026-10-24: King's Lynn site with an LE postcode, nothing corrected."""
    result, _ = replay()
    (site,) = [loc for loc in result.locations if loc.id == "fastned:GB:FAS:51040"]
    assert site.address.city == "King's Lynn"
    assert site.address.postal_code == "LE34 3LW"


def test_removed_chargers_have_no_evse_id_and_their_locations_stay():
    """Finding of 2026-10-24: removed EVSEs carry no evse_id; they show as out of service."""
    result, _ = replay()
    evses = [e for loc in result.locations for e in loc.evses]
    removed = [e for e in evses if e.status == "removed"]
    assert len(removed) == 11 and all(e.evse_id is None for e in removed)
    assert all(e.evse_id for e in evses if e.status != "removed")
    assert all(any(e.status != "removed" for e in loc.evses) for loc in result.locations)


def test_published_files_carry_the_adapted_attribution_and_no_logo(tmp_path):
    operators = load_registry()
    result, _ = replay()
    publish.publish([result], operators, tmp_path, mode="fixtures", generated_at=WHEN)
    data = tmp_path / "data"
    statement = " ".join(operators["fastned"].attribution.split())
    assert statement.endswith("Open Government Licence v3.0. Adapted from Fastned's data.")
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["operators"]["fastned"]["attribution"] == statement
    layer = json.loads((data / "locations.geojson").read_text(encoding="utf-8"))
    assert statement in layer["attribution"]
    # The feed's operator object links a Fastned logo; only the operator's name is kept.
    for path in [data / "locations.geojson", *(data / "loc").rglob("*.json")]:
        text = path.read_text(encoding="utf-8")
        assert "logo" not in text and "presspage" not in text, path.name
        if path.parent.parent.name == "loc":
            assert statement in text, path.name


def test_the_fixtures_hold_no_key_or_credential():
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "x-api-key" not in text.lower() and "authorization" not in text.lower(), path.name
        assert "status_code" in json.loads(text).get("response", {"status_code": 0})


def test_fastned_records_its_policy_key_and_rate_limit():
    config = load_registry()["fastned"]
    assert config.adapter == "ocpi_221" and config.enabled
    assert config.licence.name == "OGL-3.0"
    basis = " ".join(config.licence.basis.split())
    assert "ADR 0028" in basis and "2026-10-24" in basis
    assert config.auth.method == "header" and config.auth.name == "x-api-key"
    assert config.auth.scheme is None
    assert config.auth.secret_name == "FASTNED_API_KEY"  # pragma: allowlist secret
    assert config.rate_limit.limits == []  # Fastned publishes no numeric limit
    assert config.rate_limit.min_seconds_between_requests >= 2
    assert config.access_granted.isoformat() == "2026-10-24"
