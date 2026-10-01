"""Strict Aseprite export loading and deterministic contract comparison.

Paths are supplied by the caller. Frame names and meta.image are never paths.
Source indices are explicit data; neither insertion order nor names infer them.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, UnidentifiedImageError

from . import __version__

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
MAX_ATLAS_PIXELS = 16 * 1024 * 1024
MAX_FRAME_PIXELS = 1024 * 1024
MAX_TOTAL_FRAME_PIXELS = 16 * 1024 * 1024
MAX_ATLAS_SIDE = 8192
MAX_FRAME_SIDE = 2048
MAX_FRAMES = 2048
IGNORED_METADATA = ["meta.app", "meta.image", "meta.version"]


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass
class Frame:
    name: str
    rect: tuple[int, int, int, int]
    trim: tuple[int, int, int, int]
    trimmed: bool
    duration: int
    index: int | None
    pixels: Image.Image
    digest: str
    extra: dict[str, Any]

    def contract(self) -> dict[str, Any]:
        return {
            "atlas_rect": list(self.rect), "trim_rect": list(self.trim),
            "trimmed": self.trimmed, "source_size": list(self.pixels.size),
            "duration_ms": self.duration, "source_index": self.index,
            "pixel_sha256": self.digest,
        }


@dataclass
class Atlas:
    frames: dict[str, Frame]
    tags: dict[str, dict[str, Any]]
    size: tuple[int, int]
    metadata: dict[str, Any]


def _fail(code: str, message: str) -> None:
    raise ContractError(code, message)


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("invalid_json", f"{where} must be an object")
    return value


def _integer(value: Any, where: str, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("invalid_value", f"{where} must be an integer in {minimum}..{maximum}")
    return value


def _name(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or "\x00" in value:
        _fail("invalid_name", f"{where} must be a nonempty name of at most 256 characters")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_key", f"duplicate JSON key: {key[:80]!r}")
        result[key] = value
    return result


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > 32:
        _fail("resource_limit", "JSON nesting exceeds 32 levels")
    if isinstance(value, dict):
        for key in value:
            _check_depth(key, depth + 1)
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)
    elif isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _fail("invalid_json", "JSON contains an unpaired Unicode surrogate")
    elif isinstance(value, float) and not math.isfinite(value):
        _fail("invalid_json", "JSON contains a nonfinite number")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _read(path: Path | str, limit: int, label: str) -> bytes:
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError:
        _fail("missing_file", f"{label} is missing or unreadable")
    if len(data) > limit:
        _fail("resource_limit", f"{label} exceeds the {limit}-byte limit")
    return data


def read_json(path: Path | str, label: str = "JSON") -> Any:
    data = _read(path, MAX_JSON_BYTES, label)
    try:
        value = json.loads(
            data.decode("utf-8-sig"), object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail("invalid_json", f"{label} contains NaN or Infinity"),
        )
    except ContractError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        _fail("invalid_json", f"{label} is not valid UTF-8 JSON")
    _check_depth(value)
    return value


def read_mapping(path: Path | str, *, indices: bool = False, label: str = "mapping") -> dict:
    result = _object(read_json(path, label), label)
    for key, value in result.items():
        _name(key, f"{label} key")
        if indices:
            _integer(value, f"{label} index")
        else:
            _name(value, f"{label} target")
    return result


def _rect(value: Any, where: str, *, size_only: bool = False) -> tuple:
    obj = _object(value, where)
    keys = ("w", "h") if size_only else ("x", "y", "w", "h")
    if set(obj) != set(keys):
        _fail("invalid_rect", f"{where} must contain exactly {', '.join(keys)}")
    return tuple(_integer(obj[k], f"{where}.{k}", 1 if k in ("w", "h") else 0) for k in keys)


def _png(path: Path | str, label: str) -> Image.Image:
    data = _read(path, MAX_PNG_BYTES, label)
    # Pillow reduces 16-bit PNG channels when converting to RGBA8. Inspect
    # IHDR rather than image.mode: RGB16 is already exposed as RGB by Pillow.
    if (len(data) >= 33 and data[:8] == b"\x89PNG\r\n\x1a\n"
            and data[8:16] == b"\x00\x00\x00\x0dIHDR" and data[24] == 16):
        _fail("unsupported_png", f"{label}: 16-bit PNG is unsupported; use an 8-bit or palette export")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
                w, h = image.size
                if w > MAX_ATLAS_SIDE or h > MAX_ATLAS_SIDE or w * h > MAX_ATLAS_PIXELS:
                    _fail("resource_limit", f"{label} dimensions exceed the atlas limit")
                if getattr(image, "n_frames", 1) != 1:
                    _fail("unsupported_png", f"{label}: animated PNG is unsupported")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
                return image.convert("RGBA")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        _fail("resource_limit", f"{label} exceeds Pillow's decompression limit")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        if isinstance(exc, ContractError):
            raise
        _fail("invalid_png", f"{label} is not a complete, valid PNG")


def _tags(raw: Any, frames: dict[str, Frame], label: str) -> dict:
    if not isinstance(raw, list) or len(raw) > MAX_FRAMES:
        _fail("invalid_tags", f"{label}.frameTags must be a bounded array")
    if raw and any(f.index is None for f in frames.values()):
        _fail("missing_source_index", f"{label}: tags require explicit source indices for every frame; supply an indices sidecar")
    by_index = {f.index: f.name for f in frames.values() if f.index is not None}
    tags = {}
    for entry in raw:
        tag = _object(entry, f"{label}.tag")
        name = _name(tag.get("name"), f"{label}.tag.name")
        if name in tags:
            _fail("duplicate_name", f"{label}: duplicate tag name {name!r}")
        start = _integer(tag.get("from"), f"{label}.tag.from")
        end = _integer(tag.get("to"), f"{label}.tag.to")
        direction = tag.get("direction", "forward")
        if direction not in ("forward", "reverse", "pingpong", "pingpong_reverse"):
            _fail("invalid_tags", f"{label}: unsupported tag direction")
        repeat = _integer(tag.get("repeat", 0), f"{label}.tag.repeat", maximum=65535)
        if start > end or end - start + 1 > len(frames) or any(i not in by_index for i in range(start, end + 1)):
            _fail("invalid_tags", f"{label}: tag {name!r} references absent source indices")
        tags[name] = {
            "from": start, "to": end, "direction": direction, "repeat": repeat,
            "members": [by_index[i] for i in range(start, end + 1)],
            "extra": {k: v for k, v in tag.items() if k not in {"name", "from", "to", "direction", "repeat"}},
        }
    return dict(sorted(tags.items()))


def load_atlas(json_path: Path | str, png_path: Path | str, *, indices: dict | None = None, label: str = "atlas") -> Atlas:
    document = _object(read_json(json_path, f"{label} JSON"), label)
    meta = _object(document.get("meta"), f"{label}.meta")
    image = _png(png_path, f"{label} PNG")
    if _rect(meta.get("size"), f"{label}.meta.size", size_only=True) != image.size:
        _fail("invalid_rect", f"{label}.meta.size does not match PNG dimensions")
    if meta.get("scale", "1") != "1":
        _fail("unsupported_export", f"{label}: scaled exports are unsupported; use scale 1")
    for key in ("layers", "slices"):
        if key in meta and meta[key] != []:
            _fail("unsupported_export", f"{label}: nonempty meta.{key} is unsupported in version 0.1")
    raw = document.get("frames")
    if isinstance(raw, list):
        entries = [(_object(f, f"{label}.frame").get("filename"), f) for f in raw]
    elif isinstance(raw, dict):
        entries = list(raw.items())
    else:
        _fail("invalid_json", f"{label}.frames must be an array or hash")
    if not 1 <= len(entries) <= MAX_FRAMES:
        _fail("resource_limit", f"{label} must contain 1..{MAX_FRAMES} frames")
    frames, total_pixels = {}, 0
    known = {"filename", "frame", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration", "index"}
    for raw_name, raw_frame in entries:
        name = _name(raw_name, f"{label}.frame name")
        if name in frames:
            _fail("duplicate_name", f"{label}: duplicate frame name {name!r}")
        frame = _object(raw_frame, f"{label}.frame")
        if "filename" in frame and frame["filename"] != name:
            _fail("invalid_name", f"{label}: hash key and filename disagree")
        if frame.get("rotated") is not False:
            _fail("unsupported_rotation", f"{label}: rotated must be false; rotation is unsupported")
        if type(frame.get("trimmed")) is not bool:
            _fail("invalid_value", f"{label}: trimmed must be a boolean")
        rect = _rect(frame.get("frame"), f"{label}.frame.rect")
        trim = _rect(frame.get("spriteSourceSize"), f"{label}.frame.spriteSourceSize")
        w, h = _rect(frame.get("sourceSize"), f"{label}.frame.sourceSize", size_only=True)
        x, y, rw, rh = rect
        tx, ty, tw, th = trim
        if x + rw > image.width or y + rh > image.height:
            _fail("invalid_rect", f"{label}: frame {name!r} extends outside the PNG")
        if (rw, rh) != (tw, th) or tx + tw > w or ty + th > h:
            _fail("invalid_trim", f"{label}: frame {name!r} has invalid trim dimensions or offset")
        if not frame["trimmed"] and trim != (0, 0, w, h):
            _fail("invalid_trim", f"{label}: untrimmed frame {name!r} must cover the source canvas")
        total_pixels += w * h
        if w > MAX_FRAME_SIDE or h > MAX_FRAME_SIDE or w * h > MAX_FRAME_PIXELS or total_pixels > MAX_TOTAL_FRAME_PIXELS:
            _fail("resource_limit", f"{label}: reconstructed sprites exceed the pixel budget")
        duration = _integer(frame.get("duration"), f"{label}.frame.duration", 1, 3_600_000)
        index = _integer(frame["index"], f"{label}.frame.index") if "index" in frame else None
        pixels = Image.new("RGBA", (w, h))
        pixels.paste(image.crop((x, y, x + rw, y + rh)), (tx, ty))
        # Hidden RGB at alpha zero has no rendered meaning. Preserve all nonzero alpha exactly.
        pixels.paste((0, 0, 0, 0), mask=pixels.getchannel("A").point(lambda a: 255 if a == 0 else 0))
        digest = hashlib.sha256(struct.pack(">II", w, h) + pixels.tobytes()).hexdigest()
        frames[name] = Frame(name, rect, trim, frame["trimmed"], duration, index, pixels, digest,
                             {k: v for k, v in frame.items() if k not in known})
    if indices is not None:
        if not isinstance(indices, dict) or set(indices) != set(frames):
            _fail("invalid_mapping", f"{label}: indices sidecar must name every exported frame exactly once")
        for name, index in indices.items():
            _integer(index, f"{label}.indices")
            if frames[name].index is not None and frames[name].index != index:
                _fail("invalid_mapping", f"{label}: sidecar disagrees with explicit frame.index")
            frames[name].index = index
    present = [f.index for f in frames.values() if f.index is not None]
    if present and len(present) != len(frames):
        _fail("missing_source_index", f"{label}: partial source indices are ambiguous")
    if len(set(present)) != len(present):
        _fail("invalid_mapping", f"{label}: duplicate source indices are unsupported")
    tags = _tags(meta.get("frameTags", []), frames, f"{label}.meta")
    excluded = {"app", "version", "image", "size", "frameTags", "scale", "layers", "slices"}
    metadata = {"meta": {k: v for k, v in meta.items() if k not in excluded},
                "root": {k: v for k, v in document.items() if k not in {"frames", "meta"}}}
    return Atlas(dict(sorted(frames.items())), tags, image.size, metadata)


def pixel_diff(before: Image.Image, after: Image.Image) -> tuple[Image.Image, int]:
    size = (max(before.width, after.width), max(before.height, after.height))
    old, new = Image.new("RGBA", size), Image.new("RGBA", size)
    old.paste(before)
    new.paste(after)
    channels = ImageChops.difference(old, new).split()
    mask = channels[0]
    for channel in channels[1:]:
        mask = ImageChops.lighter(mask, channel)
    mask = mask.point(lambda v: 255 if v else 0)
    diff = Image.new("RGBA", size)
    diff.paste((255, 87, 119, 255), mask=mask)
    return diff, mask.histogram()[255]


def compare(before: Atlas, after: Atlas, *, mode: str = "content", mapping: dict | None = None) -> dict:
    if mode not in ("content", "coordinates"):
        _fail("invalid_mode", "mode must be content or coordinates")
    mapping = {} if mapping is None else mapping
    if not isinstance(mapping, dict):
        _fail("invalid_mapping", "name mapping must be an object")
    for old, new in mapping.items():
        if old not in before.frames or not isinstance(new, str) or new not in after.frames:
            _fail("invalid_mapping", "name mapping references an absent frame")
    pairs = {old: mapping.get(old, old) for old in before.frames if old in mapping or old in after.frames}
    if len(set(pairs.values())) != len(pairs):
        _fail("invalid_mapping", "name mapping must be one-to-one, including unchanged names")
    removed = sorted(set(before.frames) - set(pairs))
    added = sorted(set(after.frames) - set(pairs.values()))
    records = []
    summary = {k: 0 for k in ("renamed", "pixels_changed", "duration_changed", "coordinates_moved", "packing_changed", "source_index_changed", "frame_metadata_changed")}
    for old, new in sorted(pairs.items()):
        a, b = before.frames[old], after.frames[new]
        changes = []
        for key, changed in (
            ("renamed", old != new), ("pixels_changed", a.digest != b.digest),
            ("duration_changed", a.duration != b.duration), ("coordinates_moved", a.rect != b.rect),
            ("packing_changed", (a.rect, a.trim, a.trimmed) != (b.rect, b.trim, b.trimmed)),
            ("source_index_changed", a.index != b.index), ("frame_metadata_changed", _canonical(a.extra) != _canonical(b.extra)),
        ):
            if changed:
                changes.append(key)
                summary[key] += 1
        incompatible = bool(set(changes) - {"coordinates_moved", "packing_changed"}) or (mode == "coordinates" and "packing_changed" in changes)
        records.append({"before": old, "after": new, "changes": changes, "incompatible": incompatible,
                        "before_contract": a.contract(), "after_contract": b.contract(),
                        "changed_pixel_count": pixel_diff(a.pixels, b.pixels)[1] if a.digest != b.digest else 0})
    for name in removed:
        records.append({"before": name, "after": None, "changes": ["removed"], "incompatible": True,
                        "before_contract": before.frames[name].contract(), "after_contract": None, "changed_pixel_count": None})
    for name in added:
        records.append({"before": None, "after": name, "changes": ["added"], "incompatible": True,
                        "before_contract": None, "after_contract": after.frames[name].contract(), "changed_pixel_count": None})
    tag_changes = []
    for name in sorted(set(before.tags) | set(after.tags)):
        a, b = before.tags.get(name), after.tags.get(name)
        mapped = {**a, "members": [pairs.get(n, n) for n in a["members"]]} if a else None
        if _canonical(mapped) != _canonical(b):
            tag_changes.append({"name": name, "before": a, "after": b})
    metadata_changed = _canonical(before.metadata) != _canonical(after.metadata)
    sheet_changed = before.size != after.size
    compatible = not (added or removed or tag_changes or metadata_changed or any(r["incompatible"] for r in records) or (mode == "coordinates" and sheet_changed))
    summary.update({"frames_before": len(before.frames), "frames_after": len(after.frames), "matched": len(pairs),
                    "added": len(added), "removed": len(removed), "tags_changed": len(tag_changes),
                    "metadata_changed": metadata_changed, "sheet_size_changed": sheet_changed})
    return {"schema_version": 1, "tool_version": __version__, "mode": mode,
            "status": "pass" if compatible else "changed", "compatible": compatible, "summary": summary,
            "ignored_metadata": IGNORED_METADATA, "sheet_sizes": {"before": list(before.size), "after": list(after.size)},
            "changes": {"added": added, "removed": removed, "tags": tag_changes,
                        "metadata": {"before": before.metadata, "after": after.metadata} if metadata_changed else None},
            "frames": records}
