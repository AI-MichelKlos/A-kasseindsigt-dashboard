from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Validerer også fuld langtidsdækning i dashboardets standardperiode.
BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "dashboard-data.json"
HTML = BASE / "index.html"
PERSONAL_VIEW = BASE / "assets" / "personal-view.js"


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
        "jobTalkForms",
        "jobAfterlon",
        "jobAfterlonContrib",
        "jobLongTerm",
        "jobExhaustedRights",
        "jobSanctions",
        "jobDagpengeforbrug",
        "jobOverlevelse",
        "jobStatusAfter",
        "jobCompletedDuration",
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
        "talkForms",
        "afterlon",
        "afterlonContrib",
        "longTerm",
        "exhaustedRights",
        "sanctions",
        "benefitConsumption",
        "survival",
        "statusAfter3m",
        "completedDuration",
    ]
    missing_modules = {}
    for code, fund in funds.items():
        missing = [key for key in required_job_modules if not fund.get("jobindsats", {}).get(key)]
        if missing:
            missing_modules[code] = missing
    if missing_modules:
        details = "; ".join(f"{code}: {','.join(keys)}" for code, keys in missing_modules.items())
        raise RuntimeError(f"Manglende Jobindsats-moduler pr. a-kasse: {details}")

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

    sanctions_total = total.get("jobindsats", {}).get("sanctions", {})
    sanctions_labels = sanctions_total.get("labels", [])[-12:]
    if len(sanctions_labels) < 12:
        raise RuntimeError(f"Rådighedssanktioner har kun {len(sanctions_labels)} kvartaler; forventer mindst 12")
    sanctions_errors = []
    for code, fund in funds.items():
        block = fund.get("jobindsats", {}).get("sanctions", {})
        labels = block.get("labels", [])
        totals = block.get("total", [])
        shares = block.get("shareSanctioned", [])
        avgs = block.get("avgPerSanctioned", [])
        if not (len(labels) == len(totals) == len(shares) == len(avgs)):
            sanctions_errors.append(f"{code}: uens længde på sanktionstidsserier")
            continue
        lookup_total = dict(zip(labels, totals))
        lookup_share = dict(zip(labels, shares))
        missing = [q for q in sanctions_labels if lookup_total.get(q) is None or lookup_share.get(q) is None]
        if missing:
            sanctions_errors.append(f"{code}: mangler total/andel i {','.join(missing)}")
    if sanctions_errors:
        raise RuntimeError("Ufuldstændige rådighedssanktioner: " + "; ".join(sanctions_errors))

    total_jobs = total.get("jobindsats", {})
    period_checks = [
        ("dagpenge", "labels", "jobDagpenge"),
        ("graduates", "labels", "jobDimittend"),
        ("talkForms", "labels", "jobTalkForms"),
        ("afterlon", "labels", "jobAfterlon"),
        ("afterlonContrib", "labels", "jobAfterlonContrib"),
        ("longTerm", "labels", "jobLongTerm"),
        ("exhaustedRights", "labels", "jobExhaustedRights"),
        ("sanctions", "labels", "jobSanctions"),
        ("benefitConsumption", "period", "jobDagpengeforbrug"),
        ("survival", "period", "jobOverlevelse"),
        ("statusAfter3m", "period", "jobStatusAfter"),
        ("completedDuration", "period", "jobCompletedDuration"),
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
        '<label for="fundSelect">A-kasse</label>',
        "$('fundSelect').value=total",
        'id="compareOptions"',
        'id="periodSelect"',
        'id="membersRawChart"',
        'id="membersIndexChart"',
        'id="longRawChart"',
        'id="longIndexChart"',
        'id="gradCountChart"',
        'id="exhaustedChart"',
        'id="statusPeriodText"',
        'id="statusPeriodHeadline"',
        'id="survPeriodHeadline"',
        'id="completedDurationPeriodHeadline"',
        'id="completedDurationChart"',
        'id="talkPeriodText"',
        'id="afterlonPeriodText"',
        'id="afterlonContribPeriodText"',
        'id="afterlonChart"',
        'id="afterlonContribChart"',
        'id="sanctionsTotalChart"',
        'id="sanctionsShareChart"',
        'id="sanctionsTypeChart"',
        'id="sanctionsAvgChart"',
        'id="sanctionsPeriodText"',
        'DAK_DYNAMIC_LINE_SCALE_20260903',
        "cubicInterpolationMode='monotone'",
        "grace:'8%'",
        'Samtaleformer i a-kassen',
        'Efterløn',
        'Varighed af afsluttede a-dagpengeforløb',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"HTML mangler: {missing}")

    personal_view = PERSONAL_VIEW.read_text(encoding="utf-8")
    required_personal_view = [
        "DAK_CONTROL_ORDER_20260903",
        "DAK_CROSS_GEOGRAPHY_COMPARE_20260903",
        "dak-a-kasseindsigt-personal-view-v5",
        "comparisonFundSelect",
        "comparisonRegionSelect",
        "new Option('Ingen','')",
        "new Option('I alt',total)",
        "Sammenligning:",
        "DAK_GEOGRAPHY_CONTEXT_20260903",
    ]
    missing_personal_view = [item for item in required_personal_view if item not in personal_view]
    if missing_personal_view:
        raise RuntimeError(f"Sammenligningsvisning mangler: {missing_personal_view}")
    print("OK: A-kasseindsigt bestod datavalidering")


def main():
    subprocess.run([sys.executable, str(BASE / "scripts" / "fetch_sources.py")], check=True)
    subprocess.run([sys.executable, str(BASE / "scripts" / "jobindsats_patch.py")], check=True)
    subprocess.run([sys.executable, str(BASE / "scripts" / "completed_duration.py")], check=True)
    subprocess.run([sys.executable, str(BASE / "scripts" / "apply_dak_names.py")], check=True)
    validate()


if __name__ == "__main__":
    main()
