"""Crop and export the ImageGen-edited ZJU-SCATT workflow figure.

ImageGen performs the requested element removal; this Python step gives the
project a stable, tightly framed deliverable without adding new content.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "generated_figures"
OUTPUT_PATH = OUTPUT_DIR / "08_zju_scatt_workflow_compact.png"

IMAGEGEN_EDIT = Path(
    r"C:\Users\15803\.codex\generated_images\01a0387a-f603-7ff3-a963-19c826b8957e\exec-6712c6a2-b885-4aff-8678-5cce1442aa15.png"
)


def finalize() -> Path:
    if not IMAGEGEN_EDIT.exists():
        raise FileNotFoundError(f"ImageGen edit was not found: {IMAGEGEN_EDIT}")

    source = Image.open(IMAGEGEN_EDIT).convert("RGB")

    # Keep a small white margin around the surviving sources lane and workflow.
    cropped = source.crop((24, 92, 1542, 826))
    framed = ImageOps.expand(cropped, border=22, fill="white")

    target_width = 2400
    scale = target_width / framed.width
    final = framed.resize((target_width, round(framed.height * scale)), Image.Resampling.LANCZOS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final.save(OUTPUT_PATH, format="PNG", optimize=True)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(finalize())
