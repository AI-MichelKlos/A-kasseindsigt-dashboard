#!/usr/bin/env python3
"""Check graph permalinks, filter restoration and static social previews.

Run from any directory:
    python scripts/test_sharing.py
    python scripts/test_sharing.py --static-only
    python scripts/test_sharing.py --base-url https://ai-michelklos.github.io/A-kasseindsigt-dashboard/

Browser checks require the Python playwright package and Chromium. The test never
posts to LinkedIn, changes production data or contacts a signed-in account.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import struct
import threading
import unittest
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_BASE = "https://ai-michelklos.github.io/A-kasseindsigt-dashboard/"
STORAGE_KEY = "dak-a-kasseindsigt-personal-view-v5"


def encode_state(state):
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_state(url):
    value = parse_qs(urlsplit(url).query)["pv"][0]
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def fetch_bytes(url):
    request = Request(url, headers={"User-Agent": "A-kasseindsigt-sharing-check/1.0"})
    with urlopen(request, timeout=40) as response:
        if response.status != 200:
            raise AssertionError(f"HTTP {response.status}: {url}")
        return response.read(), response.headers


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *args):
        pass


@contextmanager
def test_server(base_url=None):
    if base_url:
        yield base_url.rstrip("/") + "/"
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = []
        self.anchors = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "meta":
            self.meta[attrs.get("property") or attrs.get("name")] = attrs.get("content", "")
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "a":
            self.anchors.append(attrs)


def load_manifest(base_url):
    body, _headers = fetch_bytes(urljoin(base_url, "config/share-charts.json"))
    manifest = json.loads(body)
    charts = manifest.get("charts", []) if isinstance(manifest, dict) else manifest
    assert len(charts) == 23, f"Expected 23 chart definitions, got {len(charts)}"
    assert len({chart["id"] for chart in charts}) == len(charts), "Duplicate chart id"
    assert len({chart["slug"] for chart in charts}) == len(charts), "Duplicate share slug"
    return charts


def check_static_previews(base_url, charts):
    for chart in charts:
        url = urljoin(base_url, f"share/{chart['slug']}/")
        body, headers = fetch_bytes(url)
        assert "text/html" in headers.get("Content-Type", ""), url
        parser = MetadataParser()
        parser.feed(body.decode("utf-8"))
        tags = parser.meta
        for key in ("og:title", "og:description", "og:type", "og:image", "og:image:alt"):
            assert tags.get(key), f"Missing {key}: {url}"
        assert chart["title"] in tags["og:title"], f"Wrong chart title: {url}"
        assert tags["og:image:width"] == "1200" and tags["og:image:height"] == "630", url
        # A fixed canonical URL must not replace the state-bearing incoming URL.
        assert not tags.get("og:url"), f"Static og:url could discard filter parameters: {url}"
        assert not any(link.get("rel") == "canonical" for link in parser.links), url
        fallback = next((link for link in parser.anchors if chart["id"] in link.get("href", "")), None)
        assert fallback, f"No usable no-JavaScript chart link: {url}"
        assert "chart=" in fallback["href"] and "#graf-" in fallback["href"], url
        image_url = tags["og:image"]
        assert image_url.startswith(PRODUCTION_BASE), f"Unexpected image origin: {image_url}"
        # Read generated assets locally while exercising their true URLs on Pages.
        local_image = urljoin(base_url, image_url.removeprefix(PRODUCTION_BASE))
        image, image_headers = fetch_bytes(local_image)
        assert "image/png" in image_headers.get("Content-Type", ""), image_url
        assert image[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG: {image_url}"
        assert struct.unpack(">II", image[16:24]) == (1200, 630), image_url
        assert len(image) < 5 * 1024 * 1024, f"Preview exceeds 5 MB: {image_url}"
    print(f"OK: {len(charts)} static share pages, metadata and public PNG previews", flush=True)


class SharingTests(unittest.TestCase):
    base_url = ""
    charts = []
    screenshot_dir = None

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        bundled = Path(cls.playwright.chromium.executable_path)
        executable = None if bundled.exists() else shutil.which("chromium")
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True, executable_path=executable)
        except Exception:
            cls.playwright.stop()
            raise
        payload, _headers = fetch_bytes(urljoin(cls.base_url, "data/dashboard-data.json"))
        cls.data = json.loads(payload)
        cls.total = cls.data["meta"]["totalFundCode"]
        cls.fund = next((code for code, value in cls.data["funds"].items() if "A&Til" in value["name"]), None)
        cls.fund = cls.fund or next(code for code in cls.data["funds"] if code != cls.total)
        cls.comparison = next(code for code in cls.data["funds"] if code not in (cls.total, cls.fund))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.contexts = []
        self.errors = []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.assertEqual([], self.errors, "Uncaught browser errors")

    def page(self, *, mobile=False, storage=None, deny_clipboard=False):
        context = self.browser.new_context(
            viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 1000},
            locale="da-DK",
            reduced_motion="reduce",
            is_mobile=mobile,
            has_touch=mobile,
        )
        self.contexts.append(context)
        context.route("**/gc.zgo.at/**", lambda route: route.abort())
        context.route("**/*.goatcounter.com/**", lambda route: route.abort())
        if storage is not None:
            value = json.dumps(json.dumps(storage, ensure_ascii=False))
            context.add_init_script(f"localStorage.setItem({json.dumps(STORAGE_KEY)}, {value});")
        if deny_clipboard:
            context.add_init_script("Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText:()=>Promise.reject(new Error('Clipboard blocked for test'))}});")
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        return page

    def open(self, page, url=None):
        url = url or self.base_url
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if "/share/" in urlsplit(url).path:
            page.wait_for_url(lambda value: "/share/" not in urlsplit(value).path, timeout=30000)
        page.wait_for_function("Boolean(window.DAKSharing && window.DAKPersonalView)", timeout=30000)
        page.evaluate("async () => { await window.DAKSharing.ready; await window.DAKPersonalView.ready; }")
        page.wait_for_function("!window.DAKPersonalView.isBusy")
        return page

    def state(self, **values):
        result = {"v": 5, "fund": self.fund, "region": "all", "period": "24", "comparisonFund": self.comparison,
                  "comparisonRegion": "all", "hidden": [], "rmHorizon": "three"}
        result.update(values)
        return result

    def direct(self, chart_id, state):
        query = urlencode({"pv": encode_state(state), "chart": chart_id})
        return self.base_url + "?" + query + "#graf-" + chart_id

    def assert_state(self, page, expected):
        actual = page.evaluate("window.DAKPersonalView.getState()")
        for field in ("fund", "region", "period", "comparisonFund", "comparisonRegion", "rmHorizon"):
            self.assertEqual(expected[field], actual[field], field)
        return actual

    def assert_chart_open(self, page, chart_id):
        card = page.locator("#graf-" + chart_id)
        self.assertTrue(card.is_visible(), chart_id)
        self.assertTrue(card.evaluate("card => {const section=card.closest('section'); return !section.hidden && section.dataset.expanded === 'true';}"))
        page.wait_for_function("id => Boolean(Chart.getChart(id))", arg=chart_id)
        return card

    def test_all_chart_actions_have_correct_share_destination(self):
        page = self.open(self.page())
        self.assertEqual(len(self.charts), page.locator("a.share-linkedin").count())
        self.assertEqual(len(self.charts), page.locator("button.copy-chart-link").count())
        for chart in self.charts:
            card = page.locator("#graf-" + chart["id"])
            self.assertEqual(chart["id"], card.get_attribute("data-share-chart"))
            href = card.locator("a.share-linkedin").get_attribute("href")
            offsite = urlsplit(href)
            self.assertEqual("www.linkedin.com", offsite.netloc)
            self.assertEqual("/sharing/share-offsite/", offsite.path)
            link = parse_qs(offsite.query)["url"][0]
            self.assertEqual(urljoin(self.base_url, "share/" + chart["slug"] + "/"), link.split("?")[0])
            self.assertIn("fund", decode_state(link))
            self.assertIn("period", decode_state(link))

    def test_filter_roundtrip_from_actual_controls(self):
        page = self.open(self.page())
        page.select_option("#fundSelect", self.fund)
        page.select_option("#regionSelect", "hovedstaden")
        page.wait_for_function("!window.DAKPersonalView.isBusy && DATA.meta.regional?.areaName === 'Region Hovedstaden'")
        page.select_option("#periodSelect", "24")
        page.select_option("#comparisonFundSelect", self.comparison)
        page.select_option("#comparisonRegionSelect", "syddanmark")
        page.wait_for_function("!window.DAKPersonalView.isBusy")
        page.evaluate("window.DAKSharing.openChart('unempChart')")
        original_series = page.evaluate("Chart.getChart('unempChart').data.datasets.map(d => ({label:d.label, data:d.data}))")
        link = page.evaluate("window.DAKSharing.getLink('unempChart')")
        expected = self.state(region="hovedstaden", comparisonRegion="syddanmark")
        for field, value in expected.items():
            self.assertEqual(value, decode_state(link)[field], field)
        destination = self.open(self.page(), link)
        self.assert_state(destination, expected)
        self.assert_chart_open(destination, "unempChart")
        self.assertEqual(original_series, destination.evaluate("Chart.getChart('unempChart').data.datasets.map(d => ({label:d.label, data:d.data}))"))

    def test_mobile_result_link_restores_six_months_and_overrides_saved_view(self):
        expected = self.state(rmHorizon="six", hidden=["section-1", "section-4"])
        stale = self.state(fund=self.total, period="12", rmHorizon="three", hidden=["section-4"])
        page = self.open(self.page(mobile=True, storage=stale), self.direct("rmMainChart", expected))
        self.assert_state(page, expected)
        card = self.assert_chart_open(page, "rmMainChart")
        self.assertEqual("six", page.locator("#rmHorizon").input_value())
        self.assertTrue(page.evaluate("Boolean(RM_DATA?.series?.six)"))
        self.assertTrue(page.locator('[data-pv-module][value="section-4"]').is_checked())
        self.assertFalse(page.locator('[data-pv-module][value="section-1"]').is_checked())
        self.assertGreater(card.bounding_box()["y"], -20)
        self.assertLess(card.bounding_box()["y"], 844)
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        self.assertLessEqual(overflow, 2, "Mobile page overflows horizontally")
        if self.screenshot_dir:
            page.screenshot(path=str(self.screenshot_dir / "sharing-mobile-results.png"))

    def test_new_filter_values_replace_old_url_state(self):
        original = self.state(period="12", comparisonFund="", comparisonRegion="")
        page = self.open(self.page(), self.direct("membersRawChart", original))
        page.select_option("#fundSelect", self.comparison)
        page.select_option("#periodSelect", "60")
        latest = decode_state(page.evaluate("window.DAKSharing.getLink('membersRawChart')"))
        self.assertEqual(self.comparison, latest["fund"])
        self.assertEqual("60", latest["period"])
        self.assertEqual("", latest["comparisonFund"])
        link = page.evaluate("window.DAKSharing.getDirectLink('membersRawChart')")
        self.assertEqual("membersRawChart", parse_qs(urlsplit(link).query)["chart"][0])
        self.assertEqual("graf-membersRawChart", urlsplit(link).fragment)

    def test_hidden_legend_series_survives_share(self):
        page = self.open(self.page(), self.direct("talkChart", self.state(comparisonFund="", comparisonRegion="")))
        self.assert_chart_open(page, "talkChart")
        self.assertGreater(page.evaluate("Chart.getChart('talkChart').data.datasets.length"), 1)
        page.evaluate("() => {const chart=Chart.getChart('talkChart');chart.setDatasetVisibility(1,false);chart.update('none');}")
        link = page.evaluate("window.DAKSharing.getLink('talkChart')")
        destination = self.open(self.page(), link)
        self.assert_chart_open(destination, "talkChart")
        self.assertFalse(destination.evaluate("Chart.getChart('talkChart').isDatasetVisible(1)"))
        self.assertTrue(destination.evaluate("Chart.getChart('talkChart').isDatasetVisible(0)"))

    def test_invalid_state_and_unknown_chart_do_not_crash(self):
        states = ["not-valid-base64!", encode_state(["unexpected-array"]), encode_state({"fund": "unknown", "region": "mars", "period": "999", "rmHorizon": "invalid", "hidden": 42})]
        for value in states:
            with self.subTest(state=value):
                page = self.open(self.page(), self.base_url + "?" + urlencode({"pv": value, "chart": "unknown-chart"}))
                self.assertTrue(page.locator("#dashboard").is_visible())
                self.assertEqual(len(self.charts), page.locator("button.copy-chart-link").count())
                self.assertIn(page.locator("#fundSelect").input_value(), self.data["funds"])
                self.assertIn(page.locator("#rmHorizon").input_value(), ["three", "six"])

    def test_clipboard_failure_offers_copyable_link(self):
        page = self.open(self.page(deny_clipboard=True))
        page.locator("#graf-membersRawChart button.copy-chart-link").click()
        dialog = page.locator("dialog#chartShareDialog")
        dialog.wait_for(state="visible")
        link = dialog.locator("#chartShareUrl").input_value()
        self.assertEqual(page.evaluate("window.DAKSharing.getLink('membersRawChart')"), link)
        self.assertIsNotNone(dialog.locator("#chartShareUrl").get_attribute("readonly"))
        dialog.locator("button[data-share-close]").click()
        self.assertFalse(dialog.is_visible())
        if self.screenshot_dir:
            page.screenshot(path=str(self.screenshot_dir / "sharing-desktop.png"))

    def test_copy_button_writes_current_graph_link(self):
        page = self.page()
        page.context.add_init_script("Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText:text=>{window.__copiedChartLink=text;return Promise.resolve();}}});")
        self.open(page)
        page.select_option("#fundSelect", self.fund)
        page.select_option("#periodSelect", "12")
        card = page.locator("#graf-membersRawChart")
        card.locator("button.copy-chart-link").click()
        page.wait_for_function("Boolean(window.__copiedChartLink)")
        self.assertEqual(page.evaluate("window.DAKSharing.getLink('membersRawChart')"), page.evaluate("window.__copiedChartLink"))
        self.assertIn("kopieret", card.locator(".chart-share-feedback").inner_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Read-only check of a deployed dashboard instead of a local server")
    parser.add_argument("--static-only", action="store_true", help="Check HTML metadata and PNGs without Playwright")
    parser.add_argument("--screenshot-dir", type=Path, help="Optional directory for desktop and mobile evidence")
    args = parser.parse_args()
    if args.screenshot_dir:
        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
    with test_server(args.base_url) as base_url:
        charts = load_manifest(base_url)
        check_static_previews(base_url, charts)
        if args.static_only:
            return 0
        SharingTests.base_url = base_url
        SharingTests.charts = charts
        SharingTests.screenshot_dir = args.screenshot_dir
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SharingTests))
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
