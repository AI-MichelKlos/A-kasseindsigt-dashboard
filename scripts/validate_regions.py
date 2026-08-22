from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MAIN = BASE / "data" / "dashboard-data.json"
REGION_DIR = BASE / "data" / "regions"
EXPECTED = {
    "hovedstaden": "Region Hovedstaden",
    "sjaelland": "Region Sjælland",
    "syddanmark": "Region Syddanmark",
    "midtjylland": "Region Midtjylland",
    "nordjylland": "Region Nordjylland",
}
REQUIRED_JOB_SOURCES = [
    "jobDagpenge",
    "jobDimittend",
    "jobTalkForms",
    "jobAfterlon",
    "jobAfterlonContrib",
    "jobLongTerm",
    "jobSanctions",
    "jobDagpengeforbrug",
    "jobOverlevelse",
    "jobStatusAfter",
    "jobCompletedDuration",
]
REQUIRED_JOB_MODULES = [
    "dagpenge",
    "graduates",
    "talkForms",
    "afterlon",
    "afterlonContrib",
    "longTerm",
    "sanctions",
    "benefitConsumption",
    "survival",
    "statusAfter3m",
    "completedDuration",
]


def valid_series(block: dict, key: str = "values") -> bool:
    labels = block.get("labels", [])
    values = block.get(key, [])
    return bool(labels) and len(labels) == len(values) and len(labels) <= 60


def main() -> None:
    main_data = json.loads(MAIN.read_text(encoding="utf-8"))
    main_funds = main_data.get("funds", {})
    total = str(main_data.get("meta", {}).get("totalFundCode") or "")
    if not main_funds or total not in main_funds:
        raise RuntimeError("Hoveddata er ikke valide")

    for slug, name in EXPECTED.items():
        path = REGION_DIR / f"{slug}.json"
        if not path.exists():
            raise RuntimeError(f"Regional datafil mangler: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        funds = data.get("funds", {})
        if meta.get("areaName") != name:
            raise RuntimeError(f"Forkert områdenavn i {slug}: {meta.get('areaName')}")
        if meta.get("historyMonths") != 60:
            raise RuntimeError(f"Forkert historiklængde i {slug}")
        if set(funds) != set(main_funds):
            raise RuntimeError(f"A-kassekoder afviger i {slug}")

        statuses = meta.get("sourceStatus", {})
        for source in ("AUA01", "AUP03", *REQUIRED_JOB_SOURCES):
            if statuses.get(source, {}).get("state") != "ok":
                raise RuntimeError(f"{slug}: {source} er ikke ok")

        exhausted_state = statuses.get("jobExhaustedRights", {}).get("state")
        if exhausted_state not in {"ok", "unsupported"}:
            raise RuntimeError(f"{slug}: jobExhaustedRights har ugyldig status {exhausted_state}")

        total_fund = funds.get(total, {})
        members = total_fund.get("members", {})
        rate = total_fund.get("unemploymentRate", {})
        if not valid_series(members):
            raise RuntimeError(f"{slug}: ugyldig medlemstidsserie")
        if not valid_series(rate):
            raise RuntimeError(f"{slug}: ugyldig ledighedstidsserie")
        if members["labels"][-1] != statuses["AUA01"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: AUA01 periode mismatch")
        if rate["labels"][-1] != statuses["AUP03"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: AUP03 periode mismatch")
        if not total_fund.get("profileAge"):
            raise RuntimeError(f"{slug}: aldersprofil mangler")

        missing = []
        unavailable = []
        concrete_codes = [code for code in funds if code != total]
        for code, fund in funds.items():
            jobs = fund.get("jobindsats", {})
            if code != total and not jobs:
                unavailable.append((code, fund.get("name", code)))
                continue
            absent = [module for module in REQUIRED_JOB_MODULES if not jobs.get(module)]
            if exhausted_state == "ok" and not jobs.get("exhaustedRights"):
                absent.append("exhaustedRights")
            if absent:
                missing.append(f"{code}: {','.join(absent)}")
        if missing:
            raise RuntimeError(f"{slug}: ufuldstændige regionale Jobindsats-moduler: {'; '.join(missing)}")

        available_count = len(concrete_codes) - len(unavailable)
        minimum_count = max(1, int(len(concrete_codes) * 0.9))
        if available_count < minimum_count or len(unavailable) > 1:
            details = ", ".join(f"{code} {name}" for code, name in unavailable)
            raise RuntimeError(f"{slug}: for mange a-kasser uden regionale Jobindsats-observationer: {details}")
        for code, fund_name in unavailable:
            print(f"{slug}: ingen regionale Jobindsats-observationer for {code} {fund_name}")

        total_jobs = total_fund.get("jobindsats", {})
        if total_jobs.get("dagpenge", {}).get("labels", [None])[-1] != statuses["jobDagpenge"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: jobDagpenge periode mismatch")
        if total_jobs.get("longTerm", {}).get("labels", [None])[-1] != statuses["jobLongTerm"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: jobLongTerm periode mismatch")
        if total_jobs.get("talkForms", {}).get("labels", [None])[-1] != statuses["jobTalkForms"].get("latestPeriod"):
            raise RuntimeError(f"{slug}: jobTalkForms periode mismatch")

    print("OK: regionale A-kassedata og Jobindsats-moduler bestod validering")


if __name__ == "__main__":
    main()
