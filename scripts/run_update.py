from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "dashboard-data.json"
HTML = BASE / "index.html"


def validate():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    state = meta.get("updateStatus", {}).get("state")
    if state not in {"ok", "partial"}:
        raise RuntimeError(f"Dashboardstatus er {state}")
    funds = data.get("funds", {})
    total_code = meta.get("totalFundCode")
    if not total_code or total_code not in funds:
        raise RuntimeError("Total a-kasse mangler")
    if len(funds) < 10:
        raise RuntimeError(f"For faa aktive a-kasser: {len(funds)}")
    total = funds[total_code]
    for key, source in (("members", "AUA01"), ("unemploymentRate", "AUP03"), ("longTermPer1000", "AULK08")):
        series = total.get(key, {})
        labels = series.get("labels", [])
        values = series.get("values", [])
        if not labels or len(labels) != len(values):
            raise RuntimeError(f"Ugyldig totalserie {key}")
        source_info = meta.get("sourceStatus", {}).get(source, {})
        if source_info.get("state") == "ok" and source_info.get("latestPeriod") != labels[-1]:
            raise RuntimeError(f"Periode mismatch for {source}")
    text = HTML.read_text(encoding="utf-8")
    required = ['data/dashboard-data.json', 'akassesiden.goatcounter.com/count', 'gc.zgo.at/count.js', 'id="fundSelect"', 'id="benchmarkSelect"']
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"HTML mangler: {missing}")
    print("OK: A-kasseindsigt bestod datavalidering")


def main():
    subprocess.run([sys.executable, str(BASE / "scripts" / "fetch_sources.py")], check=True)
    validate()


if __name__ == "__main__":
    main()
