from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.code_quality.service import (
    generate_fix_preview_response,
    get_progress_response,
    get_push_gate_response,
    get_result_response,
    list_fix_previews_response,
    list_results_response,
)
from app.core.database import get_db
from app.core.response import ok
from app.review_record.repository import (
    get_review_task_detail,
    get_review_task_result,
    list_notifications,
    list_review_tasks,
)
from app.review_record.service import create_manual_review, rerun_review_task, rerun_review_task_in_place


router = APIRouter(prefix="/api/review-tasks", tags=["review-tasks"])


@router.post("/manual")
async def manual_review(request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(create_manual_review(db, request))


@router.post("/{task_id}/rerun")
async def rerun(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(rerun_review_task(db, task_id))


@router.post("/{task_id}/rerun-in-place")
async def rerun_in_place(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(rerun_review_task_in_place(db, task_id))


@router.get("")
async def find_review_tasks(
    project_id: int | None = Query(default=None, alias="projectId"),
    group_id: int | None = Query(default=None, alias="groupId"),
    target_type: str | None = Query(default=None, alias="targetType"),
    trigger_type: str | None = Query(default=None, alias="triggerType"),
    status: str | None = None,
    risk_level: str | None = Query(default=None, alias="riskLevel"),
    keyword: str | None = None,
    page_no: int = Query(default=1, alias="pageNo"),
    page_size: int = Query(default=20, alias="pageSize"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(list_review_tasks(db, project_id, status, risk_level, keyword, group_id, target_type, trigger_type, page_no, page_size))


@router.get("/{task_id}/result")
async def get_result(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(get_review_task_result(db, task_id))


@router.get("/{task_id}/notifications")
async def get_notifications(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(list_notifications(db, task_id))


@router.get("/{task_id}/code-quality-result")
async def get_code_quality_result(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(get_result_response(db, task_id))


@router.get("/{task_id}/code-quality-results")
async def list_code_quality_results(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(list_results_response(db, task_id))


@router.get("/{task_id}/code-quality-progress")
async def get_code_quality_progress(
    task_id: int,
    review_key: str | None = Query(default=None, alias="reviewKey"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(get_progress_response(db, task_id, review_key))


@router.get("/{task_id}/code-quality-gate")
async def get_code_quality_gate(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(get_push_gate_response(db, task_id))


@router.post("/{task_id}/code-quality-fix-preview")
async def generate_code_quality_fix_preview(task_id: int, request: dict, db: Session = Depends(get_db)) -> dict:
    return ok(generate_fix_preview_response(db, task_id, request))


@router.get("/{task_id}/code-quality-fix-previews")
async def list_code_quality_fix_previews(
    task_id: int,
    review_key: str | None = Query(default=None, alias="reviewKey"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(list_fix_previews_response(db, task_id, review_key))


@router.get("/{task_id}")
async def get_detail(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(get_review_task_detail(db, task_id))
