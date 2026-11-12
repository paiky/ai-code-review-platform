from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, undefer

from app.project_integration.models import Project
from app.project_review_policy.models import ProjectReviewPolicy
from app.review_feedback.models import ReviewItemFeedback
from app.review_memory.models import ReviewMemoryEntry, ReviewMemorySource, ReviewMemoryWriteback
from app.review_memory.schemas import LoadMode, MemorySourceQuery, SourceState


def get_project(db: Session, project_id: int, *, lock: bool = False) -> Project | None:
    query = select(Project).where(Project.id == project_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def get_source(
    db: Session,
    project_id: int,
    source_id: int,
    *,
    lock: bool = False,
) -> ReviewMemorySource | None:
    query = select(ReviewMemorySource).where(
        ReviewMemorySource.id == source_id,
        ReviewMemorySource.project_id == project_id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def get_entry(
    db: Session,
    project_id: int,
    source_id: int,
    entry_id: int,
) -> ReviewMemoryEntry | None:
    return db.scalar(
        select(ReviewMemoryEntry)
        .join(ReviewMemorySource, ReviewMemorySource.id == ReviewMemoryEntry.source_id)
        .where(
            ReviewMemorySource.project_id == project_id,
            ReviewMemorySource.id == source_id,
            ReviewMemoryEntry.id == entry_id,
        )
        .options(undefer(ReviewMemoryEntry.content))
    )


def list_entries(
    db: Session, project_id: int, source_id: int, *, lock: bool = False
) -> list[ReviewMemoryEntry]:
    query = (
        select(ReviewMemoryEntry)
        .join(ReviewMemorySource, ReviewMemorySource.id == ReviewMemoryEntry.source_id)
        .where(ReviewMemorySource.project_id == project_id, ReviewMemorySource.id == source_id)
        .options(undefer(ReviewMemoryEntry.content))
        .order_by(ReviewMemoryEntry.ordinal, ReviewMemoryEntry.id)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(query))


def list_sources(
    db: Session,
    project_id: int,
    filters: MemorySourceQuery,
) -> tuple[list[ReviewMemorySource], int]:
    conditions = [ReviewMemorySource.project_id == project_id]
    if filters.state is not None:
        conditions.append(ReviewMemorySource.state == filters.state)
    else:
        conditions.append(ReviewMemorySource.state != SourceState.DELETED)
    if filters.kind is not None:
        conditions.append(ReviewMemorySource.kind == filters.kind)
    entry_conditions = [ReviewMemoryEntry.source_id == ReviewMemorySource.id]
    if filters.target_type is not None:
        entry_conditions.append(ReviewMemoryEntry.target_type == filters.target_type)
    if filters.issue_type is not None:
        entry_conditions.append(ReviewMemoryEntry.issue_type == filters.issue_type)
    if filters.target_type is not None or filters.issue_type is not None:
        conditions.append(exists(select(ReviewMemoryEntry.id).where(*entry_conditions)))
    if filters.keyword:
        conditions.append(
            or_(
                ReviewMemorySource.title.contains(filters.keyword, autoescape=True),
                exists(
                    select(ReviewMemoryEntry.id).where(
                        ReviewMemoryEntry.source_id == ReviewMemorySource.id,
                        or_(
                            ReviewMemoryEntry.heading.contains(filters.keyword, autoescape=True),
                            ReviewMemoryEntry.content.contains(filters.keyword, autoescape=True),
                        ),
                    )
                ),
            )
        )
    total = db.scalar(select(func.count()).select_from(ReviewMemorySource).where(*conditions)) or 0
    rows = db.scalars(
        select(ReviewMemorySource)
        .where(*conditions)
        .order_by(ReviewMemorySource.updated_at.desc(), ReviewMemorySource.id.desc())
        .offset((filters.page_no - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return list(rows), total


def list_project_core_entries(
    db: Session,
    project_id: int,
    *,
    lock: bool = False,
) -> list[tuple[ReviewMemorySource, ReviewMemoryEntry]]:
    # Keep all targets and path scopes: publication validates their conservative upper bound.
    query = (
        select(ReviewMemorySource, ReviewMemoryEntry)
        .join(ReviewMemoryEntry, ReviewMemoryEntry.source_id == ReviewMemorySource.id)
        .where(
            ReviewMemorySource.project_id == project_id,
            ReviewMemorySource.state == SourceState.PUBLISHED,
            ReviewMemorySource.deleted_at.is_(None),
            ReviewMemoryEntry.state == "ACTIVE",
            ReviewMemoryEntry.load_mode == LoadMode.CORE,
        )
        .options(undefer(ReviewMemoryEntry.content))
        .order_by(ReviewMemorySource.id, ReviewMemoryEntry.ordinal, ReviewMemoryEntry.id)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return list(db.execute(query).all())


def legacy_policy_ids(db: Session, project_id: int, feedback_id: int | None) -> list[int]:
    if feedback_id is None:
        return []
    return list(
        db.scalars(
            select(ProjectReviewPolicy.id)
            .where(
                ProjectReviewPolicy.project_id == project_id,
                ProjectReviewPolicy.source_feedback_id == feedback_id,
            )
            .order_by(ProjectReviewPolicy.id)
        )
    )


def has_duplicate_upload(db: Session, project_id: int, digest: str) -> bool:
    return (
        db.scalar(
            select(ReviewMemorySource.id)
            .where(
                ReviewMemorySource.project_id == project_id,
                ReviewMemorySource.original_sha256 == digest,
                ReviewMemorySource.state != SourceState.DELETED,
            )
            .limit(1)
        )
        is not None
    )


def get_writeback(
    db: Session,
    project_id: int,
    writeback_id: int,
) -> ReviewMemoryWriteback | None:
    return db.scalar(
        select(ReviewMemoryWriteback)
        .join(ReviewItemFeedback, ReviewItemFeedback.id == ReviewMemoryWriteback.feedback_id)
        .where(
            ReviewItemFeedback.project_id == project_id, ReviewMemoryWriteback.id == writeback_id
        )
    )
