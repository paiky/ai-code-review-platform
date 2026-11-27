from datetime import UTC, datetime
from hashlib import sha256
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import AppError
from app.core.json_utils import utc_now
from app.review_quality.governance_materials import approved_samples
from app.review_quality.governance_models import GovernanceControl, GovernanceEvent, GovernanceRun
from app.review_quality.governance_queue import (
    ACTIVE, add_event, configured_provider_code, governance_enabled, transition,
)
from app.review_quality.governance_schemas import (
    GovernanceIntervention, GovernanceIssueView, GovernanceOverview, GovernanceRunDetail, GovernanceRunView,
)
from app.review_quality.monitoring import get_monitoring_report, require_monitoring_enabled
from app.review_quality.monitoring_models import MonitoringIssue, MonitoringReport
from app.review_quality.monitoring_schemas import MonitoringIssueSnapshot, MonitoringReportResponse


BATCH_SIZE = 10
PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def require_governance(db: Session) -> None:
    require_monitoring_enabled(db)
    if not governance_enabled():
        raise AppError("RESOURCE_NOT_FOUND", "Review quality governance is disabled", 404)


def lock_issue(db: Session, project_id: int, issue_id: int) -> MonitoringIssue:
    issue = db.scalar(select(MonitoringIssue).where(
        MonitoringIssue.id == issue_id, MonitoringIssue.project_id == project_id,
    ).with_for_update())
    if issue is None:
        raise AppError("RESOURCE_NOT_FOUND", "Governance issue not found", 404)
    return issue


def _input(report: MonitoringReportResponse, draft: MonitoringIssueSnapshot, provider_code: str) -> dict:
    metrics = [item.model_dump(mode="json") for item in report.snapshot.metrics
               if item.engine == draft.engine]
    return {
        "projectId": report.projectId,
        "reportId": report.id,
        "truncated": report.snapshot.truncated,
        "providerCode": provider_code,
        "issue": draft.model_dump(mode="json", exclude={"title", "firstSeenAt"}),
        "metrics": metrics,
        "actions": ["REPLAY", "OBSERVE", "NEEDS_INPUT"],
        "maxReplays": 1,
    }


def enqueue_report(
    db: Session, project_id: int, report_id: int, issue_id: int | None = None, *, scheduled: bool = False,
) -> list[GovernanceRunView]:
    require_governance(db)
    report = get_monitoring_report(db, project_id, report_id)
    if report.status != "SUCCEEDED" or report.snapshot is None:
        raise AppError("GOVERNANCE_REPORT_NOT_READY", "Governance requires a successful report", 409)
    if issue_id is not None and all(item.issueId != issue_id for item in report.snapshot.issues):
        raise AppError("RESOURCE_NOT_FOUND", "Issue is not present in this report", 404)

    drafts = sorted(
        (item for item in report.snapshot.issues if issue_id is None or item.issueId == issue_id),
        key=lambda item: (PRIORITY_ORDER[item.priority], -item.affectedTaskCount, item.issueId),
    )
    provider_code = configured_provider_code()
    # Start the MySQL snapshot only after taking the report or issue lock below.
    db.rollback()
    if not drafts:
        # A successful report without issues is observable as a completed governance pass.
        db.scalar(select(MonitoringReport.id).where(MonitoringReport.id == report_id).with_for_update())
        key = sha256(f"empty:{report_id}".encode()).hexdigest()
        run = db.scalar(select(GovernanceRun).where(
            GovernanceRun.project_id == project_id, GovernanceRun.evidence_key == key,
        ))
        if run is None:
            now = utc_now()
            run = GovernanceRun(
                project_id=project_id, report_id=report_id, evidence_key=key,
                source="SCHEDULED" if scheduled else "MANUAL", status="SUCCEEDED",
                input_json={"issue": None, "metrics": [], "truncated": report.snapshot.truncated},
                result_json={}, available_at=now, created_at=now, updated_at=now, finished_at=now,
            )
            db.add(run)
            db.flush()
            add_event(db, run, "NO_ISSUES")
        views = [run_view(run)]
        db.commit()
        return views
    runs = []
    for draft in drafts:
        if len(runs) >= BATCH_SIZE:
            break
        if scheduled:
            db.scalar(select(MonitoringReport.id).where(MonitoringReport.id == report_id).with_for_update())
        issue = lock_issue(db, project_id, draft.issueId)
        if scheduled:
            queued = list(db.scalars(select(GovernanceRun.id).where(
                GovernanceRun.project_id == project_id, GovernanceRun.report_id == report_id,
                GovernanceRun.source == "SCHEDULED",
            )))
            if len(queued) >= BATCH_SIZE:
                db.rollback()
                break
        control = db.get(GovernanceControl, issue.id, with_for_update=True)
        if issue.status in {"CLOSED", "DISMISSED"} or (scheduled and control and control.paused):
            db.rollback()
            continue
        latest = db.scalar(select(GovernanceRun).where(
            GovernanceRun.project_id == project_id, GovernanceRun.issue_id == issue.id,
        ).order_by(GovernanceRun.id.desc()).limit(1))
        if scheduled and latest and latest.report_id != report_id:
            previous = latest.input_json["issue"]
            prior_occurrence = datetime.fromisoformat(previous["lastSeenAt"])
            if draft.lastSeenAt < prior_occurrence or (
                draft.lastSeenAt == prior_occurrence and draft.affectedTaskCount <= previous["affectedTaskCount"]
            ):
                db.rollback()
                continue
        run_input = _input(report, draft, provider_code)
        frozen_issue = run_input["issue"]
        frozen_issue["samples"].sort(key=lambda row: (row["taskId"], row["runId"] or 0, row["eventId"] or 0))
        run_input["approvedSamples"] = approved_samples(project_id, frozen_issue)
        key_source = [issue.id, frozen_issue["lastSeenAt"], frozen_issue["affectedTaskCount"],
                      frozen_issue["samples"], run_input["approvedSamples"], provider_code]
        key = sha256(json.dumps(key_source, sort_keys=True).encode()).hexdigest()
        run = db.scalar(select(GovernanceRun).where(
            GovernanceRun.project_id == project_id, GovernanceRun.evidence_key == key,
        ))
        if run is None:
            now = utc_now()
            run = GovernanceRun(
                project_id=project_id, report_id=report_id, issue_id=issue.id, evidence_key=key,
                source="SCHEDULED" if scheduled else "MANUAL", status="PAUSED" if control and control.paused else "QUEUED",
                input_json=run_input, result_json={}, available_at=now, created_at=now, updated_at=now,
            )
            db.add(run)
            db.flush()
            add_event(db, run, "ENQUEUED")
        runs.append(run_view(run))
        db.commit()
    return runs


def run_view(run: GovernanceRun) -> GovernanceRunView:
    return GovernanceRunView(
        id=run.id, reportId=run.report_id, issueId=run.issue_id, source=run.source, status=run.status,
        createdAt=run.created_at.replace(tzinfo=UTC), updatedAt=run.updated_at.replace(tzinfo=UTC),
        errorCode=run.error_code, decision=run.result_json.get("decision"),
        assessment=run.result_json.get("assessment"), replay=run.result_json.get("replay"),
    )


def run_detail(db: Session, project_id: int, run_id: int) -> GovernanceRunDetail:
    require_governance(db)
    run = db.scalar(select(GovernanceRun).where(GovernanceRun.id == run_id, GovernanceRun.project_id == project_id))
    if run is None:
        raise AppError("RESOURCE_NOT_FOUND", "Governance run not found", 404)
    control = db.get(GovernanceControl, run.issue_id) if run.issue_id else None
    events = db.scalars(select(GovernanceEvent).where(GovernanceEvent.run_id == run_id).order_by(GovernanceEvent.id))
    return GovernanceRunDetail(
        **run_view(run).model_dump(),
        evidence={key: run.input_json[key] for key in ("issue", "metrics", "truncated")},
        events=[{"kind": event.kind, "details": event.details, "createdAt": event.created_at.replace(tzinfo=UTC)}
                for event in events],
        controlRevision=control.revision if control else 0,
        paused=bool(control and control.paused),
        priority=(control.priority if control else None) or run.result_json.get("decision", {}).get("priority") or (
            run.input_json["issue"]["priority"] if run.issue_id else None
        ),
        override=control.conclusion if control else None,
    )


def overview(db: Session, project_id: int, page_no: int) -> GovernanceOverview:
    if not governance_enabled():
        return GovernanceOverview(enabled=False)
    latest = db.scalar(select(GovernanceRun).where(GovernanceRun.project_id == project_id)
                       .order_by(GovernanceRun.id.desc()).limit(1))
    latest_ids = (select(func.max(GovernanceRun.id).label("run_id"))
                  .where(GovernanceRun.project_id == project_id, GovernanceRun.issue_id.is_not(None))
                  .group_by(GovernanceRun.issue_id).subquery())
    effective_ids = (select(GovernanceRun.issue_id, func.max(GovernanceRun.id).label("run_id"))
                     .where(GovernanceRun.project_id == project_id, GovernanceRun.status == "SUCCEEDED",
                            GovernanceRun.issue_id.is_not(None))
                     .group_by(GovernanceRun.issue_id).subquery())
    effective_run = aliased(GovernanceRun)
    rows = db.execute(
        select(GovernanceRun, MonitoringIssue, GovernanceControl, effective_run)
        .join(latest_ids, latest_ids.c.run_id == GovernanceRun.id)
        .join(MonitoringIssue, MonitoringIssue.id == GovernanceRun.issue_id)
        .outerjoin(GovernanceControl, GovernanceControl.issue_id == MonitoringIssue.id)
        .outerjoin(effective_ids, effective_ids.c.issue_id == MonitoringIssue.id)
        .outerjoin(effective_run, effective_ids.c.run_id == effective_run.id)
    )
    issues = []
    for run, issue, control, previous in rows:
        current = run_view(run)
        effective = run_view(previous) if previous and previous.id != run.id else current
        action = effective.assessment or effective.decision
        if issue.status in {"CLOSED", "DISMISSED"}:
            status = "VERIFIED" if issue.status == "CLOSED" else "DISMISSED"
        elif control and control.conclusion:
            status = "OVERRIDDEN"
        elif run.status != "SUCCEEDED":
            status = run.status
        else:
            status = action.action if action else "OBSERVE"
        issues.append(GovernanceIssueView(
            id=issue.id, revision=control.revision if control else 0, paused=bool(control and control.paused),
            title=issue.title, priority=(control.priority if control else None) or (
                effective.decision.priority if effective.decision else issue.priority
            ), status=status, override=control.conclusion if control else None,
            affectedTaskCount=run.input_json["issue"]["affectedTaskCount"], run=current,
            effectiveRun=effective if effective.id != current.id else None,
        ))
    issues.sort(key=lambda item: (item.status != "NEEDS_INPUT", PRIORITY_ORDER[item.priority], -item.run.id))
    start = (page_no - 1) * 20
    return GovernanceOverview(enabled=True, latestRun=run_view(latest) if latest else None,
                              issues=issues[start:start + 20], pageNo=page_no, hasMore=len(issues) > start + 20)


def intervene(db: Session, project_id: int, issue_id: int, change: GovernanceIntervention) -> int:
    require_governance(db)
    lock_issue(db, project_id, issue_id)
    control = db.get(GovernanceControl, issue_id, with_for_update=True)
    if change.revision != (control.revision if control else 0):
        raise AppError("GOVERNANCE_CONTROL_CONFLICT", "Governance issue control was updated", 409)
    if control is None:
        control = GovernanceControl(issue_id=issue_id, revision=0, paused=False)
        db.add(control)
    runs = list(db.scalars(select(GovernanceRun).where(
        GovernanceRun.project_id == project_id, GovernanceRun.issue_id == issue_id,
        GovernanceRun.status.in_(ACTIVE),
    ).order_by(GovernanceRun.id.desc()).with_for_update()))
    latest = runs[0] if runs else db.scalar(select(GovernanceRun).where(
        GovernanceRun.project_id == project_id, GovernanceRun.issue_id == issue_id,
    ).order_by(GovernanceRun.id.desc()).limit(1))
    if latest is None:
        raise AppError("RESOURCE_NOT_FOUND", "Governance issue has no runs", 404)
    now = utc_now()
    action = change.action
    if action == "PRIORITIZE":
        control.priority = change.priority
    if action == "OVERRIDE":
        control.conclusion = change.conclusion
    if action in {"PAUSE", "RESUME"}:
        control.paused = action == "PAUSE"
    for run in runs:
        if action == "PAUSE" and run.status in {"RUNNING", "QUEUED"}:
            transition(run, "PAUSED", now)
        if action == "RESUME" and run.status == "PAUSED":
            transition(run, "QUEUED", now)
            run.available_at = now
        if action in {"CANCEL", "OVERRIDE"}:
            transition(run, "CANCELLED", now)
        add_event(db, run, action, change.model_dump(exclude_none=True))
    if not runs:
        add_event(db, latest, action, change.model_dump(exclude_none=True))
    control.revision += 1
    revision = control.revision
    db.commit()
    return revision
