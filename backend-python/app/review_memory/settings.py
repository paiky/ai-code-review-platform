"""Memory settings are explicit opt-in; callers own writes, migrations never run here."""

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.project_integration.models import ProjectReviewSettings
from app.project_integration.repository import _create_default_project_review_settings
from app.review_memory import repository
from app.review_memory.schemas import MemorySettings, MemorySettingsUpdate
from app.review_memory.service import assert_version


def settings_schema_ready(db: Session) -> bool:
    inspector = inspect(db.connection())
    if not inspector.has_table("project_review_settings"):
        return False
    columns = {column["name"] for column in inspector.get_columns("project_review_settings")}
    return {"memory_enabled", "memory_settings_version"}.issubset(columns)


def read_settings(db: Session, project_id: int) -> MemorySettings:
    if repository.get_project(db, project_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)
    if not settings_schema_ready(db):
        return MemorySettings(enabled=False, version=1, schema_ready=False)
    row = db.execute(
        select(
            ProjectReviewSettings.memory_enabled, ProjectReviewSettings.memory_settings_version
        ).where(ProjectReviewSettings.project_id == project_id)
    ).first()
    return MemorySettings(
        enabled=bool(row[0]) if row else False,
        version=row[1] if row else 1,
        schema_ready=True,
    )


def update_settings(db: Session, project_id: int, request: MemorySettingsUpdate) -> MemorySettings:
    request = MemorySettingsUpdate.model_validate(request.model_dump())
    project = repository.get_project(db, project_id, lock=True)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found", 404)
    if not settings_schema_ready(db):
        raise AppError("MEMORY_SCHEMA_PENDING", "Apply V59 before changing memory settings", 503)
    # A locking read must not reuse a previously established REPEATABLE READ snapshot.
    row = db.execute(
        select(ProjectReviewSettings.memory_enabled, ProjectReviewSettings.memory_settings_version)
        .where(ProjectReviewSettings.project_id == project_id)
        .with_for_update()
    ).first()
    version = row[1] if row else 1
    assert_version(version, request.expected_version)
    if row is None:
        record = _create_default_project_review_settings(db, project)
        record.memory_enabled = request.enabled
        record.memory_settings_version = version + 1
        db.flush()
    else:
        db.execute(
            ProjectReviewSettings.__table__.update()
            .where(ProjectReviewSettings.project_id == project_id)
            .values(memory_enabled=request.enabled, memory_settings_version=version + 1)
        )
    return MemorySettings(enabled=request.enabled, version=version + 1, schema_ready=True)
