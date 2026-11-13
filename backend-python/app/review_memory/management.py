"""Read-only management views; they do not grant eligibility for Review or sharing."""

from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.review_memory import repository
from app.review_memory.schemas import (
    BindingState,
    MemoryBindingQuery,
    MemoryLibraryPage,
    MemoryLibraryQuery,
    MemoryLibrarySource,
    MemoryProjectBinding,
    MemoryProjectBindingsPage,
    MemorySourceProjectsPage,
)
from app.review_memory.service import _binding_summary, _is_shared, _source_summary, require_project


@contextmanager
def _reader(db: Session):
    bind = db.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        bind = bind.execution_options(isolation_level="REPEATABLE READ")
    with Session(bind=bind, autoflush=False) as reader:
        yield reader


def list_library(db: Session, query: MemoryLibraryQuery) -> MemoryLibraryPage:
    query = MemoryLibraryQuery.model_validate(query.model_dump())
    with _reader(db) as reader:
        sources, total = repository.list_library_sources(reader, query)
        summaries = repository.library_binding_summaries(reader, [source.id for source in sources])
        items = []
        for source in sources:
            count, project_ids = summaries.get(source.id, (0, []))
            items.append(
                MemoryLibrarySource(
                    **_source_summary(source, can_manage=True).model_dump(),
                    active_binding_count=count,
                    using_project_ids=project_ids,
                    using_projects_truncated=count > len(project_ids),
                )
            )
        return MemoryLibraryPage(
            items=items, total=total, page_no=query.page_no, page_size=query.page_size
        )


def list_source_projects(
    db: Session, source_id: int, query: MemoryBindingQuery
) -> MemorySourceProjectsPage:
    query = MemoryBindingQuery.model_validate(query.model_dump())
    with _reader(db) as reader:
        source = repository.get_source(reader, None, source_id)
        if source is None:
            raise AppError("RESOURCE_NOT_FOUND", "Memory source not found", 404)
        bindings, total = repository.list_source_projects(reader, source_id, query)
        return MemorySourceProjectsPage(
            source_id=source.id,
            source_version=source.version,
            items=[_binding_summary(binding) for binding in bindings],
            total=total,
            page_no=query.page_no,
            page_size=query.page_size,
        )


def list_project_bindings(
    db: Session, project_id: int, query: MemoryBindingQuery
) -> MemoryProjectBindingsPage:
    query = MemoryBindingQuery.model_validate(query.model_dump())
    with _reader(db) as reader:
        require_project(reader, project_id)
        rows, total = repository.list_project_bindings(reader, project_id, query)
        items = []
        for binding, source, has_active_entries in rows:
            owner = source is not None and source.project_id == project_id
            items.append(
                MemoryProjectBinding(
                    source_id=binding.source_id,
                    binding=_binding_summary(binding),
                    source=_source_summary(source, binding, owner) if source is not None else None,
                    source_missing=source is None,
                    has_active_entries=source is not None and bool(has_active_entries),
                    can_read_source=source is not None
                    and (owner or binding.state == BindingState.ACTIVE and _is_shared(source)),
                )
            )
        return MemoryProjectBindingsPage(
            project_id=project_id,
            items=items,
            total=total,
            page_no=query.page_no,
            page_size=query.page_size,
        )
