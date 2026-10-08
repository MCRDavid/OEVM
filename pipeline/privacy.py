"""Publish the privacy notice as a page on the site (blueprint task 10).

    uv run python -m pipeline.privacy            # writes site/privacy/index.html
    uv run python -m pipeline.privacy --check    # CI: fail if the page is out of date

The notice is written once, as the quoted text under "## Notice for the site" in
docs/PRIVACY_AND_COOKIES.md, and this turns it into the page visitors read, so the two
cannot drift apart. The page has the same disclaimer and links as the other pages, no
scripts and no cookies.
"""

import argparse
import re
import sys
from pathlib import Path

from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT
from pipeline.transparency import LINKS, STYLE, _e, _link, short_disclaimer

NOTICE_PATH = ROOT / "docs" / "PRIVACY_AND_COOKIES.md"
PAGE_PATH = ROOT / "site" / "privacy" / "index.html"
HEADING = "## Notice for the site"
URL = re.compile(r"https://[^\s)]+")
BOLD = re.compile(r"\*\*(.+?)\*\*")
LAST_UPDATED = re.compile(r"^Last updated: (\d{1,2} \w+ \d{4})\.$")


class NoticeError(ValueError):
    """The notice in docs/PRIVACY_AND_COOKIES.md cannot be published as it is."""


def notice_paragraphs(path: Path | None = None) -> list[str]:
    """The quoted notice, one string per paragraph, with line breaks joined."""
    path = path or NOTICE_PATH
    paragraphs: list[list[str]] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == HEADING
            continue
        if not inside or not line.startswith(">"):
            continue
        text = line[1:].strip()
        if not text:
            paragraphs.append([])
        elif paragraphs and paragraphs[-1]:
            paragraphs[-1].append(text)
        else:
            paragraphs.append([text])
    result = [" ".join(p) for p in paragraphs if p]
    if not result:
        raise NoticeError(f"no quoted notice under '{HEADING}' in {path}")
    if "[" in " ".join(result):
        raise NoticeError("the notice still has a part in square brackets to fill in")
    if not LAST_UPDATED.match(result[-1]):
        raise NoticeError("the notice must end with 'Last updated: <day> <month> <year>.'")
    return result


def _inline(text: str) -> str:
    """Escape text, then turn **bold** into <strong> and full https addresses into links."""
    pieces, last = [], 0
    for match in URL.finditer(text):
        pieces.append(BOLD.sub(r"<strong>\1</strong>", _e(text[last : match.start()])))
        pieces.append(_link(match.group(0), match.group(0)))
        last = match.end()
    pieces.append(BOLD.sub(r"<strong>\1</strong>", _e(text[last:])))
    return "".join(pieces)


def render_html(paragraphs: list[str]) -> str:
    title = BOLD.fullmatch(paragraphs[0])
    if not title:
        raise NoticeError("the notice must start with its title in bold")
    body = "\n".join(f"<p>{_inline(p)}</p>" for p in paragraphs[1:])
    links = "".join(f"<li>{_link(url, text)}</li>" for text, url in LINKS)
    rules = f"{REPOSITORY_URL}/blob/main/docs/PRIVACY_AND_COOKIES.md"
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title.group(1))}: OEVM</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>{_e(title.group(1))}</h1>
</header>
<main>
{body}
<p>The rules this site is built to, and the law they follow, are in
{_link(rules, "PRIVACY_AND_COOKIES.md")}. Back to the <a href="../">map</a>.</p>
</main>
<footer>
<p class="note">{_e(short_disclaimer())}</p>
<ul>{links}</ul>
<p>This page has no cookies, no tracking and no scripts.</p>
</footer>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.privacy", description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the page is stale")
    args = parser.parse_args(argv)
    try:
        page = render_html(notice_paragraphs(NOTICE_PATH))
    except NoticeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    current = PAGE_PATH.read_text(encoding="utf-8") if PAGE_PATH.exists() else None
    shown = PAGE_PATH.relative_to(ROOT)
    if current == page:
        print(f"{shown} is up to date.")
        return 0
    if args.check:
        print(f"{shown} is out of date. Run: uv run python -m pipeline.privacy", file=sys.stderr)
        return 1
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAGE_PATH.write_text(page, encoding="utf-8")
    print(f"Wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
