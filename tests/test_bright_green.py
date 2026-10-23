"""BrightGreen's feed: OCPI response objects whose records differ from OCPI 2.2.1 in several
ways, each recorded as unknown rather than guessed (no network). Recorded, not switched on,
while it is open whether its prices already include VAT."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "bright_green"
FEED = "https://connect.bright.green/ocpp"


def replay():
    config = load_registry()["bright_green"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [f"{FEED}/locations", f"{FEED}/tariffs"]
    assert result.complete


def test_unpublished_and_unplaceable_locations_are_not_kept():
    # 15 sent: 5 marked publish false, and one with no coordinates.
    result, _ = replay()
    assert len(result.locations) == 9
    names = {loc.name for loc in result.locations}
    assert "Software Room" not in names and "Nabito Lab" not in names
    assert any("publish is false (5 times)" in issue for issue in result.issues)
    assert any("missing field 'coordinates'" in issue for issue in result.issues)


def test_values_outside_ocpi_are_recorded_as_unknown():
    result, _ = replay()
    evses = [e for loc in result.locations for e in loc.evses]
    connectors = [c for e in evses for c in e.connectors]
    assert Counter(e.status for e in evses) == {"unknown": len(evses)}
    assert {c.power_type for c in connectors} == {"unknown"}
    assert {c.standard for c in connectors} == {"unknown"}
    assert any("'idle'" in issue for issue in result.issues)


def test_ids_use_the_feeds_country_and_an_unknown_party():
    result, _ = replay()
    assert all(loc.id.startswith("bright_green:") for loc in result.locations)
    assert {loc.id.split(":")[2] for loc in result.locations} == {"unknown"}


def test_only_uk_points_are_mapped():
    result, _ = replay()
    outside = {loc.name for loc in result.locations if not in_uk(loc)}
    assert outside == {"Nabito Chropynska"}


def test_prices_written_as_text_are_read_and_other_currencies_are_unknown():
    result, _ = replay()
    shown = {tariff.id: describe_tariff(tariff) for tariff in result.tariffs}
    eur = [t for t in result.tariffs if t.currency == "EUR"]
    assert len(eur) == 1 and shown[eur[0].id].text == "Price unknown"
    gbp = [shown[t.id] for t in result.tariffs if t.currency == "GBP"]
    assert all(d.state == "priced" and "including VAT" in d.text for d in gbp)


def test_stays_switched_off_while_its_vat_question_is_open():
    config = load_registry()["bright_green"]
    assert not config.enabled
    assert config.licence.checked
    assert any("price_display" in finding.summary for finding in config.findings)
