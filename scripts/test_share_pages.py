"""Checks for the data and metadata behind static share previews."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import build_share_pages as share


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((share.BASE / "config/share-charts.json").read_text())
        cls.data = json.loads((share.BASE / "data/dashboard-data.json").read_text())
        cls.results = json.loads((share.BASE / "data/rm01ak-summary.json").read_text())
        cls.specs = share.make_specs(cls.registry, cls.data, cls.results)
        cls.by_id = {spec["id"]: spec for spec in cls.specs}
        cls.total = cls.data["funds"][cls.data["meta"]["totalFundCode"]]

    def test_every_existing_chart_has_a_preview(self):
        share.validate_registry(self.registry)
        self.assertEqual(set(self.by_id), {entry["id"] for entry in self.registry["charts"]})
        self.assertEqual(len(self.specs), 23)

    def test_missing_registry_chart_is_rejected(self):
        incomplete = copy.deepcopy(self.registry)
        incomplete["charts"].pop()
        with self.assertRaises(ValueError):
            share.validate_registry(incomplete)

    def test_timeseries_is_the_existing_total_with_default_window(self):
        preview = self.by_id["unempChart"]
        source = self.total["unemploymentRate"]
        self.assertEqual(preview["labels"], source["labels"][-36:])
        self.assertEqual(preview["datasets"][0]["values"], source["values"][-36:])
        self.assertEqual(preview["period"], source["labels"][-1])
        self.assertTrue(preview["percent"])

    def test_quarterly_and_yearly_windows_match_three_years(self):
        self.assertEqual(self.by_id["sanctionsTotalChart"]["labels"], self.total["jobindsats"]["sanctions"]["labels"][-12:])
        self.assertEqual(self.by_id["afterlonContribChart"]["labels"], self.total["jobindsats"]["afterlonContrib"]["labels"][-3:])

    def test_indexes_use_first_nonzero_visible_observation(self):
        labels, values = share.series({"labels": ["a", "b", "c", "d"], "values": [999, None, 20, 24]}, "values", 3, True)
        self.assertEqual(labels, ["b", "c", "d"])
        self.assertEqual(values, [None, 100.0, 120.0])

    def test_percentages_keep_missing_values_unknown(self):
        labels, values = share.category({"items": [{"label": "A", "value": None}, {"label": "B", "value": 12}]}, True)
        self.assertEqual(values, [None, None])
        labels, values = share.category({"items": [{"label": "A", "value": 3}, {"label": "B", "value": 9}]}, True)
        self.assertEqual(values, [25.0, 75.0])

    def test_completed_duration_uses_counts_as_share_denominator(self):
        values = self.by_id["completedDurationChart"]["datasets"][0]["values"]
        items = self.total["jobindsats"]["completedDuration"]["items"]
        denominator = sum(item["value"] for item in items)
        self.assertAlmostEqual(sum(values), 100)
        for value, item in zip(values, items):
            self.assertAlmostEqual(value, item["value"] / denominator * 100)

    def test_exhausted_groups_match_each_existing_category(self):
        source = self.total["jobindsats"]["exhaustedRights"]
        preview = self.by_id["exhaustedChart"]
        self.assertEqual(len(preview["datasets"]), len(source["categories"]))
        for plotted, raw in zip(preview["datasets"], source["categories"]):
            self.assertEqual(plotted["label"], raw["label"])
            self.assertEqual(plotted["values"], raw["values"][-36:])

    def test_result_measure_maps_cohort_to_report_month_without_changing_values(self):
        preview = self.by_id["rmMainChart"]
        raw = self.results["series"]["three"]["TOTAL"]
        for report, value in zip(preview["labels"], preview["datasets"][0]["values"]):
            self.assertEqual(value, raw[share.shift_month(report, -3)])
        self.assertEqual(share.shift_month("2025M11", 3), "2026M02")
        self.assertEqual(preview["period"], self.results["meta"]["latestStatusMonth"])

    def test_metadata_is_available_without_javascript_and_is_chart_specific(self):
        for spec in self.specs:
            markup = share.share_html(spec, "abcdef0123456789")
            parser = share.MetadataParser()
            parser.feed(markup)
            self.assertEqual(parser.meta["og:url"], share.SITE + f"del/{spec['id']}/")
            self.assertEqual(parser.meta["og:image:width"], "1200")
            self.assertEqual(parser.meta["og:image:height"], "630")
            self.assertIn(f"assets/share/{spec['id']}.png", parser.meta["og:image"])
            self.assertIn("I alt, hele landet", parser.meta["og:image:alt"])
            self.assertIn(f"../../?graf={spec['id']}#graf-{spec['id']}", markup)
            self.assertFalse(parser.refresh)
            self.assertIn("<noscript>", markup)

    def test_metadata_escapes_titles_and_descriptions(self):
        spec = dict(self.specs[0], title='A & B <graf> "test"', description="A < B & C")
        markup = share.share_html(spec, "123456789abc")
        self.assertIn("A &amp; B &lt;graf&gt; &quot;test&quot;", markup)
        self.assertNotIn("<graf>", markup)

    def test_previous_share_urls_use_current_preview_and_correct_relative_paths(self):
        for spec in self.specs:
            markup = share.share_html(spec, "abcdef0123456789", relative_root="../")
            parser = share.MetadataParser()
            parser.feed(markup)
            self.assertEqual(parser.meta["og:url"], share.SITE + f"del/{spec['id']}/")
            self.assertIn(f"assets/share/{spec['id']}.png", parser.meta["og:image"])
            self.assertIn(f'href="../?graf={spec["id"]}#graf-{spec["id"]}"', markup)
            self.assertIn('src="../assets/share-redirect.js?v=1"', markup)
            self.assertNotIn('src="../../', markup)
            self.assertFalse(parser.refresh)

    def test_freshness_follows_data_changes_but_not_retrieval_clock(self):
        changed = copy.deepcopy(self.data)
        changed["meta"]["checkedAt"] = "2099-01-01"
        unchanged_specs = share.make_specs(self.registry, changed, self.results)
        self.assertEqual(share.input_digest(self.specs), share.input_digest(unchanged_specs))
        changed["funds"][changed["meta"]["totalFundCode"]]["unemploymentRate"]["values"][-1] += 0.1
        changed_specs = share.make_specs(self.registry, changed, self.results)
        self.assertNotEqual(share.input_digest(self.specs), share.input_digest(changed_specs))


if __name__ == "__main__":
    unittest.main()
