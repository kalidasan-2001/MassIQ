from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(Base):
    """R1 scope: Project only. Plan/PlanPage/LegendEntry/etc. are future
    releases (R2+) and intentionally do not exist yet."""

    __tablename__ = "projects"

    # Generated client-side by SQLAlchemy (uuid.uuid4), not by a Postgres
    # extension -- keeps the schema portable and avoids requiring
    # pgcrypto/uuid-ossp to be enabled on the database.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        # values_callable: without it, SQLAlchemy stores each Python enum
        # member's .name ("ACTIVE") as the Postgres enum label, which would
        # not match server_default below (.value, "active") and would make
        # CREATE TABLE fail (default literal not a valid label of the type).
        # Storing .value keeps the DB label identical to ProjectStatus's
        # string value, so `status == "active"` comparisons and the server
        # default both agree.
        sa.Enum(ProjectStatus, name="project_status", native_enum=True, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=ProjectStatus.ACTIVE,
        server_default=ProjectStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
