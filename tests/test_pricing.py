"""Tests for pipeline/pricing.py: prices are only ever shown in pounds and pence."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import (
    VAT_IN_PRICE,
    conditions,
    describe_tariff,
    energy_always,
    energy_range,
    location_summary,
    map_label,
    pence,
    plan_label,
    pounds,
    varies_with,
)
from pipeline.registry import load_registry
from pipeline.tariffs import ConnectorPrice
from schema.models import Tariff, TariffRestrictions

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
        ([energy(0.4125, vat=20)], "50p per kWh"),
        ([energy(0.57, vat=5)], "60p per kWh"),
    ],
    ids=["half-penny-flat", "half-penny-low-vat", "half-penny-energy", "low-vat-energy"],
)
def test_vat_maths_is_exact_and_rounds_half_up(components, expected):
    assert describe_tariff(tariff(components=components)).text == f"{expected} including VAT"


def test_a_price_including_vat_is_shown_to_the_whole_penny():
    # The owner's decision of 14 November 2026 (ADR 0003): drivers are charged whole pence.
    # Pod's 0.37 with VAT 20 is 44.4p, where its app shows 44p.
    pod = tariff(components=[energy(0.37, vat=20)])
    assert describe_tariff(pod).text == "44p per kWh including VAT"
    assert energy_range(pod) == (Decimal("0.44"), Decimal("0.44"), True)
    # A price whose VAT is not stated is shown as published, to the tenth of a penny.
    unstated = tariff(components=[energy(0.4917)])
    assert describe_tariff(unstated).text == "49.2p per kWh (excluding VAT, VAT not stated)"
    assert energy_range(unstated) == (Decimal("0.4917"), Decimal("0.4917"), False)


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


# VAT the owner decided to add where a feed gives none (vat_not_stated, ADR 0003 as
# amended on 22 October 2026)

ADDED = "including VAT (20% added by this project)"


def test_vat_is_added_at_the_owners_rate_and_the_price_says_so():
    shown = describe_tariff(tariff(components=[energy(0.325)]), added_vat=20)
    assert shown.text == f"39p per kWh {ADDED}"
    assert energy_range(tariff(components=[energy(0.4167)]), 20) == (
        Decimal("0.50"),
        Decimal("0.50"),
        True,
    )


def test_a_rate_the_feed_gives_is_kept_and_only_missing_ones_are_added():
    shown = describe_tariff(tariff(components=[energy(0.45, vat=5), energy(0.30)]), added_vat=20)
    assert shown.text == f"36p to 47p per kWh {ADDED}"
    # When every price gives its own rate, nothing is added, so nothing is said.
    stated = describe_tariff(tariff(components=[energy(0.45, vat=20)]), added_vat=20)
    assert stated.text == "54p per kWh including VAT"


def test_added_vat_covers_other_charges_and_the_minimum_charge():
    shown = describe_tariff(
        tariff(
            components=[energy(0.5), {"type": "flat", "price": 1.0, "vat": None, "step_size": 1}],
            min_price=2,
        ),
        added_vat=20,
    )
    assert shown.text == (
        f"60p per kWh, plus £1.20 per session {ADDED}; "
        "minimum charge £2.40 including VAT (20% added by this project)"
    )


IN_PRICE = "including VAT (read as already in the feed's price)"


def test_stated_vat_read_as_in_the_price_is_not_added_and_the_price_says_so():
    # vat_in_price (ADR 0003, amended 23 October 2026): 0.59 with VAT 20 shows as 59p.
    shown = describe_tariff(tariff(components=[energy(0.59, vat=20)]), added_vat=VAT_IN_PRICE)
    assert shown.text == f"59p per kWh {IN_PRICE}"
    assert energy_range(tariff(components=[energy(0.59, vat=20)]), VAT_IN_PRICE) == (
        Decimal("0.59"),
        Decimal("0.59"),
        True,
    )
    with_minimum = describe_tariff(
        tariff(components=[energy(0.59, vat=20)], min_price=2), added_vat=VAT_IN_PRICE
    )
    assert with_minimum.text.endswith(f"; minimum charge £2.00 {IN_PRICE}")


def test_reading_vat_as_in_the_price_never_supplies_a_missing_rate():
    shown = describe_tariff(
        tariff(components=[energy(0.59, vat=20), energy(0.30)]), added_vat=VAT_IN_PRICE
    )
    assert shown.text == "30p to 59p per kWh (excluding VAT, VAT not stated)"
    assert energy_range(tariff(components=[energy(0.30)]), VAT_IN_PRICE)[2] is False


def test_without_a_decision_a_price_with_no_vat_is_shown_as_published():
    assert describe_tariff(tariff(components=[energy(0.325)])).text == (
        "32.5p per kWh (excluding VAT, VAT not stated)"
    )
    assert energy_range(tariff(components=[energy(0.325)]))[2] is False


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


# The label above a point on the map (ADR 0026)


@pytest.mark.parametrize(
    ("state", "lowest", "vat", "varies", "expected"),
    [
        ("free_confirmed", None, None, False, "Free"),
        # Free comes from the price state only, never from a price that happens to be low.
        ("priced", Decimal("0.56"), True, False, "56p"),
        ("priced", Decimal("0.325"), False, True, "from 32.5p excl. VAT"),
        ("priced", Decimal("0.4917"), True, True, "from 49.2p"),
        ("priced", Decimal("0.35"), False, False, "35p excl. VAT"),
        ("priced", None, None, False, None),
        ("unknown", Decimal("0.828"), True, False, "82.8p"),
        ("unknown", None, None, False, None),
    ],
)
def test_map_labels_are_short_and_say_when_they_apply(state, lowest, vat, varies, expected):
    assert map_label(state, lowest, vat, varies) == expected


def test_a_plan_label_needs_a_fixed_price_including_vat():
    assert plan_label(Decimal("0.39"), True) == "39p"
    assert plan_label(Decimal("0.39"), None) is None
    assert plan_label(Decimal("0.39"), False) is None
    assert plan_label(None, True) is None
    # A price that would show as 0p reads as free, which only free_confirmed may be.
    assert plan_label(Decimal("0"), True) is None
    assert plan_label(Decimal("0.0004"), True) is None
    assert plan_label(Decimal("0.0005"), True) == "0.1p"


def test_a_plan_label_says_from_when_the_plan_applies_only_at_some_times():
    assert plan_label(Decimal("0.44"), True, only_at_some_times=True) == "from 44p"
    assert plan_label(Decimal("0.44"), True, only_at_some_times=False) == "44p"


# Start dates that had passed when the tariff was read (owner, 15 November 2026). The
# fixture's tariff was read on 6 October 2026 at 09:05 UTC.

NOT_STATED = "(excluding VAT, VAT not stated)"


def test_a_start_date_that_had_passed_when_read_is_left_out():
    for start in ("2025-10-23", "2026-10-06"):
        shown = tariff(restrictions={"start_date": start})
        assert describe_tariff(shown).text == f"45p per kWh {NOT_STATED}"
        # The price then applies whenever it is used, so a label does not say "from".
        assert energy_always(shown)
        assert varies_with(shown) == []


def test_a_start_date_still_to_come_is_kept():
    shown = tariff(restrictions={"start_date": "2026-12-01"})
    assert describe_tariff(shown).text == f"45p per kWh from 1 December 2026 {NOT_STATED}"
    assert not energy_always(shown)
    assert varies_with(shown) == ["date"]


def test_an_element_whose_start_date_had_passed_applies_before_any_after_it():
    # OCPI uses the first element that applies, so the one after it never does.
    def two(start):
        return Tariff.model_validate(
            {
                **tariff().model_dump(mode="json"),
                "elements": [
                    {"price_components": [energy(0.50)], "restrictions": {"start_date": start}},
                    {"price_components": [energy(0.45)]},
                ],
            }
        )

    assert describe_tariff(two("2026-01-01")).text == f"50p per kWh {NOT_STATED}"
    assert (
        describe_tariff(two("2026-12-01")).text
        == f"50p per kWh from 1 December 2026, otherwise 45p per kWh {NOT_STATED}"
    )


def test_the_day_a_tariff_was_read_is_the_day_in_the_uk():
    # 23:30 UTC on 5 October 2026 is 00:30 on 6 October in the UK (BST).
    late = tariff(restrictions={"start_date": "2026-10-06"})
    late = late.model_copy(
        update={
            "provenance": late.provenance.model_copy(
                update={"fetched_at": datetime.fromisoformat("2026-10-05T23:30:00Z")}
            )
        }
    )
    assert describe_tariff(late).text == f"45p per kWh {NOT_STATED}"


# Midnight to 23:59 is all day (owner, 16 November 2026), as midnight to midnight was.

WEEK_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@pytest.mark.parametrize("end", ["23:59", "00:00"])
def test_midnight_to_2359_every_day_is_all_day(end):
    # Shell Recharge's tariffs, as read on 16 November 2026: every day, midnight to 23:59.
    shown = tariff(restrictions={"start_time": "00:00", "end_time": end, "day_of_week": WEEK_DAYS})
    assert describe_tariff(shown).text == f"45p per kWh {NOT_STATED}"
    assert energy_always(shown)
    assert varies_with(shown) == []
    assert conditions(TariffRestrictions(start_time="00:00", end_time=end)) == ""


def test_midnight_to_2359_keeps_the_other_conditions():
    shown = tariff(
        restrictions={"start_time": "00:00", "end_time": "23:59", "day_of_week": ["monday"]}
    )
    assert describe_tariff(shown).text == f"45p per kWh on Monday {NOT_STATED}"
    assert varies_with(shown) == ["day of the week"]


@pytest.mark.parametrize(
    ("start", "end"), [("00:00", "23:58"), ("00:01", "23:59"), ("07:00", "23:59")]
)
def test_other_times_are_still_said(start, end):
    shown = tariff(restrictions={"start_time": start, "end_time": end})
    assert describe_tariff(shown).text.startswith("45p per kWh from ")
    assert not energy_always(shown)
    assert varies_with(shown) == ["time of day"]


# The same prices at every hour, split only by time of day, are one price (owner, 21
# November 2026, ADR 0003).


def split_tariff(elements) -> Tariff:
    base = tariff()
    return base.model_copy(
        update={"elements": [base.elements[0].model_validate(e) for e in elements]}
    )


def kwh(price, vat=20.0):
    return [energy(price, vat=vat)]


def at(start, end, days=None, **more):
    return {"start_time": start, "end_time": end, "day_of_week": days or [], **more}


def test_the_same_price_at_every_hour_is_one_price():
    # Go Zero's tariffs, as read on 20 November 2026: 22:00 to 06:00 and 06:00 to 22:00,
    # every day, both 0.55 with VAT 20.
    shown = split_tariff(
        [
            {"price_components": kwh(0.55), "restrictions": at("22:00", "06:00", WEEK_DAYS)},
            {"price_components": kwh(0.55), "restrictions": at("06:00", "22:00", WEEK_DAYS)},
        ]
    )
    assert describe_tariff(shown).text == "66p per kWh including VAT"
    assert energy_always(shown)
    assert varies_with(shown) == []
    assert energy_range(shown) == (Decimal("0.66"), Decimal("0.66"), True)


def test_one_price_also_covers_times_that_meet_at_midnight_and_a_closing_element():
    shown = split_tariff(
        [
            {"price_components": kwh(0.5), "restrictions": at("00:00", "12:00")},
            {"price_components": kwh(0.5), "restrictions": at("12:00", None)},
        ]
    )
    assert describe_tariff(shown).text == "60p per kWh including VAT"
    with_rest = split_tariff(
        [
            {"price_components": kwh(0.5), "restrictions": at("08:00", "20:00")},
            {"price_components": kwh(0.5), "restrictions": None},
        ]
    )
    assert describe_tariff(with_rest).text == "60p per kWh including VAT"


@pytest.mark.parametrize(
    "second",
    [
        # A different price at night.
        {"price_components": kwh(0.45), "restrictions": at("22:00", "06:00")},
        # A different VAT figure.
        {"price_components": kwh(0.55, vat=None), "restrictions": at("22:00", "06:00")},
        # A gap between 22:00 and 23:00.
        {"price_components": kwh(0.55), "restrictions": at("23:00", "06:00")},
        # Weekdays only, so not every day.
        {"price_components": kwh(0.55), "restrictions": at("22:00", "06:00", WEEK_DAYS[:5])},
        # Another condition besides the time.
        {"price_components": kwh(0.55), "restrictions": at("22:00", "06:00", max_kwh=20)},
        # Another kind of charge as well.
        {
            "price_components": [*kwh(0.55), {"type": "flat", "price": 1, "vat": 20}],
            "restrictions": at("22:00", "06:00"),
        },
    ],
)
def test_prices_that_differ_by_time_or_leave_a_gap_are_still_said(second):
    first = {"price_components": kwh(0.55), "restrictions": at("06:00", "22:00")}
    shown = split_tariff([first, second])
    text = describe_tariff(shown).text
    assert "from 06:00 to 22:00" in text
    assert not energy_always(shown)
    assert "time of day" in varies_with(shown)


def test_one_price_never_reads_a_reservation_or_leaves_out_the_stated_times():
    # A single element keeps its time: only elements that together cover the day merge.
    alone = split_tariff([{"price_components": kwh(0.55), "restrictions": at("06:00", "22:00")}])
    assert describe_tariff(alone).text == "66p per kWh from 06:00 to 22:00 including VAT"
    # A start that equals its end covers nothing here, so the gap is still said.
    odd = split_tariff(
        [
            {"price_components": kwh(0.55), "restrictions": at("06:00", "06:00")},
            {"price_components": kwh(0.55), "restrictions": at("06:00", "22:00")},
        ]
    )
    assert not energy_always(odd)
