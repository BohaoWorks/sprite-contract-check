from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from sprite_contract_check import ContractError, compare, load_atlas
from sprite_contract_check import core
from sprite_contract_check.cli import main
from sprite_contract_check.report import render_html


class Fixture:
    """Independent fixture: two 4x4 sprites, with exact expected pixel locations."""

    def __init__(self, root: Path):
        self.root = root
        self.sheet = Image.new("RGBA", (8, 4))
        self.sheet.putpixel((1, 1), (255, 0, 0, 255))
        self.sheet.putpixel((2, 1), (0, 128, 255, 128))
        self.sheet.putpixel((5, 2), (0, 255, 0, 255))
        self.doc = {"frames": [self.frame("red", 0), self.frame("green", 4)],
                    "meta": {"size": {"w": 8, "h": 4}, "app": "http://www.aseprite.org/",
                             "version": "1.0", "image": "not-used.png", "scale": "1", "format": "RGBA8888", "frameTags": []}}

    @staticmethod
    def frame(name: str, x: int) -> dict:
        return {"filename": name, "frame": {"x": x, "y": 0, "w": 4, "h": 4}, "rotated": False,
                "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": 4, "h": 4},
                "sourceSize": {"w": 4, "h": 4}, "duration": 100}

    def write(self, name: str, doc=None, image=None) -> tuple[Path, Path]:
        jp, pp = self.root / f"{name}.json", self.root / f"{name}.png"
        jp.write_text(json.dumps(self.doc if doc is None else doc), encoding="utf-8")
        (self.sheet if image is None else image).save(pp)
        return jp, pp

    def repacked(self) -> tuple[dict, Image.Image]:
        doc = copy.deepcopy(self.doc)
        image = Image.new("RGBA", (4, 8))
        image.paste(self.sheet.crop((4, 0, 8, 4)), (0, 0))
        image.paste(self.sheet.crop((0, 0, 4, 4)), (0, 4))
        doc["frames"][0]["frame"] = {"x": 0, "y": 4, "w": 4, "h": 4}
        doc["frames"][1]["frame"] = {"x": 0, "y": 0, "w": 4, "h": 4}
        doc["frames"].reverse()
        doc["meta"]["size"] = {"w": 4, "h": 8}
        return doc, image


class ImagesInReport(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.active_tags = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "iframe", "object", "embed", "form"}:
            self.active_tags.append(tag)
        if tag == "img":
            self.images.append(dict(attrs)["src"])


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fx = Fixture(self.root)
        self.old_paths = self.fx.write("old")
        self.old = load_atlas(*self.old_paths)

    def candidate(self, doc=None, image=None, *, indices=None):
        return load_atlas(*self.fx.write("new", doc, image), indices=indices)

    def assert_invalid(self, doc, code, image=None, **kwargs):
        with self.assertRaises(ContractError) as caught:
            self.candidate(doc, image, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def cli(self, *extra, new_paths=None):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main([str(p) for p in (*self.old_paths, *(new_paths or self.old_paths))] + list(extra))
        return exit_code, json.loads(output.getvalue()), output.getvalue()

    def test_repacking_invariance(self):
        doc, sheet = self.fx.repacked()
        result = compare(self.old, self.candidate(doc, sheet))
        self.assertTrue(result["compatible"])
        self.assertEqual(result["summary"]["pixels_changed"], 0)
        self.assertEqual(result["summary"]["coordinates_moved"], 2)
        self.assertTrue(result["summary"]["sheet_size_changed"])

    def test_coordinate_sensitive_mode(self):
        doc, sheet = self.fx.repacked()
        self.assertFalse(compare(self.old, self.candidate(doc, sheet), mode="coordinates")["compatible"])

    def test_sheet_size_only_is_coordinate_change(self):
        sheet = Image.new("RGBA", (8, 5))
        sheet.paste(self.fx.sheet)
        doc = copy.deepcopy(self.fx.doc)
        doc["meta"]["size"]["h"] = 5
        atlas = self.candidate(doc, sheet)
        self.assertTrue(compare(self.old, atlas)["compatible"])
        self.assertFalse(compare(self.old, atlas, mode="coordinates")["compatible"])

    def test_trimmed_and_untrimmed_equivalence(self):
        doc = copy.deepcopy(self.fx.doc)
        sheet = Image.new("RGBA", (3, 1))
        sheet.putpixel((0, 0), (255, 0, 0, 255))
        sheet.putpixel((1, 0), (0, 128, 255, 128))
        sheet.putpixel((2, 0), (0, 255, 0, 255))
        doc["meta"]["size"] = {"w": 3, "h": 1}
        for frame, x, sx, sy, w in ((doc["frames"][0], 0, 1, 1, 2), (doc["frames"][1], 2, 1, 2, 1)):
            frame["trimmed"] = True
            frame["frame"] = {"x": x, "y": 0, "w": w, "h": 1}
            frame["spriteSourceSize"] = {"x": sx, "y": sy, "w": w, "h": 1}
        atlas = self.candidate(doc, sheet)
        self.assertEqual(atlas.frames["red"].pixels.getpixel((2, 1)), (0, 128, 255, 128))
        self.assertTrue(compare(self.old, atlas)["compatible"])

    def test_hash_array_and_order_equivalence(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"] = {f["filename"]: {k: v for k, v in f.items() if k != "filename"} for f in reversed(doc["frames"])}
        self.assertEqual(compare(self.old, self.old), compare(self.old, self.candidate(doc)))

    def test_duplicate_array_names(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][1]["filename"] = "red"
        self.assert_invalid(doc, "duplicate_name")

    def test_duplicate_hash_keys(self):
        jp, pp = self.fx.write("duplicate")
        jp.write_text('{"frames":{"red":{},"red":{}},"meta":{}}')
        with self.assertRaises(ContractError) as caught:
            load_atlas(jp, pp)
        self.assertEqual(caught.exception.code, "duplicate_key")

    def test_hash_filename_disagreement(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"] = {"wrong": doc["frames"][0]}
        self.assert_invalid(doc, "invalid_name")

    def test_deleted_frame(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"].pop()
        result = compare(self.old, self.candidate(doc))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["changes"]["removed"], ["green"])

    def test_added_frame(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"].append(Fixture.frame("extra", 0))
        self.assertEqual(compare(self.old, self.candidate(doc))["changes"]["added"], ["extra"])

    def test_rename_is_never_guessed(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["filename"] = "crimson"
        result = compare(self.old, self.candidate(doc))
        self.assertEqual(result["changes"]["added"], ["crimson"])
        self.assertEqual(result["changes"]["removed"], ["red"])

    def test_explicit_rename_mapping_preserves_visual_pair_but_breaks_names(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["filename"] = "crimson"
        result = compare(self.old, self.candidate(doc), mapping={"red": "crimson"})
        self.assertEqual(result["summary"]["renamed"], 1)
        self.assertEqual(result["summary"]["pixels_changed"], 0)
        self.assertFalse(result["compatible"])

    def test_mapping_must_be_bijective_including_implicit_pairs(self):
        for mapping in ({"absent": "red"}, {"red": "absent"}, {"red": "green"}, {"red": "green", "green": "green"}):
            with self.subTest(mapping=mapping), self.assertRaises(ContractError):
                compare(self.old, self.old, mapping=mapping)

    def test_transparent_hidden_rgb_ignored(self):
        sheet = self.fx.sheet.copy()
        sheet.putpixel((0, 0), (222, 111, 37, 0))
        self.assertTrue(compare(self.old, self.candidate(image=sheet))["compatible"])

    def test_partial_alpha_rgb_preserved(self):
        sheet = self.fx.sheet.copy()
        sheet.putpixel((2, 1), (1, 128, 255, 128))
        result = compare(self.old, self.candidate(image=sheet))
        self.assertEqual(result["summary"]["pixels_changed"], 1)
        self.assertEqual(next(r for r in result["frames"] if r["before"] == "red")["changed_pixel_count"], 1)

    def test_alpha_only_change_is_visible(self):
        sheet = self.fx.sheet.copy()
        sheet.putpixel((1, 1), (255, 0, 0, 254))
        self.assertEqual(compare(self.old, self.candidate(image=sheet))["summary"]["pixels_changed"], 1)

    def test_canvas_dimension_change_is_art_change_even_if_padding_is_transparent(self):
        doc = copy.deepcopy(self.fx.doc)
        f = doc["frames"][0]
        f["trimmed"] = True
        f["sourceSize"]["w"] = 5
        result = compare(self.old, self.candidate(doc))
        record = next(r for r in result["frames"] if r["before"] == "red")
        self.assertIn("pixels_changed", record["changes"])
        self.assertEqual(record["changed_pixel_count"], 0)

    def test_invalid_rect_values(self):
        for key, value in (("x", -1), ("x", 6), ("w", 0), ("w", True), ("w", 4.0)):
            doc = copy.deepcopy(self.fx.doc)
            doc["frames"][0]["frame"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                self.candidate(doc)

    def test_invalid_trim_offset_and_dimensions(self):
        for key, value in (("x", 1), ("w", 3), ("y", -1)):
            doc = copy.deepcopy(self.fx.doc)
            doc["frames"][0]["spriteSourceSize"][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.candidate(doc)

    def test_untrimmed_claim_must_match_canvas(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["sourceSize"]["w"] = 5
        self.assert_invalid(doc, "invalid_trim")

    def test_declared_sheet_size_must_match_png(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["meta"]["size"]["w"] = 9
        self.assert_invalid(doc, "invalid_rect")

    def test_invalid_duration(self):
        for value in (0, -1, True, "100", 1.5, None, 3_600_001):
            doc = copy.deepcopy(self.fx.doc)
            doc["frames"][0]["duration"] = value
            with self.subTest(value=value):
                self.assert_invalid(doc, "invalid_value")

    def test_missing_required_fields(self):
        for key in ("frame", "rotated", "trimmed", "spriteSourceSize", "sourceSize", "duration", "filename"):
            doc = copy.deepcopy(self.fx.doc)
            del doc["frames"][0][key]
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.candidate(doc)

    def tagged(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["meta"]["frameTags"] = [{"name": "walk", "from": 0, "to": 1, "direction": "forward"}]
        return doc

    def test_tags_refuse_array_position_and_filename_guesses(self):
        self.assert_invalid(self.tagged(), "missing_source_index")

    def test_explicit_indices_allow_tags_and_repacking(self):
        doc = self.tagged()
        before = self.candidate(doc, indices={"red": 0, "green": 1})
        repacked, image = self.fx.repacked()
        repacked["meta"]["frameTags"] = doc["meta"]["frameTags"]
        after = self.candidate(repacked, image, indices={"green": 1, "red": 0})
        self.assertTrue(compare(before, after)["compatible"])
        self.assertEqual(after.tags["walk"]["members"], ["red", "green"])

    def test_invalid_tags(self):
        for key, value in (("from", -1), ("to", 2), ("from", 2), ("to", True), ("direction", "sideways"), ("repeat", -1), ("repeat", True)):
            doc = self.tagged()
            doc["meta"]["frameTags"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                self.candidate(doc, indices={"red": 0, "green": 1})

    def test_duplicate_tag_names(self):
        doc = self.tagged()
        doc["meta"]["frameTags"].append(copy.deepcopy(doc["meta"]["frameTags"][0]))
        self.assert_invalid(doc, "duplicate_name", indices={"red": 0, "green": 1})

    def test_tags_cannot_reference_omitted_source_indices(self):
        self.assert_invalid(self.tagged(), "invalid_tags", indices={"red": 0, "green": 2})

    def test_partial_duplicate_or_wrong_sidecars(self):
        for indices in ({"red": 0}, {"red": 0, "green": 0}, {"red": 0, "green": True}, {"red": 0, "unknown": 1}):
            with self.subTest(indices=indices), self.assertRaises(ContractError):
                self.candidate(indices=indices)

    def test_explicit_frame_index_and_sidecar_disagreement(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["index"] = 0
        doc["frames"][1]["index"] = 1
        self.assert_invalid(doc, "invalid_mapping", indices={"red": 1, "green": 0})

    def test_partial_embedded_indices_are_rejected(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["index"] = 0
        self.assert_invalid(doc, "missing_source_index")

    def test_tag_direction_and_index_changes_are_functional(self):
        doc = self.tagged()
        before = self.candidate(doc, indices={"red": 0, "green": 1})
        doc["meta"]["frameTags"][0]["direction"] = "reverse"
        after = self.candidate(doc, indices={"red": 0, "green": 1})
        self.assertEqual(compare(before, after)["summary"]["tags_changed"], 1)
        after = self.candidate(self.tagged(), indices={"red": 1, "green": 0})
        self.assertEqual(compare(before, after)["summary"]["source_index_changed"], 2)

    def test_timing_only_and_pixel_only_classification(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["duration"] = 200
        timing = compare(self.old, self.candidate(doc))
        self.assertEqual((timing["summary"]["duration_changed"], timing["summary"]["pixels_changed"]), (1, 0))
        sheet = self.fx.sheet.copy()
        sheet.putpixel((1, 1), (0, 0, 255, 255))
        pixels = compare(self.old, self.candidate(image=sheet))
        self.assertEqual((pixels["summary"]["duration_changed"], pixels["summary"]["pixels_changed"]), (0, 1))

    def test_documented_exporter_metadata_is_ignored(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["meta"].update(app="https://www.aseprite.org/", version="2.0", image="../../secret.png")
        self.assertEqual(compare(self.old, self.old), compare(self.old, self.candidate(doc)))

    def test_unknown_metadata_is_conservatively_compared(self):
        for scope in ("root", "meta", "frame"):
            doc = copy.deepcopy(self.fx.doc)
            target = doc if scope == "root" else (doc["meta"] if scope == "meta" else doc["frames"][0])
            target["future_functional_field"] = {"x": 1}
            with self.subTest(scope=scope):
                self.assertFalse(compare(self.old, self.candidate(doc))["compatible"])

    def test_unknown_metadata_types_are_not_coerced(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["extra"] = True
        before = self.candidate(doc)
        doc["extra"] = 1
        self.assertFalse(compare(before, self.candidate(doc))["compatible"])

    def test_unsupported_rotation_scaled_layers_and_slices(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["rotated"] = True
        self.assert_invalid(doc, "unsupported_rotation")
        for key, value in (("scale", "2"), ("layers", [{"name": "body"}]), ("slices", [{}])):
            doc = copy.deepcopy(self.fx.doc)
            doc["meta"][key] = value
            self.assert_invalid(doc, "unsupported_export")

    def test_missing_json_and_png(self):
        for jp, pp in ((self.root / "absent.json", self.old_paths[1]), (self.old_paths[0], self.root / "absent.png")):
            with self.assertRaises(ContractError) as caught:
                load_atlas(jp, pp)
            self.assertEqual(caught.exception.code, "missing_file")
            self.assertNotIn(str(self.root), str(caught.exception))

    def test_truncated_png_and_non_png_rejected(self):
        jp, pp = self.fx.write("bad")
        for payload in (pp.read_bytes()[:45], b"not an image"):
            pp.write_bytes(payload)
            with self.assertRaises(ContractError) as caught:
                load_atlas(jp, pp)
            self.assertEqual(caught.exception.code, "invalid_png")

    def test_animated_png_rejected(self):
        jp, pp = self.fx.write("animated")
        extra = self.fx.sheet.copy()
        extra.putpixel((0, 0), (255, 255, 255, 255))
        self.fx.sheet.save(pp, save_all=True, append_images=[extra], duration=100)
        with self.assertRaises(ContractError) as caught:
            load_atlas(jp, pp)
        self.assertEqual(caught.exception.code, "unsupported_png")

    def test_large_sheet_rejected_before_decode(self):
        large = Image.new("RGBA", (8193, 1))
        jp, pp = self.fx.write("large", image=large)
        with patch.object(Image.Image, "convert", side_effect=AssertionError("must not decode")):
            with self.assertRaises(ContractError) as caught:
                load_atlas(jp, pp)
        self.assertEqual(caught.exception.code, "resource_limit")

    def test_reconstructed_canvas_and_total_budget(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["trimmed"] = True
        doc["frames"][0]["sourceSize"] = {"w": 2048, "h": 2048}
        self.assert_invalid(doc, "resource_limit")
        with patch.object(core, "MAX_TOTAL_FRAME_PIXELS", 20):
            self.assert_invalid(self.fx.doc, "resource_limit")

    def test_json_size_depth_nonfinite_and_unicode_limits(self):
        jp, pp = self.fx.write("limits")
        with patch.object(core, "MAX_JSON_BYTES", 20), self.assertRaises(ContractError) as caught:
            load_atlas(jp, pp)
        self.assertEqual(caught.exception.code, "resource_limit")
        for text in ('{"x":NaN}', '{"x":1e999}', '{"x":"\\ud800"}', '[' * 40 + '0' + ']' * 40, '{broken'):
            jp.write_text(text)
            with self.subTest(text=text), self.assertRaises(ContractError):
                load_atlas(jp, pp)

    def test_frame_and_tag_names_are_literal_never_output_paths(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["filename"] = "../../escaped.png"
        doc["meta"]["image"] = "../../private.png"
        atlas = self.candidate(doc)
        self.assertIn("../../escaped.png", atlas.frames)
        self.assertFalse((self.root.parent / "escaped.png").exists())
        report = render_html(compare(atlas, atlas), atlas, atlas)
        self.assertIn("../../escaped.png", report)

    def test_html_injection_is_escaped_and_all_images_are_embedded(self):
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["filename"] = '<script>alert("x")</script><img src=x onerror=alert(1)>'
        doc["extra"] = "</pre><iframe src=https://example.test>"
        atlas = self.candidate(doc)
        report = render_html(compare(self.old, atlas), self.old, atlas)
        parser = ImagesInReport()
        parser.feed(report)
        self.assertEqual(parser.active_tags, [])
        self.assertTrue(parser.images)
        self.assertTrue(all(src.startswith("data:image/png;base64,") for src in parser.images))
        self.assertIn("&lt;script&gt;", report)
        self.assertIn("Content-Security-Policy", report)

    def test_cli_exit_codes_and_outputs(self):
        jp, pp = self.fx.write("new")
        json_path, html_path = self.root / "out.json", self.root / "out.html"
        code, result, text = self.cli("--json", str(json_path), "--html", str(html_path), new_paths=(jp, pp))
        self.assertEqual(code, 0)
        self.assertEqual(json_path.read_bytes(), text.encode("ascii"))
        self.assertIn("PASS · EXIT 0", html_path.read_text(encoding="utf-8"))
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"][0]["duration"] = 200
        self.assertEqual(self.cli(new_paths=self.fx.write("changed", doc))[0], 1)
        code, result, _ = self.cli(new_paths=(self.root / "missing.json", pp))
        self.assertEqual((code, result["status"]), (2, "invalid"))

    def test_cli_replaces_stale_html_with_invalid_report(self):
        output = self.root / "stale.html"
        output.write_text("old passing report")
        self.cli("--html", str(output), new_paths=(self.root / "missing.json", self.old_paths[1]))
        self.assertIn("INVALID · EXIT 2", output.read_text(encoding="utf-8"))

    def test_cli_refuses_overwriting_any_input_or_output_collision(self):
        original = self.old_paths[0].read_bytes()
        code, result, _ = self.cli("--json", str(self.old_paths[0]))
        self.assertEqual((code, result["error"]["code"]), (2, "output_collision"))
        self.assertEqual(original, self.old_paths[0].read_bytes())
        output = self.root / "same"
        self.assertEqual(self.cli("--json", str(output), "--html", str(output))[0], 2)

    def test_cli_refuses_hard_linked_input_output(self):
        link = self.root / "hardlink.json"
        try:
            os.link(self.old_paths[0], link)
        except OSError:
            self.skipTest("filesystem does not support hard links")
        self.assertEqual(self.cli("--json", str(link))[0], 2)

    def test_cli_ascii_deterministic_across_paths_and_key_orders(self):
        code, _, first = self.cli()
        doc = copy.deepcopy(self.fx.doc)
        doc["frames"].reverse()
        paths = self.fx.write("different-location", doc)
        code2, _, second = self.cli(new_paths=paths)
        self.assertEqual((code, code2), (0, 0))
        self.assertEqual(first, second)
        self.assertNotIn(str(self.root), first)

    def test_real_module_cli_subprocess(self):
        command = [sys.executable, "-m", "sprite_contract_check", *map(str, (*self.old_paths, *self.old_paths))]
        process = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
