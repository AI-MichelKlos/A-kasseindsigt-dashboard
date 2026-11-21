#!/usr/bin/env python3
"""Build static, crawlable graph-share pages and deterministic PNG topic cards.

Run from any directory: python scripts/build_share_pages.py [--check]
Requires Pillow and DejaVu Sans (fonts-dejavu-core on Ubuntu). Cards deliberately
contain no data, so a topic card cannot misrepresent a visitor's selected filters.

Share pages intentionally have no og:url or rel=canonical. Their full URL may
contain a valid personal view in ?pv=. A fixed canonical URL would identify a
different view and could cause a sharing service to discard those parameters.
The fetched URL remains the identifier. Metadata and images are available in
the original HTTP response; no JavaScript is needed to discover the preview.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
from pathlib import Path
import re
import sys

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SITE = "https://ai-michelklos.github.io/A-kasseindsigt-dashboard/"
WIDTH, HEIGHT = 1200, 630
SCALE = 2
COLORS = {
    "background": "#F4F6F2",
    "ink": "#0F2B36",
    "green": "#6B9E78",
    "dark_green": "#3D6B47",
    "muted": "#51645C",
    "line": "#DDE5DC",
    "white": "#FFFFFF",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    paths = [
        Path("/usr/share/fonts/truetype/dejavu") / name,
        Path("/usr/share/fonts/dejavu") / name,
    ]
    for path in paths:
        if path.is_file():
            return ImageFont.truetype(str(path), size * SCALE)
    raise SystemExit("Installér fonts-dejavu-core for at bygge forhåndsbillederne.")


def wrap_words(text: str, face: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        if face.getlength(word) > max_width * SCALE:
            raise ValueError(f"Ordet er for bredt til kortet: {word}")
        candidate = f"{line} {word}".strip()
        if line and face.getlength(candidate) > max_width * SCALE:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def make_image(title: str, overview: bool = False) -> bytes:
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), COLORS["background"])
    draw = ImageDraw.Draw(image)

    def box(coords: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(value * SCALE for value in coords)

    def text(x: int, y: int, value: str, size: int, color: str, bold: bool = False) -> None:
        draw.text((x * SCALE, y * SCALE), value, font=font(size, bold), fill=COLORS[color], anchor="lt")

    draw.rectangle(box((0, 0, WIDTH, 12)), fill=COLORS["green"])
    text(72, 67, "A-KASSEINDSIGT", 25, "dark_green", True)
    text(72, 112, "INTERAKTIVE TAL OM A-KASSER OG ARBEJDSMARKEDET", 18, "muted")

    title_size = 58
    while True:
        try:
            lines = wrap_words(title, font(title_size, True), 1056)
        except ValueError:
            lines = [""] * 4
        if len(lines) <= 3:
            break
        title_size -= 2
        if title_size < 42:
            raise ValueError(f"Titlen kan ikke være på kortet: {title}")
    line_height = round(title_size * 1.22)
    for index, line in enumerate(lines):
        text(72, 186 + index * line_height, line, title_size, "ink", True)

    action = "Åbn det interaktive dashboard" if overview else "Åbn den interaktive graf"
    action_width = round(font(25, True).getlength(action) / SCALE)
    button_right = 72 + action_width + 98
    draw.rounded_rectangle(box((72, 447, button_right, 512)), radius=12 * SCALE, fill=COLORS["dark_green"])
    text(94, 467, action, 25, "white", True)
    arrow_x = button_right - 36
    draw.line([(arrow_x - 10) * SCALE, 480 * SCALE, (arrow_x + 8) * SCALE, 480 * SCALE], fill=COLORS["white"], width=3 * SCALE)
    draw.line([(arrow_x + 1) * SCALE, 473 * SCALE, (arrow_x + 8) * SCALE, 480 * SCALE, (arrow_x + 1) * SCALE, 487 * SCALE], fill=COLORS["white"], width=3 * SCALE)

    draw.line(box((72, 548, 1128, 548)), fill=COLORS["line"], width=SCALE)
    text(72, 574, "A-kasseindsigt · Danske A-kasser", 22, "muted")
    image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def make_page(chart: dict[str, str], image_hash: str) -> str:
    escape = lambda value: html.escape(value, quote=True)
    title = escape(chart["title"])
    description = escape(chart["description"])
    chart_id = escape(chart["id"])
    image_url = escape(f"{SITE}assets/share/{chart['slug']}.png?v={image_hash}")
    local_image = escape(f"../../assets/share/{chart['slug']}.png")
    direct_link = escape(f"../../?chart={chart['id']}#graf-{chart['id']}")
    alt = escape(f"{chart['title']}. Åbn den interaktive graf i A-kasseindsigt fra Danske A-kasser.")
    return f'''<!doctype html>
<html lang="da">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | A-kasseindsigt</title>
  <meta name="description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="da_DK">
  <meta property="og:site_name" content="A-kasseindsigt · Danske A-kasser">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:secure_url" content="{image_url}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{alt}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{image_url}">
  <meta name="twitter:image:alt" content="{alt}">
  <style>
    :root {{ color-scheme: light; font-family: "Segoe UI", Arial, sans-serif; color: #0f2b36; background: #f4f6f2; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; border-top: 8px solid #6b9e78; }}
    main {{ max-width: 900px; margin: 48px auto; padding: 0 24px 36px; }}
    .brand {{ color: #3d6b47; font-weight: 700; }}
    h1 {{ font-size: clamp(1.8rem, 4vw, 2.8rem); line-height: 1.18; overflow-wrap: anywhere; margin: 24px 0 16px; }}
    p {{ font-size: 1.1rem; line-height: 1.6; max-width: 70ch; }}
    .preview {{ display: block; width: 100%; height: auto; border-radius: 12px; margin: 28px 0; border: 1px solid #dde5dc; }}
    .button {{ display: inline-block; background: #3d6b47; color: #fff; text-decoration: none; font-weight: 700; padding: 16px 22px; border-radius: 8px; line-height: 1.4; }}
    .button:hover {{ background: #2b5233; }}
    a:focus-visible {{ outline: 3px solid #0f2b36; outline-offset: 4px; }}
    .note {{ color: #51645c; font-size: .98rem; }}
    @media (max-width: 480px) {{ main {{ margin-top: 28px; padding-inline: 18px; }} .button {{ display: block; text-align: center; }} }}
  </style>
</head>
<body data-chart="{chart_id}">
  <main>
    <p class="brand">A-kasseindsigt · Danske A-kasser</p>
    <h1>{title}</h1>
    <p>{description}</p>
    <a class="button" id="open-chart" href="{direct_link}">Åbn grafen i A-kasseindsigt</a>
    <p class="note" id="share-note">Grafen åbnes automatisk med de filtre, der følger med linket. Du kan ændre visningen i dashboardet.</p>
    <noscript><p class="note">Aktivér JavaScript for at gendanne delte filtre og bruge dashboardets interaktive grafer.</p></noscript>
    <img class="preview" src="{local_image}" width="1200" height="630" alt="{alt}">
  </main>
  <script src="../../assets/share-landing.js"></script>
</body>
</html>
'''


def load_charts() -> list[dict[str, str]]:
    manifest = json.loads((ROOT / "config/share-charts.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not isinstance(manifest.get("charts"), list):
        raise ValueError("Ukendt manifestformat")
    charts = manifest["charts"]
    seen_ids, seen_slugs = set(), set()
    for chart in charts:
        for key in ("id", "slug", "title", "description", "section"):
            if not isinstance(chart.get(key), str) or not chart[key].strip():
                raise ValueError(f"Mangler {key} i manifestet")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", chart["id"]):
            raise ValueError(f"Ugyldigt graf-id: {chart['id']}")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", chart["slug"]):
            raise ValueError(f"Ugyldig slug: {chart['slug']}")
        if chart["id"] in seen_ids or chart["slug"] in seen_slugs:
            raise ValueError("Dobbelt graf-id eller slug i manifestet")
        seen_ids.add(chart["id"])
        seen_slugs.add(chart["slug"])
    canvas_ids = set(re.findall(r'<canvas\b[^>]*\bid=[\"\']([^\"\']+)[\"\']', (ROOT / "index.html").read_text(encoding="utf-8")))
    if canvas_ids != seen_ids:
        raise ValueError(f"Grafmanifest afviger fra dashboardet: {sorted(canvas_ids ^ seen_ids)}")
    return charts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Kontrollér, at genererede filer svarer til manifestet")
    args = parser.parse_args()
    outputs: dict[Path, bytes] = {}
    charts = load_charts()
    for chart in charts:
        image = make_image(chart["title"])
        image_hash = hashlib.sha256(image).hexdigest()[:12]
        outputs[ROOT / "share" / chart["slug"] / "index.html"] = make_page(chart, image_hash).encode("utf-8")
        outputs[ROOT / "assets/share" / f"{chart['slug']}.png"] = image
    outputs[ROOT / "assets/share/overblik.png"] = make_image("Tal og indsigter om a-kasserne", overview=True)
    mismatch = []
    for path, data in outputs.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                mismatch.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)
    if mismatch:
        print("Kør python scripts/build_share_pages.py. Filerne er ikke ajour:", file=sys.stderr)
        print("\n".join(mismatch), file=sys.stderr)
        return 1
    operation = "Kontrolleret" if args.check else "Genereret"
    print(f"{operation}: {len(charts)} delingssider, {len(charts) + 1} PNG-forhåndsbilleder (1200 x 630).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
