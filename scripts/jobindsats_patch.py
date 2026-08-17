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


def now_iso():
    return datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds")


def pkey(period):
    text = str(period or "")
    m = re.fullmatch(r"(\d{4})M(\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    q = re.fullmatch(r"(\d{4})Q(\d)", text)
    if q:
        return int(q.group(1)), int(q.group(2)) * 3
    return 0, 0


def setup(table_id):
    spec = ji.get(f"table/{table_id}", {"format": "json"})
    fund = ji.find_hierarchy(spec, ["a kasse", "akasse"])
    level = ji.fund_level(fund)
    return spec, fund, f"level:{level}" if level else "*"


def fund_code(label, data):
    names = {code: item.get("name", code) for code, item in data["funds"].items()}
    return match_fund(label, names, data["meta"]["totalFundCode"])


def put_status(data, key, dataset, latest, unit):
    data["meta"]["sourceStatus"][key] = {
        "state": "ok",
        "source": "Jobindsats.dk / STAR",
        "dataset": dataset,
        "latestPeriod": latest,
        "unit": unit,
        "checkedAt": now_iso(),
    }


def early_talks(data):
    table = "y30e22ak"
    spec, fund_h, selection = setup(table)
    rows = ji.query(table, spec, "latest:28", ((fund_h, selection),))
    fcol = ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = ji.best_col(rows, ["periode"], distinct=True)
    vcol = next((c for c in ji.columns(rows) if ji.norm(c) == ji.norm("Andel personer fordelt på antal afholdte jobsamtaler : 3+")), None)
    if not vcol:
        raise RuntimeError("Kolonnen for andel med 3+ jobsamtaler mangler")
    grouped = defaultdict(dict)
    for row in rows:
        code = fund_code(row.get(fcol), data)
        period = str(row.get(pcol) or "")
        value = ji.number(row.get(vcol))
        if code in data["funds"] and period:
            grouped[code][period] = value
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code]["jobindsats"]["earlyTalks"] = {
            "labels": labels,
            "share": [values[p] for p in labels],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobEarlyTalks", table, latest, "pct. med mindst 3 jobsamtaler")


def consumption(data):
    table = "y01a12"
    spec, fund_h, selection = setup(table)
    dp = ji.find_hierarchy(spec, ["forbrug", "dagpengeperioden"])
    level = ji.levels(dp)[0].get("level_id")
    rows = ji.query(table, spec, "latest:1", ((fund_h, selection), (dp, f"level:{level}")))
    fcol = ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = ji.best_col(rows, ["periode"], distinct=True)
    ccol = ji.best_col(rows, ["forbrug", "dagpengeperioden"], distinct=True)
    vcol = ji.best_col(rows, ["antal personer med forbrug"])
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
    fcol = ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = ji.best_col(rows, ["periode"], distinct=True)
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
    fcol = ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = ji.best_col(rows, ["periode"], distinct=True)
    scol = ji.best_col(rows, ["arbejdsmarkedsstatus"], distinct=True)
    vcol = next((c for c in ji.columns(rows) if ji.norm(c) == ji.norm("Status 3 mdr. efter afsluttet forløb, pct.")), None)
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
    statuses = data["meta"]["sourceStatus"]
    successful = [k for k, v in statuses.items() if v.get("state") == "ok"]
    failed = [k for k, v in statuses.items() if v.get("state") != "ok"]
    data["meta"]["updateStatus"] = {
        "state": "ok" if not failed else ("partial" if successful else "failed"),
        "successful": successful,
        "failed": failed,
        "checkedAt": now_iso(),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
