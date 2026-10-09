"""The site build (pipeline/build_site.py) and rules for the committed map page."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from pipeline import build_site
from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT
from pipeline.transparency import short_disclaimer

INDEX = ROOT / "site" / "index.html"
SCRIPTS = sorted((ROOT / "site" / "assets" / "js").glob("*.js"))


class Page(HTMLParser):
    """Collects links, meta tags, scripts and the text of the footer note."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.meta: dict[str, str] = {}
        self.scripts: list[dict] = []
        self.note: list[str] = []
        self._in_note = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.hrefs.append(attributes["href"])
        if tag == "meta":
            key = attributes.get("http-equiv") or attributes.get("name")
            if key:
                self.meta[key.lower()] = attributes.get("content", "")
        if tag == "script":
            self.scripts.append(attributes)
        if tag == "p" and attributes.get("class") == "note":
            self._in_note = True

    def handle_endtag(self, tag):
        if tag == "p":
            self._in_note = False

    def handle_data(self, data):
        if self._in_note:
            self.note.append(data)


@pytest.fixture(scope="module")
def page() -> Page:
    parsed = Page()
    parsed.feed(INDEX.read_text(encoding="utf-8"))
    return parsed


def test_the_map_page_shows_the_short_disclaimer(page):
    assert " ".join("".join(page.note).split()) == short_disclaimer()


def test_the_map_page_links_to_the_required_documents(page):
    for path in ("DISCLAIMER.md", "DATA_LICENCES.md", "SECURITY.md"):
        assert f"{REPOSITORY_URL}/blob/main/{path}" in page.hrefs
    assert "transparency/" in page.hrefs
    assert "privacy/" in page.hrefs
    github = [href for href in page.hrefs if urlsplit(href).hostname == "github.com"]
    assert github and all(
        href.startswith(f"{REPOSITORY_URL}/") or href == REPOSITORY_URL for href in github
    )


def test_the_footer_tells_visitors_about_the_basemap_and_its_error_reports():
    # The owner accepted OpenFreeMap's Network Error Logging headers on condition that the
    # page says so (docs/PRIVACY_AND_COOKIES.md, rule 2).
    text = " ".join(INDEX.read_text(encoding="utf-8").split())
    assert "map files for the area on screen from OpenFreeMap" in text
    assert "Network Error Logging" in text
    assert "ask your browser to keep" in text, "the stored policy is mentioned, not only reports"


def test_the_content_security_policy_allows_only_this_site_and_the_basemap(page):
    policy = page.meta["content-security-policy"]
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    hosts = set(re.findall(r"https://[^\s;]+", policy))
    assert hosts == {"https://tiles.openfreemap.org"}
    assert build_site.STYLE_URL.startswith("https://tiles.openfreemap.org/")
    assert build_site.DARK_STYLE_URL.startswith("https://tiles.openfreemap.org/")
    assert "default-src 'none'" in policy and "script-src 'self'" in policy
    # Only the origin, even to this site, so filters in the address (which can come from
    # saved settings) are never sent in a Referer header.
    assert page.meta["referrer"] == "strict-origin"


def test_scripts_are_local_modules(page):
    assert page.scripts == [{"type": "module", "src": "assets/js/main.js"}]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_scripts_never_insert_html_or_run_strings(script):
    code = script.read_text(encoding="utf-8")
    for pattern in (
        r"\.innerHTML",
        r"\.outerHTML",
        r"insertAdjacentHTML",
        r"document\.write",
        r"\beval\(",
        r"new Function\(",
        r"document\.cookie",
        r"sessionStorage",
        r"indexedDB",
    ):
        assert not re.search(pattern, code), f"{script.name} uses {pattern}"


def test_only_settings_and_its_set_up_touch_storage():
    for script in SCRIPTS:
        code = script.read_text(encoding="utf-8")
        uses = re.findall(r"(?:localStorage|setItem|removeItem)", code)
        if script.name == "settings.js":
            assert "setItem" in uses and "removeItem" in uses
        elif script.name == "main.js":
            assert uses == ["localStorage"], "main.js only hands localStorage to settings.js"
        else:
            assert not uses, script.name


def test_maplibre_is_pinned_to_one_exact_version():
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d+\.\d+\.\d+", build_site.MAPLIBRE_VERSION)
    assert lock["packages"]["node_modules/maplibre-gl"]["version"] == build_site.MAPLIBRE_VERSION


# Building, with a small fake node_modules so these tests need neither npm nor the network.


def _write_package(root: Path, name: str, meta: dict, files: dict[str, str]) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "package.json").write_text(json.dumps({"name": name, **meta}), encoding="utf-8")
    for path, text in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


@pytest.fixture
def node_modules(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "node_modules"
    dist = {f"dist/{name}": f"/* {name} */" for name in build_site.MAPLIBRE_FILES}
    _write_package(
        root,
        "maplibre-gl",
        {
            "version": build_site.MAPLIBRE_VERSION,
            "dependencies": {"with-licence": "1", "no-licence-file": "1"},
        },
        {"LICENSE.txt": "MapLibre licence text", **dist},
    )
    _write_package(
        root,
        "with-licence",
        {"version": "1.2.3", "license": "ISC"},
        {"LICENSE": "ISC licence text"},
    )
    _write_package(
        root,
        "no-licence-file",
        {"version": "0.1.0", "license": "MIT", "author": {"name": "A. Author"}},
        {},
    )
    monkeypatch.setattr(build_site, "NODE_MODULES", root)
    return root


def test_build_copies_the_site_maplibre_and_notices(node_modules, tmp_path):
    out = tmp_path / "build"
    report = build_site.build(out)
    assert (out / "index.html").read_bytes() == INDEX.read_bytes()
    vendor = out / "vendor" / "maplibre-gl"
    for name in build_site.MAPLIBRE_FILES:
        assert (vendor / name).read_text(encoding="utf-8") == f"/* {name} */"
    assert (vendor / "LICENSE.txt").read_text(encoding="utf-8") == "MapLibre licence text"
    notices = (vendor / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    assert "with-licence 1.2.3 (ISC)" in notices and "ISC licence text" in notices
    assert "no-licence-file 0.1.0 (MIT)" in notices
    assert "declares the MIT licence, author A. Author." in notices
    config = json.loads((out / "assets" / "config.json").read_text(encoding="utf-8"))
    assert config == {
        "style": build_site.STYLE_URL,
        "darkStyle": build_site.DARK_STYLE_URL,
        "origins": ["https://tiles.openfreemap.org"],
        "repository": REPOSITORY_URL,
        "maxBounds": build_site.MAX_BOUNDS,
        "maplibre": build_site.MAPLIBRE_VERSION,
    }
    assert not (out / "assets" / "offline-style.json").exists()
    assert f"map style: {build_site.STYLE_URL}" in report


def test_offline_style_build_needs_no_outside_service(node_modules, tmp_path):
    out = tmp_path / "build"
    build_site.build(out, offline_style=True)
    config = json.loads((out / "assets" / "config.json").read_text(encoding="utf-8"))
    assert config["style"] == "assets/offline-style.json"
    assert config["origins"] == []
    style = json.loads((out / "assets" / "offline-style.json").read_text(encoding="utf-8"))
    assert style == build_site.OFFLINE_STYLE
    assert "http" not in json.dumps(style)
    assert config["darkStyle"] == "assets/offline-style-dark.json"
    dark = json.loads((out / "assets" / "offline-style-dark.json").read_text(encoding="utf-8"))
    assert dark == build_site.OFFLINE_DARK_STYLE
    assert "http" not in json.dumps(dark)


@pytest.mark.parametrize("out", [Path("."), Path("site"), Path("site/build"), Path("site/a/b")])
def test_build_refuses_the_committed_site_folder_and_folders_inside_or_around_it(node_modules, out):
    with pytest.raises(build_site.BuildError, match="not the committed site/"):
        build_site.build(ROOT / out)
    assert not (build_site.SITE / "build").exists() and not (build_site.SITE / "a").exists()


def test_build_needs_npm_ci(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "NODE_MODULES", tmp_path / "missing")
    with pytest.raises(build_site.BuildError, match="run 'npm ci' first"):
        build_site.build(tmp_path / "build")


def test_build_refuses_a_different_maplibre_version(node_modules, tmp_path):
    package = node_modules / "maplibre-gl" / "package.json"
    meta = json.loads(package.read_text(encoding="utf-8"))
    package.write_text(json.dumps({**meta, "version": "0.0.1"}), encoding="utf-8")
    with pytest.raises(build_site.BuildError, match=r"0\.0\.1"):
        build_site.build(tmp_path / "build")


def test_command_line(node_modules, tmp_path, capsys):
    assert build_site.main(["--out", str(tmp_path / "build"), "--offline-style"]) == 0
    assert "assets/offline-style.json" in capsys.readouterr().out
    assert build_site.main(["--out", str(build_site.SITE)]) == 1
    assert "Error:" in capsys.readouterr().err
