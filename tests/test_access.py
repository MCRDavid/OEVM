"""Tests for pipeline/access.py: names that mark a location private or restricted
(ADR 0023). No test touches the network."""

import pytest

from pipeline.access import PHRASES, private_words


@pytest.mark.parametrize(
    ("name", "words"),
    [
        # Names from the operators' feeds on 12 October 2026.
        ("Arthur House - Private Use Only", "Private Use Only"),
        ("Airfields Farm Primary School - PRIVATE USE ONLY", "PRIVATE USE ONLY"),
        ("STFC - Rutherford Appleton - PRIVATE", "PRIVATE"),
        ("Clarendon Road (RESTRICTED ACCESS - Private use only)", "RESTRICTED ACCESS"),
        ("Halton Stadium *restricted use workplace charger*", "restricted use"),
        ("CPS TEST SITE TERRY - NOT PUBLIC", "NOT PUBLIC"),
        ("NEC North 1B Car Park - STAFF ONLY", "STAFF ONLY"),
        ("Sunderland Royal Hospital - Staff car park", "Staff car park"),
        ("HCC Fleet Only", "Fleet Only"),
        # Other forms of the same phrases.
        ("Depot (Private)", "Private"),
        ("Private", "Private"),
        ("Main Street, Residents Use Only", "Residents Use Only"),
        ("Office - permit holders only", "permit holders only"),
        ("Non-public test bay", "Non-public"),
        ("Yard: no public access", "no public access"),
        (f"Head office {chr(0x2013)} private", "private"),  # an en dash
    ],
)
def test_names_that_say_private_or_restricted_are_caught_with_their_words(name, words):
    assert private_words(name) == words


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        # Places, not rules: these stay on the map.
        "Spire Private Hospital",
        "Private Road Car Park",
        "MFG Fleet",
        "10 Fleetwood Road",
        "Market Weighton Depot",
        "East Saltoun On-Street Residential Charger",
        "NHS State Hospital Visitors Car Park",
        "UoL MSCP 9 (Blue Badge holders only)",
        "Staffordshire County Hall",
        "Publicity House",
    ],
)
def test_other_names_are_not_caught(name):
    assert private_words(name) is None


def test_every_phrase_has_a_description_for_the_transparency_page():
    assert all(description.startswith('"') and pattern for description, pattern in PHRASES)
