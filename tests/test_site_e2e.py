"""The map page in a real browser (blueprint task 9).

These tests build the site from the recorded fixtures with the offline map style, serve it
on this computer and drive Chromium with Playwright. The browser is told to refuse every
other host, so nothing here reaches the internet.

They need 'npm ci' (for MapLibre and Lighthouse) and a Chromium or Chrome browser. Set
CHROME_PATH to the browser if Playwright cannot find its own. Without them the tests are
skipped, unless OEVM_REQUIRE_E2E=1 (as in CI), when they fail instead.
"""

import base64
import functools
import json
import os
import re
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

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
    "--no-proxy-server",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
]
# In the fixtures (recorded, and Monta's made-up ones), without the two hidden unless
# asked for (ADR 0023): Evolt Network's "Arthur House - Private Use Only" and PoGo
# Charge's taxi-only "Swales Central Avenue".
LOCATIONS = 124
PRIVATE = "Arthur House - Private Use Only"
TAXIS = "Swales Central Avenue"
OUT_OF_SERVICE = 11  # fixture locations with every charger reported out of service
SERVED: list[str] = []  # every path the test server was asked for
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
            SERVED.append(self.path)

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

    def __init__(
        self, browser, site: str, viewport: dict, init_script: str | None = None, **options
    ):
        self.site = site
        self.context = browser.new_context(viewport=viewport, locale="en-GB", **options)
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

    def start(viewport=PHONE, init_script=None, **options):
        visits.append(Visit(browser, site, viewport, init_script, **options))
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
    # Saved settings stay out of the address, so a reload never sends them to the host,
    # until the visitor changes a filter.
    assert urlsplit(page.url).query == ""
    page.select_option("#minkw", "22")
    page.wait_for_url("**?minkw=22&plug=ccs**")

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
    osm = page.get_attribute("text=View this place on OpenStreetMap", "href")
    assert osm.startswith("https://www.openstreetmap.org/?mlat=")
    page.keyboard.press("Escape")
    assert page.is_hidden("#detail")
    assert page.evaluate("document.activeElement.classList.contains('item')")


def test_details_colour_charge_point_statuses_with_words_and_the_time_read(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _open_details_containing(page, "● ")  # a location with a charge point available
    summary = page.text_content("#detail-body .status-summary")
    assert re.fullmatch(r"\d+ of \d+ charge points? available", summary)
    chip = page.locator("#detail-body .status-chips .status-available")
    expect(chip).to_have_count(1)
    assert re.fullmatch(r"● \d+ available", chip.text_content())
    assert chip.locator("[aria-hidden=true]").text_content() == "● "
    body = page.text_content("#detail-body")
    assert "Status from the operator's feed, read " in body
    # Each charge point's status has its group's colour too.
    colours = {
        page.evaluate("(e) => getComputedStyle(e).color", e.element_handle())
        for e in page.locator("#detail-body .charge-points .status").all()
    }
    available = page.evaluate("(e) => getComputedStyle(e).color", chip.element_handle())
    assert available in colours


def test_details_list_every_tariff_with_the_lowest_energy_price(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    buttons = page.locator("#list-items button")
    for n in range(buttons.count()):
        buttons.nth(n).click()
        expect(page.locator("#detail-heading")).to_be_focused()
        if "Lowest energy price listed here" in page.text_content("#detail-body"):
            break
        page.keyboard.press("Escape")
    else:
        raise AssertionError("no location compares its tariffs")
    tariffs = page.locator("ul.tariffs > li")
    assert tariffs.count() >= 2
    body = page.text_content("ul.tariffs")
    assert "Pay at the charger, for example by card" in body
    assert "With an account, app or card from a charging provider" in body


def _open_details_containing(page, text):
    buttons = page.locator("#list-items button")
    for n in range(buttons.count()):
        buttons.nth(n).click()
        expect(page.locator("#detail-heading")).to_be_focused()
        if text in page.text_content("#detail-body"):
            return
        page.keyboard.press("Escape")
    raise AssertionError(f"no location's details contain {text!r}")


def test_details_show_plans_from_providers_pages_and_the_visitors_own(visit):
    v = visit()
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _open_details_containing(page, "Other ways to pay here")
    plans = " ".join(page.locator("ul.plans").all_text_contents())
    assert "per kWh" in plans and "checked 9 Oct 2026" in plans
    headings = page.locator("#detail-body h4").all_text_contents()
    assert headings and all(
        t.startswith(("No subscription needed", "With a paid subscription")) for t in headings
    )
    assert "You have this plan" not in plans
    page.keyboard.press("Escape")
    open_filters(page)
    page.locator("#my-plans input[name=plan]").first.check()
    page.click("#remember")
    stored = json.loads(v.stored()["oevm.settings.v1"])
    assert stored["plans"] == [
        page.locator("#my-plans input[name=plan]").first.get_attribute("value")
    ]
    page.click("#forget")
    assert v.stored() == {}


def test_the_calculator_works_out_when_a_plan_pays_for_itself(visit):
    plans = {
        "schema_version": 1,
        "generated_at": "2026-10-09T04:17:00Z",
        "note": "test",
        "plans": [
            {
                "id": "test.fixed",
                "provider": "Test",
                "provider_kind": "roaming",
                "name": "Fixed plan",
                "pay_by": "Test app",
                "fee_text": "£5.00 a month",
                "price_text": "50p per kWh including VAT",
                "monthly_fee": 5,
                "ppk": 50,
                "discount_percent": None,
                "networks": ["GeniePoint"],
                "operator_ids": ["geniepoint"],
                "conditions": None,
                "needs_testing": None,
                "fee_note": None,
                "attribution": None,
                "source_url": "https://example.com/plan",
                "checked": "2026-10-09",
            },
            {
                "id": "test.discount",
                "provider": "Test",
                "provider_kind": "roaming",
                "name": "Discount plan",
                "pay_by": "Test app",
                "fee_text": "£4.00 a month",
                "price_text": "20% off the app price",
                "monthly_fee": 4,
                "ppk": None,
                "discount_percent": 20,
                "networks": ["GeniePoint"],
                "operator_ids": ["geniepoint"],
                "conditions": None,
                "needs_testing": None,
                "fee_note": None,
                "attribution": None,
                "source_url": "https://example.com/plan",
                "checked": "2026-10-09",
            },
        ],
    }
    v = visit()
    v.page.route(
        "**/data/plans.json",
        lambda route: route.fulfill(content_type="application/json", body=json.dumps(plans)),
    )
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _open_details_containing(page, "Is a subscription worth it here?")
    page.click(".calculator summary")
    assert page.input_value("#calc-fee") == "5"
    assert page.input_value("#calc-with") == "50"
    page.fill("#calc-now", "82.8")
    answer = page.locator("#calc-answer")
    expect(answer).to_contain_text("pays for itself once you charge 16 kWh a month")
    page.fill("#calc-kwh", "100")
    expect(answer).to_contain_text("save about £27.80 a month after the fee")
    page.select_option("#calc-plan", "test.discount")
    expect(page.locator("#calc-note")).to_contain_text("enter it from the provider's app")
    page.fill("#calc-base", "60")
    assert page.input_value("#calc-with") == "48"
    expect(answer).to_contain_text("pays for itself once you charge 12 kWh a month")
    page.fill("#calc-with", "45")
    expect(answer).to_contain_text("pays for itself once you charge 11 kWh a month")
    assert page.input_value("#calc-with") == "45", "a price the visitor types is kept"
    assert (
        "Lowest published energy price here with any listed plan: 50p per kWh including "
        "VAT, with Fixed plan from Test" in page.text_content("#detail-body")
    )


def test_ticking_a_plan_redraws_open_details_and_a_failed_list_keeps_saved_plans(visit):
    v = visit(viewport=WIDE)
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _open_details_containing(page, "Other ways to pay here")
    open_filters(page)
    first = page.locator("#my-plans input[name=plan]").first
    plan_name = first.evaluate("box => box.parentElement.textContent")
    shown = " ".join(page.locator("ul.plans").all_text_contents())
    covering = [box for box in page.locator("#my-plans input[name=plan]").all()]
    for box in covering:
        label = box.evaluate("box => box.parentElement.textContent").split(":")[0].strip()
        if label and label in shown:
            box.check()
            break
    else:
        raise AssertionError(f"no ticked plan covers this location ({plan_name})")
    expect(page.locator("#detail-body .mine")).to_have_count(1)
    page.click("#remember")
    saved = json.loads(v.stored()["oevm.settings.v1"])["plans"]
    v.page.route("**/data/plans.json", lambda route: route.fulfill(status=503, body=""))
    page.reload()
    expect(page.locator("#my-plans")).to_contain_text("could not be loaded")
    open_filters(page)
    page.check("#free")
    assert json.loads(v.stored()["oevm.settings.v1"])["plans"] == saved


def test_details_say_when_coordinates_were_swapped_back(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    page.locator("#list-items button", has_text="UBI 98 Southwell Road").click()
    note = page.locator("#detail-body .corrected")
    expect(note).to_contain_text("latitude and longitude the wrong way round")
    expect(note).to_contain_text("latitude -0.09703 and longitude 51.467819")


def test_details_say_when_tariffs_come_from_a_related_networks_feed(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    page.locator("#list-items button", has_text="Lancing Manor Leisure Centre").click()
    body = page.locator("#detail-body")
    expect(body.locator(".related")).to_contain_text("only Evolt Network's tariff data holds")
    expect(body.locator(".charge-points")).to_contain_text("56p per kWh including VAT")
    options = body.locator(".tariffs li", has_text="Published in Evolt Network's tariff data.")
    expect(options).to_have_count(2)
    expect(body).to_contain_text("Contains data from Evolt Network")
    link = body.get_by_role("link", name="Evolt Network's tariff feed")
    href = "https://info.smartcharging.uk/public_feed/locations/3666/tariffs"
    expect(link).to_have_attribute("href", href)


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
    expect(page.locator("#notice")).to_contain_text("could not start in this browser")
    assert page.is_visible("#list") and page.is_disabled("#show-map")
    assert page.locator("#list-items li").count() == LOCATIONS
    assert v.outside == []


def test_if_the_basemap_cannot_load_the_list_takes_over(visit):
    v = visit()
    v.page.route("**/assets/offline-style.json", lambda route: route.fulfill(status=404))
    page = v.open(map_ready=False)
    expect(page.locator("#notice")).to_contain_text("background map could not be loaded")
    assert page.is_visible("#list") and page.is_disabled("#show-map")
    assert page.locator("#list-items li").count() == LOCATIONS
    assert v.outside == []


def test_widening_a_screen_that_opened_in_the_list_starts_the_map(visit):
    page = visit({"width": 768, "height": 1024}).open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    assert page.locator("#map canvas").count() == 0
    page.set_viewport_size(WIDE)
    expect(page.locator("#map canvas")).to_have_count(1)
    expect(page.locator("#list-summary")).to_contain_text("map area")


def test_a_narrow_phone_header_wraps_without_pushing_the_map_off_screen(visit):
    page = visit({"width": 360, "height": 740}).open()
    header, map_view = (page.locator(selector).bounding_box() for selector in (".top", "#map-view"))
    assert header["height"] > 60, "the header wraps at this width"
    assert map_view["y"] + map_view["height"] < 740


def test_the_header_shrinks_back_after_it_has_wrapped(visit):
    page = visit({"width": 360, "height": 740}).open()
    wrapped = page.locator(".top").bounding_box()["height"]
    assert wrapped > 60, "the header wraps at this width"
    # Widen to a desktop width, where the header fits one row whatever fonts the system has.
    page.set_viewport_size(WIDE)
    page.wait_for_timeout(300)
    one_row = page.locator(".top").bounding_box()["height"]
    assert one_row < 70 and one_row < wrapped
    # The page measures the header in a ResizeObserver callback, which a busy page can run
    # after the wait above, so give the measurement up to 5 seconds more to catch up.
    # (wait_for_function would need eval, which the page's security policy blocks.)
    for _ in range(50):
        measured = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--header-measured')"
        )
        if measured.strip() == f"{round(one_row)}px":
            break
        page.wait_for_timeout(100)
    assert measured.strip() == f"{round(one_row)}px"
    map_view = page.locator("#map-view").bounding_box()
    assert abs(map_view["y"] + map_view["height"] - WIDE["height"]) < 2


def test_without_the_map_a_wide_screen_keeps_details_in_view_beside_the_list(visit):
    v = visit({"width": 1400, "height": 800})
    v.page.route("**/assets/offline-style.json", lambda route: route.fulfill(status=404))
    page = v.open(map_ready=False)
    expect(page.locator("#notice")).to_contain_text("background map could not be loaded")
    items = page.locator("#list-items button")
    items.nth(8).click()
    expect(page.locator("#detail-heading")).to_be_focused()
    first = page.text_content("#detail-heading")
    page.mouse.wheel(0, 900)
    page.wait_for_timeout(300)
    panel = page.locator("#detail").bounding_box()
    assert 0 <= panel["y"] < 800, "the panel stays on screen"
    items.nth(10).click()
    expect(page.locator("#detail-heading")).not_to_have_text(first)
    # The footer (disclaimer, links, privacy line) is never hidden behind the panel.
    page.keyboard.press("End")
    page.mouse.wheel(0, 5000)
    page.wait_for_timeout(300)
    panel = page.locator("#detail").bounding_box()
    for link in page.locator(".bottom a, .bottom p").all():
        box = link.bounding_box()
        if box and box["height"]:
            assert box["x"] + box["width"] <= panel["x"] + 1, link.text_content()[:40]


def test_the_skip_link_closes_open_details_on_a_wide_screen(visit):
    page = visit(WIDE).open()
    page.locator("#list-items button").first.click()
    expect(page.locator("#detail-heading")).to_be_focused()
    page.focus(".skip")
    page.keyboard.press("Enter")
    assert page.is_hidden("#detail")
    assert page.evaluate("document.activeElement.id") == "list"
    assert not page.evaluate("document.getElementById('list').inert")


def test_on_a_wide_screen_details_cover_only_the_list(visit):
    v = visit(WIDE)
    page = v.open()
    page.locator("#list-items button").first.click()
    expect(page.locator("#detail-heading")).to_be_focused()
    page.click("#toggle-filters", timeout=2000)  # the header stays usable
    assert page.is_visible("#filters")
    assert page.evaluate("document.getElementById('list').inert")
    page.focus("#close-detail")
    page.keyboard.press("Shift+Tab")
    assert not page.evaluate("document.getElementById('list').contains(document.activeElement)")


IN_DETAILS_OR_OUT_OF_PAGE = (
    "document.activeElement === document.body"
    " || document.getElementById('detail').contains(document.activeElement)"
)


def test_on_a_phone_focus_stays_in_the_details_until_they_close(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    page.locator("#list-items button").first.click()
    expect(page.locator("#detail-heading")).to_be_focused()
    for key in ["Tab"] * 12 + ["Shift+Tab"] * 12:
        page.keyboard.press(key)
        # Past the last link, focus may leave the page for the browser's own controls.
        assert page.evaluate(IN_DETAILS_OR_OUT_OF_PAGE), key
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.classList.contains('item')")


def test_a_slow_answer_never_replaces_newer_details(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    first, second = (page.locator("#list-items button").nth(i) for i in (0, 1))
    held = []
    page.route(f"**/{first.get_attribute('data-key')}.json", lambda route: held.append(route))
    first.click()
    page.keyboard.press("Escape")
    second.click()
    expect(page.locator("#detail-heading")).to_be_focused()
    expected = page.text_content("#detail-heading")
    held[0].continue_()
    page.wait_for_timeout(500)
    assert page.text_content("#detail-heading") == expected


def test_filters_used_while_data_loads_keep_the_ones_in_the_address(visit):
    v = visit()
    held = []
    v.page.route("**/data/locations.geojson", lambda route: held.append(route))
    page = v.open("?minkw=50&op=geniepoint&view=list", map_ready=False)
    open_filters(page)
    assert page.input_value("#minkw") == "50"
    page.check('input[name="plug"][value="ccs"]')
    held[0].continue_()
    expect(page.locator("#list-items li").first).to_be_visible()
    assert "minkw=50&plug=ccs&op=geniepoint" in page.url
    assert page.is_checked('input[name="op"][value="geniepoint"]')


def test_a_network_missing_from_the_data_is_dropped_from_the_filters(visit):
    page = visit().open("?op=not_in_the_data&view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    assert "removed from the filters" in page.text_content("#notice")
    assert "op=" not in page.url


def test_forget_in_another_tab_is_not_undone(visit):
    v = visit()
    page = v.open()
    open_filters(page)
    page.check("#remember")
    other = v.context.new_page()
    other.goto(v.site)
    open_filters(other)
    other.click("#forget")
    assert v.stored() == {}
    expect(page.locator("#remember")).not_to_be_checked()
    page.select_option("#minkw", "22")
    assert v.stored() == {}


def test_power_and_price_filters_apply_to_the_same_connector(visit):
    # In the fixtures this site's 50 kW connectors cost 82.8p and only a 7 kW one costs less.
    page = visit().open("?minkw=50&maxp=60&unknown=0&view=list", map_ready=False)
    expect(page.locator("#list-summary")).not_to_contain_text("Loading")
    assert page.locator("#list-items", has_text="Premier Inn Alnwick").count() == 0
    page.goto(page.url.replace("maxp=60", "maxp=85"))
    expect(page.locator("#list-items")).to_contain_text("Premier Inn Alnwick")
    assert "Energy 57.6p to 82.8p per kWh including VAT" in page.text_content("#list-items")


OUTSIDE_SOURCE = {
    "type": "vector",
    "tiles": ["https://outside.invalid/tiles/{z}/{x}/{y}.pbf"],
    "maxzoom": 14,
}


def test_map_requests_to_other_hosts_are_stopped_in_the_page(visit):
    v = visit()

    def style(route):
        data = json.loads(route.fetch().text())
        data["sources"]["outside"] = OUTSIDE_SOURCE
        data["layers"].append(
            {"id": "outside", "type": "fill", "source": "outside", "source-layer": "any"}
        )
        route.fulfill(json=data)

    v.page.route("**/assets/offline-style.json", style)
    SERVED.clear()
    page = v.open()
    expect(page.locator("#map canvas")).to_have_count(1)
    page.wait_for_timeout(1000)
    assert any(path.startswith("/blocked-outside-request") for path in SERVED)
    assert not any("outside.invalid" in url for url in v.outside)
    assert page.is_hidden("#notice"), "a missing tile leaves the map in place"


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
        option = {"kind": MARKUP, "state": "priced", "text": MARKUP, "connectors": 1}
        data["tariff_options"] = [
            {**option, "tariff_id": f"x:GB:XXX:{n}", "name": MARKUP, "published_by": MARKUP}
            for n in (1, 2)
        ]
        data["tariff_sources"] = [
            {
                "name": MARKUP,
                "note": MARKUP,
                "attribution": MARKUP,
                "source_url": "javascript:window.injected=3",
                "licence": MARKUP,
                "licence_url": "javascript:window.injected=4",
                "fetched_at": data["fetched_at"],
            }
        ]
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
    assert page.locator(".related", has_text=MARKUP).count() == 1
    assert page.locator(".tariffs li", has_text=f"Published in {MARKUP}'s").count() == 2
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
            # The host rule is quoted so its spaces survive Lighthouse's flag parsing.
            "--chrome-flags=--headless=new --no-sandbox "
            + " ".join(arg for arg in BROWSER_ARGS if not arg.startswith("--host-"))
            + ' --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"',
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


def test_quick_filters_match_the_form_and_the_address(visit):
    v = visit()
    page = v.open()
    page.click("#quick-rapid")
    page.wait_for_url("**?minkw=50**")
    assert page.get_attribute("#quick-rapid", "aria-pressed") == "true"
    assert page.text_content("#toggle-filters") == "Filters (1)"
    assert page.input_value("#minkw") == "50"
    page.click("#quick-working")
    page.wait_for_url("**?minkw=50&ok=1**")
    assert page.text_content("#toggle-filters") == "Filters (2)"
    open_filters(page)
    assert page.is_checked("#working")
    page.click("#reset")
    assert page.get_attribute("#quick-rapid", "aria-pressed") == "false"
    assert page.text_content("#toggle-filters") == "Filters"
    page.click("#done")
    assert page.is_hidden("#filters")
    assert page.evaluate("document.activeElement.id") == "toggle-filters"
    assert v.stored() == {}


def test_chargers_reported_out_of_service_can_be_hidden(visit):
    v = visit()

    def layer(route):
        data = json.loads(route.fetch().text())
        for connector in data["features"][0]["properties"]["cons"]:
            connector["out"] = True
        route.fulfill(json=data)

    v.page.route("**/data/locations.geojson", layer)
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    expect(page.locator("#list-items")).to_contain_text("Reported out of service")
    page.goto(page.url.split("?")[0] + "?view=list&ok=1")
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS - 1 - OUT_OF_SERVICE)
    assert "Reported out of service" not in page.text_content("#list-items")


def test_the_red_count_in_the_details_switches_hide_out_of_service(visit):
    v = visit()
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _open_details_containing(page, "reported out of service")
    button = page.locator('#detail-body button[data-filter="working"]')
    expect(button).to_have_attribute("aria-pressed", "false")
    assert button.get_attribute("aria-describedby") == "status-filter-hint"
    expect(button).to_have_accessible_name(
        re.compile(r"^Hide out of service: \d+ reported out of service$")
    )
    assert re.fullmatch(r"✕ \d+ reported out of service", button.text_content())
    button.click()
    page.wait_for_url("**ok=1**")
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#quick-working")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS - OUT_OF_SERVICE)
    # Details opened later show the filter's state, and the count switches it off again.
    page.keyboard.press("Escape")
    _open_details_containing(page, "reported out of service")
    expect(button).to_have_attribute("aria-pressed", "true")
    button.click()
    page.wait_for_url(re.compile(r"^(?!.*ok=1)"))
    expect(page.locator("#quick-working")).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    # Counts for other groups stay plain text.
    assert page.locator("#detail-body .status-chips button").count() == 1


def test_on_a_wide_screen_the_red_count_follows_the_header_button(visit):
    v = visit({"width": 1400, "height": 800})
    v.page.route("**/assets/offline-style.json", lambda route: route.fulfill(status=404))
    page = v.open(map_ready=False)
    expect(page.locator("#notice")).to_contain_text("background map could not be loaded")
    _open_details_containing(page, "reported out of service")
    button = page.locator('#detail-body button[data-filter="working"]')
    expect(button).to_have_attribute("aria-pressed", "false")
    page.click("#quick-working")
    expect(button).to_have_attribute("aria-pressed", "true")
    button.click()
    expect(page.locator("#quick-working")).to_have_attribute("aria-pressed", "false")
    expect(button).to_be_focused()  # the details are not redrawn, so focus stays put


def test_dark_mode_follows_the_device_and_the_button_switches_the_map(visit):
    v = visit(WIDE, color_scheme="dark")
    SERVED.clear()
    page = v.open()
    assert page.get_attribute("html", "data-theme") == "dark"
    assert page.get_attribute("#toggle-theme", "aria-pressed") == "true"
    assert any(path.endswith("offline-style-dark.json") for path in SERVED)
    background = page.evaluate("getComputedStyle(document.documentElement).backgroundColor")
    page.click("#toggle-theme")
    assert page.get_attribute("html", "data-theme") == "light"
    assert page.evaluate("getComputedStyle(document.documentElement).backgroundColor") != background
    expect(page.locator("#list-summary")).to_contain_text("map area")
    page.wait_for_timeout(500)
    assert any(path.endswith("offline-style.json") for path in SERVED)
    # The chargers are drawn again on the new style, so a cluster still opens.
    assert page.locator("#list-items li").count() == LOCATIONS
    assert v.stored() == {}, "picking light or dark saves nothing until the visitor opts in"
    open_filters(page)
    page.check("#remember")
    saved = json.loads(v.stored()["oevm.settings.v1"])
    assert saved == {"version": 1, "filters": "", "theme": "light"}
    v.open()
    assert page.get_attribute("html", "data-theme") == "light", "the saved choice wins"
    assert v.errors == [] and v.outside == []


def test_find_my_location_moves_the_map_there(visit):
    v = visit(
        WIDE,
        geolocation={"latitude": 51.507, "longitude": -0.128},
        permissions=["geolocation"],
    )
    page = v.open()
    page.click("button.maplibregl-ctrl-geolocate")
    expect(page).to_have_url(
        re.compile(r"#1[0-2](\.[0-9]+)?/51\.5[0-9]*/-0\.1[0-9]*$"), timeout=15000
    )
    assert v.stored() == {} and v.outside == [] and v.errors == []


REFUSE_LOCATION = """
navigator.geolocation.getCurrentPosition = (success, failure) =>
  failure({ code: 1, PERMISSION_DENIED: 1, message: "User denied Geolocation" });
"""


def test_a_refused_location_is_explained(visit):
    v = visit(WIDE, init_script=REFUSE_LOCATION)
    page = v.open()
    page.click("button.maplibregl-ctrl-geolocate")
    expect(page.locator("#notice")).to_contain_text("did not allow the map to use your location")


# Grouping, private chargers and each charge point (ADR 0023)

# The colour of a numbered circle on the map (main.js), counted in a screenshot of the map
# by drawing it on a canvas in the page, since the map's own canvas cannot be read back.
COUNT_CLUSTER_PIXELS = """async (src) => {
  const img = new Image();
  img.src = src;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.width;
  canvas.height = img.height;
  const context = canvas.getContext("2d");
  context.drawImage(img, 0, 0);
  const { width, height } = canvas;
  const data = context.getImageData(0, 0, width, height).data;
  const near = (value, target) => Math.abs(value - target) < 6;
  const is = (x, y) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return false;
    const i = (y * width + x) * 4;
    return near(data[i], 0x24) && near(data[i + 1], 0x32) && near(data[i + 2], 0x3f);
  };
  // Only pixels well inside a filled shape count, so a thin outline in the same colour,
  // such as a price label's edge, does not.
  let count = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (is(x, y) && is(x - 3, y) && is(x + 3, y) && is(x, y - 3) && is(x, y + 3)) count++;
    }
  }
  return count;
}"""


def cluster_pixels(page) -> int:
    shot = base64.b64encode(page.locator("#map").screenshot()).decode()
    return page.evaluate(COUNT_CLUSTER_PIXELS, f"data:image/png;base64,{shot}")


def wait_for_clusters(page, present: bool):
    for _ in range(40):
        if (cluster_pixels(page) > 50) == present:
            return
        page.wait_for_timeout(250)
    raise AssertionError(f"numbered circles {'never appeared' if present else 'stayed'}")


def test_grouping_can_be_turned_off_and_on_from_the_map_or_the_filters(visit):
    v = visit()
    page = v.open()
    button = page.locator("#toggle-group")
    expect(button).to_have_attribute("aria-pressed", "true")
    wait_for_clusters(page, True)
    button.click()
    page.wait_for_url("**?group=0**")
    expect(button).to_have_attribute("aria-pressed", "false")
    wait_for_clusters(page, False)
    open_filters(page)
    assert not page.is_checked("#group")
    assert page.text_content("#toggle-filters") == "Filters", "grouping is not a filter"
    assert page.locator("#list-items li").count() == LOCATIONS, "no charger is hidden"
    page.check("#group")
    expect(button).to_have_attribute("aria-pressed", "true")
    assert "group=" not in page.url
    wait_for_clusters(page, True)
    # Clearing the filters leaves grouping as the visitor set it.
    page.uncheck("#group")
    page.click("#reset")
    assert not page.is_checked("#group") and "group=0" in page.url
    assert v.errors == [] and v.stored() == {}


def test_a_link_with_grouping_off_opens_without_numbered_circles(visit):
    page = visit().open("?group=0")
    expect(page.locator("#toggle-group")).to_have_attribute("aria-pressed", "false")
    wait_for_clusters(page, False)


def test_private_chargers_are_hidden_until_the_visitor_asks(visit):
    v = visit()
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    assert PRIVATE not in page.text_content("#list-items")
    assert TAXIS not in page.text_content("#list-items")
    open_filters(page)
    assert not page.is_checked("#private")
    page.check("#private")
    page.wait_for_url("**priv=1**")
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS + 2)
    assert page.text_content("#toggle-filters") == "Filters (1)"
    expect(page.locator("#list-items li", has_text=TAXIS)).to_contain_text(
        "Taxis only: the operator marks every charge point here for taxis only"
    )
    item = page.locator("#list-items li", has_text=PRIVATE)
    expect(item).to_contain_text(
        'Marked private or restricted: the operator\'s name for it includes "Private Use Only"'
    )
    page.click("#done")
    item.locator("button").click()
    expect(page.locator("#detail-heading")).to_have_text(PRIVATE)
    expect(page.locator("#detail-body .private-note")).to_contain_text(
        'Chargers like this are hidden unless "Show chargers marked private or restricted"'
    )
    page.keyboard.press("Escape")
    open_filters(page)
    page.click("#reset")
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    links = page.locator("#private-hint a")
    assert [links.nth(i).get_attribute("href") for i in range(2)] == [
        "transparency/#private",
        "status/#private",
    ]
    assert v.errors == []


def test_details_list_each_charge_point_with_its_label_id_and_status(visit):
    page = visit().open("?view=list&priv=1", map_ready=False)
    page.locator("#list-items button", has_text=PRIVATE).click()
    expect(page.locator("#detail-heading")).to_be_focused()
    points = page.locator("#detail-body .charge-points > li")
    expect(points).to_have_count(6)
    assert page.text_content("#detail-body h3 >> nth=1") == "Charge points (6)"
    first = points.first
    assert first.locator(".charge-point-name").text_content() == "SEC31617"
    expect(first).to_contain_text("ID GB*SSM*ESEC31617*1")
    assert re.fullmatch(r"● Available, reported .+", first.locator(".status").text_content())
    expect(first.locator(".connectors li")).to_have_count(1)
    expect(first.locator(".connectors")).to_contain_text("Type 2 · 7 kW")
    # The reference numbers come last, in small print.
    last = page.locator("#detail-body > *").last
    assert last.get_attribute("class") == "references"
    refs = [li.text_content() for li in last.locator("li").all()]
    assert refs[0] == (
        "Site: 12343565 in Evolt Network's feed (on this map: evolt:GB:SSM:12343565)."
    )
    assert refs[1] == "SEC31617: EVSE ID GB*SSM*ESEC31617*1, uid SEC31617_1."
    assert len(refs) == 7


def test_parking_restrictions_are_shown_with_each_charge_point(visit):
    page = visit().open("?view=list", map_ready=False)
    page.locator("#list-items button", has_text="Premier Inn Alnwick").click()
    expect(page.locator("#detail-heading")).to_be_focused()
    expect(page.locator("#detail-body .charge-points .parking").first).to_have_text(
        "Parking: only while plugged in and charging; customers only."
    )


def test_taxi_only_charge_points_are_labelled(visit):
    page = visit().open("?view=list&priv=1", map_ready=False)
    page.locator("#list-items button", has_text=TAXIS).click()
    expect(page.locator("#detail-heading")).to_be_focused()
    expect(page.locator("#detail-body .private-note")).to_contain_text("Taxis only")
    parking = page.locator("#detail-body .charge-points .parking")
    expect(parking).to_have_count(3)
    expect(parking.first).to_have_text("Parking: taxis only.")


# Price labels (ADR 0026)


def _item(page, name):
    return page.locator("#list-items li", has_text=name)


def test_the_list_shows_the_cheapest_price_for_the_connectors_the_filters_allow(visit):
    v = visit()
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    # GeniePoint's app price is lower than paying at the charger, which the summary shows.
    dumbarton = _item(page, "Premier Inn Dumbarton")
    expect(dumbarton).to_contain_text("Cheapest here: 82.8p")
    expect(dumbarton).to_contain_text("Energy 92.4p per kWh including VAT")
    expect(_item(page, "Premier Inn Alnwick")).to_contain_text("Cheapest here: 57.6p")
    # char.gy's feed gives 32.5p with no VAT; the owner decided to add 20% (vat_not_stated).
    seaford = _item(page, "141 - 143 Seaford Road")
    expect(seaford).to_contain_text("Cheapest here: from 39p")
    expect(seaford).not_to_contain_text("excl. VAT")
    expect(_item(page, "Atlantic Quay")).to_contain_text("Cheapest here: Free")
    expect(_item(page, "Glengarry")).not_to_contain_text("Cheapest here")
    # With rapid chargers only, the 7 kW connector's price no longer counts.
    page.click("#quick-rapid")
    expect(_item(page, "Premier Inn Alnwick")).to_contain_text("Cheapest here: 82.8p")
    assert v.errors == []


def test_details_say_where_the_map_label_comes_from(visit):
    page = visit().open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _item(page, "Premier Inn Dumbarton").locator("button").click()
    line = page.locator("#detail-body .map-label")
    expect(line).to_contain_text("Cheapest here: 82.8p, the lowest price per kWh listed here")
    expect(line).to_contain_text("with an account, app or card from a charging provider")
    expect(line).to_contain_text("are not included")
    page.keyboard.press("Escape")
    _item(page, "Atlantic Quay").locator("button").click()
    expect(page.locator("#detail-body .map-label")).to_contain_text(
        "Cheapest here: Free, as at least one connector here has a tariff the operator confirms "
        "is free"
    )


def test_the_details_line_follows_the_filters_while_the_details_are_open(visit):
    v = visit(WIDE)
    page = v.open("?view=list", map_ready=False)
    expect(page.locator("#list-items li")).to_have_count(LOCATIONS)
    _item(page, "Premier Inn Alnwick").locator("button").click()
    line = page.locator("#detail-body .map-label")
    expect(line).to_contain_text("Cheapest here: 57.6p, the lowest price per kWh listed here")
    expect(line).not_to_contain_text("match your filters")
    # On a wide screen the quick filters stay usable beside the panel.
    page.click("#quick-rapid")
    expect(line).to_contain_text(
        "Cheapest here: 82.8p, the lowest price per kWh listed here for the connectors that "
        "match your filters"
    )
    page.click("#quick-rapid")
    expect(line).to_contain_text("Cheapest here: 57.6p")
    assert v.errors == []


# The colour of a price label from a ticked plan (PILLS in main.js), counted the same way.
COUNT_AMBER_PIXELS = (
    COUNT_CLUSTER_PIXELS.replace("0x24", "0xff").replace("0x32", "0xe0").replace("0x3f", "0x8a")
)
CHEAP_PLAN = {
    "id": "test.cheap",
    "provider": "Test",
    "provider_kind": "roaming",
    "name": "Cheap plan",
    "pay_by": "Test app",
    "fee_text": "£4.99 a month",
    "price_text": "39p per kWh including VAT",
    "monthly_fee": 4.99,
    "ppk": 39,
    "label": "39p",
    "discount_percent": None,
    "networks": ["GeniePoint"],
    "operator_ids": ["geniepoint"],
    "conditions": None,
    "needs_testing": None,
    "fee_note": None,
    "attribution": None,
    "source_url": "https://example.com/plan",
    "checked": "2026-10-09",
}


def amber_pixels(page) -> int:
    shot = base64.b64encode(page.locator("#map").screenshot()).decode()
    return page.evaluate(COUNT_AMBER_PIXELS, f"data:image/png;base64,{shot}")


def wait_for_amber(page, present: bool):
    for _ in range(40):
        if (amber_pixels(page) > 30) == present:
            return
        page.wait_for_timeout(250)
    raise AssertionError(f"the plan's price label {'never appeared' if present else 'stayed'}")


def test_a_ticked_plan_with_a_lower_price_labels_the_map_and_the_list(visit):
    v = visit(WIDE)

    def plans(route):
        data = json.loads(route.fetch().text())
        data["plans"].append(CHEAP_PLAN)
        route.fulfill(content_type="application/json", body=json.dumps(data))

    v.page.route("**/data/plans.json", plans)
    # Premier Inn Dumbarton, a GeniePoint site, in the middle of the map.
    page = v.open("#15/55.957027/-4.560159")
    page.click("#legend summary")  # the key, open on wide screens, shows the colour too
    item = _item(page, "Premier Inn Dumbarton")
    expect(item).to_contain_text("Cheapest here: 82.8p")
    wait_for_amber(page, False)
    open_filters(page)
    page.check("#my-plans input[value='test.cheap']")
    page.click("#done")
    expect(item).to_contain_text("Cheapest here: 39p with your plan")
    wait_for_amber(page, True)
    item.locator("button").click()
    expect(page.locator("#detail-body .map-label")).to_contain_text(
        "Cheapest here: 39p with your plan Cheap plan from Test (£4.99 a month)"
    )
    page.keyboard.press("Escape")
    # A point not grouped into a numbered circle keeps its label at any zoom.
    page.evaluate("window.location.hash = '#9/55.957027/-4.560159'")
    wait_for_amber(page, True)
    assert v.errors == [] and v.outside == []
