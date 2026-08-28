"""R8 sections 41-42: shared sanitization helpers for anything written
into a generated export -- both the Excel cell content and the download
filename. Small and dependency-free on purpose; not a general text-
processing module.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that can make a spreadsheet application interpret a cell's
# text content as a formula when the cell is later re-entered/exported to
# CSV/re-opened by a different tool (R8 section 41 -- "Excel/CSV formula
# injection"). A leading apostrophe is the standard, minimally-invasive
# neutralization: it is Excel's own convention for "force this cell to be
# plain text" and is visually a single harmless leading character rather
# than mangling the rest of the value.
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell_text(value: str | None) -> str | None:
    """Neutralizes a user-controlled string before it is written into any
    normal business column (material name/code, project/plan name, notes).
    Never applied to values MassIQ itself controls (IDs, enum values,
    calculation_version) -- those can never begin with a trigger
    character in the first place, so sanitizing them would just be noise."""
    if value is None:
        return None
    text = str(value)
    if text.startswith(_FORMULA_TRIGGER_CHARS):
        return f"'{text}"
    return text


# Windows + cross-platform-unsafe filename characters, plus the path
# separators themselves (R8 section 42 -- no path traversal, no illegal
# characters). Deliberately conservative: anything not a letter, digit,
# space, hyphen, or underscore is dropped rather than guessing at a safe
# substitution for every possible unsafe character.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9 _-]+")
_MAX_FILENAME_COMPONENT_LENGTH = 80


def sanitize_filename_component(value: str) -> str:
    """Sanitizes one component of a generated filename (e.g. a project
    name) so it can never escape the intended directory (`../../x`,
    `a/b`), never contains a Windows-illegal character, and never makes
    the resulting filename unreasonably long. Unicode is normalized to
    its closest ASCII form rather than rejected outright, so a real
    project name with accented characters still produces a readable
    filename instead of an empty one."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", normalized).strip("_ ")
    if not cleaned:
        cleaned = "project"
    return cleaned[:_MAX_FILENAME_COMPONENT_LENGTH]
