from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, undefer

from app.project_integration.models import Project
from app.project_review_policy.models import ProjectReviewPolicy
from app.review_feedback.models import ReviewItemFeedback
from app.review_memory.models import (
    ReviewMemoryEntry,
    ReviewMemoryProjectSource,
    ReviewMemorySource,
    ReviewMemoryWriteback,
)
from app.review_memory.schemas import (
    BindingState,
    EntryState,
    LoadMode,
    MemoryBindingQuery,
    MemoryLibraryQuery,
    MemorySourceQuery,
    SourceState,
    SourceVisibility,
)


def shared_source_conditions() -> list:
    return [
        ReviewMemorySource.visibility == SourceVisibility.SHARED,
        ReviewMemorySource.state == SourceState.PUBLISHED,
        ReviewMemorySource.deleted_at.is_(None),
        ReviewMemorySource.kind.in_(("STANDARD", "ARCHITECTURE", "SKILL")),
        ReviewMemorySource.origin != "FEEDBACK",
        or_(
            ReviewMemorySource.replacement_of_id.is_(None),
            ReviewMemorySource.confirmed_at.is_not(None),
        ),
    ]


def get_project(db: Session, project_id: int, *, lock: bool = False) -> Project | None:
    query = select(Project).where(Project.id == project_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def get_source(
    db: Session,
    project_id: int | None,
    source_id: int,
    *,
    lock: bool = False,
) -> ReviewMemorySource | None:
    query = select(ReviewMemorySource).where(ReviewMemorySource.id == source_id)
    if project_id is not None:
        query = query.where(ReviewMemorySource.project_id == project_id)
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
    project_id: int | None,
    filters: MemorySourceQuery,
) -> tuple[list[ReviewMemorySource], int]:
    if project_id is None:
        conditions = shared_source_conditions()
    elif filters.view == "USED":
        binding_conditions = [
            ReviewMemoryProjectSource.source_id == ReviewMemorySource.id,
            ReviewMemoryProjectSource.project_id == project_id,
            ReviewMemoryProjectSource.state == BindingState.ACTIVE,
        ]
        if filters.target_type is not None:
            binding_conditions.append(
                or_(
                    ReviewMemoryProjectSource.target_type.is_(None),
                    ReviewMemoryProjectSource.target_type == filters.target_type,
                )
            )
        conditions = [
            exists(select(ReviewMemoryProjectSource.id).where(*binding_conditions)),
            ReviewMemorySource.state == SourceState.PUBLISHED,
            ReviewMemorySource.deleted_at.is_(None),
            or_(ReviewMemorySource.project_id == project_id, and_(*shared_source_conditions())),
        ]
    else:
        conditions = [ReviewMemorySource.project_id == project_id]
    if filters.state is not None:
        conditions.append(ReviewMemorySource.state == filters.state)
    else:
        conditions.append(ReviewMemorySource.state != SourceState.DELETED)
    if filters.kind is not None:
        conditions.append(ReviewMemorySource.kind == filters.kind)
    entry_conditions = [ReviewMemoryEntry.source_id == ReviewMemorySource.id]
    if filters.target_type is not None:
        entry_conditions.append(
            or_(
                ReviewMemoryEntry.target_type.is_(None),
                ReviewMemoryEntry.target_type == filters.target_type,
            )
            if filters.view == "USED"
            else ReviewMemoryEntry.target_type == filters.target_type
        )
    if filters.issue_type is not None:
        entry_conditions.append(ReviewMemoryEntry.issue_type == filters.issue_type)
    if filters.target_type is not None or filters.issue_type is not None:
        if project_id is None or filters.view == "USED":
            entry_conditions.append(ReviewMemoryEntry.state == EntryState.ACTIVE)
        conditions.append(exists(select(ReviewMemoryEntry.id).where(*entry_conditions)))
    if filters.keyword:
        conditions.append(
            or_(
                ReviewMemorySource.title.contains(filters.keyword, autoescape=True),
                exists(
                    select(ReviewMemoryEntry.id).where(
                        ReviewMemoryEntry.source_id == ReviewMemorySource.id,
                        or_(
                            ReviewMemoryEntry.state == EntryState.ACTIVE,
                            and_(project_id is not None, filters.view == "OWNED"),
                        ),
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


def list_library_sources(
    db: Session, filters: MemoryLibraryQuery
) -> tuple[list[ReviewMemorySource], int]:
    conditions = [
        ReviewMemorySource.state == filters.state
        if filters.state is not None
        else ReviewMemorySource.state != SourceState.DELETED
    ]
    if filters.owner_project_id is not None:
        conditions.append(ReviewMemorySource.project_id == filters.owner_project_id)
    if filters.using_project_id is not None:
        conditions.append(
            exists(
                select(ReviewMemoryProjectSource.id).where(
                    ReviewMemoryProjectSource.source_id == ReviewMemorySource.id,
                    ReviewMemoryProjectSource.project_id == filters.using_project_id,
                    ReviewMemoryProjectSource.state == BindingState.ACTIVE,
                )
            )
        )
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


def library_binding_summaries(
    db: Session, source_ids: list[int]
) -> dict[int, tuple[int, list[int]]]:
    if not source_ids:
        return {}
    ranked = (
        select(
            ReviewMemoryProjectSource.source_id,
            ReviewMemoryProjectSource.project_id,
            func.count().over(partition_by=ReviewMemoryProjectSource.source_id).label("total"),
            func.row_number()
            .over(
                partition_by=ReviewMemoryProjectSource.source_id,
                order_by=ReviewMemoryProjectSource.project_id,
            )
            .label("ordinal"),
        )
        .where(
            ReviewMemoryProjectSource.source_id.in_(source_ids),
            ReviewMemoryProjectSource.state == BindingState.ACTIVE,
        )
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.source_id, ranked.c.project_id, ranked.c.total)
        .where(ranked.c.ordinal <= 3)
        .order_by(ranked.c.source_id, ranked.c.project_id)
    )
    result = {}
    for source_id, project_id, total in rows:
        result.setdefault(source_id, (total, []))[1].append(project_id)
    return result


def list_source_projects(
    db: Session, source_id: int, filters: MemoryBindingQuery
) -> tuple[list[ReviewMemoryProjectSource], int]:
    conditions = [
        ReviewMemoryProjectSource.source_id == source_id,
        ReviewMemoryProjectSource.state == filters.state,
    ]
    total = (
        db.scalar(select(func.count()).select_from(ReviewMemoryProjectSource).where(*conditions))
        or 0
    )
    rows = db.scalars(
        select(ReviewMemoryProjectSource)
        .where(*conditions)
        .order_by(ReviewMemoryProjectSource.project_id, ReviewMemoryProjectSource.id)
        .offset((filters.page_no - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return list(rows), total


def list_project_bindings(
    db: Session, project_id: int, filters: MemoryBindingQuery
) -> tuple[list, int]:
    conditions = [
        ReviewMemoryProjectSource.project_id == project_id,
        ReviewMemoryProjectSource.state == filters.state,
    ]
    total = (
        db.scalar(select(func.count()).select_from(ReviewMemoryProjectSource).where(*conditions))
        or 0
    )
    active_entries = exists(
        select(ReviewMemoryEntry.id).where(
            ReviewMemoryEntry.source_id == ReviewMemoryProjectSource.source_id,
            ReviewMemoryEntry.state == EntryState.ACTIVE,
        )
    )
    rows = db.execute(
        select(ReviewMemoryProjectSource, ReviewMemorySource, active_entries)
        .outerjoin(ReviewMemorySource, ReviewMemorySource.id == ReviewMemoryProjectSource.source_id)
        .where(*conditions)
        .order_by(ReviewMemoryProjectSource.updated_at.desc(), ReviewMemoryProjectSource.id.desc())
        .offset((filters.page_no - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return list(rows), total


def get_project_source_binding(
    db: Session, project_id: int, source_id: int, *, lock: bool = False
) -> ReviewMemoryProjectSource | None:
    query = select(ReviewMemoryProjectSource).where(
        ReviewMemoryProjectSource.project_id == project_id,
        ReviewMemoryProjectSource.source_id == source_id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def list_source_bindings(
    db: Session, source_id: int, *, lock: bool = False
) -> list[ReviewMemoryProjectSource]:
    query = (
        select(ReviewMemoryProjectSource)
        .where(ReviewMemoryProjectSource.source_id == source_id)
        .order_by(ReviewMemoryProjectSource.project_id, ReviewMemoryProjectSource.id)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(query))


def project_bindings_by_source(
    db: Session, project_id: int, source_ids: list[int]
) -> dict[int, ReviewMemoryProjectSource]:
    return {
        row.source_id: row
        for row in db.scalars(
            select(ReviewMemoryProjectSource).where(
                ReviewMemoryProjectSource.project_id == project_id,
                ReviewMemoryProjectSource.source_id.in_(source_ids),
            )
        )
    }


def list_project_core_entries(
    db: Session,
    project_id: int,
    *,
    lock: bool = False,
) -> list[tuple[ReviewMemorySource, ReviewMemoryEntry, ReviewMemoryProjectSource]]:
    # Keep all targets and path scopes: publication validates their conservative upper bound.
    query = (
        select(ReviewMemorySource, ReviewMemoryEntry, ReviewMemoryProjectSource)
        .join(ReviewMemoryEntry, ReviewMemoryEntry.source_id == ReviewMemorySource.id)
        .join(
            ReviewMemoryProjectSource,
            ReviewMemoryProjectSource.source_id == ReviewMemorySource.id,
        )
        .where(
            ReviewMemoryProjectSource.project_id == project_id,
            ReviewMemoryProjectSource.state == BindingState.ACTIVE,
            or_(ReviewMemorySource.project_id == project_id, and_(*shared_source_conditions())),
            ReviewMemorySource.state == SourceState.PUBLISHED,
            ReviewMemorySource.deleted_at.is_(None),
            ReviewMemoryEntry.state == "ACTIVE",
            ReviewMemoryEntry.load_mode == LoadMode.CORE,
            or_(
                ReviewMemoryProjectSource.target_type.is_(None),
                ReviewMemoryEntry.target_type.is_(None),
                ReviewMemoryProjectSource.target_type == ReviewMemoryEntry.target_type,
            ),
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
