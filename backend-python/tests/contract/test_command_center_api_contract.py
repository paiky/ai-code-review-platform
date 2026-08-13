from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from typing import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.agent_review.models import (
    AgentReviewRun,
    AgentReviewSettings,
    AgentReviewWorker,
)
from app.code_quality.models import (
    CodeQualityModelProvider,
    CodeQualityReviewProgressEvent,
    CodeQualityReviewResult,
    CodeQualityReviewSettings,
    CodeQualitySchedulerJob,
)
from app.command_center.service import get_runtime_snapshot
from app.deterministic_checks.models import DeterministicCheckRun
from app.evaluation.models import EvaluationCase, EvaluationRun
from app.project_integration.models import Project
from app.project_review_policy.models import ProjectReviewPolicy
from app.review_feedback.models import ReviewItemFeedback
from app.review_quality_acceptance.models import ReviewQualityAcceptanceGate
from app.review_record.models import NotificationRecord, ReviewResult, ReviewTask


RUNTIME_TOP_LEVEL_KEYS = {
    "schemaVersion",
    "generatedAt",
    "window",
    "intake",
    "activeTasks",
    "activeFlows",
    "scheduler",
    "standard",
    "agent",
    "reviewLanes",
    "providersObserved",
    "alerts",
    "todayResults",
    "coverage",
}

GOVERNANCE_TOP_LEVEL_KEYS = {
    "schemaVersion",
    "generatedAt",
    "window",
    "ruleAnalysis",
    "preflight",
    "contextQuality",
    "findingRisk",
    "notifications",
    "feedback",
    "evaluation",
    "policies",
    "coverage",
}


def test_command_center_empty_database_phase_one_contract(
    client: TestClient,
) -> None:
    runtime_response = client.get("/api/command-center/runtime")
    governance_response = client.get("/api/command-center/governance")

    assert runtime_response.status_code == 200
    runtime = runtime_response.json()["data"]
    assert set(runtime) == RUNTIME_TOP_LEVEL_KEYS
    assert runtime["schemaVersion"] == "command-center-runtime-v2"
    assert runtime["intake"]["taskCount"] == 0
    assert runtime["activeTasks"] == []
    assert runtime["activeFlows"] == []
    assert runtime["agent"]["workerPool"]["workers"] == []
    assert runtime["reviewLanes"]["standard"] == {
        "zoneKey": "standard",
        "engine": "STANDARD",
        "capacity": 10,
        "runningCount": 0,
        "queuedCount": 0,
        "utilizationPercent": 0,
        "runningItems": [],
        "nextQueued": None,
        "runningItemsTruncated": False,
        "queueOrder": "PROVIDER_PRIORITY_FIFO",
    }
    assert runtime["reviewLanes"]["agent"]["capacity"] == 0
    assert runtime["providersObserved"] == []
    assert runtime["todayResults"]["scope"] == "TODAY"
    assert runtime["todayResults"]["timezone"] == "UTC+08:00"
    assert runtime["todayResults"]["totalCount"] == 0
    assert runtime["todayResults"]["statusCounts"] == {}
    assert runtime["coverage"]["phase"] == "PHASE_1"
    assert runtime["coverage"]["sections"]["activeFlows"] == "BOUNDED"
    assert runtime["coverage"]["sections"]["todayResults"] == "FULL"

    assert governance_response.status_code == 200
    governance = governance_response.json()["data"]
    assert set(governance) == GOVERNANCE_TOP_LEVEL_KEYS
    assert governance["schemaVersion"] == "command-center-governance-v1"
    assert governance["ruleAnalysis"]["scope"] == "WINDOW"
    assert governance["feedback"]["scope"] == "ALL_TIME"
    assert governance["evaluation"]["agentSampleGate"] == {
        "annotatedSampleCount": 0,
        "requiredSampleCount": 30,
        "ready": False,
    }


def test_runtime_returns_real_task_flow_worker_provider_and_alert_data(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _seed_phase_one_scenario(db_session, now)

    response = client.get(
        "/api/command-center/runtime",
        params={"windowHours": 24, "groupId": 7001},
    )

    assert response.status_code == 200
    runtime = response.json()["data"]
    assert runtime["intake"]["activeTaskCount"] == 1
    assert runtime["scheduler"]["queuedJobCount"] == 1
    assert runtime["scheduler"]["runningJobCount"] == 1
    assert len(runtime["activeTasks"]) == 1
    assert runtime["activeTasks"][0]["projectName"] == "command-center-one"
    assert runtime["activeTasks"][0]["flowCount"] == 2
    assert runtime["activeTasks"][0]["authorName"] == "Command Center Author"
    assert runtime["activeTasks"][0]["authorUsername"] == "cc-author"
    assert runtime["activeTasks"][0]["sourceBranch"] == "feature/runtime-map"
    assert runtime["activeTasks"][0]["targetBranch"] == "main"
    assert runtime["activeTasks"][0]["commitSha"] == "after-sha"
    assert runtime["activeTasks"][0]["externalUrl"].startswith("https://gitlab.example.com/")
    assert runtime["activeTasks"][0]["repositoryUrl"].startswith("https://gitlab.example.com/")
    flows = {flow["reviewKey"]: flow for flow in runtime["activeFlows"]}
    assert set(flows) == {"standard-main", "agent-main"}
    assert flows["standard-main"]["stage"] == "CONTEXT_BUILDING"
    assert flows["standard-main"]["stageSource"] == "PROGRESS"
    assert flows["agent-main"]["fallback"] is True
    assert flows["agent-main"]["stage"] == "FALLBACK"
    assert flows["agent-main"]["contextStatusCounts"] == {"INSUFFICIENT": 1}
    assert runtime["agent"]["workerPool"]["onlineCount"] == 1
    assert runtime["agent"]["workerPool"]["busyCount"] == 1
    assert runtime["agent"]["queueMetrics"]["queued"] == 1
    assert runtime["agent"]["queueMetrics"]["running"] == 0
    assert runtime["agent"]["queueMetrics"]["onlineCapacity"] == 1
    standard_lane = runtime["reviewLanes"]["standard"]
    agent_lane = runtime["reviewLanes"]["agent"]
    assert standard_lane["runningCount"] == 1
    assert standard_lane["runningItems"][0]["reviewKey"] == "standard-main"
    assert standard_lane["runningItems"][0]["stage"] == "CONTEXT_BUILDING"
    assert agent_lane["queuedCount"] == 1
    assert agent_lane["nextQueued"]["reviewKey"] == "agent-main"
    assert agent_lane["queueOrder"] == "AGENT_PRIORITY_FIFO"
    providers = {
        provider["providerCode"]: provider
        for provider in runtime["providersObserved"]
    }
    assert providers["DEEPSEEK"]["status"] == "ACTIVE"
    assert providers["DEEPSEEK"]["defaultProvider"] is True
    assert providers["DISABLED"]["enabled"] is True
    assert providers["DISABLED"]["status"] == "NO_RECENT_DATA"
    assert all(
        provider["status"]
        not in {"HEALTHY", "UNHEALTHY", "UP", "DOWN"}
        for provider in providers.values()
    )
    assert {"FALLBACK", "NOTIFICATION_FAILED", "CRITICAL_FINDING"} <= {
        alert["type"] for alert in runtime["alerts"]
    }


def test_runtime_projects_task_level_dispatch_progress_without_lane_counts(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    project = _project(7501, 7001, "dispatch-preparing")
    task = _task(7502, project.id, now)
    review_key = "agent:claude-code:deepseek-v4-pro"
    dispatch_detail = json.dumps(
        {
            "schemaVersion": "agent-dispatch-progress-v1",
            "operation": "AGENT_ENQUEUE",
            "dispatchAttemptId": "dispatch-contract-1",
            "reviewKey": review_key,
            "requestedEngine": "AGENT",
            "status": "STARTED",
            "durationMs": 0,
        }
    )
    db_session.add_all(
        [
            project,
            task,
            CodeQualityReviewProgressEvent(
                id=7503,
                task_id=task.id,
                review_key=None,
                phase="DETERMINISTIC_PRECHECK_STARTED",
                level="INFO",
                message="Preflight started",
                created_at=now - timedelta(seconds=2),
            ),
            CodeQualityReviewProgressEvent(
                id=7504,
                task_id=task.id,
                review_key=None,
                phase="AGENT_JOB_CREATE_STARTED",
                level="INFO",
                message="Agent job persistence started",
                detail=dispatch_detail,
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/command-center/runtime",
        params={"projectId": project.id},
    )

    assert response.status_code == 200
    runtime = response.json()["data"]
    assert runtime["schemaVersion"] == "command-center-runtime-v2"
    assert len(runtime["activeFlows"]) == 1
    flow = runtime["activeFlows"][0]
    assert flow["id"] == f"{task.id}:{review_key}"
    assert flow["reviewKey"] == review_key
    assert flow["requestedEngine"] == "AGENT"
    assert flow["effectiveEngine"] == "AGENT"
    assert flow["status"] == "RUNNING"
    assert flow["stage"] == "CONTEXT_BUILDING"
    assert flow["stageSource"] == "PROGRESS"
    assert flow["queuedAt"] is None
    assert flow["startedAt"] is None
    assert runtime["activeTasks"][0]["flowCount"] == 1
    assert runtime["scheduler"]["queuedJobCount"] == 0
    assert runtime["scheduler"]["runningJobCount"] == 0
    assert runtime["reviewLanes"]["standard"]["queuedCount"] == 0
    assert runtime["reviewLanes"]["standard"]["runningCount"] == 0
    assert runtime["reviewLanes"]["agent"]["queuedCount"] == 0
    assert runtime["reviewLanes"]["agent"]["runningCount"] == 0
    assert runtime["reviewLanes"]["agent"]["nextQueued"] is None
    assert "dispatchAttemptId" not in json.dumps(runtime)


def test_runtime_today_results_use_beijing_boundary_and_group_filter(
    db_session: Session,
) -> None:
    now = datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc)
    database_now = now.replace(tzinfo=None)
    today_from = datetime(2026, 8, 3, 16, 0)
    project = _project(7601, 7001, "today-in-scope")
    other_project = _project(7602, 7002, "today-out-of-scope")
    tasks = [
        _task(7610 + index, project.id, database_now)
        for index in range(1, 8)
    ]
    other_task = _task(7699, other_project.id, database_now)
    statuses_and_times = [
        ("SUCCESS", today_from),
        ("FAILED", today_from + timedelta(minutes=1)),
        ("TIMED_OUT", today_from + timedelta(minutes=2)),
        ("QUEUED", today_from + timedelta(minutes=3)),
        ("FUTURE_STATUS", today_from + timedelta(minutes=4)),
        ("SUCCESS", today_from - timedelta(microseconds=1)),
        ("SUCCESS", database_now),
    ]
    results = [
        _quality_result(
            7700 + index,
            task.id,
            project.id,
            f"today-{index}",
            status,
            updated_at,
        )
        for index, (task, (status, updated_at)) in enumerate(
            zip(tasks, statuses_and_times),
            start=1,
        )
    ]
    results.append(
        _quality_result(
            7799,
            other_task.id,
            other_project.id,
            "other-project",
            "SUCCESS",
            today_from + timedelta(minutes=5),
        )
    )
    db_session.add_all([project, other_project, *tasks, other_task, *results])
    db_session.commit()

    snapshot = get_runtime_snapshot(
        db_session,
        window_hours=24,
        active_limit=20,
        alert_limit=20,
        project_id=None,
        group_id=7001,
        now=now,
    ).model_dump(by_alias=True, mode="json")

    assert snapshot["todayResults"] == {
        "status": "LIVE",
        "scope": "TODAY",
        "date": "2026-08-04",
        "timezone": "UTC+08:00",
        "from": "2026-08-03T16:00:00Z",
        "to": "2026-08-04T04:00:00Z",
        "totalCount": 5,
        "completedCount": 3,
        "successCount": 1,
        "failureCount": 1,
        "skippedCount": 1,
        "runningCount": 1,
        "otherCount": 1,
        "statusCounts": {
            "FAILED": 1,
            "FUTURE_STATUS": 1,
            "QUEUED": 1,
            "SUCCESS": 1,
            "TIMED_OUT": 1,
        },
    }
    assert snapshot["coverage"]["scanned"]["todayResults"] == 5

    project_snapshot = get_runtime_snapshot(
        db_session,
        window_hours=24,
        active_limit=20,
        alert_limit=20,
        project_id=other_project.id,
        group_id=None,
        now=now,
    ).model_dump(by_alias=True, mode="json")
    assert project_snapshot["todayResults"]["totalCount"] == 1
    assert project_snapshot["todayResults"]["successCount"] == 1


def test_runtime_review_lanes_use_engine_specific_queue_order_and_worker_binding(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    project = _project(8101, 8001, "runtime-map")
    tasks = [_task(8200 + index, project.id, now) for index in range(1, 7)]
    jobs = [
        _scheduler_job(8301, 8201, project.id, "standard-later", "AI_REVIEW", "QUEUED", 50, now - timedelta(minutes=10), now),
        _scheduler_job(8302, 8202, project.id, "standard-next", "AI_REVIEW", "QUEUED", 10, now - timedelta(minutes=1), now),
        _scheduler_job(8303, 8203, project.id, "agent-lower", "AGENT_REVIEW", "QUEUED", 10, now - timedelta(minutes=10), now),
        _scheduler_job(8304, 8204, project.id, "agent-next", "AGENT_REVIEW", "QUEUED", 50, now - timedelta(minutes=1), now),
        _scheduler_job(8305, 8205, project.id, "standard-running", "AI_REVIEW", "RUNNING", 10, now - timedelta(minutes=5), now, started_at=now - timedelta(minutes=4)),
        _scheduler_job(8306, 8206, project.id, "agent-running", "AGENT_REVIEW", "RUNNING", 50, now - timedelta(minutes=5), now, started_at=now - timedelta(minutes=3)),
    ]
    results = [
        CodeQualityReviewResult(
            id=8400 + index,
            task_id=job.task_id,
            review_key=job.review_key,
            project_id=project.id,
            profile_code="backend-default",
            provider="AGENT" if job.job_type == "AGENT_REVIEW" else "DEEPSEEK",
            model="agent-model" if job.job_type == "AGENT_REVIEW" else "deepseek-chat",
            display_name=job.review_key,
            sort_order=index,
            status="RUNNING" if job.status == "RUNNING" else "QUEUED",
            finding_count=0,
            findings_json="[]",
            requested_engine="AGENT" if job.job_type == "AGENT_REVIEW" else "STANDARD",
            effective_engine="AGENT" if job.job_type == "AGENT_REVIEW" else "STANDARD",
            created_at=now,
            updated_at=now,
        )
        for index, job in enumerate(jobs, start=1)
    ]
    db_session.add_all([
        project,
        *tasks,
        *jobs,
        *results,
        AgentReviewSettings(
            id=8501,
            enabled=True,
            worker_id="runtime-map-worker",
            last_worker_heartbeat_at=now,
            created_at=now,
            updated_at=now,
        ),
        AgentReviewWorker(
            worker_id="runtime-map-worker",
            worker_version="v1",
            cli_version="v1",
            state="BUSY",
            capacity=2,
            active_job_id=8306,
            active_run_id=None,
            started_at=now - timedelta(hours=1),
            last_heartbeat_at=now,
            updated_at=now,
        ),
    ])
    db_session.commit()

    response = client.get(
        "/api/command-center/runtime",
        params={"groupId": 8001},
    )

    assert response.status_code == 200
    lanes = response.json()["data"]["reviewLanes"]
    assert lanes["standard"]["nextQueued"]["reviewKey"] == "standard-next"
    assert lanes["agent"]["nextQueued"]["reviewKey"] == "agent-next"
    assert lanes["standard"]["runningItems"][0]["reviewKey"] == "standard-running"
    assert lanes["agent"]["runningItems"][0]["reviewKey"] == "agent-running"
    assert lanes["agent"]["runningItems"][0]["workerId"] == "runtime-map-worker"
    assert lanes["standard"]["runningItems"][0]["provider"] == "DEEPSEEK"
    assert lanes["agent"]["capacity"] == 2


def test_governance_returns_window_and_all_time_metrics(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _seed_phase_one_scenario(db_session, now)

    response = client.get(
        "/api/command-center/governance",
        params={"windowHours": 24, "groupId": 7001},
    )

    assert response.status_code == 200
    governance = response.json()["data"]
    assert governance["ruleAnalysis"] == {
        "status": "LIVE",
        "scope": "WINDOW",
        "resultCount": 1,
        "riskItemCount": 2,
        "riskDistribution": {"MAJOR": 1},
    }
    assert governance["preflight"]["runCount"] == 1
    assert governance["preflight"]["findingCount"] == 1
    assert governance["contextQuality"]["statusCounts"] == {
        "INSUFFICIENT": 1
    }
    assert governance["findingRisk"]["highestRisk"] == "CRITICAL"
    assert governance["notifications"]["statusCounts"] == {"FAILED": 1}
    assert governance["feedback"]["pendingCount"] == 1
    assert governance["feedback"]["contextMissingCount"] == 1
    assert governance["feedback"]["policyCandidateCount"] == 1
    assert governance["evaluation"]["verdictCounts"] == {
        "CONTEXT_MISSING": 1
    }
    assert governance["evaluation"]["runStatusCounts"] == {"SUCCESS": 1}
    assert governance["evaluation"]["acceptance"]["latestStatus"] == "PASSED"
    assert governance["evaluation"]["agentSampleGate"]["ready"] is False
    assert governance["policies"]["enabledCount"] == 1
    assert governance["policies"]["candidateCount"] == 1
    assert governance["coverage"]["truncated"] is False


def test_fallback_is_not_inferred_from_agent_failure_and_standard_result(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    project = _project(8101, 8001, "strict-fallback")
    task = _task(8201, project.id, now)
    db_session.add_all(
        [
            project,
            task,
            CodeQualityReviewResult(
                id=8301,
                task_id=task.id,
                review_key="standard-main",
                project_id=project.id,
                profile_code="backend-default",
                provider="DEEPSEEK",
                model="deepseek-chat",
                display_name="Standard",
                sort_order=0,
                status="SUCCESS",
                overall_level="MINOR",
                finding_count=0,
                findings_json="[]",
                requested_engine="STANDARD",
                effective_engine="STANDARD",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
            AgentReviewRun(
                id=8401,
                task_id=task.id,
                review_key="agent-main",
                idempotency_key="strict-agent-run",
                requested_engine="AGENT",
                effective_engine="AGENT",
                runner_version="agent-worker-v1",
                model="agent-model",
                status="FAILED",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    runtime = client.get("/api/command-center/runtime").json()["data"]
    agent_flow = next(
        flow for flow in runtime["activeFlows"] if flow["reviewKey"] == "agent-main"
    )

    assert agent_flow["fallback"] is False
    assert agent_flow["stage"] == "FAILED"


def test_command_center_query_bounds_read_only_and_sensitive_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _seed_phase_one_scenario(db_session, now)

    with _capture_statements(db_session) as runtime_statements:
        runtime_response = client.get("/api/command-center/runtime")
    with _capture_statements(db_session) as governance_statements:
        governance_response = client.get("/api/command-center/governance")

    assert runtime_response.status_code == 200
    assert governance_response.status_code == 200
    assert len(runtime_statements) <= 20
    assert len(governance_statements) <= 12
    assert all(
        statement.lstrip().upper().startswith("SELECT")
        for statement in [*runtime_statements, *governance_statements]
    )

    sql = "\n".join(runtime_statements).lower()
    assert "review_tasks.created_at >=" in sql
    assert "review_tasks.status in" in sql
    assert "review_tasks.review_status in" in sql
    assert "code_quality_scheduler_jobs.job_type in" in sql
    assert "code_quality_scheduler_jobs.status in" in sql
    assert "progress_events.detail" in sql
    for prohibited_column in [
        "api_key",
        "endpoint_url",
        "raw_output",
        "response_body",
        "notification_records.target",
        "input_json",
        "completion_context_json",
        "policy.content",
    ]:
        assert prohibited_column not in sql

    payload = json.dumps(
        {
            "runtime": runtime_response.json()["data"],
            "governance": governance_response.json()["data"],
        },
        ensure_ascii=False,
    )
    for prohibited_field in [
        "apiKey",
        "endpointUrl",
        "webhookUrl",
        "prompt",
        "rawOutput",
        "findingsJson",
        "responseBody",
        "errorMessage",
        "must never leave backend",
    ]:
        assert prohibited_field not in payload


def test_runtime_query_count_does_not_grow_with_active_task_count(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _seed_phase_one_scenario(db_session, now)
    with _capture_statements(db_session) as one_task_statements:
        assert client.get("/api/command-center/runtime").status_code == 200

    db_session.add_all(
        [
            _project(9102, 7001, "command-center-second"),
            _task(9202, 9102, now),
            CodeQualitySchedulerJob(
                id=9302,
                job_type="AI_REVIEW",
                task_id=9202,
                project_id=9102,
                review_key="second-main",
                status="QUEUED",
                priority=100,
                queued_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    with _capture_statements(db_session) as two_task_statements:
        assert client.get("/api/command-center/runtime").status_code == 200

    assert len(one_task_statements) == len(two_task_statements)
    assert len(two_task_statements) <= 20


def test_command_center_query_parameter_bounds_are_enforced(
    client: TestClient,
) -> None:
    assert client.get("/api/command-center/runtime?windowHours=0").status_code == 400
    assert client.get("/api/command-center/runtime?activeLimit=51").status_code == 400
    assert client.get("/api/command-center/runtime?alertLimit=0").status_code == 400
    assert client.get("/api/command-center/governance?windowHours=169").status_code == 400


@contextmanager
def _capture_statements(db_session: Session) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = db_session.get_bind()

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.strip())

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)


def _seed_phase_one_scenario(db_session: Session, now: datetime) -> None:
    project = _project(7101, 7001, "command-center-one")
    task = _task(7201, project.id, now)
    finding = {
        "severity": "CRITICAL",
        "contextStatus": "INSUFFICIENT",
        "body": "must never leave backend",
    }
    db_session.add_all(
        [
            project,
            task,
            ReviewResult(
                id=7251,
                task_id=task.id,
                project_id=project.id,
                template_code="backend-default",
                risk_level="HIGH",
                risk_item_count=2,
                change_analysis_json="{}",
                risk_card_json="{}",
                created_at=now,
                updated_at=now,
            ),
            CodeQualitySchedulerJob(
                id=7301,
                job_type="AI_REVIEW",
                task_id=task.id,
                project_id=project.id,
                review_key="standard-main",
                status="RUNNING",
                priority=100,
                queued_at=now - timedelta(minutes=2),
                started_at=now - timedelta(minutes=1),
                created_at=now,
                updated_at=now,
            ),
            CodeQualitySchedulerJob(
                id=7302,
                job_type="AGENT_REVIEW",
                task_id=task.id,
                project_id=project.id,
                review_key="agent-main",
                status="QUEUED",
                priority=100,
                queued_at=now,
                created_at=now,
                updated_at=now,
            ),
            CodeQualityReviewResult(
                id=7351,
                task_id=task.id,
                review_key="standard-main",
                project_id=project.id,
                profile_code="backend-default",
                provider="DEEPSEEK",
                model="deepseek-chat",
                display_name="Standard Main",
                sort_order=0,
                status="RUNNING",
                finding_count=0,
                findings_json="[]",
                requested_engine="STANDARD",
                effective_engine="STANDARD",
                started_at=now - timedelta(minutes=1),
                created_at=now,
                updated_at=now,
            ),
            CodeQualityReviewResult(
                id=7352,
                task_id=task.id,
                review_key="agent-main",
                project_id=project.id,
                profile_code="backend-default",
                provider="DEEPSEEK",
                model="deepseek-chat",
                display_name="Agent Main",
                sort_order=1,
                status="SUCCESS",
                overall_level="CRITICAL",
                finding_count=1,
                findings_json=json.dumps([finding]),
                requested_engine="AGENT",
                effective_engine="STANDARD_FALLBACK",
                started_at=now - timedelta(minutes=2),
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
            CodeQualityReviewProgressEvent(
                id=7361,
                task_id=task.id,
                review_key="standard-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context ready",
                detail="must not be selected",
                created_at=now,
            ),
            AgentReviewRun(
                id=7371,
                task_id=task.id,
                review_key="agent-main",
                scheduler_job_id=7302,
                idempotency_key="command-center-agent-run",
                requested_engine="AGENT",
                effective_engine="STANDARD_FALLBACK",
                runner_version="agent-worker-v1",
                model="agent-model",
                status="FAILED",
                created_at=now,
                updated_at=now,
            ),
            DeterministicCheckRun(
                id=7381,
                task_id=task.id,
                project_id=project.id,
                check_type="SECRET_SCAN",
                status="SUCCESS",
                config_snapshot_json="{}",
                findings_json=json.dumps([{"type": "SECRET"}]),
                created_at=now,
                updated_at=now,
            ),
            NotificationRecord(
                id=7391,
                task_id=task.id,
                result_id=7352,
                channel="DINGTALK",
                target="secret-webhook",
                status="FAILED",
                response_body="must never leave backend",
                created_at=now,
                updated_at=now,
            ),
            AgentReviewSettings(
                id=7401,
                enabled=True,
                worker_id="worker-main",
                last_worker_heartbeat_at=now,
                created_at=now,
                updated_at=now,
            ),
            AgentReviewWorker(
                worker_id="worker-main",
                worker_version="v1",
                cli_version="v1",
                state="BUSY",
                capacity=1,
                active_job_id=7302,
                active_run_id=7371,
                started_at=now - timedelta(hours=1),
                last_heartbeat_at=now,
                updated_at=now,
            ),
            CodeQualityReviewSettings(
                id=7411,
                review_enabled=True,
                default_provider_code="DEEPSEEK",
                created_at=now,
                updated_at=now,
            ),
            CodeQualityModelProvider(
                id=7421,
                provider_code="DEEPSEEK",
                provider_name="DeepSeek",
                provider_type="OPENAI_CHAT_COMPATIBLE",
                endpoint_url="https://secret.invalid",
                model_name="deepseek-chat",
                api_key="secret",
                enabled=True,
                built_in=True,
                sort_order=0,
                created_at=now,
                updated_at=now,
            ),
            CodeQualityModelProvider(
                id=7422,
                provider_code="DISABLED",
                provider_name="Disabled",
                provider_type="OPENAI_CHAT_COMPATIBLE",
                enabled=False,
                built_in=False,
                sort_order=10,
                created_at=now,
                updated_at=now,
            ),
            ReviewItemFeedback(
                id=7431,
                project_id=project.id,
                task_id=task.id,
                source_type="AI_FINDING",
                item_fingerprint="cc-feedback-1",
                feedback_type="CONTEXT_MISSING",
                reason_type="CONTEXT_MISSING",
                reason_text="long human text",
                suggest_as_project_rule=True,
                status="PENDING",
                created_at=now,
                updated_at=now,
            ),
            EvaluationCase(
                id=7441,
                project_id=project.id,
                verdict="CONTEXT_MISSING",
                source="FEEDBACK",
                rule_gap_attribution_type="MISSING_RULE",
                human_comment="long human comment",
                created_at=now,
                updated_at=now,
            ),
            EvaluationRun(
                id=7451,
                name="Command Center Evaluation",
                run_type="BASELINE",
                project_id=project.id,
                status="SUCCESS",
                total_count=1,
                completed_count=1,
                failed_count=0,
                created_at=now,
                updated_at=now,
            ),
            ProjectReviewPolicy(
                id=7461,
                project_id=project.id,
                policy_type="PROMPT_RULE",
                title="Sensitive policy",
                content="must never leave backend",
                enabled=True,
                version=1,
                created_at=now,
                updated_at=now,
            ),
            ReviewQualityAcceptanceGate(
                id=7471,
                project_id=project.id,
                title="Command Center Gate",
                change_type="BACKEND",
                status="PASSED",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()


def _project(project_id: int, group_id: int, name: str) -> Project:
    return Project(
        id=project_id,
        group_id=group_id,
        name=name,
        git_provider="GITLAB",
        git_project_id=f"cc-{project_id}",
        repository_url=f"https://gitlab.example.com/command-center/{project_id}",
        default_template_code="backend-default",
        status="ENABLED",
    )


def _task(task_id: int, project_id: int, now: datetime) -> ReviewTask:
    return ReviewTask(
        id=task_id,
        project_id=project_id,
        trigger_type="MERGE_REQUEST",
        external_url=f"https://gitlab.example.com/command-center/{project_id}/-/merge_requests/{task_id}",
        source_branch="feature/runtime-map",
        target_branch="main",
        commit_sha=None,
        after_sha="after-sha",
        author_name="Command Center Author",
        author_username="cc-author",
        template_code="backend-default",
        status="RUNNING",
        review_status="REVIEWING",
        risk_level="HIGH",
        created_at=now - timedelta(hours=1),
        updated_at=now,
    )


def _quality_result(
    result_id: int,
    task_id: int,
    project_id: int,
    review_key: str,
    status: str,
    updated_at: datetime,
) -> CodeQualityReviewResult:
    return CodeQualityReviewResult(
        id=result_id,
        task_id=task_id,
        review_key=review_key,
        project_id=project_id,
        profile_code="backend-default",
        provider="DEEPSEEK",
        model="deepseek-chat",
        display_name=review_key,
        sort_order=0,
        status=status,
        finding_count=0,
        findings_json="[]",
        requested_engine="STANDARD",
        effective_engine="STANDARD",
        created_at=updated_at,
        updated_at=updated_at,
    )


def _scheduler_job(
    job_id: int,
    task_id: int,
    project_id: int,
    review_key: str,
    job_type: str,
    status: str,
    priority: int,
    queued_at: datetime,
    now: datetime,
    *,
    started_at: datetime | None = None,
) -> CodeQualitySchedulerJob:
    return CodeQualitySchedulerJob(
        id=job_id,
        job_type=job_type,
        task_id=task_id,
        project_id=project_id,
        review_key=review_key,
        status=status,
        priority=priority,
        queued_at=queued_at,
        started_at=started_at,
        created_at=now,
        updated_at=now,
    )
