from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import jobindsats_api as ji
import statbank_api as sb

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "dashboard-data.json"


def now_iso():
    return datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds")


def pkey(period):
    text = str(period or "")
    match = re.fullmatch(r"(\d{4})M(\d{2})", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"(\d{4})K(\d)", text)
    if match:
        return int(match.group(1)), int(match.group(2)) * 3
    return 9999, 99


def old_data():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ok(source, dataset, latest, unit, updated=None, note=None):
    value = {"state": "ok", "source": source, "dataset": dataset, "latestPeriod": latest, "unit": unit, "checkedAt": now_iso()}
    if updated:
        value["sourceUpdated"] = updated
    if note:
        value["note"] = note
    return value


def problem(source, dataset, error, old=None, not_configured=False):
    old = old if isinstance(old, dict) else {}
    state = "not_configured" if not_configured else ("stale" if old.get("latestPeriod") else "failed")
    value = {"state": state, "source": source, "dataset": dataset, "error": str(error)[:600], "checkedAt": now_iso()}
    if old.get("latestPeriod"):
        value["latestPeriod"] = old["latestPeriod"]
    return value


def find_total(var, names):
    return sb.find_value(var, names)


def fund_key(name):
    text = ji.norm(name)
    text = re.sub(r"\b(fra|inkl|jan|januar|juli)\b.*$", "", text).strip()
    text = re.sub(r"\b(arbejdsloeshedskasse|a kassen|a kasse|akasse)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    aliases = {
        "a til": "atil",
        "funktionaerer og tjenestemaend ftf a": "atil",
        "ftf a": "atil",
        "frie": "frie",
        "akademikernes": "akademikerne",
        "akademikerne": "akademikerne",
        "ase": "ase",
        "borne og ungdomspaedagoger bupl a": "bupl",
        "borne og ungdomspaedagoger bupl": "bupl",
        "bupl": "bupl",
        "det faglige hus": "detfagligehus",
        "din faglige": "dinfaglige",
        "din sundhedsfaglige dsa": "dsa",
        "din sundhedsfaglige": "dsa",
        "fag og arbejde foa": "foa",
        "foas": "foa",
        "foa": "foa",
        "faglig faelles 3f": "3f",
        "faglig faelles": "3f",
        "handels og kontorfunktionaerer hk": "hk",
        "hk danmarks": "hk",
        "journalistik kommunikation og sprog": "jks",
        "for journalistik komm og sprog": "jks",
        "journalistik komm og sprog": "jks",
        "kristelig": "krifa",
        "laerere dlf a": "laererne",
        "laerere dlf": "laererne",
        "laerernes": "laererne",
        "ledere": "lederne",
        "lederne": "lederne",
        "magistre ma": "magistrene",
        "magistrenes": "magistrene",
        "metalarbejdere": "metal",
        "metalarbejdernes": "metal",
        "min": "min",
        "oekonomer ca": "ca",
        "ca": "ca",
        "socialpaedagoger sla": "socialpaedagogerne",
        "socialpaedagogernes": "socialpaedagogerne",
        "teknikere": "teknikerne",
        "teknikernes": "teknikerne",
    }
    return aliases.get(text, text)

def match_fund(label, names, total_code):
    normalized = ji.norm(label)
    if "i alt" in normalized and ("a kasse" in normalized or normalized == "i alt"):
        return total_code
    key = fund_key(label)
    candidates = {code: fund_key(name) for code, name in names.items()}
    exact = [code for code, value in candidates.items() if value == key]
    if exact:
        return exact[0]
    tokens = set(key.split())
    best = (0, None)
    for code, candidate in candidates.items():
        other = set(candidate.split())
        if not tokens or not other:
            continue
        score = len(tokens & other) / len(tokens | other)
        if key in candidate or candidate in key:
            score += 0.5
        if score > best[0]:
            best = score, code
    return best[1] if best[0] >= 0.45 else None


def series(rows, fund_dim, time_dim):
    grouped = defaultdict(dict)
    for row in rows:
        grouped[str(row.get(fund_dim))][str(row.get(time_dim))] = row.get("value")
    result = {}
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        result[code] = {"labels": labels, "values": [values[p] for p in labels]}
    return result


def fetch_dst():
    statuses = {}
    funds = {}

    info = sb.tableinfo("AUA01")
    fund_var = sb.variable(info, ["a kasse"]); time_var = sb.variable(info, ["maaned", "tid"])
    area_var = sb.variable(info, ["omraade"]); age_var = sb.variable(info, ["alder"]); sex_var = sb.variable(info, ["koen"])
    fund_total = find_total(fund_var, ["i alt"]); area_total = find_total(area_var, ["hele landet", "danmark", "i alt"])
    age_total = find_total(age_var, ["alder i alt", "i alt"]); sex_total = find_total(sex_var, ["koen i alt", "i alt"])
    payload = sb.data("AUA01", {str(area_var["id"]): [area_total], str(fund_var["id"]): sb.all_codes(fund_var), str(age_var["id"]): [age_total], str(sex_var["id"]): [sex_total], str(time_var["id"]): ["*"]})
    rows, dataset = sb.records(payload)
    members = series(rows, str(fund_var["id"]), str(time_var["id"]))
    latest = max((p for item in members.values() for p in item["labels"]), key=pkey)
    names_all = sb.code_labels(fund_var)
    active = []
    for code, item in members.items():
        if code == fund_total:
            continue
        values = dict(zip(item["labels"], item["values"]))
        if (values.get(latest) or 0) > 0:
            active.append(code)
    selected = [fund_total] + sorted(active, key=lambda code: ji.norm(names_all.get(code, code)))
    names = {code: names_all.get(code, code) for code in selected}
    for code in selected:
        funds[code] = {"code": code, "name": names[code], "members": members.get(code, {"labels": [], "values": []}), "profileAge": [], "profileSex": [], "jobindsats": {}}
    statuses["AUA01"] = ok("Danmarks Statistik", "AUA01", latest, "antal forsikringsaktive", info.get("updated") or dataset.get("updated"))

    payload = sb.data("AUA01", {str(area_var["id"]): [area_total], str(fund_var["id"]): selected, str(age_var["id"]): sb.all_codes(age_var), str(sex_var["id"]): [sex_total], str(time_var["id"]): [latest]})
    rows, _ = sb.records(payload); labels = sb.code_labels(age_var)
    for row in rows:
        code, age = str(row.get(str(fund_var["id"]))), str(row.get(str(age_var["id"])))
        if code in funds and age != age_total:
            funds[code]["profileAge"].append({"label": labels.get(age, age), "value": row.get("value")})

    payload = sb.data("AUA01", {str(area_var["id"]): [area_total], str(fund_var["id"]): selected, str(age_var["id"]): [age_total], str(sex_var["id"]): sb.all_codes(sex_var), str(time_var["id"]): [latest]})
    rows, _ = sb.records(payload); labels = sb.code_labels(sex_var)
    for row in rows:
        code, sex = str(row.get(str(fund_var["id"]))), str(row.get(str(sex_var["id"])))
        if code in funds and sex != sex_total:
            funds[code]["profileSex"].append({"label": labels.get(sex, sex), "value": row.get("value")})

    info = sb.tableinfo("AUP03")
    f = sb.variable(info, ["a kasse"]); t = sb.variable(info, ["maaned", "tid"]); a = sb.variable(info, ["omraade"]); g = sb.variable(info, ["alder"]); s = sb.variable(info, ["koen"])
    payload = sb.data("AUP03", {str(a["id"]): [find_total(a, ["hele landet", "danmark", "i alt"])], str(g["id"]): [find_total(g, ["alder i alt", "i alt"])], str(s["id"]): [find_total(s, ["koen i alt", "i alt"])], str(f["id"]): sb.all_codes(f), str(t["id"]): ["*"]})
    rows, dataset = sb.records(payload); map_codes = {code: match_fund(label, names, fund_total) for code, label in sb.code_labels(f).items()}
    grouped = defaultdict(dict)
    for row in rows:
        target = map_codes.get(str(row.get(str(f["id"]))))
        if target in funds:
            grouped[target][str(row.get(str(t["id"])))] = row.get("value")
    latest_rate = None
    for code in funds:
        labels = sorted(grouped.get(code, {}), key=pkey); funds[code]["unemploymentRate"] = {"labels": labels, "values": [grouped[code][p] for p in labels] if labels else []}
        if labels and (latest_rate is None or pkey(labels[-1]) > pkey(latest_rate)):
            latest_rate = labels[-1]
    statuses["AUP03"] = ok("Danmarks Statistik", "AUP03", latest_rate, "pct. fuldtidsledige af samtlige forsikrede", info.get("updated") or dataset.get("updated"), "foreloebig opgoerelse")

    info = sb.tableinfo("AULK08")
    f = sb.variable(info, ["a kasse"]); t = sb.variable(info, ["maaned", "tid"]); u = sb.variable(info, ["enhed"]); g = sb.variable(info, ["alder"])
    unit = sb.find_value(u, ["per 1 000 forsikringsaktive", "1 000 forsikringsaktive"]); age = find_total(g, ["alder i alt", "i alt"])
    payload = sb.data("AULK08", {str(f["id"]): sb.all_codes(f), str(u["id"]): [unit], str(g["id"]): [age], str(t["id"]): ["*"]})
    rows, dataset = sb.records(payload); map_codes = {code: match_fund(label, names, fund_total) for code, label in sb.code_labels(f).items()}
    grouped = defaultdict(dict)
    for row in rows:
        target = map_codes.get(str(row.get(str(f["id"]))))
        if target in funds:
            grouped[target][str(row.get(str(t["id"])))] = row.get("value")
    latest_long = None
    for code in funds:
        labels = sorted(grouped.get(code, {}), key=pkey); funds[code]["longTermPer1000"] = {"labels": labels, "values": [grouped[code][p] for p in labels] if labels else []}
        if labels and (latest_long is None or pkey(labels[-1]) > pkey(latest_long)):
            latest_long = labels[-1]
    statuses["AULK08"] = ok("Danmarks Statistik", "AULK08", latest_long, "langtidsledige pr. 1.000 forsikringsaktive", info.get("updated") or dataset.get("updated"))
    return funds, statuses, {"totalFundCode": fund_total, "fundNames": names}


def fund_rows(rows, funds, total_code):
    fcol = ji.best_col(rows, ["a kasse"], distinct=True); pcol = ji.best_col(rows, ["periode"], distinct=True)
    names = {code: item["name"] for code, item in funds.items()}; matched = []
    for row in rows:
        code = match_fund(row.get(fcol), names, total_code)
        if code in funds:
            matched.append((code, str(row.get(pcol)), row))
    return matched, pcol


def process_timeseries(rows, funds, total_code, module, value_terms, value_key="value", excludes=()):
    matched, pcol = fund_rows(rows, funds, total_code); raw = [row for _, _, row in matched]
    vcol = ji.best_col(raw, value_terms, excludes); grouped = defaultdict(dict)
    for code, period, row in matched:
        grouped[code][period] = ji.number(row.get(vcol))
    for code, values in grouped.items():
        labels = sorted(values, key=pkey); funds[code]["jobindsats"][module] = {"labels": labels, value_key: [values[p] for p in labels]}
    return max((period for _, period, _ in matched), key=pkey) if matched else None


def process_dagpenge(rows, funds, total_code):
    matched, _ = fund_rows(rows, funds, total_code); raw = [row for _, _, row in matched]
    p = ji.best_col(raw, ["antal personer"], ["fuldtid", "andel", "pct"]); ft = ji.best_col(raw, ["fuldtid"], ["andel", "pct"]); grouped = defaultdict(dict)
    for code, period, row in matched:
        grouped[code][period] = (ji.number(row.get(p)), ji.number(row.get(ft)))
    for code, values in grouped.items():
        labels = sorted(values, key=pkey); funds[code]["jobindsats"]["dagpenge"] = {"labels": labels, "persons": [values[x][0] for x in labels], "fulltime": [values[x][1] for x in labels]}
    return max((period for _, period, _ in matched), key=pkey) if matched else None


def process_dimittend(rows, funds, total_code):
    matched, _ = fund_rows(rows, funds, total_code); raw = [row for _, _, row in matched]
    share = ji.best_col(raw, ["andel", "dimittend"], ["fuldtid"]); count = ji.best_col(raw, ["antal", "dimittend", "personer"], ["andel", "pct", "fuldtid"]); grouped = defaultdict(dict)
    for code, period, row in matched:
        grouped[code][period] = (ji.number(row.get(share)), ji.number(row.get(count)))
    for code, values in grouped.items():
        labels = sorted(values, key=pkey); funds[code]["jobindsats"]["graduates"] = {"labels": labels, "share": [values[x][0] for x in labels], "persons": [values[x][1] for x in labels]}
    return max((period for _, period, _ in matched), key=pkey) if matched else None


def process_category(rows, funds, total_code, module, category_terms, measure_terms, percent=False):
    matched, _ = fund_rows(rows, funds, total_code); raw = [row for _, _, row in matched]
    latest = max((period for _, period, _ in matched), key=pkey) if matched else None
    ccol = None
    for col in ji.columns(raw):
        values = ji.norm(" ".join(str(row.get(col)) for row in raw[:300] if row.get(col) not in (None, "")))
        if any(ji.norm(term) in values for term in category_terms):
            ccol = col; break
    if not ccol:
        raise RuntimeError(f"Kategorikolonne mangler for {category_terms}")
    mcol = ji.best_col(raw, measure_terms); grouped = defaultdict(list)
    for code, period, row in matched:
        if period != latest:
            continue
        label = str(row.get(ccol) or "").strip(); value = ji.number(row.get(mcol))
        if label and value is not None:
            grouped[code].append({"label": label, "value": value})
    for code, items in grouped.items():
        funds[code]["jobindsats"][module] = {"period": latest, "items": items}
    return latest


def jobindsats(funds, statuses, meta, old):
    old_status = old.get("meta", {}).get("sourceStatus", {}) if isinstance(old, dict) else {}
    definitions = [
        ("jobDagpenge", "dagpenge", ["a dagpenge", "antal personer og fuldtidspersoner"], ["sygedagpenge"], "latest:120", process_dagpenge, "personer og fuldtidspersoner"),
        ("jobDimittend", "graduates", ["antal dimittendledige personer"], [], "latest:120", process_dimittend, "personer og pct."),
        ("jobEarlyTalks", "earlyTalks", ["jobsamtaler", "a dagpengemodtagere", "a kasserne"], ["jobcent"], "latest:60", lambda r,f,t: process_timeseries(r,f,t,"earlyTalks",["andel"],"share"), "pct."),
        ("jobDagpengeforbrug", "benefitConsumption", ["antal personer med forbrug af dagpengeperioden"], [], "latest:1", lambda r,f,t: process_category(r,f,t,"benefitConsumption",["forbrug","maaned"],["antal personer"]), "personer"),
        ("jobOverlevelse", "survival", ["overlevelseskurver", "a dagpenge"], ["sygedagpenge","kontanthjaelp"], "latest:1", lambda r,f,t: process_category(r,f,t,"survival",["uge","uger"],["pct"]), "pct."),
        ("jobStatusAfter", "statusAfter3m", ["arbejdsmarkedsstatus", "afsluttet", "a dagpenge"], ["sygedagpenge","kontanthjaelp"], "latest:1", lambda r,f,t: process_category(r,f,t,"statusAfter3m",["beskaeftigelse","uddannelse","selvforsoergelse"],["pct"]), "pct."),
    ]
    if not os.environ.get("JOBINDSATS_API_TOKEN"):
        for key, module, *_ in definitions:
            statuses[key] = problem("Jobindsats.dk / STAR", None, "GitHub-secret API_ADGANG mangler", old_status.get(key), True)
        return
    tables = ji.get("tables", {"format": "json"}); discovered = {}
    for key, module, phrases, excludes, period, processor, unit in definitions:
        try:
            table = ji.find_table(tables, phrases, excludes); table_id = str(table["table_id"]); spec = ji.get(f"table/{table_id}", {"format": "json"})
            fund_h = ji.find_hierarchy(spec, ["a kasse", "akasse"]); level = ji.fund_level(fund_h); selection = f"level:{level}" if level else "*"
            rows = ji.query(table_id, spec, period, ((fund_h, selection),))
            latest = processor(rows, funds, meta["totalFundCode"])
            if not latest:
                raise RuntimeError("Ingen periode identificeret")
            statuses[key] = ok("Jobindsats.dk / STAR", table_id, latest, unit); discovered[key] = table_id
        except Exception as exc:
            statuses[key] = problem("Jobindsats.dk / STAR", None, exc, old_status.get(key))
    meta["jobindsatsTables"] = discovered


def main():
    old = old_data(); statuses = {}; meta = {}; funds = {}
    try:
        funds, statuses, meta = fetch_dst()
    except Exception as exc:
        previous = old.get("funds", {}) if isinstance(old, dict) else {}; funds = previous
        old_status = old.get("meta", {}).get("sourceStatus", {}) if isinstance(old, dict) else {}
        for code in ("AUA01", "AUP03", "AULK08"):
            statuses[code] = problem("Danmarks Statistik", code, exc, old_status.get(code))
        meta = {"totalFundCode": old.get("meta", {}).get("totalFundCode"), "fundNames": {code: value.get("name", code) for code, value in funds.items()}}
    if funds and meta.get("totalFundCode"):
        jobindsats(funds, statuses, meta, old)
    successful = [key for key, value in statuses.items() if value.get("state") == "ok"]
    failed = [key for key, value in statuses.items() if value.get("state") != "ok"]
    dst_ok = all(statuses.get(key, {}).get("state") == "ok" for key in ("AUA01", "AUP03", "AULK08"))
    state = "ok" if dst_ok and not failed else ("partial" if successful else "failed")
    checked = now_iso()
    data = {"meta": {"title": "A-kasseindsigt", "updated": checked[:10], "checkedAt": checked, "sourceStatus": statuses, "updateStatus": {"state": state, "successful": successful, "failed": failed, "checkedAt": checked}, "methodNotes": ["Raad medlemstal sammenlignes ikke direkte mellem store og smaa a-kasser. Udviklingsgrafer vises derfor som indeks, hvor det er relevant.", "AUP03 er Danmarks Statistiks foreloebige ledighedsprocent blandt samtlige forsikrede.", "Hvert Jobindsats-modul har egen kildestatus, saa en enkelt fejl ikke skjules."], **meta}, "funds": funds}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("A-kasseindsigt:", state)
    for key, value in statuses.items(): print(key, value.get("state"), value.get("latestPeriod"), value.get("dataset"))
    if state == "failed": raise SystemExit(2)


if __name__ == "__main__":
    main()
