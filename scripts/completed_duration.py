from __future__ import annotations

import json
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


def exact_col(rows, label):
    wanted = ji.norm(label)
    return next((col for col in ji.columns(rows) if ji.norm(col) == wanted), None)


def find_table():
    tables = ji.get("tables", {"format": "json"})
    found = ji.find_table(
        tables,
        ["antal og varighed af afsluttede forloeb", "a dagpenge"],
        ["aktiveringsforloeb", "kontanthjaelp", "sygedagpenge", "fleksjob"],
    )
    table_id = str(found["table_id"])
    spec = ji.get(f"table/{table_id}", {"format": "json"})
    return table_id, spec


def fund_code(label, data):
    names = {code: item.get("name", code) for code, item in data["funds"].items()}
    return match_fund(label, names, data["meta"]["totalFundCode"])


def best_level(hierarchy):
    levels = ji.levels(hierarchy)
    if not levels:
        return None
    ranked = sorted(levels, key=lambda level: len(ji.hierarchy_values(level)), reverse=True)
    return ranked[0].get("level_id")


def query_rows(table, spec, fund_h, fund_selection, duration_h, duration_selection):
    return ji.query(
        table,
        spec,
        "latest:1",
        ((fund_h, fund_selection), (duration_h, duration_selection)),
    )


def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    table, spec = find_table()

    fund_h = ji.find_hierarchy(spec, ["a kasse", "akasse"])
    fund_level = ji.fund_level(fund_h)
    fund_selection = f"level:{fund_level}" if fund_level else "*"

    duration_h = ji.find_hierarchy(spec, ["varighed", "afsluttede forloeb"])
    duration_level = best_level(duration_h)
    duration_selection = f"level:{duration_level}" if duration_level else "*"

    rows = query_rows(table, spec, fund_h, fund_selection, duration_h, duration_selection)
    total_rows = query_rows(table, spec, fund_h, ji.total_value(fund_h), duration_h, duration_selection)
    for row in total_rows:
        row["_dak_force_total"] = True
    rows.extend(total_rows)

    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    dcol = exact_col(rows, "Varighed af afsluttede forløb") or ji.best_col(
        rows, ["varighed", "afsluttede", "forloeb"], ["gnsn", "gennemsnit"], distinct=True
    )
    count_col = exact_col(rows, "Antal afsluttede forløb")
    if not count_col:
        count_col = ji.best_col(
            rows,
            ["antal", "afsluttede", "forloeb"],
            ["gnsn", "gennemsnit"],
        )

    avg_candidates = [
        col
        for col in ji.columns(rows)
        if ("gnsn" in ji.norm(col) or "gennemsnit" in ji.norm(col))
        and "varighed" in ji.norm(col)
        and "afsluttede" in ji.norm(col)
    ]
    avg_col = avg_candidates[0] if avg_candidates else None

    periods = [str(row.get(pcol) or "") for row in rows if row.get(pcol)]
    if not periods:
        raise RuntimeError("Afsluttede forløb gav ingen periode")
    latest = max(periods)

    grouped = defaultdict(list)
    averages = {}
    total_code = data["meta"]["totalFundCode"]
    for row in rows:
        if str(row.get(pcol) or "") != latest:
            continue
        code = total_code if row.get("_dak_force_total") else fund_code(row.get(fcol), data)
        if code not in data["funds"]:
            continue
        label = str(row.get(dcol) or "").strip()
        value = ji.number(row.get(count_col))
        if label and ji.norm(label) not in {"i alt", "total"} and value is not None:
            grouped[code].append({"label": label, "value": value})
        if avg_col and code not in averages:
            avg = ji.number(row.get(avg_col))
            if avg is not None:
                averages[code] = avg

    if not grouped:
        raise RuntimeError(
            "Afsluttede forløb gav ingen varighedsfordeling. "
            f"Kolonner: {ji.columns(rows)}"
        )

    missing = []
    for code in data["funds"]:
        items = grouped.get(code)
        if not items:
            missing.append(code)
            continue
        data["funds"][code]["jobindsats"]["completedDuration"] = {
            "period": latest,
            "items": items,
            "averageWeeks": averages.get(code),
        }
    if missing:
        raise RuntimeError("Afsluttede forløb mangler a-kasser: " + ", ".join(missing))

    data["meta"]["sourceStatus"]["jobCompletedDuration"] = {
        "state": "ok",
        "source": "Jobindsats.dk / STAR",
        "dataset": table,
        "latestPeriod": latest,
        "unit": "antal afsluttede a-dagpengeforløb efter varighed og gennemsnitlig varighed i uger",
        "checkedAt": now_iso(),
        "note": "Et forløb er afsluttet, når der følger en sammenhængende kalendermåned uden udbetaling af a-dagpenge.",
    }
    data["meta"].setdefault("jobindsatsTables", {})["jobCompletedDuration"] = table
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("jobCompletedDuration ok", table, latest)


if __name__ == "__main__":
    main()
