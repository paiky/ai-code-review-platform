"""Project-scoped human confirmation; callers own the transaction."""

import hashlib
import json
from datetime import datetime

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, undefer

from app.core.errors import AppError
from app.core.json_utils import read_json, read_json_array, utc_now
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.service import _ai_targets
from app.review_memory.models import ReviewMemorySource, ReviewMemoryWriteback
from app.review_memory.schemas import (
    MemoryCaseConfirmation,
    MemoryEntryDraft,
    MemoryFeedbackDetail,
    MemoryFeedbackPage,
    MemoryFeedbackQuery,
    MemoryFeedbackSummary,
    MemoryKind,
    MemoryWritebackSummary,
)
from app.review_memory.service import (
    assert_version,
    require_project,
    validate_entry_for_publication,
)
from app.review_record.models import ReviewTask


IN_FLIGHT = ("PENDING", "RUNNING", "RETRY_WAIT")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def feedback_digest(record: ReviewItemFeedback) -> str:
    fields = (
        "id",
        "project_id",
        "task_id",
        "source_type",
        "item_fingerprint",
        "review_key",
        "finding_index",
        "risk_type",
        "risk_title",
        "original_risk_level",
        "feedback_type",
        "reason_type",
        "reason_text",
        "missing_context_types_json",
        "item_snapshot_json",
        "status",
        "admin_comment",
        "suggest_as_project_rule",
        "updated_at",
    )
    return hashlib.sha256(
        canonical({key: getattr(record, key) for key in fields}).encode()
    ).hexdigest()


def lock_feedback(db: Session, project_id: int, feedback_id: int) -> ReviewItemFeedback:
    record = db.scalar(
        select(ReviewItemFeedback)
        .where(
            ReviewItemFeedback.id == feedback_id,
            ReviewItemFeedback.project_id == project_id,
            ReviewItemFeedback.source_type == "AI_FINDING",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", "AI feedback not found in project", 404)
    return record


def source_for_feedback(db: Session, feedback_id: int, *, lock: bool = False):
    query = select(ReviewMemorySource).where(ReviewMemorySource.source_feedback_id == feedback_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def finding_available(db: Session, feedback: ReviewItemFeedback) -> bool:
    task = db.get(ReviewTask, feedback.task_id)
    if task is None or task.project_id != feedback.project_id:
        return False
    target = _ai_targets(db, task).get(feedback.item_fingerprint)
    return bool(
        target
        and target.get("reviewKey") == feedback.review_key
        and target.get("findingIndex") == feedback.finding_index
        and canonical(target.get("snapshot"))
        == canonical(read_json(feedback.item_snapshot_json, {}))
    )


def case_entry(request: MemoryCaseConfirmation) -> MemoryEntryDraft:
    labels = ("适用条件", "原误判及原因", "正确判断方法", "下次应查证据", "例外/失效条件")
    values = (
        request.applicability,
        request.misjudgment_cause,
        request.correct_approach,
        request.required_evidence,
        request.exceptions,
    )
    entry = MemoryEntryDraft(
        heading=request.title,
        content="\n\n".join(
            f"## {label}\n\n{value}" for label, value in zip(labels, values) if value
        ),
        target_type=request.target_type,
        issue_type=request.issue_type,
        path_globs=request.path_globs,
        keywords=request.keywords,
    )
    validate_entry_for_publication(MemoryKind.PITFALL, entry)
    return entry


def writeback_summary(job: ReviewMemoryWriteback) -> MemoryWritebackSummary:
    return MemoryWritebackSummary(
        id=job.id,
        feedback_id=job.feedback_id,
        source_id=job.source_id,
        state=job.state,
        attempts=job.attempts,
        last_error_code=job.last_error_code,
    )


def _summary(db: Session, record: ReviewItemFeedback) -> MemoryFeedbackSummary:
    source = source_for_feedback(db, record.id)
    job = db.scalar(
        select(ReviewMemoryWriteback)
        .where(ReviewMemoryWriteback.feedback_id == record.id)
        .order_by(ReviewMemoryWriteback.id.desc())
        .limit(1)
    )
    return MemoryFeedbackSummary(
        id=record.id,
        project_id=record.project_id,
        task_id=record.task_id,
        review_key=record.review_key,
        item_fingerprint=record.item_fingerprint,
        risk_title=record.risk_title,
        risk_type=record.risk_type,
        feedback_type=record.feedback_type,
        reason_type=record.reason_type,
        reason_text=record.reason_text,
        status=record.status,
        feedback_digest=feedback_digest(record),
        memory_source_id=source.id if source else None,
        source_version=source.version if source else None,
        source_state=source.state if source else None,
        writeback_id=job.id if job else None,
        writeback_state=job.state if job else None,
    )


def list_feedbacks(db: Session, project_id: int, query: MemoryFeedbackQuery) -> MemoryFeedbackPage:
    require_project(db, project_id)
    conditions = [
        ReviewItemFeedback.project_id == project_id,
        ReviewItemFeedback.source_type == "AI_FINDING",
    ]
    if query.feedback_type:
        conditions.append(ReviewItemFeedback.feedback_type == query.feedback_type)
    if query.status:
        conditions.append(ReviewItemFeedback.status == query.status)
    total = db.scalar(select(func.count()).select_from(ReviewItemFeedback).where(*conditions)) or 0
    records = db.scalars(
        select(ReviewItemFeedback)
        .where(*conditions)
        .order_by(ReviewItemFeedback.id.desc())
        .offset((query.page_no - 1) * query.page_size)
        .limit(query.page_size)
    )
    return MemoryFeedbackPage(
        items=[_summary(db, row) for row in records],
        total=total,
        page_no=query.page_no,
        page_size=query.page_size,
    )


def get_feedback_detail(db: Session, project_id: int, feedback_id: int) -> MemoryFeedbackDetail:
    record = db.scalar(
        select(ReviewItemFeedback).where(
            ReviewItemFeedback.id == feedback_id,
            ReviewItemFeedback.project_id == project_id,
            ReviewItemFeedback.source_type == "AI_FINDING",
        )
    )
    if record is None:
        raise AppError("RESOURCE_NOT_FOUND", "AI feedback not found in project", 404)
    return MemoryFeedbackDetail(
        **_summary(db, record).model_dump(),
        item_snapshot=read_json(record.item_snapshot_json, {}),
        missing_context_types=read_json_array(record.missing_context_types_json),
        task_url=f"/tasks/{record.task_id}",
        finding_available=finding_available(db, record),
    )


def finish_job(job: ReviewMemoryWriteback, state: str, code: str | None, now: datetime) -> None:
    job.state = state
    job.last_error_code = code
    job.updated_at = now
    job.finished_at = now
    job.lease_owner = None
    job.lease_until = None


def invalidate_feedback_memory(db: Session, feedback_id: int) -> None:
    """Called with the feedback row locked, in the original feedback write transaction."""
    # Legacy feedback remains usable before the additive memory migrations are installed.
    inspector = inspect(db.connection())
    if not all(
        inspector.has_table(name) for name in ("review_memory_sources", "review_memory_writebacks")
    ):
        return
    source = source_for_feedback(db, feedback_id, lock=True)
    now = utc_now()
    if source is not None and source.state != "DELETED":
        source.state = "DISABLED"
        source.version += 1
        source.updated_at = now
    jobs = db.scalars(
        select(ReviewMemoryWriteback)
        .where(
            ReviewMemoryWriteback.feedback_id == feedback_id,
            ReviewMemoryWriteback.state.in_(IN_FLIGHT),
        )
        .order_by(ReviewMemoryWriteback.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    for job in jobs:
        finish_job(job, "CANCELLED_STALE_SOURCE", "MEMORY_FEEDBACK_CHANGED", now)
    db.flush()


def confirm_feedback(
    db: Session, project_id: int, feedback_id: int, request: MemoryCaseConfirmation
) -> MemoryWritebackSummary:
    request = MemoryCaseConfirmation.model_validate(request.model_dump())
    case_entry(request)
    feedback = lock_feedback(db, project_id, feedback_id)
    source = source_for_feedback(db, feedback_id, lock=True)
    payload = request.model_dump(mode="json", exclude={"expected_feedback_digest"})
    serialized = canonical(payload)
    key = hashlib.sha256(
        f"{feedback_id}:{request.expected_feedback_digest}:{serialized}".encode()
    ).hexdigest()
    jobs = list(
        db.scalars(
            select(ReviewMemoryWriteback)
            .where(ReviewMemoryWriteback.feedback_id == feedback_id)
            .options(undefer(ReviewMemoryWriteback.confirmation_json))
            .order_by(ReviewMemoryWriteback.id.desc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    current_digest = feedback_digest(feedback)
    for job in jobs:
        if job.idempotency_key == key:
            if job.state in ("FAILED", "CANCELLED_STALE_SOURCE"):
                return writeback_summary(job)
            source_valid = (
                source is None
                if job.state != "SUCCEEDED"
                else bool(
                    source
                    and source.state == "PUBLISHED"
                    and source.deleted_at is None
                    and source.version == (job.expected_source_version or 0) + 1
                )
            )
            if job.state in IN_FLIGHT and source:
                source_valid = (
                    source.version == job.expected_source_version and source.state != "DELETED"
                )
            if job.feedback_digest != current_digest or not source_valid:
                raise AppError("MEMORY_VERSION_CONFLICT", "Confirmation is no longer current", 409)
            return writeback_summary(job)
    if request.expected_feedback_digest != current_digest:
        raise AppError("MEMORY_FEEDBACK_CHANGED", "Feedback changed; reload before confirming", 409)
    if feedback.feedback_type != "FALSE_POSITIVE" or feedback.status not in ("PENDING", "VALID"):
        raise AppError(
            "MEMORY_FEEDBACK_NOT_CONFIRMABLE",
            "Only pending/valid false positives can be confirmed",
            409,
        )
    if not finding_available(db, feedback):
        raise AppError(
            "MEMORY_FINDING_UNAVAILABLE", "Saved AI finding no longer matches feedback", 409
        )
    business_payload = {k: v for k, v in payload.items() if k != "expected_source_version"}
    for job in jobs:
        old = json.loads(job.confirmation_json)
        same_business_payload = {
            k: v for k, v in old.items() if k != "expected_source_version"
        } == business_payload
        if (
            job.feedback_digest == current_digest
            and same_business_payload
            and job.expected_source_version == request.expected_source_version
            and job.state in ("FAILED", "CANCELLED_STALE_SOURCE")
        ):
            return writeback_summary(job)
        source_valid = (
            source is None
            and job.expected_source_version is None
            and job.state in IN_FLIGHT
            or source is not None
            and source.deleted_at is None
            and source.version == (job.expected_source_version or 0) + (job.state == "SUCCEEDED")
            and (source.state == "PUBLISHED" or job.state in IN_FLIGHT)
        )
        if (
            job.feedback_digest == current_digest
            and same_business_payload
            and (job.state in IN_FLIGHT or job.state == "SUCCEEDED")
            and source_valid
        ):
            return writeback_summary(job)
    if source:
        if source.deleted_at or source.state == "DELETED":
            raise AppError("MEMORY_STATE_CONFLICT", "Deleted cases cannot be restored", 409)
        assert_version(source.version, request.expected_source_version)
    elif request.expected_source_version is not None:
        raise AppError("MEMORY_VERSION_CONFLICT", "Case does not exist", 409)
    if feedback.status == "PENDING":
        feedback.status = "VALID"
        feedback.updated_at = datetime.now()
        db.flush()
        # DATETIME precision differs from memory timestamps; hash the value actually persisted.
        db.refresh(feedback)
    now = utc_now()
    for job in jobs:
        if job.state in IN_FLIGHT:
            finish_job(job, "CANCELLED_STALE_SOURCE", "MEMORY_CONFIRMATION_SUPERSEDED", now)
    job = ReviewMemoryWriteback(
        feedback_id=feedback_id,
        idempotency_key=key,
        feedback_digest=feedback_digest(feedback),
        confirmation_json=serialized,
        expected_source_version=request.expected_source_version,
        state="PENDING",
        attempts=0,
        next_attempt_at=now,
        confirmed_by=request.operator_name,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    return writeback_summary(job)
