"""BrightGreen's feed: OCPI response objects whose records differ from OCPI 2.2.1 in several
ways, each recorded as unknown rather than guessed (no network). Its prices are read as
including VAT and one missing minus sign is corrected, by the owner's decisions."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import VAT_IN_PRICE, describe_tariff
from pipeline.publish import corrected_coordinates
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


def test_prices_are_read_as_including_vat_by_the_owners_decision():
    config = load_registry()["bright_green"]
    assert config.enabled and config.licence.checked
    assert config.vat_in_price is not None and config.vat_not_stated is None
    result, _ = replay()
    gbp = [t for t in result.tariffs if t.currency == "GBP"]
    shown = [describe_tariff(t, added_vat=VAT_IN_PRICE).text for t in gbp]
    assert any(text.startswith("59p per kWh ") for text in shown)
    assert not any("70.8p" in text for text in shown)
    in_price = "reading the VAT rate the feed states as already in the price"
    assert all(in_price in text for text in shown)
    # Without the decision, OCPI's reading adds the stated 20%.
    assert any("70.8p" in describe_tariff(t).text for t in gbp)


def test_the_named_missing_minus_sign_is_corrected():
    config = load_registry()["bright_green"]
    result, _ = replay()
    kiln = next(loc for loc in result.locations if loc.name == "Kiln Farm Station")
    assert in_uk(kiln) and kiln.coordinates.longitude > 0  # in Suffolk as published
    moved, correction = corrected_coordinates(kiln, config)
    assert moved.coordinates.longitude == -kiln.coordinates.longitude
    assert correction.published == kiln.coordinates
    assert "postcode" in correction.note
    others = [loc for loc in result.locations if loc.name != "Kiln Farm Station" and in_uk(loc)]
    assert all(corrected_coordinates(loc, config) is None for loc in others)
