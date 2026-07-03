from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.evaluation import service


router = APIRouter(prefix="/api/evaluation-cases", tags=["evaluation-cases"])
run_router = APIRouter(prefix="/api/evaluation-runs", tags=["evaluation-runs"])


@router.post("")
async def create_evaluation_case(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.create_evaluation_case_response(db, request))


@router.get("")
async def list_evaluation_cases(
    project_id: int | None = Query(default=None, alias="projectId"),
    provider: str | None = None,
    profile: str | None = None,
    risk_type: str | None = Query(default=None, alias="riskType"),
    verdict: str | None = None,
    page_no: int = Query(default=1, alias="pageNo", ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        service.list_evaluation_case_response(
            db,
            project_id=project_id,
            provider=provider,
            profile=profile,
            risk_type=risk_type,
            verdict=verdict,
            page_no=page_no,
            page_size=page_size,
        )
    )


@router.get("/{case_id}")
async def get_evaluation_case(case_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.get_evaluation_case_response(db, case_id))


@router.put("/{case_id}")
async def update_evaluation_case(case_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_evaluation_case_response(db, case_id, request))


@router.get("/{case_id}/rule-gap-attribution")
async def get_rule_gap_attribution(case_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.get_rule_gap_attribution_response(db, case_id))


@router.put("/{case_id}/rule-gap-attribution")
async def update_rule_gap_attribution(case_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_rule_gap_attribution_response(db, case_id, request))


@run_router.post("")
async def create_evaluation_run(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.create_evaluation_run_response(db, request))


@run_router.get("")
async def list_evaluation_runs(
    project_id: int | None = Query(default=None, alias="projectId"),
    provider: str | None = None,
    profile: str | None = None,
    run_type: str | None = Query(default=None, alias="runType"),
    status: str | None = None,
    page_no: int = Query(default=1, alias="pageNo", ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        service.list_evaluation_run_response(
            db,
            project_id=project_id,
            provider=provider,
            profile=profile,
            run_type=run_type,
            status=status,
            page_no=page_no,
            page_size=page_size,
        )
    )


@run_router.get("/{run_id}")
async def get_evaluation_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(service.get_evaluation_run_response(db, run_id))


@run_router.put("/{run_id}/items/{item_id}")
async def update_evaluation_run_item(run_id: int, item_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(service.update_evaluation_run_item_response(db, run_id, item_id, request))
