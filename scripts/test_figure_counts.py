import copy
import unittest
from unittest.mock import patch
import jobindsats_patch as national
import fetch_jobindsats_regions as regional
from fetch_rm01ak import cohort
from validate_figure_counts import COLUMN, validate_survival

WEEK = 'Overlevelseskurve u. tilbagefald til den valgte ydelse: 52 uger'
ROWS = [
    {'Periode': '2025Q01', 'A-kasse': 'total', WEEK: 10, COLUMN: 123},
    {'Periode': '2025Q01', 'A-kasse': 'fund', WEEK: 11, COLUMN: 17},
    {'Periode': '2025Q02', 'A-kasse': 'total', WEEK: None, COLUMN: 999},
    {'Periode': '2025Q02', 'A-kasse': 'fund', WEEK: None, COLUMN: 888},
]

class CountsTest(unittest.TestCase):
    def payload(self):
        return {'meta': {'totalFundCode': 'total'}, 'funds': {'total': {'jobindsats': {}}, 'fund': {'jobindsats': {}}}}

    def test_national_matches_curve_period_not_latest_count(self):
        data = self.payload()
        with patch.object(national, 'setup', return_value=({}, {}, 'all')), patch.object(national.ji, 'query', return_value=ROWS), patch.object(national, 'fund_code', side_effect=lambda name, data: name), patch.object(national, 'put_status'):
            national.survival(data)
        self.assertEqual(data['funds']['fund']['jobindsats']['survival']['startedCount'], 17)
        self.assertEqual(data['funds']['fund']['jobindsats']['survival']['period'], '2025Q01')
        self.assertEqual(validate_survival(data), 2)

    def test_regional_suppression_is_not_zero(self):
        rows = copy.deepcopy(ROWS)
        rows[1][COLUMN] = '..'
        data = self.payload()
        with patch.object(regional.ji, 'get', return_value={}), patch.object(regional, 'all_fund_rows', return_value=rows), patch.object(regional, 'fund_code', side_effect=lambda row, col, data: row[col]), patch.object(regional, 'put_status'):
            regional.survival({}, data, {})
        self.assertIsNone(data['funds']['fund']['jobindsats']['survival']['startedCount'])
        validate_survival(data)

    def test_wrong_curve_count_column_rejected(self):
        rows = [{k: v for k, v in row.items() if k != COLUMN} for row in ROWS]
        with patch.object(national, 'setup', return_value=({}, {}, 'all')), patch.object(national.ji, 'query', return_value=rows):
            with self.assertRaises(RuntimeError): national.survival(self.payload())

    def test_horizons(self):
        self.assertEqual(cohort('2026M08', 3), '2026M05')
        self.assertEqual(cohort('2026M08', 6), '2026M02')
        self.assertEqual(cohort('2026M01', 6), '2025M07')

if __name__ == '__main__': unittest.main()
