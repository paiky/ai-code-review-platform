from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent_review.models import AgentReviewRun
from app.code_quality.models import CodeQualityReviewResult
from app.evaluation.models import EvaluationCase
from app.project_integration.models import Project, ProjectGroup
from app.review_feedback.models import ReviewItemFeedback
from app.review_record.models import ReviewTask


def test_agent_observation_supports_scope_filters_and_insufficient_sample_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_observation(db_session)

    response = client.get(
        "/api/review-quality/agent-observation",
        params={
            "taskId": 97001,
            "groupId": 9701,
            "projectId": 97001,
            "profile": "backend-observation",
            "startAt": "2026-07-18T08:00:00",
            "endAt": "2026-07-18T12:00:00",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["dataMode"] == "PRODUCTION_OBSERVATION"
    assert data["sampleSummary"]["standardSampleCount"] == 1
    assert data["sampleSummary"]["agentSampleCount"] == 1
    assert data["sampleSummary"]["pairedTaskCount"] == 1
    assert data["annotationProgress"]["annotatedPairedTaskCount"] == 1
    assert data["annotationProgress"]["annotationSampleCount"] == 3
    assert data["findingSummary"]["standardFindingCount"] == 2
    assert data["findingSummary"]["agentFindingCount"] == 1
    assert data["findingSummary"]["humanFalsePositiveCount"] == 1
    assert data["findingSummary"]["contextInsufficientCount"] == 1
    assert data["agentReliability"]["successCount"] == 1
    assert data["agentReliability"]["runCount"] == 1
    assert data["agentReliability"]["fallbackCount"] == 0
    assert data["agentExecutionMetrics"]["durationMs"]["p95"] == 1500
    assert data["agentExecutionMetrics"]["turnCount"]["p50"] == 3
    assert data["agentExecutionMetrics"]["toolCallCount"]["p50"] == 6
    assert data["agentExecutionMetrics"]["sourceBytesReturned"]["p50"] == 2048
    assert data["sampleGate"]["status"] == "INSUFFICIENT_SAMPLE"
    assert data["sampleGate"]["conclusionCalculated"] is False
    assert data["sampleGate"]["expansionConclusion"] is None

    no_match = client.get(
        "/api/review-quality/agent-observation",
        params={"groupId": 999999},
    ).json()["data"]
    assert no_match["sampleSummary"]["taskCount"] == 0


def test_synthetic_demo_needs_no_provider_key_and_remains_explicit(client: TestClient) -> None:
    response = client.get(
        "/api/review-quality/agent-observation",
        params={"syntheticDemo": True, "projectId": 99001, "profile": "stage3a-synthetic-profile"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["dataMode"] == "SYNTHETIC_DEMO"
    assert data["sampleSummary"]["pairedTaskCount"] == 2
    assert data["annotationProgress"]["annotatedPairedTaskCount"] == 2
    assert data["annotationProgress"]["annotationSampleCount"] == 5
    assert data["agentReliability"]["runCount"] == 3
    assert data["agentReliability"]["fallbackCount"] == 1
    assert data["sampleGate"]["status"] == "INSUFFICIENT_SAMPLE"
    assert all(item["synthetic"] is True for item in data["comparisons"])


def test_export_requires_sanitized_scope_and_never_returns_sensitive_content(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_observation(db_session)

    missing_confirmation = client.post(
        "/api/review-quality/agent-observation/export",
        json={"filters": {"projectId": 97001}},
    )
    assert missing_confirmation.status_code == 403
    assert missing_confirmation.json()["code"] == "EXPORT_SCOPE_FORBIDDEN"

    forbidden = client.post(
        "/api/review-quality/agent-observation/export",
        json={
            "confirmation": "SANITIZED_SUMMARY_ONLY",
            "filters": {"projectId": 97001, "includeSource": True},
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "EXPORT_SCOPE_FORBIDDEN"

    response = client.post(
        "/api/review-quality/agent-observation/export",
        json={
            "confirmation": "SANITIZED_SUMMARY_ONLY",
            "filters": {"projectId": 97001, "profile": "backend-observation"},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    payload = json.dumps(data, ensure_ascii=False)
    assert data["redactionPolicy"]["identifiersPseudonymized"] is True
    assert data["redactionPolicy"]["sourceIncluded"] is False
    assert data["filters"]["projectRef"].startswith("project-")
    assert data["comparisons"][0]["taskRef"].startswith("task-")
    assert "Sensitive Production Project" not in payload
    assert "backend-observation" not in payload
    assert "sk-stage3a-do-not-export" not in payload
    assert "FULL_DIFF_MUST_NOT_EXPORT" not in payload
    assert "PROMPT_MUST_NOT_EXPORT" not in payload
    assert "MODEL_REASONING_MUST_NOT_EXPORT" not in payload
    assert "MCP_SOURCE_MUST_NOT_EXPORT" not in payload


def test_agent_observation_rejects_invalid_time_range(client: TestClient) -> None:
    response = client.get(
        "/api/review-quality/agent-observation",
        params={"startAt": "2026-07-19T00:00:00", "endAt": "2026-07-18T00:00:00"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def _seed_observation(db: Session) -> None:
    now = datetime(2026, 7, 18, 10, 0, 0)
    db.add(
        ProjectGroup(
            id=9701,
            group_name="Sensitive Observation Group",
            group_code="observation-sensitive",
            review_engine="STANDARD",
            agent_source_export_allowed=False,
            ai_review_enabled=True,
            trigger_on_manual=True,
            trigger_on_mr=True,
            trigger_on_push=False,
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        Project(
            id=97001,
            group_id=9701,
            name="Sensitive Production Project",
            git_provider="GITLAB",
            git_project_id="97001",
            repository_url="https://gitlab.example.test/sensitive/project.git",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-observation",
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        ReviewTask(
            id=97001,
            project_id=97001,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="97",
            source_branch="feature/observation",
            target_branch="main",
            template_code="backend-default",
            code_quality_profile_code="backend-observation",
            status="SUCCESS",
            review_status="SUCCESS",
            created_at=now,
            updated_at=now,
        )
    )
    db.add_all(
        [
            CodeQualityReviewResult(
                id=97001,
                task_id=97001,
                review_key="standard-observation",
                project_id=97001,
                profile_code="backend-observation",
                provider="DEEPSEEK",
                status="SUCCESS",
                finding_count=2,
                findings_json='[{"title":"one"},{"title":"two"}]',
                raw_output="FULL_DIFF_MUST_NOT_EXPORT",
                requested_engine="STANDARD",
                effective_engine="STANDARD",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
            CodeQualityReviewResult(
                id=97002,
                task_id=97001,
                review_key="agent-observation",
                project_id=97001,
                profile_code="backend-observation",
                provider="AGENT",
                status="SUCCESS",
                finding_count=1,
                findings_json='[{"title":"agent"}]',
                raw_output="MODEL_REASONING_MUST_NOT_EXPORT",
                requested_engine="AGENT",
                effective_engine="AGENT",
                agent_run_id=97001,
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
            CodeQualityReviewResult(
                id=97003,
                task_id=97001,
                review_key="agent-other-profile",
                project_id=97001,
                profile_code="other-profile",
                provider="AGENT",
                status="SUCCESS",
                finding_count=9,
                findings_json='[{"title":"out of filtered profile"}]',
                requested_engine="AGENT",
                effective_engine="AGENT",
                agent_run_id=97002,
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.add_all(
        [
            AgentReviewRun(
            id=97001,
            task_id=97001,
            review_key="agent-observation",
            idempotency_key="agent-observation-97001",
            requested_engine="AGENT",
            effective_engine="AGENT",
            runner_version="agent-worker-v1",
            model="deepseek-v4-pro[1m]",
            status="SUCCEEDED",
            turn_count=3,
            tool_call_count=6,
            source_bytes_returned=2048,
            diff_bytes_returned=512,
            duration_ms=1500,
            usage_json=json.dumps(
                {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "api_key": "sk-stage3a-do-not-export",
                    "prompt": "PROMPT_MUST_NOT_EXPORT",
                }
            ),
            tool_summary_json='{"source":"MCP_SOURCE_MUST_NOT_EXPORT"}',
            input_json='{"diff":"FULL_DIFF_MUST_NOT_EXPORT"}',
            created_at=now,
            updated_at=now,
            ),
            AgentReviewRun(
                id=97002,
                task_id=97001,
                review_key="agent-other-profile",
                idempotency_key="agent-observation-97002",
                requested_engine="AGENT",
                effective_engine="AGENT",
                runner_version="agent-worker-v1",
                model="deepseek-v4-pro[1m]",
                status="SUCCEEDED",
                turn_count=99,
                tool_call_count=99,
                source_bytes_returned=99999,
                diff_bytes_returned=99999,
                duration_ms=99999,
                usage_json='{"input_tokens":99999}',
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.add_all(
        [
            EvaluationCase(
                id=97001,
                task_id=97001,
                review_key="standard-observation",
                fingerprint="standard-finding",
                project_id=97001,
                profile="backend-observation",
                verdict="TRUE_POSITIVE",
                source="AI_FINDING",
                item_snapshot_json='{"sourceSnippet":"MCP_SOURCE_MUST_NOT_EXPORT"}',
                created_at=now,
                updated_at=now,
            ),
            EvaluationCase(
                id=97002,
                task_id=97001,
                review_key="agent-observation",
                fingerprint="agent-finding",
                project_id=97001,
                profile="backend-observation",
                verdict="FALSE_POSITIVE",
                source="AI_FINDING",
                item_snapshot_json='{"prompt":"PROMPT_MUST_NOT_EXPORT"}',
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.add(
        ReviewItemFeedback(
            id=97001,
            project_id=97001,
            task_id=97001,
            source_type="AI_FINDING",
            item_fingerprint="agent-context-feedback",
            review_key="agent-observation",
            feedback_type="USEFUL",
            reason_type="CONTEXT_MISSING",
            reason_text="MCP_SOURCE_MUST_NOT_EXPORT",
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
