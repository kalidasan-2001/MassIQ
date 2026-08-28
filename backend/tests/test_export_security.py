"""R8 sections 41-42 -- pure unit tests, no DB needed."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.export_security import sanitize_cell_text, sanitize_filename_component


class SanitizeCellTextTests(unittest.TestCase):
    def test_equals_prefix_neutralized(self):
        self.assertEqual(sanitize_cell_text("=1+1"), "'=1+1")

    def test_plus_prefix_neutralized(self):
        self.assertEqual(sanitize_cell_text("+cmd|' /c calc'!A1"), "'+cmd|' /c calc'!A1")

    def test_minus_prefix_neutralized(self):
        self.assertEqual(sanitize_cell_text("-2+3"), "'-2+3")

    def test_at_prefix_neutralized(self):
        self.assertEqual(sanitize_cell_text("@SUM(A1:A10)"), "'@SUM(A1:A10)")

    def test_tab_and_cr_prefix_neutralized(self):
        self.assertEqual(sanitize_cell_text("\t=1+1"), "'\t=1+1")
        self.assertEqual(sanitize_cell_text("\r=1+1"), "'\r=1+1")

    def test_ordinary_text_unchanged(self):
        self.assertEqual(sanitize_cell_text("Stahlbeton C25/30"), "Stahlbeton C25/30")
        self.assertEqual(sanitize_cell_text("Existing Concrete"), "Existing Concrete")

    def test_none_stays_none(self):
        self.assertIsNone(sanitize_cell_text(None))

    def test_formula_looking_text_in_the_middle_is_not_touched(self):
        # Only a LEADING trigger character matters -- a material name that
        # merely contains "=" elsewhere is not a formula-injection risk.
        self.assertEqual(sanitize_cell_text("Concrete (C25/30, f=30MPa)"), "Concrete (C25/30, f=30MPa)")


class SanitizeFilenameComponentTests(unittest.TestCase):
    def test_path_traversal_stripped(self):
        result = sanitize_filename_component("../../project")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)

    def test_slashes_stripped(self):
        result = sanitize_filename_component("a/b\\c")
        self.assertNotIn("/", result)
        self.assertNotIn("\\", result)

    def test_windows_illegal_characters_stripped(self):
        result = sanitize_filename_component('a:b*c?d"e<f>g|h')
        for char in ':*?"<>|':
            self.assertNotIn(char, result)

    def test_ordinary_name_mostly_preserved(self):
        result = sanitize_filename_component("My Project 2026")
        self.assertEqual(result, "My Project 2026")

    def test_very_long_name_truncated(self):
        result = sanitize_filename_component("x" * 500)
        self.assertLessEqual(len(result), 80)

    def test_unicode_does_not_crash_and_produces_ascii(self):
        result = sanitize_filename_component("Projekt Straße München")
        result.encode("ascii")  # must not raise

    def test_empty_or_whitespace_only_falls_back(self):
        self.assertEqual(sanitize_filename_component(""), "project")
        self.assertEqual(sanitize_filename_component("   "), "project")
        self.assertEqual(sanitize_filename_component("///"), "project")

    def test_result_never_empty(self):
        for value in ("", "   ", "///", "...", "***"):
            self.assertTrue(sanitize_filename_component(value))


if __name__ == "__main__":
    unittest.main()
