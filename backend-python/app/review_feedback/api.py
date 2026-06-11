from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.project_review_policy.service import convert_feedback_to_policy_response
from app.review_feedback.service import (
    create_or_update_feedback,
    get_task_feedback_response,
    list_feedback_pool_response,
    update_feedback_status_response,
)


task_feedback_router = APIRouter(prefix="/api/review-tasks", tags=["review-feedback"])
feedback_pool_router = APIRouter(prefix="/api/risk-feedback", tags=["risk-feedback"])


@task_feedback_router.post("/{task_id}/feedback")
async def submit_task_feedback(task_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(create_or_update_feedback(db, task_id, request))


@task_feedback_router.get("/{task_id}/feedback")
async def list_task_feedback(task_id: int, db: Session = Depends(get_db)) -> dict:
    return ok(get_task_feedback_response(db, task_id))


@feedback_pool_router.get("")
async def list_feedback_pool(
    project_id: int | None = Query(default=None, alias="projectId"),
    source_type: str | None = Query(default=None, alias="sourceType"),
    risk_type: str | None = Query(default=None, alias="riskType"),
    feedback_type: str | None = Query(default=None, alias="feedbackType"),
    reason_type: str | None = Query(default=None, alias="reasonType"),
    missing_context_type: str | None = Query(default=None, alias="missingContextType"),
    policy_candidate: bool = Query(default=False, alias="policyCandidate"),
    status: str | None = None,
    keyword: str | None = None,
    page_no: int = Query(default=1, alias="pageNo"),
    page_size: int = Query(default=20, alias="pageSize"),
    db: Session = Depends(get_db),
) -> dict:
    return ok(
        list_feedback_pool_response(
            db,
            project_id=project_id,
            source_type=source_type,
            risk_type=risk_type,
            feedback_type=feedback_type,
            reason_type=reason_type,
            missing_context_type=missing_context_type,
            policy_candidate=policy_candidate,
            status=status,
            keyword=keyword,
            page_no=page_no,
            page_size=page_size,
        )
    )


@feedback_pool_router.put("/{feedback_id}/status")
async def update_feedback_status(feedback_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(update_feedback_status_response(db, feedback_id, request))


@feedback_pool_router.post("/{feedback_id}/convert-to-policy")
async def convert_feedback_to_policy(feedback_id: int, request: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    return ok(convert_feedback_to_policy_response(db, feedback_id, request))
