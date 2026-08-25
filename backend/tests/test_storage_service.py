"""Pure filesystem tests -- no database required."""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.storage_service import StorageError, StorageService


class StorageServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.storage = StorageService(root=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_and_resolve_original_plan_roundtrip(self):
        plan_id = uuid.uuid4()
        reference = self.storage.save_original_plan(plan_id, b"%PDF-1.4 fake content")
        self.assertEqual(reference, f"plans/{plan_id}/original.pdf")
        resolved = self.storage.resolve_original_plan(reference)
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.read_bytes(), b"%PDF-1.4 fake content")

    def test_reference_is_relative_not_absolute(self):
        plan_id = uuid.uuid4()
        reference = self.storage.save_original_plan(plan_id, b"content")
        self.assertFalse(Path(reference).is_absolute())
        self.assertNotIn(str(self.storage.root), reference)

    def test_save_and_resolve_preview_roundtrip(self):
        plan_id = uuid.uuid4()
        reference = self.storage.save_page_preview(plan_id, 1, b"\x89PNG fake")
        self.assertEqual(reference, f"plans/{plan_id}/pages/0001.png")
        resolved = self.storage.resolve_preview(reference)
        self.assertEqual(resolved.read_bytes(), b"\x89PNG fake")

    def test_resolve_missing_original_raises(self):
        with self.assertRaises(StorageError):
            self.storage.resolve_original_plan(f"plans/{uuid.uuid4()}/original.pdf")

    def test_resolve_missing_preview_raises(self):
        with self.assertRaises(StorageError):
            self.storage.resolve_preview(f"plans/{uuid.uuid4()}/pages/0001.png")

    def test_path_traversal_outside_root_is_rejected(self):
        with self.assertRaises(StorageError):
            self.storage.resolve_original_plan("../../../../etc/passwd")

    def test_path_traversal_with_dotdot_inside_reference_is_rejected(self):
        with self.assertRaises(StorageError):
            self.storage.resolve_preview("plans/../../outside.png")

    def test_client_filename_never_reaches_path_construction(self):
        """save_original_plan/save_page_preview take only a server-generated
        plan_id (UUID) and, for previews, a server-derived page_number --
        neither has a parameter for the client's original filename, so a
        malicious filename like '../../evil.pdf' cannot influence the
        resulting path no matter what a caller does with it elsewhere."""
        plan_id = uuid.uuid4()
        reference = self.storage.save_original_plan(plan_id, b"content")
        self.assertEqual(reference, f"plans/{plan_id}/original.pdf")
        self.assertNotIn("evil", reference)

    def test_delete_plan_assets_removes_everything(self):
        plan_id = uuid.uuid4()
        self.storage.save_original_plan(plan_id, b"content")
        self.storage.save_page_preview(plan_id, 1, b"preview")
        self.storage.delete_plan_assets(plan_id)
        self.assertFalse((self.storage.plans_root / str(plan_id)).exists())

    def test_delete_plan_assets_is_safe_when_nothing_exists(self):
        self.storage.delete_plan_assets(uuid.uuid4())  # must not raise


if __name__ == "__main__":
    unittest.main()
