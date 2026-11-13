"""Read-only global false-positive summaries; writes retain their project boundary."""

from typing import get_args

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.project_integration.schemas import TargetType
from app.review_feedback.models import ReviewItemFeedback as Feedback
from app.review_memory.management import _reader
from app.review_memory.models import ReviewMemorySource as Source, ReviewMemoryWriteback as Writeback
from app.review_memory.schemas import (
    MemoryFeedbackManagementItem,
    MemoryFeedbackManagementPage,
    MemoryFeedbackManagementQuery,
)
from app.review_record.models import ReviewTask


def list_feedbacks(db: Session, query: MemoryFeedbackManagementQuery) -> MemoryFeedbackManagementPage:
    query = MemoryFeedbackManagementQuery.model_validate(query.model_dump())
    conditions = [Feedback.source_type == "AI_FINDING", Feedback.feedback_type == "FALSE_POSITIVE"]
    if query.project_id is not None:
        conditions.append(Feedback.project_id == query.project_id)
    if query.target_type is not None:
        conditions.append(ReviewTask.target_type == query.target_type)
    if query.status is not None:
        conditions.append(Feedback.status == query.status)
    if query.keyword:
        conditions.append(or_(
            Feedback.risk_title.contains(query.keyword, autoescape=True),
            Feedback.reason_text.contains(query.keyword, autoescape=True),
        ))
    task_match = and_(ReviewTask.id == Feedback.task_id, ReviewTask.project_id == Feedback.project_id)
    with _reader(db) as reader:
        total = reader.scalar(
            select(func.count()).select_from(Feedback).outerjoin(ReviewTask, task_match)
            .where(*conditions)
        ) or 0
        rows = reader.execute(
            select(
                Feedback.id, Feedback.project_id, Feedback.task_id, Feedback.risk_title,
                Feedback.risk_type, Feedback.reason_type,
                func.substr(Feedback.reason_text, 1, 1000).label("reason_text"),
                Feedback.status, Feedback.created_at, ReviewTask.target_type,
            ).outerjoin(ReviewTask, task_match).where(*conditions)
            .order_by(Feedback.id.desc())
            .offset((query.page_no - 1) * query.page_size).limit(query.page_size)
        ).mappings().all()
        ids = [row["id"] for row in rows]
        sources, jobs = {}, {}
        if ids:
            sources = {row.source_feedback_id: row for row in reader.execute(
                select(Source.source_feedback_id, Source.id, Source.version, Source.state)
                .where(Source.source_feedback_id.in_(ids))
            )}
            latest = select(func.max(Writeback.id)).where(Writeback.feedback_id.in_(ids)).group_by(Writeback.feedback_id)
            jobs = {row.feedback_id: row for row in reader.execute(
                select(Writeback.feedback_id, Writeback.id, Writeback.state)
                .where(Writeback.id.in_(latest))
            )}
        items = []
        for row in rows:
            source, job = sources.get(row["id"]), jobs.get(row["id"])
            values = dict(row)
            if values["target_type"] not in get_args(TargetType):
                values["target_type"] = None
            items.append(MemoryFeedbackManagementItem(
                **values,
                memory_source_id=source.id if source else None,
                source_version=source.version if source else None,
                source_state=source.state if source else None,
                writeback_id=job.id if job else None,
                writeback_state=job.state if job else None,
            ))
        return MemoryFeedbackManagementPage(
            items=items, total=total, page_no=query.page_no, page_size=query.page_size,
        )
