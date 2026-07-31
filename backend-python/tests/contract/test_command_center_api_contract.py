from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualitySchedulerJob
from app.evaluation.models import EvaluationCase
from app.project_integration.models import Project
from app.review_feedback.models import ReviewItemFeedback
from app.review_record.models import ReviewTask


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
    "providersObserved",
    "alerts",
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


def test_command_center_empty_database_contract(client: TestClient) -> None:
    runtime_response = client.get("/api/command-center/runtime")
    governance_response = client.get("/api/command-center/governance")

    assert runtime_response.status_code == 200
    runtime = runtime_response.json()["data"]
    assert set(runtime) == RUNTIME_TOP_LEVEL_KEYS
    assert runtime["schemaVersion"] == "command-center-runtime-v1"
    assert runtime["intake"]["taskCount"] == 0
    assert runtime["intake"]["activeTaskCount"] == 0
    assert runtime["scheduler"]["activeJobCount"] == 0
    assert runtime["coverage"]["sections"]["activeFlows"] == "DEFERRED"

    assert governance_response.status_code == 200
    governance = governance_response.json()["data"]
    assert set(governance) == GOVERNANCE_TOP_LEVEL_KEYS
    assert governance["schemaVersion"] == "command-center-governance-v1"
    assert governance["feedback"]["pendingCount"] == 0
    assert governance["evaluation"]["caseCount"] == 0
    assert governance["contextQuality"]["status"] == "DEFERRED"


def test_command_center_returns_real_basic_counts_with_group_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _seed_basic_counts(db_session, now)

    runtime_response = client.get(
        "/api/command-center/runtime",
        params={"windowHours": 24, "groupId": 7001},
    )
    governance_response = client.get(
        "/api/command-center/governance",
        params={"windowHours": 24, "groupId": 7001},
    )

    assert runtime_response.status_code == 200
    runtime = runtime_response.json()["data"]
    assert runtime["intake"]["taskCount"] == 1
    assert runtime["intake"]["activeTaskCount"] == 1
    assert runtime["scheduler"] == {
        "status": "BASIC",
        "scope": "CURRENT_STATE",
        "activeJobCount": 1,
        "queuedJobCount": 1,
        "runningJobCount": 0,
    }

    assert governance_response.status_code == 200
    governance = governance_response.json()["data"]
    assert governance["feedback"]["pendingCount"] == 1
    assert governance["evaluation"]["caseCount"] == 1


def test_command_center_query_parameter_bounds_are_enforced(client: TestClient) -> None:
    assert client.get("/api/command-center/runtime?windowHours=0").status_code == 400
    assert client.get("/api/command-center/runtime?activeLimit=51").status_code == 400
    assert client.get("/api/command-center/runtime?alertLimit=0").status_code == 400
    assert client.get("/api/command-center/governance?windowHours=169").status_code == 400


def test_command_center_requests_execute_select_statements_only(
    client: TestClient,
    db_session: Session,
) -> None:
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
        runtime_response = client.get("/api/command-center/runtime")
        governance_response = client.get("/api/command-center/governance")
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert runtime_response.status_code == 200
    assert governance_response.status_code == 200
    assert statements
    assert all(statement.upper().startswith("SELECT") for statement in statements)

    payload = json.dumps(
        {
            "runtime": runtime_response.json()["data"],
            "governance": governance_response.json()["data"],
        },
        ensure_ascii=False,
    )
    for prohibited in [
        "apiKey",
        "endpointUrl",
        "webhookUrl",
        "prompt",
        "rawOutput",
        "findingsJson",
        "responseBody",
    ]:
        assert prohibited not in payload


def _seed_basic_counts(db_session: Session, now: datetime) -> None:
    db_session.add_all(
        [
            Project(
                id=7101,
                group_id=7001,
                name="command-center-one",
                git_provider="GITLAB",
                git_project_id="cc-7101",
                default_template_code="backend-default",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=7102,
                group_id=7002,
                name="command-center-two",
                git_provider="GITLAB",
                git_project_id="cc-7102",
                default_template_code="backend-default",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            ),
            ReviewTask(
                id=7201,
                project_id=7101,
                trigger_type="MERGE_REQUEST",
                template_code="backend-default",
                status="SUCCESS",
                review_status="NO_RISK",
                created_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
            ),
            ReviewTask(
                id=7202,
                project_id=7101,
                trigger_type="MANUAL",
                template_code="backend-default",
                status="RUNNING",
                review_status="REVIEWING",
                created_at=now - timedelta(days=10),
                updated_at=now,
            ),
            ReviewTask(
                id=7203,
                project_id=7102,
                trigger_type="PUSH",
                template_code="backend-default",
                status="RUNNING",
                review_status="REVIEWING",
                created_at=now - timedelta(hours=2),
                updated_at=now,
            ),
            CodeQualitySchedulerJob(
                id=7301,
                job_type="AI_REVIEW",
                task_id=7202,
                project_id=7101,
                review_key="standard-main",
                status="QUEUED",
                priority=100,
                created_at=now,
                updated_at=now,
            ),
            CodeQualitySchedulerJob(
                id=7302,
                job_type="AGENT_REVIEW",
                task_id=7203,
                project_id=7102,
                review_key="agent-main",
                status="RUNNING",
                priority=100,
                created_at=now,
                updated_at=now,
            ),
            ReviewItemFeedback(
                id=7401,
                project_id=7101,
                task_id=7201,
                source_type="AI_FINDING",
                item_fingerprint="cc-feedback-1",
                feedback_type="FALSE_POSITIVE",
                status="PENDING",
                created_at=now,
                updated_at=now,
            ),
            ReviewItemFeedback(
                id=7402,
                project_id=7102,
                task_id=7203,
                source_type="AI_FINDING",
                item_fingerprint="cc-feedback-2",
                feedback_type="VALID",
                status="PENDING",
                created_at=now,
                updated_at=now,
            ),
            EvaluationCase(
                id=7501,
                project_id=7101,
                verdict="FALSE_POSITIVE",
                source="FEEDBACK",
                created_at=now,
                updated_at=now,
            ),
            EvaluationCase(
                id=7502,
                project_id=7102,
                verdict="CONTEXT_MISSING",
                source="FEEDBACK",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()
