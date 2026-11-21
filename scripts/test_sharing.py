#!/usr/bin/env python3
"""Browser checks for graph sharing, using the dashboard's real published data.

Install with ``pip install playwright`` and ``playwright install chromium``.
Run in CI with ``python scripts/test_sharing.py --artifacts /tmp/sharing-test``.
Pass ``--base-url https://ai-michelklos.github.io/A-kasseindsigt-dashboard/``
to check the deployed site instead of starting the local HTTP server.

No LinkedIn post is created: popup/anchor navigation is captured in-page and
LinkedIn requests are blocked at the browser-context boundary. Analytics calls
are also blocked. A local Chart.js file can be supplied with ``--chart-js``;
otherwise the real CDN asset referenced by index.html is used.
"""

from __future__ import annotations

import argparse
import base64
import functools
import json
import re
import struct
import sys
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit


REPO = Path(__file__).resolve().parents[1]
STORAGE_KEY = "dak-a-kasseindsigt-personal-view-v5"
GRAPH_IDS = (
    "membersRawChart", "membersIndexChart", "ageChart", "unempChart",
    "longRawChart", "longIndexChart", "dagChart", "gradCountChart", "gradChart",
    "rmMainChart", "consChart", "exhaustedChart", "survChart",
    "completedDurationChart", "statusChart", "talkChart", "afterlonChart",
    "afterlonContribChart", "sanctionsTotalChart", "sanctionsShareChart",
    "sanctionsTypeChart", "sanctionsAvgChart", "jobSearchShareChart",
)
STATE_KEYS = (
    "v", "region", "fund", "period", "comparisonFund", "comparisonRegion",
    "rmHorizon", "hidden",
)

CAPTURE_SCRIPT = r"""
(() => {
  const capture = window.__sharingTest = {
    copied: [], fallback: [], opened: [], anchorClicks: [], exportText: [], failClipboard: false
  };
  const originalFillText = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
    if (!this.canvas.isConnected) capture.exportText.push(String(text));
    return originalFillText.call(this, text, ...args);
  };
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {writeText: async text => {
      if (capture.failClipboard) throw new DOMException('Clipboard unavailable', 'NotAllowedError');
      capture.copied.push(String(text));
    }}
  });
  window.prompt = (_message, value) => {capture.fallback.push(String(value || '')); return null;};
  const originalExec = document.execCommand?.bind(document);
  document.execCommand = (command, ...args) => {
    if (String(command).toLowerCase() === 'copy') {
      capture.fallback.push(String(document.activeElement?.value || window.getSelection()?.toString() || ''));
      return true;
    }
    return originalExec ? originalExec(command, ...args) : false;
  };
  window.open = url => {
    if (url) capture.opened.push(String(url));
    const location = {};
    Object.defineProperty(location, 'href', {set(value) {capture.opened.push(String(value));}});
    const popup = {opener: null, closed: false, focus() {}, close() {this.closed = true;}};
    Object.defineProperty(popup, 'location', {
      get() {return location;}, set(value) {capture.opened.push(String(value));}
    });
    return popup;
  };
  document.addEventListener('click', event => {
    const anchor = event.target.closest?.('a');
    if (!anchor) return;
    try {
      const url = new URL(anchor.href);
      if (url.hostname === 'linkedin.com' || url.hostname.endsWith('.linkedin.com')) {
        capture.anchorClicks.push(url.href);
        event.preventDefault();
      }
    } catch (_) {}
  });
})();
"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *args):
        pass


@contextmanager
def site_url(base_url: str | None):
    if base_url:
        yield base_url.rstrip("/") + "/"
        return
    handler = functools.partial(QuietHandler, directory=str(REPO))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def encoded(state: dict) -> str:
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decoded(value: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def state_subset(state: dict) -> dict:
    result = {key: state.get(key) for key in STATE_KEYS}
    result["hidden"] = sorted(result["hidden"] or [])
    return result


def shifted_month(value: str, months: int) -> str:
    year, month = map(int, value.split("M"))
    index = year * 12 + month - 1 + months
    return f"{index // 12:04d}M{index % 12 + 1:02d}"


class Suite:
    def __init__(self, browser, base_url, artifacts, chart_js=None):
        self.browser = browser
        self.base_url = base_url
        self.artifacts = artifacts
        self.chart_js = chart_js
        self.results = []
        self.contexts = []
        self.pages = []
        self.errors = []
        self.blocked_linkedin = []
        self.current_checks = 0

    def require(self, condition, message):
        self.current_checks += 1
        if not condition:
            raise AssertionError(message)

    def context(self, *, mobile=False, stored=None):
        context = self.browser.new_context(
            viewport={"width": 390 if mobile else 1360, "height": 844 if mobile else 960},
            device_scale_factor=1,
            reduced_motion="reduce",
            accept_downloads=True,
            locale="da-DK",
        )
        context.set_default_timeout(20000)
        context.set_default_navigation_timeout(45000)
        context.add_init_script(CAPTURE_SCRIPT)
        if stored is not None:
            # Seed only once. Re-seeding on every navigation would mask accidental
            # writes of the incoming share state into the recipient's preferences.
            context.add_init_script(
                "if (!sessionStorage.getItem('sharing-test-seeded')) {"
                f"localStorage.setItem({json.dumps(STORAGE_KEY)}, {json.dumps(json.dumps(stored))});"
                "sessionStorage.setItem('sharing-test-seeded', '1');}"
            )

        def intercept(route):
            url = urlsplit(route.request.url)
            hostname = (url.hostname or "").lower()
            if hostname == "linkedin.com" or hostname.endswith(".linkedin.com"):
                self.blocked_linkedin.append(route.request.url)
                route.abort()
            elif hostname.endswith("goatcounter.com") or hostname == "gc.zgo.at":
                route.fulfill(status=200, content_type="application/javascript", body="")
            elif self.chart_js and "chart.umd" in url.path:
                route.fulfill(path=str(self.chart_js), content_type="application/javascript")
            else:
                route.continue_()

        context.route("**/*", intercept)
        self.contexts.append(context)
        return context

    def page(self, context=None):
        page = (context or self.context()).new_page()
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.pages.append(page)
        return page

    def settle(self, page):
        page.wait_for_function(
            "window.DAKPersonalView && window.DAKDashboardExperience && window.DAKSharing"
        )
        page.evaluate("""async () => {
          await window.DAKPersonalView.ready;
          await window.DAKDashboardExperience.ready;
          await window.DAKSharing.ready;
          await window.DAKPersonalView.whenIdle();
        }""")
        page.wait_for_function("!window.DAKPersonalView.getStatus().busy")
        page.wait_for_function("document.querySelector('#fundSelect')?.options.length > 1")

    def goto(self, page, target=""):
        url = urljoin(self.base_url, target)
        page.goto(url, wait_until="domcontentloaded")
        if "/del/" in urlsplit(url).path:
            page.wait_for_url(lambda current: "/del/" not in urlsplit(current).path, wait_until="domcontentloaded")
        self.settle(page)

    def get_state(self, page):
        return page.evaluate("window.DAKPersonalView.getState()")

    def share_url(self, page, chart_id):
        return page.evaluate("id => window.DAKSharing.getShareUrl(id)", chart_id)

    def localize(self, url):
        """Keep share state intact while exercising local pages in CI."""
        parsed = urlsplit(url)
        if "/del/" in parsed.path:
            relative = "del/" + parsed.path.split("/del/", 1)[1]
        else:
            relative = ""
        return urlunsplit((*urlsplit(urljoin(self.base_url, relative))[:3], parsed.query, parsed.fragment))

    def open_chart(self, page, chart_id):
        page.evaluate("async id => {await window.DAKSharing.openChart(id);}", chart_id)
        self.assert_chart(page, chart_id)

    def assert_chart(self, page, chart_id, *, viewport=False):
        card = page.locator(f"#graf-{chart_id}")
        card.wait_for(state="visible")
        page.wait_for_function("""id => {
          const chart = window.Chart?.getChart(document.getElementById(id));
          return chart && chart.width > 0 && chart.height > 0 && chart.data.labels.length > 0
            && chart.data.datasets.some(set => set.data.some(value => Number.isFinite(value)));
        }""", arg=chart_id)
        self.require(card.count() == 1, f"Expected one permanent card id for {chart_id}")
        section = card.evaluate("el => ({hidden: el.closest('section').hidden, expanded: el.closest('section').dataset.expanded})")
        self.require(not section["hidden"], f"Target section stays hidden for {chart_id}")
        if viewport:
            page.wait_for_function("""id => {
              const heading = document.querySelector('#graf-' + id + ' h3');
              const box = heading?.getBoundingClientRect();
              return box && box.top >= 0 && box.top < innerHeight;
            }""", arg=chart_id)
            heading = card.locator("h3").bounding_box()
            size = page.viewport_size
            self.require(bool(heading) and 0 <= heading["y"] < size["height"], f"Heading is outside viewport for {chart_id}: {heading}")
            self.require(heading["x"] >= -1 and heading["x"] + heading["width"] <= size["width"] + 1, f"Heading overflows viewport for {chart_id}")

    def json_data(self, page, relative):
        response = page.request.get(urljoin(self.base_url, relative))
        self.require(response.ok, f"Could not read real test data: {relative}: {response.status}")
        return response.json()

    def fund_options(self, page):
        options = page.locator("#fundSelect option").evaluate_all(
            "items => items.map(item => ({value:item.value, label:item.textContent}))"
        )
        primary = next((x["value"] for x in options if re.search(r"3F|Faglig Fælles", x["label"], re.I)), None)
        comparison = next((x["value"] for x in options if re.search(r"A\s*&\s*Til", x["label"], re.I)), None)
        self.require(primary and comparison and primary != comparison, f"Real 3F/A&Til options are missing: {options}")
        return primary, comparison

    def choose_state(self, page):
        primary, comparison = self.fund_options(page)
        page.select_option("#fundSelect", primary)
        page.select_option("#regionSelect", "hovedstaden")
        page.evaluate("window.DAKPersonalView.whenIdle()")
        page.select_option("#periodSelect", "24")
        page.select_option("#comparisonFundSelect", comparison)
        page.select_option("#comparisonRegionSelect", "syddanmark")
        page.evaluate("window.DAKPersonalView.whenIdle()")
        self.open_chart(page, "rmMainChart")
        page.select_option("#rmHorizon", "six")
        page.locator("#pvDetails > summary").click()
        page.locator('[data-pv-module][value="kpis"]').uncheck()
        page.locator('[data-pv-module][value="section-10"]').uncheck()
        if page.locator("#pvDetails").get_attribute("open") is not None:
            page.locator("#pvDetails > summary").click()
        page.evaluate("window.DAKPersonalView.whenIdle()")
        expected = {
            "v": 5, "fund": primary, "region": "hovedstaden", "period": "24",
            "comparisonFund": comparison, "comparisonRegion": "syddanmark",
            "rmHorizon": "six", "hidden": ["kpis", "section-10"],
        }
        self.require(state_subset(self.get_state(page)) == state_subset(expected), "UI choices did not produce the full v5 state")
        return expected

    def validate_link(self, url, chart_id, expected=None):
        parsed = urlsplit(url)
        self.require(parsed.scheme in ("http", "https"), f"Not a web share URL: {url}")
        self.require(parsed.path.endswith(f"/del/{chart_id}/"), f"No static graph-specific landing page in URL: {url}")
        values = parse_qs(parsed.query)
        self.require(len(values.get("pv", [])) == 1, f"Expected exactly one pv parameter in {url}")
        state = decoded(values["pv"][0])
        if expected is not None:
            self.require(state_subset(state) == state_subset(expected), f"Share link lost filters: {state}")
        return state

    def toolbar_contract(self):
        page = self.page()
        self.goto(page)
        ids = page.locator(".card[data-share-chart]").evaluate_all("cards => cards.map(card => card.dataset.shareChart)")
        self.require(set(ids) == set(GRAPH_IDS) and len(ids) == 23, f"Expected 23 distinct graph toolbars; got {ids}")
        for chart_id in GRAPH_IDS:
            card = page.locator(f"#graf-{chart_id}")
            self.require(card.locator(".chart-share").count() == 1, f"Missing or duplicate sharing toolbar: {chart_id}")
            for action in ("linkedin", "copy", "image"):
                self.require(card.locator(f'[data-share-action="{action}"]').count() == 1, f"Missing {action} action on {chart_id}")
            href = card.locator('[data-share-action="linkedin"]').get_attribute("href")
            parsed = urlsplit(href or "")
            self.require(parsed.hostname == "www.linkedin.com" and parsed.path.rstrip("/") == "/sharing/share-offsite", f"Invalid LinkedIn URL for {chart_id}: {href}")
            shares = parse_qs(parsed.query).get("url", [])
            self.require(len(shares) == 1, f"Target URL was not encoded as one LinkedIn parameter: {href}")
            self.validate_link(shares[0], chart_id, self.get_state(page))
        self.require(self.get_state(page)["rmHorizon"] == "three", "Default result horizon changed")

    def lazy_navigation(self):
        page = self.page()
        self.goto(page)
        for chart_id in GRAPH_IDS:
            self.open_chart(page, chart_id)
        self.require(page.locator(".card[data-share-chart]").count() == 23, "Rendering duplicated or removed sharing toolbars")

    def filter_roundtrip(self):
        page = self.page()
        self.goto(page)
        expected = self.choose_state(page)
        self.open_chart(page, "unempChart")
        page.locator('#graf-unempChart [data-share-action="copy"]').click()
        page.wait_for_function("window.__sharingTest.copied.length > 0")
        shared = page.evaluate("window.__sharingTest.copied.at(-1)")
        self.validate_link(shared, "unempChart", expected)
        recipient = self.page()
        self.goto(recipient, self.localize(shared))
        self.require(state_subset(self.get_state(recipient)) == state_subset(expected), "Landing-page roundtrip lost a state field")
        self.assert_chart(recipient, "unempChart", viewport=True)
        params = parse_qs(urlsplit(recipient.url).query)
        self.require(params.get("graf") == ["unempChart"], f"Landing page did not forward graph id: {recipient.url}")
        self.require(urlsplit(recipient.url).fragment == "graf-unempChart", "Landing page did not preserve a direct graph anchor")
        primary = self.json_data(recipient, "data/regions/hovedstaden.json")["funds"][expected["fund"]]["unemploymentRate"]
        comparison = self.json_data(recipient, "data/regions/syddanmark.json")["funds"][expected["comparisonFund"]]["unemploymentRate"]
        chart = recipient.evaluate("""() => {
          const chart = Chart.getChart('unempChart');
          return {labels:chart.data.labels, datasets:chart.data.datasets.map(set => ({label:set.label, data:set.data}))};
        }""")
        labels = primary["labels"][-24:]
        self.require(chart["labels"] == labels, "Recipient graph uses the wrong period or geography")
        self.require(chart["datasets"][0]["data"] == primary["values"][-24:], "Primary graph values do not match the shared regional fund")
        lookup = dict(zip(comparison["labels"], comparison["values"]))
        self.require(len(chart["datasets"]) == 2 and chart["datasets"][1]["data"] == [lookup.get(label) for label in labels], "Comparison values do not match the independently chosen region and fund")
        recipient.screenshot(path=str(self.artifacts / "desktop-shared-unemployment.png"))

    def preference_isolation(self):
        stored = {"v": 5, "fund": "43", "region": "all", "period": "60", "comparisonFund": "", "comparisonRegion": "", "rmHorizon": "three", "hidden": ["section-5"]}
        incoming = {"v": 5, "fund": "13", "region": "hovedstaden", "period": "24", "comparisonFund": "43", "comparisonRegion": "nordjylland", "rmHorizon": "six", "hidden": ["kpis", "section-10"]}
        page = self.page(self.context(stored=stored))
        self.goto(page, "?" + urlencode({"graf": "unempChart", "pv": encoded(incoming)}))
        self.require(state_subset(self.get_state(page)) == state_subset(incoming), "Saved preferences overrode incoming share filters")
        after = page.evaluate("key => JSON.parse(localStorage.getItem(key))", STORAGE_KEY)
        self.require(state_subset(after) == state_subset(stored), "Opening a shared view overwrote recipient preferences")
        self.goto(page)
        self.require(state_subset(self.get_state(page)) == state_subset(stored), "Opening the dashboard without pv did not restore recipient preferences")

    def malformed_state(self):
        payloads = ["not!base64", encoded([]), encoded({"v": 5, "fund": "unknown", "region": "../../bad", "period": "99999", "rmHorizon": "invalid", "comparisonFund": "unknown", "comparisonRegion": "unknown", "hidden": ["__proto__", "section-999"]})]
        for payload in payloads:
            page = self.page()
            self.goto(page, "?" + urlencode({"graf": "membersRawChart", "pv": payload}))
            state = self.get_state(page)
            self.require(state["fund"] == "TOT" and state["region"] == "all", f"Malformed pv did not fall back safely: {state}")
            self.require(state["period"] in ("12", "24", "36", "60", "120") and state["rmHorizon"] in ("three", "six"), f"Malformed pv selected unsupported controls: {state}")
            self.assert_chart(page, "membersRawChart")

    def hidden_target(self, *, mobile=False):
        state = {"v": 5, "fund": "TOT", "region": "all", "period": "24", "comparisonFund": "", "comparisonRegion": "", "rmHorizon": "three", "hidden": ["kpis", "section-9", "section-10"]}
        page = self.page(self.context(mobile=mobile))
        self.goto(page, "?" + urlencode({"graf": "sanctionsAvgChart", "pv": encoded(state)}) + "#graf-sanctionsAvgChart")
        self.assert_chart(page, "sanctionsAvgChart", viewport=True)
        section = page.locator("#graf-sanctionsAvgChart").evaluate("card => card.closest('section').dataset.expanded")
        self.require(section == "true", "Target's mobile accordion was not expanded")
        self.require(sorted(self.get_state(page)["hidden"]) == ["kpis", "section-10"], "Opening a hidden target changed unrelated visibility preferences")
        widths = page.evaluate("({page:document.documentElement.scrollWidth, viewport:innerWidth})")
        self.require(widths["page"] <= widths["viewport"] + 1, f"Horizontal overflow at target: {widths}")
        page.screenshot(path=str(self.artifacts / ("mobile-shared-sanctions.png" if mobile else "desktop-hidden-target.png")))

    def anchors_and_legacy(self):
        page = self.page()
        self.goto(page, "?figure=exhaustedChart")
        self.assert_chart(page, "exhaustedChart", viewport=True)
        self.goto(page, "#graf-statusChart")
        self.assert_chart(page, "statusChart", viewport=True)
        page.evaluate("location.hash = 'graf-jobSearchShareChart'")
        page.wait_for_function("document.querySelector('#graf-jobSearchShareChart')?.getBoundingClientRect().top < innerHeight")
        self.assert_chart(page, "jobSearchShareChart", viewport=True)

    def delayed_results(self):
        page = self.page()
        requests = []

        def slow_summary(route):
            requests.append(route.request.url)
            time.sleep(0.35)  # Real data, with a deliberately slow asynchronous fetch.
            route.continue_()

        page.route("**/data/rm01ak-summary.json*", slow_summary)
        state = {"v": 5, "fund": "43", "region": "hovedstaden", "period": "12", "comparisonFund": "", "comparisonRegion": "", "rmHorizon": "six", "hidden": []}
        self.goto(page, "?" + urlencode({"graf": "rmMainChart", "pv": encoded(state)}))
        self.assert_chart(page, "rmMainChart", viewport=True)
        self.require(bool(requests), "Result summary was not loaded lazily from the real endpoint")
        self.require(page.locator("#rmHorizon").input_value() == "six", "Shared six-month result selection was lost during summary fetch")
        geography = page.locator("#graf-rmMainChart .geography-context").inner_text()
        self.require("Hele landet" in geography and "Hovedstaden" not in geography, f"National result data are incorrectly labelled as regional: {geography}")
        summary = self.json_data(page, "data/rm01ak-summary.json")
        funds = self.json_data(page, "data/dashboard-data.json")["funds"]
        source_code = funds["43"]["starCode"]
        reports = sorted(shifted_month(label, 6) for label in summary["series"]["six"]["TOTAL"])[-12:]
        expected_values = [summary["series"]["six"][source_code].get(shifted_month(report, -6)) for report in reports]
        actual = page.evaluate("({labels:Chart.getChart('rmMainChart').data.labels, values:Chart.getChart('rmMainChart').data.datasets[0].data})")
        self.require(actual == {"labels": reports, "values": expected_values}, "Result graph shows the wrong horizon or stale asynchronously loaded data")
        self.require("6 måneders" in page.locator("#rmOfficialCounts").inner_text(), "Official count explanation does not follow the shared horizon")

    def linkedin_click(self):
        page = self.page()
        self.goto(page)
        page.select_option("#periodSelect", "12")
        self.open_chart(page, "exhaustedChart")
        expected = self.get_state(page)
        page.locator('#graf-exhaustedChart [data-share-action="linkedin"]').click()
        page.wait_for_function("[...window.__sharingTest.opened, ...window.__sharingTest.anchorClicks].some(url => url.includes('linkedin.com/sharing/share-offsite'))")
        captures = page.evaluate("[...window.__sharingTest.opened, ...window.__sharingTest.anchorClicks]")
        actual = next(url for url in reversed(captures) if "linkedin.com/sharing/share-offsite" in url)
        target = parse_qs(urlsplit(actual).query).get("url", [])
        self.require(len(target) == 1, "LinkedIn action split the shared URL's query parameters")
        self.validate_link(target[0], "exhaustedChart", expected)
        self.require(not self.blocked_linkedin, "LinkedIn navigation escaped in-page interception; requests were safely blocked")

    def clipboard_fallback(self):
        page = self.page()
        self.goto(page)
        page.evaluate("window.__sharingTest.failClipboard = true")
        page.locator('#graf-membersRawChart [data-share-action="copy"]').click()
        page.wait_for_function("window.__sharingTest.fallback.some(value => value.includes('pv='))")
        copied = page.evaluate("window.__sharingTest.fallback.find(value => value.includes('pv='))")
        self.validate_link(copied, "membersRawChart", self.get_state(page))

    def png_download(self):
        page = self.page()
        self.goto(page)
        primary, _comparison = self.fund_options(page)
        page.select_option("#fundSelect", primary)
        page.select_option("#periodSelect", "12")
        page.select_option("#comparisonFundSelect", "TOT")
        page.select_option("#comparisonRegionSelect", "all")
        page.evaluate("window.DAKPersonalView.whenIdle()")
        self.open_chart(page, "membersRawChart")
        comparison_chips = page.locator("#graf-membersRawChart .comparison-chip").all_text_contents()
        self.require(len(comparison_chips) >= 2 and any("I alt" in chip for chip in comparison_chips), "Expected actual count comparisons before exporting the graph")
        before = self.get_state(page)
        page.evaluate("window.__sharingTest.exportText = []")
        with page.expect_download(timeout=30000) as downloaded:
            page.locator('#graf-membersRawChart [data-share-action="image"]').click()
        download = downloaded.value
        path = self.artifacts / "downloaded-filtered-chart.png"
        download.save_as(str(path))
        blob = path.read_bytes()
        self.require(download.failure() is None and download.suggested_filename.lower().endswith(".png"), "Chart image did not download as a PNG")
        self.require(blob.startswith(b"\x89PNG\r\n\x1a\n") and len(blob) > 5000, "Downloaded chart is empty or not a PNG")
        width, height = struct.unpack(">II", blob[16:24])
        self.require(width >= 300 and height >= 200, f"Downloaded chart is too small: {width}x{height}")
        exported_text = re.sub(r"\s+", " ", " ".join(page.evaluate("window.__sharingTest.exportText"))).strip()
        for chip in comparison_chips:
            normalized = re.sub(r"\s+", " ", chip).strip()
            self.require(normalized in exported_text, f"PNG export lost a comparison label or count: {normalized}")
        self.require(state_subset(self.get_state(page)) == state_subset(before), "PNG export changed the selected filters")

    def run_case(self, name, method):
        self.contexts, self.pages, self.errors, self.blocked_linkedin = [], [], [], []
        self.current_checks = 0
        started = time.monotonic()
        result = {"name": name, "status": "passed"}
        try:
            method()
            self.require(not self.errors, f"Browser JavaScript errors: {self.errors}")
        except Exception as error:
            result.update(status="failed", error=str(error), traceback=traceback.format_exc())
            if self.pages:
                screenshot = self.artifacts / (re.sub(r"[^a-z0-9]+", "-", name.lower()) + "-failure.png")
                try:
                    self.pages[-1].screenshot(path=str(screenshot), timeout=5000)
                    result["screenshot"] = str(screenshot)
                except Exception:
                    pass
        finally:
            result["checks"] = self.current_checks
            result["duration_ms"] = round((time.monotonic() - started) * 1000)
            if self.errors:
                result["page_errors"] = self.errors
            for context in self.contexts:
                context.close()
        self.results.append(result)
        print(f"{result['status'].upper()}: {name} ({result['checks']} assertions)", flush=True)
        if result["status"] == "failed":
            print(result["error"], flush=True)

    def run(self):
        cases = [
            ("23 graph toolbars and encoded LinkedIn links", self.toolbar_contract),
            ("Lazy navigation renders every graph", self.lazy_navigation),
            ("Real filter choices survive landing-page roundtrip", self.filter_roundtrip),
            ("Incoming state and stored preferences stay independent", self.preference_isolation),
            ("Malformed sharing state fails safely", self.malformed_state),
            ("Hidden desktop target opens without unhiding other sections", self.hidden_target),
            ("390px target expands and fits without horizontal overflow", lambda: self.hidden_target(mobile=True)),
            ("Legacy query, bare anchor and later hash changes", self.anchors_and_legacy),
            ("Six-month result state survives delayed summary fetch", self.delayed_results),
            ("LinkedIn click captures the full URL without external navigation", self.linkedin_click),
            ("Clipboard rejection provides a usable fallback", self.clipboard_fallback),
            ("Filtered graph downloads as a nonempty PNG", self.png_download),
        ]
        for name, method in cases:
            self.run_case(name, method)
        return self.results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Check an already published dashboard, without starting a local server")
    parser.add_argument("--artifacts", type=Path, default=Path(tempfile.mkdtemp(prefix="dak-sharing-test-")))
    parser.add_argument("--chart-js", type=Path, help="Optional local copy of the actual Chart.js CDN bundle")
    parser.add_argument("--browser-executable", type=Path, help="Explicit installed Chromium executable for CI")
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "repository": str(REPO), "artifacts": str(args.artifacts), "results": []}
    exit_code = 1
    try:
        from playwright.sync_api import sync_playwright

        if args.chart_js and not args.chart_js.is_file():
            raise FileNotFoundError(f"Chart.js bundle does not exist: {args.chart_js}")
        with site_url(args.base_url) as base_url, sync_playwright() as playwright:
            report["base_url"] = base_url
            launch = {"headless": True}
            if args.browser_executable:
                launch["executable_path"] = str(args.browser_executable)
            browser = playwright.chromium.launch(**launch)
            try:
                report["browser"] = browser.version
                suite = Suite(browser, base_url, args.artifacts, args.chart_js)
                report["results"] = suite.run()
            finally:
                browser.close()
        report["passed"] = sum(result["status"] == "passed" for result in report["results"])
        report["failed"] = sum(result["status"] == "failed" for result in report["results"])
        report["assertions"] = sum(result["checks"] for result in report["results"])
        exit_code = int(report["failed"] > 0)
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc(), passed=0, failed=1)
        print(f"Unable to complete browser checks: {error}", file=sys.stderr)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        summary = args.artifacts / "summary.json"
        summary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report.get("passed", 0), "failed": report.get("failed", 1), "assertions": report.get("assertions", 0), "report": str(summary)}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
