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
from pipeline.tariffs import (
    price_connector,
    price_locations,
    related_tariffs,
    site_tariffs,
    summary,
    withheld_free_tariffs,
)
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


# Zero-price tariffs the owner does not show as free (ADR 0022)


def _zero(tariff_id="Z"):
    return tariff(tariff_id, [{"price_components": [component("energy", 0), component("flat", 0)]}])


def test_a_withheld_zero_price_tariff_shows_price_unknown_with_the_reason():
    zero = _zero()
    withheld = withheld_free_tariffs([zero], ["Z"])
    assert withheld == {zero.id}
    shown = price_connector(
        connector("Z"), {zero.id: zero}, location_id="L", evse_uid="E", withheld=withheld
    )
    assert shown.state == "unknown" and shown.text == "Price unknown"
    assert "zero_price_tariffs" in shown.reason
    assert shown.indicative is None and shown.tariff_ids == [zero.id]
    # The tariff itself is unchanged, and without the decision it is free.
    assert zero.price_state == "free_confirmed"
    assert price(connector("Z"), zero).state == "free_confirmed"


def test_only_tariffs_named_by_exact_id_and_still_free_are_withheld():
    priced = tariff("P")
    others = [_zero("Z"), _zero("Z2"), priced]
    assert withheld_free_tariffs(others, ["Z"]) == {"example:GB:EXA:Z"}
    # A named tariff the operator has since priced is shown with its price.
    assert withheld_free_tariffs(others, ["P"]) == frozenset()
    assert withheld_free_tariffs(others, ["z"]) == frozenset()


def test_a_priced_tariff_alongside_a_withheld_one_is_still_shown():
    zero, priced = _zero(), tariff("P", type_="ad_hoc_payment")
    zero = zero.model_copy(update={"type": "ad_hoc_payment"})
    index = {zero.id: zero, priced.id: priced}
    withheld = withheld_free_tariffs([zero, priced], ["Z"])
    shown = price_connector(
        connector("Z", "P"), index, location_id="L", evse_uid="E", withheld=withheld
    )
    assert shown.state == "priced" and shown.text == "48p per kWh including VAT"
    assert shown.indicative == "48p/kWh"


def test_the_site_lists_a_withheld_tariff_as_unknown():
    zero = _zero()
    location = Location.model_validate(
        json.loads((FIXTURES / "normalised" / "location.json").read_text())
    )
    evse = location.evses[0].model_copy(update={"connectors": [connector("Z")]})
    location = location.model_copy(update={"evses": [evse]})
    withheld = withheld_free_tariffs([zero], ["Z"])
    (option,) = site_tariffs(location, {zero.id: zero}, withheld).options
    assert option.state == "unknown" and option.text == "Price unknown"
    assert option.energy_low is None and "zero_price_tariffs" in option.reason
    (free,) = site_tariffs(location, {zero.id: zero}).options
    assert free.state == "free"


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
        (
            "Members",
            "With an account, app or card from a charging provider",
            "36p per kWh including VAT",
        ),
        ("Contactless", "Pay at the charger, for example by card", "48p per kWh including VAT"),
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
    assert shown.options[1].text == "48p per kWh including VAT"
    assert [o.connectors for o in shown.options] == [1, 1] and shown.connectors == 2
    assert shown.comparison.startswith("Lowest energy price listed here: 30p per kWh")
    assert "including VAT at some times (how to pay" not in shown.comparison
    assert "including VAT at some times." in shown.comparison


def test_tariffs_are_listed_cheapest_first():
    dear = tariff("D", [energy(0.60)])
    cheap = tariff("C", [energy(0.30)])
    no_vat = tariff("N", [energy(0.10, vat=None)])
    unreadable = "GONE"
    euro = tariff("E", currency="EUR")
    flat = tariff("F", [{"price_components": [component("flat", 1.00, 20)]}])
    shown = site_tariffs(
        site(connector("D", unreadable, "E", "F", "N", "C")),
        index(dear, cheap, no_vat, euro, flat),
    )
    order = [o.tariff_id.rsplit(":", 1)[1] for o in shown.options]
    # Including VAT by price, then the price whose VAT is not stated (never mixed in with
    # them), then priced with no energy price, then unknown in the order first listed.
    assert order == ["C", "D", "N", "F", "GONE", "E"]


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
        (f"Tariff_Contactless_Rapid{SYSTEM_ID}", "Contactless rapid"),
        (f"Tariff________OffPeakRapid{SYSTEM_ID}", "Off peak rapid"),
        ("AC_22kW_Tariff", "AC 22kW tariff"),
        ("Pay_As_You_Go", "Pay as you go"),
        ("Standard_Tariff", "Standard tariff"),
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
    assert (shown.options[0].name, shown.options[0].original_name) == ("Contactless rapid", raw)
    plain = site_tariffs(site(connector("B")), index(tariff("B", alt_text="Members")))
    assert (plain.options[0].name, plain.options[0].original_name) == ("Members", None)


# Tariffs from a related operator's feed (ADR 0020)


def uuid_like(n: int) -> str:
    """An id in the form of a UUID, built here so the key scan never sees one."""
    return "-".join((f"{n:08x}", "0000", "4000", "8000", f"{n:012x}"))


def feed_tariff(source: str, tariff_id: str, country="GB", party="SIS", **extra) -> Tariff:
    """A tariff as another operator's feed publishes it."""
    return Tariff.model_validate(
        {
            "id": f"{source}:{country}:{party}:{tariff_id}",
            "currency": "GBP",
            "elements": [{"price_components": [component("energy", 0.50, 20)]}],
            "provenance": {**PROVENANCE, "source_id": source},
            **extra,
        }
    )


def test_a_connector_is_priced_from_the_one_related_tariff_with_its_exact_id():
    named = uuid_like(1)
    location = site(connector(named))
    sister = feed_tariff("sister", named)
    found = related_tariffs([location], [], {"sister": [sister]})
    assert found == {f"example:GB:EXA:{named}": sister}
    (shown,) = price_locations([location], [], found)
    assert (shown.state, shown.tariff_ids, shown.unresolved_ids) == ("priced", [sister.id], [])
    (unmatched,) = price_locations([location], [])
    assert (unmatched.state, unmatched.text) == ("unknown", "Price unknown")


@pytest.mark.parametrize(
    ("named", "own", "related"),
    [
        ("T1", [], {"sister": [feed_tariff("sister", "T1")]}),
        (
            uuid_like(1),
            [feed_tariff("example", uuid_like(1), country="IE", party="OTH")],
            {"sister": [feed_tariff("sister", uuid_like(1))]},
        ),
        (
            uuid_like(1),
            [],
            {
                "sister": [feed_tariff("sister", uuid_like(1))],
                "cousin": [feed_tariff("cousin", uuid_like(1))],
            },
        ),
        (
            uuid_like(1),
            [],
            {
                "sister": [
                    feed_tariff("sister", uuid_like(1)),
                    feed_tariff("sister", uuid_like(1), party="TWO"),
                ]
            },
        ),
        (uuid_like(1), [], {"sister": [feed_tariff("sister", uuid_like(1), country="IE")]}),
        (
            uuid_like(1),
            [],
            {"sister": [feed_tariff("sister", uuid_like(2), alt_text=f"Tariff {uuid_like(1)}")]},
        ),
        (uuid_like(0xABC), [], {"sister": [feed_tariff("sister", uuid_like(0xABC).upper())]}),
    ],
    ids=[
        "not-a-uuid",
        "own-response-has-the-id",
        "two-related-operators-have-it",
        "listed-twice",
        "another-country",
        "only-the-name-matches",
        "different-case",
    ],
)
def test_anything_but_one_exact_match_stays_unresolved(named, own, related):
    location = site(connector(named))
    assert related_tariffs([location], own, related) == {}
    (shown,) = price_locations([location], own, related_tariffs([location], own, related))
    assert shown.state == "unknown"


# The lowest price per kWh for the label above a point on the map (ADR 0026)


def test_the_label_uses_the_cheapest_tariff_not_only_the_preferred_one():
    contactless = tariff("A", [energy(0.77)], type_="ad_hoc_payment")
    app = tariff("R", [energy(0.69)], type_="regular")
    shown = price(connector("A", "R"), contactless, app)
    # The price shown for the connector is still the pay-at-the-charger one...
    assert shown.text == "92.4p per kWh including VAT"
    # ...but the label is the lowest price any listed tariff gives.
    assert (shown.lowest, shown.lowest_vat, shown.lowest_varies) == (Decimal("0.828"), True, False)
    assert shown.label == "82.8p"


def test_the_label_says_from_when_the_lowest_price_applies_only_at_some_times():
    night = tariff("N", [energy(0.25, start_time="00:00", end_time="07:00"), energy(0.5)])
    assert price(connector("N"), night).label == "from 30p"
    # Another tariff that always charges that price means it is not only at some times.
    flat = tariff("F", [energy(0.25)])
    assert price(connector("N", "F"), night, flat).label == "30p"
    # A price per kWh only at night, and by the hour otherwise, is "from" too.
    hourly = tariff(
        "H",
        [
            energy(0.25, start_time="00:00", end_time="07:00"),
            {"price_components": [component("time", 3.0, 20)]},
        ],
    )
    assert price(connector("H"), hourly).label == "from 30p"


def test_a_connector_whose_price_is_unknown_has_no_label():
    # Its pay-at-the-charger tariff is in euros, so it shows "Price unknown"; a label from
    # its other tariff would sit on a point marked "?".
    euro = tariff("E", currency="EUR", type_="ad_hoc_payment")
    app = tariff("R", [energy(0.40)], type_="regular")
    shown = price(connector("E", "R"), euro, app)
    assert shown.state == "unknown" and shown.label is None


def test_the_lowest_figure_wins_whether_or_not_its_vat_is_stated():
    stated = tariff("S", [energy(0.50)])
    unstated = tariff("U", [energy(0.30, vat=None)])
    # 30p plus any VAT is still below 60p, so the price including VAT is not the cheapest.
    # VAT is never added: the label says the published figure excludes it.
    assert price(connector("S", "U"), stated, unstated).label == "30p excl. VAT"
    assert price(connector("U"), unstated).label == "30p excl. VAT"
    # On a tie the price including VAT is used.
    same = tariff("V", [energy(0.25)])
    assert price(connector("V", "U"), same, unstated).label == "30p"
    assert price(connector("U", "V"), unstated, same).label == "30p"


def test_a_price_that_would_show_as_0p_gives_no_label():
    tiny = tariff("T", [energy(0.0004, vat=None)])
    assert price(connector("T"), tiny).label is None


def test_a_tariff_free_per_kwh_at_some_times_or_free_altogether_means_no_label():
    # 0p at night is cheaper than anything else listed, and "0p" would read as free.
    night_free = tariff("C", [energy(0, start_time="00:00", end_time="07:00"), energy(0.50)])
    day = tariff("D", [energy(0.55)], type_="regular")
    shown = price(connector("C", "D"), night_free, day)
    assert shown.state == "priced" and shown.label is None
    # A free tariff next to a priced one, on a connector that is not confirmed free.
    free = tariff("F", [{"price_components": [component("energy", 0), component("flat", 0)]}])
    paid = tariff("P", [energy(0.50)], type_="ad_hoc_payment")
    shown = price(connector("P", "F"), paid, free)
    assert shown.state == "priced" and shown.label is None


def test_ties_are_judged_on_the_tenth_of_a_penny_the_label_shows():
    stated = tariff("S", [energy(0.40975)])  # 49.17p including VAT
    unstated = tariff("U", [energy(0.4916, vat=None)])
    shown = price(connector("S", "U"), stated, unstated)
    assert (shown.lowest, shown.lowest_vat, shown.label) == (Decimal("0.492"), True, "49.2p")
    night = tariff("N", [energy(0.40972, start_time="00:00", end_time="07:00"), energy(0.5)])
    assert price(connector("N", "S"), night, stated).label == "49.2p"


def test_tariffs_outside_their_validity_dates_give_no_label():
    # The fixture tariffs were fetched in October 2026.
    ended = tariff("OLD", [energy(0.30)], end_date_time="2026-01-01T00:00:00Z")
    future = tariff("NEW", [energy(0.25)], start_date_time="2030-01-01T00:00:00Z")
    current = tariff("NOW", [energy(0.40)], start_date_time="2026-01-01T00:00:00Z")
    assert price(connector("OLD", "NEW", "NOW"), ended, future, current).label == "48p"


def test_no_label_from_a_zero_price_unknown_price_or_another_currency():
    zero_energy = tariff(
        "Z", [{"price_components": [component("energy", 0, 20), component("time", 2.0, 20)]}]
    )
    euro = tariff("E", currency="EUR")
    for listed in (zero_energy, euro):
        assert price(connector(listed.id.rsplit(":", 1)[1]), listed).label is None
    assert price(connector("GONE")).label is None
    # A priced tariff next to one of those still gives the label.
    assert price(connector("Z", "T1"), zero_energy, tariff("T1")).label == "48p"


def test_free_only_for_a_confirmed_free_connector():
    free = tariff("F", [{"price_components": [component("energy", 0), component("flat", 0)]}])
    assert price(connector("F"), free).label == "Free"
    # Free cannot be confirmed when another listed tariff could not be read.
    assert price(connector("F", "GONE"), free).label is None


def test_a_withheld_zero_price_tariff_gives_no_label():
    zero = _zero()
    shown = price_connector(
        connector("Z"),
        {zero.id: zero},
        location_id="L",
        evse_uid="E",
        withheld=frozenset({zero.id}),
    )
    assert shown.text == "Price unknown" and shown.label is None
    # A priced tariff next to it still gives the label: the withheld one is left out.
    paid = tariff("P", [energy(0.40)])
    shown = price_connector(
        connector("Z", "P"),
        {zero.id: zero, paid.id: paid},
        location_id="L",
        evse_uid="E",
        withheld=frozenset({zero.id}),
    )
    assert shown.label == "48p"
