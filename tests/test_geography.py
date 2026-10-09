"""Whether a point is genuinely in the UK (pipeline/geography.py). No network."""

import json

import pytest

from pipeline import geography
from pipeline.geography import place_in_uk


@pytest.mark.parametrize(
    ("name", "latitude", "longitude", "postcode"),
    [
        ("Central London", 51.5074, -0.1278, "SW1A 1AA"),
        ("Leeds", 53.80797, -1.56237, "LS3 1HF"),
        ("Belfast", 54.5973, -5.9301, "BT1 5GS"),
        ("Lerwick, Shetland", 60.1546, -1.1494, "ZE1 0LL"),
        ("St Mary's, Isles of Scilly", 49.9145, -6.3115, "TR21 0HY"),
        ("Brighton Palace Pier", 50.8165, -0.1366, "BN2 1TW"),
        ("Dover Eastern Docks", 51.1270, 1.3311, "CT16 1JA"),
        ("Holyhead harbour", 53.3110, -4.6280, "LL65 1DQ"),
        ("Newry, near the border", 54.1751, -6.3402, "BT35 6HP"),
        ("Strabane, near the border", 54.8270, -7.4630, "BT82 8DY"),
        ("Millport, Great Cumbrae (not in the outlines)", 55.754, -4.928, "KA28 0AA"),
        ("St Agnes, Isles of Scilly (not in the outlines)", 49.893, -6.342, "TR22 0PL"),
        ("Holy Island, Lindisfarne (not in the outlines)", 55.669, -1.80, "TD15 2SD"),
        ("Eigg (not in the outlines)", 56.879, -6.129, "PH42 4RL"),
    ],
)
def test_places_in_the_uk_are_kept(name, latitude, longitude, postcode):
    assert place_in_uk(latitude, longitude, postcode), name


@pytest.mark.parametrize(
    ("name", "latitude", "longitude", "postcode"),
    [
        ("Dublin (Clenergy EV, Green Isle 1)", 53.309903, -6.403055, "D22 F9F4"),
        ("Maynooth (Clenergy EV, Glenroyal Hotel)", 53.379821, -6.587941, "W23 C2V1"),
        ("Sligo", 54.2766, -8.4761, "F91 X2C4"),
        ("Dundalk, near the border", 54.0090, -6.4049, "A91 X2C4"),
        ("Lifford, across the river from Strabane", 54.8336, -7.4794, "F93 X2C4"),
        ("Douglas, Isle of Man", 54.1523, -4.4861, "IM1 2AA"),
        ("Calais", 50.9513, 1.8587, None),
        ("Boulogne-sur-Mer", 50.7264, 1.6147, None),
        ("St Helier, Jersey", 49.1868, -2.1068, "JE2 3NN"),
        ("North Sea (Clenergy EV, UoL MSCP 1)", 53.804825, 1.551283, "N/A"),
        ("Irish Sea, far from any coast", 53.8, -5.4, None),
        ("Leeds swapped round", -1.56237, 53.80797, "LS3 1HF"),
    ],
)
def test_places_outside_the_uk_are_left_off(name, latitude, longitude, postcode):
    assert not place_in_uk(latitude, longitude, postcode), name


def test_near_the_irish_border_the_postcode_decides():
    strabane = (54.8270, -7.4630)  # about 1.7 km from the border on the outlines
    assert place_in_uk(*strabane, "BT82 8DY")
    assert not place_in_uk(*strabane, None)
    assert not place_in_uk(*strabane, "F93 X2C4")
    newry = (54.1751, -6.3402)  # about 7 km from it, so the outlines decide
    assert place_in_uk(*newry, None)


def test_the_outlines_are_natural_earth_and_cover_the_neighbours():
    data = json.loads(geography.DATA.read_text(encoding="utf-8"))
    assert "Natural Earth" in data["source"] and "Public domain" in data["licence"]
    assert {"GBR", "IRL", "IMN", "FRA", "BEL", "NLD", "JEY", "GGY"} <= set(data["countries"])


def test_islands_the_outlines_leave_out_need_a_uk_postcode():
    millport = (55.754, -4.928)
    assert place_in_uk(*millport, "KA28 0AA")
    assert not place_in_uk(*millport, None)
    assert not place_in_uk(*millport, "IM1 2AA")
    assert not place_in_uk(*millport, "N/A")


def test_a_uk_postcode_does_not_pull_in_points_far_out_at_sea():
    assert not place_in_uk(53.097591, 2.444352, "CW1 2JZ")  # GeniePoint's Crewe Civic
    assert not place_in_uk(50.9513, 1.8587, "CT16 1JA")  # Calais, with a Dover postcode
    assert not place_in_uk(53.309903, -6.403055, "SW1A 1AA")  # Dublin, with a London one
