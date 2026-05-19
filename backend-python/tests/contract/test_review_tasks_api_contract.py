from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import GitLabMergeRequestEvent, Project
from app.review_record.models import NotificationRecord, ReviewResult, ReviewTask


def seed_review_task(db_session: Session) -> None:
    created_at = datetime(2026, 5, 18, 10, 0, 0)
    finished_at = datetime(2026, 5, 18, 10, 0, 8)
    db_session.add(
        Project(
            id=1,
            name="demo-service",
            git_provider="GITLAB",
            git_project_id="1001",
            repository_url="https://gitlab.example.com/demo/service",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            default_code_quality_provider_code=None,
            dingtalk_webhook_id=None,
            status="ENABLED",
            description=None,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.add(
        ReviewTask(
            id=10001,
            project_id=1,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="12",
            external_url="https://gitlab.example.com/demo/service/-/merge_requests/12",
            source_branch="feature/risk-demo",
            target_branch="main",
            commit_sha="abcdef123456",
            before_sha=None,
            after_sha=None,
            author_name="Alice",
            author_username="alice",
            template_code="backend-default",
            status="SUCCESS",
            risk_level="HIGH",
            error_message=None,
            started_at=created_at,
            finished_at=finished_at,
            created_at=created_at,
            updated_at=finished_at,
        )
    )
    db_session.add(
        ReviewResult(
            id=20001,
            task_id=10001,
            project_id=1,
            template_code="backend-default",
            risk_level="HIGH",
            risk_item_count=2,
            change_analysis_json=json.dumps(
                {
                    "changeTypes": ["DB", "CACHE"],
                    "changedFileCount": 2,
                    "impactedResources": [],
                }
            ),
            risk_card_json=json.dumps(
                {
                    "riskLevel": "HIGH",
                    "riskItems": [],
                    "focusIndicators": [{"category": "DB_SCHEMA", "riskLevel": "HIGH"}],
                }
            ),
            summary="涉及数据库和缓存变更",
            created_at=finished_at,
            updated_at=finished_at,
        )
    )
    db_session.add(
        GitLabMergeRequestEvent(
            id=30001,
            task_id=10001,
            git_project_id="1001",
            project_name="demo-service",
            mr_id="12",
            event_action="open",
            event_time=created_at,
            source_branch="feature/risk-demo",
            target_branch="main",
            author_name="Alice",
            author_username="alice",
            changed_files_summary=json.dumps([{"path": "src/main/resources/db/V1.sql"}]),
            raw_payload=json.dumps({"object_kind": "merge_request"}),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.add(
        NotificationRecord(
            id=40001,
            task_id=10001,
            result_id=20001,
            channel="DINGTALK",
            target="研发质量群",
            status="SKIPPED",
            request_digest="DINGTALK_WEBHOOK_URL is empty",
            response_body=None,
            error_message=None,
            sent_at=None,
            created_at=finished_at,
            updated_at=finished_at,
        )
    )
    db_session.commit()


def test_review_tasks_read_api_contract(client: TestClient, db_session: Session) -> None:
    seed_review_task(db_session)

    list_response = client.get("/api/review-tasks", params={"keyword": "risk-demo"})
    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    item = list_data["items"][0]
    assert item["id"] == 10001
    assert item["projectName"] == "demo-service"
    assert item["riskLevel"] == "HIGH"
    assert item["riskItemCount"] == 2
    assert item["focusIndicators"] == [{"category": "DB_SCHEMA", "riskLevel": "HIGH"}]

    detail_response = client.get("/api/review-tasks/10001")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["gitProjectId"] == "1001"
    assert detail["mrId"] == "12"
    assert detail["eventAction"] == "open"
    assert detail["changedFilesSummary"] == [{"path": "src/main/resources/db/V1.sql"}]
    assert detail["rawPayload"] == {"object_kind": "merge_request"}

    result_response = client.get("/api/review-tasks/10001/result")
    assert result_response.status_code == 200
    result = result_response.json()["data"]
    assert result["taskId"] == 10001
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "CACHE"]
    assert result["riskCard"]["riskLevel"] == "HIGH"

    notification_response = client.get("/api/review-tasks/10001/notifications")
    assert notification_response.status_code == 200
    notifications = notification_response.json()["data"]
    assert notifications[0]["channel"] == "DINGTALK"
    assert notifications[0]["status"] == "SKIPPED"


def test_review_task_detail_not_found_uses_unified_error(client: TestClient) -> None:
    response = client.get("/api/review-tasks/404")

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"

