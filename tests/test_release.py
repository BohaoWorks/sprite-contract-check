"""Release checks: installed CLI, complete demo classification and hostile inputs."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from sprite_contract_check import ContractError, load_atlas
from sprite_contract_check.core import read_json
from sprite_contract_check.report import render_html
from test_contract import ContractTests as _Helpers


class ReleaseTests(unittest.TestCase):
    setUp = _Helpers.setUp
    def test_16bit_png_channels_are_rejected_before_lossy_conversion(self):
        import struct
        import zlib
        from unittest.mock import patch
        from PIL import Image
        from sprite_contract_check.core import _png

        def chunk(kind, payload):
            return (struct.pack(">I", len(payload)) + kind + payload
                    + struct.pack(">I", zlib.crc32(kind + payload)))

        # Cover grayscale, RGB, grayscale+alpha, and RGBA. Pillow's mode
        # alone cannot identify RGB16 after its decoder has reduced channels.
        for color_type, channels in ((0, 1), (2, 3), (4, 2), (6, 4)):
            for sample in (256, 257):
                with self.subTest(color_type=color_type, sample=sample):
                    png = (b"\x89PNG\r\n\x1a\n"
                           + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 16, color_type, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(b"\x00" + struct.pack(">H", sample) * channels))
                           + chunk(b"IEND", b""))
                    path = self.root / "sixteen.png"
                    path.write_bytes(png)
                    with patch.object(Image.Image, "convert", side_effect=AssertionError("lossy conversion")):
                        with self.assertRaises(ContractError) as caught:
                            _png(path, "PNG")
                    self.assertEqual(caught.exception.code, "unsupported_png")

    def test_overlong_integer_is_structured_invalid_json(self):
        path = self.root / "number.json"
        path.write_text('{"n":' + '9' * 10000 + '}')
        with self.assertRaises(ContractError) as caught:
            read_json(path)
        self.assertEqual(caught.exception.code, "invalid_json")

    def test_png_checksum_is_verified(self):
        jp, pp = self.fx.write("checksum")
        data = bytearray(pp.read_bytes())
        pos = 8
        while pos < len(data):
            length = int.from_bytes(data[pos:pos + 4], "big")
            if data[pos + 4:pos + 8] == b"IDAT":
                data[pos + 8 + length] ^= 1
                break
            pos += 12 + length
        pp.write_bytes(data)
        with self.assertRaises(ContractError) as caught:
            load_atlas(jp, pp)
        self.assertEqual(caught.exception.code, "invalid_png")

    def test_html_bytes_are_deterministic(self):
        from sprite_contract_check import compare
        result = compare(self.old, self.old)
        self.assertEqual(render_html(result, self.old, self.old), render_html(result, self.old, self.old))

    def test_installed_module_demo_exit_and_classification(self):
        demo = Path(__file__).resolve().parents[1] / "examples" / "demo"
        for name, code, pixels, timing, removed in (
            ("repacked", 0, 0, 0, 0), ("metadata", 0, 0, 0, 0),
            ("timing", 1, 0, 1, 0), ("pixel", 1, 1, 0, 0),
            ("deleted", 1, 0, 0, 1), ("changed", 1, 1, 1, 1),
        ):
            with self.subTest(name=name):
                args = [sys.executable, "-m", "sprite_contract_check",
                        str(demo / "before.json"), str(demo / "before.png"),
                        str(demo / f"{name}.json"), str(demo / f"{name}.png"),
                        "--old-indices", str(demo / "before-indices.json"),
                        "--new-indices", str(demo / f"{name}-indices.json")]
                p = subprocess.run(args, capture_output=True, text=True, timeout=20)
                self.assertEqual(p.returncode, code, p.stderr)
                s = json.loads(p.stdout)["summary"]
                self.assertEqual((s["pixels_changed"], s["duration_changed"], s["removed"]),
                                 (pixels, timing, removed))


# The imported base TestCase supplies setup only, not another discoverable suite.
del _Helpers
