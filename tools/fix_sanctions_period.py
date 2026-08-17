from pathlib import Path

p = Path('scripts/jobindsats_patch.py')
text = p.read_text(encoding='utf-8')
old = '    rows = ji.query(table, spec, "latest:40", ((fund_h, selection),))\n'
new = '''    try:\n        rows = ji.query(table, spec, "latest:40", ((fund_h, selection),))\n    except RuntimeError as exc:\n        # Tabellen starter i 2019 og har derfor endnu under 40 kvartaler.\n        # Jobindsats afviser latest:N, hvis N er større end den tilgængelige historik.\n        match = re.search(r"only (\\d+) periods are available", str(exc), re.IGNORECASE)\n        if not match:\n            raise\n        available = min(40, int(match.group(1)))\n        rows = ji.query(table, spec, f"latest:{available}", ((fund_h, selection),))\n'''
if text.count(old) != 1:
    raise RuntimeError(f'Forventede præcis én sanctions-query, fandt {text.count(old)}')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')
