"""Pure validation unit tests -- no database required."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pydantic

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectCreateValidationTests(unittest.TestCase):
    def test_blank_name_rejected(self):
        with self.assertRaises(pydantic.ValidationError):
            ProjectCreate(name="   ")

    def test_missing_name_rejected(self):
        with self.assertRaises(pydantic.ValidationError):
            ProjectCreate(description="no name given")

    def test_name_is_trimmed(self):
        created = ProjectCreate(name="  My Project  ")
        self.assertEqual(created.name, "My Project")

    def test_client_cannot_set_id(self):
        with self.assertRaises(pydantic.ValidationError):
            ProjectCreate(name="Valid", id="11111111-1111-1111-1111-111111111111")

    def test_client_cannot_set_created_at(self):
        with self.assertRaises(pydantic.ValidationError):
            ProjectCreate(name="Valid", created_at="2020-01-01T00:00:00Z")

    def test_description_optional(self):
        created = ProjectCreate(name="Valid")
        self.assertIsNone(created.description)


class ProjectUpdateValidationTests(unittest.TestCase):
    def test_blank_name_rejected(self):
        with self.assertRaises(pydantic.ValidationError):
            ProjectUpdate(name="   ")

    def test_all_fields_optional(self):
        update = ProjectUpdate()
        self.assertEqual(update.model_dump(exclude_unset=True), {})

    def test_partial_update_only_carries_provided_fields(self):
        update = ProjectUpdate(description="new description")
        self.assertEqual(update.model_dump(exclude_unset=True), {"description": "new description"})

    def test_client_cannot_set_updated_at(self):
        with self.assertRaises(pydantic.ValidationError):
            ProjectUpdate(updated_at="2020-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
