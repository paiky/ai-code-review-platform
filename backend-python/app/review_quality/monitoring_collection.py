from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewRun
from app.code_quality.models import CodeQualityReviewProgressEvent, CodeQualityReviewResult, CodeQualitySchedulerJob
from app.core.json_utils import read_json
from app.release_metadata import normalize_release_sha
from app.review_record.models import ReviewTask


_MAX_REVIEWS = 1_000
_MAX_EVENTS = 25_000
_MAX_FINDINGS = 100
_WIDE_RETRIEVAL_MATCHES = 1_000
_EVENT_LOOKBACK = timedelta(days=1)
_SAVE_MARKER_GRACE = timedelta(seconds=5)
_AGENT_TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT")
_AGENT_TERMINAL_PHASES = ("AGENT_FINISHED", "FAILED", "AGENT_FALLBACK", "AGENT_CANCELLED")
_RESULT_TERMINAL = ("SUCCESS", "SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED", "TIMED_OUT")
_STANDARD_ENGINES = ("STANDARD", "STANDARD_FALLBACK")
_TRIGGER_GROUPS = {
    "GITLAB_MR_WEBHOOK": "MR",
    "GITLAB_PUSH_WEBHOOK": "PUSH",
    "MANUAL": "MANUAL",
    "MANUAL_REVIEW": "MANUAL",
}
_TOOL_PHASES = ("AGENT_TOOL_ACTIVITY", "AGENT_CONVERGING", "AGENT_SUBMITTING", "AGENT_REVIEW_SUBMITTED")
_RUN_PHASES = (
    "AGENT_QUEUED", "AGENT_CONVERSATION_INPUT", "AGENT_CONVERSATION_TURN", "AGENT_ANALYZING",
    *_AGENT_TERMINAL_PHASES, *_TOOL_PHASES,
)
_STANDARD_PHASES = ("CONTEXT_PACK_BUILT", "LOCAL_CONTEXT_RETRIEVED", "LOCAL_CONTEXT_RETRIEVE_FAILED", "RESULT_SAVED", "PROVIDER_FAILED")
_STANDARD_RULE_GAPS = ("UNSUPPORTED_PLANNER_SIGNAL", "UNAVAILABLE_REQUESTED_CONTEXT", "RETRIEVAL_FAILED", "BUDGET_CUT")
_TOOL_NAMES = {"READ_DIFF_RANGE", "READ_FILE_RANGE", "SEARCH_CODE", "SUBMIT_REVIEW", "LIST_FILES"}
_PROVIDER_FAILURES = {
    "AGENT_CUSTOM_AUTH_FAILED": "AUTH_FAILED",
    "AGENT_CUSTOM_MODEL_UNAVAILABLE": "MODEL_UNAVAILABLE",
    "AGENT_CUSTOM_RATE_LIMITED": "RATE_LIMITED",
    "AGENT_CUSTOM_NETWORK_ERROR": "NETWORK_ERROR",
    "AGENT_RESPONSES_PROTOCOL_INVALID": "PROTOCOL_INVALID",
    "AGENT_CHAT_COMPLETIONS_PROTOCOL_INVALID": "PROTOCOL_INVALID",
    "AGENT_ANTHROPIC_MESSAGES_PROTOCOL_INVALID": "PROTOCOL_INVALID",
}
_TOKEN_KEYS = {
    "input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "total_tokens",
    "cache_creation_input_tokens", "cache_read_input_tokens",
}
_SAFE_REVIEW_KEY = re.compile(r"[A-Za-z0-9_.:\-]{1,64}")
_RESULT_ID = re.compile(r"(?:^|,\s*)resultId=([0-9]+)(?:\s*$|,)")


@dataclass(frozen=True)
class _Event:
    id: int
    phase: str
    at: datetime
    data: dict[str, Any]
    result_id: int | None = None


@dataclass(frozen=True)
class _Tool:
    name: str
    status: str | None
    count: int | None
    error: str | None
    event: _Event | None


@dataclass
class _Observation:
    sample: dict[str, Any]
    at: datetime
    release: tuple[str, str | None] | None = None
    values: dict[str, int | None] = field(default_factory=dict)
    issues: list[tuple[str, str, str, str, str, _Event | datetime | None]] = field(default_factory=list)


def collect_monitoring_report(
    db: Session, *, project_id: int, start_at: datetime, end_at: datetime,
) -> dict[str, Any]:
    """Read scoped operational facts and emit only fixed metrics, issue codes and references."""
    with db.no_autoflush:
        return _collect(db, project_id, _utc_naive(start_at), _utc_naive(end_at))


def _collect(db, project_id, start_at, end_at):
    run = AgentReviewRun
    job = CodeQualitySchedulerJob
    result = CodeQualityReviewResult
    runs = db.execute(
        select(
            run.id, run.task_id, run.review_key, run.status, run.effective_engine, run.duration_ms,
            run.started_at, run.finished_at, run.turn_count, run.tool_call_count, run.failure_code, run.usage_json,
            run.tool_summary_json, ReviewTask.trigger_type, job.attempt,
        )
        .join(ReviewTask, ReviewTask.id == run.task_id)
        .outerjoin(job, and_(job.id == run.scheduler_job_id, job.task_id == run.task_id))
        .where(ReviewTask.project_id == project_id, run.status.in_(_AGENT_TERMINAL),
               run.finished_at >= start_at, run.finished_at < end_at)
        .order_by(run.finished_at.desc(), run.id.desc()).limit(_MAX_REVIEWS + 1)
    ).all()
    results = db.execute(
        select(
            result.id, result.task_id, result.review_key, result.status, result.effective_engine,
            result.agent_run_id, result.finding_count, result.findings_json, result.started_at,
            result.finished_at, result.updated_at,
        )
        .join(ReviewTask, ReviewTask.id == result.task_id)
        .where(result.project_id == project_id, ReviewTask.project_id == project_id,
               result.status.in_(_RESULT_TERMINAL), result.finished_at >= start_at, result.finished_at < end_at)
        .order_by(result.finished_at.desc(), result.id.desc()).limit(_MAX_REVIEWS + 1)
    ).all()
    truncated = len(runs) > _MAX_REVIEWS or len(results) > _MAX_REVIEWS
    runs, results = runs[:_MAX_REVIEWS], results[:_MAX_REVIEWS]
    target_keys = {(row.task_id, row.review_key) for row in (*runs, *results)}
    task_ids = {item[0] for item in target_keys}
    events_by_target, events_truncated = _load_events(db, task_ids, target_keys, start_at, end_at)
    if events_truncated:
        # Missing events in a capped scan may otherwise appear to be an authoritative zero.
        events_by_target.clear()
    run_ids = [row.id for row in runs]
    selected_by_id = {
        row.agent_run_id: row for row in db.execute(
            select(result.task_id, result.review_key, result.status, result.effective_engine,
                   result.agent_run_id, result.finding_count, result.finished_at)
            .where(result.project_id == project_id, result.agent_run_id.in_(run_ids))
        )
    } if run_ids else {}
    agent: dict[str, list[_Observation]] = defaultdict(list)
    for row in runs:
        selected = selected_by_id.get(row.id)
        target = (row.task_id, row.review_key)
        if selected is not None and (selected.task_id, selected.review_key) != target:
            selected = None
        agent[_TRIGGER_GROUPS.get(row.trigger_type, "OTHER")].append(
            _agent_observation(row, selected, events_by_target.get(target, ()))
        )
    standard = [
        _standard_observation(row, events_by_target.get((row.task_id, row.review_key), ()))
        for row in results if row.effective_engine in _STANDARD_ENGINES
    ]
    findings = _finding_observations(results, agent, standard)

    metrics = []
    for group in ("MR", "PUSH", "MANUAL", "OTHER"):
        rows = agent.get(group, ())
        metrics.extend(_metrics("AGENT", group, rows, _AGENT_METRICS))
        empty = sum(row.values["emptyDiffReads"] or 0 for row in rows)
        known = sum(row.values["measuredSuccessfulDiffReads"] or 0 for row in rows)
        successful = sum(row.values["successfulDiffReads"] or 0 for row in rows)
        metrics.append(_metric("AGENT", group, "EMPTY_DIFF_READ_RATE", "成功 Diff 调用空读率",
                               successful, known, empty / known if known else None, "RATIO"))
    metrics.extend(_metrics("STANDARD", "STANDARD", standard, _STANDARD_METRICS))
    for engine in ("AGENT", "STANDARD"):
        specs = _FINDING_METRICS if engine == "AGENT" else _FINDING_METRICS[:1]
        metrics.extend(_metrics(engine, None, findings.get(engine, ()), specs))
    groups = [("AGENT", row) for rows in agent.values() for row in rows]
    groups.extend(("STANDARD", row) for row in standard)
    groups.extend((engine, row) for engine, rows in findings.items() for row in rows)
    scan_truncated = truncated or events_truncated
    agent_rows = [row for rows in agent.values() for row in rows]
    agent_cohort_by_run = {row.sample["runId"]: row.release for row in agent_rows}
    # Finding metrics use formal-result time, which can differ from terminal Run time at a window boundary.
    agent_cohort = list(agent_cohort_by_run.values()) + [
        None for row in findings.get("AGENT", ()) if row.sample.get("runId") not in agent_cohort_by_run
    ]
    return {
        "metrics": metrics,
        "issues": _issues(groups),
        "truncated": scan_truncated,
        "releaseCohorts": [
            _release_cohort("AGENT", agent_cohort, scan_truncated),
            _release_cohort("STANDARD", [row.release for row in standard], scan_truncated),
        ],
    }


def _release_cohort(engine, rows, truncated):
    counts = Counter(release for release in rows if release is not None)
    known = sum(counts.values())
    status = "UNKNOWN"
    if not truncated and rows and known == len(rows):
        status = "KNOWN" if len(counts) == 1 else "MIXED"
    return {
        "engine": engine, "eligibleCount": len(rows), "observedCount": known, "status": status,
        "releases": [
            {"backendRelease": backend, "workerRelease": worker, "count": count}
            for (backend, worker), count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
        ],
    }


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _load_events(db, task_ids, target_keys, start_at, end_at):
    by_target = defaultdict(list)
    if not task_ids:
        return by_target, False
    event = CodeQualityReviewProgressEvent
    records = db.execute(
        select(event.id, event.task_id, event.review_key, event.phase, event.detail, event.created_at)
        .where(event.task_id.in_(task_ids), event.phase.in_((*_RUN_PHASES, *_STANDARD_PHASES)),
               event.created_at >= start_at - _EVENT_LOOKBACK, event.created_at < end_at + _SAVE_MARKER_GRACE)
        .order_by(event.id.desc()).limit(_MAX_EVENTS + 1)
    ).all()
    if len(records) > _MAX_EVENTS:
        return by_target, True
    for row in reversed(records):
        target = (row.task_id, row.review_key or "default")
        if target not in target_keys:
            continue
        marker = _RESULT_ID.search(row.detail or "") if row.phase == "RESULT_SAVED" else None
        by_target[target].append(_Event(row.id, row.phase, row.created_at, _object(row.detail),
                                        int(marker.group(1)) if marker else None))
    return by_target, False


def _agent_observation(row, selected, events) -> _Observation:
    sample = _sample(row.task_id, row.review_key, row.id)
    observation = _Observation(sample, row.finished_at)
    matching = [event for event in events if _integer(event.data.get("runId")) == row.id]
    attempts = {_integer(event.data.get("claimAttempt")) for event in matching} - {None, 0}
    terminal_attempts = {
        _integer(event.data.get("claimAttempt")) for event in matching if event.phase in _AGENT_TERMINAL_PHASES
    } - {None, 0}
    recorded_terminal = next(iter(terminal_attempts)) if len(terminal_attempts) == 1 else None
    attempt = row.attempt or recorded_terminal or (next(iter(attempts)) if len(attempts) == 1 else None)
    active = [event for event in matching if attempt and _integer(event.data.get("claimAttempt")) == attempt]
    queued = next((event.data for event in matching if event.phase == "AGENT_QUEUED"), {})
    first_input = next((event.data for event in active if event.phase == "AGENT_CONVERSATION_INPUT"), {})
    terminal_events = [event for event in active if event.phase in _AGENT_TERMINAL_PHASES]
    if len(terminal_events) == 1:
        queued_release = normalize_release_sha(queued.get("backendReleaseSha"))
        terminal = terminal_events[0].data
        worker_release = normalize_release_sha(terminal.get("workerReleaseSha"))
        if (
            queued_release and worker_release
            and queued_release == normalize_release_sha(terminal.get("backendReleaseSha"))
            and attempt == 1
        ):
            observation.release = queued_release, worker_release
    tools, complete = _agent_tools(row, active, bool(attempt and (row.attempt or recorded_terminal)))
    diff = [tool for tool in tools if tool.name == "READ_DIFF_RANGE"]
    successful = [tool for tool in diff if tool.status == "SUCCESS"]
    measured = [tool for tool in successful if tool.count is not None]
    empty = [tool for tool in measured if tool.count == 0]
    missing = [tool for tool in diff if tool.status == "FAILED" and tool.error == "DIFF_CONTENT_UNAVAILABLE"]
    outside = [tool for tool in diff if tool.status == "FAILED" and tool.error == "DIFF_RANGE_OUT_OF_BOUNDS"]
    other_failure = [tool for tool in diff if tool.status == "FAILED" and tool.error and tool not in missing and tool not in outside]
    reason_unknown = [tool for tool in diff if (tool.status == "FAILED" and not tool.error) or (tool in empty and not tool.error)]
    measured_all = complete and len(measured) == len(successful) and all(tool.status for tool in diff)
    first_error = next((index for index, tool in enumerate(tools) if tool in empty or tool in missing or tool in outside), None)
    recovery = int(any(
        tool.status == "SUCCESS" and tool.count and tool.name in ("READ_FILE_RANGE", "SEARCH_CODE")
        for tool in tools[first_error + 1:]
    )) if first_error is not None else None
    if recovery == 0 and not complete:
        recovery = None
    turns = {
        number: event for event in reversed(active)
        if event.phase == "AGENT_CONVERSATION_TURN" and (number := _integer(event.data.get("turn")))
    }
    stall_turns = [_integer(event.data.get("consecutiveNoNewEvidenceTurns")) for event in turns.values()
                   if event.data.get("evidenceStatus") == "MEASURED"]
    usable_stalls = [value for value in stall_turns if value is not None]
    has_turn_usage = any(_has_usage(event.data.get("usage")) for event in turns.values())
    finding_count = selected.finding_count if selected and selected.effective_engine == "AGENT" and selected.status in ("SUCCESS", "SUCCEEDED") else None
    submitted = next((tool for tool in reversed(tools) if tool.name == "SUBMIT_REVIEW" and tool.status == "SUCCESS"), None)
    if finding_count is None and submitted:
        finding_count = submitted.count
    diff_mode = first_input.get("diffMode", queued.get("diffMode"))
    observation.values = {
        "diffVerified": int(bool(diff)) if diff or complete else None,
        "diffNotInvoked": int(not diff) if diff or complete else None,
        "diffKnownOutcomes": sum(bool(tool.status == "FAILED" or tool.status == "SUCCESS" and tool.count is not None) for tool in diff) if diff or complete else None,
        "nonemptyDiffReadCount": len(measured) - len(empty) if measured or measured_all else None,
        "emptyDiffReads": len(empty) if measured or measured_all else None,
        "measuredSuccessfulDiffReads": len(measured),
        "successfulDiffReads": len(successful),
        "diffReturnedLines": sum(tool.count for tool in measured) if measured or measured_all else None,
        "diffMissingCount": len(missing) if missing or complete else None,
        "diffOutsideCount": len(outside) if outside or complete else None,
        "diffOtherFailureCount": len(other_failure) if other_failure or complete else None,
        "diffUnknownReasonCount": len(reason_unknown) if reason_unknown or measured_all else None,
        "recovery": recovery,
        "maxStallTurns": max(usable_stalls) if usable_stalls else None,
        "queuedDiffBytes": _integer(queued.get("diffBytes")),
        "firstRequestBytes": _integer(first_input.get("requestBytes")),
        "pagedInput": int(diff_mode == "TOOL_PAGED") if diff_mode in ("INLINE", "TOOL_PAGED") else None,
        "duration": _integer(row.duration_ms),
        "success": int(row.status == "SUCCEEDED"),
        "fallback": int(row.effective_engine == "STANDARD_FALLBACK") if row.effective_engine in ("AGENT", "STANDARD_FALLBACK") else None,
        "formal": int(bool(selected and selected.finished_at and selected.status in _RESULT_TERMINAL)),
        "findingCount": finding_count,
        "turnSummaryZero": int(row.turn_count == 0),
        "usageSummaryMissing": int(not _has_usage(row.usage_json)),
        "turnUsageVisible": int(has_turn_usage) if turns else None,
        "turnSummaryMismatch": int(row.turn_count < max(turns)) if turns else None,
        "usageSummaryMismatch": int(not _has_usage(row.usage_json)) if has_turn_usage else None,
        "knownProviderFailure": 1 if row.failure_code in _PROVIDER_FAILURES else None,
    }
    # Audit-only tool records have no clock. A Run start is a conservative lower bound for recurrence.
    first_input_event = next((event for event in active if event.phase == "AGENT_CONVERSATION_INPUT"), None)
    run_lower_bound = first_input_event.at if first_input_event else row.started_at
    terminal_event = terminal_events[-1] if terminal_events else None
    for tool in empty:
        observation.issues.append(("DIFF_READ", "EMPTY_SUCCESS", "Diff 读取返回空内容", "HIGH", "emptyDiffReads", tool.event or run_lower_bound))
    for tool in missing:
        observation.issues.append(("DIFF_READ", "PATCH_UNAVAILABLE", "Diff 分页缺少可读 patch", "HIGH", "diffMissingCount", tool.event or run_lower_bound))
    for tool in outside:
        observation.issues.append(("DIFF_READ", "OUT_OF_BOUNDS", "Diff 分页范围越界", "MEDIUM", "diffOutsideCount", tool.event or run_lower_bound))
    for tool in other_failure:
        observation.issues.append(("DIFF_READ", "OTHER_FAILURE", "Diff 工具执行失败", "LOW", "diffOtherFailureCount", tool.event or run_lower_bound))
    if row.failure_code in _PROVIDER_FAILURES:
        observation.issues.append(("PROVIDER_FAILURE", _PROVIDER_FAILURES[row.failure_code], "Agent 模型调用记录到失败", "MEDIUM", "knownProviderFailure", terminal_event))
    if observation.values["turnSummaryMismatch"] or observation.values["usageSummaryMismatch"]:
        observation.issues.append(("RUN_SUMMARY_MISMATCH", "TURN_OR_USAGE", "Agent Run 汇总遗漏轮次或用量", "MEDIUM", "turnSummaryMismatch", None))
    return observation


def _agent_tools(row, active, verified_attempt: bool) -> tuple[list[_Tool], bool]:
    tools = {}
    for event in active:
        name = event.data.get("activity")
        sequence = _integer(event.data.get("sequence"))
        if not sequence or name not in _TOOL_NAMES or event.phase not in _TOOL_PHASES:
            continue
        if event.data.get("status") == "STARTED":
            continue
        tools.setdefault(sequence, _tool(name, event.data, event))
    audit = _object(row.tool_summary_json)
    audit_events = audit.get("events")
    if verified_attempt and isinstance(audit_events, list):
        # The persisted Run summary is from the terminal attempt. Exact sequence matches belong to one call.
        for item in audit_events:
            if not isinstance(item, dict) or not isinstance(item.get("tool"), str):
                continue
            sequence, name = _integer(item.get("sequence")), item["tool"].upper()
            if sequence and name in _TOOL_NAMES:
                tools.setdefault(sequence, _tool(name, item, None))
    audit_total = _integer(audit.get("toolCallCount"))
    complete = bool(verified_attempt and isinstance(audit_events, list) and audit_total == row.tool_call_count == len(tools))
    return [tools[key] for key in sorted(tools)], complete


def _tool(name, data, event) -> _Tool:
    status = data.get("status")
    code = data.get("errorCode")
    return _Tool(name, status if status in ("SUCCESS", "FAILED") else None,
                 _integer(data.get("itemCount")), code if isinstance(code, str) and code else None, event)


def _standard_observation(row, events) -> _Observation:
    observation = _Observation(_sample(row.task_id, row.review_key), row.finished_at)
    pack, lookup, provider_failed = _standard_events(row, events)
    detail = pack.data if pack else {}
    if backend_release := normalize_release_sha(detail.get("backendReleaseSha")):
        observation.release = backend_release, None
    meta, summary = _object(detail.get("meta")), _object(detail.get("summary"))
    budget = _object(summary.get("budgetCutSummary"))
    local = _object(summary.get("localReferenceSearch"))
    retrieval = lookup.data if lookup else {}
    queries = _number(retrieval.get("queryCount"), local.get("queryCount"), meta.get("localReferenceQueryCount"))
    matched = _number(retrieval.get("matchedFileCount"), local.get("matchedFileCount"), meta.get("localReferenceMatchedFileCount"))
    candidates = _number(retrieval.get("evidenceCandidateCount"), local.get("evidenceCandidateCount"))
    included = _number(meta.get("localReferenceSnippetCount"), local.get("includedSnippetCount"), retrieval.get("includedSnippetCount"))
    prompt_size = _number(meta.get("promptLength"), summary.get("promptLength"), budget.get("promptLength"))
    target = _number(meta.get("maxTotalChars"), budget.get("maxTotalChars"))
    gap_items = summary.get("ruleGapItems")
    gap_types = {item.get("gapType") for item in gap_items if isinstance(item, dict) and isinstance(item.get("gapType"), str)} if isinstance(gap_items, list) else set()
    gap_breakdown = _object(summary.get("ruleGapSummary")).get("byGapType")
    if isinstance(gap_breakdown, list):
        gap_types.update(item["gapType"] for item in gap_breakdown
                         if isinstance(item, dict) and isinstance(item.get("gapType"), str) and (_integer(item.get("count")) or 0) > 0)
    budget_cut = int(any((_integer(value) or 0) > 0 for key, value in budget.items() if "Removed" in key or "Excluded" in key)) if budget else None
    if "BUDGET_CUT" in gap_types:
        budget_cut = 1
    observation.values = {
        "queries": queries,
        "matches": matched,
        "candidates": candidates,
        "included": included,
        "zeroMatches": int(matched == 0) if queries and matched is not None else None,
        "zeroIncluded": int(included == 0) if queries and included is not None else None,
        "candidatesNotIncluded": int(candidates > 0 and included == 0) if candidates is not None and included is not None else None,
        "wideNoCandidates": int(matched >= _WIDE_RETRIEVAL_MATCHES and candidates == 0) if matched is not None and candidates is not None else None,
        "contextChars": prompt_size,
        "targetChars": target,
        "overTarget": int(prompt_size > target) if prompt_size is not None and target is not None else None,
        "budgetCut": budget_cut,
        "ruleGapCount": len(gap_types.intersection(_STANDARD_RULE_GAPS)) if isinstance(gap_items, list) or isinstance(gap_breakdown, list) else None,
        "plannerSignals": _number(meta.get("plannerSignalCount"), summary.get("plannerSignalCount")),
        "success": int(row.status in ("SUCCESS", "SUCCEEDED")),
        "fallback": int(row.effective_engine == "STANDARD_FALLBACK"),
        "knownProviderFailure": 1 if provider_failed else None,
    }
    for field_name, issue_type, diagnostic_type, title, priority, event in (
        ("wideNoCandidates", "CONTEXT_RETRIEVAL", "WIDE_WITHOUT_CANDIDATES", "检索命中范围过宽且未形成证据候选", "HIGH", lookup or pack),
        ("zeroMatches", "CONTEXT_RETRIEVAL", "NO_MATCHES", "已触发的上下文检索未命中文件", "LOW", lookup or pack),
        ("zeroIncluded", "CONTEXT_RETRIEVAL", "NO_RETAINED_SNIPPETS", "已执行上下文检索但未保留引用片段", "MEDIUM", lookup or pack),
        ("candidatesNotIncluded", "CONTEXT_RETRIEVAL", "CANDIDATES_DROPPED", "上下文检索候选未保留", "HIGH", pack or lookup),
        ("overTarget", "CONTEXT_BUDGET", "OVER_TARGET", "Context Pack 超过裁剪目标", "MEDIUM", pack),
        ("budgetCut", "CONTEXT_BUDGET", "CANDIDATES_TRIMMED", "Context Pack 因预算移除候选内容", "LOW", pack),
        ("knownProviderFailure", "PROVIDER_FAILURE", "STANDARD_ERROR", "Standard Provider 执行记录到失败", "MEDIUM", provider_failed),
    ):
        if observation.values[field_name]:
            observation.issues.append((issue_type, diagnostic_type, title, priority, field_name, event))
    return observation


def _standard_events(row, events) -> tuple[_Event | None, _Event | None, _Event | None]:
    # Provider start is recorded after the pack is built. Anchor on the matching save event or an unambiguous legacy pack.
    before = [event for event in events if event.at <= (row.updated_at or row.finished_at) + _SAVE_MARKER_GRACE]
    markers = [event for event in before if event.result_id == row.id and event.at >= row.finished_at]
    if len(markers) == 1:
        marker = markers[0]
        previous = max((event.id for event in before if event.phase == "RESULT_SAVED" and event.id < marker.id), default=0)
        candidates = [event for event in before if previous < event.id < marker.id]
    elif not markers and not any(event.phase == "RESULT_SAVED" for event in before):
        candidates = [event for event in before if event.at <= row.finished_at]
    else:
        return None, None, None
    packs = [event for event in candidates if event.phase == "CONTEXT_PACK_BUILT"]
    if len(packs) != 1 or row.started_at is None or not row.started_at - _EVENT_LOOKBACK <= packs[0].at <= row.started_at:
        if len(markers) == 1 and not packs:
            failures = [event for event in candidates if event.phase == "PROVIDER_FAILED"]
            return None, None, failures[0] if len(failures) == 1 else None
        return None, None, None
    pack = packs[0]
    lookup = next((event for event in candidates if event.id > pack.id and event.phase in ("LOCAL_CONTEXT_RETRIEVED", "LOCAL_CONTEXT_RETRIEVE_FAILED")), None)
    failed = next((event for event in candidates if event.id > pack.id and event.phase == "PROVIDER_FAILED"), None)
    return pack, lookup, failed


def _finding_observations(results, agent, standard) -> dict[str, list[_Observation]]:
    reviewed = defaultdict(list)
    agent_by_run = {row.sample["runId"]: row for group in agent.values() for row in group}
    standard_by_review = {(row.sample["taskId"], row.sample.get("reviewKey")): row for row in standard}
    previous_agent_findings = {}
    for run in sorted(agent_by_run.values(), key=lambda item: (item.at, item.sample["runId"])):
        if "reviewKey" not in run.sample or run.values["success"] != 1:
            continue
        target = (run.sample["taskId"], run.sample["reviewKey"])
        prior = previous_agent_findings.get(target)
        previous_agent_findings[target] = run.values["findingCount"]
        if prior is not None and run.values["findingCount"] is not None:
            run.values["zeroAfterPositive"] = int(prior > 0 and run.values["findingCount"] == 0)
    for row in results:
        if row.status not in ("SUCCESS", "SUCCEEDED"):
            continue
        engine = "AGENT" if row.effective_engine == "AGENT" else "STANDARD"
        sample = _sample(row.task_id, row.review_key, row.agent_run_id if engine == "AGENT" else None)
        observed = _Observation(sample, row.finished_at)
        source = agent_by_run.get(row.agent_run_id) if engine == "AGENT" else standard_by_review.get((row.task_id, sample.get("reviewKey")))
        findings = read_json(row.findings_json, []) if len(row.findings_json or "") <= 1_048_576 else None
        has_diagnostic = source and any(item[0] in ("DIFF_READ", "CONTEXT_RETRIEVAL", "CONTEXT_BUDGET") for item in source.issues)
        if row.finding_count == 0 and has_diagnostic:
            observed.issues.append(("FINDING_REVIEW", "ZERO_WITH_DIAGNOSTIC", "零 Finding 结果存在取证或监测异常，待复核", "LOW", "zeroWithDiagnostic", None))
        observed.values["zeroWithDiagnostic"] = int(bool(observed.issues)) if source else None
        if engine == "AGENT":
            observed.values["zeroAfterPositive"] = source.values.get("zeroAfterPositive") if source else None
            if observed.values["zeroAfterPositive"]:
                observed.issues.append(("FINDING_REVIEW", "FELL_TO_ZERO", "同一审查目标的 Finding 数降为零，待复核", "LOW", "zeroAfterPositive", None))
        high_partial = 0
        known_count = 0
        for finding in findings[:min(row.finding_count, _MAX_FINDINGS)] if isinstance(findings, list) else ():
            if not isinstance(finding, dict):
                continue
            severity = finding.get("severity")
            context = finding.get("contextStatus") or finding.get("context_status")
            confidence = finding.get("confidence")
            if severity in ("MINOR", "MAJOR", "CRITICAL", "HIGH", "BLOCKER") and context in ("PARTIAL", "UNKNOWN", "SUFFICIENT", "INSUFFICIENT") and confidence in ("HIGH", "MEDIUM", "LOW"):
                known_count += 1
                if severity != "MINOR" and context == "PARTIAL" and confidence == "HIGH":
                    high_partial += 1
                    observed.issues.append(("FINDING_REVIEW", "HIGH_CONFIDENCE_PARTIAL", "高风险 Finding 证据部分缺失，待复核", "MEDIUM", "highPartial", None))
        observed.values["findingEligible"] = row.finding_count
        observed.values["findingMeasured"] = known_count
        observed.values["highPartial"] = high_partial if known_count else None
        reviewed[engine].append(observed)
    return reviewed


_AGENT_METRICS = (
    ("DIFF_PAGED_RUNS", "有 Diff 分页记录的 Run", "diffVerified", "COUNT"),
    ("DIFF_NOT_INVOKED_RUNS", "未记录 Diff 分页调用的完整 Run", "diffNotInvoked", "COUNT"),
    ("DIFF_KNOWN_OUTCOMES", "结果已知的 Diff 分页调用", "diffKnownOutcomes", "COUNT"),
    ("DIFF_NONEMPTY_READS", "实际返回内容的 Diff 调用", "nonemptyDiffReadCount", "COUNT"),
    ("DIFF_RETURNED_LINES", "Diff 分页返回行数", "diffReturnedLines", "ROWS"),
    ("DIFF_UNAVAILABLE", "Diff patch 缺失调用", "diffMissingCount", "COUNT"),
    ("DIFF_OUT_OF_BOUNDS", "Diff 分页越界调用", "diffOutsideCount", "COUNT"),
    ("DIFF_OTHER_FAILURE", "其他 Diff 读取失败", "diffOtherFailureCount", "COUNT"),
    ("DIFF_UNKNOWN_REASON", "原因未知的 Diff 空读或失败调用", "diffUnknownReasonCount", "COUNT"),
    ("DIFF_RECOVERY", "Diff 异常后有源码或搜索补证的 Run", "recovery", "COUNT"),
    ("MAX_STALL_TURNS_AVERAGE", "平均最长连续无新增证据轮数", "maxStallTurns", "COUNT", True),
    ("QUEUED_DIFF_BYTES_AVERAGE", "平均入队 Diff 字节", "queuedDiffBytes", "BYTES", True),
    ("FIRST_REQUEST_BYTES_AVERAGE", "平均首轮请求字节", "firstRequestBytes", "BYTES", True),
    ("PAGED_INPUT_RUNS", "按需分页输入 Run", "pagedInput", "COUNT"),
    ("RUN_DURATION_AVERAGE", "平均 Run 耗时", "duration", "MS", True),
    ("SUCCESS_RUNS", "成功 Run", "success", "COUNT"),
    ("FALLBACK_RUNS", "降级 Run", "fallback", "COUNT"),
    ("FORMAL_RESULT_RUNS", "当前正式结果指向的 Run", "formal", "COUNT"),
    ("REPORTED_FINDINGS", "可观测的 Finding 数", "findingCount", "COUNT"),
    ("ZERO_TURN_SUMMARIES", "终态汇总为零轮次的 Run", "turnSummaryZero", "COUNT"),
    ("MISSING_USAGE_SUMMARIES", "缺少用量汇总的 Run", "usageSummaryMissing", "COUNT"),
    ("TURN_USAGE_RECORDED", "轮次事件包含用量的 Run", "turnUsageVisible", "COUNT"),
    ("TURN_SUMMARY_MISMATCH", "轮次汇总少于实际已记录轮次的 Run", "turnSummaryMismatch", "COUNT"),
    ("USAGE_SUMMARY_MISMATCH", "轮次含用量但汇总缺失的 Run", "usageSummaryMismatch", "COUNT"),
    ("KNOWN_PROVIDER_FAILURES", "可归因的模型调用失败 Run", "knownProviderFailure", "COUNT"),
    ("DIFF_PATCH_COVERAGE", "可读文本 patch 覆盖率", "patchCoverage", "RATIO"),
)
_STANDARD_METRICS = (
    ("CONTEXT_QUERIES", "上下文查询数", "queries", "COUNT"),
    ("CONTEXT_MATCHED_FILES", "上下文查询匹配文件数", "matches", "COUNT"),
    ("CONTEXT_CANDIDATES", "上下文证据候选数", "candidates", "COUNT"),
    ("CONTEXT_RETAINED_SNIPPETS", "上下文保留片段数", "included", "COUNT"),
    ("CONTEXT_ZERO_MATCHES", "已查询但零文件命中", "zeroMatches", "COUNT"),
    ("CONTEXT_ZERO_RETAINED", "已查询但零保留", "zeroIncluded", "COUNT"),
    ("CONTEXT_CANDIDATES_DROPPED", "有候选但零保留", "candidatesNotIncluded", "COUNT"),
    ("CONTEXT_WIDE_NO_CANDIDATES", "宽匹配且零证据候选", "wideNoCandidates", "COUNT"),
    ("CONTEXT_CHARS_AVERAGE", "平均 Context Pack 字符数", "contextChars", "CHARS", True),
    ("CONTEXT_TARGET_CHARS_AVERAGE", "平均 Context Pack 目标字符数", "targetChars", "CHARS", True),
    ("CONTEXT_OVER_TARGET", "超过 Context Pack 裁剪目标的记录数", "overTarget", "COUNT"),
    ("CONTEXT_BUDGET_CUT", "有预算裁剪证据的记录数", "budgetCut", "COUNT"),
    ("CONTEXT_RULE_GAP_TYPES", "上下文规则缺口类型数", "ruleGapCount", "COUNT"),
    ("PLANNER_SIGNALS", "Planner 信号数", "plannerSignals", "COUNT"),
    ("SUCCESS_RESULTS", "成功结果", "success", "COUNT"),
    ("FALLBACK_RESULTS", "Standard 降级结果", "fallback", "COUNT"),
    ("KNOWN_PROVIDER_FAILURES", "可归因的 Provider 执行失败", "knownProviderFailure", "COUNT"),
)
_FINDING_METRICS = (
    ("FINDING_ZERO_WITH_DIAGNOSTIC", "有诊断线索的零 Finding 结果", "zeroWithDiagnostic", "COUNT"),
    ("FINDING_FELL_TO_ZERO", "同一审查目标有可配对记录且 Finding 数降为零", "zeroAfterPositive", "COUNT"),
)


def _metrics(engine, group, rows, specs):
    for key, label, field_name, unit, *average in specs:
        values = [row.values[field_name] for row in rows if row.values.get(field_name) is not None]
        value = (round(sum(values) / len(values), 2) if average else sum(values)) if values else None
        yield _metric(engine, group, key, label, len(rows), len(values), value, unit)
    if group is None:
        eligible = sum(row.values["findingEligible"] for row in rows)
        known = sum(row.values["findingMeasured"] for row in rows)
        high_partial = sum(row.values["highPartial"] or 0 for row in rows)
        yield _metric(engine, group, "FINDING_HIGH_CONFIDENCE_PARTIAL", "高风险、高置信、证据部分缺失的 Finding",
                      eligible, known, high_partial if known or not eligible else None, "COUNT")


def _metric(engine, group, key, label, eligible, observed, value, unit):
    return {
        "engine": engine, "group": group, "key": key, "label": label,
        "eligibleCount": eligible, "observedCount": observed,
        "unknownCount": max(0, eligible - observed), "value": value, "unit": unit,
    }


def _issues(groups):
    grouped = {}
    measured_tasks = defaultdict(set)
    for engine, row in groups:
        for key, value in row.values.items():
            if value is not None:
                measured_tasks[engine, key].add(row.sample["taskId"])
        for issue_type, diagnostic, title, priority, coverage_key, event in row.issues:
            key = (engine, issue_type, diagnostic)
            group = grouped.setdefault(key, {"title": title, "priority": priority, "coverage": coverage_key, "observations": []})
            sample = row.sample.copy()
            if isinstance(event, _Event):
                sample["eventId"] = event.id
            occurred_at = event.at if isinstance(event, _Event) else (event or row.at)
            group["observations"].append((occurred_at, sample))
    issues = []
    for (engine, issue_type, diagnostic), group in grouped.items():
        observations = sorted(group["observations"], key=lambda item: (item[0], item[1]["taskId"]), reverse=True)
        samples = []
        for _, sample in observations:
            if sample not in samples and len(samples) < 10:
                samples.append(sample)
        issues.append({
            "engine": engine, "issueType": issue_type, "diagnosticType": diagnostic,
            "title": group["title"], "priority": group["priority"], "eventCount": len(observations),
            "affectedTaskCount": len({sample["taskId"] for _, sample in observations}),
            "observedCount": len(measured_tasks[engine, group["coverage"]]), "firstSeenAt": observations[-1][0],
            "lastSeenAt": observations[0][0], "samples": samples,
        })
    return sorted(issues, key=lambda item: (item["priority"] != "HIGH", item["priority"] == "LOW", -item["affectedTaskCount"], item["engine"], item["issueType"], item["diagnosticType"]))


def _sample(task_id, review_key, run_id=None):
    result = {"taskId": task_id}
    if isinstance(review_key, str) and _SAFE_REVIEW_KEY.fullmatch(review_key):
        result["reviewKey"] = review_key
    if run_id is not None:
        result["runId"] = run_id
    return result


def _object(raw):
    value = read_json(raw, {})
    return value if isinstance(value, dict) else {}


def _integer(value):
    return value if type(value) is int and value >= 0 else None


def _number(*values):
    return next((value for value in values if _integer(value) is not None), None)


def _has_usage(raw):
    return any(key in _TOKEN_KEYS and _integer(value) is not None for key, value in _object(raw).items())
