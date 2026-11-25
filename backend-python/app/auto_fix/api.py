import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auto_fix import config, service
from app.auto_fix.gitlab import full_sha
from app.auto_fix.models import AutoFixSettings, FixRound, FixRun
from app.code_quality.models import CodeQualityReviewResult
from app.code_quality.repository import get_settings_record
from app.core.database import get_db
from app.core.errors import AppError
from app.core.response import ok
from app.project_integration.models import Project
from app.project_integration.repository import project_auto_fix_enabled
from app.review_record.models import ReviewTask


LOG = logging.getLogger(__name__)


def _prevent_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(tags=["review-auto-fix"], dependencies=[Depends(_prevent_caching)])
_TASK_FIX_PATH = "/api/review-tasks/{task_id}/auto-fix"
_FINDING_REASONS = {
    "EVIDENCE_AND_LOCATION_MATCH": "文件位置和问题证据相符",
    "REVIEW_INCOMPLETE": "本轮缺少完整复审",
    "AMBIGUOUS_MATCH": "存在多个或证据不足的匹配候选",
    "INSUFFICIENT_FILE_EVIDENCE": "该文件缺少有效的对照证据",
    "OLD_RANGE_REMOVED": "原代码范围已删除，本轮未再发现对应问题",
    "NO_REVIEW_MATCH": "本轮复审没有发现对应问题",
    "NO_PREVIOUS_MATCH": "上一份正式复审结果没有对应问题",
}


class AutoFixSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


def _require_schema(db: Session) -> None:
    if not service.schema_ready(db):
        raise AppError("RESOURCE_NOT_FOUND", "自动修复功能不可用", 404)


def settings_fields(db: Session) -> dict[str, bool]:
    settings = db.get(AutoFixSettings, 1) if service.schema_ready(db) else None
    enabled = bool(settings and settings.enabled)
    return {"autoFixAvailable": settings is not None and (enabled or config.configured()), "autoFixEnabled": enabled}


@router.put("/api/code-quality-reviews/auto-fix-settings")
def update_auto_fix_settings(
    payload: AutoFixSettingsRequest,
    db: Session = Depends(get_db),
) -> dict:
    _require_schema(db)
    if payload.enabled and not (config.configured() and get_settings_record(db).review_enabled):
        raise AppError("AUTO_FIX_UNAVAILABLE", "自动修复配置未完成或全局 AI Review 已关闭", 409)
    record = db.get(AutoFixSettings, 1, with_for_update=True)
    if record is None:
        raise AppError("AUTO_FIX_UNAVAILABLE", "自动修复设置尚未初始化", 409)
    if record.enabled != payload.enabled:
        now = datetime.now()
        record.enabled = payload.enabled
        record.enabled_at = now if payload.enabled else None
        record.updated_at = now
        record.updated_by = "platform-settings"
        db.commit()
        LOG.info("Auto-fix global switch changed: enabled=%s", payload.enabled)
    return ok({"autoFixEnabled": bool(record.enabled)})


def _source_task(db: Session, task_id: int) -> tuple[ReviewTask, Project]:
    task = db.get(ReviewTask, task_id)
    project = db.get(Project, task.project_id) if task else None
    if task is None or project is None:
        raise AppError("RESOURCE_NOT_FOUND", "未找到可查看的自动修复任务", 404)
    return task, project


def _source_run(db: Session, task: ReviewTask, run_id: int, *, lock: bool = False) -> FixRun:
    query = select(FixRun).where(
        FixRun.id == run_id,
        FixRun.source_task_id == task.id,
        FixRun.project_id == task.project_id,
    )
    if lock:
        query = query.with_for_update()
    run = db.scalar(query)
    if run is None:
        raise AppError("RESOURCE_NOT_FOUND", "未找到可查看的自动修复任务", 404)
    return run


def _compare_url(run: FixRun, base: str, head: str | None) -> str | None:
    if not run.project_url or not full_sha(base) or not full_sha(head):
        return None
    return f"{run.project_url.rstrip('/')}/-/compare/{base}...{head}"


def _serialize_run(db: Session, run: FixRun) -> dict:
    rounds = service.rounds_for(db, run)
    latest = rounds[-1] if rounds else None
    last_pushed = next((item for item in reversed(rounds) if item.pushed), None)
    last_verified = next((item for item in reversed(rounds) if item.critical_count is not None), None)
    findings = json.loads(run.inputs_json).get("findings") or []
    original_count = len(service.critical_findings(findings))
    remaining_count = last_verified.critical_count if last_verified else None
    return {
        "runId": run.id,
        "status": run.status,
        "step": run.step,
        "reasonCode": run.reason_code,
        "reason": run.reason,
        "baseSha": run.base_sha,
        "developerSha": run.developer_sha,
        "developerBranch": run.developer_branch,
        "fixBranch": service.branch_name(run),
        "currentSha": last_pushed.commit_sha if last_pushed else None,
        "currentRound": latest.number if latest else None,
        "maxRounds": service.MAX_ROUNDS,
        "originalCriticalCount": original_count,
        "remainingCriticalCount": remaining_count,
        "criticalCount": original_count if remaining_count is None else remaining_count,
        "canCancel": run.status in service.WORK_STATUSES and run.cancel_requested_at is None,
        "cancelRequestedAt": run.cancel_requested_at,
        "cumulativeDiffUrl": _compare_url(run, run.developer_sha, last_pushed.commit_sha) if last_pushed else None,
        "sourceMergeRequest": (
            {"iid": run.source_mr_iid,
             "webUrl": f"{run.project_url.rstrip('/')}/-/merge_requests/{run.source_mr_iid}"}
            if run.project_url else None
        ),
        "mergeRequest": {"iid": run.mr_iid, "webUrl": run.mr_url} if run.mr_iid else None,
        "mergeCommitSha": run.merge_sha,
        "mergedAt": run.merged_at,
        "notificationStatus": json.loads(run.notification_json) if run.notification_json else None,
        "rounds": [{
            "number": item.number,
            "inputSha": item.input_sha,
            "commitSha": item.commit_sha,
            "reviewTaskId": item.review_task_id,
            "reviewKey": item.review_key,
            "criticalCount": item.critical_count,
            "step": run.step if item is latest else None,
            "diffUrl": _compare_url(run, item.input_sha, item.commit_sha) if item.pushed else None,
        } for item in rounds],
    }


def _not_triggered(db: Session, task: ReviewTask, project: Project, review_key: str | None) -> dict:
    result = {"status": "NOT_TRIGGERED", "runId": None, "canCancel": False}
    if task.trigger_type != "GITLAB_MR_WEBHOOK" or not review_key:
        return result
    settings = db.get(AutoFixSettings, 1)
    if not settings or not settings.enabled:
        return result
    review = db.scalar(select(CodeQualityReviewResult).where(
        CodeQualityReviewResult.task_id == task.id, CodeQualityReviewResult.review_key == review_key,
        CodeQualityReviewResult.status == "SUCCESS",
    ))
    if review is None or not service.critical_findings(json.loads(review.findings_json or "[]")):
        return result
    snapshot = json.loads(review.review_snapshot_json or "{}")
    if not project_auto_fix_enabled(db, project.id):
        reason = "项目自动修复开关已关闭"
    elif not config.configured() or not get_settings_record(db).review_enabled:
        reason = "自动修复配置未完成或全局 AI Review 已关闭"
    elif snapshot.get("isPrimary") is not True:
        reason = "仅使用已验证的主 Review 结果触发自动修复"
    elif snapshot.get("trustedIngress") is not True:
        reason = "本次 Review 未从已验证的 GitLab Webhook 触发"
    elif snapshot.get("complete") is not True or not snapshot.get("executionId"):
        reason = "本次 Review 缺少完整、可验证的提交快照"
    else:
        reason = "本次 Review 未产生可用的自动修复任务"
    return {**result, "reason": reason}


@router.get(_TASK_FIX_PATH)
def get_auto_fix_summary(
    task_id: int,
    review_key: str | None = Query(default=None, alias="reviewKey", min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> dict:
    _require_schema(db)
    task, project = _source_task(db, task_id)
    query = select(FixRun).where(FixRun.source_task_id == task.id, FixRun.project_id == project.id)
    if review_key is not None:
        query = query.where(FixRun.source_review_key == review_key)
    run = db.scalar(query.order_by(FixRun.id.desc()).limit(1))
    return ok(_serialize_run(db, run) if run else _not_triggered(db, task, project, review_key))


@router.get(f"{_TASK_FIX_PATH}/{{run_id}}")
def get_auto_fix_run(
    task_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> dict:
    _require_schema(db)
    task, _ = _source_task(db, task_id)
    return ok(_serialize_run(db, _source_run(db, task, run_id)))


@router.post(f"{_TASK_FIX_PATH}/{{run_id}}/cancel")
def cancel_auto_fix_run(
    task_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> dict:
    _require_schema(db)
    task, _ = _source_task(db, task_id)
    run = _source_run(db, task, run_id, lock=True)
    if run.status in service.WORK_STATUSES and run.cancel_requested_at is None:
        now = datetime.now()
        run.cancel_requested_at = now
        run.next_at = now
        run.updated_at = now
        db.commit()
        LOG.info("Auto-fix cancel requested: run_id=%s", run.id)
    return ok(_serialize_run(db, run))


def _finding_at(findings: list, index: int | None) -> dict | None:
    if type(index) is not int or not 0 <= index < len(findings) or not isinstance(findings[index], dict):
        return None
    return {**service._compact_finding(findings[index]), "index": index}


def _round_result(db: Session, round_: FixRound, base_sha: str) -> list | None:
    if not round_.review_task_id or not round_.review_key or not round_.review_version:
        return None
    result = service._result(db, round_)
    if result is None or result.status != "SUCCESS":
        return None
    snapshot = json.loads(result.review_snapshot_json or "{}")
    if (
        snapshot.get("executionId") != round_.review_version
        or snapshot.get("baseSha") != base_sha
        or snapshot.get("headSha") != round_.commit_sha
    ):
        return None
    return json.loads(result.findings_json or "[]")


@router.get(f"{_TASK_FIX_PATH}/{{run_id}}/rounds/{{round_number}}/findings")
def get_auto_fix_round_findings(
    task_id: int,
    run_id: int,
    round_number: int = Path(ge=1, le=service.MAX_ROUNDS),
    db: Session = Depends(get_db),
) -> dict:
    _require_schema(db)
    task, _ = _source_task(db, task_id)
    run = _source_run(db, task, run_id)
    round_ = db.get(FixRound, (run.id, round_number))
    if round_ is None:
        raise AppError("RESOURCE_NOT_FOUND", "未找到本轮风险处理详情", 404)
    common = {
        "inputSha": round_.input_sha,
        "commitSha": round_.commit_sha,
        "diffUrl": _compare_url(run, round_.input_sha, round_.commit_sha) if round_.pushed else None,
    }
    if round_.findings_json is None:
        status = "PENDING" if run.status in service.WORK_STATUSES else "UNAVAILABLE"
        return ok({**common, "status": status, "reason": run.reason, "items": []})
    previous_round = db.get(FixRound, (run.id, round_.number - 1)) if round_.number > 1 else None
    if previous_round:
        previous = _round_result(db, previous_round, run.base_sha)
    elif round_.number == 1:
        previous = json.loads(run.inputs_json).get("findings", [])
    else:
        previous = None
    current = _round_result(db, round_, run.base_sha)
    if previous is None or current is None:
        return ok({**common, "status": "UNAVAILABLE", "reason": "无法核对对应版本的正式复审结果", "items": []})
    items = []
    before_version = previous_round.review_version if previous_round else run.source_review_version
    for raw in json.loads(round_.findings_json):
        status = "UNCERTAIN" if raw["status"] == "NEEDS_VERIFICATION" else raw["status"]
        items.append({
            "status": status,
            "before": _finding_at(previous, raw.get("previousIndex")),
            "after": _finding_at(current, raw.get("currentIndex")),
            "beforeReviewVersion": before_version,
            "afterReviewVersion": round_.review_version,
            "reasonCode": raw.get("reasonCode"),
            "reason": _FINDING_REASONS.get(raw.get("reasonCode")),
            "beforeCandidates": [
                finding for index in raw.get("candidatePreviousIndexes", ())
                if (finding := _finding_at(previous, index)) is not None
            ],
            "afterCandidates": [
                finding for index in raw.get("candidateCurrentIndexes", ())
                if (finding := _finding_at(current, index)) is not None
            ],
        })
    return ok({**common, "status": "COMPLETE", "items": items})
