import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.command_center.repository import (
    FINDING_SCAN_LIMIT,
    LANE_RUNNING_ITEM_LIMIT,
    WORKER_LIMIT,
    GovernanceProjectionData,
    RuntimeProjectionData,
    load_governance_projection,
    load_runtime_projection,
)
from app.command_center.schemas import (
    AcceptanceSnapshot,
    ActiveFlowSnapshot,
    ActiveTaskSnapshot,
    AgentQueueSnapshot,
    AgentSnapshot,
    AlertSnapshot,
    ContextQualitySnapshot,
    EvaluationSnapshot,
    FeedbackSnapshot,
    FindingRiskSnapshot,
    FlowEngineSnapshot,
    GovernanceSnapshot,
    IntakeSnapshot,
    NotificationGovernanceSnapshot,
    PolicySnapshot,
    PreflightSnapshot,
    ProviderSnapshot,
    ReviewLaneItemSnapshot,
    ReviewLanesSnapshot,
    ReviewLaneSnapshot,
    RuleAnalysisSnapshot,
    RuntimeSnapshot,
    SampleGateSnapshot,
    SchedulerSnapshot,
    SnapshotCoverage,
    SnapshotWindow,
    TodayResultsSnapshot,
    WorkerPoolSnapshot,
    WorkerSnapshot,
)
from app.code_quality.scheduler_config import PROVIDER_SCHEDULER_CAPACITY


RUNTIME_COVERAGE = {
    "intake": "FULL",
    "activeTasks": "BOUNDED",
    "activeFlows": "BOUNDED",
    "scheduler": "FULL",
    "standard": "BOUNDED",
    "agent": "BOUNDED",
    "reviewLanes": "BOUNDED",
    "providersObserved": "FULL",
    "alerts": "BOUNDED",
    "todayResults": "FULL",
}

GOVERNANCE_COVERAGE = {
    "ruleAnalysis": "FULL",
    "preflight": "BOUNDED",
    "contextQuality": "BOUNDED",
    "findingRisk": "BOUNDED",
    "notifications": "FULL",
    "feedback": "FULL",
    "evaluation": "FULL",
    "policies": "FULL",
}

DEFAULT_REVIEW_KEY = "default"
DISPATCH_PROGRESS_SCHEMA_VERSION = "agent-dispatch-progress-v1"
DISPATCH_PROGRESS_OPERATION = "AGENT_ENQUEUE"
DISPATCH_PROGRESS_ENGINE = "AGENT"
DISPATCH_PROGRESS_STATUSES = frozenset({"STARTED", "COMPLETED", "FAILED"})
REVIEW_KEY_MAX_LENGTH = 64
DISPATCH_PROGRESS_PHASES = frozenset(
    {
        "LOCAL_REPO_PREPARE_STARTED",
        "LOCAL_REPO_PREPARED",
        "LOCAL_REPO_PREPARE_FAILED",
        "PROJECT_POLICY_BUILD_STARTED",
        "PROJECT_POLICY_BUILD_COMPLETED",
        "PROJECT_POLICY_BUILD_FAILED",
        "AGENT_INPUT_BUILD_STARTED",
        "AGENT_INPUT_BUILD_COMPLETED",
        "AGENT_INPUT_BUILD_FAILED",
        "AGENT_JOB_CREATE_STARTED",
        "AGENT_JOB_CREATE_COMPLETED",
        "AGENT_JOB_CREATE_FAILED",
        "AGENT_QUEUED",
    }
)
DISPATCH_PROGRESS_FAILED_PHASES = frozenset(
    {
        "LOCAL_REPO_PREPARE_FAILED",
        "PROJECT_POLICY_BUILD_FAILED",
        "AGENT_INPUT_BUILD_FAILED",
        "AGENT_JOB_CREATE_FAILED",
    }
)
DISPATCH_PROGRESS_CONTEXT_PHASES = DISPATCH_PROGRESS_PHASES - (
    DISPATCH_PROGRESS_FAILED_PHASES | {"AGENT_QUEUED"}
)
WORKER_HEARTBEAT_SECONDS = 60
SAMPLE_GATE_REQUIRED = 30
FAILED_STATUSES = {"FAILED", "TIMED_OUT"}
SKIPPED_STATUSES = {"SKIPPED", "CANCELLED"}
RUNNING_STATUSES = {"RUNNING", "PENDING", "CLAIMED"}
TODAY_RUNNING_STATUSES = {"QUEUED", "PENDING", "CLAIMED", "RUNNING"}
TODAY_SKIPPED_STATUSES = {"SKIPPED", "CANCELLED", "TIMED_OUT"}
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
BEIJING_TIMEZONE_LABEL = "UTC+08:00"
ACTIVE_TASK_STATUSES = {"RUNNING"}
ACTIVE_REVIEW_STATUSES = {"REVIEWING"}
SEVERITY_ORDER = {"CRITICAL": 3, "MAJOR": 2, "MINOR": 1}
STAGE_PRIORITY = {
    "FAILED": 100,
    "FALLBACK": 95,
    "AGENT_SUBMITTING": 90,
    "AGENT_CONVERGING": 89,
    "AGENT_TOOL_ACTIVITY": 88,
    "AGENT_ANALYZING": 87,
    "MODEL_CALLING": 80,
    "CONTEXT_BUILDING": 75,
    "QUEUED": 70,
    "PREFLIGHT": 65,
    "NOTIFYING": 60,
    "FINDING_READY": 55,
    "RULE_COMPLETED": 45,
    "RULE_ANALYSIS": 40,
    "SKIPPED": 20,
    "COMPLETED": 10,
}


def get_runtime_snapshot(
    db: Session,
    *,
    window_hours: int,
    active_limit: int,
    alert_limit: int,
    project_id: int | None,
    group_id: int | None,
    now: datetime | None = None,
) -> RuntimeSnapshot:
    generated_at = _normalize_utc(now)
    today_from, _ = _beijing_day_window(generated_at)
    data = load_runtime_projection(
        db,
        window_from=_database_datetime(
            generated_at - timedelta(hours=window_hours)
        ),
        today_from=_database_datetime(today_from),
        now=_database_datetime(generated_at),
        active_limit=active_limit,
        alert_limit=alert_limit,
        project_id=project_id,
        group_id=group_id,
    )
    return build_runtime_snapshot(
        data,
        now=generated_at,
        window_hours=window_hours,
        active_limit=active_limit,
        alert_limit=alert_limit,
        project_id=project_id,
        group_id=group_id,
    )


def get_governance_snapshot(
    db: Session,
    *,
    window_hours: int,
    project_id: int | None,
    group_id: int | None,
    now: datetime | None = None,
) -> GovernanceSnapshot:
    generated_at = _normalize_utc(now)
    data = load_governance_projection(
        db,
        window_from=_database_datetime(
            generated_at - timedelta(hours=window_hours)
        ),
        project_id=project_id,
        group_id=group_id,
    )
    return build_governance_snapshot(
        data,
        now=generated_at,
        window_hours=window_hours,
        project_id=project_id,
        group_id=group_id,
    )


def build_runtime_snapshot(
    data: RuntimeProjectionData,
    *,
    now: datetime,
    window_hours: int,
    active_limit: int,
    alert_limit: int,
    project_id: int | None,
    group_id: int | None,
) -> RuntimeSnapshot:
    generated_at = _normalize_utc(now)
    database_now = _database_datetime(generated_at)
    task_rows = {
        int(row["task_id"]): row
        for row in data.tasks
    }
    rule_by_task = _group_rows(data.rule_results, "task_id")
    flows_by_task = _build_flow_rows(data)

    active_flows: list[ActiveFlowSnapshot] = []
    active_tasks: list[ActiveTaskSnapshot] = []
    for task_id, task in task_rows.items():
        flow_rows = flows_by_task.get(task_id) or [
            _empty_flow_row(task_id, DEFAULT_REVIEW_KEY)
        ]
        task_flows = [
            _build_active_flow(
                task,
                flow_row,
                rule_rows=rule_by_task.get(task_id, []),
                now=database_now,
            )
            for flow_row in flow_rows
        ]
        active_flows.extend(task_flows)
        task_stage = max(
            task_flows,
            key=lambda flow: STAGE_PRIORITY.get(flow.stage, 0),
        )
        active_tasks.append(
            ActiveTaskSnapshot(
                taskId=task_id,
                projectId=int(task["project_id"]),
                projectName=str(task.get("project_name") or f"Project {task['project_id']}"),
                groupId=_int_or_none(task.get("group_id")),
                triggerType=str(task.get("trigger_type") or "UNKNOWN"),
                authorName=task.get("author_name"),
                authorUsername=task.get("author_username"),
                externalUrl=task.get("external_url"),
                repositoryUrl=task.get("repository_url"),
                sourceBranch=task.get("source_branch"),
                targetBranch=task.get("target_branch"),
                commitSha=task.get("commit_sha") or task.get("after_sha"),
                technicalStatus=str(task.get("technical_status") or "UNKNOWN"),
                reviewStatus=str(task.get("review_status") or "UNKNOWN"),
                riskLevel=_normalize_severity(task.get("risk_level")),
                ruleRiskItemCount=sum(
                    int(row.get("risk_item_count") or 0)
                    for row in rule_by_task.get(task_id, [])
                ),
                flowCount=len(task_flows),
                stage=task_stage.stage,
                stageSource=task_stage.stage_source,
                createdAt=task.get("created_at"),
                updatedAt=_max_datetime(
                    task.get("updated_at"),
                    *(flow.updated_at for flow in task_flows),
                ),
            )
        )

    active_tasks.sort(
        key=lambda item: (_sort_time(item.updated_at), item.task_id),
        reverse=True,
    )
    active_flows.sort(
        key=lambda item: (_sort_time(item.updated_at), item.id),
        reverse=True,
    )

    worker_pool = _build_worker_pool(
        data.workers,
        data.agent_settings,
        now=database_now,
    )
    agent_queue = _build_agent_queue(
        data,
        worker_pool,
        now=database_now,
    )
    providers = _build_providers(data.providers, active_flows)
    alerts = _build_alerts(
        data,
        task_rows=task_rows,
        worker_pool=worker_pool,
        now=database_now,
        alert_limit=alert_limit,
    )
    standard_flows = [
        flow for flow in active_flows if flow.requested_engine != "AGENT"
    ]
    agent_flows = [
        flow for flow in active_flows if flow.requested_engine == "AGENT"
    ]
    flow_lookup = {flow.id: flow for flow in active_flows}
    worker_by_job_id = {
        int(row["active_job_id"]): row.get("worker_id")
        for row in data.workers
        if row.get("active_job_id") is not None
    }
    lane_running_items = [
        _build_review_lane_item(
            row,
            flow_lookup=flow_lookup,
            worker_by_job_id=worker_by_job_id,
            now=database_now,
        )
        for row in data.lane_running_jobs
    ]
    standard_running_items = [
        item for item in lane_running_items if item.status == "RUNNING"
        and _lane_engine(item) == "STANDARD"
    ]
    agent_running_items = [
        item for item in lane_running_items if item.status == "RUNNING"
        and _lane_engine(item) == "AGENT"
    ]
    standard_running_count = max(
        data.counts.running_job_count - data.counts.agent_running_job_count,
        0,
    )
    standard_queued_count = max(
        data.counts.queued_job_count - data.counts.agent_queued_job_count,
        0,
    )
    agent_capacity = agent_queue.online_capacity
    today_results = _build_today_results(
        data.today_result_status_counts,
        generated_at=generated_at,
    )

    return RuntimeSnapshot(
        generatedAt=generated_at,
        window=_window(generated_at, window_hours),
        intake=IntakeSnapshot(
            taskCount=data.counts.intake_task_count,
            activeTaskCount=data.counts.active_task_count,
        ),
        activeTasks=active_tasks,
        activeFlows=active_flows,
        scheduler=SchedulerSnapshot(
            activeJobCount=data.counts.queued_job_count
            + data.counts.running_job_count,
            queuedJobCount=data.counts.queued_job_count,
            runningJobCount=data.counts.running_job_count,
        ),
        standard=_engine_snapshot(standard_flows),
        agent=AgentSnapshot(
            **_engine_snapshot(agent_flows).model_dump(by_alias=True),
            workerPool=worker_pool,
            queueMetrics=agent_queue,
        ),
        reviewLanes=ReviewLanesSnapshot(
            standard=ReviewLaneSnapshot(
                zoneKey="standard",
                engine="STANDARD",
                capacity=PROVIDER_SCHEDULER_CAPACITY,
                runningCount=standard_running_count,
                queuedCount=standard_queued_count,
                utilizationPercent=_utilization_percent(
                    standard_running_count,
                    PROVIDER_SCHEDULER_CAPACITY,
                ),
                runningItems=standard_running_items,
                nextQueued=(
                    _build_review_lane_item(
                        data.standard_next_queued_job,
                        flow_lookup=flow_lookup,
                        worker_by_job_id=worker_by_job_id,
                        now=database_now,
                    )
                    if data.standard_next_queued_job
                    else None
                ),
                runningItemsTruncated=(
                    standard_running_count
                    > len(standard_running_items)
                ),
                queueOrder="PROVIDER_PRIORITY_FIFO",
            ),
            agent=ReviewLaneSnapshot(
                zoneKey="agent",
                engine="AGENT",
                capacity=agent_capacity,
                runningCount=data.counts.agent_running_job_count,
                queuedCount=data.counts.agent_queued_job_count,
                utilizationPercent=_utilization_percent(
                    data.counts.agent_running_job_count,
                    agent_capacity,
                ),
                runningItems=agent_running_items,
                nextQueued=(
                    _build_review_lane_item(
                        data.agent_next_queued_job,
                        flow_lookup=flow_lookup,
                        worker_by_job_id=worker_by_job_id,
                        now=database_now,
                    )
                    if data.agent_next_queued_job
                    else None
                ),
                runningItemsTruncated=(
                    data.counts.agent_running_job_count
                    > len(agent_running_items)
                ),
                queueOrder="AGENT_PRIORITY_FIFO",
            ),
        ),
        providersObserved=providers,
        alerts=alerts,
        todayResults=today_results,
        coverage=SnapshotCoverage(
            truncated=(
                data.candidate_task_count > data.selected_task_count
                or len(data.alerts) >= alert_limit
                or standard_running_count > len(standard_running_items)
                or data.counts.agent_running_job_count > len(agent_running_items)
            ),
            sections=RUNTIME_COVERAGE,
            limits={
                "activeLimit": active_limit,
                "alertLimit": alert_limit,
                "workerLimit": WORKER_LIMIT,
                "laneRunningItemLimit": LANE_RUNNING_ITEM_LIMIT,
            },
            filters={
                "projectId": project_id,
                "groupId": group_id,
            },
            scanned={
                "candidateTasks": data.candidate_task_count,
                "selectedTasks": data.selected_task_count,
                "activeFlows": len(active_flows),
                "todayResults": today_results.total_count,
                "laneRunningItems": len(lane_running_items),
                "alerts": len(alerts),
            },
        ),
    )


def _build_today_results(
    raw_status_counts: dict[str, int],
    *,
    generated_at: datetime,
) -> TodayResultsSnapshot:
    status_counts: Counter[str] = Counter()
    for status, count in raw_status_counts.items():
        status_counts[_safe_enum(status)] += max(int(count or 0), 0)

    success_count = status_counts["SUCCESS"]
    failure_count = status_counts["FAILED"]
    skipped_count = sum(status_counts[status] for status in TODAY_SKIPPED_STATUSES)
    running_count = sum(status_counts[status] for status in TODAY_RUNNING_STATUSES)
    total_count = sum(status_counts.values())
    completed_count = success_count + failure_count + skipped_count
    categorized_count = completed_count + running_count
    today_from, today_to = _beijing_day_window(generated_at)
    return TodayResultsSnapshot(
        date=generated_at.astimezone(BEIJING_TIMEZONE).date(),
        timezone=BEIJING_TIMEZONE_LABEL,
        **{
            "from": today_from,
            "to": today_to,
            "totalCount": total_count,
            "completedCount": completed_count,
            "successCount": success_count,
            "failureCount": failure_count,
            "skippedCount": skipped_count,
            "runningCount": running_count,
            "otherCount": max(total_count - categorized_count, 0),
            "statusCounts": dict(status_counts),
        },
    )


def _build_review_lane_item(
    row: dict[str, Any],
    *,
    flow_lookup: dict[str, ActiveFlowSnapshot],
    worker_by_job_id: dict[int, str | None],
    now: datetime,
) -> ReviewLaneItemSnapshot:
    task_id = int(row["task_id"])
    review_key = str(row.get("review_key") or DEFAULT_REVIEW_KEY)
    job_type = str(row.get("job_type") or "AI_REVIEW").upper()
    requested_engine = str(
        row.get("result_requested_engine")
        or ("AGENT" if job_type == "AGENT_REVIEW" else "STANDARD")
    ).upper()
    effective_engine = str(
        row.get("result_effective_engine")
        or requested_engine
    ).upper()
    fallback = (
        requested_engine == "AGENT"
        and effective_engine == "STANDARD_FALLBACK"
    )
    flow = flow_lookup.get(f"{task_id}:{review_key}")
    status = str(row.get("status") or "QUEUED").upper()
    stage = (
        flow.stage
        if flow is not None
        else (
            "QUEUED"
            if status == "QUEUED"
            else "AGENT_ANALYZING"
            if job_type == "AGENT_REVIEW"
            else "FALLBACK"
            if fallback
            else "MODEL_CALLING"
        )
    )
    provider = row.get("provider_code")
    if str(provider or "").upper() == "AGENT":
        provider = None
    return ReviewLaneItemSnapshot(
        jobId=int(row["job_id"]),
        taskId=task_id,
        reviewKey=review_key,
        projectId=_int_or_none(row.get("project_id")),
        projectName=str(
            row.get("project_name")
            or f"Project {row.get('project_id') or '-'}"
        ),
        displayName=str(
            row.get("display_name")
            or ("Agent Review" if requested_engine == "AGENT" else review_key)
        ),
        requestedEngine=requested_engine,
        effectiveEngine=effective_engine,
        fallback=fallback,
        status=status,
        stage=stage,
        provider=(str(provider) if provider else None),
        model=row.get("model"),
        workerId=(worker_by_job_id.get(int(row["job_id"])) if status == "RUNNING" else None),
        queuedAt=row.get("queued_at"),
        startedAt=row.get("started_at"),
        durationSeconds=_duration_seconds(
            row.get("started_at"),
            None,
            now=now,
            duration_ms=None,
        ),
    )


def _lane_engine(item: ReviewLaneItemSnapshot) -> str:
    return "AGENT" if item.requested_engine == "AGENT" and not item.fallback else "STANDARD"


def _utilization_percent(running_count: int, capacity: int) -> int:
    if capacity <= 0:
        return 0
    return min(round((running_count / capacity) * 100), 100)


def build_governance_snapshot(
    data: GovernanceProjectionData,
    *,
    now: datetime,
    window_hours: int,
    project_id: int | None,
    group_id: int | None,
) -> GovernanceSnapshot:
    generated_at = _normalize_utc(now)
    rule_distribution: Counter[str] = Counter()
    rule_result_count = 0
    rule_risk_item_count = 0
    for row in data.rule_rows:
        risk_level = _normalize_severity(row.get("risk_level")) or "NONE"
        count = int(row.get("result_count") or 0)
        rule_distribution[risk_level] += count
        rule_result_count += count
        rule_risk_item_count += int(row.get("risk_item_count") or 0)

    preflight_statuses: Counter[str] = Counter()
    preflight_finding_count = 0
    for row in data.preflight_rows:
        preflight_statuses[_safe_enum(row.get("status"))] += 1
        preflight_finding_count += len(_safe_json_list(row.get("findings_json")))

    finding_severities: Counter[str] = Counter()
    context_statuses: Counter[str] = Counter()
    affected_tasks: set[int] = set()
    for row in data.finding_rows:
        task_has_finding = False
        for finding in _safe_json_list(row.get("findings_json")):
            if not isinstance(finding, dict):
                continue
            severity = _normalize_severity(finding.get("severity")) or "UNKNOWN"
            context_status = _normalize_context_status(
                finding.get("contextStatus") or finding.get("context_status")
            )
            finding_severities[severity] += 1
            context_statuses[context_status] += 1
            task_has_finding = True
        if task_has_finding:
            affected_tasks.add(int(row["task_id"]))

    notification_statuses = _count_grouped(
        data.notification_rows,
        key="status",
    )
    feedback_statuses: Counter[str] = Counter()
    feedback_types: Counter[str] = Counter()
    feedback_total = 0
    context_missing_count = 0
    policy_candidate_count = 0
    for row in data.feedback_rows:
        count = int(row.get("count") or 0)
        status = _safe_enum(row.get("status"))
        feedback_type = _safe_enum(row.get("feedback_type"))
        reason_type = _safe_enum(row.get("reason_type"))
        feedback_total += count
        feedback_statuses[status] += count
        feedback_types[feedback_type] += count
        if "CONTEXT_MISSING" in {feedback_type, reason_type}:
            context_missing_count += count
        if bool(row.get("suggest_as_project_rule")):
            policy_candidate_count += count

    verdict_counts: Counter[str] = Counter()
    rule_gap_counts: Counter[str] = Counter()
    evaluation_case_count = 0
    for row in data.evaluation_case_rows:
        count = int(row.get("count") or 0)
        evaluation_case_count += count
        verdict_counts[_safe_enum(row.get("verdict"))] += count
        rule_gap = row.get("rule_gap_type")
        if rule_gap:
            rule_gap_counts[_safe_enum(rule_gap)] += count

    run_status_counts = _count_grouped(data.evaluation_run_rows, key="status")
    acceptance_status_counts = _count_grouped(data.acceptance_rows, key="status")
    latest_acceptance = max(
        data.acceptance_rows,
        key=lambda row: row.get("latest_at") or datetime.min,
        default=None,
    )
    policy_enabled_count = sum(
        int(row.get("count") or 0)
        for row in data.policy_rows
        if bool(row.get("enabled"))
    )
    policy_total_count = sum(int(row.get("count") or 0) for row in data.policy_rows)
    highest_risk = _highest_severity(finding_severities)
    finding_count = sum(finding_severities.values())
    truncated = data.preflight_truncated or data.finding_truncated

    return GovernanceSnapshot(
        generatedAt=generated_at,
        window=_window(generated_at, window_hours),
        ruleAnalysis=RuleAnalysisSnapshot(
            resultCount=rule_result_count,
            riskItemCount=rule_risk_item_count,
            riskDistribution=dict(rule_distribution),
        ),
        preflight=PreflightSnapshot(
            runCount=len(data.preflight_rows),
            findingCount=preflight_finding_count,
            statusCounts=dict(preflight_statuses),
        ),
        contextQuality=ContextQualitySnapshot(
            findingCount=finding_count,
            statusCounts=dict(context_statuses),
        ),
        findingRisk=FindingRiskSnapshot(
            findingCount=finding_count,
            highestRisk=highest_risk,
            affectedTaskCount=len(affected_tasks),
            severityCounts=dict(finding_severities),
        ),
        notifications=NotificationGovernanceSnapshot(
            recordCount=sum(notification_statuses.values()),
            statusCounts=dict(notification_statuses),
        ),
        feedback=FeedbackSnapshot(
            totalCount=feedback_total,
            pendingCount=feedback_statuses["PENDING"],
            statusCounts=dict(feedback_statuses),
            typeCounts=dict(feedback_types),
            contextMissingCount=context_missing_count,
            policyCandidateCount=policy_candidate_count,
        ),
        evaluation=EvaluationSnapshot(
            caseCount=evaluation_case_count,
            verdictCounts=dict(verdict_counts),
            ruleGapCounts=dict(rule_gap_counts),
            runCount=sum(run_status_counts.values()),
            runStatusCounts=dict(run_status_counts),
            acceptance=AcceptanceSnapshot(
                totalCount=sum(acceptance_status_counts.values()),
                statusCounts=dict(acceptance_status_counts),
                latestStatus=(
                    _safe_enum(latest_acceptance.get("status"))
                    if latest_acceptance
                    else None
                ),
            ),
            agentSampleGate=SampleGateSnapshot(
                annotatedSampleCount=evaluation_case_count,
                requiredSampleCount=SAMPLE_GATE_REQUIRED,
                ready=evaluation_case_count >= SAMPLE_GATE_REQUIRED,
            ),
        ),
        policies=PolicySnapshot(
            totalCount=policy_total_count,
            enabledCount=policy_enabled_count,
            candidateCount=policy_candidate_count,
        ),
        coverage=SnapshotCoverage(
            truncated=truncated,
            sections=GOVERNANCE_COVERAGE,
            limits={"findingResultScanLimit": FINDING_SCAN_LIMIT},
            filters={
                "projectId": project_id,
                "groupId": group_id,
            },
            scanned={
                "preflightRuns": len(data.preflight_rows),
                "findingResults": len(data.finding_rows),
            },
        ),
    )


def _build_flow_rows(
    data: RuntimeProjectionData,
) -> dict[int, list[dict[str, Any]]]:
    groups: dict[tuple[int, str], dict[str, Any]] = {}

    def group(task_id: int, review_key: object) -> dict[str, Any]:
        normalized_key = str(review_key or DEFAULT_REVIEW_KEY)
        return groups.setdefault(
            (task_id, normalized_key),
            _empty_flow_row(task_id, normalized_key),
        )

    for job in data.active_jobs:
        group(int(job["task_id"]), job.get("review_key"))["jobs"].append(job)
    for result in data.ai_results:
        group(int(result["task_id"]), result.get("review_key"))["results"].append(
            result
        )
    for event in data.progress_events:
        task_id = int(event["task_id"])
        review_key = event.get("review_key")
        dispatch_identity = _dispatch_progress_identity(event)
        projected_event = event
        if dispatch_identity is not None:
            dispatch_review_key, requested_engine = dispatch_identity
            if review_key is None:
                review_key = dispatch_review_key
            if str(review_key) == dispatch_review_key:
                projected_event = {
                    **event,
                    "_dispatch_requested_engine": requested_engine,
                }
        group(task_id, review_key)["progress"].append(projected_event)
    for run in data.agent_runs:
        group(int(run["task_id"]), run.get("review_key"))["runs"].append(run)

    keys_by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
    result_key_by_id = {
        int(result["id"]): (
            int(result["task_id"]),
            str(result.get("review_key") or DEFAULT_REVIEW_KEY),
        )
        for result in data.ai_results
    }
    for notification in data.notifications:
        key = result_key_by_id.get(_int_or_none(notification.get("result_id")) or -1)
        if key is None:
            task_id = int(notification["task_id"])
            task_keys = [item for item in groups if item[0] == task_id]
            key = task_keys[0] if len(task_keys) == 1 else (task_id, DEFAULT_REVIEW_KEY)
        group(*key)["notifications"].append(notification)

    _merge_single_dispatch_default_flows(groups)

    deterministic_by_task = _group_rows(data.deterministic_runs, "task_id")
    for (task_id, _review_key), flow in groups.items():
        flow["deterministic"] = deterministic_by_task.get(task_id, [])
        keys_by_task[task_id].append(flow)

    for task in data.tasks:
        task_id = int(task["task_id"])
        if task_id not in keys_by_task:
            flow = group(task_id, DEFAULT_REVIEW_KEY)
            flow["deterministic"] = deterministic_by_task.get(task_id, [])
            keys_by_task[task_id].append(flow)
    return keys_by_task


def _merge_single_dispatch_default_flows(
    groups: dict[tuple[int, str], dict[str, Any]],
) -> None:
    task_ids = {task_id for task_id, _review_key in groups}
    for task_id in task_ids:
        candidate_keys = {
            review_key
            for (group_task_id, review_key), flow in groups.items()
            if group_task_id == task_id
            and review_key != DEFAULT_REVIEW_KEY
            and _is_agent_dispatch_flow(flow)
        }
        if len(candidate_keys) != 1:
            continue
        target_key = next(iter(candidate_keys))
        default_group_key = (task_id, DEFAULT_REVIEW_KEY)
        target_group_key = (task_id, target_key)
        default_flow = groups.get(default_group_key)
        target_flow = groups.get(target_group_key)
        if default_flow is None or target_flow is None:
            continue
        if any(
            default_flow[field]
            for field in ("jobs", "results", "runs", "notifications")
        ):
            continue
        target_flow["progress"].extend(default_flow["progress"])
        del groups[default_group_key]


def _is_agent_dispatch_flow(flow: dict[str, Any]) -> bool:
    return any(
        event.get("_dispatch_requested_engine") == DISPATCH_PROGRESS_ENGINE
        for event in flow["progress"]
    ) or any(
        _safe_enum(job.get("job_type")) == "AGENT_REVIEW"
        for job in flow["jobs"]
    ) or any(
        _safe_enum(run.get("requested_engine")) == DISPATCH_PROGRESS_ENGINE
        for run in flow["runs"]
    ) or any(
        _safe_enum(result.get("requested_engine")) == DISPATCH_PROGRESS_ENGINE
        for result in flow["results"]
    )


def _build_active_flow(
    task: dict[str, Any],
    flow: dict[str, Any],
    *,
    rule_rows: list[dict[str, Any]],
    now: datetime,
) -> ActiveFlowSnapshot:
    job = _latest(flow["jobs"])
    result = _latest(flow["results"])
    progress = _latest(flow["progress"], timestamp_key="created_at")
    run = _latest(flow["runs"])
    notification = _latest(flow["notifications"])
    deterministic = _latest(flow["deterministic"])
    dispatch_progress = _latest(
        [
            event
            for event in flow["progress"]
            if event.get("_dispatch_requested_engine")
            == DISPATCH_PROGRESS_ENGINE
        ],
        timestamp_key="created_at",
    )

    requested_engine = str(
        (result or {}).get("requested_engine")
        or (run or {}).get("requested_engine")
        or (
            "AGENT"
            if job and job.get("job_type") == "AGENT_REVIEW"
            else "STANDARD" if job else None
        )
        or (dispatch_progress or {}).get("_dispatch_requested_engine")
        or "STANDARD"
    ).upper()
    effective_engine = str(
        (result or {}).get("effective_engine")
        or (run or {}).get("effective_engine")
        or requested_engine
    ).upper()
    fallback = (
        requested_engine == "AGENT"
        and effective_engine == "STANDARD_FALLBACK"
    )
    stage, stage_source = _derive_stage(
        task=task,
        job=job,
        result=result,
        progress=progress,
        run=run,
        notification=notification,
        deterministic=deterministic,
        has_rule_result=bool(rule_rows),
        fallback=fallback,
        requested_engine=requested_engine,
    )
    findings = _safe_json_list((result or {}).get("findings_json"))
    context_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        context_counts[
            _normalize_context_status(
                finding.get("contextStatus") or finding.get("context_status")
            )
        ] += 1
        severity_counts[
            _normalize_severity(finding.get("severity")) or "UNKNOWN"
        ] += 1
    highest_risk = (
        _normalize_severity((result or {}).get("overall_level"))
        or _highest_severity(severity_counts)
    )
    queued_at = (job or {}).get("queued_at") or (job or {}).get("created_at")
    started_at = (
        (run or {}).get("started_at")
        or (result or {}).get("started_at")
        or (job or {}).get("started_at")
    )
    finished_at = (
        (run or {}).get("finished_at")
        or (result or {}).get("finished_at")
    )
    duration_seconds = _duration_seconds(
        started_at,
        finished_at,
        now=now,
        duration_ms=(run or {}).get("duration_ms"),
    )
    status = _flow_status(
        stage,
        job=job,
        result=result,
        run=run,
    )
    review_key = str(flow["review_key"])
    provider = (result or {}).get("provider")
    if str(provider or "").upper() == "AGENT":
        provider = None
    return ActiveFlowSnapshot(
        id=f"{int(task['task_id'])}:{review_key}",
        taskId=int(task["task_id"]),
        reviewKey=review_key,
        displayName=str(
            (result or {}).get("display_name")
            or ("Agent Review" if requested_engine == "AGENT" else review_key)
        ),
        jobType=(job or {}).get("job_type"),
        requestedEngine=requested_engine,
        effectiveEngine=effective_engine,
        fallback=fallback,
        status=status,
        stage=stage,
        stageSource=stage_source,
        providerCode=(str(provider) if provider else None),
        model=(result or {}).get("model") or (run or {}).get("model"),
        findingCount=int((result or {}).get("finding_count") or len(findings)),
        highestRisk=highest_risk,
        contextStatusCounts=dict(context_counts),
        queuedAt=queued_at,
        startedAt=started_at,
        updatedAt=_max_datetime(
            *(row.get("updated_at") or row.get("created_at") for row in [
                job,
                result,
                progress,
                run,
                notification,
                deterministic,
            ] if row)
        ),
        durationSeconds=duration_seconds,
    )


def _derive_stage(
    *,
    task: dict[str, Any],
    job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    progress: dict[str, Any] | None,
    run: dict[str, Any] | None,
    notification: dict[str, Any] | None,
    deterministic: dict[str, Any] | None,
    has_rule_result: bool,
    fallback: bool,
    requested_engine: str,
) -> tuple[str, str]:
    if job and _safe_enum(job.get("status")) in FAILED_STATUSES:
        return "FAILED", "SCHEDULER_JOB"
    if run and _safe_enum(run.get("status")) in FAILED_STATUSES and not fallback:
        return "FAILED", "AGENT_RUN"
    if result and _safe_enum(result.get("status")) in FAILED_STATUSES:
        return "FAILED", "AI_RESULT"
    if fallback:
        return (
            "FALLBACK",
            "AI_RESULT"
            if result
            and _safe_enum(result.get("effective_engine")) == "STANDARD_FALLBACK"
            else "AGENT_RUN",
        )
    if job and _safe_enum(job.get("status")) == "QUEUED":
        return "QUEUED", "SCHEDULER_JOB"

    if progress:
        mapped = _map_progress_phase(progress.get("phase"))
        is_dispatch_progress = (
            _safe_enum(progress.get("phase")) in DISPATCH_PROGRESS_PHASES
        )
        actual_review_fact = job is not None or run is not None or result is not None
        if mapped and not (
            actual_review_fact
            and is_dispatch_progress
        ):
            return mapped, "PROGRESS"
        if not is_dispatch_progress and (
            job
            or run
            or (result and _safe_enum(result.get("status")) == "RUNNING")
        ):
            return (
                "AGENT_ANALYZING"
                if requested_engine == "AGENT"
                else "MODEL_CALLING",
                "PROGRESS",
            )

    if run:
        run_status = _safe_enum(run.get("status"))
        if run_status in SKIPPED_STATUSES:
            return "SKIPPED", "AGENT_RUN"
        if run_status in RUNNING_STATUSES:
            return "AGENT_ANALYZING", "AGENT_RUN"
    if job and _safe_enum(job.get("status")) == "RUNNING":
        return (
            "AGENT_ANALYZING"
            if requested_engine == "AGENT"
            else "MODEL_CALLING",
            "SCHEDULER_JOB",
        )
    if deterministic and _safe_enum(deterministic.get("status")) == "RUNNING":
        return "PREFLIGHT", "PROGRESS"
    if result:
        result_status = _safe_enum(result.get("status"))
        if result_status in SKIPPED_STATUSES:
            return "SKIPPED", "AI_RESULT"
        if result_status == "RUNNING":
            return (
                "AGENT_ANALYZING"
                if requested_engine == "AGENT"
                else "MODEL_CALLING",
                "AI_RESULT",
            )
        if result_status == "SUCCESS":
            if notification is not None:
                return "COMPLETED", "TASK"
            return "NOTIFYING", "INFERRED"
    if has_rule_result:
        return "RULE_COMPLETED", "RULE_RESULT"
    if (
        _safe_enum(task.get("technical_status")) in ACTIVE_TASK_STATUSES
        or _safe_enum(task.get("review_status")) in ACTIVE_REVIEW_STATUSES
    ):
        return "RULE_ANALYSIS", "INFERRED"
    return "COMPLETED", "TASK"


def _map_progress_phase(value: object) -> str | None:
    phase = _safe_enum(value)
    if phase in {"QUEUED", "AGENT_QUEUED"}:
        return "QUEUED"
    if phase.startswith("DETERMINISTIC_"):
        return "PREFLIGHT"
    if phase in DISPATCH_PROGRESS_FAILED_PHASES:
        return "FAILED"
    if phase in DISPATCH_PROGRESS_CONTEXT_PHASES:
        return "CONTEXT_BUILDING"
    if phase in {
        "REQUEST_BUILT",
        "CONTEXT_PACK_BUILT",
        "PROJECT_POLICIES_INJECTED",
        "LOCAL_CONTEXT_RETRIEVED",
        "LOCAL_CONTEXT_RETRIEVE_FAILED",
    }:
        return "CONTEXT_BUILDING"
    if phase in {"PROVIDER_CALLING", "PROVIDER_STARTED", "SAVE_RESULT"}:
        return "MODEL_CALLING"
    if phase == "AGENT_ANALYZING":
        return "AGENT_ANALYZING"
    if phase == "AGENT_TOOL_ACTIVITY":
        return "AGENT_TOOL_ACTIVITY"
    if phase == "AGENT_CONVERGING":
        return "AGENT_CONVERGING"
    if phase == "AGENT_SUBMITTING":
        return "AGENT_SUBMITTING"
    if phase in {"RESULT_SAVED", "FINISHED", "AGENT_FINISHED"}:
        return "FINDING_READY"
    if phase == "NOTIFICATION_SENT":
        return "COMPLETED"
    if phase in {"FAILED", "PROVIDER_FAILED"}:
        return "FAILED"
    if phase in {"JOB_INTERRUPTED", "AGENT_CANCELLED"}:
        return "SKIPPED"
    return None


def _dispatch_progress_identity(event: dict[str, Any]) -> tuple[str, str] | None:
    if _safe_enum(event.get("phase")) not in DISPATCH_PROGRESS_PHASES:
        return None
    detail = _safe_json_object(event.get("detail"))
    if detail.get("schemaVersion") != DISPATCH_PROGRESS_SCHEMA_VERSION:
        return None
    if detail.get("operation") != DISPATCH_PROGRESS_OPERATION:
        return None
    dispatch_attempt_id = detail.get("dispatchAttemptId")
    if (
        not isinstance(dispatch_attempt_id, str)
        or not dispatch_attempt_id.strip()
        or len(dispatch_attempt_id) > 128
    ):
        return None
    requested_engine = _safe_enum(detail.get("requestedEngine"))
    if requested_engine != DISPATCH_PROGRESS_ENGINE:
        return None
    if _safe_enum(detail.get("status")) not in DISPATCH_PROGRESS_STATUSES:
        return None
    duration_ms = detail.get("durationMs")
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0:
        return None
    review_key_value = detail.get("reviewKey")
    if not isinstance(review_key_value, str):
        return None
    review_key = review_key_value.strip()
    if not review_key or len(review_key) > REVIEW_KEY_MAX_LENGTH:
        return None
    return review_key, requested_engine


def _build_worker_pool(
    workers: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    now: datetime,
) -> WorkerPoolSnapshot:
    threshold = now - timedelta(seconds=WORKER_HEARTBEAT_SECONDS)
    records = list(workers)
    if not records and settings and settings.get("last_worker_heartbeat_at"):
        records.append(
            {
                "worker_id": settings.get("worker_id") or "legacy-worker",
                "state": "IDLE",
                "capacity": 1,
                "active_job_id": None,
                "active_run_id": None,
                "last_heartbeat_at": settings.get("last_worker_heartbeat_at"),
                "source": "LEGACY",
            }
        )

    worker_snapshots: list[WorkerSnapshot] = []
    for row in records[:WORKER_LIMIT]:
        state = _safe_enum(row.get("state"))
        if state not in {"IDLE", "BUSY", "DRAINING"}:
            state = "IDLE"
        heartbeat = row.get("last_heartbeat_at")
        worker_snapshots.append(
            WorkerSnapshot(
                workerId=str(row.get("worker_id") or "unknown-worker"),
                state=state,
                online=bool(heartbeat and heartbeat >= threshold),
                capacity=max(int(row.get("capacity") or 1), 1),
                activeJobId=_int_or_none(row.get("active_job_id")),
                activeRunId=_int_or_none(row.get("active_run_id")),
                lastHeartbeatAt=heartbeat,
                source=str(row.get("source") or "REGISTERED"),
            )
        )
    online = [worker for worker in worker_snapshots if worker.online]
    return WorkerPoolSnapshot(
        enabled=bool((settings or {}).get("enabled")),
        onlineCount=len(online),
        offlineCount=len(worker_snapshots) - len(online),
        idleCount=sum(
            1 for worker in online if worker.state == "IDLE"
        ),
        busyCount=sum(
            1 for worker in online if worker.state == "BUSY"
        ),
        drainingCount=sum(
            1 for worker in worker_snapshots if worker.state == "DRAINING"
        ),
        workers=worker_snapshots,
    )


def _build_agent_queue(
    data: RuntimeProjectionData,
    worker_pool: WorkerPoolSnapshot,
    *,
    now: datetime,
) -> AgentQueueSnapshot:
    online_workers = [
        worker for worker in worker_pool.workers if worker.online
    ]
    online_capacity = sum(worker.capacity for worker in online_workers)
    busy_capacity = sum(
        worker.capacity for worker in online_workers if worker.state == "BUSY"
    )
    oldest_queued_seconds = None
    oldest_queued_at = data.counts.oldest_queued_at
    if isinstance(oldest_queued_at, datetime):
        if oldest_queued_at.tzinfo is not None:
            oldest_queued_at = oldest_queued_at.astimezone(timezone.utc).replace(
                tzinfo=None
            )
        oldest_queued_seconds = max(
            int((now - oldest_queued_at).total_seconds()),
            0,
        )
    return AgentQueueSnapshot(
        queued=data.counts.agent_queued_job_count,
        running=data.counts.agent_running_job_count,
        expiredLease=data.counts.expired_lease_count,
        oldestQueuedSeconds=oldest_queued_seconds,
        onlineCapacity=online_capacity,
        busyCapacity=busy_capacity,
        utilizationPercent=(
            round((busy_capacity / online_capacity) * 100)
            if online_capacity
            else 0
        ),
        drainingWorkers=worker_pool.draining_count,
    )


def _build_providers(
    provider_rows: list[dict[str, Any]],
    active_flows: list[ActiveFlowSnapshot],
) -> list[ProviderSnapshot]:
    active_counts: Counter[str] = Counter(
        flow.provider_code.upper()
        for flow in active_flows
        if flow.provider_code and flow.provider_code.upper() != "AGENT"
    )
    providers: list[ProviderSnapshot] = []
    for row in provider_rows:
        provider_code = str(row.get("provider_code") or "UNKNOWN")
        active_count = active_counts[provider_code.upper()]
        success_count = int(row.get("recent_success_count") or 0)
        failure_count = int(row.get("recent_failure_count") or 0)
        enabled = bool(row.get("enabled"))
        if not enabled:
            status = "DISABLED"
        elif active_count:
            status = "ACTIVE"
        elif failure_count:
            status = "RECENT_FAILURE"
        elif success_count:
            status = "RECENT_SUCCESS"
        else:
            status = "NO_RECENT_DATA"
        providers.append(
            ProviderSnapshot(
                providerCode=provider_code,
                providerName=str(row.get("provider_name") or provider_code),
                providerType=str(row.get("provider_type") or "UNKNOWN"),
                modelName=row.get("model_name"),
                enabled=enabled,
                defaultProvider=bool(row.get("default_provider")),
                status=status,
                activeFlowCount=active_count,
                recentSuccessCount=success_count,
                recentFailureCount=failure_count,
                lastObservedAt=row.get("last_observed_at"),
            )
        )
    return providers


def _build_alerts(
    data: RuntimeProjectionData,
    *,
    task_rows: dict[int, dict[str, Any]],
    worker_pool: WorkerPoolSnapshot,
    now: datetime,
    alert_limit: int,
) -> list[AlertSnapshot]:
    candidates: list[AlertSnapshot] = []
    for row in data.alerts:
        task_id = _int_or_none(row.get("task_id"))
        candidates.append(
            AlertSnapshot(
                id=f"{row.get('alert_type')}:{row.get('source_id')}",
                type=str(row.get("alert_type") or "UNKNOWN"),
                status=str(row.get("status") or "UNKNOWN"),
                taskId=task_id,
                reviewKey=(
                    str(row.get("review_key"))
                    if row.get("review_key") is not None
                    else None
                ),
                projectId=_int_or_none(row.get("project_id")),
                projectName=row.get("project_name"),
                occurredAt=row.get("occurred_at"),
                navigationTarget=f"/tasks/{task_id}" if task_id else None,
            )
        )
    for worker in worker_pool.workers:
        alert_type = None
        if not worker.online:
            alert_type = "WORKER_OFFLINE"
        elif worker.state == "DRAINING":
            alert_type = "WORKER_DRAINING"
        if alert_type:
            candidates.append(
                AlertSnapshot(
                    id=f"{alert_type}:{worker.worker_id}",
                    type=alert_type,
                    status=worker.state,
                    occurredAt=worker.last_heartbeat_at or now,
                )
            )
    for job in data.active_jobs:
        if (
            job.get("status") == "RUNNING"
            and job.get("lease_expires_at")
            and job["lease_expires_at"] < now
        ):
            task_id = int(job["task_id"])
            task = task_rows.get(task_id) or {}
            candidates.append(
                AlertSnapshot(
                    id=f"LEASE_EXPIRED:{job['id']}",
                    type="LEASE_EXPIRED",
                    status="EXPIRED",
                    taskId=task_id,
                    reviewKey=job.get("review_key"),
                    projectId=_int_or_none(job.get("project_id")),
                    projectName=task.get("project_name"),
                    occurredAt=job.get("lease_expires_at"),
                    navigationTarget=f"/tasks/{task_id}",
                )
            )
    candidates.sort(
        key=lambda item: _sort_time(item.occurred_at),
        reverse=True,
    )
    return candidates[:alert_limit]


def _engine_snapshot(flows: list[ActiveFlowSnapshot]) -> FlowEngineSnapshot:
    return FlowEngineSnapshot(
        activeFlowCount=len(flows),
        findingCount=sum(flow.finding_count for flow in flows),
        statusCounts=dict(Counter(flow.status for flow in flows)),
    )


def _flow_status(
    stage: str,
    *,
    job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    run: dict[str, Any] | None,
) -> str:
    if stage == "FALLBACK":
        return "FALLBACK"
    if stage == "FAILED":
        return "FAILED"
    if stage == "SKIPPED":
        return "SKIPPED"
    if stage == "COMPLETED":
        return "SUCCESS"
    if stage == "QUEUED":
        return "QUEUED"
    return str(
        (run or {}).get("status")
        or (result or {}).get("status")
        or (job or {}).get("status")
        or "RUNNING"
    ).upper()


def _empty_flow_row(task_id: int, review_key: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "review_key": review_key,
        "jobs": [],
        "results": [],
        "progress": [],
        "runs": [],
        "notifications": [],
        "deterministic": [],
    }


def _group_rows(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row[key])].append(row)
    return grouped


def _latest(
    rows: list[dict[str, Any]],
    *,
    timestamp_key: str = "updated_at",
) -> dict[str, Any] | None:
    return max(
        rows,
        key=lambda row: (
            row.get(timestamp_key)
            or row.get("created_at")
            or datetime.min,
            int(row.get("id") or 0),
        ),
        default=None,
    )


def _safe_json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_severity(value: object) -> str | None:
    normalized = _safe_enum(value)
    return {
        "BLOCKER": "CRITICAL",
        "CRITICAL": "CRITICAL",
        "HIGH": "MAJOR",
        "MAJOR": "MAJOR",
        "MEDIUM": "MINOR",
        "MINOR": "MINOR",
        "LOW": "MINOR",
        "NO_RISK": None,
        "NONE": None,
        "UNKNOWN": None,
    }.get(normalized)


def _normalize_context_status(value: object) -> str:
    normalized = _safe_enum(value)
    return (
        normalized
        if normalized in {"SUFFICIENT", "PARTIAL", "INSUFFICIENT"}
        else "UNKNOWN"
    )


def _highest_severity(counts: Counter[str]) -> str | None:
    present = [
        severity
        for severity, count in counts.items()
        if count and severity in SEVERITY_ORDER
    ]
    return max(present, key=SEVERITY_ORDER.get) if present else None


def _count_grouped(
    rows: list[dict[str, Any]],
    *,
    key: str,
) -> Counter[str]:
    return Counter(
        {
            _safe_enum(row.get(key)): int(row.get("count") or 0)
            for row in rows
        }
    )


def _duration_seconds(
    started_at: datetime | None,
    finished_at: datetime | None,
    *,
    now: datetime,
    duration_ms: object,
) -> int | None:
    if duration_ms is not None:
        return max(round(int(duration_ms) / 1000), 0)
    if not started_at:
        return None
    return max(int(((finished_at or now) - started_at).total_seconds()), 0)


def _max_datetime(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _sort_time(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.timestamp()


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_enum(value: object) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    return normalized or "UNKNOWN"


def _window(now: datetime, hours: int) -> SnapshotWindow:
    return SnapshotWindow(
        **{
            "from": now - timedelta(hours=hours),
            "to": now,
            "hours": hours,
        }
    )


def _beijing_day_window(now: datetime) -> tuple[datetime, datetime]:
    generated_at = _normalize_utc(now)
    local_now = generated_at.astimezone(BEIJING_TIMEZONE)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc), generated_at


def _normalize_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _database_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)
