from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import jobindsats_api as ji
from fetch_sources import match_fund

BASE = Path(__file__).resolve().parents[1]
MAIN = BASE / "data" / "dashboard-data.json"
REGION_DIR = BASE / "data" / "regions"
REGIONS = {
    "hovedstaden": "Region Hovedstaden",
    "sjaelland": "Region Sjælland",
    "syddanmark": "Region Syddanmark",
    "midtjylland": "Region Midtjylland",
    "nordjylland": "Region Nordjylland",
}
_TABLES = None


def now_iso():
    return datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds")


def pkey(period):
    text = str(period or "")
    m = re.fullmatch(r"(\d{4})M(\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    q = re.fullmatch(r"(\d{4})Q0?([1-4])", text)
    if q:
        return int(q.group(1)), int(q.group(2)) * 3
    y = re.fullmatch(r"(\d{4})Y\d{2}", text)
    if y:
        return int(y.group(1)), 12
    return 0, 0


def exact_col(rows, label):
    wanted = ji.norm(label)
    return next((col for col in ji.columns(rows) if ji.norm(col) == wanted), None)


def tables():
    global _TABLES
    if _TABLES is None:
        _TABLES = ji.get("tables", {"format": "json"})
    return _TABLES


def table_for(main, key, phrases, excludes=()):
    source = main.get("meta", {}).get("sourceStatus", {}).get(key, {})
    table_id = source.get("dataset")
    if table_id:
        return str(table_id), ji.get(f"table/{table_id}", {"format": "json"})
    found = ji.find_table(tables(), phrases, excludes)
    table_id = str(found["table_id"])
    return table_id, ji.get(f"table/{table_id}", {"format": "json"})


def region_breakdown(spec, region_name):
    wanted = ji.norm(region_name)
    short = wanted.replace("region ", "").strip()
    candidates = []
    for hierarchy in ji.hierarchies(spec):
        hid = str(hierarchy.get("hierarchy_id") or "")
        htext = ji.norm(json.dumps(hierarchy, ensure_ascii=False))
        for value_id, text in ji.hierarchy_values(hierarchy):
            score = 0
            if wanted and wanted in text:
                score += 1000
            if short and short in text:
                score += 700
            if "region" in ji.norm(hid) or "region" in htext:
                score += 150
            if score:
                candidates.append((score, len(text), hierarchy, value_id))
    if not candidates:
        raise RuntimeError(f"Jobindsats-tabellen har ikke regional værdi for {region_name}")
    candidates.sort(reverse=True, key=lambda x: (x[0], x[1]))
    return candidates[0][2], candidates[0][3]


def fund_setup(spec):
    fund = ji.find_hierarchy(spec, ["a kasse", "akasse"])
    level = ji.fund_level(fund)
    return fund, f"level:{level}" if level else "*"


def query_up_to(table, spec, limit, breakdowns):
    try:
        return ji.query(table, spec, f"latest:{limit}", breakdowns)
    except RuntimeError as exc:
        matches = [int(x) for x in re.findall(r"only (\d+) periods are available", str(exc), re.IGNORECASE)]
        if not matches:
            raise
        available = max(matches)
        return ji.query(table, spec, f"latest:{min(limit, available)}", breakdowns)


def all_fund_rows(table, spec, limit, region_name, extras=()):
    fund, selection = fund_setup(spec)
    geo, region_value = region_breakdown(spec, region_name)
    base = ((geo, region_value), (fund, selection), *extras)
    rows = query_up_to(table, spec, limit, base)
    total = query_up_to(table, spec, limit, ((geo, region_value), (fund, ji.total_value(fund)), *extras))
    for row in total:
        row["_dak_force_total"] = True
    rows.extend(total)
    return rows


def fund_code(row, fcol, data):
    if row.get("_dak_force_total"):
        return data["meta"]["totalFundCode"]
    names = {code: item.get("name", code) for code, item in data["funds"].items()}
    return match_fund(row.get(fcol), names, data["meta"]["totalFundCode"])


def put_status(data, key, table, latest, unit):
    data["meta"].setdefault("sourceStatus", {})[key] = {
        "state": "ok",
        "source": "Jobindsats.dk / STAR",
        "dataset": table,
        "latestPeriod": latest,
        "unit": unit,
        "area": data["meta"]["areaName"],
        "checkedAt": now_iso(),
    }


def store_timeseries(data, rows, module, measure_col, value_key="persons"):
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data)
        period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = ji.number(row.get(measure_col))
    if not grouped:
        raise RuntimeError(f"Ingen regionale a-kassedata for {module}")
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})[module] = {
            "labels": labels,
            value_key: [values[p] for p in labels],
        }
    return max((p for values in grouped.values() for p in values), key=pkey)


def dagpenge(main, data, region):
    table, spec = table_for(main, "jobDagpenge", ["a dagpenge", "antal personer og fuldtidspersoner"], ["sygedagpenge"])
    rows = all_fund_rows(table, spec, 60, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    persons = ji.best_col(rows, ["antal personer"], ["fuldtid", "andel", "pct"])
    fulltime = ji.best_col(rows, ["fuldtid"], ["andel", "pct"])
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data); period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = (ji.number(row.get(persons)), ji.number(row.get(fulltime)))
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})["dagpenge"] = {
            "labels": labels,
            "persons": [values[p][0] for p in labels],
            "fulltime": [values[p][1] for p in labels],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobDagpenge", table, latest, "personer og fuldtidspersoner")


def graduates(main, data, region):
    table, spec = table_for(main, "jobDimittend", ["antal dimittendledige personer"])
    rows = all_fund_rows(table, spec, 60, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    share = ji.best_col(rows, ["andel", "dimittend"], ["fuldtid"])
    count = ji.best_col(rows, ["antal", "dimittend", "personer"], ["andel", "pct", "fuldtid"])
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data); period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = (ji.number(row.get(share)), ji.number(row.get(count)))
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})["graduates"] = {
            "labels": labels,
            "share": [values[p][0] for p in labels],
            "persons": [values[p][1] for p in labels],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobDimittend", table, latest, "personer og pct.")


def talk_forms(main, data, region):
    table = "smt02"; spec = ji.get(f"table/{table}", {"format": "json"})
    rows = all_fund_rows(table, spec, 60, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    cols = {
        "total": exact_col(rows, "Samtaler i alt"), "physical": exact_col(rows, "Fysiske samtaler"),
        "phone": exact_col(rows, "Telefoniske samtaler"), "video": exact_col(rows, "Videosamtaler"),
        "other": exact_col(rows, "Anden kontakt"),
    }
    if any(v is None for v in cols.values()):
        raise RuntimeError("Samtaleformer mangler forventede kolonner")
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data); period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = {key: ji.number(row.get(col)) for key, col in cols.items()}
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})["talkForms"] = {
            "labels": labels, **{key: [values[p][key] for p in labels] for key in cols}
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobTalkForms", table, latest, "antal jobsamtaler efter samtaleform")


def afterlon(main, data, region):
    table = "y28a02"; spec = ji.get(f"table/{table}", {"format": "json"})
    rows = all_fund_rows(table, spec, 60, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    persons = exact_col(rows, "Antal personer på efterløn")
    paid = exact_col(rows, "Antal personer med udbetalt efterløn")
    fulltime = exact_col(rows, "Antal fuldtidspersoner med udbetalt efterløn")
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data); period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = {"persons": ji.number(row.get(persons)), "paidPersons": ji.number(row.get(paid)), "fulltime": ji.number(row.get(fulltime))}
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})["afterlon"] = {
            "labels": labels,
            "persons": [values[p]["persons"] for p in labels],
            "paidPersons": [values[p]["paidPersons"] for p in labels],
            "fulltime": [values[p]["fulltime"] for p in labels],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobAfterlon", table, latest, "personer og fuldtidspersoner på efterløn")


def afterlon_contrib(main, data, region):
    table = "y28a15"; spec = ji.get(f"table/{table}", {"format": "json"})
    rows = all_fund_rows(table, spec, 5, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    count = exact_col(rows, "Antal efterlønsbidragsbetalere")
    share = exact_col(rows, "Andel efterlønsbidragsbetalere blandt dagpengeforsikrede")
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data); period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = {"count": ji.number(row.get(count)), "share": ji.number(row.get(share))}
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})["afterlonContrib"] = {
            "labels": labels, "count": [values[p]["count"] for p in labels], "share": [values[p]["share"] for p in labels]
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobAfterlonContrib", table, latest, "antal og pct. efterlønsbidragsbetalere")


def long_term(main, data, region):
    table, spec = table_for(main, "jobLongTerm", ["antal langtidsledige personer"], ["unge", "udenlandsk"])
    rows = all_fund_rows(table, spec, 60, region)
    vcol = exact_col(rows, "Antal langtidsledige personer") or ji.best_col(rows, ["antal", "langtidsledige", "personer"], ["fuldtid", "andel", "brutto"])
    latest = store_timeseries(data, rows, "longTerm", vcol, "persons")
    put_status(data, "jobLongTerm", table, latest, "antal langtidsledige personer på a-dagpenge")


def exhausted_rights(main, data, region):
    table, spec = table_for(main, "jobExhaustedRights", ["opbrugt dagpengeret", "dimittender", "oevrige ledige"], ["efterfoelgende arbejdsmarkedsstatus"])
    try:
        rows = all_fund_rows(table, spec, 60, region)
    except RuntimeError as exc:
        data["meta"].setdefault("unsupportedModules", []).append("exhaustedRights")
        data["meta"].setdefault("sourceStatus", {})["jobExhaustedRights"] = {
            "state": "unsupported", "source": "Jobindsats.dk / STAR", "dataset": table,
            "area": data["meta"]["areaName"], "error": str(exc)[:300], "checkedAt": now_iso(),
        }
        return
    vcol = exact_col(rows, "Antal personer med opbrugt dagpengeret") or ji.best_col(rows, ["antal", "personer", "opbrugt", "dagpengeret"], ["andel", "pct"])
    latest = store_timeseries(data, rows, "exhaustedRights", vcol, "persons")
    put_status(data, "jobExhaustedRights", table, latest, "antal personer med opbrugt dagpengeret")


def sanctions(main, data, region):
    table = "y01h01"; spec = ji.get(f"table/{table}", {"format": "json"})
    rows = all_fund_rows(table, spec, 20, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    cols = {
        "total": exact_col(rows, "Antal sanktioner i alt"),
        "excluded": exact_col(rows, "Antal sanktioner fordelt på type: Udelukkes fra dagpenge i en periode"),
        "quarantine": exact_col(rows, "Antal sanktioner fordelt på type: Karantæne (selvforskyldt ledighed)"),
        "repeat": exact_col(rows, "Antal sanktioner fordelt på type: Gentagelsesvirkning (arbejdskrav)"),
        "other": exact_col(rows, "Antal sanktioner fordelt på type: Andre (arbejdskrav)"),
        "share": exact_col(rows, "Andel sanktionerede ledige"),
        "avg": exact_col(rows, "Gnsn. antal sanktioner pr. sanktioneret ledig"),
    }
    if any(v is None for v in cols.values()):
        raise RuntimeError("Sanktioner mangler forventede kolonner")
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row, fcol, data); period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = {key: ji.number(row.get(col)) for key, col in cols.items()}
    types = [("Udelukkelse fra dagpenge i en periode", "excluded"), ("Karantæne (selvforskyldt ledighed)", "quarantine"), ("Gentagelsesvirkning (arbejdskrav)", "repeat"), ("Andre arbejdskrav", "other")]
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code].setdefault("jobindsats", {})["sanctions"] = {
            "labels": labels,
            "total": [values[p]["total"] for p in labels], "shareSanctioned": [values[p]["share"] for p in labels],
            "avgPerSanctioned": [values[p]["avg"] for p in labels],
            "types": [{"label": label, "values": [values[p][key] for p in labels]} for label, key in types],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobSanctions", table, latest, "antal, pct. sanktionerede og gennemsnit")


def consumption(main, data, region):
    table = "y01a12"; spec = ji.get(f"table/{table}", {"format": "json"})
    dp = ji.find_hierarchy(spec, ["forbrug", "dagpengeperioden"])
    level = ji.levels(dp)[0].get("level_id")
    rows = all_fund_rows(table, spec, 1, region, ((dp, f"level:{level}"),))
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    ccol = exact_col(rows, "Forbrug af dagpengeperioden")
    vcol = exact_col(rows, "Antal personer med forbrug af dagpengeperioden")
    latest = max((str(r.get(pcol)) for r in rows if r.get(pcol)), key=pkey)
    bands = [("0-3 mdr.", 0, 3), ("3-6 mdr.", 3, 6), ("6-12 mdr.", 6, 12), ("12-18 mdr.", 12, 18), ("18+ mdr.", 18, 999)]
    grouped = defaultdict(lambda: defaultdict(float))
    for row in rows:
        if str(row.get(pcol)) != latest: continue
        code = fund_code(row, fcol, data); label = str(row.get(ccol) or ""); value = ji.number(row.get(vcol))
        m = re.match(r"\s*(\d+)\s*[-–]", label)
        if code not in data["funds"] or value is None or not m: continue
        start = int(m.group(1))
        for band, lo, hi in bands:
            if lo <= start < hi:
                grouped[code][band] += float(value); break
    for code, values in grouped.items():
        data["funds"][code].setdefault("jobindsats", {})["benefitConsumption"] = {
            "period": latest, "items": [{"label": band, "value": round(values.get(band, 0), 6)} for band, _, _ in bands]
        }
    put_status(data, "jobDagpengeforbrug", table, latest, "personer efter forbrugt dagpengeperiode")


def survival(main, data, region):
    table = "y01b01"; spec = ji.get(f"table/{table}", {"format": "json"})
    rows = all_fund_rows(table, spec, 8, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    week_cols = []
    for col in ji.columns(rows):
        n = ji.norm(col)
        if "overlevelseskurve u tilbagefald til den valgte ydelse" in n:
            m = re.search(r"(\d+) uger", n)
            if m: week_cols.append((int(m.group(1)), col))
    week_cols.sort()
    if not week_cols: raise RuntimeError("Overlevelseskurve mangler ugekolonner")
    periods = sorted({str(r.get(pcol)) for r in rows if r.get(pcol)}, key=pkey, reverse=True)
    chosen = next((p for p in periods if any(ji.number(r.get(week_cols[-1][1])) is not None for r in rows if str(r.get(pcol)) == p)), None)
    if not chosen: raise RuntimeError("Ingen moden regional overlevelsesperiode")
    for row in rows:
        if str(row.get(pcol)) != chosen: continue
        code = fund_code(row, fcol, data)
        if code not in data["funds"]: continue
        items = [{"label": f"{week} uger", "value": ji.number(row.get(col))} for week, col in week_cols]
        items = [item for item in items if item["value"] is not None]
        if items: data["funds"][code].setdefault("jobindsats", {})["survival"] = {"period": chosen, "items": items}
    put_status(data, "jobOverlevelse", table, chosen, "pct. fortsat på dagpenge uden tilbagefald")


def status_after(main, data, region):
    table = "y01b15"; spec = ji.get(f"table/{table}", {"format": "json"})
    status_h = ji.find_hierarchy(spec, ["arbejdsmarkedsstatus"]); level = ji.levels(status_h)[0].get("level_id")
    rows = all_fund_rows(table, spec, 8, region, ((status_h, f"level:{level}"),))
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    scol = exact_col(rows, "Arbejdsmarkedsstatus") or ji.best_col(rows, ["arbejdsmarkedsstatus"], distinct=True)
    vcol = exact_col(rows, "Status 3 mdr. efter afsluttet forløb, pct.")
    periods = sorted({str(r.get(pcol)) for r in rows if r.get(pcol)}, key=pkey, reverse=True)
    chosen = next((p for p in periods if any(ji.number(r.get(vcol)) is not None and ji.norm(r.get(scol)) != "i alt" for r in rows if str(r.get(pcol)) == p)), None)
    if not chosen: raise RuntimeError("Ingen regional periode med 3-måneders status")
    grouped = defaultdict(list)
    for row in rows:
        if str(row.get(pcol)) != chosen: continue
        code = fund_code(row, fcol, data); label = str(row.get(scol) or "").strip(); value = ji.number(row.get(vcol))
        if code in data["funds"] and value is not None and ji.norm(label) != "i alt": grouped[code].append({"label": label, "value": value})
    for code, items in grouped.items():
        items.sort(key=lambda x: x["value"], reverse=True)
        data["funds"][code].setdefault("jobindsats", {})["statusAfter3m"] = {"period": chosen, "items": items}
    put_status(data, "jobStatusAfter", table, chosen, "pct. efter arbejdsmarkedsstatus 3 mdr. efter afsluttet forløb")


def completed_duration(main, data, region):
    table, spec = table_for(main, "jobCompletedDuration", ["antal og varighed af afsluttede forloeb", "a dagpenge"], ["aktiveringsforloeb", "kontanthjaelp", "sygedagpenge", "fleksjob"])
    rows = all_fund_rows(table, spec, 1, region)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    duration_cols = []
    for col in ji.columns(rows):
        n = ji.norm(col)
        if "antal" in n and "afsluttede" in n and "forloeb" in n and "varighed" in n and "gnsn" not in n and "gennemsnit" not in n:
            label = str(col).rsplit(":", 1)[-1].strip() if ":" in str(col) else str(col)
            if ji.norm(label) not in {"i alt", "total"}: duration_cols.append((col, label))
    avg_cols = [c for c in ji.columns(rows) if ("gnsn" in ji.norm(c) or "gennemsnit" in ji.norm(c)) and "varighed" in ji.norm(c)]
    if not duration_cols: raise RuntimeError("Regional varighed mangler kategorier")
    latest = max((str(r.get(pcol)) for r in rows if r.get(pcol)), key=pkey)
    for row in rows:
        if str(row.get(pcol)) != latest: continue
        code = fund_code(row, fcol, data)
        if code not in data["funds"]: continue
        items = [{"label": label, "value": ji.number(row.get(col))} for col, label in duration_cols]
        items = [item for item in items if item["value"] is not None]
        avg = ji.number(row.get(avg_cols[0])) if avg_cols else None
        if items: data["funds"][code].setdefault("jobindsats", {})["completedDuration"] = {"period": latest, "items": items, "averageWeeks": avg}
    put_status(data, "jobCompletedDuration", table, latest, "afsluttede forløb efter varighed")


def process_region(main, slug, region_name):
    path = REGION_DIR / f"{slug}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for fund in data.get("funds", {}).values():
        fund["jobindsats"] = {}
    jobs = [
        ("jobDagpenge", dagpenge), ("jobDimittend", graduates), ("jobTalkForms", talk_forms),
        ("jobAfterlon", afterlon), ("jobAfterlonContrib", afterlon_contrib), ("jobLongTerm", long_term),
        ("jobExhaustedRights", exhausted_rights), ("jobSanctions", sanctions),
        ("jobDagpengeforbrug", consumption), ("jobOverlevelse", survival),
        ("jobStatusAfter", status_after), ("jobCompletedDuration", completed_duration),
    ]
    required = {key for key, _ in jobs if key != "jobExhaustedRights"}
    failures = []
    for key, func in jobs:
        try:
            func(main, data, region_name)
            state = data["meta"].get("sourceStatus", {}).get(key, {}).get("state")
            print(region_name, key, state or "ok")
        except Exception as exc:
            failures.append((key, str(exc)))
            data["meta"].setdefault("sourceStatus", {})[key] = {
                "state": "failed", "source": "Jobindsats.dk / STAR", "dataset": main.get("meta", {}).get("sourceStatus", {}).get(key, {}).get("dataset"),
                "area": region_name, "error": str(exc)[:500], "checkedAt": now_iso(),
            }
            print(region_name, key, "failed", exc)
    failed_required = [key for key, _ in failures if key in required]
    if failed_required:
        raise RuntimeError(region_name + " mangler regionale Jobindsats-moduler: " + ", ".join(failed_required))
    data["meta"]["checkedAt"] = now_iso()
    data["meta"]["methodNotes"] = [
        "Regional visning kombinerer region og a-kasse i de officielle DST- og Jobindsats-kilder.",
        "Regional historik er begrænset til de seneste 60 måneder.",
        "Moduler uden geografidimension i den konkrete Jobindsats-måling markeres som ikke understøttet og vises ikke regionalt.",
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    main_data = json.loads(MAIN.read_text(encoding="utf-8"))
    for slug, region_name in REGIONS.items():
        process_region(main_data, slug, region_name)
    print("OK: regionale Jobindsats-data hentet")


if __name__ == "__main__":
    main()
