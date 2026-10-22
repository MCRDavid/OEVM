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


POSTS = sorted(p.name for p in documents.FINDINGS.glob("*.md") if p.name != "README.md")


def test_each_document_the_report_page_and_the_findings_are_published(pages):
    names = {post["name"] for post in documents.posts()}
    assert len(names) == len(POSTS) > 0
    assert set(pages) == {"disclaimer", "data-licences", "security", "report", "findings"} | names


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


@pytest.mark.parametrize("file", POSTS)
def test_every_word_of_each_post_is_on_its_page(pages, file):
    markdown = (documents.FINDINGS / file).read_text(encoding="utf-8")
    markdown = re.sub(r"(?m)^\d+\. ", "", re.sub(r"\]\([^)]*\)", "]", markdown))
    name = documents.POST_NAME.match(file).group(2)
    page = pages[name]
    shown = set(re.findall(r"\w+", " ".join(parse(page).text)))
    assert set(re.findall(r"\w+", markdown)) - shown == set()
    assert "**" not in page and "](" not in page and "`" not in page
    assert f'<a href="{REPOSITORY_URL}/blob/main/findings/{file}">findings/{file}</a>' in page


@pytest.mark.parametrize("file", POSTS)
def test_each_post_page_has_the_disclaimer_footer_links_and_its_date(pages, file):
    name = documents.POST_NAME.match(file).group(2)
    page = pages[name]
    parsed = parse(page)
    assert '<html lang="en-GB">' in page and chr(0x2014) not in page
    assert html.escape(short_disclaimer(), quote=True) in page
    # Posts are one folder deeper, so the site's own links climb two folders.
    for _, url in LINKS:
        assert (url.replace("../", "../../", 1) if url.startswith("../") else url) in parsed.hrefs
    assert not {"script", "img", "iframe", "link"} & set(parsed.tags)
    assert "../" in parsed.hrefs and "../../" in parsed.hrefs  # all findings, and the map
    published = file[:10]
    assert f'Published <time datetime="{published}">' in page
    assert not [
        href
        for href in parsed.hrefs
        if href.startswith("../") and "../../" not in href and href != "../"
    ]


def test_the_findings_page_lists_every_post_newest_first(pages):
    page = pages["findings"]
    parsed = parse(page)
    assert '<html lang="en-GB">' in page and chr(0x2014) not in page
    for _, url in LINKS:
        assert url in parsed.hrefs
    listed = [post["name"] + "/" for post in documents.posts()]
    assert [href for href in parsed.hrefs if href in listed] == listed
    dates = [post["date"] for post in documents.posts()]
    assert dates == sorted(dates, reverse=True)
    for post in documents.posts():
        assert html.escape(post["title"]) in page and post["summary"] in page
    assert f'<a href="{REPOSITORY_URL}/blob/main/findings/README.md">' in page


def test_posts_are_ordered_newest_first_then_by_their_number(tmp_path):
    (tmp_path / "README.md").write_text("# Findings\n\nIntro.\n", encoding="utf-8")
    for name, title in [
        ("2026-10-17-02-second.md", "Second"),
        ("2026-10-17-01-first.md", "First"),
        ("2026-10-18-later.md", "Later"),
        ("2026-09-30-older.md", "Older"),
    ]:
        (tmp_path / name).write_text(f"# {title}\n\nSummary of {title}.\n\nMore.\n", "utf-8")
    found = documents.posts(tmp_path)
    assert [post["name"] for post in found] == ["later", "first", "second", "older"]
    assert found[1]["summary"] == "Summary of First."
    assert found[1]["source"] == "findings/2026-10-17-01-first.md"
    page = documents.findings_page(tmp_path)
    assert page.index('href="later/"') < page.index('href="first/"') < page.index('href="older/"')
    assert '<time datetime="2026-09-30">30 September 2026</time>' in page


@pytest.mark.parametrize(
    "name, error",
    [
        ("17-10-2026-post.md", "file name"),
        ("2026-10-17-Post.md", "file name"),
        ("2026-10-17-post_one.md", "file name"),
        ("2026-13-01-post.md", "not a date"),
    ],
)
def test_a_post_needs_a_dated_lower_case_file_name(tmp_path, name, error):
    (tmp_path / name).write_text("# Title\n\nSummary.\n", encoding="utf-8")
    with pytest.raises(documents.DocumentError, match=error):
        documents.posts(tmp_path)


def test_two_posts_cannot_share_an_address(tmp_path):
    for name in ("2026-10-17-same.md", "2026-10-18-same.md"):
        (tmp_path / name).write_text("# Title\n\nSummary.\n", encoding="utf-8")
    with pytest.raises(documents.DocumentError, match="already uses same/"):
        documents.posts(tmp_path)


@pytest.mark.parametrize("markdown", ["# Title\n\n## Heading first\n", "# Title\n\n- a list\n"])
def test_a_post_must_start_with_a_summary_paragraph(tmp_path, markdown):
    (tmp_path / "2026-10-17-post.md").write_text(markdown, encoding="utf-8")
    with pytest.raises(documents.DocumentError, match="paragraph that sums it up"):
        documents.posts(tmp_path)


def test_links_to_the_site_own_pages_follow_the_page_depth():
    text = "[t](transparency/) [f](findings/data-quality/) [d](DISCLAIMER.md) [o](operators/)"
    top = documents.inline(text)
    assert '<a href="../transparency/">t</a>' in top
    assert '<a href="../findings/data-quality/">f</a>' in top
    assert '<a href="../disclaimer/">d</a>' in top
    # A folder that is not one of the site's pages is a repository folder, as before.
    assert f'<a href="{REPOSITORY_URL}/blob/main/operators/">o</a>' in top
    deep = documents.inline(text, up="../../")
    assert '<a href="../../transparency/">t</a>' in deep
    assert '<a href="../../disclaimer/">d</a>' in deep
