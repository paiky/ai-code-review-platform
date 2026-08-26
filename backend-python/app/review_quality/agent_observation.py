from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewRun
from app.agent_review.repository import ensure_agent_review_schema
from app.code_quality.models import CodeQualityReviewResult
from app.core.errors import AppError
from app.core.json_utils import format_datetime, read_json
from app.evaluation.models import EvaluationCase
from app.evaluation.repository import ensure_evaluation_case_schema
from app.project_integration.models import Project
from app.review_feedback.models import ReviewItemFeedback
from app.review_feedback.repository import ensure_feedback_schema
from app.review_record.models import ReviewTask


MINIMUM_ANNOTATED_SAMPLE_COUNT = 30
_TERMINAL_FAILURE_STATUSES = {"FAILED", "CANCELLED", "TIMED_OUT"}
_PROHIBITED_EXPORT_FLAGS = {
    "includesource",
    "includediff",
    "includeapikey",
    "includeprompt",
    "includereasoning",
    "includethoughts",
    "includemcpresponses",
    "includesession",
    "includesensitive",
}
_PROHIBITED_FIELD_TOKENS = {
    "source",
    "diff",
    "apikey",
    "api_key",
    "prompt",
    "reasoning",
    "thought",
    "mcpresponse",
    "session",
    "rawoutput",
}
_USAGE_ALIASES = {
    "inputtokens": "inputTokens",
    "outputtokens": "outputTokens",
    "totaltokens": "totalTokens",
    "cachereadtokens": "cacheReadTokens",
    "cachewritetokens": "cacheWriteTokens",
    "estimatedcost": "estimatedCost",
    "cost": "estimatedCost",
}


def get_agent_observation(
    db: Session,
    *,
    task_id: int | None,
    project_id: int | None,
    profile: str | None,
    start_at: str | None,
    end_at: str | None,
    synthetic_demo: bool,
) -> dict[str, Any]:
    filters = _normalize_filters(
        task_id=task_id,
        project_id=project_id,
        profile=profile,
        start_at=start_at,
        end_at=end_at,
        synthetic_demo=synthetic_demo,
    )
    snapshot = (
        _filter_synthetic_snapshot(_synthetic_demo_snapshot(), filters)
        if synthetic_demo
        else _load_snapshot(db, filters)
    )
    return aggregate_agent_observation(snapshot, filters=filters)


def export_agent_observation(db: Session, request: dict[str, Any]) -> dict[str, Any]:
    if str(request.get("confirmation") or "") != "SANITIZED_SUMMARY_ONLY":
        raise AppError(
            "EXPORT_SCOPE_FORBIDDEN",
            "Sanitized summary export requires confirmation=SANITIZED_SUMMARY_ONLY",
            403,
        )
    _assert_export_scope(request)
    raw_filters = request.get("filters") if isinstance(request.get("filters"), dict) else request
    observation = get_agent_observation(
        db,
        task_id=_optional_int(raw_filters.get("taskId"), "taskId"),
        project_id=_optional_int(raw_filters.get("projectId"), "projectId"),
        profile=_clean_text(raw_filters.get("profile")),
        start_at=_clean_text(raw_filters.get("startAt")),
        end_at=_clean_text(raw_filters.get("endAt")),
        synthetic_demo=bool(raw_filters.get("syntheticDemo")),
    )
    return _sanitized_export(observation)


def aggregate_agent_observation(
    snapshot: dict[str, list[dict[str, Any]]],
    *,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results = list(snapshot.get("results") or [])
    runs = list(snapshot.get("runs") or [])
    cases = list(snapshot.get("cases") or [])
    feedback = list(snapshot.get("feedback") or [])
    engine_by_target = {
        (int(item["taskId"]), str(item.get("reviewKey") or "")): _result_engine(item)
        for item in results
    }
    grouped_results: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        grouped_results[int(item["taskId"])].append(item)

    standard_results = [item for item in results if _result_engine(item) == "STANDARD"]
    agent_results = [item for item in results if _result_engine(item) == "AGENT"]
    standard_tasks = {int(item["taskId"]) for item in standard_results}
    agent_tasks = {int(item["taskId"]) for item in agent_results}
    paired_tasks = standard_tasks & agent_tasks

    annotation = _annotation_summary(cases, feedback, engine_by_target, paired_tasks)
    comparisons = _comparison_rows(grouped_results, runs, cases, feedback)
    agent_status_counts = Counter(str(item.get("status") or "UNKNOWN").upper() for item in runs)
    success_count = int(agent_status_counts.get("SUCCEEDED", 0))
    failure_count = sum(int(agent_status_counts.get(status, 0)) for status in _TERMINAL_FAILURE_STATUSES)
    fallback_count = sum(1 for item in runs if str(item.get("effectiveEngine") or "").upper() == "STANDARD_FALLBACK")
    in_flight_count = max(0, len(runs) - success_count - failure_count)

    gate_sample_count = int(annotation["annotationSampleCount"])
    gate_status = "INSUFFICIENT_SAMPLE" if gate_sample_count < MINIMUM_ANNOTATED_SAMPLE_COUNT else "READY_FOR_STAGE_3B_REVIEW"
    data_mode = "SYNTHETIC_DEMO" if any(bool(item.get("synthetic")) for item in results) else "PRODUCTION_OBSERVATION"
    run_count = len(runs)
    return {
        "schemaVersion": "agent-observation-v1",
        "stage": "3A",
        "dataMode": data_mode,
        "filters": _public_filters(filters or {}),
        "sampleSummary": {
            "taskCount": len(set(grouped_results)),
            "standardSampleCount": len(standard_results),
            "agentSampleCount": len(agent_results),
            "pairedTaskCount": len(paired_tasks),
            "unpairedStandardTaskCount": len(standard_tasks - paired_tasks),
            "unpairedAgentTaskCount": len(agent_tasks - paired_tasks),
        },
        "annotationProgress": annotation,
        "findingSummary": {
            "standardFindingCount": sum(_non_negative(item.get("findingCount")) for item in standard_results),
            "agentFindingCount": sum(_non_negative(item.get("findingCount")) for item in agent_results),
            "humanFalsePositiveCount": annotation["humanFalsePositiveCount"],
            "missingFindingCount": annotation["missingFindingCount"],
            "contextInsufficientCount": annotation["contextInsufficientCount"],
            "byEngine": annotation["byEngine"],
        },
        "agentReliability": {
            "runCount": run_count,
            "successCount": success_count,
            "failureCount": failure_count,
            "inFlightCount": in_flight_count,
            "fallbackCount": fallback_count,
            "successRate": _rate(success_count, run_count),
            "failureRate": _rate(failure_count, run_count),
            "fallbackRate": _rate(fallback_count, run_count),
            "statusCounts": dict(sorted(agent_status_counts.items())),
        },
        "agentExecutionMetrics": {
            "durationMs": _distribution(item.get("durationMs") for item in runs),
            "turnCount": _distribution(item.get("turnCount") for item in runs),
            "toolCallCount": _distribution(item.get("toolCallCount") for item in runs),
            "sourceBytesReturned": _distribution(item.get("sourceBytesReturned") for item in runs),
            "diffBytesReturned": _distribution(item.get("diffBytesReturned") for item in runs),
            "usageSummary": _usage_summary(runs),
        },
        "sampleGate": {
            "status": gate_status,
            "minimumAnnotatedSampleCount": MINIMUM_ANNOTATED_SAMPLE_COUNT,
            "observedAnnotatedSampleCount": gate_sample_count,
            "remainingCount": max(0, MINIMUM_ANNOTATED_SAMPLE_COUNT - gate_sample_count),
            "conclusionCalculated": False,
            "expansionConclusion": None,
            "message": (
                "人工标注样本不足 30 条，不计算扩大范围结论。"
                if gate_status == "INSUFFICIENT_SAMPLE"
                else "样本数量达到阶段 3B 人工验收起点；阶段 3A 仍不计算准确性或扩大范围结论。"
            ),
        },
        "comparisons": comparisons,
        "safety": {
            "sourceExported": False,
            "fullDiffExported": False,
            "apiKeyExported": False,
            "promptExported": False,
            "reasoningExported": False,
            "mcpSourceExported": False,
        },
    }


def percentile_nearest_rank(values: list[int | float], percentile: float) -> int | float:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(max(0.0, min(1.0, percentile)) * len(ordered)))
    return ordered[rank - 1]


def _load_snapshot(db: Session, filters: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    ensure_agent_review_schema(db)
    ensure_evaluation_case_schema(db)
    ensure_feedback_schema(db)
    observed_at = func.coalesce(
        CodeQualityReviewResult.finished_at,
        CodeQualityReviewResult.created_at,
        ReviewTask.created_at,
    )
    stmt = (
        select(CodeQualityReviewResult, ReviewTask, Project)
        .join(ReviewTask, ReviewTask.id == CodeQualityReviewResult.task_id)
        .join(Project, Project.id == CodeQualityReviewResult.project_id)
    )
    if filters["taskId"] is not None:
        stmt = stmt.where(CodeQualityReviewResult.task_id == filters["taskId"])
    if filters["projectId"] is not None:
        stmt = stmt.where(CodeQualityReviewResult.project_id == filters["projectId"])
    if filters["profile"]:
        stmt = stmt.where(CodeQualityReviewResult.profile_code == filters["profile"])
    if filters["startAtValue"] is not None:
        stmt = stmt.where(observed_at >= filters["startAtValue"])
    if filters["endAtValue"] is not None:
        stmt = stmt.where(observed_at <= filters["endAtValue"])
    rows = db.execute(stmt.order_by(observed_at.desc(), CodeQualityReviewResult.id.desc())).all()
    results = [
        {
            "taskId": int(result.task_id),
            "projectId": int(result.project_id),
            "projectName": project.name,
            "profile": result.profile_code,
            "reviewKey": result.review_key,
            "requestedEngine": result.requested_engine or "STANDARD",
            "effectiveEngine": result.effective_engine or "STANDARD",
            "status": result.status,
            "findingCount": int(result.finding_count or 0),
            "agentRunId": int(result.agent_run_id) if result.agent_run_id is not None else None,
            "observedAt": format_datetime(result.finished_at or result.created_at or task.created_at),
            "synthetic": False,
        }
        for result, task, project in rows
    ]
    task_ids = {int(item["taskId"]) for item in results}
    if not task_ids:
        return {"results": [], "runs": [], "cases": [], "feedback": []}
    selected_targets = {
        (int(item["taskId"]), str(item.get("reviewKey") or ""))
        for item in results
    }
    selected_agent_run_ids = {
        int(item["agentRunId"])
        for item in results
        if item.get("agentRunId") is not None
    }
    runs = [
        {
            "runId": int(run.id),
            "taskId": int(run.task_id),
            "reviewKey": run.review_key,
            "status": run.status,
            "effectiveEngine": run.effective_engine,
            "durationMs": run.duration_ms,
            "turnCount": int(run.turn_count or 0),
            "toolCallCount": int(run.tool_call_count or 0),
            "sourceBytesReturned": int(run.source_bytes_returned or 0),
            "diffBytesReturned": int(run.diff_bytes_returned or 0),
            "usage": read_json(run.usage_json, {}),
            "observedAt": format_datetime(run.finished_at or run.created_at),
            "synthetic": False,
        }
        for run in db.scalars(
            select(AgentReviewRun)
            .where(AgentReviewRun.task_id.in_(task_ids))
            .order_by(AgentReviewRun.created_at.desc(), AgentReviewRun.id.desc())
        ).all()
        if int(run.id) in selected_agent_run_ids
        or (int(run.task_id), str(run.review_key or "")) in selected_targets
    ]
    cases = [
        {
            "id": int(case.id),
            "taskId": int(case.task_id) if case.task_id is not None else None,
            "reviewKey": case.review_key,
            "fingerprint": case.fingerprint,
            "verdict": case.verdict,
            "synthetic": False,
        }
        for case in db.scalars(select(EvaluationCase).where(EvaluationCase.task_id.in_(task_ids))).all()
        if (int(case.task_id), str(case.review_key or "")) in selected_targets
        or (
            case.review_key is None
            and (not filters["profile"] or str(case.profile or "") == filters["profile"])
        )
    ]
    feedback = [
        {
            "id": int(item.id),
            "taskId": int(item.task_id),
            "reviewKey": item.review_key,
            "fingerprint": item.item_fingerprint,
            "feedbackType": item.feedback_type,
            "reasonType": item.reason_type,
            "synthetic": False,
        }
        for item in db.scalars(
            select(ReviewItemFeedback)
            .where(ReviewItemFeedback.task_id.in_(task_ids))
            .where(ReviewItemFeedback.source_type == "AI_FINDING")
        ).all()
        if (int(item.task_id), str(item.review_key or "")) in selected_targets
    ]
    return {"results": results, "runs": runs, "cases": cases, "feedback": feedback}


def _annotation_summary(
    cases: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    engine_by_target: dict[tuple[int, str], str],
    paired_tasks: set[int],
) -> dict[str, Any]:
    counts = {
        "STANDARD": {"humanFalsePositiveCount": 0, "missingFindingCount": 0, "contextInsufficientCount": 0},
        "AGENT": {"humanFalsePositiveCount": 0, "missingFindingCount": 0, "contextInsufficientCount": 0},
        "UNATTRIBUTED": {"humanFalsePositiveCount": 0, "missingFindingCount": 0, "contextInsufficientCount": 0},
    }
    annotated_engines: dict[int, set[str]] = defaultdict(set)
    annotated_tasks: set[int] = set()
    case_targets: set[tuple[int, str, str]] = set()
    annotation_sample_count = 0
    for case in cases:
        task_id = _optional_snapshot_task_id(case)
        if task_id is None:
            continue
        review_key = str(case.get("reviewKey") or "")
        fingerprint = str(case.get("fingerprint") or f"case:{case.get('id')}")
        case_targets.add((task_id, review_key, fingerprint))
        annotation_sample_count += 1
        engine = engine_by_target.get((task_id, review_key), "UNATTRIBUTED")
        annotated_tasks.add(task_id)
        if engine in {"STANDARD", "AGENT"}:
            annotated_engines[task_id].add(engine)
        verdict = str(case.get("verdict") or "UNKNOWN").upper()
        if verdict == "FALSE_POSITIVE":
            counts[engine]["humanFalsePositiveCount"] += 1
        elif verdict == "MISSING_FINDING":
            counts[engine]["missingFindingCount"] += 1
        elif verdict == "CONTEXT_MISSING":
            counts[engine]["contextInsufficientCount"] += 1
    for item in feedback:
        task_id = _optional_snapshot_task_id(item)
        if task_id is None:
            continue
        review_key = str(item.get("reviewKey") or "")
        fingerprint = str(item.get("fingerprint") or f"feedback:{item.get('id')}")
        if (task_id, review_key, fingerprint) in case_targets:
            continue
        annotation_sample_count += 1
        engine = engine_by_target.get((task_id, review_key), "UNATTRIBUTED")
        annotated_tasks.add(task_id)
        if engine in {"STANDARD", "AGENT"}:
            annotated_engines[task_id].add(engine)
        if str(item.get("feedbackType") or "").upper() == "FALSE_POSITIVE":
            counts[engine]["humanFalsePositiveCount"] += 1
        if str(item.get("reasonType") or "").upper() == "CONTEXT_MISSING":
            counts[engine]["contextInsufficientCount"] += 1
    annotated_pair_count = sum(
        1 for task_id in paired_tasks if annotated_engines.get(task_id, set()) >= {"STANDARD", "AGENT"}
    )
    return {
        "evaluationCaseCount": len(cases),
        "findingFeedbackCount": len(feedback),
        "annotationSampleCount": annotation_sample_count,
        "annotatedTaskCount": len(annotated_tasks),
        "annotatedPairedTaskCount": annotated_pair_count,
        "targetAnnotatedSampleCount": MINIMUM_ANNOTATED_SAMPLE_COUNT,
        "remainingAnnotatedSampleCount": max(0, MINIMUM_ANNOTATED_SAMPLE_COUNT - annotation_sample_count),
        "humanFalsePositiveCount": sum(item["humanFalsePositiveCount"] for item in counts.values()),
        "missingFindingCount": sum(item["missingFindingCount"] for item in counts.values()),
        "contextInsufficientCount": sum(item["contextInsufficientCount"] for item in counts.values()),
        "byEngine": counts,
    }


def _comparison_rows(
    grouped_results: dict[int, list[dict[str, Any]]],
    runs: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    runs_by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        runs_by_task[int(run["taskId"])].append(run)
    annotation_counts = Counter(
        int(item["taskId"])
        for item in [*cases, *feedback]
        if item.get("taskId") is not None
    )
    rows: list[dict[str, Any]] = []
    for task_id, task_results in grouped_results.items():
        first = task_results[0]
        standard = [item for item in task_results if _result_engine(item) == "STANDARD"]
        agent = [item for item in task_results if _result_engine(item) == "AGENT"]
        task_runs = runs_by_task.get(task_id, [])
        latest_run = task_runs[0] if task_runs else {}
        rows.append(
            {
                "taskId": task_id,
                "projectId": first.get("projectId"),
                "projectName": first.get("projectName"),
                "profile": first.get("profile"),
                "standardResultCount": len(standard),
                "agentResultCount": len(agent),
                "paired": bool(standard and agent),
                "standardFindingCount": sum(_non_negative(item.get("findingCount")) for item in standard),
                "agentFindingCount": sum(_non_negative(item.get("findingCount")) for item in agent),
                "annotationCount": int(annotation_counts.get(task_id, 0)),
                "agentStatus": latest_run.get("status"),
                "fallbackTriggered": any(
                    str(run.get("effectiveEngine") or "").upper() == "STANDARD_FALLBACK"
                    for run in task_runs
                ),
                "durationMs": latest_run.get("durationMs"),
                "turnCount": latest_run.get("turnCount"),
                "toolCallCount": latest_run.get("toolCallCount"),
                "sourceBytesReturned": latest_run.get("sourceBytesReturned"),
                "observedAt": first.get("observedAt"),
                "synthetic": bool(first.get("synthetic")),
            }
        )
    rows.sort(key=lambda item: (str(item.get("observedAt") or ""), int(item["taskId"])), reverse=True)
    return rows[:200]


def _distribution(raw_values: Any) -> dict[str, int | float]:
    values = [_non_negative(value) for value in raw_values if value is not None]
    if not values:
        return {"sampleCount": 0, "total": 0, "average": 0, "p50": 0, "p95": 0, "max": 0}
    return {
        "sampleCount": len(values),
        "total": sum(values),
        "average": round(sum(values) / len(values), 4),
        "p50": percentile_nearest_rank(values, 0.50),
        "p95": percentile_nearest_rank(values, 0.95),
        "max": max(values),
    }


def _usage_summary(runs: list[dict[str, Any]]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {
        "inputTokens": 0,
        "outputTokens": 0,
        "totalTokens": 0,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "estimatedCost": 0,
    }
    recorded = 0
    for run in runs:
        usage = run.get("usage")
        if not isinstance(usage, dict) or not usage:
            continue
        recorded += 1
        _collect_usage_numbers(usage, totals)
    totals["recordedRunCount"] = recorded
    totals["estimatedCost"] = round(float(totals["estimatedCost"]), 6)
    return totals


def _collect_usage_numbers(value: Any, totals: dict[str, int | float]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            target = _USAGE_ALIASES.get(normalized)
            if target and isinstance(item, (int, float)) and not isinstance(item, bool):
                totals[target] += max(0, item)
            elif isinstance(item, (dict, list)):
                _collect_usage_numbers(item, totals)
    elif isinstance(value, list):
        for item in value:
            _collect_usage_numbers(item, totals)


def _normalize_filters(
    *,
    task_id: int | None,
    project_id: int | None,
    profile: str | None,
    start_at: str | None,
    end_at: str | None,
    synthetic_demo: bool,
) -> dict[str, Any]:
    start_value = _parse_datetime(start_at, "startAt")
    end_value = _parse_datetime(end_at, "endAt")
    if start_value is not None and end_value is not None and start_value > end_value:
        raise AppError("VALIDATION_ERROR", "startAt must be earlier than or equal to endAt", 400)
    return {
        "taskId": task_id,
        "projectId": project_id,
        "profile": _clean_text(profile),
        "startAt": _clean_text(start_at),
        "endAt": _clean_text(end_at),
        "syntheticDemo": bool(synthetic_demo),
        "startAtValue": start_value,
        "endAtValue": end_value,
    }


def _parse_datetime(value: str | None, field: str) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError("VALIDATION_ERROR", f"{field} must be an ISO-8601 datetime", 400) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _sanitized_export(observation: dict[str, Any]) -> dict[str, Any]:
    filters = observation.get("filters") or {}
    safe_filters = {
        "taskRef": _opaque_ref("task", filters.get("taskId")),
        "projectRef": _opaque_ref("project", filters.get("projectId")),
        "profileRef": _opaque_ref("profile", filters.get("profile")),
        "startAt": filters.get("startAt"),
        "endAt": filters.get("endAt"),
        "syntheticDemo": bool(filters.get("syntheticDemo")),
    }
    comparisons = []
    for item in observation.get("comparisons") or []:
        comparisons.append(
            {
                "taskRef": _opaque_ref("task", item.get("taskId")),
                "projectRef": _opaque_ref("project", item.get("projectId")),
                "profileRef": _opaque_ref("profile", item.get("profile")),
                "standardResultCount": item.get("standardResultCount"),
                "agentResultCount": item.get("agentResultCount"),
                "paired": bool(item.get("paired")),
                "standardFindingCount": item.get("standardFindingCount"),
                "agentFindingCount": item.get("agentFindingCount"),
                "annotationCount": item.get("annotationCount"),
                "agentStatus": item.get("agentStatus"),
                "fallbackTriggered": bool(item.get("fallbackTriggered")),
                "durationMs": item.get("durationMs"),
                "turnCount": item.get("turnCount"),
                "toolCallCount": item.get("toolCallCount"),
                "sourceBytesReturned": item.get("sourceBytesReturned"),
                "observedAt": item.get("observedAt"),
                "synthetic": bool(item.get("synthetic")),
            }
        )
    return {
        "schemaVersion": "agent-observation-export-v1",
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "stage": "3A",
        "dataMode": observation.get("dataMode"),
        "filters": safe_filters,
        "sampleSummary": observation.get("sampleSummary"),
        "annotationProgress": observation.get("annotationProgress"),
        "findingSummary": observation.get("findingSummary"),
        "agentReliability": {
            key: value
            for key, value in (observation.get("agentReliability") or {}).items()
            if key != "statusCounts"
        },
        "agentExecutionMetrics": observation.get("agentExecutionMetrics"),
        "sampleGate": observation.get("sampleGate"),
        "comparisons": comparisons,
        "redactionPolicy": {
            "identifiersPseudonymized": True,
            "sourceIncluded": False,
            "fullDiffIncluded": False,
            "apiKeyIncluded": False,
            "promptIncluded": False,
            "reasoningIncluded": False,
            "mcpSourceIncluded": False,
            "freeTextIncluded": False,
        },
    }


def _assert_export_scope(request: dict[str, Any]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized in _PROHIBITED_EXPORT_FLAGS and bool(item):
                    raise AppError("EXPORT_SCOPE_FORBIDDEN", f"Sensitive export field is forbidden: {key}", 403)
                if normalized == "fields":
                    if not isinstance(item, list):
                        raise AppError("VALIDATION_ERROR", "fields must be an array", 400)
                    for field in item:
                        field_name = re.sub(r"[^a-z_]", "", str(field).lower())
                        if any(token in field_name for token in _PROHIBITED_FIELD_TOKENS):
                            raise AppError(
                                "EXPORT_SCOPE_FORBIDDEN",
                                f"Sensitive export field is forbidden: {field}",
                                403,
                            )
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(request)


def _synthetic_demo_snapshot() -> dict[str, list[dict[str, Any]]]:
    def result(task: int, key: str, requested: str, effective: str, findings: int, at: str) -> dict[str, Any]:
        return {
            "taskId": task,
            "projectId": 99001,
            "projectName": "Stage 3A Synthetic Project",
            "profile": "stage3a-synthetic-profile",
            "reviewKey": key,
            "requestedEngine": requested,
            "effectiveEngine": effective,
            "status": "SUCCESS",
            "findingCount": findings,
            "observedAt": at,
            "synthetic": True,
        }

    results = [
        result(990001, "standard-demo-1", "STANDARD", "STANDARD", 2, "2026-07-18T09:00:00"),
        result(990001, "agent-demo-1", "AGENT", "AGENT", 1, "2026-07-18T09:05:00"),
        result(990002, "standard-demo-2", "STANDARD", "STANDARD", 1, "2026-07-18T10:00:00"),
        result(990002, "agent-demo-2", "AGENT", "STANDARD_FALLBACK", 1, "2026-07-18T10:05:00"),
        result(990003, "agent-demo-3", "AGENT", "AGENT", 0, "2026-07-18T11:00:00"),
    ]
    runs = [
        {
            "runId": 991001,
            "taskId": 990001,
            "reviewKey": "agent-demo-1",
            "status": "SUCCEEDED",
            "effectiveEngine": "AGENT",
            "durationMs": 1000,
            "turnCount": 2,
            "toolCallCount": 4,
            "sourceBytesReturned": 1200,
            "diffBytesReturned": 300,
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "synthetic": True,
        },
        {
            "runId": 991002,
            "taskId": 990002,
            "reviewKey": "agent-demo-2",
            "status": "FAILED",
            "effectiveEngine": "STANDARD_FALLBACK",
            "durationMs": 3000,
            "turnCount": 0,
            "toolCallCount": 1,
            "sourceBytesReturned": 0,
            "diffBytesReturned": 400,
            "usage": {},
            "synthetic": True,
        },
        {
            "runId": 991003,
            "taskId": 990003,
            "reviewKey": "agent-demo-3",
            "status": "SUCCEEDED",
            "effectiveEngine": "AGENT",
            "durationMs": 2000,
            "turnCount": 4,
            "toolCallCount": 8,
            "sourceBytesReturned": 2400,
            "diffBytesReturned": 600,
            "usage": {"inputTokens": 200, "outputTokens": 40, "totalTokens": 240},
            "synthetic": True,
        },
    ]
    cases = [
        {"id": 992001, "taskId": 990001, "reviewKey": "standard-demo-1", "fingerprint": "std-1", "verdict": "TRUE_POSITIVE", "synthetic": True},
        {"id": 992002, "taskId": 990001, "reviewKey": "agent-demo-1", "fingerprint": "agent-1", "verdict": "FALSE_POSITIVE", "synthetic": True},
        {"id": 992003, "taskId": 990002, "reviewKey": "standard-demo-2", "fingerprint": "std-2", "verdict": "MISSING_FINDING", "synthetic": True},
        {"id": 992004, "taskId": 990002, "reviewKey": "agent-demo-2", "fingerprint": "agent-2", "verdict": "CONTEXT_MISSING", "synthetic": True},
    ]
    feedback = [
        {"id": 993001, "taskId": 990001, "reviewKey": "agent-demo-1", "fingerprint": "agent-feedback-1", "feedbackType": "USEFUL", "reasonType": "CONTEXT_MISSING", "synthetic": True},
    ]
    return {"results": results, "runs": runs, "cases": cases, "feedback": feedback}


def _filter_synthetic_snapshot(
    snapshot: dict[str, list[dict[str, Any]]],
    filters: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    results = []
    for item in snapshot.get("results") or []:
        if filters["taskId"] is not None and int(item["taskId"]) != filters["taskId"]:
            continue
        if filters["projectId"] is not None and int(item["projectId"]) != filters["projectId"]:
            continue
        if filters["profile"] and str(item.get("profile") or "") != filters["profile"]:
            continue
        observed_at = _parse_datetime(str(item.get("observedAt") or ""), "observedAt")
        if filters["startAtValue"] is not None and observed_at is not None and observed_at < filters["startAtValue"]:
            continue
        if filters["endAtValue"] is not None and observed_at is not None and observed_at > filters["endAtValue"]:
            continue
        results.append(item)
    task_ids = {int(item["taskId"]) for item in results}
    return {
        "results": results,
        "runs": [item for item in snapshot.get("runs") or [] if int(item["taskId"]) in task_ids],
        "cases": [item for item in snapshot.get("cases") or [] if int(item["taskId"]) in task_ids],
        "feedback": [item for item in snapshot.get("feedback") or [] if int(item["taskId"]) in task_ids],
    }


def _public_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "taskId": filters.get("taskId"),
        "projectId": filters.get("projectId"),
        "profile": filters.get("profile"),
        "startAt": filters.get("startAt"),
        "endAt": filters.get("endAt"),
        "syntheticDemo": bool(filters.get("syntheticDemo")),
    }


def _result_engine(item: dict[str, Any]) -> str:
    return "AGENT" if str(item.get("requestedEngine") or "STANDARD").upper() == "AGENT" else "STANDARD"


def _opaque_ref(kind: str, value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    digest = hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total > 0 else 0


def _non_negative(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_snapshot_task_id(value: dict[str, Any]) -> int | None:
    try:
        return int(value.get("taskId")) if value.get("taskId") is not None else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any, field: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError("VALIDATION_ERROR", f"{field} must be an integer", 400) from exc
    if parsed <= 0:
        raise AppError("VALIDATION_ERROR", f"{field} must be positive", 400)
    return parsed


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
