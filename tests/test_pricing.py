"""Tests for pipeline/pricing.py: prices are only ever shown in pounds and pence."""

import json
from pathlib import Path

import pytest

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import describe_tariff, pence, pounds
from pipeline.registry import load_registry
from schema.models import Tariff

FIXTURES = Path(__file__).parent / "fixtures"


def tariff(currency="GBP", components=None, restrictions=None, **extra) -> Tariff:
    components = components or [{"type": "energy", "price": 0.45, "vat": None, "step_size": 1}]
    return Tariff.model_validate(
        {
            "id": "example:GB:EXA:T1",
            "currency": currency,
            "elements": [{"price_components": components, "restrictions": restrictions}],
            "provenance": json.loads((FIXTURES / "normalised" / "tariff.json").read_text())[
                "provenance"
            ],
            **extra,
        }
    )


def energy(price, vat=None):
    return {"type": "energy", "price": price, "vat": vat, "step_size": 1}


@pytest.mark.parametrize(
    ("amount", "expected"), [(0.45, "45p"), (0.4917, "49.2p"), (0.325, "32.5p"), (0, "0p")]
)
def test_pence(amount, expected):
    assert pence(amount) == expected


def test_pounds():
    assert pounds(1.5) == "£1.50"
    assert pounds(0.005) == "£0.01"


def test_vat_is_added_only_when_stated():
    assert describe_tariff(tariff(components=[energy(0.45, vat=20)])).text == (
        "54p per kWh including VAT"
    )
    assert describe_tariff(tariff(components=[energy(0.45)])).text == (
        "45p per kWh (VAT not stated)"
    )


def test_mixed_vat_shows_all_prices_excluding_vat():
    shown = describe_tariff(tariff(components=[energy(0.45, vat=20), energy(0.30)]))
    assert shown.text == "30p to 45p per kWh (VAT not stated)"


def test_other_charges_are_shown_in_pounds():
    shown = describe_tariff(
        tariff(
            components=[
                energy(0.5),
                {"type": "flat", "price": 1.0, "vat": None, "step_size": 1},
                {"type": "parking_time", "price": 6.0, "vat": None, "step_size": 60},
            ]
        )
    )
    assert shown.text == (
        "50p per kWh, plus £1.00 per session, plus £6.00 per hour parked (VAT not stated)"
    )


def test_minimum_charge_is_shown_after_the_vat_note():
    shown = describe_tariff(tariff(components=[energy(0.45, vat=20)], min_price=2))
    assert shown.text == "54p per kWh including VAT; minimum charge £2.00 excluding VAT"


@pytest.mark.parametrize("currency", ["EUR", "USD"])
def test_other_currencies_are_never_converted(currency):
    shown = describe_tariff(tariff(currency=currency))
    assert shown.state == "unknown"
    assert shown.text == "Price unknown"
    assert currency in shown.reason and "never converted" in shown.reason


def test_a_zero_price_in_another_currency_is_not_shown_as_free():
    shown = describe_tariff(tariff(currency="EUR", components=[energy(0)]))
    assert shown.state == "unknown"


def test_free_only_for_a_confirmed_free_gbp_tariff():
    assert describe_tariff(tariff(components=[energy(0)])).text == "Free"
    assert describe_tariff(tariff(components=[energy(0)], min_price=1)).state == "priced"


def test_reservation_fees_are_not_shown_as_charging_prices():
    shown = describe_tariff(
        tariff(
            components=[{"type": "time", "price": 3.0, "vat": None, "step_size": 1}],
            restrictions={"reservation": "reservation"},
        )
    )
    assert shown.state == "unknown"


def test_recorded_chargy_tariffs_show_only_pounds_and_pence():
    config = load_registry()["chargy"]
    transport = ReplayTransport(FIXTURES / "chargy")
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        result = fetch(config, client, page_size=2, max_pages=2)
    shown = {t.currency: describe_tariff(t) for t in result.tariffs}

    assert shown["GBP"].text == "32.5p to 49.2p per kWh (VAT not stated)"
    assert shown["EUR"].text == shown["USD"].text == "Price unknown"
    for display in shown.values():
        assert "€" not in display.text and "$" not in display.text
