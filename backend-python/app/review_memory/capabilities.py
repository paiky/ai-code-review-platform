"""Check the live schema without migrating or caching deployment readiness."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.review_memory.schemas import MemoryCapabilities


def read_capabilities(db: Session) -> MemoryCapabilities:
    inspector = inspect(db.connection())
    ready = False
    if inspector.has_table("review_memory_sources"):
        ready = any(
            column["name"] == "project_id" and column["nullable"]
            for column in inspector.get_columns("review_memory_sources")
        )
    return MemoryCapabilities(schema_ready=ready)


def require_library_schema(db: Session) -> None:
    if not read_capabilities(db).schema_ready:
        raise AppError("MEMORY_SCHEMA_PENDING", "Apply V60 before creating library assets", 503)
