"""Build public graph cards for link previews from the dashboard's existing data.

The static image is explicitly the national default (I alt, up to 36 months),
while the personal-view query is applied after opening the shared link. No
network, API key or browser is needed. Use --check to validate source freshness,
complete chart coverage, metadata, image dimensions and output hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import textwrap
from html.parser import HTMLParser

BASE = Path(__file__).resolve().parents[1]
SITE = "https://ai-michelklos.github.io/A-kasseindsigt-dashboard/"
IMAGE_SIZE = (1200, 630)
FORMAT_VERSION = 1
COLORS = ["#3d6b47", "#4a90c4", "#9a5b34", "#8C7FCF"]
INK = "#2B211B"
MUTED = "#6f6258"
PAPER = "#f7f1ea"
GRID = "#E6DDD2"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def format_period(value):
    value = str(value or "")
    months = ["jan.", "feb.", "mar.", "apr.", "maj", "jun.", "jul.", "aug.", "sep.", "okt.", "nov.", "dec."]
    if match := re.fullmatch(r"(\d{4})M(\d{2})", value):
        month = int(match[2])
        if 1 <= month <= 12:
            return f"{months[month - 1]} {match[1]}"
    if match := re.fullmatch(r"(\d{4})Q0?([1-4])", value):
        return f"{match[2]}. kvt. {match[1]}"
    if match := re.fullmatch(r"(\d{4})Y\d{2}", value):
        return match[1]
    return value


def shift_month(value, offset):
    match = re.fullmatch(r"(\d{4})M(\d{2})", value)
    if not match:
        raise ValueError(f"Ugyldig RM01AK-måned: {value}")
    absolute = int(match[1]) * 12 + int(match[2]) - 1 + offset
    year, month = divmod(absolute, 12)
    return f"{year:04d}M{month + 1:02d}"


def series(block, key, count=36, indexed=False):
    labels = block.get("labels", [])[-count:]
    values = block.get(key, [])[-count:]
    if len(labels) != len(values):
        raise ValueError(f"Labels og værdier har forskellig længde: {key}")
    values = [value if finite(value) else None for value in values]
    if indexed:
        first = next((value for value in values if value not in (None, 0)), None)
        values = [value / first * 100 if first is not None and value is not None else None for value in values]
    return labels, values


def category(block, normalize=False):
    items = block.get("items", [])
    labels = [item["label"] for item in items]
    values = [item.get("value") if finite(item.get("value")) else None for item in items]
    if normalize:
        # A missing count must not silently become zero or change the denominator.
        total = sum(values) if values and all(v is not None for v in values) else 0
        values = [100 * value / total if total else None for value in values]
    return labels, values


def make_specs(registry, data, results):
    fund = data["funds"][data["meta"]["totalFundCode"]]
    jobs = fund.get("jobindsats", {})
    source_status = data["meta"].get("sourceStatus", {})
    specs = []
    line_defs = {
        "membersRawChart": (fund.get("members", {}), "values", "AUA01", False, False, 36),
        "membersIndexChart": (fund.get("members", {}), "values", "AUA01", False, True, 36),
        "unempChart": (fund.get("unemploymentRate", {}), "values", "AUP03", True, False, 36),
        "longRawChart": (jobs.get("longTerm", {}), "persons", "jobLongTerm", False, False, 36),
        "longIndexChart": (jobs.get("longTerm", {}), "persons", "jobLongTerm", False, True, 36),
        "dagChart": (jobs.get("dagpenge", {}), "fulltime", "jobDagpenge", False, False, 36),
        "gradCountChart": (jobs.get("graduates", {}), "persons", "jobDimittend", False, False, 36),
        "gradChart": (jobs.get("graduates", {}), "share", "jobDimittend", True, False, 36),
        "afterlonChart": (jobs.get("afterlon", {}), "persons", "jobAfterlon", False, False, 36),
        "afterlonContribChart": (jobs.get("afterlonContrib", {}), "share", "jobAfterlonContrib", True, False, 3),
        "sanctionsTotalChart": (jobs.get("sanctions", {}), "total", "jobSanctions", False, False, 12),
        "sanctionsShareChart": (jobs.get("sanctions", {}), "shareSanctioned", "jobSanctions", True, False, 12),
        "sanctionsAvgChart": (jobs.get("sanctions", {}), "avgPerSanctioned", "jobSanctions", False, False, 12),
        "jobSearchShareChart": (jobs.get("jobSearch", {}), "shareWithApplication", "jobJobSearch", True, False, 36),
    }
    category_defs = {
        "consChart": (jobs.get("benefitConsumption", {}), "jobDagpengeforbrug", True, "barh"),
        "survChart": (jobs.get("survival", {}), "jobOverlevelse", False, "bar"),
        "completedDurationChart": (jobs.get("completedDuration", {}), "jobCompletedDuration", True, "barh"),
        "statusChart": (jobs.get("statusAfter3m", {}), "jobStatusAfter", False, "barh"),
    }
    for definition in registry["charts"]:
        chart_id = definition["id"]
        spec = dict(definition, type="line", percent=False, indexed=False, labels=[], datasets=[], note="")
        key = ""
        if chart_id in line_defs:
            block, field, key, percent, indexed, count = line_defs[chart_id]
            labels, values = series(block, field, count, indexed)
            spec.update(labels=labels, datasets=[{"label": "I alt", "values": values}], percent=percent, indexed=indexed)
            spec["period"] = next((label for label, value in reversed(list(zip(labels, values))) if value is not None), "")
        elif chart_id in category_defs:
            block, key, normalize, kind = category_defs[chart_id]
            labels, values = category(block, normalize)
            spec.update(type=kind, percent=True, labels=labels, datasets=[{"label": "I alt", "values": values}], period=block.get("period", ""))
            if chart_id == "survChart":
                spec["note"] = "Forløb påbegyndt i " + format_period(spec["period"])
            elif chart_id == "statusChart":
                spec["note"] = "Forløb afsluttet i " + format_period(spec["period"])
        elif chart_id == "ageChart":
            key = "AUA01"
            labels, values = category({"items": fund.get("profileAge", [])}, True)
            spec.update(type="bar", percent=True, labels=labels, datasets=[{"label": "I alt", "values": values}], period=source_status.get(key, {}).get("latestPeriod", ""))
        elif chart_id == "sanctionsTypeChart":
            key = "jobSanctions"
            block = jobs.get("sanctions", {})
            last = len(block.get("labels", [])) - 1
            labels = [item["label"] for item in block.get("types", [])]
            values = [item.get("values", [])[last] if last >= 0 and len(item.get("values", [])) > last else None for item in block.get("types", [])]
            spec.update(type="barh", labels=labels, datasets=[{"label": "I alt", "values": values}], period=(block.get("labels") or [""])[-1])
        elif chart_id in ("talkChart", "exhaustedChart"):
            key = "jobTalkForms" if chart_id == "talkChart" else "jobExhaustedRights"
            block = jobs.get("talkForms" if chart_id == "talkChart" else "exhaustedRights", {})
            labels = block.get("labels", [])[-36:]
            if chart_id == "talkChart":
                datasets = [{"label": name, "values": series(block, field)[1]} for name, field in [("Fysisk", "physical"), ("Telefon", "phone"), ("Video", "video"), ("Anden kontakt", "other")]]
            elif len(block.get("categories", [])) == 3:
                datasets = [{"label": item["label"], "values": series({"labels": block["labels"], "values": item["values"]}, "values")[1]} for item in block["categories"]]
            else:
                datasets = [{"label": "I alt", "values": series(block, "persons")[1]}]
            spec.update(labels=labels, datasets=datasets, period=labels[-1] if labels else "")
        elif chart_id == "rmMainChart":
            points = results.get("series", {}).get("three", {}).get("TOTAL", {})
            cohorts = sorted(points)[-36:]
            labels = [shift_month(cohort, 3) for cohort in cohorts]
            spec.update(labels=labels, percent=True, datasets=[{"label": "Efter 3 måneder", "values": [points[cohort] for cohort in cohorts]}], period=results.get("meta", {}).get("latestStatusMonth", ""), note="Efter 3 måneder. Månederne er opgørelsesmåneder.")
        else:
            raise ValueError(f"Graf mangler datadefinition: {chart_id}")
        metadata = source_status.get(key, {}) if key else results.get("meta", {})
        spec["source"] = metadata.get("source", "Jobindsats.dk / STAR")
        dataset = metadata.get("dataset", "")
        # Long report identifiers are not readable inside a 1200px image.
        spec["sourceLabel"] = spec["source"] + (f" ({dataset.upper()})" if dataset and len(dataset) < 20 else "")
        spec["sourceState"] = metadata.get("state", "unknown")
        if metadata.get("state") != "ok":
            spec["note"] = "Kildestatus: " + str(metadata.get("state", "ukendt"))
        specs.append(spec)
    return specs


def number_dk(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def render_image(spec):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    fig = Figure(figsize=(12, 6.3), dpi=100, facecolor=PAPER)
    FigureCanvasAgg(fig)
    fig.text(.045, .94, "A-KASSEINDSIGT", color="#9A5B34", weight="bold", size=14)
    title = "\n".join(textwrap.wrap(spec["title"], width=63, break_long_words=False))
    fig.text(.045, .87, title, va="top", color=INK, weight="bold", size=23, linespacing=1.12)
    period = format_period(spec.get("period"))
    meta = "Forhåndsbillede: I alt · Hele landet" + (" · " + period if period else "")
    fig.text(.045, .715, meta, color=MUTED, size=12)

    horizontal = spec["type"] == "barh"
    long_labels = max((len(label) for label in spec["labels"]), default=0) > 24
    left = .33 if horizontal and long_labels else .155 if horizontal else .10
    bottom = .24 if spec["type"] == "bar" else .225
    ax = fig.add_axes([left, bottom, .955 - left, .42], facecolor="white")
    ax.set_axisbelow(True)
    ax.grid(axis="x" if horizontal else "y", color=GRID, linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=10, length=0, pad=7)
    values_all = [value for dataset in spec["datasets"] for value in dataset["values"] if finite(value)]
    count = len(spec["labels"])
    if not values_all:
        ax.axis("off")
        ax.text(.5, .5, "Data er ikke tilgængelige i den seneste opgørelse.", transform=ax.transAxes, ha="center", va="center", color=MUTED, size=14)
    elif spec["type"] == "line":
        for index, dataset in enumerate(spec["datasets"]):
            values = [float(value) if finite(value) else float("nan") for value in dataset["values"]]
            ax.plot(range(count), values, color=COLORS[index % len(COLORS)], linewidth=2.8, label=dataset["label"])
            valid = [(i, value) for i, value in enumerate(values) if math.isfinite(value)]
            if valid:
                ax.plot(valid[-1][0], valid[-1][1], "o", color=COLORS[index % len(COLORS)], markersize=5)
        ticks = sorted({0, max(0, count - 1), *(round(i * (count - 1) / 4) for i in range(1, 4))})
        ax.set_xticks(ticks, [format_period(spec["labels"][i]) for i in ticks])
        ax.set_xlim(-.4, max(.5, count - .5))
        if len(spec["datasets"]) > 1:
            ax.legend(loc="lower left", bbox_to_anchor=(0, 1.015), frameon=False, ncol=min(4, len(spec["datasets"])), fontsize=10, labelcolor=MUTED, borderaxespad=0)
        # National snapshots use a visible zero origin except explicitly indexed
        # plots, which state their baseline in the title and axis unit.
        if not spec["indexed"]:
            ax.set_ylim(bottom=0)
        else:
            ax.set_ylim(bottom=min(80, math.floor(min(values_all) / 5) * 5))
    else:
        values = [float(value) if finite(value) else float("nan") for value in spec["datasets"][0]["values"]]
        labels = ["\n".join(textwrap.wrap(label, width=48 if horizontal else 15, break_long_words=False)) for label in spec["labels"]]
        if horizontal:
            ax.barh(range(count), values, color=COLORS[0], height=.66)
            ax.set_yticks(range(count), labels)
            ax.invert_yaxis()
            ax.set_xlim(left=0)
            if count > 9:
                ax.tick_params(axis="y", labelsize=9.5, pad=8)
        else:
            ax.bar(range(count), values, color=COLORS[0], width=.65)
            ax.set_xticks(range(count), labels)
            ax.set_ylim(bottom=0)
            if count > 8:
                ax.tick_params(axis="x", labelsize=8.5)
    axis = ax.xaxis if horizontal else ax.yaxis
    decimals = 2 if spec["id"] == "sanctionsAvgChart" else 1 if spec["percent"] else 0
    axis.set_major_formatter(FuncFormatter(lambda value, position: number_dk(value, decimals) + (" %" if spec["percent"] else "")))
    axis.set_major_locator(MaxNLocator(nbins=5, integer=not spec["percent"] and spec["id"] != "sanctionsAvgChart"))
    if spec["percent"] and values_all:
        if horizontal:
            ax.set_xlim(right=max(5, ax.get_xlim()[1]))
        else:
            ax.set_ylim(top=max(5, ax.get_ylim()[1]))
    note = spec.get("note", "")
    if note:
        fig.text(.045, .143, note, color=MUTED, size=9)
    fig.text(.045, .107, "Kilde: " + spec["sourceLabel"], color=MUTED, size=10)
    fig.text(.045, .053, "Åbn grafen i dashboardet med de valgte filtre", color=INK, weight="bold", size=13)
    fig.text(.955, .053, "→", ha="right", color="#9A5B34", size=21)
    stream = io.BytesIO()
    fig.savefig(stream, format="png", dpi=100, metadata={"Software": "A-kasseindsigt preview builder"}, facecolor=PAPER)
    return stream.getvalue()


def render_overview():
    from PIL import Image, ImageDraw, ImageFont
    from matplotlib import font_manager
    image = Image.new("RGB", IMAGE_SIZE, PAPER)
    draw = ImageDraw.Draw(image)
    regular = font_manager.findfont("DejaVu Sans")
    bold = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold"))
    draw.rectangle((0, 0, 1200, 17), fill="#9A5B34")
    draw.text((64, 70), "A-KASSEINDSIGT", fill="#9A5B34", font=ImageFont.truetype(bold, 25))
    draw.text((64, 144), "Tal om a-kasserne", fill=INK, font=ImageFont.truetype(bold, 62))
    draw.text((64, 234), "Udforsk grafer. Vælg a-kasse og geografi.", fill=MUTED, font=ImageFont.truetype(regular, 30))
    labels = ["Medlemmer", "Ledighed", "Dagpenge", "Job og uddannelse", "Samtaler", "Efterløn"]
    for index, label in enumerate(labels):
        x, y = 64 + (index % 3) * 365, 335 + (index // 3) * 84
        draw.rounded_rectangle((x, y, x + 343, y + 64), radius=12, fill="white", outline=GRID, width=2)
        draw.text((x + 20, y + 18), label, fill=INK, font=ImageFont.truetype(regular, 24))
    draw.text((64, 552), "Åbn det interaktive dashboard", fill=INK, font=ImageFont.truetype(bold, 29))
    stream = io.BytesIO()
    image.save(stream, "PNG", optimize=True)
    return stream.getvalue()


def share_html(spec, image_hash, *, relative_root="../../"):
    escape = lambda value: html.escape(str(value), quote=True)
    chart_id = spec["id"]
    page_url = SITE + "del/" + chart_id + "/"
    image_url = SITE + "assets/share/" + chart_id + ".png?v=" + image_hash[:12]
    title = spec["title"] + " | A-kasseindsigt"
    description = spec["description"] + " Linket åbner grafen med de valgte filtre."
    image_alt = spec["title"] + ". Forhåndsbillede for I alt, hele landet. Valgte filtre vises efter åbning."
    target = relative_root + "?graf=" + chart_id + "#graf-" + chart_id
    return f'''<!doctype html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{escape(page_url)}">
<meta property="og:type" content="website">
<meta property="og:locale" content="da_DK">
<meta property="og:site_name" content="A-kasseindsigt">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{escape(page_url)}">
<meta property="og:image" content="{escape(image_url)}">
<meta property="og:image:secure_url" content="{escape(image_url)}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{escape(image_alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(title)}">
<meta name="twitter:description" content="{escape(description)}">
<meta name="twitter:image" content="{escape(image_url)}">
<meta name="twitter:image:alt" content="{escape(image_alt)}">
<style>
body{{margin:0;background:#f7f1ea;color:#2B211B;font:18px/1.55 Arial,sans-serif}}
main{{max-width:850px;padding:32px 24px;margin:auto}}
h1{{font-size:clamp(1.6rem,4vw,2.4rem);line-height:1.2}}
.label{{color:#9A5B34;font-weight:700;letter-spacing:.08em}}
img{{display:block;width:100%;height:auto;border-radius:10px}}
a{{display:inline-block;margin:20px 0;padding:12px 18px;background:#4a3428;color:#fff;border-radius:7px;font-weight:700;text-decoration:none}}
a:focus-visible{{outline:3px solid #146298;outline-offset:4px}}
.note{{color:#6f6258;font-size:.9rem}}
</style>
</head>
<body>
<main>
<p class="label">A-KASSEINDSIGT</p>
<h1>{escape(spec['title'])}</h1>
<p>{escape(spec['description'])}</p>
<img src="{relative_root}assets/share/{escape(chart_id)}.png?v={image_hash[:12]}" width="1200" height="630" alt="{escape(image_alt)}">
<a id="open-dashboard" href="{escape(target)}">Åbn grafen i dashboardet</a>
<p class="note">Forhåndsbilledet viser I alt for hele landet. Linkets valgte filtre anvendes i dashboardet.</p>
<noscript><p>Dashboardets grafer og delte filtre kræver JavaScript. Aktivér JavaScript, og åbn linket igen.</p></noscript>
</main>
<script src="{relative_root}assets/share-redirect.js?v=1"></script>
</body>
</html>
'''


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.canvas_ids = set()
        self.refresh = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[attrs.get("property", attrs.get("name", ""))] = attrs.get("content", "")
            self.refresh |= attrs.get("http-equiv", "").lower() == "refresh"
        if tag == "canvas":
            self.canvas_ids.add(attrs.get("id"))


def validate_registry(registry):
    charts = registry.get("charts", [])
    identifiers = [entry["id"] for entry in charts]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Dubleret graf-id i delingsregistret")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", value) for value in identifiers):
        raise ValueError("Ugyldigt graf-id i delingsregistret")
    parser = MetadataParser()
    parser.feed((BASE / "index.html").read_text())
    if set(identifiers) != parser.canvas_ids:
        raise ValueError(f"Delingsregister og dashboard er forskellige: {set(identifiers) ^ parser.canvas_ids}")


def input_digest(specs):
    return digest({"version": FORMAT_VERSION, "specs": specs, "generator": file_digest(Path(__file__)), "redirect": file_digest(BASE / "assets/share-redirect.js")})


def write_if_changed(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != content:
        path.write_bytes(content)


def validate_outputs(output, specs, inputs):
    from PIL import Image
    manifest_path = output / "assets/share/manifest.json"
    if not manifest_path.exists():
        raise ValueError("Forhåndsbilleder mangler. Kør scripts/build_share_pages.py")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("inputsSha256") != inputs:
        raise ValueError("Forhåndsbilleder er ikke ajour med data eller kode. Genopbyg dem.")
    for relative, expected in manifest["files"].items():
        path = output / relative
        if not path.is_file() or file_digest(path) != expected:
            raise ValueError(f"Manglende eller ændret genereret fil: {relative}")
    for spec in specs:
        chart_id = spec["id"]
        image = output / f"assets/share/{chart_id}.png"
        with Image.open(image) as preview:
            if preview.size != IMAGE_SIZE or preview.format != "PNG":
                raise ValueError(f"Forkert billedformat: {image}")
        if image.stat().st_size > 5_000_000:
            raise ValueError(f"For stort forhåndsbillede: {image}")
        for relative in (f"del/{chart_id}/index.html", f"share/{chart_id}.html"):
            parser = MetadataParser()
            page = output / relative
            parser.feed(page.read_text())
            if parser.refresh:
                raise ValueError("HTTP-equiv refresh må ikke erstatte grafens metadata")
            for key in ("og:title", "og:description", "og:url", "og:image", "og:image:alt", "twitter:card"):
                if not parser.meta.get(key):
                    raise ValueError(f"{page}: {key} mangler")
            if parser.meta["og:url"] != SITE + f"del/{chart_id}/":
                raise ValueError(f"Forkert kanonisk delings-URL: {page}")
            if not parser.meta["og:image"].startswith(SITE + f"assets/share/{chart_id}.png?v="):
                raise ValueError(f"Forkert forhåndsbillede: {page}")
    if manifest.get("chartCount") != len(specs):
        raise ValueError("Forkert antal grafer i manifest")


def build(output, specs, inputs):
    files = {}
    for spec in specs:
        image_path = output / f"assets/share/{spec['id']}.png"
        write_if_changed(image_path, render_image(spec))
        image_hash = file_digest(image_path)
        page_path = output / f"del/{spec['id']}/index.html"
        write_if_changed(page_path, share_html(spec, image_hash).encode())
        # Preserve previously published URLs while keeping one canonical graph
        # page and one current PNG. A relative root differs for the .html alias.
        legacy_path = output / f"share/{spec['id']}.html"
        write_if_changed(legacy_path, share_html(spec, image_hash, relative_root="../").encode())
        for path in (image_path, page_path, legacy_path):
            files[path.relative_to(output).as_posix()] = file_digest(path)
    overview = output / "assets/share/dashboard.png"
    write_if_changed(overview, render_overview())
    files[overview.relative_to(output).as_posix()] = file_digest(overview)
    manifest = {"version": FORMAT_VERSION, "chartCount": len(specs), "inputsSha256": inputs, "files": files,
                "preview": {"fund": "I alt", "geography": "Hele landet", "months": 36, "rmHorizon": "three"},
                "charts": [{"id": spec["id"], "period": spec.get("period"), "source": spec["sourceLabel"], "specSha256": digest(spec)} for spec in specs]}
    write_if_changed(output / "assets/share/manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    validate_outputs(output, specs, inputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Kontrollér genererede filer og aktuelle datadefinitioner uden at ændre filer")
    parser.add_argument("--output-dir", type=Path, default=BASE)
    args = parser.parse_args()
    registry = json.loads((BASE / "config/share-charts.json").read_text())
    data = json.loads((BASE / "data/dashboard-data.json").read_text())
    results = json.loads((BASE / "data/rm01ak-summary.json").read_text())
    validate_registry(registry)
    specs = make_specs(registry, data, results)
    inputs = input_digest(specs)
    if args.check:
        validate_outputs(args.output_dir, specs, inputs)
    else:
        build(args.output_dir, specs, inputs)
    print(f"OK: {len(specs)} delesider med gamle URL-aliaser, grafbilleder og dashboardbillede {'kontrolleret' if args.check else 'bygget'}")


if __name__ == "__main__":
    main()
