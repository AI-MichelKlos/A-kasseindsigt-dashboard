import json
import jobindsats_api as ji

DEFS = [
    ("early", ["jobsamtaler", "a dagpengemodtagere", "a kasserne"], ["jobcent"], "latest:1"),
    ("consumption", ["antal personer med forbrug af dagpengeperioden"], [], "latest:1"),
    ("survival", ["overlevelseskurver", "a dagpenge"], ["sygedagpenge", "kontanthjaelp"], "latest:1"),
    ("status", ["arbejdsmarkedsstatus", "afsluttet", "a dagpenge"], ["sygedagpenge", "kontanthjaelp"], "latest:1"),
]

tables = ji.get("tables", {"format": "json"})
for name, phrases, excludes, period in DEFS:
    print("\n###", name)
    table = ji.find_table(tables, phrases, excludes)
    table_id = str(table["table_id"])
    print("table", table_id, table.get("_match_text"))
    spec = ji.get(f"table/{table_id}", {"format": "json"})
    print("hierarchies")
    for h in ji.hierarchies(spec):
        print(" ", h.get("hierarchy_id"), json.dumps(h, ensure_ascii=False)[:1200])
    fund = ji.find_hierarchy(spec, ["a kasse", "akasse"])
    level = ji.fund_level(fund)
    selection = f"level:{level}" if level else "*"
    rows = ji.query(table_id, spec, period, ((fund, selection),))
    print("columns", ji.columns(rows))
    for row in rows[:8]:
        print(json.dumps(row, ensure_ascii=False)[:2000])
