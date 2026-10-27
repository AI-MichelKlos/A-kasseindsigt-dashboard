"""Læs manuelle Jobindsats-eksporter af rapporten Dagpengemodtageres jobsøgning.

Filerne ligger i data/raw/jobsearch/ som YYYYMM-fordeling.xlsx og YYYYMM-tabel.xlsx.
Der findes ikke en Jobindsats-API-tabel for målingen. En manglende måned må ikke
stoppe den øvrige opdatering, og tal, der ikke står i filerne, bliver ikke beregnet.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import jobindsats_api as ji

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "dashboard-data.json"
NAMES = BASE / "config" / "a-kasse-navne.json"
RAW = BASE / "data" / "raw" / "jobsearch"
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SOURCE_KEY = "jobJobSearch"
DATASET = "rapportbank/dagpengemodtageres-jobsogning"
REPORT_URL = "https://jobindsats.dk/rapportbank/rapporter/dagpengemodtageres-jobsogning/"
MONTHS = {
    "januar": 1,
    "februar": 2,
    "marts": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}
# Betegnelser i Power BI-eksporten, som ikke står ordret i navnestandarden.
# Værdien er DAK-forkortelsen. Ukendte betegnelser mappes ikke.
EXPLICIT_SHORT = {
    "DFH-A": "DFH",
    "Det Faglige Hus": "DFH",
    "Laka": "LAK",
    "3FA": "3F-A",
    "FOA - Fag og Arbejdes A-kasse": "FOA-A",
}


def now_iso():
    return datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds")


def period_sort(period):
    match = re.fullmatch(r"(\d{4})M(\d{2})", str(period or ""))
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def filename_period(stem):
    match = re.fullmatch(r"(\d{4})(\d{2})", stem)
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{year}M{month:02d}"


def text_period(value):
    match = re.search(r"Periode er ([A-Za-zÆØÅæøå]+) (\d{4})", str(value or ""))
    if not match:
        return None
    month = MONTHS.get(match.group(1).lower())
    if not month:
        return None
    return f"{match.group(2)}M{month:02d}"


def as_percent(value):
    """Omsæt en andel fra 0-1 til procent med to decimaler. Intet estimeres."""
    if ji.number(value) is None:
        return None
    number = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else float(ji.number(value))
    if number < 0 or number > 1:
        return None
    quantized = (Decimal(str(number)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(quantized)


def column_index(ref):
    letters = "".join(char for char in str(ref or "") if char.isalpha())
    if not letters:
        return None
    index = 0
    for char in letters:
        index = index * 26 + ord(char.upper()) - 64
    return index - 1


def cell_text(cell):
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", NS))
    node = cell.find("x:v", NS)
    if node is None or node.text is None:
        return None
    if kind == "s":
        return ("shared", int(node.text))
    if kind == "b":
        return node.text == "1"
    try:
        number = float(node.text)
    except ValueError:
        return node.text
    return int(number) if number.is_integer() else number


def worksheet_rows(path):
    with zipfile.ZipFile(path) as workbook:
        shared = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml").decode("utf-8-sig"))
            for item in root.findall("x:si", NS):
                shared.append("".join(node.text or "" for node in item.findall(".//x:t", NS)))
        sheet_name = next(name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet"))
        root = ElementTree.fromstring(workbook.read(sheet_name).decode("utf-8-sig"))
    rows = []
    for row in root.findall("x:sheetData/x:row", NS):
        values = {}
        for position, cell in enumerate(row.findall("x:c", NS)):
            index = column_index(cell.get("r"))
            if index is None:
                index = position
            value = cell_text(cell)
            if isinstance(value, tuple) and value[0] == "shared":
                value = shared[value[1]] if value[1] < len(shared) else None
            if isinstance(value, str):
                value = value.replace("\r\n", "\n").strip()
            values[index] = value
        if not values:
            rows.append([])
            continue
        width = max(values) + 1
        rows.append([values.get(index) for index in range(width)])
    return rows


def filter_text(rows):
    for row in rows:
        if row and isinstance(row[0], str) and "periode er" in row[0].lower():
            return row[0]
    return ""


def is_label_row(value):
    text = ji.norm(value)
    return not text or text.startswith("anvendte filtre") or text.startswith("kategori")


def find_header(rows, expected_first):
    for index, row in enumerate(rows):
        if row and ji.norm(row[0]) == expected_first:
            return index
    return None


def blank_observation():
    return {
        "shareWithApplication": None,
        "shareWithout": None,
        "countWith": None,
        "countWithout": None,
        "population": None,
        "avgApplications": None,
        "allFundsShare": None,
    }


def same_number(left, right):
    return left == right or (left is None and right is None)


def merge_observation(current, incoming):
    if current is None:
        return dict(incoming), False
    conflict = False
    merged = dict(current)
    for key, value in incoming.items():
        if value is None:
            continue
        if merged[key] is None:
            merged[key] = value
        elif not same_number(merged[key], value):
            conflict = True
    return merged, conflict


class LabelMap:
    def __init__(self, data):
        reference = json.loads(NAMES.read_text(encoding="utf-8"))
        total = data["meta"]["totalFundCode"]
        self.total = total
        self.lookup = {}
        self.by_short = {}
        for code, fund in data.get("funds", {}).items():
            if code == total:
                continue
            short = fund.get("short")
            if short:
                self.by_short[short] = code
            self.add(fund.get("short"), code, "forkortelse")
            self.add(fund.get("name"), code, "navn")
            for value in (fund.get("sourceNames") or {}).values():
                self.add(value, code, "kildenavn")
        for row in reference.get("funds", []):
            code = self.by_short.get(row.get("dakShort"))
            if not code:
                continue
            for field in ("dakName", "dakShort", "jobindsatsName", "starMemberName", "dstName"):
                self.add(row.get(field), code, field)
        for label, short in EXPLICIT_SHORT.items():
            code = self.by_short.get(short)
            if not code:
                raise RuntimeError(f"Eksplicit alias {label!r} peger på ukendt forkortelse {short}")
            self.add(label, code, "eksplicit eksportalias")
        self.add("Alle A-kasser", total, "totalrække")
        self.add("I alt", total, "totalrække")

    def add(self, label, code, origin):
        key = ji.norm(label)
        if not key:
            return
        previous = self.lookup.get(key)
        if previous and previous[0] != code:
            raise RuntimeError(f"Betegnelsen {label!r} matcher både {previous[0]} og {code}")
        if previous is None:
            self.lookup[key] = (code, origin)

    def resolve(self, label):
        hit = self.lookup.get(ji.norm(label))
        return hit


def read_fordeling(path, labels: LabelMap):
    rows = worksheet_rows(path)
    header_index = find_header(rows, "a kasse forkortelse")
    if header_index is None:
        raise ValueError("fordelingsfilen mangler kolonnen A-kasse forkortelse")
    header = [ji.norm(value) for value in rows[header_index]]
    expected = ["a kasse forkortelse", "foerste a kasse", "grundpopulation", "gennemsnit alle a kasser", "andel"]
    if header[:3] != expected[:3] or header[4:6] != expected[3:] or not header[3].startswith("gennemsnitlige antal"):
        raise ValueError(f"uventet fordelingsheader: {rows[header_index]}")
    parsed = []
    for row in rows[header_index + 1 :]:
        if not row or not row[0] or is_label_row(row[0]):
            continue
        short = str(row[0]).strip()
        name = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        hit = labels.resolve(short) or labels.resolve(name)
        observation = blank_observation()
        observation["population"] = ji.number(row[2] if len(row) > 2 else None)
        observation["avgApplications"] = ji.number(row[3] if len(row) > 3 else None)
        observation["allFundsShare"] = as_percent(row[4] if len(row) > 4 else None)
        observation["shareWithApplication"] = as_percent(row[5] if len(row) > 5 else None)
        for index, parsed_share in ((4, observation["allFundsShare"]), (5, observation["shareWithApplication"])):
            raw = row[index] if len(row) > index else None
            if raw not in (None, "") and parsed_share is None and ji.number(raw) is not None:
                raise ValueError(f"andel uden for 0-1 i fordelingsfilen for {short}")
        parsed.append({"short": short, "name": name, "code": hit[0] if hit else None, "origin": hit[1] if hit else None, "observation": observation})
    return filter_text(rows), parsed


def read_tabel(path, labels: LabelMap):
    rows = worksheet_rows(path)
    header_index = find_header(rows, "a kasse")
    if header_index is None or header_index < 1:
        raise ValueError("tabelfilen mangler kolonnen A-kasse")
    header = [ji.norm(value) for value in rows[header_index]]
    group = [ji.norm(value) for value in rows[header_index - 1]]
    if header[:5] != ["a kasse", "antal", "andel", "antal", "andel"]:
        raise ValueError(f"uventet tabelheader: {rows[header_index]}")
    if "uden" not in group[1] or "mindst" not in group[3]:
        raise ValueError(f"tabelkolonnerne uden/med kan ikke skelnes: {rows[header_index - 1]}")
    parsed = []
    for row in rows[header_index + 1 :]:
        if not row or not row[0] or is_label_row(row[0]):
            continue
        name = str(row[0]).strip()
        hit = labels.resolve(name)
        observation = blank_observation()
        observation["countWithout"] = ji.number(row[1] if len(row) > 1 else None)
        observation["shareWithout"] = as_percent(row[2] if len(row) > 2 else None)
        observation["countWith"] = ji.number(row[3] if len(row) > 3 else None)
        observation["shareWithApplication"] = as_percent(row[4] if len(row) > 4 else None)
        for index in (2, 4):
            raw = row[index] if len(row) > index else None
            if raw not in (None, "") and (observation["shareWithout"] if index == 2 else observation["shareWithApplication"]) is None and ji.number(raw) is not None:
                raise ValueError(f"andel uden for 0-1 i tabelfilen for {name}")
        parsed.append({"name": name, "code": hit[0] if hit else None, "origin": hit[1] if hit else None, "observation": observation})
    return filter_text(rows), parsed


def shares_close(left, right):
    if left is None or right is None:
        return True
    return left == right


def load_months(labels: LabelMap):
    warnings = []
    unmapped = []
    mapped_labels = defaultdict(set)
    by_period = {}
    files = sorted(path for path in RAW.glob("*.xlsx") if path.is_file()) if RAW.is_dir() else []
    pairs = defaultdict(dict)
    for path in files:
        match = re.fullmatch(r"(\d{6})-(fordeling|tabel)\.xlsx", path.name)
        if not match or not filename_period(match.group(1)):
            warnings.append(f"{path.name}: filnavnet følger ikke YYYYMM-fordeling.xlsx eller YYYYMM-tabel.xlsx")
            continue
        pairs[filename_period(match.group(1))][match.group(2)] = path

    for period in sorted(pairs, key=period_sort):
        pair = pairs[period]
        if "fordeling" not in pair or "tabel" not in pair:
            missing = "fordeling" if "fordeling" not in pair else "tabel"
            warnings.append(f"{period}: mangler {missing}-filen og er derfor ikke importeret")
            continue
        try:
            fordeling_filter, fordeling_rows = read_fordeling(pair["fordeling"], labels)
            tabel_filter, tabel_rows = read_tabel(pair["tabel"], labels)
        except (ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            warnings.append(f"{period}: {exc}")
            continue
        if "alle kommuner" not in ji.norm(fordeling_filter) or "alle kommuner" not in ji.norm(tabel_filter):
            warnings.append(f"{period}: filteret er ikke Alle kommuner")
            continue
        if text_period(fordeling_filter) != period or text_period(tabel_filter) != period:
            warnings.append(
                f"{period}: perioden i filen ({text_period(fordeling_filter)}, {text_period(tabel_filter)}) "
                "stemmer ikke med filnavnet"
            )
            continue

        month_alias = {}
        for row in fordeling_rows:
            if row["code"]:
                month_alias[ji.norm(row["short"])] = row["code"]
                month_alias[ji.norm(row["name"])] = row["code"]
                mapped_labels[row["code"]].add(row["short"])
                if row["name"]:
                    mapped_labels[row["code"]].add(row["name"])
            else:
                unmapped.append(f"{period} fordeling: {row['short']} / {row['name']}")

        observations = {}
        conflicts = []
        averages = {row["observation"]["allFundsShare"] for row in fordeling_rows if row["observation"]["allFundsShare"] is not None}
        if len(averages) > 1:
            warnings.append(f"{period}: Gennemsnit alle a-kasser er ikke ens på alle rækker")
            average = None
        else:
            average = next(iter(averages), None)

        for row in fordeling_rows:
            code = row["code"]
            if not code or code == labels.total:
                continue
            incoming = row["observation"]
            incoming["allFundsShare"] = None
            merged, conflict = merge_observation(observations.get(code), incoming)
            observations[code] = merged
            if conflict:
                conflicts.append(code)

        for row in tabel_rows:
            code = row["code"] or month_alias.get(ji.norm(row["name"]))
            if code and not row["code"]:
                mapped_labels[code].add(row["name"])
            if not code:
                unmapped.append(f"{period} tabel: {row['name']}")
                continue
            if code == labels.total:
                incoming = row["observation"]
                incoming["allFundsShare"] = average
                merged, conflict = merge_observation(observations.get(code), incoming)
                observations[code] = merged
                mapped_labels[code].add(row["name"])
                if conflict:
                    conflicts.append(code)
                continue
            fordeling = observations.get(code)
            if fordeling and not shares_close(fordeling["shareWithApplication"], row["observation"]["shareWithApplication"]):
                warnings.append(f"{period}: {code} har forskellig andel i fordeling og tabel")
                observations[code] = blank_observation()
                continue
            merged, conflict = merge_observation(fordeling, row["observation"])
            observations[code] = merged
            if conflict:
                conflicts.append(code)
            mapped_labels[code].add(row["name"])

        for code in conflicts:
            observations[code] = blank_observation()
            warnings.append(f"{period}: {code} har modstridende tal og er udeladt i måneden")

        for code, observation in observations.items():
            if code == labels.total:
                continue
            population = observation["population"]
            with_count = observation["countWith"]
            without_count = observation["countWithout"]
            if population is not None and with_count is not None and without_count is not None and population != with_count + without_count:
                warnings.append(
                    f"{period}: {code} har grundpopulation {population}, men antal med og uden summerer til {with_count + without_count}"
                )

        by_period[period] = observations

    return by_period, warnings, unmapped, mapped_labels


def series_block(periods, observations_by_period, code, include_average):
    block = {
        "labels": periods,
        "shareWithApplication": [],
        "shareWithout": [],
        "countWith": [],
        "countWithout": [],
        "population": [],
        "avgApplications": [],
    }
    if include_average:
        block["allFundsShare"] = []
    for period in periods:
        observation = observations_by_period[period].get(code) or blank_observation()
        for key in ("shareWithApplication", "shareWithout", "countWith", "countWithout", "population", "avgApplications"):
            block[key].append(observation[key])
        if include_average:
            block["allFundsShare"].append(observation["allFundsShare"])
    return block


def write_status(data, latest, mapped_codes, unmapped, warnings, month_count):
    note_parts = [
        "Manuel eksport fra Jobindsats-rapporten Dagpengemodtageres jobsøgning. "
        "En manglende måned importeres ikke og stopper ikke den øvrige opdatering."
    ]
    if unmapped:
        note_parts.append("Ikke mappet: " + "; ".join(unmapped[:30]))
    if warnings:
        note_parts.append("Bemærkninger: " + "; ".join(warnings[:30]))
    value = {
        "state": "ok" if latest else "absent",
        "source": "Jobindsats.dk / STAR",
        "dataset": DATASET,
        "unit": "andel med mindst én jobansøgning, antal med og uden, grundpopulation og gennemsnitligt antal jobsøgninger",
        "note": " ".join(note_parts),
        "reportUrl": REPORT_URL,
        "months": month_count,
        "mappedFunds": mapped_codes,
        "unmappedLabels": unmapped,
        "checkedAt": now_iso(),
    }
    if latest:
        value["latestPeriod"] = latest
    data["meta"].setdefault("sourceStatus", {})[SOURCE_KEY] = value
    if latest:
        data["meta"].setdefault("jobindsatsTables", {})[SOURCE_KEY] = DATASET
    update = data["meta"].get("updateStatus")
    if isinstance(update, dict) and latest:
        successful = update.setdefault("successful", [])
        if SOURCE_KEY not in successful:
            successful.append(SOURCE_KEY)
        failed = update.get("failed")
        if isinstance(failed, list) and SOURCE_KEY in failed:
            update["failed"] = [item for item in failed if item != SOURCE_KEY]


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    labels = LabelMap(data)
    by_period, warnings, unmapped, mapped_labels = load_months(labels)
    periods = sorted(by_period, key=period_sort)
    if not periods:
        write_status(data, None, [], unmapped, warnings, 0)
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("jobJobSearch absent")
        for warning in warnings:
            print("bemærkning:", warning)
        for label in unmapped:
            print("ikke mappet:", label)
        return

    present_codes = []
    for code in data.get("funds", {}):
        if any(code in observations for observations in by_period.values()):
            present_codes.append(code)
            block = series_block(periods, by_period, code, code == labels.total)
            data["funds"][code].setdefault("jobindsats", {})["jobSearch"] = block
        else:
            data["funds"][code].get("jobindsats", {}).pop("jobSearch", None)

    latest = periods[-1]
    write_status(data, latest, present_codes, unmapped, warnings, len(periods))
    note = (
        "Jobsøgning hentes fra manuelle Excel-eksporter af Jobindsats-rapporten Dagpengemodtageres jobsøgning. "
        "Der er ikke en API-tabel for målingen."
    )
    notes = data["meta"].setdefault("methodNotes", [])
    if note not in notes:
        notes.append(note)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"jobJobSearch ok {latest} ({len(periods)} måneder)")
    print("Mappede a-kasser:")
    for code in present_codes:
        fund = data["funds"][code]
        export_labels = ", ".join(sorted(mapped_labels.get(code, [])))
        print(f"  {code} {fund.get('short') or ''} {fund.get('name') or ''} <- {export_labels}")
    if unmapped:
        print("Ikke mappet:")
        for label in unmapped:
            print(" ", label)
    else:
        print("Ikke mappet: ingen")
    total = data["funds"][labels.total]["jobindsats"]["jobSearch"]
    index = total["labels"].index(latest)
    print(
        f"Seneste {latest}: med {total['countWith'][index]} ({total['shareWithApplication'][index]} %), "
        f"uden {total['countWithout'][index]} ({total['shareWithout'][index]} %)"
    )
    for warning in warnings:
        print("bemærkning:", warning)


if __name__ == "__main__":
    main()
