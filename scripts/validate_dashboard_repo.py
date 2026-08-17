#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def validate(repo, required_sources):
    errors = []
    warnings = []
    html = repo / "index.html"
    data_path = repo / "data" / "dashboard-data.json"
    workflow_dir = repo / ".github" / "workflows"
    if not html.is_file() or html.stat().st_size == 0:
        errors.append("index.html is missing or empty")
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid dashboard data: {exc}")
        data = {}
    workflows = list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")) if workflow_dir.is_dir() else []
    if not workflows:
        warnings.append("No GitHub Actions workflow found")
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    status = meta.get("sourceStatus", {}) if isinstance(meta, dict) else {}
    for source in required_sources:
        if source not in status:
            errors.append(f"Required source not registered: {source}")
    update = meta.get("updateStatus", {}) if isinstance(meta, dict) else {}
    if update.get("state") == "ok" and update.get("failed"):
        errors.append("updateStatus is ok but failed is not empty")
    for key, info in status.items():
        if isinstance(info, dict) and info.get("state") == "ok" and not info.get("latestPeriod"):
            errors.append(f"Source {key} is ok without latestPeriod")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--require-source", action="append", default=[])
    args = parser.parse_args()
    errors, warnings = validate(Path(args.repo).resolve(), args.require_source)
    for item in warnings:
        print("WARNING:", item)
    for item in errors:
        print("ERROR:", item)
    if errors:
        return 1
    print("OK: dashboard repository passed structural validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
