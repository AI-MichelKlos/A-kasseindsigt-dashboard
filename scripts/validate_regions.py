from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MAIN = BASE / "data" / "dashboard-data.json"
REGION_DIR = BASE / "data" / "regions"
EXPECTED = {
    "hovedstaden": "Region Hovedstaden",
    "sjaelland": "Region Sjælland",
    "syddanmark": "Region Syddanmark",
    "midtjylland": "Region Midtjylland",
    "nordjylland": "Region Nordjylland",
}


def valid_series(block: dict, key: str = "values") -> bool:
    labels = block.get("labels", [])
    values = block.get(key, [])
    return bool(labels) and len(labels) == len(values) and len(labels) <= 60


def main() -> None:
    main_data = json.loads(MAIN.read_text(encoding="utf-8"))
    main_funds = main_data.get("funds", {})
    total = str(main_data.get("meta", {}).get("totalFundCode") or "")
    if not main_funds or total not in main_funds:
        raise RuntimeError("Hoveddata er ikke valide")

    for slug, name in EXPECTED.items():
        path = REGION_DIR / f"{slug}.json"
        if not path.exists():
            raise RuntimeError(f"Regional datafil mangler: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        funds = data.get("funds", {})
        if meta.get("areaName") != name:
            raise RuntimeError(f"Forkert områdenavn i {slug}: {meta.get('areaName')}")
        if meta.get("historyMonths") != 60:
            raise RuntimeError(f"Forkert historiklængde i {slug}")
        if set(funds) != set(main_funds):
            raise RuntimeError(f"A-kassekoder afviger i {slug}")
        statuses = meta.get("sourceStatus", {})
        for source in ("AUA01", "AUP03"):
            if statuses.get(source, {}).get("state") != "ok":
                raise RuntimeError(f"{slug}: {source} er ikke ok")
        total_fund = funds.get(total, {})
        members = total_fund.get("members", {})
        rate = total_fund.get("unemploymentRate", {})
        if not valid_series(members):
            raise RuntimeError(f"{slug}: ugyldig medlemstidsserie")
        if not valid_series(rate):
            raise RuntimeError(f"{slug}: ugyldig ledighedstidsserie")
        if members["labels"][-1] != statuses["AUA01"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: AUA01 periode mismatch")
        if rate["labels"][-1] != statuses["AUP03"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: AUP03 periode mismatch")
        if not total_fund.get("profileAge"):
            raise RuntimeError(f"{slug}: aldersprofil mangler")

    print("OK: regionale A-kassedata bestod validering")


if __name__ == "__main__":
    main()
