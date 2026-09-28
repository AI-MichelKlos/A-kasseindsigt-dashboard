"""Hent og valider Jobindsats RM01AK til det selvstændige resultatdashboard."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import jobindsats_api as api

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "rm01ak.json"
CONFIG = BASE / "config" / "a-kasse-navne.json"
TABLE = "rm01ak"
MEASURES = {
    "three": "Personer i job og uddannelse 3 mdr. efter nyledighed: Andel i job og uddannelse",
    "six": "Personer i job og uddannelse 6 mdr. efter nyledighed: Andel i job og uddannelse",
}
COUNTS = {
    "three": "Personer i job og uddannelse 3 mdr. efter nyledighed: Antal nyledige for 3 mdr. siden",
    "six": "Personer i job og uddannelse 6 mdr. efter nyledighed: Antal nyledige for 6 mdr. siden",
}


def cohort(status_month: str, offset: int) -> str:
    match = re.fullmatch(r"(\d{4})M(\d{2})", status_month)
    if not match:
        raise ValueError(f"Uventet statusperiode: {status_month}")
    month_index = int(match[1]) * 12 + int(match[2]) - 1 - offset
    return f"{month_index // 12}M{month_index % 12 + 1:02d}"


def main() -> None:
    spec = api.get(f"table/{TABLE}", {"format": "json"})
    if spec.get("table_id") != TABLE or "3 og 6" not in spec.get("table_name", ""):
        raise ValueError("Jobindsats-metadata matcher ikke den forventede resultatmåling")
    available = next((p["values"] for p in spec.get("periods", []) if p.get("periodtype_id") == "M"), [])
    if not available:
        raise ValueError("Ingen månedlige perioder i Jobindsats-metadata")
    latest_status = available[0]["period_id"]
    if not re.fullmatch(r"\d{4}M\d{2}", latest_status):
        raise ValueError(f"Uventet nyeste periode: {latest_status}")
    fund_h = api.find_hierarchy(spec, ["a kasse", "akasse"])
    level = api.fund_level(fund_h)
    if not level:
        raise ValueError("A-kasseniveau kunne ikke verificeres")
    take = min(60, len(available))
    funds_rows = api.query(TABLE, spec, f"latest:{take}", ((fund_h, f"level:{level}"),))
    total_rows = api.query(TABLE, spec, f"latest:{take}", ((fund_h, api.total_value(fund_h)),))
    expected_columns = {"Periode", "A-kasse", *MEASURES.values(), *COUNTS.values()}
    if not expected_columns.issubset(api.columns(funds_rows)) or not expected_columns.issubset(api.columns(total_rows)):
        raise ValueError(f"Målingskolonner ændret: {api.columns(funds_rows)}")

    config = json.loads(CONFIG.read_text(encoding="utf-8"))["funds"]
    names = {api.norm(item["jobindsatsName"]): item for item in config}
    if len(names) != len(config):
        raise ValueError("Dublerede a-kassenavne i navnebroen")
    funds = {"TOTAL": {"short": "I alt", "name": "A-kasser i alt"}}
    funds.update({item["starCode"]: {"short": item["dakShort"], "name": item["dakName"]} for item in config})
    series = {key: {code: {} for code in funds} for key in MEASURES}
    counts = {key: {code: {} for code in funds} for key in MEASURES}
    observed = set()

    def add(row: dict, code: str) -> None:
        status_month = str(row["Periode"])
        for key, offset in (("three", 3), ("six", 6)):
            start_month = cohort(status_month, offset)
            value = api.number(row[MEASURES[key]])
            count = api.number(row[COUNTS[key]])
            if value is not None and not (0 <= value <= 100):
                raise ValueError(f"Ugyldig procent for {code} {status_month}: {value}")
            if count is not None and count < 0:
                raise ValueError(f"Ugyldigt antal for {code} {status_month}: {count}")
            if start_month in series[key][code]:
                raise ValueError(f"Dublet for {code} {key} {start_month}")
            series[key][code][start_month] = value
            counts[key][code][start_month] = count

    for row in funds_rows:
        source_name = api.norm(row["A-kasse"])
        if source_name in {"ingen a kasse", "a kasse i alt", "i alt"}:
            continue
        item = names.get(source_name)
        if item is None:
            raise ValueError(f"Ukendt a-kasse i Jobindsats: {row['A-kasse']}")
        code = item["starCode"]
        observed.add(code)
        add(row, code)
    for row in total_rows:
        if api.norm(row["A-kasse"]) not in ("a kasse i alt", "i alt"):
            raise ValueError(f"Totalrækken er ikke en verificeret a-kassetotal: {row['A-kasse']}")
        add(row, "TOTAL")

    if observed != set(funds) - {"TOTAL"}:
        raise ValueError(f"A-kassedækning afviger: mangler {sorted(set(funds)-observed-{'TOTAL'})}")
    for key, offset in (("three", 3), ("six", 6)):
        latest_cohort = cohort(latest_status, offset)
        if not isinstance(series[key]["TOTAL"].get(latest_cohort), (int, float)):
            raise ValueError(f"Manglende officiel total for {key} i {latest_status}")
        if not isinstance(counts[key]["TOTAL"].get(latest_cohort), (int, float)):
            raise ValueError(f"Manglende populationsstørrelse for {key} i {latest_status}")
        if len(series[key]["TOTAL"]) != take:
            raise ValueError(f"Ufuldstændig historik for {key}")

    payload = {
        "meta": {
            "state": "ok", "source": "Jobindsats.dk / STAR", "dataset": TABLE,
            "latestStatusMonth": latest_status,
            "latestCohort": {key: cohort(latest_status, n) for key, n in (("three", 3), ("six", 6))},
            "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "unit": "pct. af nyledige", "geography": "Hele landet",
            "filters": "Alle køn, aldre og herkomster; a-kasse ved nyledighed",
            "note": "Officiel totalrække og officielle a-kasserækker. Prikker/diskretionerede værdier er null. Ujusterede andele.",
        },
        "funds": funds, "series": series, "counts": counts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RM01AK: {latest_status}, {len(observed)} a-kasser, {take} måneder, 3 mdr. {series['three']['TOTAL'][cohort(latest_status,3)]} %, 6 mdr. {series['six']['TOTAL'][cohort(latest_status,6)]} %")


if __name__ == "__main__":
    main()
