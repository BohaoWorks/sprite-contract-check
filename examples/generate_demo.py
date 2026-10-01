"""Generate original, synthetic eight-frame sprites and small offline reports.

Run from the repository root after installing the package. No Aseprite needed.
Every source index is supplied by this generator, never inferred by the checker.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from PIL import Image, ImageDraw

from sprite_contract_check import compare, load_atlas
from sprite_contract_check.report import render_html

DEST = Path(__file__).resolve().parent / "demo"


def sprite(number: int) -> Image.Image:
    image = Image.new("RGBA", (20, 20))
    draw = ImageDraw.Draw(image)
    body = (105, 230, 192, 255) if number < 4 else (119, 163, 255, 255)
    rise = number % 2
    draw.rectangle((4, 5 - rise, 15, 13 - rise), fill=body)
    draw.rectangle((7, 3 - rise, 12, 4 - rise), fill=body)
    draw.rectangle((6, 7 - rise, 7, 8 - rise), fill=(12, 16, 24, 255))
    draw.rectangle((12, 7 - rise, 13, 8 - rise), fill=(12, 16, 24, 255))
    draw.rectangle((8, 11 - rise, 11, 11 - rise), fill=(38, 92, 86, 255))
    draw.rectangle((4 + number % 3, 14 - rise, 7 + number % 3, 16 - rise), fill=body)
    draw.rectangle((12 - number % 3, 14 - rise, 15 - number % 3, 16 - rise), fill=body)
    if number >= 4:
        draw.point((16, 5 + number % 3), fill=(255, 213, 124, 255))
    return image


def write_export(name: str, numbers: list[int], *, repacked: bool = False, timing: bool = False, pixel: bool = False, metadata_only: bool = False) -> None:
    columns = 2 if repacked else 4
    sheet = Image.new("RGBA", (columns * 20, ((len(numbers) + columns - 1) // columns) * 20))
    order = list(reversed(numbers)) if repacked else list(numbers)
    frames, indices = [], {}
    for place, number in enumerate(order):
        pixels = sprite(number)
        if pixel and number == 4:
            pixels.putpixel((12, 7), (255, 87, 119, 255))
        left, top, right, bottom = pixels.getchannel("A").getbbox()
        tile = pixels.crop((left, top, right, bottom))
        x, y = (place % columns) * 20 + 1, (place // columns) * 20 + 1
        sheet.paste(tile, (x, y))
        frame_name = f'{"idle" if number < 4 else "pulse"}/{number:03d}'
        indices[frame_name] = number
        frames.append({"filename": frame_name, "frame": {"x": x, "y": y, "w": tile.width, "h": tile.height},
                       "rotated": False, "trimmed": True,
                       "spriteSourceSize": {"x": left, "y": top, "w": tile.width, "h": tile.height},
                       "sourceSize": {"w": 20, "h": 20}, "duration": 180 if timing and number == 1 else 100})
    tags = [{"name": "idle", "from": 0, "to": 2 if 3 not in numbers else 3, "direction": "forward"},
            {"name": "pulse", "from": 4, "to": 7, "direction": "pingpong"}]
    meta = {"app": "https://www.aseprite.org/" if repacked or metadata_only else "http://www.aseprite.org/",
            "version": "synthetic-demo", "image": name + ".png", "format": "RGBA8888",
            "size": {"w": sheet.width, "h": sheet.height}, "scale": "1", "frameTags": tags}
    frame_data = {f["filename"]: {k: v for k, v in f.items() if k != "filename"} for f in frames} if repacked else frames
    (DEST / f"{name}.json").write_text(json.dumps({"frames": frame_data, "meta": meta}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (DEST / f"{name}-indices.json").write_text(json.dumps(indices, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    sheet.save(DEST / f"{name}.png")


def generate() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    numbers = list(range(8))
    write_export("before", numbers)
    write_export("repacked", numbers, repacked=True)
    write_export("metadata", numbers, metadata_only=True)
    write_export("timing", numbers, repacked=True, timing=True)
    write_export("pixel", numbers, repacked=True, pixel=True)
    write_export("deleted", [0, 1, 2, 4, 5, 6, 7], repacked=True)
    write_export("changed", [0, 1, 2, 4, 5, 6, 7], repacked=True, timing=True, pixel=True)
    before = load_atlas(DEST / "before.json", DEST / "before.png", indices=json.loads((DEST / "before-indices.json").read_text()))
    for name in ("repacked", "changed"):
        after = load_atlas(DEST / f"{name}.json", DEST / f"{name}.png", indices=json.loads((DEST / f"{name}-indices.json").read_text()))
        result = compare(before, after)
        (DEST / f"{name}-report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        (DEST / f"{name}-report.html").write_text(render_html(result, before, after), encoding="utf-8", newline="\n")
    print("Generated seven synthetic cases and two offline reports.")


if __name__ == "__main__":
    generate()
