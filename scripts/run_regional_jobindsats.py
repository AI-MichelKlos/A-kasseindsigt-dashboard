from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import fetch_jobindsats_regions as base
import jobindsats_api as ji
from fetch_sources import match_fund

BASE = Path(__file__).resolve().parents[1]
REGION_DIR = BASE / "data" / "regions"
MAIN = BASE / "data" / "dashboard-data.json"

MUNICIPALITIES = {
    "hovedstaden": [
        "Albertslund", "Allerød", "Ballerup", "Bornholm", "Brøndby", "Dragør", "Egedal", "Fredensborg",
        "Frederiksberg", "Frederikssund", "Furesø", "Gentofte", "Gladsaxe", "Glostrup", "Gribskov", "Halsnæs",
        "Helsingør", "Herlev", "Hillerød", "Hvidovre", "Høje-Taastrup", "Hørsholm", "Ishøj", "København",
        "Lyngby-Taarbæk", "Rudersdal", "Rødovre", "Tårnby", "Vallensbæk",
    ],
    "sjaelland": [
        "Faxe", "Greve", "Guldborgsund", "Holbæk", "Kalundborg", "Køge", "Lejre", "Lolland", "Næstved",
        "Odsherred", "Ringsted", "Roskilde", "Slagelse", "Solrød", "Sorø", "Stevns", "Vordingborg",
    ],
    "syddanmark": [
        "Assens", "Billund", "Esbjerg", "Fanø", "Fredericia", "Faaborg-Midtfyn", "Haderslev", "Kerteminde",
        "Kolding", "Langeland", "Middelfart", "Nordfyns", "Nyborg", "Odense", "Svendborg", "Sønderborg",
        "Tønder", "Varde", "Vejen", "Vejle", "Ærø", "Aabenraa",
    ],
    "midtjylland": [
        "Aarhus", "Favrskov", "Hedensted", "Herning", "Holstebro", "Horsens", "Ikast-Brande", "Lemvig",
        "Norddjurs", "Odder", "Randers", "Ringkøbing-Skjern", "Samsø", "Silkeborg", "Skanderborg", "Skive",
        "Struer", "Syddjurs", "Viborg",
    ],
    "nordjylland": [
        "Aalborg", "Brønderslev", "Frederikshavn", "Hjørring", "Jammerbugt", "Læsø", "Mariagerfjord", "Morsø",
        "Rebild", "Thisted", "Vesthimmerlands",
    ],
}


def clean_place(value):
    text = ji.norm(value)
    for word in ("kommune", "bopaelskommune"):
        text = text.replace(word, " ")
    return " ".join(text.split())


def skip_direct_talk(main, data, region):
    table = "smt02"
    data["meta"].setdefault("sourceStatus", {})["jobTalkForms"] = {
        "state": "pending",
        "source": "Jobindsats.dk / STAR",
        "dataset": table,
        "area": region,
        "checkedAt": base.now_iso(),
        "note": "Aggregeres efterfølgende fra bopælskommuner til region.",
    }


def query_all_municipal_talks():
    table = "smt02"
    spec = ji.get(f"table/{table}", {"format": "json"})
    fund, fund_selection = base.fund_setup(spec)
    municipality = ji.find_hierarchy(spec, ["kommune"], ("_nykom",))
    levels = ji.levels(municipality)
    candidates = []
    for level in levels:
        level_id = str(level.get("level_id") or "")
        text = ji.norm(json.dumps(level, ensure_ascii=False))
        count = len(ji.hierarchy_values(level))
        score = (500 if "kommune" in text else 0) + (300 if 90 <= count <= 110 else 0)
        candidates.append((score, count, level_id))
    candidates.sort(reverse=True)
    if not candidates or candidates[0][0] <= 0:
        raise RuntimeError("Kunne ikke identificere kommuneniveau i smt02")
    municipality_selection = f"level:{candidates[0][2]}"
    return table, spec, base.query_up_to(table, spec, 60, ((municipality, municipality_selection), (fund, fund_selection)))


def aggregate_talks(main_data):
    table, spec, rows = query_all_municipal_talks()
    if not rows:
        raise RuntimeError("Samtaleformer gav ingen kommunedata")
    fcol = base.exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = base.exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    ccol = base.exact_col(rows, "Kommune") or ji.best_col(rows, ["kommune"], distinct=True)
    cols = {
        "total": base.exact_col(rows, "Samtaler i alt"),
        "physical": base.exact_col(rows, "Fysiske samtaler"),
        "phone": base.exact_col(rows, "Telefoniske samtaler"),
        "video": base.exact_col(rows, "Videosamtaler"),
        "other": base.exact_col(rows, "Anden kontakt"),
    }
    if any(value is None for value in cols.values()):
        raise RuntimeError(f"Samtaleformer mangler kolonner: {ji.columns(rows)}")

    municipality_to_region = {}
    for slug, names in MUNICIPALITIES.items():
        for name in names:
            municipality_to_region[clean_place(name)] = slug

    unmatched = sorted({clean_place(row.get(ccol)) for row in rows if clean_place(row.get(ccol)) not in municipality_to_region})
    unmatched = [name for name in unmatched if name and name not in {"hele landet", "i alt"}]
    if unmatched:
        raise RuntimeError("Ukendte kommuner i samtaledata: " + ", ".join(unmatched[:20]))

    regional_data = {slug: json.loads((REGION_DIR / f"{slug}.json").read_text(encoding="utf-8")) for slug in MUNICIPALITIES}
    names = {code: item.get("name", code) for code, item in main_data["funds"].items()}
    total_code = main_data["meta"]["totalFundCode"]
    grouped = {slug: defaultdict(lambda: defaultdict(lambda: defaultdict(float))) for slug in MUNICIPALITIES}

    for row in rows:
        slug = municipality_to_region.get(clean_place(row.get(ccol)))
        if not slug:
            continue
        code = match_fund(row.get(fcol), names, total_code)
        period = str(row.get(pcol) or "")
        if code not in main_data["funds"] or not period:
            continue
        for key, col in cols.items():
            value = ji.number(row.get(col))
            if value is not None:
                grouped[slug][code][period][key] += float(value)

    for slug, data in regional_data.items():
        fund_group = grouped[slug]
        for code in main_data["funds"]:
            values = fund_group.get(code, {})
            labels = sorted(values, key=base.pkey)
            if not labels:
                continue
            block = {"labels": labels}
            for key in cols:
                block[key] = [round(values[p].get(key, 0), 6) for p in labels]
            data["funds"][code].setdefault("jobindsats", {})["talkForms"] = block

        # Totalen beregnes som summen af de konkrete a-kasser, fordi kommuneniveau-kaldet bruger a-kasseniveauet.
        concrete = [code for code in main_data["funds"] if code != total_code]
        periods = sorted({p for code in concrete for p in fund_group.get(code, {})}, key=base.pkey)
        if periods:
            total_block = {"labels": periods}
            for key in cols:
                total_block[key] = [round(sum(fund_group.get(code, {}).get(p, {}).get(key, 0) for code in concrete), 6) for p in periods]
            data["funds"][total_code].setdefault("jobindsats", {})["talkForms"] = total_block

        total = data["funds"][total_code].get("jobindsats", {}).get("talkForms", {})
        labels = total.get("labels", [])
        if not labels:
            raise RuntimeError(f"{data['meta']['areaName']}: samtaleformer mangler total")
        data["meta"]["sourceStatus"]["jobTalkForms"] = {
            "state": "ok",
            "source": "Jobindsats.dk / STAR",
            "dataset": table,
            "latestPeriod": labels[-1],
            "unit": "antal jobsamtaler efter samtaleform",
            "area": data["meta"]["areaName"],
            "checkedAt": base.now_iso(),
            "note": "Regionstal er summeret fra Jobindsats' bopælskommuner.",
        }
        (REGION_DIR / f"{slug}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(data["meta"]["areaName"], "jobTalkForms ok", labels[-1])


def main():
    main_data = json.loads(MAIN.read_text(encoding="utf-8"))
    original = base.talk_forms
    base.talk_forms = skip_direct_talk
    try:
        for slug, region_name in base.REGIONS.items():
            base.process_region(main_data, slug, region_name)
    finally:
        base.talk_forms = original
    aggregate_talks(main_data)
    print("OK: regionale Jobindsats-data inkl. samtaleformer hentet")


if __name__ == "__main__":
    main()
