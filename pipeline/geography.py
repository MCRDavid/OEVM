"""Whether a charger's coordinates are genuinely in the UK, for deciding what the map shows.

Operators may list sites outside the UK; only UK sites are mapped. A point counts as in
the UK when it is inside the map's UK limits and either:

- on the UK's land, using Natural Earth's 1:10m country outlines (pipeline/data/, public
  domain), or
- off every outline but within COAST_METRES of the UK's and nearer to it than to any
  other country, for piers, harbours and stretches of coast the outlines cut short, or
- off every outline, within ISLAND_METRES of the UK's and nearer to it than to any other
  country, with a UK postcode, for small islands the outlines leave out (Great Cumbrae,
  Gigha, Eigg, several Orkney and Shetland isles, St Agnes on Scilly, Holy Island).

The outlines are accurate to a few hundred metres, so a point within BORDER_METRES of the
land border with Ireland is decided by its postcode instead: a Northern Ireland postcode
(BT) means the UK, anything else does not. Points in Ireland, the Isle of Man, the Channel
Islands, France, Belgium or the Netherlands are not in the UK.

Nothing here moves a point or fills in a missing one; it only decides whether to show it.
"""

import json
import math
import re
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from pathlib import Path

DATA = Path(__file__).parent / "data" / "uk_and_neighbours.json"

# Latitude and longitude limits that include the Isles of Scilly, Shetland, Northern
# Ireland and the east coast. A point outside them is never in the UK.
UK_LATITUDE = (49.8, 60.95)
UK_LONGITUDE = (-8.7, 1.8)

COAST_METRES = 2_000
ISLAND_METRES = 25_000
BORDER_METRES = 2_000
_NI_POSTCODE = re.compile(r"^BT[0-9]{1,2} ?[0-9][A-Z]{2}$", re.IGNORECASE)
# A UK postcode, leaving out the Isle of Man and Channel Islands, which share the format.
_UK_POSTCODE = re.compile(r"^(?!IM|JE|GY)[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$", re.IGNORECASE)
_BAND = 0.05  # degrees of latitude per bucket of edges
_EARTH_METRES = 6_371_000


@dataclass(frozen=True)
class _Country:
    code: str
    # Each polygon is a list of rings (outer first, then holes); each ring a list of
    # (longitude, latitude) edges, bucketed by latitude band for quick lookups.
    rings: tuple[tuple[int, tuple], ...]  # (polygon index, edges)
    bands: dict[int, list[tuple[int, int]]]  # band -> [(ring index, edge index)]
    bounds: tuple[float, float, float, float]  # min lon, min lat, max lon, max lat


def _band(latitude: float) -> int:
    return math.floor(latitude / _BAND)


def _build(code: str, polygons: list) -> _Country:
    rings: list[tuple[int, tuple]] = []
    bands: dict[int, list[tuple[int, int]]] = {}
    xs, ys = [], []
    for p_index, polygon in enumerate(polygons):
        for ring in polygon:
            points = [tuple(point) for point in ring]
            if points[0] != points[-1]:
                points.append(points[0])
            edges = tuple(pairwise(points))
            r_index = len(rings)
            rings.append((p_index, edges))
            for e_index, ((_, y1), (_, y2)) in enumerate(edges):
                for band in range(_band(min(y1, y2)), _band(max(y1, y2)) + 1):
                    bands.setdefault(band, []).append((r_index, e_index))
            xs += [x for x, _ in points]
            ys += [y for _, y in points]
    return _Country(code, tuple(rings), bands, (min(xs), min(ys), max(xs), max(ys)))


@cache
def _countries() -> dict[str, _Country]:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return {code: _build(code, c["polygons"]) for code, c in data["countries"].items()}


def _inside(country: _Country, lon: float, lat: float) -> bool:
    """Even-odd ray casting over every ring of one country: inside an outer ring and not
    in one of its holes. Islands do not overlap, so one count over all rings works."""
    min_x, min_y, max_x, max_y = country.bounds
    if not (min_x <= lon <= max_x and min_y <= lat <= max_y):
        return False
    crossings = 0
    for r_index, e_index in country.bands.get(_band(lat), ()):
        (x1, y1), (x2, y2) = country.rings[r_index][1][e_index]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x > lon:
                crossings += 1
    return crossings % 2 == 1


def _metres_to_edge(lon: float, lat: float, a: tuple, b: tuple) -> float:
    """Distance from a point to a segment, on a local flat projection (fine for a few km)."""
    scale = math.cos(math.radians(lat))

    def project(point: tuple) -> tuple[float, float]:
        return ((point[0] - lon) * scale, point[1] - lat)

    (ax, ay), (bx, by) = project(a), project(b)
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length))
    cx, cy = ax + t * dx, ay + t * dy
    return math.radians(math.hypot(cx, cy)) * _EARTH_METRES


def _metres_to(country: _Country, lon: float, lat: float, within: float) -> float:
    """Distance to the country's outline, or infinity if it is further than `within`."""
    reach = math.degrees(within / _EARTH_METRES)
    min_x, min_y, max_x, max_y = country.bounds
    wide = reach / max(math.cos(math.radians(lat)), 0.1)
    if not (min_x - wide <= lon <= max_x + wide and min_y - reach <= lat <= max_y + reach):
        return math.inf
    best = math.inf
    seen = set()
    for band in range(_band(lat - reach), _band(lat + reach) + 1):
        for key in country.bands.get(band, ()):
            if key in seen:
                continue
            seen.add(key)
            a, b = country.rings[key[0]][1][key[1]]
            best = min(best, _metres_to_edge(lon, lat, a, b))
    return best if best <= within else math.inf


def in_uk_limits(latitude: float, longitude: float) -> bool:
    return (
        UK_LATITUDE[0] <= latitude <= UK_LATITUDE[1]
        and UK_LONGITUDE[0] <= longitude <= UK_LONGITUDE[1]
    )


def place_in_uk(latitude: float, longitude: float, postcode: str | None = None) -> bool:
    """True if the point is genuinely in the UK, as the module docstring describes."""
    if not in_uk_limits(latitude, longitude):
        return False
    countries = _countries()
    uk, ireland = countries["GBR"], countries["IRL"]
    if _metres_to(ireland, longitude, latitude, BORDER_METRES) < math.inf and (
        _metres_to(uk, longitude, latitude, BORDER_METRES) < math.inf
    ):
        # Near the land border with Ireland, where the outlines are not precise enough.
        return bool(_NI_POSTCODE.match((postcode or "").strip()))
    if _inside(uk, longitude, latitude):
        return True
    if any(_inside(c, longitude, latitude) for code, c in countries.items() if code != "GBR"):
        return False
    reach = ISLAND_METRES if _UK_POSTCODE.match((postcode or "").strip()) else COAST_METRES
    to_uk = _metres_to(uk, longitude, latitude, reach)
    if to_uk == math.inf:
        return False
    return all(
        _metres_to(c, longitude, latitude, to_uk) >= to_uk
        for code, c in countries.items()
        if code != "GBR"
    )
