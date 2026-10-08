"""Tests for pipeline/pricing.py: prices are only ever shown in pounds and pence."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import describe_tariff, location_summary, pence, pounds
from pipeline.registry import load_registry
from pipeline.tariffs import ConnectorPrice
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
        "45p per kWh (excluding VAT, VAT not stated)"
    )


def test_mixed_vat_shows_all_prices_excluding_vat():
    shown = describe_tariff(tariff(components=[energy(0.45, vat=20), energy(0.30)]))
    assert shown.text == "30p to 45p per kWh (excluding VAT, VAT not stated)"


def test_a_free_extra_without_vat_does_not_hide_vat_on_the_real_price():
    shown = describe_tariff(
        tariff(
            components=[
                energy(0.45, vat=20),
                {"type": "flat", "price": 0, "vat": None, "step_size": 1},
            ]
        )
    )
    assert shown.text == "54p per kWh including VAT"


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        ([{"type": "flat", "price": 0.4125, "vat": 20, "step_size": 1}], "£0.50 per session"),
        ([{"type": "flat", "price": 1.90, "vat": 5, "step_size": 1}], "£2.00 per session"),
        ([energy(0.57, vat=5)], "59.9p per kWh"),
    ],
    ids=["half-penny-flat", "half-penny-low-vat", "half-tenth-penny-energy"],
)
def test_vat_maths_is_exact_and_rounds_half_up(components, expected):
    assert describe_tariff(tariff(components=components)).text == f"{expected} including VAT"


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
        "50p per kWh, plus £1.00 per session, plus £6.00 per hour parked "
        "(excluding VAT, VAT not stated)"
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

    assert shown["GBP"].text == (
        "45p per kWh at weekends, 32.5p per kWh from midnight to 07:00 on weekdays, "
        "49.2p per kWh from 07:00 to midnight on weekdays (excluding VAT, VAT not stated)"
    )
    assert shown["EUR"].text == shown["USD"].text == "Price unknown"
    for display in shown.values():
        assert "€" not in display.text and "$" not in display.text


def connector(state, low=None, high=None, vat=None):
    return ConnectorPrice(
        location_id="L",
        evse_uid="E",
        connector_id="1",
        state=state,
        text="",
        energy_low=None if low is None else Decimal(low),
        energy_high=None if high is None else Decimal(high),
        includes_vat=vat,
    )


@pytest.mark.parametrize(
    ("prices", "expected"),
    [
        ([], "Price unknown"),
        ([connector("free_confirmed")] * 2, "Free (confirmed)"),
        ([connector("unknown")], "Price unknown"),
        ([connector("priced", "0.45", "0.79", True)], "Energy 45p to 79p per kWh including VAT"),
        ([connector("priced", "0.5", "0.5", True)], "Energy 50p per kWh including VAT"),
        (
            [connector("priced", "0.4", "0.4", False)],
            "Energy 40p per kWh excluding VAT, VAT not stated",
        ),
        ([connector("priced")], "Priced: see details"),
        (
            [connector("free_confirmed"), connector("priced", "0.79", "0.79", True)],
            "Energy 79p per kWh including VAT; some connectors free (confirmed)",
        ),
        (
            [connector("free_confirmed"), connector("unknown")],
            "Some connectors free (confirmed); some prices unknown",
        ),
        (
            [connector("priced", "0.5", "0.6", True), connector("priced", "0.3", "0.3", False)],
            "Energy 50p to 60p per kWh including VAT; 30p per kWh excluding VAT, VAT not stated",
        ),
    ],
)
def test_location_summary_never_calls_a_mixed_location_free(prices, expected):
    assert location_summary(prices) == expected
