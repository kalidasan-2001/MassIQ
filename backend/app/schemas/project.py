from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import ProjectStatus


def _reject_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("name cannot be blank")
    return stripped


class ProjectCreate(BaseModel):
    """Client-writable fields only. `id`, `created_at`, `updated_at` are not
    accepted -- extra="forbid" rejects a request that tries to set them
    instead of silently ignoring it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _reject_blank(value)


class ProjectUpdate(BaseModel):
    """All fields optional (PATCH semantics); only fields explicitly present
    in the request are applied (see ProjectService.update_project)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: ProjectStatus | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _reject_blank(value)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
