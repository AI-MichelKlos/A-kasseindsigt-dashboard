from pathlib import Path

p = Path('scripts/jobindsats_patch.py')
text = p.read_text(encoding='utf-8')
old = '''    rows = fetch_periods(selection)\n    rows.extend(fetch_periods(ji.total_value(fund_h)))\n    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)\n'''
new = '''    rows = fetch_periods(selection)\n    total_rows = fetch_periods(ji.total_value(fund_h))\n    for row in total_rows:\n        row["_dak_force_total"] = True\n    rows.extend(total_rows)\n    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)\n'''
if text.count(old) != 1:
    raise RuntimeError(f'Forventede præcis én totalblok, fandt {text.count(old)}')
text = text.replace(old, new, 1)
old2 = '''    for row in rows:\n        code = fund_code(row.get(fcol), data)\n        period = str(row.get(pcol) or "")\n'''
# Kun sanctions-loopet skal ændres; find første forekomst efter def sanctions.
pos = text.index('def sanctions(data):')
head, tail = text[:pos], text[pos:]
if tail.count(old2) < 1:
    raise RuntimeError('Mangler sanctions-loop')
new2 = '''    for row in rows:\n        code = data["meta"]["totalFundCode"] if row.get("_dak_force_total") else fund_code(row.get(fcol), data)\n        period = str(row.get(pcol) or "")\n'''
tail = tail.replace(old2, new2, 1)
p.write_text(head + tail, encoding='utf-8')
