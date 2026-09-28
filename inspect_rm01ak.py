import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import jobindsats_api as ji

tables = ji.get("tables", {"format": "json"})
matches = []
for item in ji.walk(tables):
    table_id = item.get("table_id")
    if table_id and ("rm01ak" in str(table_id).lower() or ("nyledighed" in ji.norm(json.dumps(item, ensure_ascii=False)) and "kasse" in ji.norm(json.dumps(item, ensure_ascii=False)))):
        matches.append((table_id, ji.blob(item)[:400]))
print("TABLES", matches[:15])
for table_id, _ in matches[:3]:
    spec = ji.get(f"table/{table_id}", {"format": "json"})
    print("SPEC", table_id, json.dumps(spec, ensure_ascii=False)[:12000])
    try:
        fund = ji.find_hierarchy(spec, ["a kasse", "akasse"])
        level = ji.fund_level(fund)
        selection = f"level:{level}" if level else "*"
        for label, choice in (("funds", selection), ("total", ji.total_value(fund))):
            rows = ji.query(table_id, spec, "latest:2", ((fund, choice),))
            print("ROWS", table_id, label, len(rows), ji.columns(rows), json.dumps(rows[:3], ensure_ascii=False)[:9000])
    except Exception as exc:
        print("ERROR", table_id, str(exc)[:1500])
