#!/usr/bin/env python3
"""Generate a synthetic crop-leaf sample image for smoke-testing the API.

    python scripts/make_sample.py                 # -> data/sample.jpg
    curl -X POST http://localhost:8000/api/detect -F "file=@data/sample.jpg"
"""
import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def make_image(size: int, seed: int = 7) -> Image.Image:
    """A green 'leaf' with dark lesions and a tiny 'pest' dot."""
    rng = random.Random(seed)
    img = Image.new("RGB", (size, size), (96, 156, 96))  # field green
    draw = ImageDraw.Draw(img)

    # A couple of leaf shapes (ellipses) in different greens.
    for _ in range(3):
        x = rng.randint(0, size // 2)
        y = rng.randint(0, size // 2)
        w = rng.randint(size // 3, size // 2)
        h = rng.randint(size // 5, size // 3)
        shade = rng.randint(90, 140)
        draw.ellipse((x, y, x + w, y + h), fill=(shade, shade + 40, shade - 10))

    # Dark lesion spots (simulated disease).
    for _ in range(14):
        x = rng.randint(0, size - 20)
        y = rng.randint(0, size - 20)
        r = rng.randint(3, 12)
        draw.ellipse((x, y, x + r * 2, y + r * 2), fill=(60, 40, 20))

    # A small dark 'pest' body with legs.
    cx, cy = rng.randint(size // 2, size - 40), rng.randint(size // 2, size - 40)
    draw.ellipse((cx, cy, cx + 14, cy + 18), fill=(20, 20, 20))
    draw.line((cx, cy + 8, cx - 10, cy - 4), fill=(20, 20, 20), width=2)
    draw.line((cx + 14, cy + 8, cx + 24, cy - 4), fill=(20, 20, 20), width=2)

    return img


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "data" / "sample.jpg")
    p.add_argument("--size", type=int, default=640, help="Square image side in px.")
    args = p.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    make_image(args.size).save(output, format="JPEG")
    print(f"Sample image written to {output}")


if __name__ == "__main__":
    main()
