"""The map page in a real browser (blueprint task 9).

These tests build the site from the recorded fixtures with the offline map style, serve it
on this computer and drive Chromium with Playwright. The browser is told to refuse every
other host, so nothing here reaches the internet.

They need 'npm ci' (for MapLibre and Lighthouse) and a Chromium or Chrome browser. Set
CHROME_PATH to the browser if Playwright cannot find its own. Without them the tests are
skipped, unless OEVM_REQUIRE_E2E=1 (as in CI), when they fail instead.
"""

import functools
import json
import os
import re
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import expect

from pipeline import build_site, run
from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT

pytestmark = pytest.mark.e2e
REQUIRED = os.environ.get("OEVM_REQUIRE_E2E") == "1"
PHONE = {"width": 412, "height": 823}  # a common mid-range Android screen, in CSS pixels
WIDE = {"width": 1280, "height": 800}
# Software WebGL for headless Chromium, and no host other than this computer. Waits use
# expect() and locators, because the page's Content Security Policy blocks the string
# evaluation that wait_for_function relies on.
BROWSER_ARGS = [
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
]
LOCATIONS = 13  # in the recorded fixtures
# MapLibre writes the map position after the # a moment after the map settles, starting
# from 0/0/0.
MAP_SETTLED = re.compile(r"#[1-9][0-9.]*/")


def _unavailable(reason: str):
    if REQUIRED:
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> str:
    if not (build_site.NODE_MODULES / "maplibre-gl").exists():
        _unavailable("node_modules is missing; run 'npm ci'")
    out = tmp_path_factory.mktemp("site")
    assert run.main(["--fixtures", "--publish", str(out)]) == 0
    build_site.build(out, offline_style=True)

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=out))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(
                executable_path=os.environ.get("CHROME_PATH") or None, args=BROWSER_ARGS
            )
        except Error as exc:
            first_line = str(exc).splitlines()[0]
            _unavailable(f"no browser for Playwright (set CHROME_PATH): {first_line}")
        yield chromium
        chromium.close()


class Visit:
    """One fresh browser profile on the map page, recording problems and outside requests."""

    def __init__(self, browser, site: str, viewport: dict, init_script: str | None = None):
        self.site = site
        self.context = browser.new_context(viewport=viewport, locale="en-GB")
        if init_script:
            self.context.add_init_script(init_script)
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.outside: list[str] = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on(
            "console",
            lambda message: message.type == "error" and self.errors.append(message.text),
        )
        self.page.on(
            "request",
            lambda request: request.url.startswith(site) or self.outside.append(request.url),
        )

    def open(self, query: str = "", *, map_ready: bool = True):
        self.page.goto(self.site + query)
        if map_ready:
            expect(self.page.locator("#list-summary")).to_contain_text("map area")
            expect(self.page).to_have_url(MAP_SETTLED)
        return self.page

    def stored(self) -> dict:
        return self.page.evaluate(
            "() => Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage[k]]))"
        )

    def close(self):
        self.context.close()


@pytest.fixture
def visit(site, browser):
    visits = []

    def start(viewport=PHONE, init_script=None):
        visits.append(Visit(browser, site, viewport, init_script))
        return visits[-1]

    yield start
    for v in visits:
        v.close()


def open_filters(page):
    if page.get_attribute("#toggle-filters", "aria-expanded") != "true":
        page.click("#toggle-filters")


def test_map_loads_on_a_phone_with_nothing_from_outside(visit):
    v = visit()
    page = v.open()
    assert page.locator("#map canvas").count() == 1
    assert page.text_content("#list-summary").startswith(f"{LOCATIONS} charger locations")
    assert page.is_hidden("#notice")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.evaluate("document.cookie") == ""
    assert v.stored() == {}
    assert v.outside == []
    assert v.errors == []


def test_wide_screens_show_the_map_and_list_together(visit):
    page = visit(WIDE).open()
    assert page.is_visible("#map") and page.is_visible("#list")
    assert page.is_hidden("#show-map")
    assert page.locator("#list-items li").count() == LOCATIONS


def test_filters_change_the_list_and_the_address(visit):
    v = visit()
    page = v.open()
    open_filters(page)
    page.select_option("#minkw", "50")
    page.wait_for_url("**minkw=50**")
    rapid = page.text_content("#list-summary")
    assert not rapid.startswith(f"{LOCATIONS} ")
    position = page.url.split("#")[1]
    page.reload()
    expect(page.locator("#list-summary")).to_contain_text("map area")
    expect(page).to_have_url(MAP_SETTLED)
    assert page.input_value("#minkw") == "50"
    assert page.text_content("#list-summary") == rapid
    assert page.url.endswith(f"?minkw=50#{position}")
    assert v.stored() == {}, "filters alone must not save anything on the device"


def test_settings_are_saved_only_after_opting_in_and_forget_deletes_them(visit):
    v = visit()
    page = v.open()
    open_filters(page)
    page.check('input[name="plug"][value="ccs"]')
    assert v.stored() == {}
    page.check("#remember")
    saved = json.loads(v.stored()["oevm.settings.v1"])
    assert saved == {"version": 1, "filters": "plug=ccs"}
    assert "saved on this device" in page.text_content("#settings-message")

    v.open()  # no filters in the address, so the saved settings apply
    open_filters(page)
    assert page.is_checked('input[name="plug"][value="ccs"]')
    assert page.is_checked("#remember")

    page.click("#forget")
    assert v.stored() == {}
    assert not page.is_checked("#remember")
    assert "deleted" in page.text_content("#settings-message")


def test_details_show_provenance_and_return_focus(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    first = page.locator("#list-items button").first
    first.click()
    expect(page.locator("#detail-heading")).to_be_focused()
    body = page.text_content("#detail-body")
    assert "Where this comes from" in body and "Fetched " in body and "Licence:" in body
    report = page.get_attribute("text=Report a mistake about this charger", "href")
    assert report.startswith(f"{REPOSITORY_URL}/issues/new?template=correction.yml")
    page.keyboard.press("Escape")
    assert page.is_hidden("#detail")
    assert page.evaluate("document.activeElement.classList.contains('item')")


def test_a_phone_opening_in_the_list_starts_the_map_when_first_shown(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    assert page.locator("#map canvas").count() == 0
    assert "#" not in page.url
    page.click("#show-map")
    expect(page.locator("#list-summary")).to_contain_text("map area")
    expect(page).to_have_url(MAP_SETTLED)
    zoom, latitude, longitude = (float(n) for n in page.url.split("#")[1].split("/")[:3])
    assert zoom > 3 and 49 < latitude < 61 and -9 < longitude < 2
    assert page.url.split("#")[0].endswith("/"), "the view is not in the address by default"


def test_skip_link_opens_the_list_on_a_phone(visit):
    page = visit().open()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.classList.contains('skip')")
    page.keyboard.press("Enter")
    assert page.is_visible("#list") and page.is_hidden("#map-view")
    assert page.evaluate("document.activeElement.id") == "list"
    assert page.get_attribute("#show-list", "aria-pressed") == "true"


NO_WEBGL = """
const getContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
  return /webgl/i.test(type) ? null : getContext.call(this, type, ...rest);
};
"""


def test_without_webgl_the_list_is_shown_instead(visit):
    v = visit(init_script=NO_WEBGL)
    page = v.open(map_ready=False)
    page.wait_for_selector("#notice:not([hidden])")
    assert "shown as a list" in page.text_content("#notice")
    assert page.is_visible("#list") and page.is_disabled("#show-map")
    assert page.locator("#list-items li").count() == LOCATIONS
    assert v.outside == []


MARKUP = '<img src="x" onerror="window.injected = 1">'


def test_text_from_feeds_is_never_treated_as_markup(visit, site):
    v = visit()
    page = v.page

    def layer(route):
        data = json.loads(route.fetch().text())
        data["features"][0]["properties"]["name"] = MARKUP
        route.fulfill(json=data)

    def detail(route):
        data = json.loads(route.fetch().text())
        data["location"]["name"] = MARKUP
        data["location"]["provenance"]["source_url"] = "javascript:window.injected=2"
        data["attribution"] = MARKUP
        route.fulfill(json=data)

    page.route("**/data/locations.geojson", layer)
    page.route("**/data/loc/**", detail)
    v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    item = page.locator("#list-items button", has_text=MARKUP)
    assert item.count() == 1
    item.click()
    expect(page.locator("#detail-heading")).to_be_focused()
    assert page.text_content("#detail-heading") == MARKUP
    assert page.locator("main img").count() == 0
    assert page.locator('a[href^="javascript:"]').count() == 0
    assert page.evaluate("window.injected") is None


def test_lighthouse_accessibility_score_on_a_phone(site, tmp_path):
    lighthouse = ROOT / "node_modules" / ".bin" / "lighthouse"
    chrome = os.environ.get("CHROME_PATH")
    if not lighthouse.exists() or not chrome or not shutil.which(chrome):
        _unavailable("Lighthouse needs 'npm ci' and CHROME_PATH")
    report = tmp_path / "lighthouse.json"
    subprocess.run(
        [
            str(lighthouse),
            site,
            "--only-categories=accessibility",
            "--form-factor=mobile",
            "--output=json",
            f"--output-path={report}",
            "--quiet",
            "--chrome-flags=--headless=new --no-sandbox " + " ".join(BROWSER_ARGS[:2]),
        ],
        check=True,
        timeout=180,
        env={**os.environ, "CHROME_PATH": chrome},
    )
    result = json.loads(report.read_text(encoding="utf-8"))
    failed = [
        audit["id"]
        for audit in result["audits"].values()
        if audit.get("scoreDisplayMode") == "binary" and audit.get("score") == 0
    ]
    assert result["categories"]["accessibility"]["score"] >= 0.9, failed
