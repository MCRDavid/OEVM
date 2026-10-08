"""The privacy notice page (pipeline/privacy.py, blueprint task 10)."""

import html
import re

import pytest

from pipeline import privacy
from pipeline.project import REPOSITORY_URL
from pipeline.transparency import short_disclaimer


@pytest.fixture(scope="module")
def page() -> str:
    return privacy.render_html(privacy.notice_paragraphs())


def test_the_committed_page_is_up_to_date():
    assert privacy.main(["--check"]) == 0


def test_every_paragraph_of_the_notice_is_on_the_page(page):
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    for paragraph in privacy.notice_paragraphs()[1:]:
        assert paragraph.replace("**", "") in " ".join(text.split())


def test_the_page_names_every_party_that_sees_a_visit(page):
    for name in ("GitHub Pages", "OpenFreeMap", "Cloudflare", "Network Error Logging"):
        assert name in page
    for url in (
        "https://openfreemap.org/privacy/",
        "https://www.cloudflare.com/privacypolicy/",
    ):
        assert f'href="{url}"' in page


def test_the_page_shows_the_disclaimer_and_required_links(page):
    assert html.escape(short_disclaimer(), quote=True) in page
    for path in ("DISCLAIMER.md", "DATA_LICENCES.md", "SECURITY.md", "docs/PRIVACY_AND_COOKIES.md"):
        assert f"{REPOSITORY_URL}/blob/main/{path}" in page
    assert "<script" not in page


def test_text_is_escaped_and_only_https_addresses_become_links():
    out = privacy._inline("**Bold** <b>x</b> see https://example.org/a (b) and http://plain")
    assert out.startswith("<strong>Bold</strong> &lt;b&gt;x&lt;/b&gt;")
    assert '<a href="https://example.org/a">https://example.org/a</a>' in out
    assert "http://plain" in out and 'href="http://plain"' not in out


def _notice(tmp_path, body: str):
    path = tmp_path / "notice.md"
    path.write_text(f"# Doc\n\n## Notice for the site\n\n{body}\n\n## Next\n\n> not this\n")
    return path


def test_unfinished_notices_are_refused(tmp_path):
    with pytest.raises(privacy.NoticeError, match="square brackets"):
        privacy.notice_paragraphs(_notice(tmp_path, "> **T**\n>\n> Last updated: [date]."))
    with pytest.raises(privacy.NoticeError, match="Last updated"):
        privacy.notice_paragraphs(_notice(tmp_path, "> **T**\n>\n> Some text."))
    with pytest.raises(privacy.NoticeError, match="no quoted notice"):
        privacy.notice_paragraphs(_notice(tmp_path, "Not quoted."))
    paragraphs = privacy.notice_paragraphs(
        _notice(tmp_path, "> **T**\n>\n> One\n> two.\n>\n> Last updated: 8 October 2026.")
    )
    assert paragraphs == ["**T**", "One two.", "Last updated: 8 October 2026."]
    with pytest.raises(privacy.NoticeError, match="title in bold"):
        privacy.render_html(["Plain title", "Last updated: 8 October 2026."])


def test_command_line_reports_a_stale_page(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(privacy, "PAGE_PATH", tmp_path / "privacy" / "index.html")
    monkeypatch.setattr(privacy, "ROOT", tmp_path)
    assert privacy.main(["--check"]) == 1
    assert "out of date" in capsys.readouterr().err
    assert privacy.main([]) == 0
    assert privacy.main(["--check"]) == 0
    monkeypatch.setattr(privacy, "NOTICE_PATH", _notice(tmp_path, "> nothing finished [x]"))
    assert privacy.main([]) == 1
