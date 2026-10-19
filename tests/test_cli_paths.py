"""Path-resolution failures must not masquerade as changed sprite contracts."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sprite_contract_check.cli import main
from test_contract import Fixture


class PathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = Fixture(self.root).write("input")
        self.arguments = list(map(str, self.inputs * 2))

    def invoke(self, arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(arguments)
        return status, json.loads(output.getvalue()), output.getvalue()

    def make_loop(self):
        first, second = self.root / "loop-a", self.root / "loop-b"
        try:
            first.symlink_to(second.name)
            second.symlink_to(first.name)
        except (OSError, NotImplementedError):
            self.skipTest("filesystem does not permit symlinks")
        return first

    def assert_path_error(self, arguments):
        status, result, output = self.invoke(arguments)
        self.assertEqual(status, 2)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["error"]["code"], "output_error")
        self.assertNotIn(str(self.root), output)
        self.assertNotIn("loop-a", output)

    def test_resolution_exceptions_are_structured_without_writes(self):
        # Python <=3.12 reports loops as RuntimeError; later versions use
        # OSError with strict resolution. Exercise both even without symlinks.
        report = self.root / "report.json"
        report.write_text("previous report", encoding="utf-8")
        for error in (RuntimeError("private loop path"), OSError("private path")):
            with self.subTest(error=type(error).__name__):
                with patch.object(Path, "resolve", side_effect=error):
                    self.assert_path_error(self.arguments + ["--json", str(report)])
                self.assertEqual(report.read_text(encoding="utf-8"), "previous report")

    def test_loop_in_each_input_or_sidecar_is_invalid(self):
        loop = self.make_loop()
        for position in range(4):
            arguments = self.arguments.copy()
            arguments[position] = str(loop)
            with self.subTest(position=position):
                self.assert_path_error(arguments)
        for option in ("--mapping", "--old-indices", "--new-indices"):
            with self.subTest(option=option):
                self.assert_path_error(self.arguments + [option, str(loop)])

    def test_loop_output_and_loop_parent_preserve_other_output(self):
        loop = self.make_loop()
        sentinel = self.root / "keep-report"
        sentinel.write_text("keep", encoding="utf-8")
        for option, companion in (("--json", "--html"), ("--html", "--json")):
            for target in (loop, loop / "report"):
                with self.subTest(option=option, target=target.name):
                    self.assert_path_error(self.arguments + [option, str(target), companion, str(sentinel)])
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
                    self.assertTrue(loop.is_symlink())

    def test_loop_is_exit_two_and_json_in_real_subprocess(self):
        loop = self.make_loop()
        process = subprocess.run(
            [sys.executable, "-m", "sprite_contract_check", *self.arguments, "--json", str(loop)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "invalid")
        self.assertEqual(process.stderr, "")
        self.assertNotIn(str(self.root), process.stdout)

    def test_loops_around_parent_traversal_never_write_reports(self):
        loop = self.make_loop()
        missing = self.root / "missing"
        sentinel = self.root / "keep.html"
        sentinel.write_text("keep", encoding="utf-8")
        targets = (missing / ".." / loop.name, loop / ".." / "report.json",
                   missing / ".." / loop.name / ".." / "report.json")
        for target in targets:
            with self.subTest(target=str(target)):
                self.assert_path_error(self.arguments + ["--json", str(target), "--html", str(sentinel)])
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
                self.assertFalse(missing.exists())
                self.assertFalse((self.root / "report.json").exists())
                self.assertTrue(loop.is_symlink())

    def test_missing_suffix_never_uses_non_strict_resolution(self):
        original = Path.resolve

        def strict_only(path, strict=False):
            self.assertTrue(strict, "loose resolution can conceal symlink loops")
            return original(path, strict=strict)

        with patch.object(Path, "resolve", strict_only):
            status, result, _ = self.invoke(self.arguments + ["--json", str(self.root / "new" / "report.json")])
        self.assertEqual((status, result["status"]), (0, "pass"))

    def test_dangling_links_are_path_errors_and_are_not_replaced(self):
        link = self.root / "dangling"
        try:
            link.symlink_to("absent-target")
        except (OSError, NotImplementedError):
            self.skipTest("filesystem does not permit symlinks")
        arguments = self.arguments.copy()
        arguments[0] = str(link)
        self.assert_path_error(arguments)
        self.assert_path_error(self.arguments + ["--json", str(link)])
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.root / "absent-target").exists())

    def test_existing_parent_traversal_can_create_new_reports(self):
        existing = self.root / "existing"
        existing.mkdir()
        output = existing / ".." / "new" / "result.json"
        status, result, _ = self.invoke(self.arguments + ["--json", str(output)])
        self.assertEqual((status, result["status"]), (0, "pass"))
        self.assertTrue((self.root / "new" / "result.json").is_file())

    def test_missing_input_still_has_missing_file_error(self):
        arguments = self.arguments.copy()
        arguments[0] = str(self.root / "absent.json")
        status, result, _ = self.invoke(arguments)
        self.assertEqual((status, result["error"]["code"]), (2, "missing_file"))

    def test_new_nested_reports_are_still_created(self):
        json_path = self.root / "new" / "nested" / "result.json"
        html_path = json_path.with_suffix(".html")
        status, result, output = self.invoke(
            self.arguments + ["--json", str(json_path), "--html", str(html_path)]
        )
        self.assertEqual((status, result["status"]), (0, "pass"))
        self.assertEqual(json_path.read_text(encoding="utf-8"), output)
        self.assertIn("PASS · EXIT 0", html_path.read_text(encoding="utf-8"))

    def test_symlink_to_input_is_still_an_output_collision(self):
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.inputs[0].name)
        except (OSError, NotImplementedError):
            self.skipTest("filesystem does not permit symlinks")
        original = self.inputs[0].read_bytes()
        status, result, _ = self.invoke(self.arguments + ["--json", str(alias)])
        self.assertEqual((status, result["error"]["code"]), (2, "output_collision"))
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.inputs[0].read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
