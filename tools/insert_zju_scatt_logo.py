"""Crop and export the verified ImageGen logo replacement."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "generated_figures"
TARGET_PATH = OUTPUT_DIR / "08_zju_scatt_workflow_compact.png"
OUTPUT_PATH = OUTPUT_DIR / "08_zju_scatt_workflow_with_logo.png"
IMAGEGEN_EDIT = Path(
    r"C:\Users\15803\.codex\generated_images\01a0387a-f603-7ff3-a963-19c826b8957e\exec-463a16be-6e88-4c16-8c7d-9a8e98855a72.png"
)


def content_bbox(image: Image.Image, threshold: int = 12) -> tuple[int, int, int, int]:
    """Return the non-white artwork bounds of the edited figure."""

    rgb = image.convert("RGB")
    white = Image.new("RGB", rgb.size, "white")
    diff = ImageChops.difference(rgb, white)
    mask = diff.convert("L").point(lambda value: 255 if value > threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError("The supplied logo contains no detectable artwork")
    return bbox


def finalize() -> Path:
    if not IMAGEGEN_EDIT.exists():
        raise FileNotFoundError(f"ImageGen edit was not found: {IMAGEGEN_EDIT}")

    figure = Image.open(IMAGEGEN_EDIT).convert("RGB")

    # Crop only the outer blank canvas, retaining a balanced white margin.
    left, top, right, bottom = content_bbox(figure)
    pad = 22
    crop_box = (
        max(0, left - pad),
        max(0, top - pad),
        min(figure.width, right + pad),
        min(figure.height, bottom + pad),
    )
    figure = ImageOps.expand(figure.crop(crop_box), border=18, fill="white")

    target_width = 2400
    scale = target_width / figure.width
    figure = figure.resize((target_width, round(figure.height * scale)), Image.Resampling.LANCZOS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure.save(OUTPUT_PATH, format="PNG", optimize=True)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(finalize())
