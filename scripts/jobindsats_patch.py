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
OUT = BASE / "data" / "dashboard-data.json"
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
    return 0, 0


def exact_col(rows, label):
    wanted = ji.norm(label)
    return next((col for col in ji.columns(rows) if ji.norm(col) == wanted), None)


def tables():
    global _TABLES
    if _TABLES is None:
        _TABLES = ji.get("tables", {"format": "json"})
    return _TABLES


def discover(phrases, excludes=()):
    found = ji.find_table(tables(), phrases, excludes)
    table_id = str(found["table_id"])
    spec = ji.get(f"table/{table_id}", {"format": "json"})
    return table_id, spec


def setup(table_id):
    spec = ji.get(f"table/{table_id}", {"format": "json"})
    fund = ji.find_hierarchy(spec, ["a kasse", "akasse"])
    level = ji.fund_level(fund)
    return spec, fund, f"level:{level}" if level else "*"


def setup_spec(spec):
    fund = ji.find_hierarchy(spec, ["a kasse", "akasse"])
    level = ji.fund_level(fund)
    return fund, f"level:{level}" if level else "*"


def fund_code(label, data):
    names = {code: item.get("name", code) for code, item in data["funds"].items()}
    return match_fund(label, names, data["meta"]["totalFundCode"])


def put_status(data, key, dataset, latest, unit, note=None):
    value = {
        "state": "ok",
        "source": "Jobindsats.dk / STAR",
        "dataset": dataset,
        "latestPeriod": latest,
        "unit": unit,
        "checkedAt": now_iso(),
    }
    if note:
        value["note"] = note
    data["meta"]["sourceStatus"][key] = value
    data["meta"].setdefault("jobindsatsTables", {})[key] = dataset


def store_timeseries(data, rows, module, measure_col, value_key="persons"):
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row.get(fcol), data)
        period = str(row.get(pcol) or "")
        value = ji.number(row.get(measure_col))
        if code in data["funds"] and period:
            grouped[code][period] = value
    if not grouped:
        raise RuntimeError(f"Ingen a-kassedata fundet for {module}")
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code]["jobindsats"][module] = {
            "labels": labels,
            value_key: [values[p] for p in labels],
        }
    return max((p for values in grouped.values() for p in values), key=pkey)


def early_talks(data):
    table = "y30e22ak"
    spec, fund_h, selection = setup(table)
    rows = ji.query(table, spec, "latest:28", ((fund_h, selection),))
    vcol = exact_col(rows, "Andel personer fordelt på antal afholdte jobsamtaler : 3+")
    if not vcol:
        raise RuntimeError("Kolonnen for andel med 3+ jobsamtaler mangler")
    latest = store_timeseries(data, rows, "earlyTalks", vcol, "share")
    put_status(
        data,
        "jobEarlyTalks",
        table,
        latest,
        "pct. med mindst 3 jobsamtaler",
        "Populationen er personer, der i måneden afslutter a-kassens kontaktforløb med overgang til jobcenter.",
    )


def long_term(data):
    table, spec = discover(["antal langtidsledige personer"], ["unge", "udenlandsk"])
    fund_h, selection = setup_spec(spec)
    # A-kasse er selve fordelingen i denne tabel. Jobindsats API'et eksponerer
    # ikke ledighedstype som et separat hierarki her, så a-dagpengepopulationen
    # identificeres gennem a-kassefordelingen frem for et ekstra filter.
    rows = ji.query(table, spec, "latest:120", ((fund_h, selection),))
    vcol = exact_col(rows, "Antal langtidsledige personer") or ji.best_col(
        rows,
        ["antal", "langtidsledige", "personer"],
        ["fuldtid", "andel", "brutto"],
    )
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    seen = {}
    for row in rows:
        code = fund_code(row.get(fcol), data)
        period = str(row.get(pcol) or "")
        value = ji.number(row.get(vcol))
        if code not in data["funds"] or not period:
            continue
        key = (code, period)
        if key in seen and seen[key] != value:
            raise RuntimeError(
                "Langtidsledighed gav flere forskellige værdier for samme a-kasse og periode; "
                f"kolonner: {ji.columns(rows)}"
            )
        seen[key] = value
    latest = store_timeseries(data, rows, "longTerm", vcol, "persons")
    put_status(
        data,
        "jobLongTerm",
        table,
        latest,
        "antal langtidsledige personer på a-dagpenge",
        "Langtidsledige har været ledige eller aktiverede mindst 80 pct. af de seneste 12 måneder.",
    )


def exhausted_rights(data):
    table, spec = discover(
        ["opbrugt dagpengeret", "dimittender", "oevrige ledige"],
        ["efterfoelgende arbejdsmarkedsstatus"],
    )
    fund_h, selection = setup_spec(spec)
    rows = ji.query(table, spec, "latest:120", ((fund_h, selection),))
    vcol = exact_col(rows, "Antal personer med opbrugt dagpengeret") or ji.best_col(
        rows,
        ["antal", "personer", "opbrugt", "dagpengeret"],
        ["andel", "pct", "beskaeftigelse", "uddannelse"],
    )
    latest = store_timeseries(data, rows, "exhaustedRights", vcol, "persons")
    put_status(
        data,
        "jobExhaustedRights",
        table,
        latest,
        "antal personer med opbrugt dagpengeret",
        "A-kassefordelingen følger seneste udbetalende a-kasse.",
    )



def sanctions(data):
    table = "y01h01"
    spec, fund_h, selection = setup(table)

    def fetch_periods(fund_selection):
        try:
            return ji.query(table, spec, "latest:40", ((fund_h, fund_selection),))
        except RuntimeError as exc:
            # Tabellen starter i 2019 og har derfor endnu under 40 kvartaler.
            # Jobindsats afviser latest:N, hvis N er større end den tilgængelige historik.
            match = re.search(r"only (\d+) periods are available", str(exc), re.IGNORECASE)
            if not match:
                raise
            available = min(40, int(match.group(1)))
            return ji.query(table, spec, f"latest:{available}", ((fund_h, fund_selection),))

    # Niveauvalget returnerer de enkelte a-kasser, men ikke totalrækken.
    # Hent derfor A-kasse i alt særskilt fra samme officielle tabel.
    rows = fetch_periods(selection)
    total_rows = fetch_periods(ji.total_value(fund_h))
    for row in total_rows:
        row["_dak_force_total"] = True
    rows.extend(total_rows)
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
    missing = [key for key, col in cols.items() if not col]
    if missing:
        raise RuntimeError(f"Sanktionstabellen mangler kolonner: {missing}; har {ji.columns(rows)}")

    grouped = defaultdict(dict)
    for row in rows:
        code = data["meta"]["totalFundCode"] if row.get("_dak_force_total") else fund_code(row.get(fcol), data)
        period = str(row.get(pcol) or "")
        if code not in data["funds"] or not period:
            continue
        grouped[code][period] = {
            "total": ji.number(row.get(cols["total"])),
            "share": ji.number(row.get(cols["share"])),
            "avg": ji.number(row.get(cols["avg"])),
            "excluded": ji.number(row.get(cols["excluded"])),
            "quarantine": ji.number(row.get(cols["quarantine"])),
            "repeat": ji.number(row.get(cols["repeat"])),
            "other": ji.number(row.get(cols["other"])),
        }
    if not grouped:
        raise RuntimeError("Rådighedssanktioner gav ingen a-kassedata")

    type_defs = [
        ("Udelukkelse fra dagpenge i en periode", "excluded"),
        ("Karantæne (selvforskyldt ledighed)", "quarantine"),
        ("Gentagelsesvirkning (arbejdskrav)", "repeat"),
        ("Andre arbejdskrav", "other"),
    ]
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code]["jobindsats"]["sanctions"] = {
            "labels": labels,
            "total": [values[p]["total"] for p in labels],
            "shareSanctioned": [values[p]["share"] for p in labels],
            "avgPerSanctioned": [values[p]["avg"] for p in labels],
            "types": [
                {"label": label, "values": [values[p][key] for p in labels]}
                for label, key in type_defs
            ],
        }

    latest = max((period for values in grouped.values() for period in values), key=pkey)
    total_code = data["meta"]["totalFundCode"]
    total_block = data["funds"].get(total_code, {}).get("jobindsats", {}).get("sanctions", {})
    if not total_block.get("labels") or total_block["labels"][-1] != latest:
        raise RuntimeError("Sanktioner mangler seneste kvartal for I alt")
    if total_block.get("total", [None])[-1] is None:
        raise RuntimeError("Seneste samlede antal rådighedssanktioner er tomt")

    put_status(
        data,
        "jobSanctions",
        table,
        latest,
        "antal rådighedssanktioner, pct. sanktionerede og gennemsnit pr. sanktioneret ledig",
        "Databrud: 2019-2020 omfatter kun bestemte sager rejst via jobcentrene; fra 1. kvt. 2021 indgår også sager rejst af a-kasserne selv.",
    )

def consumption(data):
    table = "y01a12"
    spec, fund_h, selection = setup(table)
    dp = ji.find_hierarchy(spec, ["forbrug", "dagpengeperioden"])
    level = ji.levels(dp)[0].get("level_id")
    rows = ji.query(table, spec, "latest:1", ((fund_h, selection), (dp, f"level:{level}")))
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode")
    ccol = exact_col(rows, "Forbrug af dagpengeperioden")
    vcol = exact_col(rows, "Antal personer med forbrug af dagpengeperioden")
    if not pcol or not ccol or not vcol:
        raise RuntimeError(f"Uventede kolonner i dagpengeforbrug: {ji.columns(rows)}")
    latest = max((str(r.get(pcol)) for r in rows if r.get(pcol)), key=pkey)
    bands = [("0-3 mdr.", 0, 3), ("3-6 mdr.", 3, 6), ("6-12 mdr.", 6, 12), ("12-18 mdr.", 12, 18), ("18+ mdr.", 18, 999)]
    grouped = defaultdict(lambda: defaultdict(float))
    for row in rows:
        if str(row.get(pcol)) != latest:
            continue
        code = fund_code(row.get(fcol), data)
        label = str(row.get(ccol) or "")
        value = ji.number(row.get(vcol))
        m = re.match(r"\s*(\d+)\s*[-–]", label)
        if code not in data["funds"] or value is None or not m:
            continue
        start = int(m.group(1))
        for band, lo, hi in bands:
            if lo <= start < hi:
                grouped[code][band] += float(value)
                break
    if not grouped:
        raise RuntimeError("Dagpengeforbrug gav ingen fordelte a-kassedata")
    for code, values in grouped.items():
        data["funds"][code]["jobindsats"]["benefitConsumption"] = {
            "period": latest,
            "items": [{"label": band, "value": round(values.get(band, 0), 6)} for band, _, _ in bands],
        }
    put_status(data, "jobDagpengeforbrug", table, latest, "personer efter forbrugt dagpengeperiode")


def survival(data):
    table = "y01b01"
    spec, fund_h, selection = setup(table)
    rows = ji.query(table, spec, "latest:8", ((fund_h, selection),))
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    week_cols = []
    for col in ji.columns(rows):
        n = ji.norm(col)
        if "overlevelseskurve u tilbagefald til den valgte ydelse" not in n:
            continue
        m = re.search(r"(\d+) uger", n)
        if m:
            week_cols.append((int(m.group(1)), col))
    week_cols.sort()
    if not week_cols:
        raise RuntimeError("Ugekolonner til overlevelseskurven mangler")
    periods = sorted({str(r.get(pcol)) for r in rows if r.get(pcol)}, key=pkey, reverse=True)
    chosen = None
    for period in periods:
        total_rows = [r for r in rows if str(r.get(pcol)) == period and fund_code(r.get(fcol), data) == data["meta"]["totalFundCode"]]
        if total_rows and ji.number(total_rows[0].get(week_cols[-1][1])) is not None:
            chosen = period
            break
    if chosen is None:
        for period in periods:
            if any(ji.number(r.get(week_cols[min(len(week_cols)-1, 3)][1])) is not None for r in rows if str(r.get(pcol)) == period):
                chosen = period
                break
    if chosen is None:
        raise RuntimeError("Ingen moden overlevelsesperiode fundet")
    for row in rows:
        if str(row.get(pcol)) != chosen:
            continue
        code = fund_code(row.get(fcol), data)
        if code not in data["funds"]:
            continue
        items = [{"label": f"{week} uger", "value": ji.number(row.get(col))} for week, col in week_cols]
        items = [item for item in items if item["value"] is not None]
        data["funds"][code]["jobindsats"]["survival"] = {"period": chosen, "items": items}
    put_status(data, "jobOverlevelse", table, chosen, "pct. fortsat på dagpenge uden tilbagefald")


def status_after(data):
    table = "y01b15"
    spec, fund_h, selection = setup(table)
    status_h = ji.find_hierarchy(spec, ["arbejdsmarkedsstatus"])
    status_level = ji.levels(status_h)[0].get("level_id")
    rows = ji.query(table, spec, "latest:8", ((fund_h, selection), (status_h, f"level:{status_level}")))
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    scol = exact_col(rows, "Arbejdsmarkedsstatus") or ji.best_col(rows, ["arbejdsmarkedsstatus"], distinct=True)
    vcol = exact_col(rows, "Status 3 mdr. efter afsluttet forløb, pct.")
    if not vcol:
        raise RuntimeError("3-måneders statuskolonnen mangler")
    periods = sorted({str(r.get(pcol)) for r in rows if r.get(pcol)}, key=pkey, reverse=True)
    chosen = next((p for p in periods if any(ji.number(r.get(vcol)) is not None and ji.norm(r.get(scol)) != "i alt" for r in rows if str(r.get(pcol)) == p)), None)
    if not chosen:
        raise RuntimeError("Ingen periode med 3-måneders status fundet")
    grouped = defaultdict(list)
    for row in rows:
        if str(row.get(pcol)) != chosen:
            continue
        code = fund_code(row.get(fcol), data)
        label = str(row.get(scol) or "").strip()
        value = ji.number(row.get(vcol))
        if code in data["funds"] and value is not None and ji.norm(label) != "i alt":
            grouped[code].append({"label": label, "value": value})
    for code, items in grouped.items():
        items.sort(key=lambda x: x["value"], reverse=True)
        data["funds"][code]["jobindsats"]["statusAfter3m"] = {"period": chosen, "items": items}
    put_status(data, "jobStatusAfter", table, chosen, "pct. efter arbejdsmarkedsstatus 3 mdr. efter afsluttet forløb")


def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    jobs = [
        ("jobEarlyTalks", early_talks),
        ("jobLongTerm", long_term),
        ("jobExhaustedRights", exhausted_rights),
        ("jobSanctions", sanctions),
        ("jobDagpengeforbrug", consumption),
        ("jobOverlevelse", survival),
        ("jobStatusAfter", status_after),
    ]
    for key, func in jobs:
        try:
            func(data)
            print(key, "ok", data["meta"]["sourceStatus"][key].get("latestPeriod"))
        except Exception as exc:
            old = data["meta"]["sourceStatus"].get(key, {})
            state = "stale" if old.get("latestPeriod") else "failed"
            data["meta"]["sourceStatus"][key] = {
                "state": state,
                "source": "Jobindsats.dk / STAR",
                "dataset": old.get("dataset"),
                "latestPeriod": old.get("latestPeriod"),
                "error": str(exc)[:600],
                "checkedAt": now_iso(),
            }
            print(key, state, exc)

    data["meta"]["sourceStatus"].pop("AULK08", None)
    for fund in data.get("funds", {}).values():
        fund.pop("longTermPer1000", None)

    statuses = data["meta"]["sourceStatus"]
    successful = [k for k, v in statuses.items() if v.get("state") == "ok"]
    failed = [k for k, v in statuses.items() if v.get("state") != "ok"]
    data["meta"]["updateStatus"] = {
        "state": "ok" if not failed else ("partial" if successful else "failed"),
        "successful": successful,
        "failed": failed,
        "checkedAt": now_iso(),
    }
    data["meta"]["methodNotes"] = [
        "Rå antal vises for den valgte a-kasse alene. Indeks, procenter og andele kan sammenlignes med I alt og flere valgte a-kasser.",
        "AUP03 er Danmarks Statistiks foreløbige ledighedsprocent blandt samtlige forsikrede.",
        "Langtidsledighed hentes fra Jobindsats og afgrænses til a-dagpenge.",
        "Rådighedssanktioner hentes kvartalsvist fra Jobindsats. Der er databrud fra 1. kvt. 2021, hvor sager rejst af a-kasserne selv også indgår.",
        "Hvert Jobindsats-modul har egen kildestatus, så en enkelt fejl ikke skjules.",
    ]
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
