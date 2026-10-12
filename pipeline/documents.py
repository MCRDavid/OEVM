"""Publish the disclaimer, the data licences and the security policy as pages on the site.

    uv run python -m pipeline.build_site --out build    # writes these pages too

DISCLAIMER.md, DATA_LICENCES.md and SECURITY.md stay the only copy of each document. The
site build turns each into a page with the same disclaimer and footer links as the other
pages, so the site's own links stay on the site and only "Source code" goes to GitHub
(the owner's request, 11 October 2026). It also writes a "Report a mistake" page from the
issue forms in .github/ISSUE_TEMPLATE, whose links open the forms on GitHub. The pages
have no scripts and no cookies.

Only the Markdown these files use is understood: headings, paragraphs, quotes, lists,
tables, bold, code and links. Text is escaped before any of it becomes HTML, and links
go only to https addresses or to files in the repository.
"""

import re
from pathlib import Path

import yaml

from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT
from pipeline.transparency import LINKS, STYLE, _e, _link, short_disclaimer

# Each document and the folder its page is published in.
DOCUMENTS = {
    "DISCLAIMER.md": "disclaimer",
    "DATA_LICENCES.md": "data-licences",
    "SECURITY.md": "security",
}
REPORT_FOLDER = "report"
ISSUE_FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"

HEADING = re.compile(r"^(#{1,4}) (.+)$")
BULLET = re.compile(r"^[-*] (.*)$")
NUMBER = re.compile(r"^\d+\. (.*)$")
TABLE_RULE = re.compile(r"^\|?[\s:|-]+$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
# Code, [text](target) and bare https addresses, without trailing punctuation.
INLINE = re.compile(r"`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)|(https://[^\s<>|)`]*[^\s<>|)`.,;:])")

EXTRA_STYLE = """
blockquote { margin: 1rem 0; padding: 0.25rem 1rem; border-left: 4px solid var(--line);
  background: var(--note); }
code { font-size: 0.9em; overflow-wrap: anywhere; }
"""


class DocumentError(ValueError):
    """A document cannot be published as it is."""


def _href(target: str) -> str | None:
    """Where a link in a document goes: its page on the site, GitHub, or nowhere."""
    if target in DOCUMENTS:
        return f"../{DOCUMENTS[target]}/"
    if target.startswith("https://"):
        return target
    if ":" in target or target.startswith(("/", "#", ".")):
        return None  # only https addresses and repository files become links
    return f"{REPOSITORY_URL}/blob/main/{target}"


def _text(text: str) -> str:
    return BOLD.sub(r"<strong>\1</strong>", _e(text))


def inline(text: str) -> str:
    """Escape text, then turn code, bold, links and bare https addresses into HTML."""
    pieces, last = [], 0
    for match in INLINE.finditer(text):
        pieces.append(_text(text[last : match.start()]))
        code, label, target, url = match.groups()
        if code is not None:
            pieces.append(f"<code>{_e(code)}</code>")
        elif label is not None:
            href = _href(target)
            pieces.append(f'<a href="{_e(href)}">{_text(label)}</a>' if href else _text(label))
        elif "{" in url:
            pieces.append(_e(url))  # a template such as .../tariffs/{tariffId}, not a page
        else:
            pieces.append(_link(url, url))
        last = match.end()
    pieces.append(_text(text[last:]))
    return "".join(pieces)


def _starts_block(line: str) -> bool:
    return bool(HEADING.match(line) or BULLET.match(line) or NUMBER.match(line) or line[:1] in ">|")


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().removeprefix("|").removesuffix("|").split("|")]


def _table(rows: list[str]) -> str:
    header, *body = rows
    if body and TABLE_RULE.match(body[0]):
        body = body[1:]
    head = "".join(f'<th scope="col">{inline(cell)}</th>' for cell in _cells(header))
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in _cells(row)) + "</tr>"
        for row in body
    )
    return (
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{rows_html}</tbody></table></div>"
    )


def blocks(lines: list[str]) -> list[str]:
    """The HTML for each heading, paragraph, quote, list and table, in order."""
    parts, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif heading := HEADING.match(line):
            level = len(heading.group(1))
            parts.append(f"<h{level}>{inline(heading.group(2).strip())}</h{level}>")
            i += 1
        elif line.startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].startswith(">"):
                quoted.append(lines[i][1:].removeprefix(" "))
                i += 1
            parts.append(f"<blockquote>{''.join(blocks(quoted))}</blockquote>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            parts.append(_table(rows))
        elif BULLET.match(line) or NUMBER.match(line):
            marker = NUMBER if NUMBER.match(line) else BULLET
            items: list[list[str]] = []
            while i < len(lines):
                item = marker.match(lines[i])
                if item:
                    items.append([item.group(1)])
                elif lines[i].startswith(" ") and lines[i].strip():
                    items[-1].append(lines[i].strip())
                else:
                    break
                i += 1
            tag = "ol" if marker is NUMBER else "ul"
            entries = "".join(f"<li>{inline(' '.join(item))}</li>" for item in items)
            parts.append(f"<{tag}>{entries}</{tag}>")
        else:
            paragraph = []
            while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
                paragraph.append(lines[i].strip())
                i += 1
            parts.append(f"<p>{inline(' '.join(paragraph))}</p>")
    return parts


def render_document(markdown: str) -> tuple[str, str]:
    """The title (the document's first "# " heading) and the rest as HTML."""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.strip():
            title = HEADING.match(line)
            if not title or len(title.group(1)) != 1:
                raise DocumentError("a document must start with its title as '# Title'")
            return title.group(2).strip(), "\n".join(blocks(lines[index + 1 :]))
    raise DocumentError("the document is empty")


def page(title: str, body: str, source: str | None = None) -> str:
    """A page with the site's disclaimer and footer links, like the other pages."""
    links = "".join(f"<li>{_link(url, text)}</li>" for text, url in LINKS)
    origin = (
        f"This page is published from {_link(f'{REPOSITORY_URL}/blob/main/{source}', source)} "
        "in the project&rsquo;s source code. "
        if source
        else ""
    )
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}: OEVM</title>
<style>{STYLE}{EXTRA_STYLE}</style>
</head>
<body>
<header>
<h1>{_e(title)}</h1>
</header>
<main>
{body}
<p>{origin}Back to the <a href="../">map</a>.</p>
</main>
<footer>
<p class="note">{_e(short_disclaimer())}</p>
<ul>{links}</ul>
<p>This page has no cookies, no tracking and no scripts.</p>
</footer>
</body>
</html>
"""


def issue_forms(folder: Path = ISSUE_FORMS) -> tuple[list[dict], list[dict]]:
    """The public issue forms (name, description, url) and the private contact links."""
    forms = []
    # "Something else" goes last; the others keep their file order.
    for path in sorted(folder.glob("*.yml"), key=lambda p: (p.name == "other.yml", p.name)):
        if path.name == "config.yml":
            continue
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        forms.append(
            {
                "name": form["name"],
                "about": form["description"],
                "url": f"{REPOSITORY_URL}/issues/new?template={path.name}",
            }
        )
    config_path = folder / "config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    contacts = [
        {"name": link["name"], "about": link["about"], "url": link["url"]}
        for link in (config or {}).get("contact_links", [])
    ]
    if not forms:
        raise DocumentError(f"no issue forms found in {folder}")
    return forms, contacts


def report_page(folder: Path = ISSUE_FORMS) -> str:
    forms, contacts = issue_forms(folder)
    public = "".join(
        f"<li>{_link(form['url'], form['name'])}: {_e(form['about'])}</li>" for form in forms
    )
    private = "".join(
        f"<li>{_link(link['url'], link['name'])}: {_e(link['about'])}</li>" for link in contacts
    )
    body = (
        "<p>Thank you for helping to put things right. Each link below opens a form on GitHub, "
        "where this project keeps its list of reports. You need a GitHub account to send one. "
        "Reports are public, so please do not include personal information such as your "
        "name, email address or where you live.</p>"
        f"<ul>{public}</ul>"
        + (
            "<h2>Reporting privately</h2>"
            f"<ul>{private}</ul>"
            '<p>The <a href="../security/">security policy</a> says what happens next.</p>'
            if private
            else ""
        )
    )
    return page("Report a mistake", body)


def outputs(out: Path, root: Path = ROOT) -> dict[Path, str]:
    """Every page this module publishes, by where it goes in the build folder."""
    files = {}
    for name, folder in DOCUMENTS.items():
        title, body = render_document((root / name).read_text(encoding="utf-8"))
        files[out / folder / "index.html"] = page(title, body, name)
    files[out / REPORT_FOLDER / "index.html"] = report_page(root / ".github" / "ISSUE_TEMPLATE")
    return files


def write(out: Path) -> list[Path]:
    written = []
    for path, text in outputs(out).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
