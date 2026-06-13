from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewProgressEvent
from app.code_quality.repository import ensure_progress_schema, scrub_sensitive
from app.core.json_utils import format_datetime
from app.project_integration.models import Project
from app.review_record.models import ReviewTask


_LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[^\s,;'\"}]+"),
    re.compile(r"/[^\s,;'\"}]+(?:/\.local|/review-workspaces|/worktrees|/mirrors|/tmp)[^\s,;'\"}]*"),
]


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

    items = [_group_to_response(group) for group in groups.values()]
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


def _is_later(left: Any, right: Any) -> bool:
    if right is None:
        return left is not None
    if left is None:
        return False
    return left > right


def _group_to_response(group: dict[str, Any]) -> dict[str, Any]:
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
    }
