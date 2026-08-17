from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "dashboard-data.json"
NAMES = BASE / "config" / "a-kasse-navne.json"


def norm(value):
    text = str(value or "").lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    reference = json.loads(NAMES.read_text(encoding="utf-8"))
    aliases = {}
    for row in reference.get("funds", []):
        for field in ("dakName", "dakShort", "dstName", "jobindsatsName", "starMemberName"):
            key = norm(row.get(field))
            if key:
                aliases[key] = row

    total_code = data.get("meta", {}).get("totalFundCode")
    missing = []
    for code, fund in data.get("funds", {}).items():
        if code == total_code:
            fund["name"] = "I alt"
            fund["short"] = "I alt"
            continue
        candidates = [fund.get("name")]
        candidates.extend((fund.get("sourceNames") or {}).values())
        ref = next((aliases.get(norm(value)) for value in candidates if aliases.get(norm(value))), None)
        if not ref:
            missing.append(f"{code}: {fund.get('name')}")
            continue
        fund["sourceNames"] = {
            "dst": ref.get("dstName"),
            "jobindsats": ref.get("jobindsatsName"),
            "starMembers": ref.get("starMemberName"),
        }
        fund["name"] = ref.get("dakName")
        fund["short"] = ref.get("dakShort")
        fund["starCode"] = ref.get("starCode")

    if missing:
        raise RuntimeError("A-kasser uden DAK-navnematch: " + "; ".join(missing))

    data["meta"]["fundNames"] = {code: fund.get("name", code) for code, fund in data.get("funds", {}).items()}
    data["meta"]["nameStandard"] = {
        "source": "Danske A-kasser",
        "asOf": reference.get("meta", {}).get("asOf"),
        "file": "config/a-kasse-navne.json",
    }
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DAK-navnestandard anvendt på {len(data.get('funds', {})) - 1} a-kasser")


if __name__ == "__main__":
    main()
