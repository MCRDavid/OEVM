"""Locations whose operator's name says they are not for public use (ADR 0023).

The repository owner decided on 11 October 2026 that chargers marked private are hidden on
the map unless the visitor asks to see them. OCPI 2.2.1 has no field that says a location
is private: a location whose publish flag is false is never kept at all
(adapters/ocpi_221/normalise.py), and parking restrictions say who may park, not who may
charge. So the only sign is the operator's own name for the location, such as "Arthur
House - Private Use Only".

Only the clear phrases below count. Words that often name a place rather than a rule
("Fleet" in Fleetwood Road, "Depot", "Residential", "Visitor Centre", "Blue Badge holders
only") do not. The map shows the words found with each location, the transparency page
lists the phrases, and the feed health page lists every location they hide.
"""

import re

# What each phrase means, for the transparency page, and its pattern. Matching ignores
# case and needs whole words.
PHRASES: tuple[tuple[str, str], ...] = (
    (
        '"private use", "private access" or "private only", as in "Private Use Only"',
        r"private\s+(?:(?:use|access)(?:\s+only)?|only)",
    ),
    (
        '"private" at the end of the name or in brackets, as in "Site - PRIVATE"',
        r"(?:^|[-\u2013(*,/|]\s*)private\s*[)*]?\s*$",
    ),
    (
        '"not public", "not for public use" or "non-public"',
        r"not\s+(?:for\s+)?public|non[-\s]public",
    ),
    ('"no public access"', r"no\s+public\s+access"),
    ('"restricted access" or "restricted use"', r"restricted\s+(?:access|use)"),
    (
        '"staff only", "fleet only", "employees only", "residents only", '
        '"tenants only", "members only" or "permit holders only", with or without '
        '"use" before "only"',
        r"(?:staff|fleet|employees?|residents?|tenants?|members?|permit\s+holders?)"
        r"(?:\s+use)?\s+only",
    ),
    ('"staff car park"', r"staff\s+car\s*park"),
    (
        '"taxi only" or "taxis only", as in "[E-TAXI ONLY]"',
        r"taxis?\s+only",
    ),
)

_PATTERN = re.compile(
    "|".join(rf"(?<![\w]){pattern}(?![\w])" for _, pattern in PHRASES), re.IGNORECASE
)


def private_words(name: str | None) -> str | None:
    """The words in a location's name that mark it private or restricted, exactly as the
    operator wrote them, or None when there are none."""
    if not name:
        return None
    match = _PATTERN.search(name)
    if match is None:
        return None
    return match.group(0).strip(" -\u2013(*,/|)").strip()
