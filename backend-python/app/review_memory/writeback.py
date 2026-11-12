"""Durable, bounded feedback-memory writeback using the existing SQL table."""

from datetime import timedelta
import hashlib
import json
import logging
import time
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import undefer

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.json_utils import utc_now
from app.review_memory.feedback import (
    case_entry,
    feedback_digest,
    finding_available,
    finish_job,
    lock_feedback,
    source_for_feedback,
)
from app.review_memory.models import (
    ReviewMemoryEntry,
    ReviewMemoryProjectSource,
    ReviewMemorySource,
    ReviewMemoryWriteback,
)
from app.review_memory.schemas import MemoryCaseConfirmation


log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LEASE_SECONDS = 60


def _claim_batch(session_factory) -> list[tuple[int, int, str, int]]:
    now = utc_now()
    owner = uuid4().hex
    claims = []
    with session_factory() as db:
        dialect = db.connection().dialect
        skip_locked = (
            dialect.name == "mysql"
            and not getattr(dialect, "is_mariadb", False)
            and (dialect.server_version_info or (0,)) >= (8,)
        )
        jobs = db.scalars(
            select(ReviewMemoryWriteback)
            .where(
                or_(
                    and_(
                        ReviewMemoryWriteback.state.in_(("PENDING", "RETRY_WAIT")),
                        ReviewMemoryWriteback.next_attempt_at <= now,
                    ),
                    and_(
                        ReviewMemoryWriteback.state == "RUNNING",
                        ReviewMemoryWriteback.lease_until <= now,
                    ),
                )
            )
            .order_by(ReviewMemoryWriteback.id)
            .limit(20)
            .with_for_update(skip_locked=skip_locked)
        )
        for job in jobs:
            if job.attempts >= MAX_ATTEMPTS:
                finish_job(job, "FAILED", "MEMORY_WRITEBACK_ATTEMPTS_EXHAUSTED", now)
                continue
            job.attempts += 1
            job.state = "RUNNING"
            job.lease_owner = owner
            job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
            job.updated_at = now
            claims.append((job.id, job.feedback_id, owner, job.attempts))
        db.commit()
    return claims


def _locked_claim(db, claim):
    job_id, feedback_id, owner, attempt = claim
    # Never hold a job lock while waiting for a feedback/source lock.
    feedback = db.scalar(
        select(ReviewMemoryWriteback.feedback_id).where(ReviewMemoryWriteback.id == job_id)
    )
    if feedback != feedback_id:
        return None
    from app.review_feedback.models import ReviewItemFeedback

    project_id = db.scalar(
        select(ReviewItemFeedback.project_id).where(ReviewItemFeedback.id == feedback_id)
    )
    if project_id is None:
        job = db.scalar(
            select(ReviewMemoryWriteback)
            .where(ReviewMemoryWriteback.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if _owns(job, owner, attempt):
            finish_job(job, "CANCELLED_STALE_SOURCE", "MEMORY_FEEDBACK_MISSING", utc_now())
        return None
    feedback = lock_feedback(db, project_id, feedback_id)
    source = source_for_feedback(db, feedback_id, lock=True)
    job = db.scalar(
        select(ReviewMemoryWriteback)
        .where(ReviewMemoryWriteback.id == job_id)
        .options(undefer(ReviewMemoryWriteback.confirmation_json))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not _owns(job, owner, attempt):
        return None
    return feedback, source, job


def _owns(job, owner, attempt) -> bool:
    return bool(
        job
        and job.state == "RUNNING"
        and job.lease_owner == owner
        and job.attempts == attempt
        and job.lease_until
        and job.lease_until > utc_now()
    )


def _write_claim(session_factory, claim) -> tuple[str, str | None]:
    with session_factory() as db:
        locked = _locked_claim(db, claim)
        if locked is None:
            db.commit()
            return "SKIPPED", None
        feedback, source, job = locked
        now = utc_now()
        if (
            feedback.feedback_type != "FALSE_POSITIVE"
            or feedback.status != "VALID"
            or feedback_digest(feedback) != job.feedback_digest
            or not finding_available(db, feedback)
        ):
            finish_job(job, "CANCELLED_STALE_SOURCE", "MEMORY_FEEDBACK_CHANGED", now)
            db.commit()
            return "CANCELLED_STALE_SOURCE", "MEMORY_FEEDBACK_CHANGED"
        if (
            source
            and (
                source.deleted_at
                or source.state == "DELETED"
                or source.version != job.expected_source_version
            )
            or source is None
            and job.expected_source_version is not None
        ):
            finish_job(job, "CANCELLED_STALE_SOURCE", "MEMORY_VERSION_CONFLICT", now)
            db.commit()
            return "CANCELLED_STALE_SOURCE", "MEMORY_VERSION_CONFLICT"
        payload = json.loads(job.confirmation_json)
        request = MemoryCaseConfirmation(expected_feedback_digest=job.feedback_digest, **payload)
        entry = case_entry(request)
        if source is None:
            source = ReviewMemorySource(
                project_id=feedback.project_id,
                visibility="PROJECT",
                kind="PITFALL",
                origin="FEEDBACK",
                title=request.title,
                state="PUBLISHED",
                version=1,
                source_feedback_id=feedback.id,
                created_at=now,
                updated_at=now,
            )
            db.add(source)
            db.flush()
            db.add(
                ReviewMemoryProjectSource(
                    project_id=feedback.project_id,
                    source_id=source.id,
                    state="ACTIVE",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            # A disabled source may only be restored by this *new*, versioned human confirmation.
            source.version += 1
            source.title = request.title
            source.state = "PUBLISHED"
            source.updated_at = now
        source.feedback_digest = job.feedback_digest
        source.confirmed_by = job.confirmed_by
        source.confirmed_at = now
        record = db.scalar(
            select(ReviewMemoryEntry)
            .where(ReviewMemoryEntry.source_id == source.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if record is None:
            record = ReviewMemoryEntry(
                source_id=source.id,
                section_key="feedback-case",
                ordinal=0,
                version=1,
                created_at=now,
            )
            db.add(record)
        else:
            record.version += 1
        record.heading = entry.heading
        record.content = entry.content
        record.target_type = entry.target_type
        record.issue_type = entry.issue_type
        record.path_globs_json = json.dumps(entry.path_globs, ensure_ascii=False)
        record.keywords_json = json.dumps(entry.keywords, ensure_ascii=False)
        record.load_mode = "ON_DEMAND"
        record.state = "ACTIVE"
        record.content_sha256 = hashlib.sha256(entry.content.encode()).hexdigest()
        record.validation_errors_json = "[]"
        record.updated_at = now
        job.source_id = source.id
        finish_job(job, "SUCCEEDED", None, now)
        db.commit()
        return "SUCCEEDED", None


def _transient(exception: Exception) -> bool:
    if not isinstance(exception, DBAPIError):
        return False
    code = getattr(exception.orig, "args", (None,))[0]
    return exception.connection_invalidated or code in {1040, 1205, 1213, 2006, 2013}


def _record_failure(session_factory, claim, exception: Exception) -> tuple[str, str | None]:
    with session_factory() as db:
        locked = _locked_claim(db, claim)
        if locked is None:
            db.commit()
            return "SKIPPED", None
        _, _, job = locked
        now = utc_now()
        if _transient(exception) and job.attempts < MAX_ATTEMPTS:
            job.state = "RETRY_WAIT"
            job.last_error_code = "MEMORY_DATABASE_TEMPORARY"
            job.next_attempt_at = now + timedelta(seconds=(30, 120)[job.attempts - 1])
            job.updated_at = now
            job.lease_owner = None
            job.lease_until = None
        else:
            code = (
                exception.code
                if isinstance(exception, AppError)
                else (
                    "MEMORY_CONFIRMATION_INVALID"
                    if isinstance(exception, (ValidationError, ValueError))
                    else "MEMORY_WRITEBACK_FAILED"
                )
            )
            finish_job(job, "FAILED", code, now)
        result = job.state, job.last_error_code
        db.commit()
        return result


def sweep_writebacks(session_factory=SessionLocal) -> int:
    claims = _claim_batch(session_factory)
    for claim in claims:
        started = time.monotonic()
        try:
            state, code = _write_claim(session_factory, claim)
        except Exception as exception:
            try:
                state, code = _record_failure(session_factory, claim, exception)
            except Exception:
                # The durable lease is reclaimed after restart/database recovery.
                log.warning("Memory writeback failure recording deferred id=%s", claim[0])
                state, code = "RUNNING", "MEMORY_FAILURE_RECORDING_DEFERRED"
        log.info(
            "Memory writeback id=%s attempt=%s state=%s elapsed_ms=%s code=%s",
            claim[0],
            claim[3],
            state,
            int((time.monotonic() - started) * 1000),
            code,
        )
    return len(claims)
