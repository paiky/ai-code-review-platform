from datetime import datetime, timedelta, timezone
import json

import pytest

from app.command_center.repository import (
    GovernanceProjectionData,
    RuntimeBaseCounts,
    RuntimeProjectionData,
)
from app.command_center.service import (
    _derive_stage,
    _map_progress_phase,
    build_governance_snapshot,
    build_runtime_snapshot,
)


NOW = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
DB_NOW = NOW.replace(tzinfo=None)


def test_runtime_snapshot_groups_review_keys_and_keeps_explicit_fallback() -> None:
    data = _runtime_data(
        tasks=[_task(101)],
        active_jobs=[
            _job(1, 101, "standard-main", "AI_REVIEW", "RUNNING"),
            _job(2, 101, "agent-main", "AGENT_REVIEW", "RUNNING"),
        ],
        ai_results=[
            _result(11, 101, "standard-main", "STANDARD", "STANDARD"),
            _result(
                12,
                101,
                "agent-main",
                "AGENT",
                "STANDARD_FALLBACK",
                status="SUCCESS",
                findings=[
                    {"severity": "CRITICAL", "contextStatus": "INSUFFICIENT"}
                ],
            ),
        ],
        agent_runs=[
            {
                "id": 21,
                "task_id": 101,
                "review_key": "agent-main",
                "requested_engine": "AGENT",
                "effective_engine": "STANDARD_FALLBACK",
                "model": "agent-model",
                "status": "FAILED",
                "duration_ms": 1500,
                "started_at": DB_NOW - timedelta(seconds=2),
                "finished_at": DB_NOW,
                "created_at": DB_NOW,
                "updated_at": DB_NOW,
            }
        ],
    )

    snapshot = _runtime_snapshot(data)
    flows = {flow["reviewKey"]: flow for flow in snapshot["activeFlows"]}

    assert set(flows) == {"standard-main", "agent-main"}
    assert flows["standard-main"]["id"] == "101:standard-main"
    assert flows["standard-main"]["fallback"] is False
    assert flows["agent-main"]["fallback"] is True
    assert flows["agent-main"]["stage"] == "FALLBACK"
    assert flows["agent-main"]["stageSource"] == "AI_RESULT"
    assert flows["agent-main"]["highestRisk"] == "CRITICAL"
    assert flows["agent-main"]["contextStatusCounts"] == {"INSUFFICIENT": 1}
    assert snapshot["activeTasks"][0]["flowCount"] == 2
    assert snapshot["activeTasks"][0]["stage"] == "FALLBACK"
    assert snapshot["activeTasks"][0]["authorName"] == "Mayn"
    assert snapshot["activeTasks"][0]["commitSha"] == "after-sha"


def test_runtime_snapshot_builds_beijing_today_result_buckets() -> None:
    snapshot = _runtime_snapshot(
        _runtime_data(
            today_result_status_counts={
                "SUCCESS": 4,
                "FAILED": 2,
                "SKIPPED": 1,
                "CANCELLED": 1,
                "TIMED_OUT": 1,
                "QUEUED": 2,
                "PENDING": 1,
                "CLAIMED": 1,
                "RUNNING": 3,
                "FUTURE_STATUS": 2,
            }
        )
    )

    today = snapshot["todayResults"]
    assert today["date"] == "2026-07-31"
    assert today["timezone"] == "UTC+08:00"
    assert today["from"] == "2026-07-30T16:00:00Z"
    assert today["to"] == "2026-07-31T02:00:00Z"
    assert today["totalCount"] == 18
    assert today["completedCount"] == 9
    assert today["successCount"] == 4
    assert today["failureCount"] == 2
    assert today["skippedCount"] == 3
    assert today["runningCount"] == 7
    assert today["otherCount"] == 2
    assert today["statusCounts"]["FUTURE_STATUS"] == 2


def test_runtime_snapshot_builds_standard_fallback_lane_from_scheduler_job() -> None:
    data = _runtime_data(
        counts=RuntimeBaseCounts(
            intake_task_count=1,
            active_task_count=1,
            queued_job_count=1,
            running_job_count=1,
            agent_queued_job_count=1,
            agent_running_job_count=0,
        ),
        lane_running_jobs=[
            {
                "job_id": 51,
                "job_type": "AI_REVIEW",
                "task_id": 101,
                "review_key": "agent-fallback",
                "project_id": 9001,
                "project_name": "Command Center",
                "display_name": "Agent Fallback",
                "result_requested_engine": "AGENT",
                "result_effective_engine": "STANDARD_FALLBACK",
                "provider_code": "DEEPSEEK",
                "model": "deepseek-chat",
                "status": "RUNNING",
                "queued_at": DB_NOW - timedelta(minutes=2),
                "started_at": DB_NOW - timedelta(minutes=1),
            }
        ],
        agent_next_queued_job={
            "job_id": 52,
            "job_type": "AGENT_REVIEW",
            "task_id": 102,
            "review_key": "agent-next",
            "project_id": 9001,
            "project_name": "Command Center",
            "display_name": "Agent Next",
            "run_requested_engine": "AGENT",
            "run_effective_engine": "AGENT",
            "run_model": "agent-model",
            "status": "QUEUED",
            "queued_at": DB_NOW,
            "started_at": None,
        },
    )

    snapshot = _runtime_snapshot(data)
    standard = snapshot["reviewLanes"]["standard"]
    agent = snapshot["reviewLanes"]["agent"]

    assert snapshot["schemaVersion"] == "command-center-runtime-v2"
    assert standard["capacity"] == 10
    assert standard["runningCount"] == 1
    assert standard["runningItems"][0]["fallback"] is True
    assert standard["runningItems"][0]["stage"] == "FALLBACK"
    assert agent["queuedCount"] == 1
    assert agent["nextQueued"]["reviewKey"] == "agent-next"
    assert agent["nextQueued"]["workerId"] is None


def test_runtime_snapshot_keeps_first_agent_waiter_without_timestamp_crash() -> None:
    data = _runtime_data(
        counts=RuntimeBaseCounts(
            intake_task_count=3,
            active_task_count=3,
            queued_job_count=1,
            running_job_count=2,
            agent_queued_job_count=1,
            agent_running_job_count=2,
            oldest_queued_at=DB_NOW - timedelta(seconds=45),
        ),
        workers=[
            {
                "worker_id": f"agent-worker-{index}",
                "state": "BUSY",
                "capacity": 1,
                "active_job_id": 70 + index,
                "active_run_id": 80 + index,
                "last_heartbeat_at": DB_NOW,
            }
            for index in range(2)
        ],
        lane_running_jobs=[
            {
                "job_id": 70 + index,
                "job_type": "AGENT_REVIEW",
                "task_id": 200 + index,
                "review_key": "agent:claude-code:deepseek-v4-pro",
                "project_id": 9001,
                "project_name": f"Agent Project {index}",
                "display_name": "Agent Review",
                "result_requested_engine": "AGENT",
                "result_effective_engine": "AGENT",
                "provider_code": "AGENT",
                "model": "deepseek-v4-pro",
                "status": "RUNNING",
                "queued_at": DB_NOW - timedelta(minutes=2),
                "started_at": DB_NOW - timedelta(minutes=1),
            }
            for index in range(2)
        ],
        agent_next_queued_job={
            "job_id": 72,
            "job_type": "AGENT_REVIEW",
            "task_id": 202,
            "review_key": "agent:claude-code:deepseek-v4-pro",
            "project_id": 9001,
            "project_name": "Queued Agent Project",
            "display_name": "Agent Review",
            "result_requested_engine": "AGENT",
            "result_effective_engine": "AGENT",
            "provider_code": "AGENT",
            "model": "deepseek-v4-pro",
            "status": "QUEUED",
            "queued_at": DB_NOW - timedelta(seconds=45),
            "started_at": None,
        },
    )

    snapshot = _runtime_snapshot(data)
    agent = snapshot["reviewLanes"]["agent"]

    assert snapshot["scheduler"] == {
        "status": "LIVE",
        "scope": "CURRENT_STATE",
        "activeJobCount": 3,
        "queuedJobCount": 1,
        "runningJobCount": 2,
    }
    assert agent["capacity"] == 2
    assert agent["runningCount"] == 2
    assert agent["queuedCount"] == 1
    assert agent["nextQueued"]["taskId"] == 202
    assert snapshot["agent"]["queueMetrics"]["oldestQueuedSeconds"] == 45
    assert snapshot["reviewLanes"]["standard"]["queuedCount"] == 0


def test_runtime_snapshot_accepts_timezone_aware_agent_queue_timestamp() -> None:
    data = _runtime_data(
        counts=RuntimeBaseCounts(
            intake_task_count=1,
            active_task_count=1,
            queued_job_count=1,
            running_job_count=0,
            agent_queued_job_count=1,
            agent_running_job_count=0,
            oldest_queued_at=NOW - timedelta(seconds=30),
        )
    )

    snapshot = _runtime_snapshot(data)

    assert snapshot["agent"]["queueMetrics"]["oldestQueuedSeconds"] == 30


def test_agent_failure_plus_standard_result_is_not_inferred_as_fallback() -> None:
    data = _runtime_data(
        tasks=[_task(102)],
        ai_results=[
            _result(31, 102, "standard-main", "STANDARD", "STANDARD", status="SUCCESS")
        ],
        agent_runs=[
            {
                "id": 32,
                "task_id": 102,
                "review_key": "agent-main",
                "requested_engine": "AGENT",
                "effective_engine": "AGENT",
                "model": "agent-model",
                "status": "FAILED",
                "duration_ms": None,
                "started_at": DB_NOW,
                "finished_at": DB_NOW,
                "created_at": DB_NOW,
                "updated_at": DB_NOW,
            }
        ],
    )

    flows = {
        flow["reviewKey"]: flow
        for flow in _runtime_snapshot(data)["activeFlows"]
    }

    assert flows["agent-main"]["fallback"] is False
    assert flows["agent-main"]["stage"] == "FAILED"
    assert flows["standard-main"]["fallback"] is False


@pytest.mark.parametrize(
    ("phase", "stage"),
    [
        ("DETERMINISTIC_PRECHECK_STARTED", "PREFLIGHT"),
        ("CONTEXT_PACK_BUILT", "CONTEXT_BUILDING"),
        ("LOCAL_CONTEXT_RETRIEVED", "CONTEXT_BUILDING"),
        ("SAVE_RESULT", "MODEL_CALLING"),
        ("AGENT_ANALYZING", "AGENT_ANALYZING"),
        ("AGENT_TOOL_ACTIVITY", "AGENT_TOOL_ACTIVITY"),
        ("AGENT_CONVERGING", "AGENT_CONVERGING"),
        ("AGENT_SUBMITTING", "AGENT_SUBMITTING"),
        ("RESULT_SAVED", "FINDING_READY"),
        ("NOTIFICATION_SENT", "COMPLETED"),
        ("PROVIDER_FAILED", "FAILED"),
        ("JOB_INTERRUPTED", "SKIPPED"),
    ],
)
def test_progress_phase_mapping(phase: str, stage: str) -> None:
    assert _map_progress_phase(phase) == stage


def test_unknown_progress_uses_safe_running_stage_without_thinking() -> None:
    stage, source = _derive_stage(
        task=_task(103),
        job=_job(41, 103, "standard-main", "AI_REVIEW", "RUNNING"),
        result=None,
        progress={
            "id": 42,
            "phase": "FUTURE_PROVIDER_PHASE",
            "created_at": DB_NOW,
        },
        run=None,
        notification=None,
        deterministic=None,
        has_rule_result=True,
        fallback=False,
        requested_engine="STANDARD",
    )

    assert stage == "MODEL_CALLING"
    assert source == "PROGRESS"
    assert stage != "THINKING"


def test_worker_provider_and_alert_aggregation_are_observation_only() -> None:
    data = _runtime_data(
        tasks=[_task(104)],
        active_jobs=[_job(51, 104, "standard-main", "AI_REVIEW", "RUNNING")],
        ai_results=[
            _result(52, 104, "standard-main", "STANDARD", "STANDARD")
        ],
        workers=[
            {
                "worker_id": "worker-online",
                "state": "BUSY",
                "capacity": 1,
                "active_job_id": 51,
                "active_run_id": None,
                "last_heartbeat_at": DB_NOW - timedelta(seconds=30),
            },
            {
                "worker_id": "worker-offline",
                "state": "IDLE",
                "capacity": 1,
                "active_job_id": None,
                "active_run_id": None,
                "last_heartbeat_at": DB_NOW - timedelta(seconds=61),
            },
            {
                "worker_id": "worker-draining",
                "state": "DRAINING",
                "capacity": 1,
                "active_job_id": None,
                "active_run_id": None,
                "last_heartbeat_at": DB_NOW - timedelta(seconds=10),
            },
        ],
        providers=[
            {
                "provider_code": "DEEPSEEK",
                "provider_name": "DeepSeek",
                "provider_type": "OPENAI_CHAT_COMPATIBLE",
                "model_name": "deepseek-chat",
                "enabled": True,
                "default_provider": True,
                "recent_success_count": 4,
                "recent_failure_count": 1,
                "last_observed_at": DB_NOW,
            },
            {
                "provider_code": "DISABLED",
                "provider_name": "Disabled",
                "provider_type": "OPENAI_CHAT_COMPATIBLE",
                "model_name": None,
                "enabled": False,
                "default_provider": False,
                "recent_success_count": 0,
                "recent_failure_count": 0,
                "last_observed_at": None,
            },
        ],
    )

    snapshot = _runtime_snapshot(data)
    worker_pool = snapshot["agent"]["workerPool"]
    providers = {
        provider["providerCode"]: provider
        for provider in snapshot["providersObserved"]
    }
    alert_types = {alert["type"] for alert in snapshot["alerts"]}

    assert worker_pool["onlineCount"] == 2
    assert worker_pool["offlineCount"] == 1
    assert worker_pool["busyCount"] == 1
    assert worker_pool["drainingCount"] == 1
    assert providers["DEEPSEEK"]["status"] == "ACTIVE"
    assert providers["DISABLED"]["status"] == "DISABLED"
    assert all(
        provider["status"]
        not in {"HEALTHY", "UNHEALTHY", "UP", "DOWN"}
        for provider in providers.values()
    )
    assert {"WORKER_OFFLINE", "WORKER_DRAINING"} <= alert_types


def test_governance_snapshot_has_explicit_scopes_and_safe_json_aggregation() -> None:
    data = GovernanceProjectionData(
        rule_rows=[
            {"risk_level": "HIGH", "result_count": 2, "risk_item_count": 3}
        ],
        preflight_rows=[
            {"status": "SUCCESS", "findings_json": json.dumps([{"type": "SECRET"}])},
            {"status": "FAILED", "findings_json": "broken"},
        ],
        finding_rows=[
            {
                "task_id": 201,
                "findings_json": json.dumps(
                    [
                        {
                            "severity": "BLOCKER",
                            "contextStatus": "INSUFFICIENT",
                            "body": "must never be returned",
                        },
                        {"severity": "MAJOR", "contextStatus": "PARTIAL"},
                    ]
                ),
            },
            {"task_id": 202, "findings_json": "not-json"},
        ],
        notification_rows=[
            {"status": "SUCCESS", "count": 2},
            {"status": "FAILED", "count": 1},
        ],
        feedback_rows=[
            {
                "status": "PENDING",
                "feedback_type": "CONTEXT_MISSING",
                "reason_type": "CONTEXT_MISSING",
                "suggest_as_project_rule": True,
                "count": 2,
            }
        ],
        evaluation_case_rows=[
            {
                "verdict": "VALID",
                "rule_gap_type": "MISSING_RULE",
                "count": 30,
            }
        ],
        evaluation_run_rows=[{"status": "SUCCESS", "count": 3}],
        policy_rows=[
            {"enabled": True, "count": 2},
            {"enabled": False, "count": 1},
        ],
        acceptance_rows=[
            {"status": "PASSED", "count": 2, "latest_at": DB_NOW}
        ],
        preflight_truncated=False,
        finding_truncated=False,
    )

    snapshot = build_governance_snapshot(
        data,
        now=NOW,
        window_hours=24,
        project_id=None,
        group_id=7,
    ).model_dump(by_alias=True, mode="json")

    assert snapshot["ruleAnalysis"]["scope"] == "WINDOW"
    assert snapshot["ruleAnalysis"]["riskDistribution"] == {"MAJOR": 2}
    assert snapshot["preflight"]["findingCount"] == 1
    assert snapshot["findingRisk"]["severityCounts"] == {
        "CRITICAL": 1,
        "MAJOR": 1,
    }
    assert snapshot["findingRisk"]["highestRisk"] == "CRITICAL"
    assert snapshot["contextQuality"]["statusCounts"] == {
        "INSUFFICIENT": 1,
        "PARTIAL": 1,
    }
    assert snapshot["feedback"]["scope"] == "ALL_TIME"
    assert snapshot["feedback"]["policyCandidateCount"] == 2
    assert snapshot["evaluation"]["agentSampleGate"]["ready"] is True
    assert snapshot["evaluation"]["agentSampleGate"]["requiredSampleCount"] == 30
    assert snapshot["policies"] == {
        "status": "LIVE",
        "scope": "ALL_TIME",
        "totalCount": 3,
        "enabledCount": 2,
        "candidateCount": 2,
    }
    assert "must never be returned" not in json.dumps(snapshot)


def test_governance_coverage_reports_truncation() -> None:
    data = GovernanceProjectionData(
        rule_rows=[],
        preflight_rows=[],
        finding_rows=[],
        notification_rows=[],
        feedback_rows=[],
        evaluation_case_rows=[],
        evaluation_run_rows=[],
        policy_rows=[],
        acceptance_rows=[],
        preflight_truncated=False,
        finding_truncated=True,
    )

    snapshot = build_governance_snapshot(
        data,
        now=NOW,
        window_hours=24,
        project_id=None,
        group_id=None,
    ).model_dump(by_alias=True, mode="json")

    assert snapshot["coverage"]["phase"] == "PHASE_1"
    assert snapshot["coverage"]["truncated"] is True
    assert snapshot["coverage"]["limits"]["findingResultScanLimit"] == 2000
    assert snapshot["evaluation"]["agentSampleGate"]["ready"] is False


def _runtime_snapshot(data: RuntimeProjectionData) -> dict:
    return build_runtime_snapshot(
        data,
        now=NOW,
        window_hours=24,
        active_limit=20,
        alert_limit=20,
        project_id=None,
        group_id=None,
    ).model_dump(by_alias=True, mode="json")


def _runtime_data(**overrides: object) -> RuntimeProjectionData:
    values = {
        "counts": RuntimeBaseCounts(
            intake_task_count=2,
            active_task_count=1,
            queued_job_count=0,
            running_job_count=1,
        ),
        "active_jobs": [],
        "tasks": [],
        "rule_results": [],
        "ai_results": [],
        "progress_events": [],
        "agent_runs": [],
        "deterministic_runs": [],
        "notifications": [],
        "workers": [],
        "agent_settings": {"enabled": True},
        "providers": [],
        "alerts": [],
        "lane_running_jobs": [],
        "standard_next_queued_job": None,
        "agent_next_queued_job": None,
        "candidate_task_count": 1,
        "selected_task_count": 1,
    }
    values.update(overrides)
    return RuntimeProjectionData(**values)


def _task(task_id: int) -> dict:
    return {
        "task_id": task_id,
        "project_id": 9001,
        "project_name": "Command Center",
        "group_id": 7001,
        "trigger_type": "MERGE_REQUEST",
        "author_name": "Mayn",
        "author_username": "mayn",
        "external_url": "https://gitlab.example.com/group/project/-/merge_requests/1",
        "repository_url": "https://gitlab.example.com/group/project",
        "source_branch": "feature/live-topology",
        "target_branch": "main",
        "commit_sha": None,
        "after_sha": "after-sha",
        "technical_status": "RUNNING",
        "review_status": "REVIEWING",
        "risk_level": "HIGH",
        "created_at": DB_NOW - timedelta(minutes=5),
        "updated_at": DB_NOW,
    }


def _job(
    job_id: int,
    task_id: int,
    review_key: str,
    job_type: str,
    status: str,
) -> dict:
    return {
        "id": job_id,
        "job_type": job_type,
        "task_id": task_id,
        "review_key": review_key,
        "project_id": 9001,
        "status": status,
        "lease_expires_at": DB_NOW + timedelta(minutes=1),
        "queued_at": DB_NOW - timedelta(minutes=2),
        "started_at": DB_NOW - timedelta(minutes=1),
        "created_at": DB_NOW - timedelta(minutes=2),
        "updated_at": DB_NOW,
    }


def _result(
    result_id: int,
    task_id: int,
    review_key: str,
    requested_engine: str,
    effective_engine: str,
    *,
    status: str = "RUNNING",
    findings: list[dict] | None = None,
) -> dict:
    finding_list = findings or []
    return {
        "id": result_id,
        "task_id": task_id,
        "review_key": review_key,
        "provider": "DEEPSEEK",
        "model": "deepseek-chat",
        "display_name": review_key,
        "status": status,
        "overall_level": "CRITICAL" if finding_list else None,
        "finding_count": len(finding_list),
        "findings_json": json.dumps(finding_list),
        "requested_engine": requested_engine,
        "effective_engine": effective_engine,
        "started_at": DB_NOW - timedelta(minutes=1),
        "finished_at": DB_NOW if status == "SUCCESS" else None,
        "created_at": DB_NOW - timedelta(minutes=2),
        "updated_at": DB_NOW,
    }
