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
STATUS = {
    "three": {
        "job": "Status 3 mdr. efter nyledighed, pct.: Job",
        "education": "Status 3 mdr. efter nyledighed, pct.: Uddannelse",
        "onBenefit": "Status 3 mdr. efter nyledighed, pct.: Fortsat på ydelsen",
        "otherBenefit": "Status 3 mdr. efter nyledighed, pct.: Anden ydelse",
        "selfSupport": "Status 3 mdr. efter nyledighed, pct.: Selvforsørgelse mv.",
    },
    "six": {
        "job": "Status 6 mdr. efter nyledighed, pct.: Job",
        "education": "Status 6 mdr. efter nyledighed, pct.: Uddannelse",
        "onBenefit": "Status 6 mdr. efter nyledighed, pct.: Fortsat på ydelsen",
        "otherBenefit": "Status 6 mdr. efter nyledighed, pct.: Anden ydelse",
        "selfSupport": "Status 6 mdr. efter nyledighed, pct.: Selvforsørgelse mv.",
    },
}
GROUPS = {
    "sex": ("Køn", "_kon", "kon", "Køn"),
    "age": ("Alder", "_alder5i30", "alder5i", "Alder"),
    "origin": ("Herkomst", "_oprinda", "oprinda", "Herkomst"),
    "region": ("Region", "_region", "region", "Område"),
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
    expected_columns = {"Periode", "A-kasse", *MEASURES.values(), *COUNTS.values(), *(col for group in STATUS.values() for col in group.values())}
    if not expected_columns.issubset(api.columns(funds_rows)) or not expected_columns.issubset(api.columns(total_rows)):
        raise ValueError(f"Målingskolonner ændret: {api.columns(funds_rows)}")

    config = json.loads(CONFIG.read_text(encoding="utf-8"))["funds"]
    names = {api.norm(item["jobindsatsName"]): item for item in config}
    if len(names) != len(config):
        raise ValueError("Dublerede a-kassenavne i navnebroen")
    funds = {"TOTAL": {"short": "I alt", "name": "A-kasser i alt"}}
    funds.update({item["starCode"]: {"short": item["dakShort"], "name": item["dakName"]} for item in config})
    def empty_view() -> dict:
        return {
            "series": {key: {code: {} for code in funds} for key in MEASURES},
            "counts": {key: {code: {} for code in funds} for key in MEASURES},
            "statusShares": {key: {code: {} for code in funds} for key in MEASURES},
        }

    overall = empty_view()
    series, counts, status_shares = (overall[key] for key in ("series", "counts", "statusShares"))
    observed = set()

    def add(row: dict, code: str, view: dict) -> None:
        series, counts, status_shares = (view[key] for key in ("series", "counts", "statusShares"))
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
            shares = {name: api.number(row[col]) for name, col in STATUS[key].items()}
            for name, share in shares.items():
                if share is not None and not 0 <= share <= 100:
                    raise ValueError(f"Ugyldig statusandel for {code} {status_month} {name}: {share}")
            if all(share is not None for share in shares.values()):
                if abs(sum(shares.values()) - 100) > 0.35:
                    raise ValueError(f"Statusfordeling summerer ikke til 100 for {code} {status_month}")
                if value is not None and abs(shares["job"] + shares["education"] - value) > 0.25:
                    raise ValueError(f"Job og uddannelse matcher ikke hovedmålet for {code} {status_month}")
            status_shares[key][code][start_month] = shares

    for row in funds_rows:
        source_name = api.norm(row["A-kasse"])
        if source_name in {"ingen a kasse", "a kasse i alt", "i alt", "uoplyst"}:
            continue
        item = names.get(source_name)
        if item is None:
            raise ValueError(f"Ukendt a-kasse i Jobindsats: {row['A-kasse']}")
        code = item["starCode"]
        observed.add(code)
        add(row, code, overall)
    for row in total_rows:
        if api.norm(row["A-kasse"]) not in ("a kasse i alt", "i alt"):
            raise ValueError(f"Totalrækken er ikke en verificeret a-kassetotal: {row['A-kasse']}")
        add(row, "TOTAL", overall)

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
        shares = status_shares[key]["TOTAL"].get(latest_cohort)
        if not shares or not all(isinstance(value, (int, float)) for value in shares.values()):
            raise ValueError(f"Manglende officiel statusfordeling for {key} i {latest_status}")

    subgroups = {}
    for group_id, (title, hierarchy_id, level_id, column) in GROUPS.items():
        hierarchy = next((h for h in api.hierarchies(spec) if h["hierarchy_id"] == hierarchy_id), None)
        if hierarchy is None:
            raise ValueError(f"Manglende kildehierarki: {hierarchy_id}")
        level_node = next((l for l in api.levels(hierarchy) if l["level_id"] == level_id), None)
        if level_node is None:
            raise ValueError(f"Manglende kildeniveau: {level_id}")
        categories = []
        for node in api.walk(level_node):
            if isinstance(node.get("value_id"), str) and node["value_id"] != "/" and isinstance(node.get("value_name"), str) and (group_id != "region" or api.norm(node["value_name"]).startswith("region ")):
                categories.append({"id": node["value_id"], "label": node["value_name"]})
        if len(categories) != len({item["id"] for item in categories}) or not categories:
            raise ValueError(f"Ugyldige kildekategorier for {group_id}")
        by_name = {api.norm(item["label"]): item["id"] for item in categories}
        if len(by_name) != len(categories):
            raise ValueError(f"Dobbelte kategorinavne for {group_id}")
        views = {item["id"]: empty_view() for item in categories}
        period_count = min(25, len(available))
        for fund_selection in (f"level:{level}", api.total_value(fund_h)):
            rows = api.query(TABLE, spec, f"latest:{period_count}", ((fund_h, fund_selection), (hierarchy, f"level:{level_id}")))
            if not expected_columns.issubset(api.columns(rows)) or column not in api.columns(rows):
                raise ValueError(f"Uventede kolonner for {group_id}: {api.columns(rows)}")
            for row in rows:
                name = api.norm(row[column])
                if name in {"koen i alt", "alder i alt", "herkomst i alt", "hele landet", "uoplyst omraade"}:
                    continue
                category = by_name.get(name)
                if category is None:
                    raise ValueError(f"Ukendt {title.lower()} i Jobindsats: {row[column]}")
                fund_name = api.norm(row["A-kasse"])
                if fund_selection == api.total_value(fund_h):
                    if fund_name not in {"a kasse i alt", "i alt"}:
                        raise ValueError(f"Uventet totalrække i {group_id}: {row['A-kasse']}")
                    code = "TOTAL"
                else:
                    if fund_name in {"ingen a kasse", "a kasse i alt", "i alt", "uoplyst"}:
                        continue
                    item = names.get(fund_name)
                    if item is None:
                        raise ValueError(f"Ukendt a-kasse i {group_id}: {row['A-kasse']}")
                    code = item["starCode"]
                add(row, code, views[category])
        for category in categories:
            for key in MEASURES:
                if len(views[category["id"]]["series"][key]["TOTAL"]) != period_count:
                    raise ValueError(f"Ufuldstændig officiel total for {group_id}: {category['label']}")
        subgroups[group_id] = {"label": title, "categories": categories, "slices": views}

    payload = {
        "meta": {
            "state": "ok", "source": "Jobindsats.dk / STAR", "dataset": TABLE,
            "latestStatusMonth": latest_status,
            "latestCohort": {key: cohort(latest_status, n) for key, n in (("three", 3), ("six", 6))},
            "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "unit": "pct. af nyledige", "geography": "Hele landet",
            "filters": "Separate opdelinger efter region, køn, alder og herkomst; a-kasse ved nyledighed",
            "note": "Officiel totalrække og officielle a-kasserækker. Prikker/diskretionerede værdier er null. Ujusterede andele.",
        },
        "funds": funds, **overall, "subgroups": subgroups,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RM01AK: {latest_status}, {len(observed)} a-kasser, {take} måneder, {sum(len(group['categories']) for group in subgroups.values())} undergrupper, 3 mdr. {series['three']['TOTAL'][cohort(latest_status,3)]} %, 6 mdr. {series['six']['TOTAL'][cohort(latest_status,6)]} %")


if __name__ == "__main__":
    main()
