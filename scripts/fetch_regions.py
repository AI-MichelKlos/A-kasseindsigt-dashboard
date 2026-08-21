from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import statbank_api as sb
from fetch_sources import match_fund, pkey

BASE = Path(__file__).resolve().parents[1]
MAIN = BASE / "data" / "dashboard-data.json"
OUT = BASE / "data" / "regions"
HISTORY_MONTHS = 60
REGIONS = {
    "hovedstaden": "Region Hovedstaden",
    "sjaelland": "Region Sjælland",
    "syddanmark": "Region Syddanmark",
    "midtjylland": "Region Midtjylland",
    "nordjylland": "Region Nordjylland",
}


def now_iso() -> str:
    return datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds")


def status(table: str, latest: str, updated: str | None, unit: str, area: str) -> dict:
    value = {
        "state": "ok",
        "source": "Danmarks Statistik",
        "dataset": table,
        "latestPeriod": latest,
        "unit": unit,
        "area": area,
        "checkedAt": now_iso(),
    }
    if updated:
        value["sourceUpdated"] = updated
    return value


def grouped_series(rows: list[dict], fund_dim: str, time_dim: str, selected: set[str]) -> dict[str, dict]:
    grouped: dict[str, dict[str, float | int | None]] = defaultdict(dict)
    for row in rows:
        code = str(row.get(fund_dim))
        if code in selected:
            grouped[code][str(row.get(time_dim))] = row.get("value")
    result = {}
    for code in selected:
        values = grouped.get(code, {})
        labels = sorted(values, key=pkey)
        result[code] = {"labels": labels, "values": [values[p] for p in labels]}
    return result


def main() -> None:
    base = json.loads(MAIN.read_text(encoding="utf-8"))
    funds_main = base.get("funds", {})
    if not funds_main:
        raise RuntimeError("Hoveddata mangler a-kasser")
    selected_codes = list(funds_main)
    selected = set(selected_codes)
    total_code = str(base.get("meta", {}).get("totalFundCode") or "")
    if not total_code or total_code not in selected:
        raise RuntimeError("Hoveddata mangler total a-kasse")
    names = {code: str(item.get("name") or code) for code, item in funds_main.items()}

    aua = sb.tableinfo("AUA01")
    aua_f = sb.variable(aua, ["a kasse"])
    aua_t = sb.variable(aua, ["maaned", "tid"])
    aua_area = sb.variable(aua, ["omraade"])
    aua_age = sb.variable(aua, ["alder"])
    aua_sex = sb.variable(aua, ["koen"])
    aua_age_total = sb.find_value(aua_age, ["alder i alt", "i alt"])
    aua_sex_total = sb.find_value(aua_sex, ["koen i alt", "i alt"])
    aua_times = sb.all_codes(aua_t)[-HISTORY_MONTHS:]
    if not aua_times:
        raise RuntimeError("AUA01 mangler perioder")
    aua_latest = aua_times[-1]
    age_labels = sb.code_labels(aua_age)
    age_order = {code: idx for idx, code in enumerate(sb.all_codes(aua_age))}

    aup = sb.tableinfo("AUP03")
    aup_f = sb.variable(aup, ["a kasse"])
    aup_t = sb.variable(aup, ["maaned", "tid"])
    aup_area = sb.variable(aup, ["omraade"])
    aup_age = sb.variable(aup, ["alder"])
    aup_sex = sb.variable(aup, ["koen"])
    aup_age_total = sb.find_value(aup_age, ["alder i alt", "i alt"])
    aup_sex_total = sb.find_value(aup_sex, ["koen i alt", "i alt"])
    aup_times = sb.all_codes(aup_t)[-HISTORY_MONTHS:]
    if not aup_times:
        raise RuntimeError("AUP03 mangler perioder")
    aup_latest = aup_times[-1]
    aup_map = {
        code: match_fund(label, names, total_code)
        for code, label in sb.code_labels(aup_f).items()
    }

    OUT.mkdir(parents=True, exist_ok=True)

    for slug, region_name in REGIONS.items():
        aua_area_code = sb.find_value(aua_area, [region_name])
        aup_area_code = sb.find_value(aup_area, [region_name])

        member_payload = sb.data(
            "AUA01",
            {
                str(aua_area["id"]): [aua_area_code],
                str(aua_f["id"]): selected_codes,
                str(aua_age["id"]): [aua_age_total],
                str(aua_sex["id"]): [aua_sex_total],
                str(aua_t["id"]): aua_times,
            },
        )
        member_rows, _ = sb.records(member_payload)
        members = grouped_series(member_rows, str(aua_f["id"]), str(aua_t["id"]), selected)

        profile_payload = sb.data(
            "AUA01",
            {
                str(aua_area["id"]): [aua_area_code],
                str(aua_f["id"]): selected_codes,
                str(aua_age["id"]): sb.all_codes(aua_age),
                str(aua_sex["id"]): [aua_sex_total],
                str(aua_t["id"]): [aua_latest],
            },
        )
        profile_rows, _ = sb.records(profile_payload)
        profiles: dict[str, list[dict]] = defaultdict(list)
        for row in profile_rows:
            code = str(row.get(str(aua_f["id"])))
            age = str(row.get(str(aua_age["id"])))
            if code in selected and age != aua_age_total:
                profiles[code].append(
                    {"code": age, "label": age_labels.get(age, age), "value": row.get("value")}
                )
        for code in profiles:
            profiles[code].sort(key=lambda item: age_order.get(item["code"], 999))
            for item in profiles[code]:
                item.pop("code", None)

        rate_payload = sb.data(
            "AUP03",
            {
                str(aup_area["id"]): [aup_area_code],
                str(aup_age["id"]): [aup_age_total],
                str(aup_sex["id"]): [aup_sex_total],
                str(aup_f["id"]): sb.all_codes(aup_f),
                str(aup_t["id"]): aup_times,
            },
        )
        rate_rows, _ = sb.records(rate_payload)
        rate_grouped: dict[str, dict[str, float | int | None]] = defaultdict(dict)
        for row in rate_rows:
            source_code = str(row.get(str(aup_f["id"])))
            target = aup_map.get(source_code)
            if target in selected:
                rate_grouped[target][str(row.get(str(aup_t["id"])))] = row.get("value")

        regional_funds = {}
        for code in selected_codes:
            rate_values = rate_grouped.get(code, {})
            rate_labels = sorted(rate_values, key=pkey)
            regional_funds[code] = {
                "code": code,
                "name": names[code],
                "members": members.get(code, {"labels": [], "values": []}),
                "profileAge": profiles.get(code, []),
                "unemploymentRate": {
                    "labels": rate_labels,
                    "values": [rate_values[p] for p in rate_labels],
                },
            }

        output = {
            "meta": {
                "areaCode": aua_area_code,
                "areaName": region_name,
                "historyMonths": HISTORY_MONTHS,
                "updated": now_iso()[:10],
                "checkedAt": now_iso(),
                "totalFundCode": total_code,
                "sourceStatus": {
                    "AUA01": status(
                        "AUA01",
                        aua_latest,
                        aua.get("updated"),
                        "antal forsikringsaktive",
                        region_name,
                    ),
                    "AUP03": status(
                        "AUP03",
                        aup_latest,
                        aup.get("updated"),
                        "pct. fuldtidsledige af samtlige forsikrede",
                        region_name,
                    ),
                },
                "methodNotes": [
                    "Regional visning bruger Danmarks Statistiks område-dimension sammen med a-kasse.",
                    "Regional historik er begrænset til de seneste 60 måneder for at holde dashboardet let.",
                    "Kun nøgletal med verificeret kombination af region og a-kasse indgår i regional visning.",
                ],
            },
            "funds": regional_funds,
        }
        path = OUT / f"{slug}.json"
        path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(region_name, aua_latest, aup_latest, len(regional_funds), path)


if __name__ == "__main__":
    main()
