from typing import Annotated

from fastapi import APIRouter, Query

from app.core.response import ok
from app.review_quality import governance_service as governance
from app.review_quality.governance_schemas import (
    CreateGovernanceRun, GovernanceIntervention, GovernanceOverview, GovernanceRunDetail, GovernanceRunView,
)
from app.review_quality.monitoring_api import Database, MonitoringId, ProjectScope
from app.review_quality.monitoring_schemas import MonitoringResponseEnvelope


router = APIRouter(prefix="/api/review-quality/monitoring/governance", tags=["review-quality-governance"])


@router.get("", response_model=MonitoringResponseEnvelope[GovernanceOverview])
def overview(project_id: ProjectScope, db: Database,
             page_no: Annotated[int, Query(alias="pageNo", ge=1, le=10000)] = 1) -> dict:
    return ok(governance.overview(db, project_id, page_no).model_dump(mode="json"))


@router.post("/runs", response_model=MonitoringResponseEnvelope[list[GovernanceRunView]])
def create_runs(request: CreateGovernanceRun, project_id: ProjectScope, db: Database) -> dict:
    return ok([run.model_dump(mode="json") for run in governance.enqueue_report(
        db, project_id, request.reportId, request.issueId,
    )])


@router.get("/runs/{run_id}", response_model=MonitoringResponseEnvelope[GovernanceRunDetail])
def get_run(run_id: MonitoringId, project_id: ProjectScope, db: Database) -> dict:
    return ok(governance.run_detail(db, project_id, run_id).model_dump(mode="json"))


@router.patch("/issues/{issue_id}", response_model=MonitoringResponseEnvelope[dict[str, int]])
def intervene(issue_id: MonitoringId, request: GovernanceIntervention, project_id: ProjectScope, db: Database) -> dict:
    return ok({"revision": governance.intervene(db, project_id, issue_id, request)})
