"""Generate traceable ZJU-SCATT figures from local source material.

The overview uses the imagegen-generated scientific illustration as a visual base.
The remaining figures are deliberately drawn with Pillow so exact code, labels,
coordinates, and validation values remain faithful to the repository.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated_figures"
IMAGEGEN_BASE = (
    Path(r"C:\Users\15803\.codex\generated_images\01a0387a-f603-7ff3-a963-19c826b8957e")
    / "exec-abe0d134-e663-4bde-b19f-f40e68154b52.png"
)
PHASE5 = ROOT / "phase5_validation_output" / "phase5_interpolation_validation.png"
PHASE9 = ROOT / "phase9_validation_output" / "phase9_workflow_validation.png"
OBSERVED_PSD = ROOT / "examples" / "data" / "observed_psd_example.csv"

COLORS = {
    "navy": "#0B2342",
    "blue": "#1769AA",
    "cyan": "#19A7B8",
    "teal": "#128C8C",
    "green": "#3FAF65",
    "orange": "#F39C35",
    "purple": "#7A64A5",
    "red": "#D45454",
    "ink": "#17324D",
    "muted": "#58708A",
    "grid": "#D7E0E9",
    "line": "#9BB2C8",
    "panel": "#FFFFFF",
    "soft": "#EEF5F8",
    "bg": "#F7FAFC",
    "pass": "#217A45",
    "pass_bg": "#E8F6ED",
    "warn_bg": "#FFF4DF",
}


def font(size: int, *, mono: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = []
    if mono:
        candidates += [r"C:\Windows\Fonts\consolab.ttf", r"C:\Windows\Fonts\consola.ttf"]
    elif bold:
        candidates += [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\seguisb.ttf"]
    else:
        candidates += [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuil.ttf"]
    candidates += [r"C:\Windows\Fonts\arial.ttf"]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box, radius=18, fill=None, outline=None, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text(draw, xy, value, size=28, fill=None, *, bold=False, mono=False, anchor=None):
    draw.text(
        xy,
        str(value),
        font=font(size, mono=mono, bold=bold),
        fill=fill or COLORS["ink"],
        anchor=anchor,
    )


def wrapped(draw, xy, value, width, size=26, fill=None, *, bold=False, mono=False, line_gap=8):
    f = font(size, mono=mono, bold=bold)
    words = str(value).split()
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=f) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    y = xy[1]
    for line in lines:
        draw.text((xy[0], y), line, font=f, fill=fill or COLORS["ink"])
        y += size + line_gap
    return y


def title_block(draw, title_value, subtitle, width, *, accent=COLORS["cyan"]):
    text(draw, (70, 48), "ZJU-SCATT / GENERATED FIGURE", 24, COLORS["muted"], bold=True)
    text(draw, (70, 92), title_value, 54, COLORS["navy"], bold=True)
    text(draw, (70, 162), subtitle, 25, COLORS["muted"])
    draw.line((70, 208, width - 70, 208), fill=accent, width=5)


def panel(draw, box, *, fill=COLORS["panel"], outline=COLORS["grid"], radius=22, width=2):
    rounded(draw, box, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw, start, end, fill=COLORS["blue"], width=7, head=18):
    draw.line((start[0], start[1], end[0], end[1]), fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - head * math.cos(angle - math.pi / 6), end[1] - head * math.sin(angle - math.pi / 6))
    right = (end[0] - head * math.cos(angle + math.pi / 6), end[1] - head * math.sin(angle + math.pi / 6))
    draw.polygon([end, left, right], fill=fill)


def pill(draw, box, label, *, fill=COLORS["soft"], ink=COLORS["blue"], size=22):
    rounded(draw, box, radius=18, fill=fill, outline=None)
    text(draw, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), label, size, ink, bold=True, anchor="mm")


def badge(draw, xy, label, *, passed=True):
    fill = COLORS["pass_bg"] if passed else COLORS["warn_bg"]
    ink = COLORS["pass"] if passed else COLORS["orange"]
    w = int(draw.textlength(label, font=font(22, bold=True)) + 48)
    pill(draw, (xy[0], xy[1], xy[0] + w, xy[1] + 48), label, fill=fill, ink=ink, size=22)


def fit_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.copy().convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, COLORS["soft"])
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def overlay_shadow(base: Image.Image, box, radius=22):
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    d.rounded_rectangle(box, radius=radius, fill=(11, 35, 66, 35))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    base.paste(shadow, (0, 0), shadow)


def chart_frame(draw, box, x_label, y_label, *, x_ticks=None, y_ticks=None, title=None):
    x0, y0, x1, y1 = box
    panel(draw, box, fill=COLORS["panel"], outline=COLORS["grid"], radius=16)
    if title:
        text(draw, (x0 + 24, y0 + 20), title, 26, COLORS["navy"], bold=True)
    left = x0 + 105
    top = y0 + 74
    right = x1 - 38
    bottom = y1 - 88
    for i in range(6):
        yy = top + (bottom - top) * i / 5
        draw.line((left, yy, right, yy), fill=COLORS["grid"], width=2)
    for i in range(6):
        xx = left + (right - left) * i / 5
        draw.line((xx, top, xx, bottom), fill=COLORS["grid"], width=2)
    draw.line((left, top, left, bottom), fill=COLORS["ink"], width=3)
    draw.line((left, bottom, right, bottom), fill=COLORS["ink"], width=3)
    if x_ticks:
        for i, tick in enumerate(x_ticks):
            xx = left + (right - left) * i / max(1, len(x_ticks) - 1)
            text(draw, (xx, bottom + 18), tick, 18, COLORS["muted"], anchor="ma")
    if y_ticks:
        for i, tick in enumerate(y_ticks):
            yy = bottom - (bottom - top) * i / max(1, len(y_ticks) - 1)
            text(draw, (left - 18, yy), tick, 18, COLORS["muted"], anchor="ra")
    text(draw, ((left + right) // 2, y1 - 30), x_label, 20, COLORS["muted"], anchor="ma")
    text(draw, (x0 + 28, (top + bottom) // 2), y_label, 20, COLORS["muted"], anchor="mm")
    return left, top, right, bottom


def map_linear(value, lo, hi, start, end):
    if hi == lo:
        return (start + end) / 2
    return start + (value - lo) / (hi - lo) * (end - start)


def map_log(value, lo, hi, start, end):
    return map_linear(math.log10(value), math.log10(lo), math.log10(hi), start, end)


def draw_line_chart(draw, frame, xs, ys, *, color, log_x=False, log_y=False, x_bounds=None, y_bounds=None, width=5, dots=True):
    left, top, right, bottom = frame
    x_bounds = x_bounds or (min(xs), max(xs))
    y_bounds = y_bounds or (min(ys), max(ys))
    points = []
    for x, y in zip(xs, ys):
        px = map_log(x, *x_bounds, left, right) if log_x else map_linear(x, *x_bounds, left, right)
        py = bottom - (map_log(y, *y_bounds, top, bottom) - top) if log_y else map_linear(y, *y_bounds, bottom, top)
        points.append((px, py))
    draw.line(points, fill=color, width=width, joint="curve")
    if dots:
        for px, py in points:
            draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=color, outline=COLORS["panel"], width=2)
    return points


def table(draw, box, headers, rows, widths, *, header_fill=COLORS["navy"], row_fills=None, font_size=22, row_height=76):
    x0, y0, x1, y1 = box
    ncols = len(headers)
    xs = [x0]
    for width in widths:
        xs.append(xs[-1] + width)
    draw.rectangle((x0, y0, x1, y0 + row_height), fill=header_fill)
    for i, head in enumerate(headers):
        text(draw, (xs[i] + 18, y0 + row_height // 2), head, font_size, "#FFFFFF", bold=True, anchor="lm")
    for r, row in enumerate(rows):
        top = y0 + row_height * (r + 1)
        fill = row_fills[r] if row_fills else (COLORS["panel"] if r % 2 == 0 else COLORS["soft"])
        draw.rectangle((x0, top, x1, top + row_height), fill=fill)
        for c, value in enumerate(row):
            wrapped(draw, (xs[c] + 18, top + 14), value, widths[c] - 30, font_size, COLORS["ink"], bold=(c == 0), line_gap=3)
    for xx in xs:
        draw.line((xx, y0, xx, y0 + row_height * (len(rows) + 1)), fill=COLORS["grid"], width=2)
    for r in range(len(rows) + 2):
        yy = y0 + r * row_height
        draw.line((x0, yy, x1, yy), fill=COLORS["grid"], width=2)


def add_footer(draw, width, height, source_text):
    draw.line((70, height - 72, width - 70, height - 72), fill=COLORS["grid"], width=2)
    text(draw, (70, height - 52), source_text, 18, COLORS["muted"])
    text(draw, (width - 70, height - 52), "content locked to local source", 18, COLORS["muted"], anchor="ra")


def make_overview():
    image = Image.open(IMAGEGEN_BASE).convert("RGB")
    draw = ImageDraw.Draw(image)
    w, h = image.size
    ribbon = Image.new("RGBA", (w, 86), (11, 35, 66, 232))
    image.paste(ribbon, (0, 0), ribbon)
    draw = ImageDraw.Draw(image)
    text(draw, (42, 24), "ZJU-SCATT INTERFACE", 30, "#FFFFFF", bold=True)
    text(draw, (42, 57), "architecture · external connections · optical database hierarchy", 18, "#C6E8F3")

    labels = [
        ((180, 80, 490, 127), "USER ENTRY", "Python API / CLI", COLORS["blue"]),
        ((180, 286, 545, 334), "SCIENTIFIC ENGINE", "registry · adapters · interpolation · bulk", COLORS["teal"]),
        ((180, 504, 560, 552), "DELIVERY", "NetCDF4 / HDF5 · plots · provenance", COLORS["blue"]),
        ((1280, 42, 1515, 93), "EXTERNAL SOURCE", "remote L1 database", COLORS["blue"]),
        ((1280, 490, 1515, 540), "LOCAL CACHE", "verified files + manifests", COLORS["teal"]),
        ((86, 760, 525, 819), "RI-GRID NATIVE", "black carbon · super-spheroid", COLORS["blue"]),
        ((830, 760, 1398, 819), "WAVELENGTH-NATIVE", "sea salt · ice · sulfate · nitrate · organic carbon · water cloud", COLORS["green"]),
    ]
    for box, kicker, body, color in labels:
        x0, y0, x1, y1 = box
        rounded(draw, box, radius=12, fill=(255, 255, 255, 236), outline=color, width=2)
        text(draw, (x0 + 12, y0 + 9), kicker, 13, color, bold=True)
        text(draw, (x0 + 12, y0 + 30), body, 13, COLORS["ink"])
    out = OUT / "01_interface_overview.png"
    image.save(out, quality=95)
    return out


def make_function_map():
    w, h = 2400, 1600
    image = Image.new("RGB", (w, h), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    title_block(draw, "Function map", "Public modules and representative entry points from the active modular interface", w, accent=COLORS["blue"])
    rows = [
        ("auth", "register · session · doctor", "Direct registration, browser-token import, session validation"),
        ("catalog", "browse · list · search · estimate · metadata", "Translate scientific constraints into database selections"),
        ("download", "download · resume · cache", "Resumable downloads and automatic local storage"),
        ("retrieval", "retrieve_data · resolve_particle_sources", "High-level parameter requests and source selection"),
        ("planning", "build_dependency_queries · prepare_scheme_dependencies", "Compile schemes into deterministic queries and manifests"),
        ("size_distribution", "SizeDistribution · RemapReport", "Normalize sizes, validate PSDs, conservative remapping"),
        ("refractive_index", "RefractiveIndexTable · resolve_grid_refractive_indices", "Resolve wavelength tables into native RI coordinates"),
        ("interpolation", "interpolate_single_particle_optics · interpolate_from_sources", "Generate traceable single-particle optical products"),
        ("bulk", "calculate_bulk_optics · build_bulk_scheme · combine_bulk_optics", "PSD integration, ensemble physics, and component assembly"),
        ("schemes / output", "load_scheme_config · write_bulk_scheme_netcdf · write_bulk_scheme_hdf5", "Typed schemes plus NetCDF4/HDF5 serialization and QA"),
        ("plotting", "scientific plotting helpers", "Optional plots for single-particle and bulk quantities"),
    ]
    table(draw, (70, 260, 2330, 1380), ["MODULE", "ENTRY POINTS", "RESPONSIBILITY"], rows, [370, 780, 1080], font_size=22, row_height=102)
    add_footer(draw, w, h, "Source: zju_scatt_interface/README.md, src/__init__.py")
    out = OUT / "02_function_map.png"
    image.save(out, quality=95)
    return out


def make_command_examples():
    w, h = 2400, 1600
    image = Image.new("RGB", (w, h), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    title_block(draw, "Command examples", "A complete local workflow: validate → plan → build → inspect", w, accent=COLORS["orange"])
    left = (70, 260, 1125, 1440)
    right = (1190, 260, 2330, 1440)
    panel(draw, left, fill=COLORS["navy"], outline=COLORS["navy"])
    panel(draw, right, fill=COLORS["panel"], outline=COLORS["grid"])
    text(draw, (105, 300), "LEFT / TERMINAL", 22, "#9EE9EE", bold=True)
    text(draw, (1225, 300), "RIGHT / GENERATED OUTPUT", 22, COLORS["blue"], bold=True)
    commands = [
        ("01", "zju-scatt scheme configs/bulk_scheme.example.json"),
        ("02", "zju-scatt scheme-sources configs/bulk_scheme.example.json \\\n  --workspace zju_scatt_data"),
        ("03", "zju-scatt psd-check configs/bulk_scheme.example.json"),
        ("04", "zju-scatt bulk-opt validate configs/bulk_scheme.example.json \\\n  --report validate.json"),
        ("05", "zju-scatt bulk-opt plan configs/bulk_scheme.example.json \\\n  --workspace zju_scatt_data --dry-run"),
        ("06", "zju-scatt bulk-opt build configs/bulk_scheme.example.json \\\n  --workspace zju_scatt_data --format netcdf4 \\\n  --report build_report.json"),
    ]
    y = 365
    for step, command in commands:
        pill(draw, (105, y, 175, y + 42), step, fill="#173C61", ink="#9EE9EE", size=19)
        lines = command.splitlines()
        for line in lines:
            text(draw, (205, y + 3), line, 21, "#E8F3F8", mono=True)
            y += 30
        y += 24
    text(draw, (105, 1240), "NORMALIZED SCHEME", 20, "#9EE9EE", bold=True)
    text(draw, (105, 1280), "Python / JSON → dependency plan →", 21, "#FFFFFF", mono=True)
    text(draw, (105, 1316), "single-particle optics → PSD integration", 21, "#FFFFFF", mono=True)
    output = fit_image(Image.open(PHASE9), (1010, 640))
    image.paste(output, (1250, 355))
    rounded(draw, (1250, 1025, 2270, 1158), radius=16, fill=COLORS["soft"], outline=COLORS["grid"], width=2)
    text(draw, (1280, 1052), "Phase 9 evidence", 22, COLORS["navy"], bold=True)
    text(draw, (1280, 1090), "Python → HDF5 and JSON + CLI → NetCDF4", 21, COLORS["ink"])
    badge(draw, (1250, 1200), "scientific_content_equivalent = true")
    text(draw, (1250, 1280), "Artifacts:", 21, COLORS["muted"], bold=True)
    text(draw, (1250, 1320), "phase9_python_product.h5", 21, COLORS["ink"], mono=True)
    text(draw, (1250, 1355), "phase9_cli_product.nc", 21, COLORS["ink"], mono=True)
    add_footer(draw, w, h, "Source: zju_scatt_interface/README.md, docs/SCHEME_API_AND_CLI.md, phase9_validation_output/")
    out = OUT / "03_command_examples_workflow.png"
    image.save(out, quality=95)
    return out


def make_interpolation_validation():
    w, h = 2400, 1600
    image = Image.new("RGB", (w, h), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    title_block(draw, "Refractive-index interpolation validation", "Two contracts: wavelength-native optics and refractive-index-grid optics", w, accent=COLORS["cyan"])
    left = (70, 260, 1160, 1415)
    right = (1240, 260, 2330, 1415)
    panel(draw, left, fill=COLORS["panel"])
    panel(draw, right, fill=COLORS["panel"])
    text(draw, (110, 300), "A / WAVELENGTH-BASED", 30, COLORS["blue"], bold=True)
    text(draw, (110, 347), "External RI table → physical wavelength product", 23, COLORS["muted"])
    # Wavelength table and interpolation rail.
    chart = chart_frame(draw, (110, 430, 1100, 820), "wavelength (µm)", "n and k", x_ticks=["0.50", "0.75", "1.00"], y_ticks=["1.50 / .01", "1.40 / .02", "1.30 / .03"], title="RefractiveIndexTable test")
    leftc, topc, rightc, bottomc = chart
    xs = [0.5, 1.0]
    n = [1.5, 1.3]
    k = [0.01, 0.03]
    draw_line_chart(draw, chart, xs, n, color=COLORS["blue"], x_bounds=(0.5, 1.0), y_bounds=(1.3, 1.5), width=6)
    text(draw, (leftc + 40, bottomc - 30), "k endpoints: 0.01 → 0.03", 18, COLORS["orange"], bold=True)
    tx = map_linear(0.75, 0.5, 1.0, leftc, rightc)
    ty = map_linear(1.4, 1.3, 1.5, bottomc, topc)
    draw.ellipse((tx - 13, ty - 13, tx + 13, ty + 13), fill=COLORS["green"], outline=COLORS["panel"], width=3)
    text(draw, (tx + 25, ty - 32), "target 0.75 µm", 20, COLORS["green"], bold=True)
    text(draw, (tx + 25, ty + 4), "n=1.40, k=0.02", 20, COLORS["ink"])
    pill(draw, (110, 875, 600, 925), "linear interpolation: PASS", fill=COLORS["pass_bg"], ink=COLORS["pass"], size=22)
    wrapped(draw, (110, 980), "Test contract: 0.50 µm → (1.50, 0.01); 1.00 µm → (1.30, 0.03); 0.75 µm returns (1.40, 0.02).", 970, 24, COLORS["ink"], line_gap=7)
    rounded(draw, (110, 1105, 1100, 1290), radius=18, fill=COLORS["soft"], outline=COLORS["grid"])
    text(draw, (140, 1136), "No extrapolation", 24, COLORS["navy"], bold=True)
    text(draw, (140, 1180), "target 1.10 µm → ValueError", 24, COLORS["red"], mono=True)
    text(draw, (140, 1222), "outside refractive-index table coverage", 21, COLORS["muted"])

    text(draw, (1280, 300), "B / RI-GRID-BASED", 30, COLORS["teal"], bold=True)
    text(draw, (1280, 347), "wavelength wrapper → native mr / mi lookup", 23, COLORS["muted"])
    nodes = [
        ("user wavelength", "750 nm"),
        ("normalize", "0.75 µm"),
        ("external table", "n=1.40, k=0.02"),
        ("native query", "mr / mi + shape"),
        ("optical product", "Cext, ssa, g, Pij"),
    ]
    y = 455
    for i, (head, body) in enumerate(nodes):
        box = (1340, y, 2230, y + 105)
        fill = COLORS["soft"] if i % 2 == 0 else "#F3FBF6"
        panel(draw, box, fill=fill, outline=COLORS["grid"], radius=16)
        text(draw, (1380, y + 22), head, 23, COLORS["muted"], bold=True)
        text(draw, (1380, y + 60), body, 28, COLORS["navy"], bold=True, mono=(i in {1, 2, 3}))
        if i < len(nodes) - 1:
            arrow(draw, (1785, y + 108), (1785, y + 150), fill=COLORS["teal"], width=5, head=14)
        y += 155
    rounded(draw, (1280, 1220, 2290, 1350), radius=18, fill="#F3FBF6", outline=COLORS["green"], width=2)
    text(draw, (1310, 1248), "Advanced override", 24, COLORS["green"], bold=True)
    text(draw, (1310, 1290), "mr=1.45, mi=0.01 → explicit_refractive_index", 21, COLORS["ink"], mono=True)
    add_footer(draw, w, h, "Source: tests/test_refractive_index.py, docs/REFRACTIVE_INDEX_RESOLUTION.md, interpolation_modes_report.json")
    out = OUT / "04_refractive_index_interpolation_validation.png"
    image.save(out, quality=95)
    return out


def make_profiles():
    w, h = 2400, 1600
    image = Image.new("RGB", (w, h), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    title_block(draw, "Profiles in custom optical schemes", "Each particle is calculated independently, then written to its own output group", w, accent=COLORS["green"])
    rows = [
        ("dust", "super_spheroid", "fixed 1.50 + 0.01i", "roundness 2.0 / 2.5 (0.4 / 0.6); AR 1.5", "veq"),
        ("black_carbon", "encapsulated_fractal_aggregates_black_carbon", "fixed two-material RI", "Df 1.8 / 2.4 (0.5 / 0.5); Vf 0.2", "veq"),
        ("sea_salt", "coated_super_spheroid_seasalt", "database", "RH 0.5 / 0.8 (0.3 / 0.7); deliquescence", "maxd"),
        ("ice", "super_spheroid_ice", "database_temperature; 250 K", "(roundness, AR, weight) = (2.0, 1.0, .4); (2.5, 1.5, .6)", "veq"),
        ("sulfate", "sphere_sulfate", "database", "RH 0.8", "veq"),
        ("nitrate", "sphere_nitrate", "database", "RH 0.8", "veq"),
        ("organic_carbon", "sphere_organic_carbon", "database", "RH 0.8", "veq"),
        ("water_cloud", "sphere_water_cloud", "database", "wavelength only", "veq"),
    ]
    table(draw, (70, 270, 2330, 1100), ["COMPONENT", "DATABASE PROFILE", "RI STRATEGY", "SHAPE / ENVIRONMENT", "SIZE"], rows, [330, 670, 420, 680, 200], font_size=20, row_height=98)
    text(draw, (70, 1165), "Independent calculation", 26, COLORS["navy"], bold=True)
    cards = [
        ("1", "normalize", "units · PSD · profile parameters", COLORS["blue"]),
        ("2", "resolve", "native source coordinates + provenance", COLORS["teal"]),
        ("3", "integrate", "Cext / Csca / Cabs over each PSD", COLORS["orange"]),
        ("4", "write", "separate component group", COLORS["green"]),
    ]
    x = 70
    for i, (number, head, body, color) in enumerate(cards):
        box = (x, 1230, x + 500, 1400)
        panel(draw, box, fill=COLORS["panel"], outline=color, radius=18, width=3)
        pill(draw, (x + 22, 1254, x + 76, 1308), number, fill=color, ink="#FFFFFF", size=22)
        text(draw, (x + 102, 1256), head, 26, color, bold=True)
        wrapped(draw, (x + 102, 1304), body, 360, 20, COLORS["ink"], line_gap=5)
        if i < len(cards) - 1:
            arrow(draw, (x + 510, 1320), (x + 557, 1320), fill=COLORS["line"], width=5, head=13)
        x += 575
    rounded(draw, (70, 1415, 2330, 1500), radius=18, fill=COLORS["navy"], outline=COLORS["navy"])
    text(draw, (105, 1440), "OUTPUT / all_profile_reference.h5", 21, "#9EE9EE", bold=True, anchor="lm")
    text(draw, (2220, 1440), "no implicit mixture", 18, "#F6D59E", bold=True, anchor="rm")
    text(draw, (105, 1475), "8 root groups: /dust · /black_carbon · /sea_salt · /ice · /sulfate · /nitrate · /organic_carbon · /water_cloud", 16, "#FFFFFF", mono=True, anchor="lm")
    add_footer(draw, w, h, "Source: configs/bulk_scheme.all_profiles.example.json, docs/BULK_CALCULATION.md, docs/OUTPUT_FORMATS.md")
    out = OUT / "05_profiles_custom_optical_schemes.png"
    image.save(out, quality=95)
    return out


def draw_shape(draw, center, rx, ry, *, fill, outline=COLORS["navy"], angle=0):
    cx, cy = center
    points = []
    for i in range(48):
        t = 2 * math.pi * i / 48
        x = rx * math.cos(t)
        y = ry * math.sin(t)
        ca, sa = math.cos(angle), math.sin(angle)
        points.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    draw.polygon(points, fill=fill, outline=outline)


def make_shape_ri_combination():
    w, h = 2400, 1450
    image = Image.new("RGB", (w, h), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    title_block(draw, "Shape and refractive index stay independent", "Independent scientific inputs converge only at the optical calculation boundary", w, accent=COLORS["purple"])
    left = (70, 270, 1100, 1250)
    right = (1300, 270, 2330, 1250)
    panel(draw, left, fill=COLORS["panel"], outline=COLORS["orange"], width=3)
    panel(draw, right, fill=COLORS["panel"], outline=COLORS["blue"], width=3)
    text(draw, (110, 315), "SHAPE ENSEMBLE", 28, COLORS["orange"], bold=True)
    text(draw, (110, 360), "WeightedShapeEnsemble", 23, COLORS["muted"], mono=True)
    draw_shape(draw, (335, 610), 125, 80, fill="#FFE3B2", angle=0.1)
    draw_shape(draw, (760, 610), 86, 145, fill="#FFCD82", angle=-0.35)
    pill(draw, (170, 780, 500, 840), "roundness=2.0 · AR=1.0 · w=.4", fill="#FFF3DE", ink=COLORS["orange"], size=20)
    pill(draw, (555, 780, 1010, 840), "roundness=2.5 · AR=1.5 · w=.6", fill="#FFF3DE", ink=COLORS["orange"], size=20)
    text(draw, (160, 900), "correlated shape states", 23, COLORS["ink"], bold=True)
    wrapped(draw, (160, 950), "The two members are retained separately, with normalized weights recorded in the calculation result.", 850, 23, COLORS["muted"], line_gap=7)
    text(draw, (1340, 315), "REFRACTIVE INDEX", 28, COLORS["blue"], bold=True)
    text(draw, (1340, 360), "FixedRefractiveIndex / TableRefractiveIndex", 23, COLORS["muted"], mono=True)
    draw.ellipse((1480, 500, 1665, 685), fill="#CFE8FF", outline=COLORS["blue"], width=4)
    text(draw, (1572, 595), "n", 42, COLORS["blue"], bold=True, anchor="mm")
    draw.ellipse((1870, 500, 2055, 685), fill="#FFE0C5", outline=COLORS["orange"], width=4)
    text(draw, (1962, 595), "k", 42, COLORS["orange"], bold=True, anchor="mm")
    pill(draw, (1370, 780, 1745, 840), "real = 1.50", fill="#E6F3FF", ink=COLORS["blue"], size=22)
    pill(draw, (1800, 780, 2185, 840), "imaginary = 0.01", fill="#FFF1E6", ink=COLORS["orange"], size=22)
    wrapped(draw, (1370, 900), "RI can come from a fixed native override or an external wavelength table; the shape calculation remains reusable.", 850, 23, COLORS["muted"], line_gap=7)
    arrow(draw, (1100, 760), (1290, 760), fill=COLORS["purple"], width=8, head=24)
    text(draw, (1145, 700), "combine", 21, COLORS["purple"], bold=True, anchor="mm")
    rounded(draw, (505, 1215, 1895, 1325), radius=18, fill=COLORS["navy"], outline=COLORS["navy"])
    text(draw, (1200, 1270), "single-particle optics → PSD integration → bulk result", 26, "#FFFFFF", bold=True, anchor="mm")
    text(draw, (1200, 1350), "Cext / Csca / Cabs combine linearly; ssa = βsca / βext; g and Pij are scattering-weighted", 19, COLORS["muted"], anchor="ma")
    add_footer(draw, w, h, "Source: docs/BULK_CALCULATION.md, docs/SCHEME_API_AND_CLI.md, configs/bulk_scheme.all_profiles.example.json")
    out = OUT / "06_shape_and_refractive_index_independent.png"
    image.save(out, quality=95)
    return out


def load_scheme_psd():
    # Values are copied from configs/bulk_scheme.example.py, the runnable scheme.
    return {
        "ice": ([5.0, 10.0, 20.0, 40.0, 80.0], [50.0, 200.0, 400.0, 250.0, 100.0]),
        "sulfate": ([0.03, 0.05, 0.08, 0.12, 0.20, 0.35], [100.0, 600.0, 1800.0, 1500.0, 750.0, 250.0]),
    }


def make_custom_scheme_generation():
    w, h = 2400, 1600
    image = Image.new("RGB", (w, h), COLORS["bg"])
    draw = ImageDraw.Draw(image)
    title_block(draw, "Generation of a custom optical scheme", "One scheme retains size, shape, RI, and integrated properties as inspectable evidence", w, accent=COLORS["orange"])
    panels = [(70, 260, 1160, 880), (1240, 260, 2330, 880), (70, 950, 1160, 1450), (1240, 950, 2330, 1450)]
    for box in panels:
        panel(draw, box, fill=COLORS["panel"], outline=COLORS["grid"])
    # Panel 1: single-particle curves from the interpolation docs example.
    f1 = chart_frame(draw, panels[0], "radius (µm)", "cross section (m²)", x_ticks=["0.1", "1", "10"], y_ticks=["1e-14", "1e-12", "1e-10"], title="Single-particle optical properties")
    xs = [0.1, 1.0, 10.0]
    for ys, color in [([1e-14, 1e-12, 1e-10], COLORS["blue"]), ([8e-15, 8e-13, 8e-11], COLORS["orange"]), ([2e-15, 2e-13, 2e-11], COLORS["green"])]:
        draw_line_chart(draw, f1, xs, ys, color=color, log_x=True, log_y=True, x_bounds=(0.1, 10.0), y_bounds=(1e-15, 2e-10), width=5)
    text(draw, (190, 790), "Cext", 20, COLORS["blue"], bold=True)
    text(draw, (330, 790), "Csca", 20, COLORS["orange"], bold=True)
    text(draw, (470, 790), "Cabs = Cext − Csca", 20, COLORS["green"], bold=True)
    # Panel 2: exact PSD values from the runnable scheme.
    f2 = chart_frame(draw, panels[1], "radius (µm)", "dndr (cm⁻³)", x_ticks=["0.03", "0.1", "1", "10", "80"], y_ticks=["1", "100", "1000"], title="Particle-size distributions")
    psds = load_scheme_psd()
    draw_line_chart(draw, f2, *psds["ice"], color=COLORS["blue"], log_x=True, log_y=True, x_bounds=(0.03, 80), y_bounds=(10, 2000), width=5)
    draw_line_chart(draw, f2, *psds["sulfate"], color=COLORS["orange"], log_x=True, log_y=True, x_bounds=(0.03, 80), y_bounds=(10, 2000), width=5)
    pill(draw, (1310, 780, 1450, 828), "ice", fill="#E6F3FF", ink=COLORS["blue"], size=19)
    pill(draw, (1480, 780, 1635, 828), "sulfate", fill="#FFF1E6", ink=COLORS["orange"], size=19)
    # Panel 3: shape filter subplot.
    text(draw, (105, 990), "Shape filtering", 26, COLORS["navy"], bold=True)
    text(draw, (105, 1035), "accepted shape states from the custom scheme", 21, COLORS["muted"])
    x0, y0, x1, y1 = (200, 1120, 1050, 1390)
    draw.line((x0, y1, x1, y1), fill=COLORS["ink"], width=3)
    draw.line((x0, y0, x0, y1), fill=COLORS["ink"], width=3)
    for val in [1.0, 1.5, 2.0, 2.5]:
        xx = map_linear(val, 0.8, 2.8, x0, x1)
        draw.line((xx, y0, xx, y1), fill=COLORS["grid"], width=2)
        text(draw, (xx, y1 + 18), f"{val:.1f}", 18, COLORS["muted"], anchor="ma")
    for val in [1.0, 1.5, 2.0, 2.5, 3.0]:
        yy = map_linear(val, 1.0, 3.0, y1, y0)
        draw.line((x0, yy, x1, yy), fill=COLORS["grid"], width=2)
        text(draw, (x0 - 18, yy), f"{val:.1f}", 18, COLORS["muted"], anchor="ra")
    # Roundness on y; aspect ratio on x; points include scheme members and a filtered state.
    shape_points = [(1.0, 2.0, .4), (1.5, 2.5, .6), (1.0, 2.0, .5)]
    for ar, rnd, weight in shape_points:
        xx = map_linear(ar, 0.8, 2.8, x0, x1)
        yy = map_linear(rnd, 1.0, 3.0, y1, y0)
        color = COLORS["orange"] if weight == .6 else COLORS["blue"]
        draw.ellipse((xx - 18, yy - 18, xx + 18, yy + 18), fill=color, outline=COLORS["panel"], width=3)
        text(draw, (xx + 30, yy - 12), f"w={weight:g}", 18, color, bold=True)
    text(draw, ((x0 + x1) // 2, 1424), "aspect_ratio", 19, COLORS["muted"], anchor="ma")
    text(draw, (120, (y0 + y1) // 2), "roundness", 19, COLORS["muted"], anchor="mm")
    # Panel 4: actual Phase 9 validation displays.
    text(draw, (1275, 990), "Integrated optical properties", 26, COLORS["navy"], bold=True)
    text(draw, (1275, 1035), "stored bulk coefficients and intensive properties", 21, COLORS["muted"])
    img = fit_image(Image.open(PHASE9), (980, 350))
    image.paste(img, (1275, 1090))
    badge(draw, (1275, 1460 - 52), "Phase 9: scientific_content_equivalent = true")
    add_footer(draw, w, h, "Source: docs/INTERPOLATION.md, configs/bulk_scheme.example.py, phase9_validation_output/phase9_workflow_validation.png")
    out = OUT / "07_custom_optical_scheme_generation.png"
    image.save(out, quality=95)
    return out


def write_manifest(paths: Sequence[Path]):
    manifest = {
        "generated_with": "Pillow + imagegen visual base",
        "source_root": str(ROOT),
        "assets": [
            {"file": str(path.relative_to(ROOT)), "status": "generated"} for path in paths
        ],
        "source_material": [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/PARTICLE_PROFILES.md",
            "docs/INTERPOLATION.md",
            "docs/BULK_CALCULATION.md",
            "docs/OUTPUT_FORMATS.md",
            "docs/SCHEME_API_AND_CLI.md",
            "docs/REFRACTIVE_INDEX_RESOLUTION.md",
            "configs/bulk_scheme.example.py",
            "configs/bulk_scheme.all_profiles.example.json",
            "tests/test_refractive_index.py",
            "phase5_validation_output/phase5_interpolation_validation.png",
            "phase9_validation_output/phase9_workflow_validation.png",
        ],
    }
    (OUT / "figure_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [
        make_overview(),
        make_function_map(),
        make_command_examples(),
        make_interpolation_validation(),
        make_profiles(),
        make_shape_ri_combination(),
        make_custom_scheme_generation(),
    ]
    write_manifest(paths)
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
