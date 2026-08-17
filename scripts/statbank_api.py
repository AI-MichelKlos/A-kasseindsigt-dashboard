from __future__ import annotations

import json
import math
import urllib.error
import urllib.request

API_ROOT = "https://api.statbank.dk/v1"
TIMEOUT = 90


def norm(value):
    text = str(value or "").lower()
    repl = {"æ": "ae", "ø": "oe", "å": "aa"}
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def get_json(url, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Danske-A-kasser-A-kasseindsigt/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Statistikbanken HTTP {exc.code}: {detail[:500]}") from exc


def tableinfo(table):
    return get_json(f"{API_ROOT}/tableinfo/{table}?lang=da&format=JSON")


def variables(info):
    vals = info.get("variables")
    if not isinstance(vals, list):
        raise RuntimeError(f"Tabel {info.get('id')} mangler variable i metadata")
    return vals


def variable(info, words):
    wanted = [norm(item) for item in words]
    scored = []
    for var in variables(info):
        blob = norm(f"{var.get('id')} {var.get('text')}")
        score = sum(100 for item in wanted if item in blob)
        if score:
            scored.append((score, var))
    if not scored:
        raise RuntimeError(f"Kunne ikke finde variabel {words} i {info.get('id')}")
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def value_items(var):
    values = var.get("values") or []
    if not isinstance(values, list):
        return []
    return values


def find_value(var, texts, fallback_first=False):
    wanted = [norm(item) for item in texts]
    exact = []
    partial = []
    for item in value_items(var):
        label = norm(item.get("text"))
        if label in wanted:
            exact.append(item)
        elif any(part in label for part in wanted):
            partial.append(item)
    if exact:
        return str(exact[0]["id"])
    if partial:
        return str(partial[0]["id"])
    if fallback_first and value_items(var):
        return str(value_items(var)[0]["id"])
    raise RuntimeError(f"Kunne ikke finde totalvaerdi {texts} i {var.get('text')}")


def all_codes(var):
    return [str(item.get("id")) for item in value_items(var)]


def code_labels(var):
    return {str(item.get("id")): str(item.get("text")) for item in value_items(var)}


def data(table, selections):
    body = {
        "table": table,
        "format": "JSONSTAT",
        "lang": "da",
        "variables": [
            {"code": code, "values": list(values)} for code, values in selections.items()
        ],
    }
    return get_json(f"{API_ROOT}/data", method="POST", body=body)


def category_positions(category):
    index = category.get("index")
    if isinstance(index, dict):
        return {str(code): int(pos) for code, pos in index.items()}
    if isinstance(index, list):
        return {str(code): pos for pos, code in enumerate(index)}
    labels = category.get("label")
    if isinstance(labels, dict):
        return {str(code): pos for pos, code in enumerate(labels)}
    raise RuntimeError("JSON-stat kategori mangler index")


def category_labels(category):
    labels = category.get("label")
    if isinstance(labels, dict):
        return {str(code): str(label) for code, label in labels.items()}
    positions = category_positions(category)
    return {code: code for code in positions}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace("\u00a0", "").replace(" ", "")
        if text.lower() in {"", "-", ".", "..", "null", "none", "nan"}:
            return None
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        value = float(text)
    result = float(value)
    if not math.isfinite(result):
        return None
    return int(result) if result.is_integer() else round(result, 6)


def records(payload):
    if not isinstance(payload, dict):
        raise RuntimeError("Uventet JSON-stat svar")
    dataset = payload.get("dataset", payload)
    dims = dataset.get("dimension")
    if not isinstance(dims, dict):
        raise RuntimeError("JSON-stat svar mangler dimension")
    ids = dataset.get("id") or dims.get("id")
    sizes = dataset.get("size") or dims.get("size")
    values = dataset.get("value")
    if not isinstance(ids, list) or not isinstance(sizes, list):
        raise RuntimeError("JSON-stat svar mangler id/size")
    positions = {dim: category_positions(dims[dim]["category"]) for dim in ids}
    labels = {dim: category_labels(dims[dim]["category"]) for dim in ids}
    code_by_pos = {
        dim: [code for code, _ in sorted(pos.items(), key=lambda item: item[1])]
        for dim, pos in positions.items()
    }
    total = 1
    for size in sizes:
        total *= int(size)

    def value_at(index):
        if isinstance(values, list):
            return values[index] if index < len(values) else None
        if isinstance(values, dict):
            return values.get(str(index), values.get(index))
        return None

    output = []
    for flat in range(total):
        rest = flat
        coords = [0] * len(ids)
        for idx in range(len(ids) - 1, -1, -1):
            size = int(sizes[idx])
            coords[idx] = rest % size
            rest //= size
        row = {"value": number(value_at(flat))}
        for dim, coord in zip(ids, coords):
            code = code_by_pos[dim][coord]
            row[dim] = code
            row[f"{dim}__label"] = labels[dim].get(code, code)
        output.append(row)
    return output, dataset
