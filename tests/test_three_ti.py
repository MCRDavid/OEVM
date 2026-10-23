"""3ti publishes one pair of OCPI 2.2.1 files per site on Fuuse's host, read by the ocpi_221
adapter through more_endpoints (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient, operator_hosts
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "three_ti"
HOST = "https://api.fuuse.io/opendata/"
SITES = [
    "c3947832-9352-41fa-96c1-831215eea8e0",  # Raigmore Hospital, Inverness
    "4a5b700e-6a15-40f3-92cc-dcc8732a92e0",  # Riverbridge House, Surrey
    "36bd06f3-5184-4939-a7a1-4c0c1dec5583",  # University of Surrey
    "542c7548-899e-43e8-854c-05fd0f76dc70",  # East Staffordshire Borough Council
    "6922c10c-4f17-4929-bf7a-32c4a6075277",  # Salford Royal Hospital
]
SEGEN = "6cd94287-a370-48ae-8079-a514a8ac2c7b"


def replay():
    config = load_registry()["three_ti"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_every_site_file_is_read_once_on_one_host():
    result, transport = replay()
    assert transport.requested == [f"{HOST}{site}/location" for site in SITES] + [
        f"{HOST}{site}/tariff" for site in SITES
    ]
    assert result.complete
    assert result.modules["locations"].total_reported == 6
    assert result.issues == []
    assert operator_hosts(load_registry()["three_ti"]) == {"api.fuuse.io"}


def test_segen_is_listed_but_not_read_while_it_answers_204():
    config = load_registry()["three_ti"]
    assert not any(SEGEN in url for url in config.feed_urls())
    assert any(SEGEN in source.note for source in config.sources)
    assert any(SEGEN in finding.evidence_url for finding in config.findings)


def test_each_location_keeps_the_file_it_came_from():
    result, _ = replay()
    sources = Counter(str(loc.provenance.source_url) for loc in result.locations)
    assert sources == Counter(
        {f"{HOST}{site}/location": 2 if site == SITES[-1] else 1 for site in SITES}
    )
    tariff_sources = {str(t.provenance.source_url) for t in result.tariffs}
    assert tariff_sources == {f"{HOST}{site}/tariff" for site in SITES}


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 6
    # The records carry no country_code or party_id, so the ids say unknown.
    assert all(loc.id.startswith("three_ti:unknown:unknown:") for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging"} <= set(statuses)
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    assert len(connectors) == 67
    assert {(c.standard, c.power_type) for c in connectors} == {("IEC_62196_T2", "ac_3_phase")}


def test_prices_given_as_strings_have_the_stated_vat_added():
    result, _ = replay()
    shown = {t.id.rsplit(":", 1)[1]: describe_tariff(t) for t in result.tariffs}
    assert all(s.state == "priced" for s in shown.values())
    # Raigmore Hospital: 0.2917 plus the stated 20% VAT, as 3ti's own page shows it.
    assert "35p per kWh" in shown["eca6de9f-e5ee-4b20-9786-f597cb96aacc"].text
    # University of Surrey: 0.5000 plus 20% VAT.
    assert "60p per kWh" in shown["caf84577-94ea-4bc5-af05-4c8384b47c7a"].text
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    assert {t for c in connectors for t in c.tariff_ids} == {t.id for t in result.tariffs}


def test_three_ti_records_its_source_and_terms():
    config = load_registry()["three_ti"]
    assert config.enabled and config.adapter == "ocpi_221" and config.auth.method == "none"
    assert len(config.more_endpoints) == 4
    assert config.licence.checked.isoformat() == "2026-10-23"
    assert "Terms of Service" in config.licence.basis
    assert config.rate_limit.min_seconds_between_requests == 31
    assert any(s.url == "https://3ti.co.uk/3ti-public-charge-points/" for s in config.sources)
