"""Validate direct source counts, keeping suppressed values distinct from zero."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
COLUMN = 'Overlevelseskurve u. tilbagefald til den valgte ydelse: Antal påbegyndte forløb'


def validate_survival(payload):
    found = 0
    for code, fund in payload['funds'].items():
        source = fund.get('jobindsats', {}).get('survival')
        if not source:
            continue
        assert source.get('period') and source.get('items'), code
        assert source.get('countSourceColumn') == COLUMN, code
        assert 'startedCount' in source, code
        value = source['startedCount']
        assert value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 and int(value) == value), code
        found += 1
    assert found, 'Ingen overlevelseskurver valideret'
    return found


def main():
    for path in [BASE / 'data/dashboard-data.json', *sorted((BASE / 'data/regions').glob('*.json'))]:
        payload = json.loads(path.read_text())
        # Regions without this module explicitly use the national fallback.
        if not any(f.get('jobindsats', {}).get('survival') for f in payload.get('funds', {}).values()):
            continue
        print(path.name, validate_survival(payload), 'kurver med direkte kildeantal')


if __name__ == '__main__':
    main()
