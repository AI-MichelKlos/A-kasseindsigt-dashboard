from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Validerer også fuld langtidsdækning i dashboardets standardperiode.
BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "dashboard-data.json"
HTML = BASE / "index.html"


def validate():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    state = meta.get("updateStatus", {}).get("state")
    if state != "ok":
        raise RuntimeError(f"Dashboardstatus er {state}; alle påkrævede kilder skal være ok")

    required_sources = [
        "AUA01",
        "AUP03",
        "jobDagpenge",
        "jobDimittend",
        "jobEarlyTalks",
        "jobLongTerm",
        "jobExhaustedRights",
        "jobDagpengeforbrug",
        "jobOverlevelse",
        "jobStatusAfter",
    ]
    statuses = meta.get("sourceStatus", {})
    bad_sources = {
        key: statuses.get(key, {}).get("state", "mangler")
        for key in required_sources
        if statuses.get(key, {}).get("state") != "ok"
    }
    if bad_sources:
        details = "; ".join(f"{key}: {value}" for key, value in bad_sources.items())
        raise RuntimeError(f"Påkrævede kilder er ikke ok: {details}")

    funds = data.get("funds", {})
    total_code = meta.get("totalFundCode")
    if not total_code or total_code not in funds:
        raise RuntimeError("Total a-kasse mangler")
    if len(funds) < 10:
        raise RuntimeError(f"For få aktive a-kasser: {len(funds)}")

    total = funds[total_code]
    for key, source in (("members", "AUA01"), ("unemploymentRate", "AUP03")):
        series = total.get(key, {})
        labels = series.get("labels", [])
        values = series.get("values", [])
        if not labels or len(labels) != len(values):
            raise RuntimeError(f"Ugyldig totalserie {key}")
        source_info = statuses.get(source, {})
        if source_info.get("latestPeriod") != labels[-1]:
            raise RuntimeError(f"Periode mismatch for {source}: {source_info.get('latestPeriod')} != {labels[-1]}")

    required_job_modules = [
        "dagpenge",
        "graduates",
        "earlyTalks",
        "longTerm",
        "exhaustedRights",
        "benefitConsumption",
        "survival",
        "statusAfter3m",
    ]
    missing_modules = {}
    for code, fund in funds.items():
        missing = [key for key in required_job_modules if not fund.get("jobindsats", {}).get(key)]
        if missing:
            missing_modules[code] = missing
    if missing_modules:
        details = "; ".join(f"{code}: {','.join(keys)}" for code, keys in missing_modules.items())
        raise RuntimeError(f"Manglende Jobindsats-moduler pr. a-kasse: {details}")

    # Langtidsledighed skal være komplet i standardvisningen (36 måneder)
    # for alle aktive a-kasser. Vi udfylder aldrig manglende kildeværdier med 0.
    expected_long = total.get("jobindsats", {}).get("longTerm", {})
    expected_labels = expected_long.get("labels", [])[-36:]
    if len(expected_labels) < 36:
        raise RuntimeError(f"Langtidsledighed har kun {len(expected_labels)} måneder; forventer mindst 36")
    long_errors = []
    for code, fund in funds.items():
        block = fund.get("jobindsats", {}).get("longTerm", {})
        labels = block.get("labels", [])
        values = block.get("persons", [])
        if len(labels) != len(values):
            long_errors.append(f"{code}: labels/værdier har forskellig længde")
            continue
        lookup = dict(zip(labels, values))
        missing = [period for period in expected_labels if lookup.get(period) is None]
        if missing:
            long_errors.append(f"{code}: mangler {','.join(missing)}")
    if long_errors:
        raise RuntimeError("Ufuldstændig langtidsledighed: " + "; ".join(long_errors))

    total_jobs = total.get("jobindsats", {})
    period_checks = [
        ("dagpenge", "labels", "jobDagpenge"),
        ("graduates", "labels", "jobDimittend"),
        ("earlyTalks", "labels", "jobEarlyTalks"),
        ("longTerm", "labels", "jobLongTerm"),
        ("exhaustedRights", "labels", "jobExhaustedRights"),
        ("benefitConsumption", "period", "jobDagpengeforbrug"),
        ("survival", "period", "jobOverlevelse"),
        ("statusAfter3m", "period", "jobStatusAfter"),
    ]
    for module, period_kind, source in period_checks:
        block = total_jobs.get(module, {})
        if period_kind == "labels":
            labels = block.get("labels", [])
            actual = labels[-1] if labels else None
        else:
            actual = block.get("period")
        expected = statuses.get(source, {}).get("latestPeriod")
        if not actual or actual != expected:
            raise RuntimeError(f"Periode mismatch for {source}: {expected} != {actual}")

    name_standard = meta.get("nameStandard", {})
    if name_standard.get("source") != "Danske A-kasser":
        raise RuntimeError("DAK-navnestandard er ikke anvendt")

    text = HTML.read_text(encoding="utf-8")
    required = [
        'data/dashboard-data.json',
        'akassesiden.goatcounter.com/count',
        'gc.zgo.at/count.js',
        'id="fundSelect"',
        'id="compareOptions"',
        'id="periodSelect"',
        'id="membersRawChart"',
        'id="membersIndexChart"',
        'id="longRawChart"',
        'id="longIndexChart"',
        'id="gradCountChart"',
        'id="exhaustedChart"',
        'id="statusPeriodText"',
        'id="talkPeriodText"',
        'Mindst 3 samtaler',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"HTML mangler: {missing}")
    print("OK: A-kasseindsigt bestod datavalidering")


def main():
    subprocess.run([sys.executable, str(BASE / "scripts" / "fetch_sources.py")], check=True)
    subprocess.run([sys.executable, str(BASE / "scripts" / "jobindsats_patch.py")], check=True)
    subprocess.run([sys.executable, str(BASE / "scripts" / "apply_dak_names.py")], check=True)
    validate()


if __name__ == "__main__":
    main()
