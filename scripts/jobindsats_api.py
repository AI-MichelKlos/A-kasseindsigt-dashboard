from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://api.jobindsats.dk/v3"
TIMEOUT = 90


def norm(value):
    text = str(value or "").lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def blob(value):
    if not isinstance(value, dict):
        return norm(value)
    parts = []
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)):
            parts.append(f"{key} {item}")
    return norm(" ".join(parts))


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip().replace("\u00a0", "").replace(" ", "")
        if text.lower() in {"", "-", ".", "..", "null", "none", "nan"}:
            return None
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
        try:
            result = float(text)
        except ValueError:
            return None
    if not math.isfinite(result):
        return None
    return int(result) if result.is_integer() else round(result, 6)


def get(path, params=None):
    token = os.environ.get("JOBINDSATS_API_TOKEN")
    if not token:
        raise RuntimeError("JOBINDSATS_API_TOKEN mangler")
    url = f"{API_ROOT}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe=":,*/")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Danske-A-kasser-A-kasseindsigt/1.0",
        },
    )
    last = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"Jobindsats HTTP {exc.code}: {detail[:500]}")
            if exc.code not in {429, 500, 502, 503, 504}:
                raise last
        except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
            last = exc
        if attempt < 3:
            time.sleep(attempt * 10)
    raise RuntimeError(f"Jobindsats-kald fejlede: {last}")


def records(payload):
    if isinstance(payload, dict) and isinstance(payload.get("columns"), list) and isinstance(payload.get("rows"), list):
        return [dict(zip(payload["columns"], row)) for row in payload["rows"]]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "result", "results"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
    raise RuntimeError("Uventet Jobindsats-tabelformat")


def find_table(payload, phrases, excludes=()):
    wanted = [norm(item) for item in phrases]
    banned = [norm(item) for item in excludes]
    entries = []
    for item in walk(payload):
        table_id = item.get("table_id")
        if not table_id and isinstance(item.get("id"), str) and re.fullmatch(r"y[0-9a-z_]+", item["id"].lower()):
            table_id = item["id"]
        if table_id:
            text = norm(json.dumps(item, ensure_ascii=False))
            score = 0
            for phrase in wanted:
                if phrase in text:
                    score += 500 + len(phrase)
                else:
                    score += sum(15 for word in phrase.split() if len(word) > 3 and word in text)
            score -= sum(1000 for word in banned if word in text)
            entries.append((score, len(text), str(table_id), item, text))
    entries.sort(reverse=True, key=lambda row: (row[0], row[1]))
    if not entries or entries[0][0] <= 0:
        raise RuntimeError(f"Ingen sikker Jobindsats-tabel for {phrases}")
    score, _, table_id, item, text = entries[0]
    minimum = 15 * sum(max(1, len([word for word in phrase.split() if len(word) > 3])) for phrase in wanted)
    if score < minimum:
        raise RuntimeError(f"Usikker Jobindsats-tabel for {phrases}: {table_id}")
    result = dict(item)
    result["table_id"] = table_id
    result["_match_text"] = text[:600]
    return result


def hierarchies(spec):
    best = {}
    for item in walk(spec):
        hierarchy_id = item.get("hierarchy_id")
        if isinstance(hierarchy_id, str):
            size = len(json.dumps(item, ensure_ascii=False))
            old = best.get(hierarchy_id)
            if old is None or size > old[0]:
                best[hierarchy_id] = (size, item)
    return [item for _, item in best.values()]


def find_hierarchy(spec, words, preferred=()):
    wanted = [norm(item) for item in words]
    choices = []
    for item in hierarchies(spec):
        hierarchy_id = str(item.get("hierarchy_id"))
        text = norm(json.dumps(item, ensure_ascii=False))
        score = 0
        if hierarchy_id in preferred:
            score += 1500 - preferred.index(hierarchy_id) * 30
        for word in wanted:
            score += 300 if word in norm(hierarchy_id) else 0
            score += 80 if word in text else 0
        choices.append((score, len(text), item))
    choices.sort(reverse=True, key=lambda row: (row[0], row[1]))
    if not choices or choices[0][0] <= 0:
        raise RuntimeError(f"Kunne ikke finde Jobindsats-hierarki for {words}")
    return choices[0][2]


def hierarchy_values(item):
    output = []
    seen = set()
    for node in walk(item):
        value_id = node.get("value_id")
        if isinstance(value_id, str) and value_id not in seen:
            seen.add(value_id)
            output.append((value_id, blob(node)))
    return output


def total_value(item):
    priority = ("hele landet", "i alt", "total", "alle", "samlet")
    values = hierarchy_values(item)
    for phrase in priority:
        for value_id, text in values:
            if phrase in text:
                return value_id
    for value_id, _ in values:
        if value_id in {"/", "0", "00"}:
            return value_id
    return "/"


def levels(item):
    found = {}
    for node in walk(item):
        level_id = node.get("level_id")
        if isinstance(level_id, str):
            size = len(json.dumps(node, ensure_ascii=False))
            if level_id not in found or size > found[level_id][0]:
                found[level_id] = (size, node)
    return [node for _, node in found.values()]


def fund_level(item):
    candidates = []
    for node in levels(item):
        level_id = str(node.get("level_id"))
        text = norm(json.dumps(node, ensure_ascii=False))
        count = len({value_id for value_id, _ in hierarchy_values(node)})
        score = 0
        if "a kasse" in text or "akasse" in text:
            score += 400
        if 18 <= count <= 60:
            score += 300 - abs(25 - count) * 3
        candidates.append((score, count, level_id))
    candidates.sort(reverse=True)
    return candidates[0][2] if candidates and candidates[0][0] > 0 else None


def required(item):
    for key in ("is_required", "required", "mandatory"):
        value = item.get(key)
        if value in (True, 1, "1", "true", "True"):
            return True
    return False


def query(table_id, spec, period, breakdowns=()):
    base = {"mgroup.*": "*", "format": "json"}
    used = set()
    try:
        geo = find_hierarchy(spec, ["omraade", "geografi", "kommune", "region"], ("_hele_landet", "_nykom", "_reko", "_region"))
        geo_id = str(geo["hierarchy_id"])
        base[f"hierarchy.{geo_id}"] = total_value(geo)
        used.add(geo_id)
    except RuntimeError:
        pass
    for hierarchy, selection in breakdowns:
        hierarchy_id = str(hierarchy["hierarchy_id"])
        base[f"hierarchy.{hierarchy_id}"] = selection
        used.add(hierarchy_id)
    for hierarchy in hierarchies(spec):
        hierarchy_id = str(hierarchy.get("hierarchy_id"))
        if hierarchy_id in used or not required(hierarchy):
            continue
        base[f"hierarchy.{hierarchy_id}"] = total_value(hierarchy)
    errors = []
    for period_type in ("M", "Q", "A", "Y"):
        params = dict(base)
        params[f"period.{period_type}"] = period
        try:
            return records(get(f"data/{table_id}", params))
        except RuntimeError as exc:
            text = str(exc).lower()
            errors.append(str(exc))
            if "period" not in text and "type" not in text and "422" not in text:
                raise
    raise RuntimeError("Ingen gyldig periodetype: " + " | ".join(errors[-3:]))


def all_funds_query(table_id, spec, period="latest:60", extras=()):
    fund = find_hierarchy(spec, ["a kasse", "akasse"])
    level = fund_level(fund)
    selection = f"level:{level}" if level else "*"
    return query(table_id, spec, period, ((fund, selection), *extras))


def columns(rows):
    seen = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def best_col(rows, include, exclude=(), distinct=False):
    wanted = [norm(item) for item in include]
    banned = [norm(item) for item in exclude]
    choices = []
    for column in columns(rows):
        text = norm(column)
        score = sum(120 for word in wanted if word in text) - sum(200 for word in banned if word in text)
        if score > 0:
            count = len({str(row.get(column)) for row in rows if row.get(column) not in (None, "")})
            if distinct:
                score += min(count, 100)
            choices.append((score, count, column))
    if not choices:
        raise RuntimeError(f"Ingen kolonne matcher {include}. Kolonner: {columns(rows)}")
    choices.sort(reverse=True)
    return choices[0][2]
