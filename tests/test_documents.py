"""The disclaimer, data licences, security policy and report pages (pipeline/documents.py)."""

import html
import re
from html.parser import HTMLParser

import pytest
import yaml

from pipeline import documents
from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT
from pipeline.transparency import LINKS, short_disclaimer


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tags: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.hrefs.append(dict(attrs)["href"])

    def handle_data(self, data):
        self.text.append(data)


def parse(page: str) -> Text:
    parsed = Text()
    parsed.feed(page)
    return parsed


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> dict[str, str]:
    out = tmp_path_factory.mktemp("build")
    return {
        path.parent.name: text
        for path, text in documents.outputs(out).items()
        if path.is_relative_to(out)
    }


def test_each_document_and_the_report_page_is_published(pages):
    assert set(pages) == {"disclaimer", "data-licences", "security", "report"}


@pytest.mark.parametrize("name", sorted(documents.DOCUMENTS))
def test_every_word_of_each_document_is_on_its_page(pages, name):
    markdown = (ROOT / name).read_text(encoding="utf-8")
    # Link targets and the numbers of numbered lists are not shown as text.
    markdown = re.sub(r"(?m)^\d+\. ", "", re.sub(r"\]\([^)]*\)", "]", markdown))
    words = set(re.findall(r"\w+", markdown))
    shown = set(re.findall(r"\w+", " ".join(parse(pages[documents.DOCUMENTS[name]]).text)))
    assert words - shown == set()
    page = pages[documents.DOCUMENTS[name]]
    assert "**" not in page and "](" not in page and "`" not in page
    assert f'<a href="{REPOSITORY_URL}/blob/main/{name}">{name}</a>' in page


@pytest.mark.parametrize("folder", ["disclaimer", "data-licences", "security", "report"])
def test_each_page_has_the_disclaimer_and_footer_links_and_no_scripts(pages, folder):
    page = pages[folder]
    parsed = parse(page)
    assert '<html lang="en-GB">' in page and chr(0x2014) not in page
    assert html.escape(short_disclaimer(), quote=True) in page
    for _, url in LINKS:
        assert url in parsed.hrefs
    assert not {"script", "img", "iframe", "link"} & set(parsed.tags)
    assert "../" in parsed.hrefs  # back to the map


def test_the_footer_links_stay_on_the_site_except_source_code():
    elsewhere = [text for text, url in LINKS if not url.startswith("../")]
    assert elsewhere == ["Source code"]
    assert dict(LINKS)["Source code"] == REPOSITORY_URL


def test_the_report_page_lists_every_issue_form_and_the_private_route(pages):
    page = pages["report"]
    forms = sorted(p for p in documents.ISSUE_FORMS.glob("*.yml") if p.name != "config.yml")
    assert forms
    for path in forms:
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        link = f"{REPOSITORY_URL}/issues/new?template={path.name}"
        assert f'<a href="{link}">{html.escape(form["name"])}</a>' in page
    assert f'href="{REPOSITORY_URL}/security/advisories/new"' in page
    assert 'href="../security/"' in page
    assert page.index("template=other.yml") > page.index("template=correction.yml")
    assert "Reports are public" in page


def test_text_is_escaped_and_only_https_and_repository_links_are_made():
    out = documents.inline(
        "**Bold** <b>x</b> [s](SECURITY.md) [l](LICENSE) [j](javascript:alert(1)) "
        "[h](http://plain) see https://example.org/a/b, `<code>` and "
        "https://example.org/tariffs/{id} too."
    )
    assert out.startswith("<strong>Bold</strong> &lt;b&gt;x&lt;/b&gt;")
    assert '<a href="../security/">s</a>' in out
    assert f'<a href="{REPOSITORY_URL}/blob/main/LICENSE">l</a>' in out
    assert "javascript" not in re.sub(r">[^<]*<", "><", out)  # shown as text only
    assert 'href="http://plain"' not in out
    assert '<a href="https://example.org/a/b">https://example.org/a/b</a>,' in out
    assert "<code>&lt;code&gt;</code>" in out
    assert "https://example.org/tariffs/{id}" in out and 'href="https://example.org/t' not in out


def test_headings_lists_quotes_and_tables():
    title, body = documents.render_document(
        "# Title\n\n## Part\n\nOne line\nand the next.\n\n"
        "- first\n  continued\n- second\n\n1. one\n2. two\n\n> quoted\n> text\n\n"
        "| A | B |\n|---|---|\n| 1 | **2** |\n"
    )
    assert title == "Title"
    assert body.split("\n") == [
        "<h2>Part</h2>",
        "<p>One line and the next.</p>",
        "<ul><li>first continued</li><li>second</li></ul>",
        "<ol><li>one</li><li>two</li></ol>",
        "<blockquote><p>quoted text</p></blockquote>",
        '<div class="table-wrap"><table><thead><tr><th scope="col">A</th>'
        '<th scope="col">B</th></tr></thead><tbody><tr><td>1</td>'
        "<td><strong>2</strong></td></tr></tbody></table></div>",
    ]


@pytest.mark.parametrize("markdown", ["", "\n\n", "No title\n", "## Not a title\n"])
def test_a_document_must_start_with_its_title(markdown):
    with pytest.raises(documents.DocumentError):
        documents.render_document(markdown)


def test_the_report_page_needs_issue_forms(tmp_path):
    with pytest.raises(documents.DocumentError, match="no issue forms"):
        documents.report_page(tmp_path)
