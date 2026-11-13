"""Whitelist-only summaries; never expose Agent input, source body, or lookup query."""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewRun
from app.core.errors import AppError
from app.project_integration.models import Project
from app.review_memory.schemas import MemoryRunSummary, MemorySnapshot
from app.review_record.models import ReviewTask


def snapshot_from_input(input_json: str | None) -> MemorySnapshot | None:
    payload = json.loads(input_json or "{}")
    snapshot = payload.get("memorySnapshot") if isinstance(payload, dict) else None
    if snapshot is None:
        return None
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > 32768:
        raise ValueError("memory snapshot too large")
    return MemorySnapshot.model_validate(snapshot)


def retain_memory_summary(input_json: str | None) -> str | None:
    """Replace cleared source input with validated metadata only, preserving old cleanup semantics."""
    try:
        snapshot = snapshot_from_input(input_json)
    except (ValueError, TypeError, ValidationError):
        return None
    if snapshot is None:
        return None
    return json.dumps(
        {"memorySnapshot": snapshot.model_dump(mode="json", by_alias=True)}, ensure_ascii=False
    )


def get_run_memory_summary(db: Session, run_id: int, project_id: int) -> MemoryRunSummary:
    run = db.get(AgentReviewRun, run_id)
    task = db.get(ReviewTask, run.task_id) if run else None
    if task is None or task.project_id != project_id or db.get(Project, project_id) is None:
        raise AppError("RESOURCE_NOT_FOUND", "Agent run not found in project", 404)
    try:
        snapshot = snapshot_from_input(run.input_json)
        if snapshot is not None and snapshot.project_id != project_id:
            raise ValueError("memory project mismatch")
    except (ValueError, TypeError, ValidationError):
        raise AppError("MEMORY_SNAPSHOT_INVALID", "Stored memory summary is invalid", 500) from None
    adoption = (
        "HISTORICAL"
        if snapshot is None
        else "STANDARD_FALLBACK"
        if run.effective_engine == "STANDARD_FALLBACK"
        else "NOT_LOADED"
        if not snapshot.selected
        else "PENDING"
        if run.status in {"PENDING", "RUNNING"}
        else "AGENT"
        if run.status == "SUCCEEDED" and run.effective_engine == "AGENT"
        else "UNAVAILABLE"
    )
    return MemoryRunSummary(
        run_id=run.id,
        project_id=project_id,
        recorded=snapshot is not None,
        snapshot=snapshot,
        effective_engine=run.effective_engine,
        adoption=adoption,
    )
