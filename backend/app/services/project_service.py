from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectNotFoundError(Exception):
    def __init__(self, project_id: uuid.UUID):
        self.project_id = project_id
        super().__init__(f"Project {project_id} not found")


class ProjectService:
    """Owns Project domain/application logic. Routes only wire this to HTTP
    -- no raw SQLAlchemy query logic belongs in routes/projects.py."""

    def __init__(self, db: Session):
        self._db = db

    def create_project(self, payload: ProjectCreate) -> Project:
        project = Project(name=payload.name, description=payload.description)
        self._db.add(project)
        self._db.commit()
        self._db.refresh(project)
        return project

    def list_projects(self) -> list[Project]:
        stmt = select(Project).order_by(Project.created_at.desc())
        return list(self._db.scalars(stmt).all())

    def get_project(self, project_id: uuid.UUID) -> Project:
        project = self._db.get(Project, project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def update_project(self, project_id: uuid.UUID, payload: ProjectUpdate) -> Project:
        project = self.get_project(project_id)
        # exclude_unset -> only fields the caller actually sent are applied;
        # a PATCH that omits `description` must not null it out.
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        self._db.commit()
        self._db.refresh(project)
        return project
