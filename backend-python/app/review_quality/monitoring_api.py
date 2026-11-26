from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.review_quality import monitoring
from app.review_quality.monitoring_schemas import (
    CreateMonitoringReport,
    MonitoringIssueResponse,
    MonitoringReportList,
    MonitoringReportResponse,
    MonitoringResponseEnvelope,
    UpdateMonitoringIssue,
)


router = APIRouter(prefix="/api/review-quality/monitoring", tags=["review-quality-monitoring"])


def require_monitoring_project(
    project_id: Annotated[int, Query(alias="projectId", gt=0, le=2**63 - 1)],
    db: Annotated[Session, Depends(get_db)],
) -> int:
    monitoring.require_monitoring_enabled(db)
    return project_id


ProjectScope = Annotated[int, Depends(require_monitoring_project)]
Database = Annotated[Session, Depends(get_db)]
MonitoringId = Annotated[int, Path(gt=0, le=2**63 - 1)]


@router.get("/reports", response_model=MonitoringResponseEnvelope[MonitoringReportList])
def list_reports(
    project_id: ProjectScope,
    db: Database,
    page_no: Annotated[int, Query(alias="pageNo", ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> dict:
    return ok(monitoring.list_monitoring_reports(db, project_id, page_no, page_size))


@router.post("/reports", response_model=MonitoringResponseEnvelope[MonitoringReportResponse])
def create_report(request: CreateMonitoringReport, project_id: ProjectScope, db: Database) -> dict:
    report = monitoring.generate_monitoring_report(
        db,
        project_id=project_id,
        start_at=request.startAt,
        end_at=request.endAt,
        idempotency_key=request.idempotencyKey,
    )
    return ok(report.model_dump(mode="json"))


@router.get(
    "/reports/{report_id}", response_model=MonitoringResponseEnvelope[MonitoringReportResponse]
)
def get_report(report_id: MonitoringId, project_id: ProjectScope, db: Database) -> dict:
    return ok(monitoring.get_monitoring_report(db, project_id, report_id).model_dump(mode="json"))


@router.post(
    "/reports/{report_id}/retry",
    response_model=MonitoringResponseEnvelope[MonitoringReportResponse],
)
def retry_report(report_id: MonitoringId, project_id: ProjectScope, db: Database) -> dict:
    return ok(monitoring.retry_monitoring_report(db, project_id, report_id).model_dump(mode="json"))


@router.get(
    "/issues/{issue_id}", response_model=MonitoringResponseEnvelope[MonitoringIssueResponse]
)
def get_issue(issue_id: MonitoringId, project_id: ProjectScope, db: Database) -> dict:
    return ok(monitoring.get_monitoring_issue(db, project_id, issue_id).model_dump(mode="json"))


@router.patch(
    "/issues/{issue_id}", response_model=MonitoringResponseEnvelope[MonitoringIssueResponse]
)
def update_issue(
    issue_id: MonitoringId, request: UpdateMonitoringIssue, project_id: ProjectScope, db: Database
) -> dict:
    return ok(
        monitoring.update_monitoring_issue(db, project_id, issue_id, request).model_dump(
            mode="json"
        )
    )
