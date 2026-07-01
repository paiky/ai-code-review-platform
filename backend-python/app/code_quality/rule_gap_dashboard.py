from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewProgressEvent
from app.code_quality.repository import ensure_progress_schema, scrub_sensitive
from app.core.json_utils import format_datetime
from app.project_integration.models import Project
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import ensure_feedback_schema
from app.review_record.models import ReviewTask


_LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[^\s,;'\"}]+"),
    re.compile(r"/[^\s,;'\"}]+(?:/\.local|/review-workspaces|/worktrees|/mirrors|/tmp)[^\s,;'\"}]*"),
]
_RECOMMENDATION_VERSION = "rule-gap-recommendation-v1"
_RECOMMENDATION_STATUS_ORDER = {"RECOMMENDED": 3, "WATCH": 2, "NOT_NOW": 1}
_RECOMMENDED_SCORE_THRESHOLD = 65
_WATCH_SCORE_THRESHOLD = 35
_GAP_TYPE_SCORE = {
    "UNSUPPORTED_PLANNER_SIGNAL": 22,
    "UNAVAILABLE_REQUESTED_CONTEXT": 18,
    "BUDGET_CUT": 20,
    "RETRIEVAL_FAILED": 16,
}
_SIGNAL_RISK_SCORE = {
    "DB_SQL_MAPPER_CHANGED": 24,
    "CACHE_WRITE_DELETE_CHANGED": 19,
    "MQ_CONFIG_CHANGED": 18,
    "CONFIG_FILE_CHANGED": 16,
    "METHOD_DELETED": 16,
    "METHOD_SIGNATURE_CHANGED": 18,
    "DTO_FIELD_CHANGED": 17,
    "FIELD_DELETED": 18,
    "BUDGET_CONTROLLER": 20,
    "HISTORICAL_CONTEXT_MISSING_FEEDBACK": 14,
}
_COMPLETION_TYPE_FEASIBILITY = {
    "PLANNER": 11,
    "RETRIEVER": 10,
    "BUDGET": 10,
    "PROMPT": 8,
    "STABILITY": 9,
    "OBSERVABILITY": 7,
}
_SUPPORTED_RETRIEVER_SIGNALS = {
    "DB_SQL_MAPPER_CHANGED",
    "METHOD_DELETED",
    "METHOD_SIGNATURE_CHANGED",
    "DTO_FIELD_CHANGED",
    "FIELD_DELETED",
}
_SIGNAL_NEXT_STAGE = {
    "DB_SQL_MAPPER_CHANGED": "已支持 signal 回归复盘：DB / Mapper / Entity 关联检索",
    "CACHE_WRITE_DELETE_CHANGED": "后续阶段：缓存 key 与读写链路检索设计",
    "MQ_CONFIG_CHANGED": "后续阶段：MQ producer / consumer / topic 配置检索设计",
    "CONFIG_FILE_CHANGED": "后续阶段：配置读取点与环境覆盖检索设计",
    "METHOD_DELETED": "已支持 signal 回归复盘：方法删除引用检索",
    "METHOD_SIGNATURE_CHANGED": "已支持 signal 回归复盘：方法签名引用检索",
    "DTO_FIELD_CHANGED": "已支持 signal 回归复盘：DTO / VO 字段引用检索",
    "FIELD_DELETED": "已支持 signal 回归复盘：字段删除引用检索",
    "BUDGET_CONTROLLER": "后续阶段：预算裁剪策略与未注入证据摘要复盘",
    "HISTORICAL_CONTEXT_MISSING_FEEDBACK": "后续阶段：上下文不足反馈到 Planner backlog 的归因流程",
}
_GAP_TYPE_LABELS = {
    "UNSUPPORTED_PLANNER_SIGNAL": "已有变更信号尚未被 Retriever 支持",
    "UNAVAILABLE_REQUESTED_CONTEXT": "Planner 请求的上下文当前不可用",
    "BUDGET_CUT": "证据因预算裁剪未完整注入",
    "RETRIEVAL_FAILED": "本地检索执行失败或不稳定",
}
_COMPLETION_TYPE_LABELS = {
    "PLANNER": "补 Planner 识别或请求规则",
    "RETRIEVER": "补本地证据检索器",
    "BUDGET": "补预算排序与摘要保护",
    "PROMPT": "补 Prompt 约束或输出协议",
    "STABILITY": "补稳定性和失败降级",
    "OBSERVABILITY": "补观测摘要和看板解释",
}
_FEEDBACK_CORRELATION_NOTE = (
    "现有反馈未保存 rule gap id；推荐先按受影响任务关联 CONTEXT_MISSING / FALSE_POSITIVE，"
    "无任务级反馈时只做项目近期近似统计。"
)


def get_rule_gap_dashboard(
    db: Session,
    *,
    project_id: int | None,
    gap_type: str | None,
    signal: str | None,
    recent_days: int | None,
    limit: int,
) -> dict[str, Any]:
    ensure_progress_schema(db)
    normalized_gap_type = _normalize_filter(gap_type)
    normalized_signal = _normalize_filter(signal)
    safe_limit = max(1, min(int(limit or 50), 500))
    cutoff = datetime.now() - timedelta(days=recent_days) if recent_days else None

    stmt = (
        select(CodeQualityReviewProgressEvent, ReviewTask, Project)
        .join(ReviewTask, ReviewTask.id == CodeQualityReviewProgressEvent.task_id)
        .join(Project, Project.id == ReviewTask.project_id)
        .where(CodeQualityReviewProgressEvent.phase == "CONTEXT_PACK_BUILT")
        .order_by(CodeQualityReviewProgressEvent.created_at.desc(), CodeQualityReviewProgressEvent.id.desc())
    )
    if project_id is not None:
        stmt = stmt.where(Project.id == project_id)
    if cutoff is not None:
        stmt = stmt.where(CodeQualityReviewProgressEvent.created_at >= cutoff)

    diagnostics = {
        "scannedEventCount": 0,
        "parsedEventCount": 0,
        "eventsWithRuleGapCount": 0,
        "eventsWithoutRuleGapCount": 0,
        "skippedEventCount": 0,
        "parseFailedEventCount": 0,
        "truncatedProgressSummaryCount": 0,
    }
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for event, task, project in db.execute(stmt).all():
        diagnostics["scannedEventCount"] += 1
        detail = _parse_progress_detail(event.detail)
        if detail is None:
            diagnostics["parseFailedEventCount"] += 1
            diagnostics["skippedEventCount"] += 1
            continue
        diagnostics["parsedEventCount"] += 1

        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else detail
        if bool(summary.get("progressSummaryTruncated")):
            diagnostics["truncatedProgressSummaryCount"] += 1
        raw_items = summary.get("ruleGapItems") if isinstance(summary, dict) else None
        if not isinstance(raw_items, list) or not raw_items:
            diagnostics["eventsWithoutRuleGapCount"] += 1
            continue

        event_has_gap = False
        for raw_item in raw_items:
            item = _normalize_rule_gap_item(raw_item)
            if item is None:
                continue
            if normalized_gap_type and item["gapType"].upper() != normalized_gap_type:
                continue
            if normalized_signal and normalized_signal not in _signal_tokens(item["signal"]):
                continue
            _add_gap_occurrence(groups, item, event, task, project)
            event_has_gap = True
        if event_has_gap:
            diagnostics["eventsWithRuleGapCount"] += 1
        else:
            diagnostics["eventsWithoutRuleGapCount"] += 1

    feedback_stats = _feedback_stats_for_groups(db, groups.values(), cutoff)
    items = [
        _group_to_response(group, _build_recommendation(group, feedback_stats.get(_group_key(group)), recent_days))
        for group in groups.values()
    ]
    items.sort(
        key=lambda item: (
            int(item["occurrenceCount"]),
            item.get("recentOccurredAt") or "",
            item.get("gapType") or "",
            item.get("signal") or "",
        ),
        reverse=True,
    )
    total_groups = len(items)
    total_occurrences = sum(int(item["occurrenceCount"]) for item in items)
    items = items[:safe_limit]
    return {
        "filters": {
            "projectId": project_id,
            "gapType": normalized_gap_type,
            "signal": normalized_signal,
            "recentDays": recent_days,
            "limit": safe_limit,
        },
        "items": items,
        "recommendations": _recommendations_response(items, safe_limit),
        "summary": {
            "totalGroups": total_groups,
            "returnedGroups": len(items),
            "totalOccurrences": total_occurrences,
            **diagnostics,
        },
    }


def _parse_progress_detail(detail: str | None) -> dict[str, Any] | None:
    if not detail or not str(detail).strip():
        return None
    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_rule_gap_item(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    gap_type = _safe_text(item.get("gapType"), 64).upper()
    signal = _safe_text(item.get("signal"), 120).upper()
    requested_context = _safe_text(item.get("requestedContext"), 160).upper()
    suggested_capability = _safe_text(item.get("suggestedCapability"), 240)
    if not gap_type or not signal:
        return None
    return {
        "gapType": gap_type,
        "signal": signal,
        "requestedContext": requested_context or "-",
        "suggestedCapability": suggested_capability or "-",
    }


def _safe_text(value: Any, max_length: int) -> str:
    text = scrub_sensitive(str(value or "").strip())
    for pattern in _LOCAL_PATH_PATTERNS:
        text = pattern.sub("[local-path]", text)
    text = re.sub(r"(?i)authorization\s*[:=]\s*[^,\s;}]+", "Authorization: ****", text)
    return text[:max_length]


def _normalize_filter(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _signal_tokens(signal: str) -> set[str]:
    return {part.strip().upper() for part in re.split(r"[,/|]", signal or "") if part.strip()}


def _group_key(group: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(group["gapType"]),
        str(group["signal"]),
        str(group["requestedContext"]),
        str(group["suggestedCapability"]),
    )


def _add_gap_occurrence(
    groups: dict[tuple[str, str, str, str], dict[str, Any]],
    item: dict[str, str],
    event: CodeQualityReviewProgressEvent,
    task: ReviewTask,
    project: Project,
) -> None:
    key = (
        item["gapType"],
        item["signal"],
        item["requestedContext"],
        item["suggestedCapability"],
    )
    group = groups.setdefault(
        key,
        {
            **item,
            "occurrenceCount": 0,
            "projectIds": set(),
            "taskIds": set(),
            "reviewKeys": set(),
            "recentOccurredAt": None,
            "projectStats": {},
            "recentTaskMap": {},
        },
    )
    occurred_at = event.created_at or task.created_at
    review_key = event.review_key or "default"
    group["occurrenceCount"] += 1
    group["projectIds"].add(int(project.id))
    group["taskIds"].add(int(task.id))
    group["reviewKeys"].add((int(task.id), review_key))
    if _is_later(occurred_at, group.get("recentOccurredAt")):
        group["recentOccurredAt"] = occurred_at

    project_stat = group["projectStats"].setdefault(
        int(project.id),
        {
            "projectId": int(project.id),
            "projectName": project.name,
            "occurrenceCount": 0,
            "taskIds": set(),
        },
    )
    project_stat["occurrenceCount"] += 1
    project_stat["taskIds"].add(int(task.id))

    sample_key = (int(task.id), review_key)
    sample = {
        "taskId": int(task.id),
        "reviewKey": review_key,
        "projectId": int(project.id),
        "projectName": project.name,
        "occurredAt": occurred_at,
    }
    current_sample = group["recentTaskMap"].get(sample_key)
    if current_sample is None or _is_later(occurred_at, current_sample.get("occurredAt")):
        group["recentTaskMap"][sample_key] = sample


def _feedback_stats_for_groups(
    db: Session,
    groups: Any,
    cutoff: datetime | None,
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    group_list = list(groups)
    if not group_list:
        return {}
    task_ids = {int(task_id) for group in group_list for task_id in group.get("taskIds", set())}
    project_ids = {int(project_id) for group in group_list for project_id in group.get("projectIds", set())}
    if not task_ids and not project_ids:
        return {}

    ensure_feedback_schema(db)
    filters = []
    if task_ids:
        filters.append(ReviewItemFeedback.task_id.in_(task_ids))
    if project_ids:
        filters.append(ReviewItemFeedback.project_id.in_(project_ids))
    stmt = select(ReviewItemFeedback).where(or_(*filters))
    if cutoff is not None:
        stmt = stmt.where(ReviewItemFeedback.created_at >= cutoff)
    records = db.scalars(stmt).all()

    feedback_stats: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for group in group_list:
        group_task_ids = {int(task_id) for task_id in group.get("taskIds", set())}
        group_project_ids = {int(project_id) for project_id in group.get("projectIds", set())}
        task_context_missing = 0
        task_false_positive = 0
        project_context_missing = 0
        project_false_positive = 0
        for record in records:
            is_task_match = int(record.task_id) in group_task_ids
            is_project_match = int(record.project_id) in group_project_ids
            if is_task_match and record.reason_type == "CONTEXT_MISSING":
                task_context_missing += 1
            if is_task_match and record.feedback_type == "FALSE_POSITIVE":
                task_false_positive += 1
            if is_project_match and record.reason_type == "CONTEXT_MISSING":
                project_context_missing += 1
            if is_project_match and record.feedback_type == "FALSE_POSITIVE":
                project_false_positive += 1

        if task_context_missing or task_false_positive:
            correlation = "TASK_LEVEL"
            context_missing_count = task_context_missing
            false_positive_count = task_false_positive
        elif project_context_missing or project_false_positive:
            correlation = "PROJECT_RECENT_APPROXIMATION"
            context_missing_count = project_context_missing
            false_positive_count = project_false_positive
        else:
            correlation = "NONE"
            context_missing_count = 0
            false_positive_count = 0

        feedback_stats[_group_key(group)] = {
            "contextMissingCount": context_missing_count,
            "falsePositiveCount": false_positive_count,
            "taskContextMissingCount": task_context_missing,
            "taskFalsePositiveCount": task_false_positive,
            "projectContextMissingCount": project_context_missing,
            "projectFalsePositiveCount": project_false_positive,
            "correlation": correlation,
            "note": _FEEDBACK_CORRELATION_NOTE,
        }
    return feedback_stats


def _is_later(left: Any, right: Any) -> bool:
    if right is None:
        return left is not None
    if left is None:
        return False
    return left > right


def _group_to_response(group: dict[str, Any], recommendation: dict[str, Any]) -> dict[str, Any]:
    projects = []
    for project in group["projectStats"].values():
        projects.append(
            {
                "projectId": project["projectId"],
                "projectName": project["projectName"],
                "occurrenceCount": int(project["occurrenceCount"]),
                "taskCount": len(project["taskIds"]),
            }
        )
    projects.sort(key=lambda item: (-int(item["occurrenceCount"]), str(item["projectName"])))

    recent_tasks = list(group["recentTaskMap"].values())
    recent_tasks.sort(key=lambda item: item.get("occurredAt") or datetime.min, reverse=True)
    return {
        "gapType": group["gapType"],
        "signal": group["signal"],
        "requestedContext": group["requestedContext"],
        "suggestedCapability": group["suggestedCapability"],
        "occurrenceCount": int(group["occurrenceCount"]),
        "projectCount": len(group["projectIds"]),
        "taskCount": len(group["taskIds"]),
        "reviewCount": len(group["reviewKeys"]),
        "recentOccurredAt": format_datetime(group.get("recentOccurredAt")),
        "projects": projects[:5],
        "recentTasks": [
            {
                "taskId": int(item["taskId"]),
                "reviewKey": item["reviewKey"],
                "projectId": int(item["projectId"]),
                "projectName": item["projectName"],
                "occurredAt": format_datetime(item.get("occurredAt")),
            }
            for item in recent_tasks[:5]
        ],
        "recommendation": recommendation,
    }


def _build_recommendation(
    group: dict[str, Any],
    feedback_stats: dict[str, Any] | None,
    recent_days: int | None,
) -> dict[str, Any]:
    feedback = feedback_stats or _empty_feedback_stats()
    completion_type = _completion_type(group)
    score_breakdown = _score_breakdown(group, feedback, completion_type)
    score = max(0, min(100, sum(score_breakdown.values())))
    status = _recommendation_status(score)
    signal_tokens = _signal_tokens(str(group.get("signal") or ""))
    if _is_historical_supported_gap(group):
        status = "NOT_NOW"
    if (
        group.get("gapType") == "UNSUPPORTED_PLANNER_SIGNAL"
        and signal_tokens.intersection(_SUPPORTED_RETRIEVER_SIGNALS)
        and score < 80
        and not _is_historical_supported_gap(group)
    ):
        status = "WATCH"
    next_stage = _suggested_next_stage(group, completion_type)
    reasons = _recommendation_reasons(group, feedback, completion_type, recent_days, score)
    return {
        "recommendationVersion": _RECOMMENDATION_VERSION,
        "recommendationStatus": status,
        "completionType": completion_type,
        "completionTypeLabel": _COMPLETION_TYPE_LABELS.get(completion_type, completion_type),
        "score": score,
        "scoreBreakdown": score_breakdown,
        "reasons": reasons,
        "suggestedNextStage": next_stage,
        "suggestedPrompt": _suggested_prompt(group, completion_type, next_stage, status),
        "feedbackSignals": feedback,
        "recentTaskSamples": [
            {
                "taskId": int(item["taskId"]),
                "reviewKey": item["reviewKey"],
                "projectId": int(item["projectId"]),
                "projectName": item["projectName"],
                "occurredAt": format_datetime(item.get("occurredAt")),
            }
            for item in sorted(
                group["recentTaskMap"].values(),
                key=lambda item: item.get("occurredAt") or datetime.min,
                reverse=True,
            )[:3]
        ],
    }


def _empty_feedback_stats() -> dict[str, Any]:
    return {
        "contextMissingCount": 0,
        "falsePositiveCount": 0,
        "taskContextMissingCount": 0,
        "taskFalsePositiveCount": 0,
        "projectContextMissingCount": 0,
        "projectFalsePositiveCount": 0,
        "correlation": "NONE",
        "note": _FEEDBACK_CORRELATION_NOTE,
    }


def _score_breakdown(
    group: dict[str, Any],
    feedback: dict[str, Any],
    completion_type: str,
) -> dict[str, int]:
    occurrence_count = int(group.get("occurrenceCount") or 0)
    task_count = len(group.get("taskIds") or [])
    project_count = len(group.get("projectIds") or [])
    feedback_score = min(
        15,
        int(feedback.get("contextMissingCount") or 0) * 4
        + int(feedback.get("falsePositiveCount") or 0) * 3,
    )
    resolved_current_support_penalty = 80 if _is_historical_supported_gap(group) else 0
    return {
        "gapType": _GAP_TYPE_SCORE.get(str(group.get("gapType") or ""), 10),
        "signalRisk": _signal_risk_score(str(group.get("signal") or "")),
        "occurrence": min(20, occurrence_count * 4),
        "taskImpact": min(12, task_count * 5),
        "projectImpact": min(10, project_count * 6),
        "recency": _recency_score(group.get("recentOccurredAt")),
        "feedback": feedback_score,
        "feasibility": _feasibility_score(group, completion_type),
        "complexityPenalty": -_complexity_penalty(group, completion_type),
        "resolvedCurrentSupport": -resolved_current_support_penalty,
    }


def _is_historical_supported_gap(group: dict[str, Any]) -> bool:
    if str(group.get("gapType") or "").upper() != "UNSUPPORTED_PLANNER_SIGNAL":
        return False
    signal_tokens = _signal_tokens(str(group.get("signal") or ""))
    return bool(signal_tokens) and signal_tokens.issubset(_SUPPORTED_RETRIEVER_SIGNALS)


def _signal_risk_score(signal: str) -> int:
    tokens = _signal_tokens(signal)
    if not tokens:
        return 8
    return max(_SIGNAL_RISK_SCORE.get(token, 8) for token in tokens)


def _recency_score(occurred_at: Any) -> int:
    if occurred_at is None:
        return 0
    age_days = max(0, (datetime.now() - occurred_at).days)
    if age_days <= 7:
        return 10
    if age_days <= 30:
        return 6
    if age_days <= 90:
        return 3
    return 0


def _feasibility_score(group: dict[str, Any], completion_type: str) -> int:
    base = _COMPLETION_TYPE_FEASIBILITY.get(completion_type, 7)
    signal_tokens = _signal_tokens(str(group.get("signal") or ""))
    if signal_tokens.intersection(_SUPPORTED_RETRIEVER_SIGNALS):
        return min(14, base + 3)
    if "DB_SQL_MAPPER_CHANGED" in signal_tokens:
        return base
    if signal_tokens.intersection({"CACHE_WRITE_DELETE_CHANGED", "MQ_CONFIG_CHANGED", "CONFIG_FILE_CHANGED"}):
        return max(7, base - 1)
    return base


def _complexity_penalty(group: dict[str, Any], completion_type: str) -> int:
    signal_tokens = _signal_tokens(str(group.get("signal") or ""))
    if completion_type == "BUDGET":
        return 6
    if completion_type == "PROMPT":
        return 5
    if completion_type == "STABILITY":
        return 7
    if "DB_SQL_MAPPER_CHANGED" in signal_tokens:
        return 12
    if "MQ_CONFIG_CHANGED" in signal_tokens:
        return 11
    if "CACHE_WRITE_DELETE_CHANGED" in signal_tokens:
        return 9
    if "CONFIG_FILE_CHANGED" in signal_tokens:
        return 8
    if signal_tokens.intersection(_SUPPORTED_RETRIEVER_SIGNALS):
        return 4
    return 8


def _completion_type(group: dict[str, Any]) -> str:
    gap_type = str(group.get("gapType") or "").upper()
    signal = str(group.get("signal") or "").upper()
    requested_context = str(group.get("requestedContext") or "").upper()
    capability = str(group.get("suggestedCapability") or "").upper()
    if gap_type == "BUDGET_CUT" or "BUDGET" in signal or "BUDGET" in capability:
        return "BUDGET"
    if gap_type == "RETRIEVAL_FAILED":
        return "STABILITY"
    if "PROMPT" in capability:
        return "PROMPT"
    if "OBSERV" in capability or "PROGRESS" in requested_context:
        return "OBSERVABILITY"
    if gap_type == "UNSUPPORTED_PLANNER_SIGNAL":
        if signal in {"PLANNER_REQUEST", "HISTORICAL_CONTEXT_MISSING_FEEDBACK"}:
            return "PLANNER"
        return "RETRIEVER"
    if gap_type == "UNAVAILABLE_REQUESTED_CONTEXT":
        if requested_context in {
            "REFERENCE_SEARCH",
            "CALLER_CONTEXT",
            "RELATED_FILE",
            "DB_SCHEMA_CONTEXT",
            "CONFIG_CONTEXT",
            "MQ_CONFIG_CONTEXT",
            "CACHE_USAGE_CONTEXT",
        }:
            return "RETRIEVER"
        if requested_context == "TEST_RESULT_CONTEXT":
            return "OBSERVABILITY"
        return "PLANNER"
    return "OBSERVABILITY"


def _recommendation_status(score: int) -> str:
    if score >= _RECOMMENDED_SCORE_THRESHOLD:
        return "RECOMMENDED"
    if score >= _WATCH_SCORE_THRESHOLD:
        return "WATCH"
    return "NOT_NOW"


def _suggested_next_stage(group: dict[str, Any], completion_type: str) -> str:
    signal_tokens = _signal_tokens(str(group.get("signal") or ""))
    for signal in sorted(signal_tokens):
        if signal in _SIGNAL_NEXT_STAGE:
            return _SIGNAL_NEXT_STAGE[signal]
    if completion_type == "BUDGET":
        return "后续阶段：预算裁剪策略与未注入证据摘要复盘"
    if completion_type == "PLANNER":
        return "后续阶段：Context Planner 规则补齐与请求类型治理"
    if completion_type == "PROMPT":
        return "后续阶段：上下文完整性 Prompt 约束与输出协议复盘"
    if completion_type == "STABILITY":
        return "后续阶段：本地检索稳定性、超时和失败降级复盘"
    if completion_type == "OBSERVABILITY":
        return "后续阶段：高准确模式观测摘要与缺口解释补齐"
    return "后续阶段：本地证据 Retriever 能力补齐"


def _recommendation_reasons(
    group: dict[str, Any],
    feedback: dict[str, Any],
    completion_type: str,
    recent_days: int | None,
    score: int,
) -> list[str]:
    occurrence_count = int(group.get("occurrenceCount") or 0)
    task_count = len(group.get("taskIds") or [])
    project_count = len(group.get("projectIds") or [])
    days_text = f"近 {recent_days} 天" if recent_days else "全部时间范围内"
    gap_type = str(group.get("gapType") or "")
    signal = str(group.get("signal") or "")
    reasons = [
        f"{days_text}出现 {occurrence_count} 次，影响 {task_count} 个任务、{project_count} 个项目。",
        f"缺口类型是“{_GAP_TYPE_LABELS.get(gap_type, gap_type)}”，关联 signal 为 {signal or '-'}。",
        f"建议补全方向是“{_COMPLETION_TYPE_LABELS.get(completion_type, completion_type)}”，启发式评分 {score}/100。",
    ]
    recent = format_datetime(group.get("recentOccurredAt"))
    if recent:
        reasons.append(f"最近一次出现在 {recent}，可从最近任务样例跳转人工确认。")
    context_missing_count = int(feedback.get("contextMissingCount") or 0)
    false_positive_count = int(feedback.get("falsePositiveCount") or 0)
    if context_missing_count or false_positive_count:
        reasons.append(
            f"关联反馈信号：CONTEXT_MISSING {context_missing_count} 条，FALSE_POSITIVE {false_positive_count} 条。"
        )
    else:
        reasons.append("暂无可直接关联的 CONTEXT_MISSING / FALSE_POSITIVE 反馈，已预留反馈信号字段继续观察。")
    if feedback.get("correlation") == "PROJECT_RECENT_APPROXIMATION":
        reasons.append("反馈关联为项目近期近似统计，不能视为精确归因。")
    if _is_historical_supported_gap(group):
        reasons.append("当前代码已支持该 signal；该记录来自历史 CONTEXT_PACK_BUILT 摘要，建议通过新任务或重跑验证。")
    return [_safe_text(reason, 240) for reason in reasons[:6]]


def _suggested_prompt(
    group: dict[str, Any],
    completion_type: str,
    next_stage: str,
    status: str,
) -> str:
    if _is_historical_supported_gap(group):
        prompt = f"""请只做 {next_stage}。

背景：
- 规则缺口推荐状态：{status}
- 缺口类型：{group.get("gapType") or "-"}
- signal：{group.get("signal") or "-"}
- requestedContext：{group.get("requestedContext") or "-"}
- 当前代码已经支持该 signal；该缺口来自历史 CONTEXT_PACK_BUILT 摘要。

目标：
用一个新任务或重跑最近任务验证该 signal 不再产生 UNSUPPORTED_PLANNER_SIGNAL，并确认 Context Pack / 高准确模式流转里有对应 Retriever 支持摘要。

范围：
- 只做回归验证和必要文档记录。
- 不实现新的 Retriever，不自动改规则、不自动改 Prompt、不自动降级、不自动忽略 finding。

完成后停止，输出“验证了什么、结果是什么、是否还有新缺口”。"""
        return _safe_text(prompt, 2400)

    prompt = f"""请只推进 {next_stage}。

背景：
- 规则缺口推荐状态：{status}
- 缺口类型：{group.get("gapType") or "-"}
- signal：{group.get("signal") or "-"}
- requestedContext：{group.get("requestedContext") or "-"}
- 建议能力：{group.get("suggestedCapability") or "-"}

目标：
把该类规则缺口补成可验证的 {completion_type} 能力，并降低上下文不足导致的误判。

范围：
- 先写设计和接口 / 数据结构边界，再实现最小闭环。
- 只读取当前任务所需的安全摘要或 bounded evidence。
- 补测试、README 验证步骤和 docs/34 落地记录。

禁止：
- 不自动改规则、不自动改 Prompt、不自动降级、不自动忽略 finding。
- 不接 RAG，不做 AST / LSP，不做全项目无限扫描。
- 不返回源码片段、本地绝对路径、token、认证头、大段 diff 或 provider raw output。

完成后停止，输出“改了什么、为什么、如何验证”，等待用户确认后再进入下一阶段。"""
    return _safe_text(prompt, 2400)


def _recommendations_response(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    recommendation_items = [_recommendation_dashboard_item(item) for item in items]
    recommendation_items.sort(
        key=lambda item: (
            _RECOMMENDATION_STATUS_ORDER.get(item.get("recommendationStatus"), 0),
            int(item.get("score") or 0),
            int(item.get("occurrenceCount") or 0),
            item.get("recentOccurredAt") or "",
        ),
        reverse=True,
    )
    status_counts = Counter(item.get("recommendationStatus") or "UNKNOWN" for item in recommendation_items)
    completion_counts = Counter(item.get("completionType") or "UNKNOWN" for item in recommendation_items)
    return {
        "items": recommendation_items[:limit],
        "summary": {
            "recommendationVersion": _RECOMMENDATION_VERSION,
            "totalRecommendations": len(recommendation_items),
            "recommendedCount": int(status_counts.get("RECOMMENDED", 0)),
            "watchCount": int(status_counts.get("WATCH", 0)),
            "notNowCount": int(status_counts.get("NOT_NOW", 0)),
            "completionTypeCounts": dict(completion_counts),
            "feedbackCorrelationNote": _FEEDBACK_CORRELATION_NOTE,
            "scoreFormula": (
                "gap type + signal risk + occurrence + task impact + project impact + recency "
                "+ feedback + feasibility - complexity penalty"
            ),
        },
    }


def _recommendation_dashboard_item(item: dict[str, Any]) -> dict[str, Any]:
    recommendation = item.get("recommendation") if isinstance(item.get("recommendation"), dict) else {}
    return {
        "gapType": item.get("gapType"),
        "signal": item.get("signal"),
        "requestedContext": item.get("requestedContext"),
        "suggestedCapability": item.get("suggestedCapability"),
        "occurrenceCount": item.get("occurrenceCount"),
        "projectCount": item.get("projectCount"),
        "taskCount": item.get("taskCount"),
        "reviewCount": item.get("reviewCount"),
        "recentOccurredAt": item.get("recentOccurredAt"),
        "projects": item.get("projects") or [],
        "recentTasks": item.get("recentTasks") or [],
        "recommendationStatus": recommendation.get("recommendationStatus"),
        "completionType": recommendation.get("completionType"),
        "completionTypeLabel": recommendation.get("completionTypeLabel"),
        "score": recommendation.get("score"),
        "scoreBreakdown": recommendation.get("scoreBreakdown") or {},
        "reasons": recommendation.get("reasons") or [],
        "suggestedNextStage": recommendation.get("suggestedNextStage"),
        "suggestedPrompt": recommendation.get("suggestedPrompt"),
        "feedbackSignals": recommendation.get("feedbackSignals") or _empty_feedback_stats(),
        "recentTaskSamples": recommendation.get("recentTaskSamples") or [],
    }
