"""What search engines and link previews read from each page of the site.

Every page gets, in its head, a short description, its one full address (a canonical
link, so search engines count addresses that differ only in case, or end in index.html,
as one page) and Open Graph tags, so a shared link shows a title, a summary and the
site's picture (site/assets/share.png: the site's icon and name, with no map and no
operator's data). The map page also describes its data as a schema.org Dataset, which lets Google's
Dataset Search list it.

The site build writes sitemap.xml, the list of every page, for submitting to Google
Search Console and Bing Webmaster Tools (pipeline/build_site.py).

The site has no robots.txt. Crawlers read one only from the top of a host
(mcrdavid.github.io/robots.txt, which this repository does not publish), never from a
folder such as /OEVM/, and without one every page may be crawled.
"""

import html
import json
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from pipeline.project import NAME, SITE_URL

# The picture a shared link shows, the same for every page: the site's icon with its
# colours swapped, the words "UK public EV charger map", a line on where the data comes
# from and OEVM, set in Inter, 1200 by 630 pixels. Its alt text describes it.
SHARE_IMAGE = "assets/share.png"
SHARE_IMAGE_SIZE = (1200, 630)
SHARE_IMAGE_ALT = "A lightning bolt in a white circle beside the words UK public EV charger map"
# Search results show about this many characters of a description.
DESCRIPTION_LENGTH = 160

MAP_TITLE = "UK public EV charger map with prices"
MAP_DESCRIPTION = (
    "Map of UK public EV chargers with prices per kWh, plug types and power, from the open "
    "data operators publish under the Public Charge Point Regulations 2023."
)
# A page's path is "" for the map, or its folder, such as "findings/".
PAGE_PATH = re.compile(r"(?:[a-z0-9-]+/)*")
TAG = re.compile(r"<[^>]*>")


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def address(path: str) -> str:
    """The full address of the page at path."""
    if not PAGE_PATH.fullmatch(path):
        raise ValueError(f"{path!r} is not a page's folder, such as 'findings/'")
    return SITE_URL + path


def description(text: str, limit: int = DESCRIPTION_LENGTH) -> str:
    """Text for a description: tags removed, spaces tidied, cut at a word if too long."""
    words = " ".join(html.unescape(TAG.sub("", text)).split())
    if len(words) <= limit:
        return words
    return words[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def head(path: str, title: str, summary: str, published: date | None = None) -> str:
    """The tags for a page's head: description, canonical link and Open Graph.

    title is the page's own title, without ": OEVM". A findings post passes the date it
    was published, so link previews can show it as an article.
    """
    url = address(path)
    width, height = SHARE_IMAGE_SIZE
    tags = [
        f'<meta name="description" content="{_e(summary)}">',
        f'<link rel="canonical" href="{_e(url)}">',
        f'<meta property="og:type" content="{"article" if published else "website"}">',
        f'<meta property="og:site_name" content="{_e(NAME)}">',
        '<meta property="og:locale" content="en_GB">',
        f'<meta property="og:title" content="{_e(title)}">',
        f'<meta property="og:description" content="{_e(summary)}">',
        f'<meta property="og:url" content="{_e(url)}">',
        f'<meta property="og:image" content="{_e(SITE_URL + SHARE_IMAGE)}">',
        f'<meta property="og:image:width" content="{width}">',
        f'<meta property="og:image:height" content="{height}">',
        f'<meta property="og:image:alt" content="{_e(SHARE_IMAGE_ALT)}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if published:
        tags.append(f'<meta property="article:published_time" content="{published.isoformat()}">')
    return "\n".join(tags)


def dataset() -> dict:
    """The map's data as a schema.org Dataset, for the map page.

    license points at the data sources and licences page, because each source keeps its
    own licence (DATA_LICENCES.md); no licence is given for the data as a whole. Who made
    the data is left out for the same reason: each operator made its own records.
    """
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "UK public EV charge points from operators' open data",
        "description": (
            "Locations, plug types, power and prices of public electric vehicle charge points "
            "across the UK, read each day from the open data that charge point operators "
            "publish under the Public Charge Point Regulations 2023. Each source keeps its own "
            "licence and is credited on the data sources and licences page."
        ),
        "url": SITE_URL,
        "inLanguage": "en-GB",
        "isAccessibleForFree": True,
        "license": address("data-licences/"),
        "spatialCoverage": "United Kingdom",
        "keywords": [
            "electric vehicle charging",
            "EV charge points",
            "charging prices",
            "OCPI",
            "Public Charge Point Regulations 2023",
            "United Kingdom",
        ],
        "distribution": [
            {
                "@type": "DataDownload",
                "encodingFormat": "application/geo+json",
                "contentUrl": f"{SITE_URL}data/locations.geojson",
            }
        ],
    }


def dataset_script() -> str:
    """The Dataset as a JSON-LD data block. Browsers never run it as a script."""
    data = json.dumps(dataset(), indent=1, ensure_ascii=False)
    if "<" in data:
        raise ValueError("the Dataset text must not contain '<'")
    return f'<script type="application/ld+json">\n{data}\n</script>'


def pages(out: Path) -> list[str]:
    """Every page in a build folder by its path: the map first, then the others by folder."""
    found = []
    for index in out.rglob("index.html"):
        folder = index.parent.relative_to(out).as_posix()
        found.append("" if folder == "." else f"{folder}/")
    return sorted(found, key=lambda path: (path.count("/"), path))


def sitemap(paths: Iterable[str]) -> str:
    """sitemap.xml for these pages (sitemaps.org protocol 0.9), with no change dates.

    Search engines use a change date only when every one is accurate, and pages built
    from Markdown or each day's data have none that is.
    """
    urls = "".join(f"<url><loc>{_e(address(path))}</loc></url>\n" for path in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )
