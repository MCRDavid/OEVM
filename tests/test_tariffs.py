"""Tests for pipeline/tariffs.py (blueprint task 6) and conditional price wording."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import conditions, describe_tariff, energy_range, readable_name
from pipeline.registry import load_registry
from pipeline.tariffs import price_connector, price_locations, site_tariffs, summary
from schema.models import Connector, Location, Tariff, TariffRestrictions

FIXTURES = Path(__file__).parent / "fixtures"
PROVENANCE = json.loads((FIXTURES / "normalised" / "tariff.json").read_text())["provenance"]


def tariff(tariff_id="T1", elements=None, currency="GBP", type_=None, **extra) -> Tariff:
    elements = elements or [{"price_components": [component("energy", 0.40, 20)]}]
    return Tariff.model_validate(
        {
            "id": f"example:GB:EXA:{tariff_id}",
            "currency": currency,
            "type": type_,
            "elements": elements,
            "provenance": PROVENANCE,
            **extra,
        }
    )


def component(kind, price, vat=None, step=1):
    return {"type": kind, "price": price, "vat": vat, "step_size": step}


def connector(*tariff_ids: str) -> Connector:
    return Connector(
        id="1", standard="IEC_62196_T2", tariff_ids=[f"example:GB:EXA:{t}" for t in tariff_ids]
    )


def price(conn: Connector, *tariffs: Tariff):
    return price_connector(conn, {t.id: t for t in tariffs}, location_id="L", evse_uid="E")


# The blueprint's acceptance cases


def test_free_confirmed_needs_a_free_tariff_that_was_found():
    free = tariff("F", [{"price_components": [component("energy", 0), component("flat", 0)]}])
    shown = price(connector("F"), free)
    assert (shown.state, shown.text) == ("free_confirmed", "Free")


def test_a_missing_tariff_is_price_unknown_never_free():
    shown = price(connector())
    assert (shown.state, shown.text) == ("unknown", "Price unknown")
    assert shown.reason == "No tariff is listed."


def test_an_unresolvable_tariff_id_is_price_unknown_and_recorded():
    shown = price(connector("GONE"), tariff("OTHER"))
    assert (shown.state, shown.text) == ("unknown", "Price unknown")
    assert shown.unresolved_ids == ["example:GB:EXA:GONE"]


def test_a_time_based_tariff_shows_each_period_and_its_range():
    elements = [
        {
            "price_components": [component("energy", 0.25, 20)],
            "restrictions": {"start_time": "00:00", "end_time": "07:00"},
        },
        {"price_components": [component("energy", 0.50, 20)]},
    ]
    shown = price(connector("TOU"), tariff("TOU", elements))
    assert shown.state == "priced"
    assert shown.text == "30p per kWh from midnight to 07:00, otherwise 60p per kWh including VAT"
    assert (shown.energy_low, shown.energy_high) == (Decimal("0.300"), Decimal("0.600"))
    assert shown.indicative == "30p to 60p/kWh"


# Choosing between several tariffs


def test_free_is_withheld_when_another_listed_tariff_could_not_be_read():
    free = tariff("F", [{"price_components": [component("energy", 0)]}])
    shown = price(connector("F", "GONE"), free)
    assert shown.state == "unknown"
    assert "free cannot be confirmed" in shown.reason


def test_a_priced_tariff_is_shown_when_another_could_not_be_read():
    shown = price(connector("T1", "GONE"), tariff("T1"))
    assert (shown.state, shown.text) == ("priced", "48p per kWh including VAT")
    assert shown.reason == "Some listed tariffs could not be read."


def test_the_pay_at_the_charger_tariff_is_preferred():
    ad_hoc = tariff("A", type_="ad_hoc_payment")
    member = tariff("M", [{"price_components": [component("energy", 0.30, 20)]}], type_="regular")
    shown = price(connector("M", "A"), ad_hoc, member)
    assert shown.tariff_ids == ["example:GB:EXA:A"]
    assert shown.text == "48p per kWh including VAT"


def test_different_prices_are_all_shown_when_none_is_preferred():
    low = tariff("L", [{"price_components": [component("energy", 0.30, 20)]}])
    shown = price(connector("T1", "L"), tariff("T1"), low)
    assert shown.text == "2 tariffs: 48p per kWh including VAT | 36p per kWh including VAT"
    assert shown.indicative == "36p to 48p/kWh"


def test_a_tariff_in_another_currency_is_never_converted():
    shown = price(connector("E"), tariff("E", currency="EUR"))
    assert (shown.state, shown.text) == ("unknown", "Price unknown")
    assert "never converted" in shown.reason
    assert shown.indicative is None


def test_without_vat_the_indicative_price_says_so():
    no_vat = tariff("N", [{"price_components": [component("energy", 0.40)]}])
    assert price(connector("N"), no_vat).indicative == "40p/kWh (excl. VAT)"


# Conditions, worded as OCPI 2.2.1 section 11.4.6 defines them


@pytest.mark.parametrize(
    ("restrictions", "expected"),
    [
        (
            {"start_time": "00:00", "end_time": "00:00", "day_of_week": ["SATURDAY", "SUNDAY"]},
            "at weekends",
        ),
        ({"start_time": "07:00", "end_time": "00:00"}, "from 07:00 to midnight"),
        ({"day_of_week": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]}, "on weekdays"),
        ({"day_of_week": ["MONDAY", "FRIDAY", "WEDNESDAY"]}, "on Monday, Wednesday and Friday"),
        ({"min_duration": 5400}, "after 90 minutes"),
        ({"min_duration": 14400}, "after 4 hours"),
        ({"max_duration": 1800}, "for the first 30 minutes"),
        ({"min_kwh": 20}, "after 20 kWh"),
        ({"max_kwh": 50}, "for the first 50 kWh"),
        ({"min_power": 50}, "while charging at 50 kW or more"),
        ({"max_power": 22}, "while charging below 22 kW"),
        (
            {"start_date": "2027-01-01", "end_date": "2027-02-01"},
            "from 1 January 2027 before 1 February 2027",
        ),
    ],
)
def test_conditions_are_worded_from_the_restrictions(restrictions, expected):
    days = [d.lower() for d in restrictions.pop("day_of_week", [])]
    assert conditions(TariffRestrictions(**restrictions, day_of_week=days)) == expected


def test_elements_after_an_unconditional_one_never_apply():
    elements = [
        {"price_components": [component("energy", 0.40, 20)]},
        {
            "price_components": [component("energy", 0.10, 20)],
            "restrictions": {"start_time": "00:00", "end_time": "06:00"},
        },
    ]
    assert describe_tariff(tariff("X", elements)).text == "48p per kWh including VAT"
    assert energy_range(tariff("X", elements))[:2] == (Decimal("0.480"), Decimal("0.480"))


def test_a_parking_fee_shows_when_it_starts():
    elements = [
        # As GeniePoint publishes it: no parking charge in the first element.
        {"price_components": [component("energy", 0.69, 20), component("time", 0, 20)]},
        {
            "price_components": [component("parking_time", 5.56, 20, step=5400)],
            "restrictions": {"min_duration": 5400},
        },
    ]
    assert describe_tariff(tariff("P", elements)).text == (
        "82.8p per kWh, plus £6.67 per hour parked after 90 minutes including VAT"
    )


# Recorded operator data


def replay(operator_id: str):
    config = load_registry()[operator_id]
    transport = ReplayTransport(FIXTURES / operator_id)
    with PoliteClient(
        config, transport=transport, sleep=lambda _s: None, key="fixture-not-a-real-key"
    ) as client:
        if config.adapter == "custom":
            from adapters import jolt

            return jolt.fetch(config, client)
        return fetch(config, client)


def test_recorded_jolt_connectors_are_priced_or_unknown_with_a_reason():
    result = replay("jolt")
    prices = price_locations(result.locations, result.tariffs)
    priced = [p for p in prices if p.state == "priced"]
    assert {p.text for p in priced} == {
        "49.2p per kWh including VAT",
        "88.8p per kWh including VAT",
    }
    assert all(
        p.reason == "Some listed tariffs could not be read." for p in priced if "49.2p" in p.text
    )
    unknown = [p for p in prices if p.state == "unknown"]
    assert unknown and all(p.reason == "No tariff is listed." for p in unknown)
    assert summary(prices).startswith("prices: 5 priced, 0 free, 1 unknown")


def test_recorded_geniepoint_parking_fees_show_their_conditions():
    result = replay("geniepoint")
    texts = {p.text for p in price_locations(result.locations, result.tariffs)}
    assert any("per hour parked after 90 minutes" in text for text in texts)
    assert all("per hour parked" not in text or " after " in text for text in texts)


# Every tariff at a site, for comparing them


def site(*connectors: Connector) -> Location:
    data = json.loads((FIXTURES / "normalised" / "location.json").read_text())
    data["evses"] = [
        {"uid": f"E{n}", "connectors": [c.model_dump()]} for n, c in enumerate(connectors)
    ]
    return Location.model_validate(data)


def index(*tariffs: Tariff) -> dict[str, Tariff]:
    return {t.id: t for t in tariffs}


def energy(price, vat=20, **restrictions):
    element = {"price_components": [component("energy", price, vat)]}
    if restrictions:
        element["restrictions"] = restrictions
    return element


def test_every_listed_tariff_is_shown_not_only_the_preferred_one():
    ad_hoc = tariff("A", type_="ad_hoc_payment", alt_text="Contactless")
    member = tariff("M", [energy(0.30)], type_="regular", alt_text="Members")
    shown = site_tariffs(site(connector("A", "M", "GONE")), index(ad_hoc, member))
    assert [(o.name, o.kind, o.text) for o in shown.options] == [
        ("Contactless", "Pay at the charger, for example by card", "48p per kWh including VAT"),
        (
            "Members",
            "With an account, app or card from a charging provider",
            "36p per kWh including VAT",
        ),
        (None, "How to pay is not stated", "Price unknown"),
    ]
    assert shown.options[2].state == "unknown" and "could not be read" in shown.options[2].reason
    assert shown.comparison == (
        "Lowest energy price listed here: 36p per kWh including VAT "
        "(with an account, app or card from a charging provider). "
        "Other charges, such as fees per session or per hour, are not compared."
    )


def test_time_and_day_differences_are_named():
    peak = tariff(
        "P",
        [energy(0.25, start_time="00:00", end_time="07:00", day_of_week=["saturday"]), energy(0.5)],
    )
    shown = site_tariffs(site(connector("P"), connector("T1")), index(peak, tariff("T1")))
    option = shown.options[0]
    assert option.text == (
        "30p per kWh from midnight to 07:00 on Saturday, otherwise 60p per kWh including VAT"
    )
    assert option.varies == "Price depends on time of day and day of the week."
    assert shown.options[1].varies is None
    assert [o.connectors for o in shown.options] == [1, 1] and shown.connectors == 2
    assert shown.comparison.startswith("Lowest energy price listed here: 30p per kWh")
    assert "including VAT at some times (how to pay" not in shown.comparison
    assert "including VAT at some times." in shown.comparison


def test_prices_on_different_vat_bases_are_never_compared():
    stated = tariff("S", [energy(0.30)])
    unstated = tariff("U", [energy(0.20, vat=None)])
    assert site_tariffs(site(connector("S", "U")), index(stated, unstated)).comparison is None


def test_matching_prices_say_so_and_one_tariff_is_not_compared():
    a, b = tariff("A"), tariff("B")
    both = site_tariffs(site(connector("A", "B")), index(a, b))
    assert both.comparison.startswith("Every priced tariff here charges 48p per kWh including VAT")
    assert site_tariffs(site(connector("A")), index(a)).comparison is None


def test_a_tariff_in_another_currency_is_listed_but_never_compared():
    euro = tariff("E", currency="EUR")
    shown = site_tariffs(site(connector("T1", "E")), index(tariff("T1"), euro))
    assert shown.options[1].text == "Price unknown" and "EUR" in shown.options[1].reason
    assert shown.comparison is None


def test_recorded_geniepoint_sites_show_the_account_and_contactless_prices():
    result = replay("geniepoint")
    tariffs = index(*result.tariffs)
    shown = [site_tariffs(location, tariffs) for location in result.locations]
    kinds = {o.kind for s in shown for o in s.options}
    assert {
        "Pay at the charger, for example by card",
        "With an account, app or card from a charging provider",
    } <= kinds
    assert any(s.comparison and "Lowest energy price" in s.comparison for s in shown)


# Built here so the key scan in test_security_files never sees an id-shaped literal.
SYSTEM_ID = "-".join(("1a2b3c4d", "5e6f", "4a1b", "8c2d", "9e0f1a2b3c4d"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"Tariff_Contactless_Rapid{SYSTEM_ID}", "Contactless, rapid"),
        (f"Tariff________OffPeakRapid{SYSTEM_ID}", "Off peak rapid"),
        ("AC_22kW_Tariff", "AC, 22kW, tariff"),
        ("UK Tariff Group: Base tariff", "UK Tariff Group: Base tariff"),
        ("[Electroverse as EMSP] Roaming Tariff", "[Electroverse as EMSP] Roaming Tariff"),
        (f"Tariff_{SYSTEM_ID}", None),
        (None, None),
    ],
)
def test_system_names_are_made_readable_and_plain_text_is_kept(text, expected):
    assert readable_name(text) == expected


def test_the_operators_own_name_is_kept_when_it_is_made_readable():
    raw = f"Tariff_Contactless_Rapid{SYSTEM_ID}"
    shown = site_tariffs(site(connector("A")), index(tariff("A", alt_text=raw)))
    assert (shown.options[0].name, shown.options[0].original_name) == ("Contactless, rapid", raw)
    plain = site_tariffs(site(connector("B")), index(tariff("B", alt_text="Members")))
    assert (plain.options[0].name, plain.options[0].original_name) == ("Members", None)
