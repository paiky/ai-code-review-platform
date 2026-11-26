from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewSettings
from app.core.errors import AppError
from app.core.json_utils import utc_now
from app.evaluation.models import EvaluationCase, EvaluationRun
from app.project_integration.models import Project
from app.review_quality.monitoring_collection import collect_monitoring_report
from app.review_quality.monitoring_models import MonitoringIssue, MonitoringReport
from app.review_quality.monitoring_schemas import (
    MonitoringCollection,
    MonitoringIssueDraft,
    MonitoringIssueResponse,
    MonitoringIssueSnapshot,
    MonitoringReportResponse,
    MonitoringSnapshot,
    ReportSource,
    UpdateMonitoringIssue,
)


log = logging.getLogger(__name__)
RULE_VERSION = "1"
_REPORT_ATTEMPT_TIMEOUT = timedelta(minutes=10)
_MAX_REPORT_WINDOW = timedelta(days=31)
_ISSUE_EDIT_FIELDS = {
    "assignee": "assignee",
    "resolution": "resolution",
    "acceptanceCriteria": "acceptance_criteria",
    "evaluationCaseId": "evaluation_case_id",
    "evaluationRunId": "evaluation_run_id",
}


def monitoring_enabled(db: Session) -> bool:
    return bool(db.scalar(select(CodeQualityReviewSettings.review_quality_monitoring_enabled).where(
        CodeQualityReviewSettings.id == 1,
    )))


def require_monitoring_enabled(db: Session) -> None:
    if not monitoring_enabled(db):
        raise AppError("RESOURCE_NOT_FOUND", "Monitoring is unavailable", 404)


def generate_monitoring_report(
    db: Session,
    *,
    project_id: int,
    start_at: datetime,
    end_at: datetime,
    idempotency_key: str,
    source: ReportSource = "MANUAL",
) -> MonitoringReportResponse:
    require_monitoring_enabled(db)
    if source not in {"MANUAL", "SCHEDULED"}:
        raise AppError("VALIDATION_ERROR", "Unsupported monitoring report source")
    if not 1 <= len(idempotency_key) <= 128 or not all(
        "!" <= char <= "~" for char in idempotency_key
    ):
        raise AppError("VALIDATION_ERROR", "Invalid monitoring idempotency key")
    if start_at.utcoffset() is None or end_at.utcoffset() is None:
        raise AppError("VALIDATION_ERROR", "Monitoring dates must include a timezone")
    try:
        start, end = _storage_utc(start_at), _storage_utc(end_at)
    except OverflowError as error:
        raise AppError(
            "VALIDATION_ERROR", "Monitoring dates are outside the supported range"
        ) from error
    if start.year < 1000 or not timedelta(0) < end - start <= _MAX_REPORT_WINDOW:
        raise AppError("VALIDATION_ERROR", "Choose a positive monitoring window of at most 31 days")
    if db.scalar(select(Project.id).where(Project.id == project_id)) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Monitoring project does not exist", 404)

    request_hash = sha256(idempotency_key.encode("ascii")).hexdigest()
    request_query = select(MonitoringReport).where(
        MonitoringReport.project_id == project_id,
        MonitoringReport.source == source,
        MonitoringReport.idempotency_hash == request_hash,
    )
    record = db.scalar(request_query)
    if record is None:
        now = utc_now()
        attempt_token = str(uuid4())
        record = MonitoringReport(
            project_id=project_id,
            source=source,
            idempotency_hash=request_hash,
            start_at=start,
            end_at=end,
            status="RUNNING",
            rule_version=RULE_VERSION,
            attempt_token=attempt_token,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            db.flush()
            report_id = record.id
            db.commit()
        except IntegrityError:
            db.rollback()
            record = db.scalar(request_query)
            if record is None:
                raise
        else:
            return _execute_report(db, project_id, report_id, attempt_token, start, end)
    if record.start_at != start or record.end_at != end:
        raise AppError(
            "MONITORING_REQUEST_CONFLICT",
            "The idempotency key is already used by a different window",
            409,
        )
    return _retry_report(db, record)


def retry_monitoring_report(
    db: Session, project_id: int, report_id: int
) -> MonitoringReportResponse:
    return _retry_report(db, _get_report(db, project_id, report_id))


def list_monitoring_reports(db: Session, project_id: int, page_no: int, page_size: int) -> dict:
    reports = select(MonitoringReport).where(MonitoringReport.project_id == project_id)
    total = (
        db.scalar(
            select(func.count(MonitoringReport.id)).where(MonitoringReport.project_id == project_id)
        )
        or 0
    )
    page = (
        reports.order_by(MonitoringReport.id.desc())
        .offset((page_no - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            _report_response(record, include_snapshot=False).model_dump(mode="json")
            for record in db.scalars(page)
        ],
        "total": total,
        "pageNo": page_no,
        "pageSize": page_size,
    }


def get_monitoring_report(db: Session, project_id: int, report_id: int) -> MonitoringReportResponse:
    return _report_response(_get_report(db, project_id, report_id))


def get_monitoring_issue(db: Session, project_id: int, issue_id: int) -> MonitoringIssueResponse:
    return _issue_response(_get_issue(db, project_id, issue_id))


def update_monitoring_issue(
    db: Session, project_id: int, issue_id: int, change: UpdateMonitoringIssue
) -> MonitoringIssueResponse:
    issue = _get_issue(db, project_id, issue_id)
    if change.version != issue.version:
        raise AppError("MONITORING_ISSUE_CONFLICT", "The issue changed since it was read", 409)
    values = {
        column: getattr(change, field)
        for field, column in _ISSUE_EDIT_FIELDS.items()
        if field in change.model_fields_set
    }
    _validate_reference(db, EvaluationCase, change.evaluationCaseId, project_id)
    _validate_reference(db, EvaluationRun, change.evaluationRunId, project_id)
    if change.status == "DISMISSED" and not values.get("resolution", issue.resolution):
        raise AppError("VALIDATION_ERROR", "Record a reason before dismissing an issue")
    if change.status is not None and change.status != issue.status:
        values["status"] = change.status
        values["closed_at"] = utc_now() if change.status == "CLOSED" else None
    updated = db.execute(
        update(MonitoringIssue)
        .where(
            MonitoringIssue.id == issue_id,
            MonitoringIssue.project_id == project_id,
            MonitoringIssue.version == change.version,
        )
        .values(**values, version=MonitoringIssue.version + 1)
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        db.rollback()
        raise AppError("MONITORING_ISSUE_CONFLICT", "The issue changed since it was read", 409)
    db.commit()
    return get_monitoring_issue(db, project_id, issue_id)


def _retry_report(db: Session, report: MonitoringReport) -> MonitoringReportResponse:
    now = utc_now()
    if report.status == "SUCCEEDED" or (
        report.status == "RUNNING" and report.updated_at > now - _REPORT_ATTEMPT_TIMEOUT
    ):
        return _report_response(report)
    report_id, project_id = report.id, report.project_id
    start, end = report.start_at, report.end_at
    attempt_token = str(uuid4())
    acquired = db.execute(
        update(MonitoringReport)
        .where(
            MonitoringReport.id == report_id,
            MonitoringReport.project_id == project_id,
            MonitoringReport.attempt_token == report.attempt_token,
            MonitoringReport.status == report.status,
        )
        .values(
            status="RUNNING",
            updated_at=now,
            finished_at=None,
            error_code=None,
            rule_version=RULE_VERSION,
            attempt_token=attempt_token,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if acquired.rowcount != 1:
        return get_monitoring_report(db, project_id, report_id)
    return _execute_report(db, project_id, report_id, attempt_token, start, end)


def _execute_report(
    db: Session, project_id: int, report_id: int, attempt_token: str, start: datetime, end: datetime
) -> MonitoringReportResponse:
    claim = (
        MonitoringReport.id == report_id,
        MonitoringReport.project_id == project_id,
        MonitoringReport.status == "RUNNING",
        MonitoringReport.attempt_token == attempt_token,
    )
    try:
        collected = MonitoringCollection.model_validate(
            collect_monitoring_report(db, project_id=project_id, start_at=start, end_at=end)
        )
        db.rollback()
        now = utc_now()
        current = db.execute(
            update(MonitoringReport)
            .where(*claim)
            .values(status="SUCCEEDED", updated_at=now, finished_at=now)
            .execution_options(synchronize_session=False)
        )
        if current.rowcount != 1:
            db.rollback()
            return get_monitoring_report(db, project_id, report_id)
        # Serialize issue merging for this pilot project across different report windows.
        db.execute(
            select(Project.id).where(Project.id == project_id).with_for_update()
        ).scalar_one()
        snapshot_issues = [
            _merge_issue(db, project_id, report_id, draft) for draft in collected.issues
        ]
        snapshot = MonitoringSnapshot(
            metrics=collected.metrics,
            truncated=collected.truncated,
            issues=snapshot_issues,
            releaseCohorts=collected.releaseCohorts,
        )
        db.execute(
            update(MonitoringReport)
            .where(MonitoringReport.id == report_id)
            .values(snapshot_json=snapshot.model_dump_json())
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception as error:
        db.rollback()
        log.warning("Monitoring report %s failed (%s)", report_id, type(error).__name__)
        now = utc_now()
        db.execute(
            update(MonitoringReport)
            .where(*claim)
            .values(
                status="FAILED",
                updated_at=now,
                finished_at=now,
                error_code="MONITORING_GENERATION_FAILED",
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
    return get_monitoring_report(db, project_id, report_id)


def _merge_issue(
    db: Session, project_id: int, report_id: int, draft: MonitoringIssueDraft
) -> MonitoringIssueSnapshot:
    first, last = _storage_utc(draft.firstSeenAt), _storage_utc(draft.lastSeenAt)
    if first > last:
        raise ValueError("Monitoring occurrence bounds are reversed")
    issue = db.scalar(
        select(MonitoringIssue)
        .where(
            MonitoringIssue.project_id == project_id,
            MonitoringIssue.engine == draft.engine,
            MonitoringIssue.issue_type == draft.issueType,
            MonitoringIssue.diagnostic_type == draft.diagnosticType,
        )
        .with_for_update()
    )
    if issue is None:
        issue = MonitoringIssue(
            project_id=project_id,
            engine=draft.engine,
            issue_type=draft.issueType,
            diagnostic_type=draft.diagnosticType,
            title=draft.title,
            priority=draft.priority,
            status="PENDING_REVIEW",
            version=1,
            first_seen_at=first,
            last_seen_at=last,
            last_report_id=report_id,
        )
        db.add(issue)
    else:
        issue.first_seen_at = min(first, issue.first_seen_at)
        if (last, report_id) > (issue.last_seen_at, issue.last_report_id):
            issue.last_seen_at = last
            issue.last_report_id = report_id
            issue.priority = draft.priority
            issue.title = draft.title
        if issue.status == "CLOSED" and issue.closed_at is not None and last > issue.closed_at:
            issue.status = "PENDING_REVIEW"
            issue.closed_at = None
        if db.is_modified(issue):
            issue.version += 1
    db.flush()
    return MonitoringIssueSnapshot(
        **draft.model_dump(exclude={"firstSeenAt", "lastSeenAt"}),
        firstSeenAt=_aware_utc(first),
        lastSeenAt=_aware_utc(last),
        issueId=issue.id,
    )


def _validate_reference(
    db: Session, model: type, reference_id: int | None, project_id: int
) -> None:
    if (
        reference_id is not None
        and db.scalar(
            select(model.id).where(model.id == reference_id, model.project_id == project_id)
        )
        is None
    ):
        raise AppError("RESOURCE_NOT_FOUND", "Evaluation reference not found in this project", 404)


def _get_report(db: Session, project_id: int, report_id: int) -> MonitoringReport:
    report = db.scalar(
        select(MonitoringReport).where(
            MonitoringReport.id == report_id, MonitoringReport.project_id == project_id
        )
    )
    if report is None:
        raise AppError("RESOURCE_NOT_FOUND", "Monitoring report not found", 404)
    return report


def _get_issue(db: Session, project_id: int, issue_id: int) -> MonitoringIssue:
    issue = db.scalar(
        select(MonitoringIssue).where(
            MonitoringIssue.id == issue_id, MonitoringIssue.project_id == project_id
        )
    )
    if issue is None:
        raise AppError("RESOURCE_NOT_FOUND", "Monitoring issue not found", 404)
    return issue


def _report_response(
    report: MonitoringReport, *, include_snapshot: bool = True
) -> MonitoringReportResponse:
    return MonitoringReportResponse(
        id=report.id,
        projectId=report.project_id,
        startAt=_aware_utc(report.start_at),
        endAt=_aware_utc(report.end_at),
        status=report.status,
        source=report.source,
        ruleVersion=report.rule_version,
        createdAt=_aware_utc(report.created_at),
        updatedAt=_aware_utc(report.updated_at),
        finishedAt=_aware_utc(report.finished_at) if report.finished_at is not None else None,
        errorCode=report.error_code,
        snapshot=(
            MonitoringSnapshot.model_validate_json(report.snapshot_json)
            if include_snapshot and report.snapshot_json is not None
            else None
        ),
    )


def _issue_response(issue: MonitoringIssue) -> MonitoringIssueResponse:
    return MonitoringIssueResponse(
        id=issue.id,
        projectId=issue.project_id,
        engine=issue.engine,
        issueType=issue.issue_type,
        diagnosticType=issue.diagnostic_type,
        title=issue.title,
        priority=issue.priority,
        firstSeenAt=_aware_utc(issue.first_seen_at),
        lastSeenAt=_aware_utc(issue.last_seen_at),
        lastReportId=issue.last_report_id,
        status=issue.status,
        version=issue.version,
        assignee=issue.assignee,
        resolution=issue.resolution,
        acceptanceCriteria=issue.acceptance_criteria,
        evaluationCaseId=issue.evaluation_case_id,
        evaluationRunId=issue.evaluation_run_id,
        closedAt=_aware_utc(issue.closed_at) if issue.closed_at is not None else None,
    )


def _storage_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _aware_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
