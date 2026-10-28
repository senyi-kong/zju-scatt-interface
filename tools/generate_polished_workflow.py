"""Finalize the ZJU-SCATT workflow schematic generated from the supplied references.

The structural concept is generated with ImageGen; this Python script performs the
deterministic publication export so the final title, sizing, and file path are stable.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "generated_figures"
OUTPUT_PATH = OUTPUT_DIR / "08_zju_scatt_workflow_polished.png"

IMAGEGEN_SOURCE = Path(
    r"C:\Users\15803\.codex\generated_images\01a0387a-f603-7ff3-a963-19c826b8957e\exec-be30ce36-bbbd-499e-bdff-fdc7facd49bf.png"
)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Use a consistent sans-serif font with a safe Windows fallback."""

    candidates = (
        Path(r"C:\Windows\Fonts\arialbd.ttf") if bold else Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf") if bold else Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\calibrib.ttf") if bold else Path(r"C:\Windows\Fonts\calibri.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def text_center(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, font, fill) -> None:
    box = draw.textbbox((0, 0), value, font=font)
    width = box[2] - box[0]
    draw.text((xy[0] - width / 2, xy[1]), value, font=font, fill=fill)


def finalize() -> Path:
    if not IMAGEGEN_SOURCE.exists():
        raise FileNotFoundError(f"ImageGen source was not found: {IMAGEGEN_SOURCE}")

    source = Image.open(IMAGEGEN_SOURCE).convert("RGB")

    # The ImageGen concept already has a strong 16:9 layout. Add a clean title band
    # and resize with Lanczos so the export is suitable for manuscript assembly.
    target_width = 2400
    scale = target_width / source.width
    content = source.resize((target_width, round(source.height * scale)), Image.Resampling.LANCZOS)
    title_band = 132
    footer_band = 58
    canvas = Image.new("RGB", (target_width, content.height + title_band + footer_band), "white")
    canvas.paste(content, (0, title_band))

    draw = ImageDraw.Draw(canvas)
    navy = "#12395C"
    muted = "#61768A"
    rule = "#D6E1EB"

    title_font = load_font(54, bold=True)
    subtitle_font = load_font(26, bold=False)
    footer_font = load_font(21, bold=False)

    draw.text((52, 22), "ZJU-SCATT interface workflow", font=title_font, fill=navy)
    draw.text(
        (54, 85),
        "From a scientific request to a traceable bulk-optics product",
        font=subtitle_font,
        fill=muted,
    )
    draw.line((52, title_band - 18, target_width - 52, title_band - 18), fill=rule, width=3)

    footer_y = canvas.height - footer_band + 12
    draw.line((52, footer_y - 9, target_width - 52, footer_y - 9), fill=rule, width=2)
    draw.text(
        (54, footer_y),
        "Detailed definitions of L0–L3 are provided in the accompanying table.",
        font=footer_font,
        fill=muted,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT_PATH, format="PNG", optimize=True)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(finalize())
