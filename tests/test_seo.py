"""What search engines and link previews read from each page (pipeline/seo.py)."""

import json
import xml.etree.ElementTree as ET
from datetime import date

import pytest

from pipeline import seo
from pipeline.project import SITE_URL


def test_the_site_address_is_https_and_ends_with_a_slash():
    assert SITE_URL.startswith("https://") and SITE_URL.endswith("/")


@pytest.mark.parametrize("path", ["", "findings/", "findings/statuses-every-hour/"])
def test_a_page_address_is_the_site_address_and_its_folder(path):
    assert seo.address(path) == SITE_URL + path


@pytest.mark.parametrize("path", ["/", "findings", "../x/", "https://example.com/", "a b/"])
def test_anything_but_a_page_folder_is_refused(path):
    with pytest.raises(ValueError):
        seo.address(path)


def test_a_description_loses_its_tags_and_extra_spaces():
    assert seo.description('Prices <a href="x">and</a>\n  VAT &amp; more.') == (
        "Prices and VAT & more."
    )


def test_a_long_description_is_cut_at_a_word():
    text = "word " * 60
    cut = seo.description(text)
    assert len(cut) <= seo.DESCRIPTION_LENGTH
    assert cut.endswith("word…")


def test_head_escapes_text_and_names_the_page_once():
    tags = seo.head("findings/", 'Prices "with" <VAT>', "A & B")
    assert '<meta name="description" content="A &amp; B">' in tags
    assert 'content="Prices &quot;with&quot; &lt;VAT&gt;"' in tags
    assert tags.count(f'"{SITE_URL}findings/"') == 2  # canonical link and og:url
    assert '<meta property="og:type" content="website">' in tags
    assert f'content="{SITE_URL}{seo.SHARE_IMAGE}"' in tags
    assert "article:published_time" not in tags


def test_a_post_is_an_article_with_its_date():
    tags = seo.head("findings/a-post/", "A post", "Summary.", date(2026, 11, 13))
    assert '<meta property="og:type" content="article">' in tags
    assert '<meta property="article:published_time" content="2026-11-13">' in tags


def test_the_dataset_gives_no_licence_of_its_own():
    # Each source keeps its own licence (DATA_LICENCES.md), so license points at that page.
    data = seo.dataset()
    assert data["license"] == f"{SITE_URL}data-licences/"
    assert "creator" not in data and "Apache" not in json.dumps(data)
    assert data["distribution"][0]["contentUrl"] == f"{SITE_URL}data/locations.geojson"


def test_the_dataset_script_cannot_end_early():
    assert "</script>" not in seo.dataset_script().removesuffix("</script>")


def test_pages_lists_the_map_first_then_each_folder(tmp_path):
    for folder in ("findings/b-post", "status", "", "findings", "vendor/maplibre-gl"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
        if folder != "vendor/maplibre-gl":
            (tmp_path / folder / "index.html").write_text("page", encoding="utf-8")
    assert seo.pages(tmp_path) == ["", "findings/", "status/", "findings/b-post/"]


def test_the_sitemap_is_valid_xml_with_one_entry_per_page():
    root = ET.fromstring(seo.sitemap(["", "status/"]))
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    assert root.tag == f"{namespace}urlset"
    assert [loc.text for loc in root.iter(f"{namespace}loc")] == [SITE_URL, f"{SITE_URL}status/"]
    assert not list(root.iter(f"{namespace}lastmod"))
